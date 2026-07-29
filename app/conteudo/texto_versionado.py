"""Motor de sincronização de textos versionados: repositório → MongoDB, preservando o admin.

Vários textos do produto nascem versionados no repo e podem ser reescritos pelo admin na tela: a
instrução de sistema do chat (`db.configuracoes_tutor {chave:'system_prompt'}.valor`), as
boas-vindas do tutor e o guia do conf-pipeline (`db.tutor {pipe:…}.texto_pipe`). Todos precisam da
MESMA disciplina, e é ela que vive aqui — os módulos específicos só descrevem o alvo.

O documento sincronizado carrega:

```
{ <campo_identidade>: <identidade>,
  <campo>: "<texto vigente>",     # invariante: doc existe => texto.strip() != ""
  origem: "versionado" | "admin", # de quem é o texto
  padrao_hash: "<12 hex>",        # BASELINE, não checksum (ver abaixo)
  versao: <int>,                  # contador monotônico de gravações ($inc; nunca no fonte)
  atualizado_por: "<user_id>" | "seed",
  atualizado_em: <datetime utc> }
```

Duas distinções decidem o comportamento e são fáceis de errar depois:

- **`padrao_hash` é baseline, não checksum do texto.** O hash do texto é derivável a qualquer
  momento; o que não é derivável é qual padrão o admin tinha à frente quando decidiu sobrescrever —
  e é isso que torna computável "existe padrão novo desde a sua edição".
- **`padrao_hash` ausente ≠ diferente.** Ausente significa "não sei" (documento legado adotado) e
  NÃO deve acender aviso de padrão desatualizado: seria alarme que ninguém tem como resolver.

`decidir` é pura (recebe o documento, devolve a ação e as operações do Mongo) porque a matriz tem
doze estados: testá-la com mock de coleção seria caro e frágil.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.conteudo.kb_tutor_chat import hash_prompt

ORIGEM_VERSIONADO = "versionado"
ORIGEM_ADMIN = "admin"

# Ações devolvidas por `decidir`. As quatro de `ACOES_QUE_ESCREVEM_TEXTO` mexem no texto (e por isso
# auditam); as `normalizou_*` só ajustam metadado de um documento legado; as demais não escrevem.
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


@dataclass(frozen=True)
class TextoVersionado:
    """Descreve UM texto sincronizado: onde ele mora, qual é o padrão e como falar dele.

    Descrever o alvo uma vez (em vez de repetir nove parâmetros em cada chamada) evita a classe de
    erro mais chata daqui: trocar a ordem de `campo_identidade`/`campo` e escrever no lugar errado.
    """

    campo_identidade: str          # "chave" | "pipe"
    identidade: str                # "system_prompt" | "inicio" | "conf-pipeline"
    campo: str                     # onde o texto mora: "valor" | "texto_pipe"
    padrao: str                    # a fonte da verdade versionada
    rotulo: str                    # como o log chama isto ("Instrução do tutor")
    # Concordância do `rotulo` nas mensagens de log: "preservad{a|as|o}". Sem isso o log diria
    # "Guia do conf-pipeline: preservada".
    sufixo: str = "a"
    pipe_auditoria: str = ""       # aba do conf-tutor onde o histórico aparece
    campo_auditado: Optional[str] = None    # default: o próprio `campo`
    # Textos que NÓS publicamos antes (ex.: o placeholder de uma frase do seed-mongodb.sh). Um doc
    # com esse conteúdo não é edição do admin, e por isso pode receber o padrão novo. Use apenas
    # com string curta, literal e historicamente nossa — nunca algo que um admin escreveria.
    legados: Tuple[str, ...] = ()

    @property
    def filtro(self) -> Dict[str, str]:
        return {self.campo_identidade: self.identidade}

    @property
    def hash_padrao(self) -> str:
        return hash_prompt(self.padrao)

    @property
    def campo_no_historico(self) -> str:
        return self.campo_auditado or self.campo


def classificar_origem(texto: str, alvo: TextoVersionado) -> str:
    """De quem é este texto. Quem colou exatamente o padrão NÃO é 'admin': marcá-lo assim o
    congelaria fora das próximas atualizações do repo sem que ele tenha um texto próprio a
    proteger."""
    return ORIGEM_VERSIONADO if hash_prompt(texto) == alvo.hash_padrao else ORIGEM_ADMIN


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _ops_grava_padrao(alvo: TextoVersionado) -> Dict[str, Any]:
    """Update que põe o padrão versionado no ar.

    `$inc` sozinho no `versao`: combinar `$inc` com `$setOnInsert` no MESMO campo é erro de path
    conflitante no Mongo — e no upsert que insere, `$inc` já cria o campo com 1. A identidade vai no
    `$set` (não no `$setOnInsert`) pela mesma razão: um operador por path.
    """
    return {
        "$set": {
            alvo.campo_identidade: alvo.identidade,
            alvo.campo: alvo.padrao,
            "origem": ORIGEM_VERSIONADO,
            "padrao_hash": alvo.hash_padrao,
            "atualizado_por": "seed",
            "atualizado_em": _agora(),
        },
        "$inc": {"versao": 1},
    }


def decidir(
    doc: Optional[Dict[str, Any]],
    alvo: TextoVersionado,
    *,
    forcar: bool = False,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Decide o que fazer com o documento atual. Devolve `(acao, operacoes_mongo | None)`.

    Ordem de avaliação (importa): `forcar` → texto vazio → doc ausente → **texto legado** →
    normalização de documento sem `origem` → comparação por `origem`/hash.
    """
    hash_padrao = alvo.hash_padrao
    texto = ((doc or {}).get(alvo.campo) or "").strip()
    origem = (doc or {}).get("origem")
    baseline = (doc or {}).get("padrao_hash")

    # (I) --forcar: o operador assumiu a responsabilidade de descartar o que houver.
    if forcar:
        return ACAO_FORCOU, _ops_grava_padrao(alvo)

    # (H) Documento sem texto útil. Não é destruição: é o estado que já cai no fallback em runtime,
    # ou seja, o produto já estaria servindo o padrão.
    if doc is not None and not texto:
        return ACAO_CUROU, _ops_grava_padrao(alvo)

    # (A) Primeira vez: o texto versionado passa a ser fato no banco.
    if doc is None:
        return ACAO_INSERIU, _ops_grava_padrao(alvo)

    igual_ao_padrao = hash_prompt(texto) == hash_padrao

    # (K) Texto que NÓS publicamos antes. Vem aqui, antes dos ramos de `origem`, porque é uma
    # afirmação sobre o TEXTO: se ficasse dentro de cada ramo, a mesma regra apareceria três vezes —
    # e o caso realista (o admin abre a tela, vê o placeholder de uma frase e clica em Salvar,
    # marcando `origem: admin`) congelaria o placeholder para sempre.
    if not igual_ao_padrao and hash_prompt(texto) in {hash_prompt(t) for t in alvo.legados}:
        return ACAO_PROPAGOU, _ops_grava_padrao(alvo)

    # (F, G) Normalizações de metadado — colapsam o documento nos estados canônicos.
    if origem not in (ORIGEM_VERSIONADO, ORIGEM_ADMIN):
        # Legado (gravado antes deste módulo existir): classificar sem tocar no texto.
        if igual_ao_padrao:
            return ACAO_NORMALIZOU_VERSIONADO, {
                "$set": {"origem": ORIGEM_VERSIONADO, "padrao_hash": hash_padrao}
            }
        # Conservador: qualquer texto diferente do padrão é tratado como edição do admin e
        # preservado. `padrao_hash` fica AUSENTE de propósito — não sabemos de que padrão veio.
        return ACAO_NORMALIZOU_ADMIN, {"$set": {"origem": ORIGEM_ADMIN}}

    # (J) O admin colou exatamente o padrão.
    if origem == ORIGEM_ADMIN and igual_ao_padrao:
        return ACAO_NORMALIZOU_VERSIONADO, {
            "$set": {"origem": ORIGEM_VERSIONADO, "padrao_hash": hash_padrao}
        }

    if origem == ORIGEM_VERSIONADO:
        # (B) já em dia — não toca em `atualizado_em` para não poluir o histórico.
        if igual_ao_padrao:
            return ACAO_SEM_MUDANCA, None
        # (C) É isto que significa "versionado com o sistema": quem nunca editou recebe o texto
        # novo do repo. Não é regressão — a constante já É o que roda quando não há doc.
        return ACAO_PROPAGOU, _ops_grava_padrao(alvo)

    # (D, E) Edição do admin: preservada sempre. A diferença é só se há padrão novo a avisar.
    if baseline and baseline != hash_padrao:
        return ACAO_PRESERVOU_DESATUALIZADO, None
    return ACAO_PRESERVOU, None


async def semear(
    alvo: TextoVersionado,
    colecao,
    auditoria=None,
    *,
    forcar: bool = False,
) -> Dict[str, Any]:
    """Aplica `decidir` no banco e devolve o que aconteceu.

    `colecao` é obrigatória (o motor não importa `app.database`, para seguir importável sem
    `MONGO_URL`); `auditoria=None` significa não auditar. Quem resolve os defaults é a
    especialização, que é quem sabe onde o alvo mora.
    """
    doc = await colecao.find_one(alvo.filtro)
    acao, ops = decidir(doc, alvo, forcar=forcar)

    anterior = ((doc or {}).get(alvo.campo) or "").strip()
    resultado = {
        "acao": acao,
        "hash_anterior": hash_prompt(anterior) if anterior else None,
        "hash_novo": alvo.hash_padrao,
        "chars_anteriores": len(anterior),
        "chars": len(alvo.padrao),
        "escreveu": ops is not None,
    }

    if ops is None:
        return resultado

    await colecao.update_one(alvo.filtro, ops, upsert=True)

    if auditoria is not None and acao in ACOES_QUE_ESCREVEM_TEXTO:
        # `pipe` é o rótulo da aba do conf-tutor onde este histórico aparece — não é afirmação
        # sobre a coleção de origem.
        try:
            await auditoria.insert_one({
                "pipe": alvo.pipe_auditoria,
                "tutor_id": "",
                "operacao": ACAO_FORCOU if acao == ACAO_FORCOU else "seed_padrao",
                "campos_alterados": [alvo.campo_no_historico],
                "tamanho": len(alvo.padrao),
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


def resumir(resultado: Dict[str, Any], alvo: TextoVersionado) -> str:
    """Uma linha para o log do deploy, no estilo dos outros seeds."""
    acao = resultado["acao"]
    r, s = alvo.rotulo, alvo.sufixo
    if acao == ACAO_SEM_MUDANCA:
        return f"{r}: sem mudança"
    if acao == ACAO_PRESERVOU:
        return f"{r}: preservad{s} (texto do admin, {resultado['chars_anteriores']} chars)"
    if acao == ACAO_PRESERVOU_DESATUALIZADO:
        return (f"{r}: preservad{s}, MAS o padrão versionado mudou "
                f"(admin: {resultado['chars_anteriores']} chars; padrão agora: "
                f"{resultado['hash_novo']}). O admin decide na tela; use --forcar para impor.")
    if acao == ACAO_FORCOU:
        return (f"{r}: FORÇAD{s.upper()} ao padrão "
                f"({resultado['chars_anteriores']} chars do admin descartados)")
    if acao == ACAO_NORMALIZOU_VERSIONADO:
        return f"{r}: documento marcado como padrão do sistema (texto igual)"
    if acao == ACAO_NORMALIZOU_ADMIN:
        return f"{r}: documento legado marcado como edição do admin (preservado)"
    if acao == ACAO_CUROU:
        return f"{r}: documento estava vazio, padrão gravado"
    if acao == ACAO_PROPAGOU:
        return f"{r}: padrão novo propagado ({resultado['chars']} chars)"
    return f"{r}: inserid{s} ({resultado['chars']} chars)"
