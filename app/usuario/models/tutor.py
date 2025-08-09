from pydantic import BaseModel
from fastapi import HTTPException
from typing import List

import re

from app.database import tutor

async def obter_arvore():
    arvore = await tutor.find_one()
    if arvore is None:
        raise HTTPException(status_code=404, detail="Árvore não encontrada")
    arvore.pop("_id", None)
    return arvore

def tem_condicoes_validas(lista):
    if not isinstance(lista, list) or len(lista) == 0:
        return False
    for item in lista:
        if "condicao" in item and item["condicao"].strip():
            return True
    return False

def extrair_variaveis(condicao):
    tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', condicao)
    keywords = {"and", "or", "not", "True", "False"}
    vars = [t for t in tokens if t not in keywords]
    return vars

def todas_variaveis_presentes(lista_condicoes, contexto):
    for item in lista_condicoes:
        cond = item.get("condicao", "")
        vars = extrair_variaveis(cond)
        for v in vars:
            if v not in contexto:
                return False
    return True

def formatar_descricao(descricao):
    # Se for lista, tentar extrair texto concatenado
    if isinstance(descricao, list):
        textos = []
        for item in descricao:
            if isinstance(item, dict):
                texto = item.get("texto", "")
                itens = item.get("itens", [])
                textos.append(texto)
                if itens:
                    textos.append("\n- " + "\n- ".join(itens))
            elif isinstance(item, str):
                textos.append(item)
        return "\n".join(textos).strip()
    # Se for string, retorna direto
    elif isinstance(descricao, str):
        return descricao.strip()
    # Caso contrário
    return ""

def avaliar_condicoes(lista_condicoes, contexto):
    for item in lista_condicoes:
        cond = item.get("condicao", "")
        try:
            cond_verdadeira = False
            try:
                cond_verdadeira = eval(cond, {}, contexto)
            except Exception:
                cond_verdadeira = False

            if cond_verdadeira:
                resultado = item.get("resultado")
                descricao = formatar_descricao(item.get("descricao", ""))

                # Se resultado for lista (subcondições)
                if isinstance(resultado, list) and tem_condicoes_validas(resultado):
                    if todas_variaveis_presentes(resultado, contexto):
                        desc_rec = avaliar_condicoes(resultado, contexto)
                        if desc_rec != "Nenhuma condição satisfeita":
                            return desc_rec
                        else:
                            return descricao
                    else:
                        return descricao
                # Se resultado for string JSON (não parece seu caso atual)
                elif isinstance(resultado, str):
                    resultado_strip = resultado.strip()
                    if resultado_strip.startswith("[") or resultado_strip.startswith("{"):
                        import json
                        try:
                            resultado_json = json.loads(resultado)
                            if isinstance(resultado_json, list) and tem_condicoes_validas(resultado_json):
                                if todas_variaveis_presentes(resultado_json, contexto):
                                    desc_rec = avaliar_condicoes(resultado_json, contexto)
                                    if desc_rec != "Nenhuma condição satisfeita":
                                        return desc_rec
                                    else:
                                        return descricao
                                else:
                                    return descricao
                            else:
                                return descricao
                        except Exception:
                            return descricao
                    else:
                        return descricao
                else:
                    return descricao

        except Exception as e:
            print(f"Erro ao avaliar condição '{cond}': {e}")
            continue

    return "Nenhuma condição satisfeita"

def atualizar_descricao_recursiva(lista_condicoes, contexto, nova_desc):
    import re

    def extrair_variaveis(condicao):
        tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', condicao)
        keywords = {"and", "or", "not", "True", "False"}
        vars = [t for t in tokens if t not in keywords]
        return vars

    for item in lista_condicoes:
        cond = item.get("condicao", "")
        vars = extrair_variaveis(cond)
        if not all(v in contexto for v in vars):
            continue
        try:
            if eval(cond, {}, contexto):
                item["descricao"] = nova_desc
                return True
        except Exception:
            continue
        resultado = item.get("resultado")
        if isinstance(resultado, list):
            if atualizar_descricao_recursiva(resultado, contexto, nova_desc):
                return True
    return False
