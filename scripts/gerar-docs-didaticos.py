#!/usr/bin/env python3
"""Gera material didático em Markdown (uma ficha por elemento + um consolidado por
categoria + índice) para uso na dissertação. Fonte: app/conteudo/*.json (fonte
canônica versionada).

Cada ficha tem os dois níveis (Básico/Avançado), fórmula, conceitos, quando usar/
evitar, vantagens/desvantagens, exemplo de código Python e referências oficiais.

Uso:  python scripts/gerar-docs-didaticos.py
Saída: ../docs/conteudo-didatico/ (no workspace pai).
"""
import json, os

_AQUI = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(_AQUI)
RAIZ = os.path.dirname(BACKEND)  # workspace pai (.../Projetos/Iana)
SRC = os.path.join(BACKEND, "app/conteudo")
OUT = os.path.join(RAIZ, "docs/conteudo-didatico")

CATS = [
    ("modelos", "Modelos de Machine Learning"),
    ("metricas", "Métricas de Avaliação"),
    ("pre_processamento", "Pré-processamento de Dados"),
    ("coleta_dados", "Coleta de Dados"),
    ("graficos", "Gráficos de Avaliação (Visualizações)"),
]


def load(cat):
    p = os.path.join(SRC, f"{cat}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def itens(c, chave):
    return [x for x in (c.get(chave) or []) if x]


def secao(titulo, corpo):
    return f"## {titulo}\n\n{corpo}\n" if corpo else ""


def ficha(valor, c, categoria_label, nivel="##"):
    """Monta a ficha didática de um elemento. nivel = nível base dos headings."""
    h = nivel
    L = [f"{h} {c.get('titulo', valor)}\n",
         f"> **Categoria:** {categoria_label} · **Identificador:** `{valor}`\n"]

    def sub(t, corpo):
        return f"{h}# {t}\n\n{corpo}\n" if corpo else ""

    if c.get("resumo_basico"):
        L.append(sub("Explicação acessível (nível Básico)", c["resumo_basico"]))
    if c.get("descricao"):
        L.append(sub("Fundamentação técnica (nível Avançado)", c["descricao"]))
    if c.get("intuicao"):
        L.append(sub("Intuição", c["intuicao"]))
    if c.get("formula"):
        L.append(f"{h}# Fórmula\n\n$$\n{c['formula']}\n$$\n")
    conceitos = itens(c, "conceitos")
    if conceitos:
        L.append(f"{h}# Conceitos-chave\n")
        for x in conceitos:
            L.append(f"- **{x.get('nome','')}** — {x.get('desc','')}")
        L.append("")
    qu, nq = itens(c, "quandoUsar"), itens(c, "naoUsarQuando")
    if qu or nq:
        L.append(f"{h}# Quando usar e quando evitar\n")
        if qu:
            L.append("**Quando usar:**\n")
            L += [f"- {x}" for x in qu]
            L.append("")
        if nq:
            L.append("**Quando evitar:**\n")
            L += [f"- {x}" for x in nq]
            L.append("")
    va, de = itens(c, "vantagens"), itens(c, "desvantagens")
    if va or de:
        L.append(f"{h}# Vantagens e desvantagens\n")
        if va:
            L.append("**Vantagens:**\n")
            L += [f"- {x}" for x in va]
            L.append("")
        if de:
            L.append("**Desvantagens:**\n")
            L += [f"- {x}" for x in de]
            L.append("")
    dicas = itens(c, "dicas")
    if dicas:
        L.append(f"{h}# Dicas\n")
        L += [f"- {x}" for x in dicas]
        L.append("")
    if c.get("exemplo"):
        L.append(sub("Exemplo", c["exemplo"]))
    if c.get("exemplo_codigo"):
        L.append(f"{h}# Exemplo de código (Python)\n\n```python\n{c['exemplo_codigo']}\n```\n")
    hipers = itens(c, "hiperparametros_doc")
    if hipers:
        L.append(f"{h}# Hiperparâmetros\n")
        L.append("| Nome | Padrão | Tipo | Faixa / opções | Efeito |")
        L.append("|---|---|---|---|---|")
        for hp in hipers:
            faixa = ", ".join(str(o) for o in hp["opcoes"]) if isinstance(hp.get("opcoes"), list) else (hp.get("faixa") or "")
            efeito = (hp.get("efeito") or "").replace("\n", " ").replace("|", "\\|")
            L.append(f"| `{hp.get('nome','')}` | {hp.get('default','')} | {hp.get('tipo','')} | {faixa} | {efeito} |")
        L.append("")
    refs = itens(c, "referencias")
    links = []
    for r in refs:
        if r.get("url"):
            links.append(f"- [{r.get('titulo', r['url'])}]({r['url']})")
        elif r.get("titulo"):
            links.append(f"- {r['titulo']}")
    if c.get("link_sklearn"):
        links.append(f"- Documentação scikit-learn: <{c['link_sklearn']}>")
    if c.get("link_yellowbrick"):
        links.append(f"- Documentação Yellowbrick: <{c['link_yellowbrick']}>")
    if links:
        L.append(f"{h}# Referências\n")
        L += links
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def main():
    if not os.path.isdir(os.path.dirname(OUT)):
        print(f"Pasta docs não encontrada em {OUT} — pulando (backend isolado?).")
        return
    os.makedirs(OUT, exist_ok=True)
    index = [
        "# Conteúdo didático dos elementos do pipeline de Machine Learning\n",
        "Material de apoio gerado a partir da plataforma educacional (H2IA Tutor / Mestrado Iana) "
        "para enriquecer a dissertação. Cada elemento do pipeline tem explicação em **dois níveis** — "
        "**Básico** (linguagem acessível, voltada a adolescentes) e **Avançado** (fundamentação técnica, "
        "fórmula e código) — além de conceitos, quando usar/evitar, vantagens/desvantagens, exemplo de "
        "código Python e referências oficiais (scikit-learn / Yellowbrick).\n",
        "Conteúdo verificado contra a documentação oficial. **Fonte canônica:** "
        "`app/conteudo/*.json` no backend.\n",
        "## Organização\n",
        "- `<categoria>/<elemento>.md` — uma ficha por elemento.",
        "- `<categoria>.md` — todas as fichas da categoria em um único arquivo (mais fácil de citar).\n",
        "## Sumário\n",
    ]
    total = 0
    for cat, label in CATS:
        dados = load(cat)
        total += len(dados)
        destino = os.path.join(OUT, cat)
        os.makedirs(destino, exist_ok=True)
        for f in os.listdir(destino):
            if f.endswith(".md"):
                os.remove(os.path.join(destino, f))
        # consolidado por categoria
        consolidado = [f"# {label}\n",
                       f"_{len(dados)} elementos. Material didático para a dissertação._\n", "---\n"]
        index.append(f"### {label} ({len(dados)}) — [`{cat}.md`]({cat}.md)\n")
        for valor in sorted(dados):
            c = dados[valor]
            # ficha individual (headings a partir de #)
            with open(os.path.join(destino, f"{valor}.md"), "w", encoding="utf-8") as fp:
                fp.write(ficha(valor, c, label, nivel="#"))
            index.append(f"- [{c.get('titulo', valor)}]({cat}/{valor}.md)")
            # entrada no consolidado (headings a partir de ##)
            consolidado.append(ficha(valor, c, label, nivel="##"))
            consolidado.append("\n---\n")
        with open(os.path.join(OUT, f"{cat}.md"), "w", encoding="utf-8") as fp:
            fp.write("\n".join(consolidado).rstrip() + "\n")
        index.append("")
    with open(os.path.join(OUT, "INDEX.md"), "w", encoding="utf-8") as fp:
        fp.write("\n".join(index).rstrip() + "\n")
    print(f"Gerado em {OUT}: {total} elementos, {len(CATS)} categorias.")
    for cat, _ in CATS:
        print(f"  {cat}: {len(load(cat))}")


if __name__ == "__main__":
    main()
