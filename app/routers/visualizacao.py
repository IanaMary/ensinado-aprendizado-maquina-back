import base64
import io
import logging
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import arquivos, configuracoes_treinamento
from app.funcoes_genericas.validacao import validar_object_id, MAX_ARQUIVO_BASE64

logger = logging.getLogger(__name__)

router = APIRouter()


class PairplotRequest(BaseModel):
    arquivo_id: str
    configuracao_id: str
    colunas: Optional[List[str]] = None  # Colunas para visualizar (None = todas)
    hue: Optional[str] = None  # Coluna para colorir (target por padrão)


@router.post("/pairplot")
async def gerar_pairplot(request: PairplotRequest):
    """Gera um pairplot (scatter plot matrix) dos dados."""
    logger.info(f"gerar_pairplot called with arquivo_id={request.arquivo_id}")
    
    arquivo_oid = validar_object_id(request.arquivo_id, "arquivo_id")
    configuracao_oid = validar_object_id(request.configuracao_id, "configuracao_id")
    
    # Buscar arquivo
    arquivo_doc = await arquivos.find_one({"_id": arquivo_oid})
    if not arquivo_doc:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    
    # Buscar configuração
    conf_doc = await configuracoes_treinamento.find_one({"_id": configuracao_oid})
    if not conf_doc:
        raise HTTPException(status_code=404, detail="Configuração não encontrada.")
    
    # Ler dados do arquivo
    conteudo_base64 = arquivo_doc.get("content_treino_base64")
    if not conteudo_base64:
        raise HTTPException(status_code=400, detail="Conteúdo do arquivo ausente.")
    
    if len(conteudo_base64) > MAX_ARQUIVO_BASE64:
        raise HTTPException(status_code=413, detail="Arquivo muito grande.")
    
    try:
        conteudo_bytes = base64.b64decode(conteudo_base64)
        try:
            df = pd.read_excel(io.BytesIO(conteudo_bytes), engine="openpyxl")
        except Exception:
            try:
                text = conteudo_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = conteudo_bytes.decode("latin-1")
            sep = ";" in text.split("\n")[0] and ";" or ","
            df = pd.read_csv(io.StringIO(text), sep=sep)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo: {str(e)}")
    
    # Determinar colunas para visualizar
    atributos = [k for k, v in conf_doc.get("atributos", {}).items() if v]
    target = conf_doc.get("target", "")
    
    # Se colunas não foram especificadas, usar atributos + target
    if request.colunas:
        colunas_viz = [c for c in request.colunas if c in df.columns]
    else:
        colunas_viz = atributos.copy()
        if target and target in df.columns and target not in colunas_viz:
            colunas_viz.append(target)
    
    if not colunas_viz:
        raise HTTPException(status_code=400, detail="Nenhuma coluna válida para visualizar.")
    
    # Limitar a 10 colunas para evitar gráficos muito grandes
    if len(colunas_viz) > 10:
        colunas_viz = colunas_viz[:10]
    
    # Determinar hue
    hue = request.hue
    if hue and hue not in df.columns:
        hue = None
    if not hue and target and target in df.columns:
        # Usar target como hue apenas se for categórico (poucos valores únicos)
        if df[target].nunique() <= 20:
            hue = target
    
    # Preparar dados para o pairplot
    df_viz = df[colunas_viz].dropna()
    
    # Limitar a 1000 amostras para performance
    if len(df_viz) > 1000:
        df_viz = df_viz.sample(n=1000, random_state=42)
    
    try:
        # Configurar estilo
        sns.set_theme(style="ticks")
        
        # Gerar pairplot
        g = sns.pairplot(
            df_viz,
            hue=hue,
            diag_kind="kde",
            plot_kws={"alpha": 0.6, "s": 30},
            height=2.5
        )
        
        # Ajustar layout
        g.fig.suptitle("Pairplot - Matriz de Dispersão", y=1.02, fontsize=14, fontweight="bold")
        
        # Converter para base64
        buffer = io.BytesIO()
        g.fig.savefig(buffer, format="png", bbox_inches="tight", dpi=100)
        plt.close(g.fig)
        buffer.seek(0)
        imagem_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        
        return {
            "imagem": imagem_base64,
            "colunas": colunas_viz,
            "hue": hue,
            "total_amostras": len(df_viz)
        }
        
    except Exception as e:
        logger.exception(f"Erro ao gerar pairplot: {e}")
        plt.close("all")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar visualização: {str(e)}")
