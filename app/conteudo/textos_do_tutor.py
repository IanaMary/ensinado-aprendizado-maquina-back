"""Os textos versionados que moram em `db.tutor` — quais são e como sincronizá-los.

Dois documentos de `db.tutor` têm fonte versionada no repo e podem ser reescritos pelo admin:

- `{pipe:'inicio'}.texto_pipe` — as boas-vindas que o aluno lê no painel do tutor;
- `{pipe:'conf-pipeline'}.texto_pipe` — o guia que o assistente do admin recebe como contexto.

A disciplina de sincronizar é a mesma da instrução de sistema (`app/conteudo/texto_versionado.py`).
Antes, cada um tinha o seu jeito: o das boas-vindas comparava strings brutas com uma constante de
"texto legado" (e por isso vinha reportando "editado pelo admin" para um documento que só tinha dois
espaços a mais), e o do conf-pipeline simplesmente sobrescrevia — motivo de ele nunca ter entrado no
deploy.

Consequência de registrar aqui: `ALVOS_POR_PIPE` é o que permite ao `PUT /tutor/pipe/{pipe}` marcar
`origem: 'admin'` quando o admin salva. Sem essa marcação o seed classificaria a edição dele como
"versionado" e propagaria por cima — pior que não ter guarda nenhuma.
"""
from __future__ import annotations

from typing import Any, Dict

from app.conteudo.kb_conf_pipeline import KB_CONF_PIPELINE
from app.conteudo.kb_tutor_inicio import TUTOR_INICIO_HTML, TUTOR_INICIO_LEGADO
from app.conteudo.texto_versionado import TextoVersionado, resumir, semear

ALVO_INICIO = TextoVersionado(
    campo_identidade="pipe",
    identidade="inicio",
    campo="texto_pipe",
    padrao=TUTOR_INICIO_HTML,
    rotulo="Boas-vindas do tutor",
    sufixo="as",
    pipe_auditoria="inicio",
    # O `seed-mongodb.sh` ainda insere um placeholder de uma frase. Ele é nosso, não do admin:
    # sem isto, um ambiente recém-semeado congelaria essa frase para sempre.
    legados=(TUTOR_INICIO_LEGADO,),
)

ALVO_CONF_PIPELINE = TextoVersionado(
    campo_identidade="pipe",
    identidade="conf-pipeline",
    campo="texto_pipe",
    padrao=KB_CONF_PIPELINE,
    rotulo="Guia do conf-pipeline",
    sufixo="o",
    pipe_auditoria="conf-pipeline",
    legados=(),
)

ALVOS_POR_PIPE: Dict[str, TextoVersionado] = {
    alvo.identidade: alvo for alvo in (ALVO_INICIO, ALVO_CONF_PIPELINE)
}


async def semear_texto_do_tutor(alvo: TextoVersionado, colecao=None, auditoria=None,
                                *, forcar: bool = False) -> Dict[str, Any]:
    """Sincroniza um dos textos de `db.tutor`. Import tardio de `app.database` para o módulo
    seguir importável sem `MONGO_URL` (mesma razão dos outros seeds)."""
    if colecao is None or auditoria is None:
        from app.database import tutor, tutor_audit

        colecao = colecao if colecao is not None else tutor
        auditoria = auditoria if auditoria is not None else tutor_audit

    return await semear(alvo, colecao, auditoria, forcar=forcar)


def resumo_legivel(resultado: Dict[str, Any], alvo: TextoVersionado) -> str:
    return resumir(resultado, alvo)
