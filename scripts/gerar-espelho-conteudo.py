#!/usr/bin/env python3
"""Regenera o espelho legível `base_de_conhecimento/catalogo_tutor/` a partir da
fonte canônica versionada (`app/conteudo/*.json`).

O espelho é só para leitura humana — a fonte da verdade são os JSON em app/conteudo,
aplicados no MongoDB por scripts/deploy/seed_conteudo.py. Rode este gerador depois de
editar o conteúdo, para manter o espelho em dia.

Uso:  python scripts/gerar-espelho-conteudo.py
"""
import json, os

_AQUI = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(_AQUI)
RAIZ = os.path.dirname(BACKEND)  # workspace pai (.../Projetos/Iana)
SRC = os.path.join(BACKEND, "app/conteudo")
OUT = os.path.join(RAIZ, "base_de_conhecimento/catalogo_tutor")

CATS = [
    ("modelos", "Modelos", "modelos"),
    ("metricas", "Métricas", "metricas"),
    ("pre_processamento", "Pré-processamento", "pre_processamento"),
    ("coleta_dados", "Coleta de dados", "coleta_dados"),
    ("graficos", "Gráficos (visualizações)", "graficos"),
]


def load(cat):
    p = os.path.join(SRC, f"{cat}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def lista(c, chave):
    return [x for x in (c.get(chave) or []) if x]


def ficha_md(valor, c):
    L = []
    L.append(f"# {c.get('titulo', valor)}\n")
    L.append(f"`{valor}`\n")
    if c.get("resumo_basico"):
        L.append("## Em palavras simples (Básico)\n")
        L.append(c["resumo_basico"] + "\n")
    if c.get("descricao"):
        L.append("## Descrição (Avançado)\n")
        L.append(c["descricao"] + "\n")
    if c.get("intuicao"):
        L.append("## Intuição\n")
        L.append(c["intuicao"] + "\n")
    if c.get("formula"):
        L.append("## Fórmula\n")
        L.append("`" + c["formula"] + "`\n")
    conceitos = lista(c, "conceitos")
    if conceitos:
        L.append("## Conceitos\n")
        for x in conceitos:
            L.append(f"- **{x.get('nome','')}**: {x.get('desc','')}")
        L.append("")
    for chave, titulo in [("quandoUsar", "Quando usar"), ("naoUsarQuando", "Quando evitar"),
                          ("vantagens", "Vantagens"), ("desvantagens", "Desvantagens"),
                          ("dicas", "Dicas")]:
        itens = lista(c, chave)
        if itens:
            L.append(f"## {titulo}\n")
            for x in itens:
                L.append(f"- {x}")
            L.append("")
    if c.get("exemplo"):
        L.append("## Exemplo\n")
        L.append(c["exemplo"] + "\n")
    if c.get("exemplo_codigo"):
        L.append("## Exemplo de código\n")
        L.append("```python")
        L.append(c["exemplo_codigo"])
        L.append("```\n")
    hipers = lista(c, "hiperparametros_doc")
    if hipers:
        L.append("## Hiperparâmetros\n")
        L.append("| nome | padrão | tipo | faixa/opções | efeito |")
        L.append("|---|---|---|---|---|")
        for h in hipers:
            faixa = ", ".join(str(o) for o in h["opcoes"]) if isinstance(h.get("opcoes"), list) else (h.get("faixa") or "")
            efeito = (h.get("efeito") or "").replace("\n", " ")
            L.append(f"| `{h.get('nome','')}` | {h.get('default','')} | {h.get('tipo','')} | {faixa} | {efeito} |")
        L.append("")
    refs = lista(c, "referencias")
    if refs:
        L.append("## Referências\n")
        for r in refs:
            if r.get("url"):
                L.append(f"- [{r.get('titulo', r['url'])}]({r['url']})")
            elif r.get("titulo"):
                L.append(f"- {r['titulo']}")
        L.append("")
    link = c.get("link_sklearn") or c.get("link_yellowbrick")
    if link:
        L.append(f"Documentação oficial: <{link}>")
    return "\n".join(L) + "\n"


def main():
    if not os.path.isdir(os.path.dirname(OUT)):
        print(f"Espelho não encontrado em {OUT} — pulando (backend isolado?).")
        return
    catalogo = {}
    index = ["# Índice do Catálogo do Tutor\n",
             "Espelho legível do conteúdo educacional. **Fonte da verdade:** "
             "`ensinado-aprendizado-maquina-back/app/conteudo/*.json` (versionado) → seed → MongoDB. "
             "Regenerar com o gerador a partir dessa fonte; não editar à mão.\n"]
    for cat, titulo, pasta in CATS:
        dados = load(cat)
        catalogo[cat] = dados
        destino = os.path.join(OUT, pasta)
        os.makedirs(destino, exist_ok=True)
        # remove fichas antigas .md
        for f in os.listdir(destino):
            if f.endswith(".md"):
                os.remove(os.path.join(destino, f))
        index.append(f"## {titulo} ({len(dados)})\n")
        for valor in sorted(dados):
            c = dados[valor]
            with open(os.path.join(destino, f"{valor}.md"), "w", encoding="utf-8") as f:
                f.write(ficha_md(valor, c))
            index.append(f"- [{c.get('titulo', valor)}]({pasta}/{valor}.md) — `{valor}`")
        index.append("")
    json.dump(catalogo, open(os.path.join(OUT, "catalogo_ml.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, sort_keys=True)
    open(os.path.join(OUT, "INDEX.md"), "w", encoding="utf-8").write("\n".join(index) + "\n")
    total = sum(len(load(c)) for c, _, _ in CATS)
    print(f"Espelho regenerado: {total} fichas em {len(CATS)} categorias.")
    for cat, _, _ in CATS:
        print(f"  {cat}: {len(load(cat))}")


if __name__ == "__main__":
    main()
