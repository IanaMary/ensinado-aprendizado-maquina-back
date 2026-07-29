"""Semeadura versionada da instrução de sistema do chat (`db.configuracoes_tutor`).

O texto do `system` mora no banco para que "o que está rodando" seja um fato observável, e não a
ausência de um documento. Este módulo é quem sincroniza o banco com a fonte versionada
(`app/conteudo/kb_tutor_chat.py`) a cada boot do backend, preservando o que o admin escreveu.

Documento resultante:

```
{ chave: "system_prompt",
  valor: "<texto vigente>",        # invariante: doc existe => valor.strip() != ""
  origem: "versionado" | "admin",  # de quem é o texto
  padrao_hash: "<12 hex>",         # BASELINE, não checksum: o hash do padrão VERSIONADO vigente
                                   # no momento da gravação. Ausente = baseline desconhecido.
  versao: <int>,                   # contador monotônico de gravações ($inc; nunca no fonte)
  atualizado_por: "<user_id>" | "seed",
  atualizado_em: <datetime utc> }
```

Duas distinções que decidem o comportamento e são fáceis de errar depois:

- **`padrao_hash` é baseline, não checksum de `valor`.** O hash de `valor` é derivável a qualquer
  momento; o que não é derivável é qual padrão o admin tinha à frente quando decidiu sobrescrever —
  e é isso que torna computável "existe padrão novo desde a sua edição".
- **`padrao_hash` ausente ≠ diferente.** Ausente significa "não sei" (documento legado adotado) e
  NÃO deve acender aviso de padrão desatualizado: seria um alarme que o admin não tem como resolver.

`decidir_seed` é pura (recebe o documento, devolve a ação e as operações do Mongo) porque a matriz
tem dez estados: testá-la com mock de coleção seria caro e frágil.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.conteudo.kb_tutor_chat import HASH_SYSTEM_PROMPT, SYSTEM_PROMPT_TUTOR, hash_prompt

CHAVE = "system_prompt"
ORIGEM_VERSIONADO = "versionado"
ORIGEM_ADMIN = "admin"

# Ações devolvidas por `decidir_seed`. As três primeiras escrevem o texto (e por isso auditam);
# as `normalizou_*` só ajustam metadado de um documento legado; as demais não escrevem nada.
ACAO_INSERIU = "inseriu"
ACAO_PROPAGOU = "propagou"
ACAO_CUROU = "curou_vazio"
ACAO_FORCOU = "forcou"
ACAO_SEM_MUDANCA = "sem_mudanca"
ACAO_PRESERVOU = "preservou"
ACAO_PRESERVOU_DESATUALIZADO = "preservou_padrao_novo"
ACAO_NORMALIZOU_VERSIONADO = "normalizou_versionado"
ACAO_NORMALIZOU_ADMIN = "normalizou_admin"

# Ações que mexeram no texto — só essas viram entrada de auditoria, para o histórico do admin
# não encher de ruído a cada reinício do serviço.
ACOES_QUE_ESCREVEM_TEXTO = (ACAO_INSERIU, ACAO_PROPAGOU, ACAO_CUROU, ACAO_FORCOU)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _ops_grava_padrao(padrao: str) -> Dict[str, Any]:
    """Update que põe o padrão versionado no ar. `$inc` sozinho no `versao`: combinar `$inc` com
    `$setOnInsert` no mesmo campo é erro de path conflitante no Mongo — e no upsert que insere,
    `$inc` já cria o campo com 1."""
    return {
        "$set": {
            "chave": CHAVE,
            "valor": padrao,
            "origem": ORIGEM_VERSIONADO,
            "padrao_hash": hash_prompt(padrao),
            "atualizado_por": "seed",
            "atualizado_em": _agora(),
        },
        "$inc": {"versao": 1},
    }


def decidir_seed(
    doc: Optional[Dict[str, Any]],
    padrao: str = SYSTEM_PROMPT_TUTOR,
    forcar: bool = False,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Decide o que fazer com o documento atual. Devolve `(acao, operacoes_mongo | None)`.

    Ordem de avaliação (importa): `forcar` → `valor` vazio → doc ausente → normalização de
    documento legado → comparação por `origem`/hash.
    """
    hash_padrao = hash_prompt(padrao)
    valor = ((doc or {}).get("valor") or "").strip()
    origem = (doc or {}).get("origem")
    baseline = (doc or {}).get("padrao_hash")

    # (I) --forcar: o operador assumiu a responsabilidade de descartar o que houver.
    if forcar:
        return ACAO_FORCOU, _ops_grava_padrao(padrao)

    # (H) Documento sem texto útil. Não é destruição: é o estado que hoje cai no fallback em
    # runtime, ou seja, o tutor já estaria respondendo com o padrão.
    if doc is not None and not valor:
        return ACAO_CUROU, _ops_grava_padrao(padrao)

    # (A) Primeira vez: o texto versionado passa a ser fato no banco.
    if doc is None:
        return ACAO_INSERIU, _ops_grava_padrao(padrao)

    igual_ao_padrao = hash_prompt(valor) == hash_padrao

    # (F, G, J) Normalizações de metadado — colapsam o documento nos estados canônicos.
    if origem not in (ORIGEM_VERSIONADO, ORIGEM_ADMIN):
        # Legado (gravado antes deste módulo existir): classificar sem tocar no texto.
        if igual_ao_padrao:
            return ACAO_NORMALIZOU_VERSIONADO, {
                "$set": {"origem": ORIGEM_VERSIONADO, "padrao_hash": hash_padrao}
            }
        # Conservador: qualquer texto diferente do padrão é tratado como edição do admin e
        # preservado. `padrao_hash` fica AUSENTE de propósito — não sabemos de que padrão veio.
        return ACAO_NORMALIZOU_ADMIN, {"$set": {"origem": ORIGEM_ADMIN}}

    if origem == ORIGEM_ADMIN and igual_ao_padrao:
        # (J) O admin colou exatamente o padrão. Mantê-lo como 'admin' o congelaria fora das
        # próximas atualizações do repo sem que ele tenha um texto próprio a proteger.
        return ACAO_NORMALIZOU_VERSIONADO, {
            "$set": {"origem": ORIGEM_VERSIONADO, "padrao_hash": hash_padrao}
        }

    if origem == ORIGEM_VERSIONADO:
        # (B) já em dia — não toca em `atualizado_em` para não poluir o histórico.
        if igual_ao_padrao:
            return ACAO_SEM_MUDANCA, None
        # (C) É isto que significa "versionado com o sistema": quem nunca editou recebe o texto
        # novo do repo. Não é regressão — hoje a constante já É o que roda.
        return ACAO_PROPAGOU, _ops_grava_padrao(padrao)

    # (D, E) Edição do admin: preservada sempre. A diferença é só se há padrão novo a avisar.
    if baseline and baseline != hash_padrao:
        return ACAO_PRESERVOU_DESATUALIZADO, None
    return ACAO_PRESERVOU, None


async def semear_system_prompt(
    colecao=None,
    auditoria=None,
    *,
    padrao: str = SYSTEM_PROMPT_TUTOR,
    forcar: bool = False,
) -> Dict[str, Any]:
    """Aplica `decidir_seed` no banco e devolve o que aconteceu.

    Coleções injetáveis por parâmetro (default: as de `app.database`) para que os testes não
    precisem patchar globais de módulo. Import tardio pelo mesmo motivo dos outros seeds: manter o
    módulo importável sem `MONGO_URL` definida.
    """
    if colecao is None or auditoria is None:
        from app.database import configuracoes_tutor, tutor_audit

        colecao = colecao if colecao is not None else configuracoes_tutor
        auditoria = auditoria if auditoria is not None else tutor_audit

    doc = await colecao.find_one({"chave": CHAVE})
    acao, ops = decidir_seed(doc, padrao=padrao, forcar=forcar)

    anterior = ((doc or {}).get("valor") or "").strip()
    resultado = {
        "acao": acao,
        "hash_anterior": hash_prompt(anterior) if anterior else None,
        "hash_novo": hash_prompt(padrao),
        "chars_anteriores": len(anterior),
        "chars": len(padrao),
        "escreveu": ops is not None,
    }

    if ops is None:
        return resultado

    await colecao.update_one({"chave": CHAVE}, ops, upsert=True)

    if acao in ACOES_QUE_ESCREVEM_TEXTO:
        # `pipe: 'llm'` porque é a aba do conf-tutor onde este histórico aparece — é rótulo de
        # UI, não afirmação sobre a coleção de origem.
        try:
            await auditoria.insert_one({
                "pipe": "llm",
                "tutor_id": "",
                "operacao": ACAO_FORCOU if acao == ACAO_FORCOU else "seed_padrao",
                "campos_alterados": ["system_prompt"],
                "tamanho": len(padrao),
                "tamanho_anterior": len(anterior),
                "hash_anterior": resultado["hash_anterior"],
                "hash_novo": resultado["hash_novo"],
                # O texto que saiu do ar fica guardado: sem isso, propagar o padrão novo por cima
                # de um texto de seed antigo seria perda silenciosa.
                "texto_anterior": anterior,
                "usuario_id": "",
                "usuario_email": "sistema",
                "usuario_nome": "Seed do deploy",
                "timestamp": _agora(),
            })
        except Exception:  # pragma: no cover - auditoria não pode quebrar o boot
            pass

    return resultado


def resumo_legivel(resultado: Dict[str, Any]) -> str:
    """Uma linha para o log do deploy, no estilo dos outros seeds."""
    acao = resultado["acao"]
    if acao == ACAO_SEM_MUDANCA:
        return "Instrução do tutor: sem mudança"
    if acao == ACAO_PRESERVOU:
        return (f"Instrução do tutor: preservada (texto do admin, "
                f"{resultado['chars_anteriores']} chars)")
    if acao == ACAO_PRESERVOU_DESATUALIZADO:
        return (f"Instrução do tutor: preservada, MAS o padrão versionado mudou "
                f"(admin: {resultado['chars_anteriores']} chars; padrão agora: "
                f"{resultado['hash_novo']}). O admin decide na tela; use --forcar para impor.")
    if acao == ACAO_FORCOU:
        return (f"Instrução do tutor: FORÇADA ao padrão "
                f"({resultado['chars_anteriores']} chars do admin descartados)")
    if acao == ACAO_NORMALIZOU_VERSIONADO:
        return "Instrução do tutor: documento marcado como padrão do sistema (texto igual)"
    if acao == ACAO_NORMALIZOU_ADMIN:
        return "Instrução do tutor: documento legado marcado como edição do admin (preservado)"
    if acao == ACAO_CUROU:
        return "Instrução do tutor: documento estava vazio, padrão gravado"
    if acao == ACAO_PROPAGOU:
        return f"Instrução do tutor: padrão novo propagado ({resultado['chars']} chars)"
    return f"Instrução do tutor: inserida ({resultado['chars']} chars)"
