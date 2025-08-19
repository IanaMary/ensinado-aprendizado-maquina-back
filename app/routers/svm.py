
from app.schemas.schemas import DatasetRequest
from app.deps import pd, SVC
from fastapi import APIRouter, HTTPException
from typing import List
from io import BytesIO
from app.database import configuracoes_treinamento, arquivos, opcoes_modelos, modelos_treinados
from bson import ObjectId
import bson
import pickle
import base64

router = APIRouter()


@router.post("/svm")
async def treinar_svm(request: DatasetRequest):
    tipo = request.tipo_arquivo.lower()
    arquivo_id = request.arquivo_id
    conf_treino_id = request.configuracao_id
    modelo_id = request.modelo_id
    
    arquivo_doc = await arquivos.find_one({"_id": ObjectId(arquivo_id)})
    if not arquivo_doc:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    
    conf_doc = await configuracoes_treinamento.find_one({"_id": ObjectId(conf_treino_id)})
    if not conf_doc:
        raise HTTPException(status_code=404, detail="Configuração de treino não encontrada.")
    
    modelo_doc = await opcoes_modelos.find_one({"_id": ObjectId(modelo_id)})
    if not modelo_doc:
        raise HTTPException(status_code=404, detail="Modelo de treino não encontrada.")
    
    hiperparametros = {
        h["nomeHiperparametro"]: h["valorPadrao"]
        for h in modelo_doc.get("hiperparametros", [])
    }
            
    atributos: List[str] = [k for k, v in conf_doc.get("atributos", {}).items() if v]
    target: str = conf_doc.get("target")

    conteudo_base64 = arquivo_doc.get("content_treino_base64")
    if not conteudo_base64:
        raise HTTPException(status_code=400, detail="Conteúdo do arquivo ausente ou mal formatado.")

    try:
        conteudo_bytes = base64.b64decode(conteudo_base64)
        if tipo == "xlsx":
            df = pd.read_excel(BytesIO(conteudo_bytes))
        elif tipo == "csv":
            df = pd.read_csv(BytesIO(conteudo_bytes))
        elif tipo == "json":
            df = pd.read_json(BytesIO(conteudo_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar o arquivo: {str(e)}")

    # Verificação das colunas
    for col in atributos + [target]:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Coluna '{col}' não encontrada nos dados de treino.")

    # Separação X e y
    X_train = df[atributos]
    y_train = df[target]

    try:
        modelo = SVC(**hiperparametros)
        modelo.fit(X_train, y_train)
        
        # Serializa com joblib
        modelo_bytes = bson.Binary(pickle.dumps(modelo))
        
        result = await modelos_treinados.insert_one({
            "arq_treinamento":  conteudo_base64,
            "arq_teste":  arquivo_doc.get("content_teste_base64"),
            "hiperparametros": hiperparametros,
            "atributos": atributos,
            "target": target,
            "modelo_treinado": modelo_bytes,
            "modelo": modelo_doc.get('valor'),
        })
        
        id_result = str(result.inserted_id)
    
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao treinar o modelo: {str(e)}")

    return {
        "atributos": atributos,
        "target": target,
        "modelo_treinado": str(modelo),
        "status": "modelo svm treinado com sucesso",
        "total_amostras_treino": len(X_train),
        "hiperparametros": modelo.get_params(),
        "classes": list(modelo.classes_),
        "modelo": "svm",
        "nome_modelo": modelo_doc.get('label'),
        "id": id_result
    }
