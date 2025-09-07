from fastapi import UploadFile, HTTPException
from typing import Any, Dict, List, Optional, Tuple, Union, Iterable, Mapping
import pandas as pd
from io import BytesIO
import base64
import re


# ------------------------------
# Funções utilitárias para Excel
# ------------------------------

def mapear_tipo(dtype_str: str) -> str:
    tipo = dtype_str.lower()
    if tipo in ("int64", "int32", "float64", "float32"):
        return "number"
    elif tipo in ("bool", "boolean"):
        return "boolean"
    elif tipo in ("object", "string"):
        return "string"
    return dtype_str  # fallback: retorna como está


def validar_xlsx(file: UploadFile, nome: str):
    if not file or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, f"Arquivo de {nome} deve ser .xlsx")


async def ler_excel(file: UploadFile) -> Tuple[pd.DataFrame, bytes]:
    try:
        content = await file.read()
        df = pd.read_excel(BytesIO(content), engine="openpyxl")
        return df, content
    except Exception as e:
        raise HTTPException(400, f"Erro ao ler XLSX: {e}")


def decode_excel_base64_df(base64_string: str) -> pd.DataFrame:
    try:
        binary = base64.b64decode(base64_string)
        df = pd.read_excel(BytesIO(binary))
        return df
    except Exception as e:
        raise HTTPException(500, f"Erro ao decodificar Excel: {e}")


def df_para_base64(df: pd.DataFrame) -> str:
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def gerar_colunas_detalhes(df: pd.DataFrame) -> List[dict]:
    return [
        {
            "nome_coluna": col,
            "tipo_coluna": mapear_tipo(str(df[col].dtype)),
            "atributo": False,
        }
        for col in df.columns
    ]


def montar_resposta_coleta(
    id_configuracoes_treinamento,
    atributos,
    id_coleta,
    tipo,
    df_treino,
    df_teste,
    colunas_detalhes,
    arquivo_nome_treino=None,
    arquivo_nome_teste=None,
):
    return {
        "id_configuracoes_treinamento": id_configuracoes_treinamento,
        "id_coleta": id_coleta,
        "tipo": tipo,
        "arquivo_nome_treino": arquivo_nome_treino,
        "arquivo_nome_teste": arquivo_nome_teste,
        "num_linhas_treino": df_treino.shape[0],
        "num_linhas_teste": df_teste.shape[0],
        "num_colunas": df_treino.shape[1],
        "colunas_detalhes": colunas_detalhes,
        "atributos": atributos,
        "preview_treino": df_treino.head(5).to_dict(orient="records"),
        "preview_teste": df_teste.head(5).to_dict(orient="records"),
        "tipo_target": None,
    }


def serialize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc is None:
        return None
    d = dict(doc)  # garante que é mutável
    _id = d.pop("_id", None)
    if _id is not None:
        d["id"] = str(_id)
    return d


# ------------------------------
# Navegação por caminhos aninhados
# ------------------------------

PathPart = Union[str, int]
_SENTINEL = object()


def _parse_path(path: Union[str, Iterable[PathPart]]) -> List[PathPart]:
  """
  Converte um caminho em lista de partes.
  - Suporta filtros em listas: [valor=pca]
  - Ex.: 'modelos[valor=pca].explicacao' vira ['modelos', {'valor':'pca'}, 'explicacao']
  """
  if isinstance(path, (list, tuple)):
      return list(path)
  if not isinstance(path, str):
      return [path]

  # regex captura: colchetes com número [0] ou filtro [valor=pca], ou nome simples
  tokens = re.findall(r'[^.\[\]]+|\[\d+\]|\[.+?=.+?\]', path)
  parts: List[PathPart] = []

  for tok in tokens:
      if tok.startswith("[") and tok.endswith("]"):
          inner = tok[1:-1]
          if "=" in inner:
              k, v = inner.split("=", 1)
              parts.append({k: v})
          else:
              parts.append(int(inner))
      else:
          parts.append(tok)
  return parts

def get_nested(dados: Any, path: Union[str, Iterable[PathPart]], default: Any = _SENTINEL) -> Any:
  """
  Acessa dados aninhados por caminho (dict/lista).
  Suporta filtro de listas: {"valor":"pca"} dentro do caminho.
  """
  atual = dados
  parts = _parse_path(path)

  for i, parte in enumerate(parts):
      if isinstance(parte, int):
          if isinstance(atual, (list, tuple)):
              if 0 <= parte < len(atual):
                  atual = atual[parte]
              elif default is not _SENTINEL:
                  return default
              else:
                  raise KeyError(f"Índice fora do intervalo em {parts} (parte {i}): {parte}")
          elif default is not _SENTINEL:
              return default
          else:
              raise KeyError(f"Valor intermediário não indexável em {parts} (parte {i})")
      elif isinstance(parte, dict):
          # filtro dentro de lista
          if isinstance(atual, list):
              atual = next((x for x in atual if all(x.get(k) == v for k, v in parte.items())), default)
              if atual is None and default is _SENTINEL:
                  raise KeyError(f"Nenhum item corresponde ao filtro {parte} em {parts}")
          else:
              if default is not _SENTINEL:
                  return default
              raise KeyError(f"Valor intermediário não é lista para filtro {parte} em {parts}")
      else:
          if isinstance(atual, Mapping) and parte in atual:
              atual = atual[parte]
          elif default is not _SENTINEL:
              return default
          else:
              raise KeyError(f"Chave ausente em {parts} (parte {i}): {parte}")
  return atual



def concatenar_campos(
    dados: Mapping[str, Any],
    *caminhos: Union[str, Iterable[PathPart]],
    sep: str = " ",
    ignorar_faltantes: bool = False,
    limpar_espacos: bool = True,
) -> str:
    """
    Concatena textos de caminhos (possivelmente aninhados) de um dicionário.

    Parâmetros:
      dados: dicionário base.
      *caminhos: varargs de caminhos ("a.b[0]" ou sequência ("a", "b", 0)).
                 Também aceita uma única lista/tupla com os caminhos.
      sep: separador entre os blocos concatenados.
      ignorar_faltantes: se True, pula caminhos ausentes/None; senão, lança KeyError.
      limpar_espacos: se True, compacta espaços e quebras de linha em cada trecho.
    """
    if len(caminhos) == 1 and isinstance(caminhos[0], (list, tuple)):
        caminhos = tuple(caminhos[0])  # permite passar lista única

    partes: List[str] = []
    for caminho in caminhos:  # type: ignore
        default = None if ignorar_faltantes else _SENTINEL
        valor = get_nested(dados, caminho, default=default)

        if valor is None:
            if ignorar_faltantes:
                continue
            raise KeyError(f"Valor None para caminho: {caminho}")

        texto = str(valor)
        if limpar_espacos:
            texto = " ".join(texto.split())
        partes.append(texto)

    return sep.join(partes)
