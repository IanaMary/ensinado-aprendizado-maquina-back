import base64
import hashlib
import logging
from io import BytesIO
from typing import Callable, Dict, Any, List
import bson.json_util as bson
import joblib
from fastapi import APIRouter, HTTPException
from app.deps import pd
from app.schemas.schemas import DatasetRequest
from app.database import configuracoes_treinamento, arquivos, opcoes_modelos, modelos_treinados
from app.utils.seed import get_sklearn_random_state
from app.funcoes_genericas.funcoes_genericas import converter_numpy
from app.funcoes_genericas.validacao import validar_object_id, MAX_ARQUIVO_BASE64

logger = logging.getLogger(__name__)


async def treinar_modelo_generico(
    request: DatasetRequest,
    nome_modelo_label: str,
    instancia_classe: Callable,
    **kwargs_adicionais
) -> Dict[str, Any]:
    """Treina um modelo genérico e retorna o resultado."""
    logger.info(f"treinar_modelo_generico iniciado para {nome_modelo_label}")
    logger.debug(f"Request: {request.model_dump()}")
    tipo = request.tipo_arquivo.lower()

    arquivo_oid = validar_object_id(request.arquivo_id, "arquivo_id")
    configuracao_oid = validar_object_id(request.configuracao_id, "configuracao_id")
    modelo_oid = validar_object_id(request.modelo_id, "modelo_id")

    arquivo_doc = await arquivos.find_one({"_id": arquivo_oid})
    if not arquivo_doc:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    conf_doc = await configuracoes_treinamento.find_one({"_id": configuracao_oid})
    if not conf_doc:
        raise HTTPException(status_code=404, detail="Configuração de treino não encontrada.")

    modelo_doc = await opcoes_modelos.find_one({"_id": modelo_oid})
    if not modelo_doc:
        raise HTTPException(status_code=404, detail="Modelo de treino não encontrado.")
    
    hiperparametros = {
        h["nomeHiperparametro"]: h["valorPadrao"]
        for h in modelo_doc.get("hiperparametros", [])
    }
    
    # Aplicar seed global se configurado (apenas se o modelo suportar)
    import inspect
    sig = inspect.signature(instancia_classe.__init__)
    if "random_state" in sig.parameters:
        random_state = get_sklearn_random_state()
        if random_state is not None:
            hiperparametros["random_state"] = random_state
    
    atributos: List[str] = [k for k, v in conf_doc.get("atributos", {}).items() if v]
    target: str = conf_doc.get("target")
    
    # Verificar se é clustering (sem target)
    is_clustering = target is None or target == ""
    
    conteudo_base64 = arquivo_doc.get("content_treino_base64")
    if not conteudo_base64:
        raise HTTPException(status_code=400, detail="Conteúdo do arquivo ausente ou mal formatado.")

    if len(conteudo_base64) > MAX_ARQUIVO_BASE64:
        raise HTTPException(status_code=413, detail="Arquivo de treino muito grande. O limite é de 50 MB.")

    try:
        conteudo_bytes = base64.b64decode(conteudo_base64)
        # Tenta Excel primeiro, depois CSV
        try:
            df = pd.read_excel(BytesIO(conteudo_bytes), engine="openpyxl")
        except Exception:
            try:
                text = conteudo_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = conteudo_bytes.decode("latin-1")
            sep = ";" in text.split("\n")[0] and ";" or ","
            df = pd.read_csv(pd.io.common.StringIO(text), sep=sep)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar o arquivo: {str(e)}")
    
    # Validar colunas
    colunas_necessarias = atributos.copy()
    if not is_clustering and target:
        colunas_necessarias.append(target)
    
    for col in colunas_necessarias:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Coluna '{col}' não encontrada nos dados de treino.")
    
    X_train = df[atributos]
    
    # Verificar valores ausentes
    if X_train.isnull().any().any():
        raise HTTPException(
            status_code=400,
            detail="Os dados de treino contêm valores ausentes. Remova ou preencha os valores vazios antes de treinar."
        )
    
    # Para modelos supervisionados, verificar target
    if not is_clustering:
        y_train = df[target]
        if y_train.isnull().any():
            raise HTTPException(
                status_code=400,
                detail="Os dados de treino contêm valores ausentes no target. Remova ou preencha os valores vazios antes de treinar."
            )
        if y_train.nunique() < 2:
            raise HTTPException(status_code=400, detail="O alvo precisa de pelo menos duas classes para treinar o modelo.")

    try:
        hiperparametros.update(kwargs_adicionais)
        modelo = instancia_classe(**hiperparametros)
        
        # Treinar modelo (clustering usa apenas X_train)
        if is_clustering:
            modelo.fit(X_train)
        else:
            modelo.fit(X_train, y_train)
        
        # Serializa com joblib (seguro e eficiente)
        buffer = BytesIO()
        joblib.dump(modelo, buffer)
        modelo_bytes = buffer.getvalue()
        
        # Calcula checksum de validação
        checksum = hashlib.sha256(modelo_bytes).hexdigest()
        
        # Para clustering, não há classes
        classes = []
        if hasattr(modelo, 'classes_'):
            classes = list(map(str, modelo.classes_))
        elif hasattr(modelo, 'labels_'):
            classes = list(map(str, sorted(set(modelo.labels_))))
        
        result = await modelos_treinados.insert_one({
            "arquivo_id": request.arquivo_id,
            "arq_teste": arquivo_doc.get("content_teste_base64"),
            "hiperparametros": hiperparametros,
            "atributos": atributos,
            "target": target,
            "classes": classes,
            "modelo_treinado": bson.Binary(modelo_bytes),
            "checksum": checksum,
            "modelo": modelo_doc.get('valor'),
        })
        
        id_result = str(result.inserted_id)
        
    except Exception as e:
        logger.exception(f"treinar_modelo_generico falhou: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no treinamento: {str(e)}")
    
    # Calcular total de amostras de teste se disponível
    total_amostras_teste = 0
    conteudo_teste_base64 = arquivo_doc.get("content_teste_base64")
    if conteudo_teste_base64:
        try:
            teste_bytes = base64.b64decode(conteudo_teste_base64)
            try:
                df_teste = pd.read_excel(BytesIO(teste_bytes), engine="openpyxl")
            except Exception:
                try:
                    text_teste = teste_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text_teste = teste_bytes.decode("latin-1")
                sep_teste = ";" in text_teste.split("\n")[0] and ";" or ","
                df_teste = pd.read_csv(pd.io.common.StringIO(text_teste), sep=sep_teste)
            total_amostras_teste = len(df_teste)
        except Exception as e:
            logger.warning(f"Erro ao contar amostras de teste: {e}")
    
    # Construir dicionário de valores padrão dos hiperparâmetros
    hiperparametros_padrao = {
        h["nomeHiperparametro"]: h["valorPadrao"]
        for h in modelo_doc.get("hiperparametros", [])
    }
    
    # Para clustering, não há classes
    classes = []
    if hasattr(modelo, 'classes_'):
        classes = list(modelo.classes_)
    elif hasattr(modelo, 'labels_'):
        classes = list(sorted(set(modelo.labels_)))
    
    return converter_numpy({
        "atributos": atributos,
        "target": target,
        "modelo_treinado": str(modelo),
        "status": f"modelo {nome_modelo_label} treinado com sucesso",
        "total_amostras_treino": len(X_train),
        "total_amostras_teste": total_amostras_teste,
        "hiperparametros": modelo.get_params(),
        "hiperparametros_padrao": hiperparametros_padrao,
        "classes": classes,
        "modelo": nome_modelo_label.lower().replace(" ", "_"),
        "nome_modelo": modelo_doc.get('label'),
        "id": id_result
    })
