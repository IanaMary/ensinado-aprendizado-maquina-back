from fastapi import UploadFile, HTTPException
from typing import Any, Dict, List, Optional, Tuple, Union, Iterable, Mapping
import pandas as pd
from io import BytesIO
import base64
# from typing import Any, Iterable, Mapping
import re

def mapear_tipo(dtype_str: str) -> str:
  tipo = dtype_str.lower()
  if tipo in ("int64", "int32"):
    return "number"
  elif tipo in ("float64", "float32"):
    return "number"
  elif tipo in ("bool", "boolean"):
    return "boolean"
  elif tipo in ("object", "string"):
    return "string"
  else:
    return dtype_str  # fallback: retorna como está


def validar_xlsx(file: UploadFile, nome: str):
  if not file or not file.filename.endswith(".xlsx"):
    raise HTTPException(400, f"Arquivo de {nome} deve ser .xlsx")

async def ler_excel(file: UploadFile) -> Tuple[pd.DataFrame, bytes]:
  try:
    content = await file.read()
    df = pd.read_excel(BytesIO(content), engine='openpyxl')
    return df, content
  except Exception as e:
    raise HTTPException(400, f"Erro ao ler XLSX: {e}")
    
def decode_excel_base64_df(base64_string: str) -> pd.DataFrame:
  try:
    binary = base64.b64decode(base64_string)
    df = pd.read_excel(BytesIO(binary))
    return df
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Erro ao decodificar Excel: {e}")

def df_para_base64(df: pd.DataFrame) -> str:
  buffer = BytesIO()
  df.to_excel(buffer, index=False, engine='openpyxl')
  buffer.seek(0)
  return base64.b64encode(buffer.read()).decode("utf-8")

def gerar_colunas_detalhes(df: pd.DataFrame) -> List[dict]:
  return [
    {
      "nome_coluna": col,
      "tipo_coluna": mapear_tipo(str(df[col].dtype)),
      "atributo": False
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
  arquivo_nome_teste=None
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
    "tipo_target": None
  }



def serialize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
  if doc is None:
    return None
  d = dict(doc)  # garante que é mutável
  _id = d.pop("_id", None)
  if _id is not None:
    d["id"] = str(_id)
  return d



PathPart = Union[str, int]
_SENTINEL = object()

def _parse_path(path: Union[str, Iterable[PathPart]]) -> List[PathPart]:
    """
    Converte um caminho em lista de partes.
    - Se for lista/tupla: mantém as partes como estão (strings e ints).
    - Se for string: usa notação a.b[0].c (ponto e colchetes).
      Obs.: chaves com hífen funcionam; com ponto/colchetes no nome, use lista/tupla.
    """
    if isinstance(path, (list, tuple)):
        return list(path)
    if not isinstance(path, str):
        return [path]  # caso raro: um int ou algo já atômico

    tokens = re.findall(r'[^.\[\]]+|\[\d+\]', path)
    parts: List[PathPart] = []
    for tok in tokens:
        if tok.startswith('[') and tok.endswith(']'):
            parts.append(int(tok[1:-1]))
        else:
            parts.append(tok)
    return parts

def get_nested(dados: Any, path: Union[str, Iterable[PathPart]], default: Any = _SENTINEL) -> Any:
    """
    Acessa dados aninhados por caminho (mapping/lista).
    - path: string "a.b[0].c" OU sequência como ("a", "b", 0, "c").
    - default: valor a retornar se faltar algo (se não fornecido, lança KeyError).
    """
    atual = dados
    parts = _parse_path(path)

    for i, parte in enumerate(parts):
        if isinstance(parte, int):
            if isinstance(atual, (list, tuple)):
                if 0 <= parte < len(atual):
                    atual = atual[parte]
                else:
                    if default is not _SENTINEL:
                        return default
                    raise KeyError("Índice fora do intervalo em {} (parte {}): {}".format(parts, i, parte))
            else:
                if default is not _SENTINEL:
                    return default
                raise KeyError("Valor intermediário não indexável por inteiro em {} (parte {}).".format(parts, i))
        else:
            if isinstance(atual, Mapping) and parte in atual:
                atual = atual[parte]
            else:
                if default is not _SENTINEL:
                    return default
                raise KeyError("Chave ausente em {} (parte {}): {!r}".format(parts, i, parte))
    return atual


PathPart = Union[str, int]
_SENTINEL = object()

def _parse_path(path: Union[str, Iterable[PathPart]]) -> List[PathPart]:
    """
    Converte um caminho em lista de partes.
    - Se for lista/tupla: mantém as partes como estão (strings e ints).
    - Se for string: usa notação a.b[0].c (ponto e colchetes).
      Obs.: chaves com hífen funcionam; com ponto/colchetes no nome, use lista/tupla.
    """
    if isinstance(path, (list, tuple)):
        return list(path)
    if not isinstance(path, str):
        return [path]  # caso raro: um int ou algo já atômico

    tokens = re.findall(r'[^.\[\]]+|\[\d+\]', path)
    parts: List[PathPart] = []
    for tok in tokens:
        if tok.startswith('[') and tok.endswith(']'):
            parts.append(int(tok[1:-1]))
        else:
            parts.append(tok)
    return parts

def get_nested(dados: Any, path: Union[str, Iterable[PathPart]], default: Any = _SENTINEL) -> Any:
    """
    Acessa dados aninhados por caminho (mapping/lista).
    - path: string "a.b[0].c" OU sequência como ("a", "b", 0, "c").
    - default: valor a retornar se faltar algo (se não fornecido, lança KeyError).
    """
    atual = dados
    parts = _parse_path(path)

    for i, parte in enumerate(parts):
        if isinstance(parte, int):
            if isinstance(atual, (list, tuple)):
                if 0 <= parte < len(atual):
                    atual = atual[parte]
                else:
                    if default is not _SENTINEL:
                        return default
                    raise KeyError("Índice fora do intervalo em {} (parte {}): {}".format(parts, i, parte))
            else:
                if default is not _SENTINEL:
                    return default
                raise KeyError("Valor intermediário não indexável por inteiro em {} (parte {}).".format(parts, i))
        else:
            if isinstance(atual, Mapping) and parte in atual:
                atual = atual[parte]
            else:
                if default is not _SENTINEL:
                    return default
                raise KeyError("Chave ausente em {} (parte {}): {!r}".format(parts, i, parte))
    return atual

def concatenar_campos(
    dados: Mapping[str, Any],
    *caminhos: Union[str, Iterable[PathPart]],
    sep: str = " ",
    ignorar_faltantes: bool = False,
    limpar_espacos: bool = True,
) -> str:
    """
    Concatena textos de caminhos (possivelmente aninhados) do dicionário.

    Parâmetros:
      dados: dicionário base.
      *caminhos: varargs de caminhos (string "a.b[0]" ou sequência ("a", "b", 0)).
                 Também aceita passar uma única lista/tupla com os caminhos.
      sep: separador entre os blocos concatenados.
      ignorar_faltantes: se True, pula caminhos ausentes/None; caso contrário, lança KeyError.
      limpar_espacos: se True, compacta espaços e quebras de linha em cada trecho.
    """
    # Permite passar uma coleção única de caminhos
    if len(caminhos) == 1 and isinstance(caminhos[0], (list, tuple)):
        caminhos = tuple(caminhos[0])  # type: ignore

    partes: List[str] = []
    for caminho in caminhos:  # type: ignore
        default = None if ignorar_faltantes else _SENTINEL
        valor = get_nested(dados, caminho, default=default)

        if valor is None:
            if ignorar_faltantes:
                continue
            raise KeyError("Valor None para caminho: {!r}".format(caminho))

        texto = str(valor)
        if limpar_espacos:
            texto = " ".join(texto.split())
        partes.append(texto)

    return sep.join(partes)

# resumo = concatenar_campos(
#     obj,
#     ["texto-pipe",
#     "planilha_de_treino",
#     "secoes[0].texto",
#     "metadados.autor"]
#     ("config", "porta.http"),   # chave com ponto -> passe como sequência
#     sep="\n\n",
# )