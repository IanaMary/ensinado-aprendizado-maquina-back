import base64
import hashlib
import re
from io import BytesIO
from typing import Callable, Dict, Any, List
from bson.objectid import ObjectId
import bson.json_util as bson
import joblib
from fastapi import APIRouter, HTTPException
from app.deps import pd
from app.schemas.schemas import DatasetRequest
from app.database import configuracoes_treinamento, arquivos, opcoes_modelos, modelos_treinados
from app.utils.seed import get_sklearn_random_state


HEX_24 = re.compile(r"^[0-9a-fA-F]{24}$")


def _validar_object_id(valor: str, nome_campo: str) -> ObjectId:
    """Valida e converte uma string em ObjectId, retornando 400 em vez de 500 quando inválida."""
    if not valor or not isinstance(valor, str) or not HEX_24.match(valor):
        raise HTTPException(
            status_code=400,
            detail=f"Identificador inválido para '{nome_campo}'. É necessário um ObjectId de 24 caracteres hexadecimais."
        )
    return ObjectId(valor)


async def treinar_modelo_generico(
    request: DatasetRequest,
    nome_modelo_label: str,
    instancia_classe: Callable,
    **kwargs_adicionais
) -> Dict[str, Any]:
    """Treina um modelo genérico e retorna o resultado."""
    tipo = request.tipo_arquivo.lower()

    arquivo_oid = _validar_object_id(request.arquivo_id, "arquivo_id")
    configuracao_oid = _validar_object_id(request.configuracao_id, "configuracao_id")
    modelo_oid = _validar_object_id(request.modelo_id, "modelo_id")

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
    
    # Aplicar seed global se configurado
    random_state = get_sklearn_random_state()
    if random_state is not None:
        hiperparametros["random_state"] = random_state
    
    atributos: List[str] = [k for k, v in conf_doc.get("atributos", {}).items() if v]
    target: str = conf_doc.get("target")
    
    conteudo_base64 = arquivo_doc.get("content_treino_base64")
    if not conteudo_base64:
        raise HTTPException(status_code=400, detail="Conteúdo do arquivo ausente ou mal formatado.")
    
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
    
    for col in atributos + [target]:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Coluna '{col}' não encontrada nos dados de treino.")
    
    X_train = df[atributos]
    y_train = df[target]
    
    try:
        hiperparametros.update(kwargs_adicionais)
        modelo = instancia_classe(**hiperparametros)
        modelo.fit(X_train, y_train)
        
        # Serializa com joblib (seguro e eficiente)
        buffer = BytesIO()
        joblib.dump(modelo, buffer)
        modelo_bytes = buffer.getvalue()
        
        # Calcula checksum de validação
        checksum = hashlib.sha256(modelo_bytes).hexdigest()
        
        result = await modelos_treinados.insert_one({
            "arquivo_id": request.arquivo_id,
            "arq_teste": arquivo_doc.get("content_teste_base64"),
            "hiperparametros": hiperparametros,
            "atributos": atributos,
            "target": target,
            "modelo_treinado": bson.Binary(modelo_bytes),
            "checksum": checksum,
            "modelo": modelo_doc.get('valor'),
        })
        
        id_result = str(result.inserted_id)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao treinar o modelo: {str(e)}")
    
    return {
        "atributos": atributos,
        "target": target,
        "modelo_treinado": str(modelo),
        "status": f"modelo {nome_modelo_label} treinado com sucesso",
        "total_amostras_treino": len(X_train),
        "hiperparametros": modelo.get_params(),
        "classes": list(modelo.classes_),
        "modelo": nome_modelo_label.lower().replace(" ", "_"),
        "nome_modelo": modelo_doc.get('label'),
        "id": id_result
    }
