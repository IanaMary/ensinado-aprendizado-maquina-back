#!/usr/bin/env python
"""Contas de demonstração (admin, professor e aluno) com conteúdo pronto para a banca.

Cria três contas já ativas, uma turma com um desafio de montagem e uma atividade de
pipeline, e um histórico plausível do aluno — para que a banca encontre as telas com
dados no primeiro login, em vez de listas vazias.

IDEMPOTENTE: rodar de novo não duplica nada (as contas são achadas pelo e-mail, a turma
pelo código, as atividades pelo título). Nunca toca documentos que não tenham o marcador
`demo: "banca"` — se um e-mail já pertencer a uma conta real, o script aborta.

    .venv/bin/python -m scripts.deploy.seed_usuarios_demo            # criar/atualizar
    .venv/bin/python -m scripts.deploy.seed_usuarios_demo --remover  # apagar tudo

DEPOIS DA DEFESA, RODE `--remover`: são contas com senha compartilhada e o login não
verifica `status`, então "desativar" pelo painel do admin não bloqueia o acesso.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

MARCA = "banca"
SENHA = os.getenv("SENHA_DEMO", "h2ia-banca-2026")

CONTAS = [
    ("admin.banca@h2ia.demo", "Banca (Admin)", "admin"),
    ("professor.banca@h2ia.demo", "Banca (Professor)", "professor"),
    ("aluno.banca@h2ia.demo", "Banca (Aluno)", "aluno"),
]

TURMA_NOME = "Banca — 9º ano B"
TURMA_CODIGO = "BANCA26"

DESAFIO_TITULO = "Desafio: montar um pipeline de classificação"
DESAFIO_DESCRICAO = (
    "A escola quer prever a espécie de uma flor a partir das medidas das pétalas. "
    "Monte o pipeline com as peças do tabuleiro — não é preciso executar nada."
)
DESAFIO_GABARITO = {
    "tarefa": "classificacao",
    "exige": ["coleta", "pre_processamento", "modelo", "metrica"],
    "dados": {"faltantes": True, "texto": False, "escalas_diferentes": True},
    "dificuldade": "medio",
    "fixar": [],
    "vetar": [],
}

# Segundo desafio, deixado SEM tentativas de propósito: é o que faz aparecer o aviso de
# desafio pendente na Área de Trabalho do aluno (o primeiro já tem histórico).
DESAFIO2_TITULO = "Desafio: montar um pipeline de regressão"
DESAFIO2_DESCRICAO = (
    "Agora o problema é prever um número: o preço de um imóvel a partir do tamanho e da "
    "localização. Escolha as peças que servem para regressão."
)
DESAFIO2_GABARITO = {
    "tarefa": "regressao",
    "exige": ["coleta", "modelo", "metrica"],
    "dados": {"faltantes": False, "texto": False, "escalas_diferentes": False},
    "dificuldade": "facil",
    "fixar": [],
    "vetar": [],
}

PIPELINE_TITULO = "Atividade: classificar flores (Iris)"
PIPELINE_DESCRICAO = (
    "Carregue o dataset de exemplo Iris, treine um modelo e envie a sua melhor acurácia."
)

# Duas tentativas do aluno na MESMA base, para o bloco "Sua evolução nesta base" ter o que
# comparar. A matriz de confusão é o que permite calcular o chute burro da base.
TENTATIVAS_PIPELINE = [
    {"nome": "Iris com k-NN (1ª tentativa)", "modelo": "knn", "acuracia": 0.8684,
     "matriz": [[13, 0, 0], [0, 10, 3], [0, 2, 10]], "dias_atras": 6},
    {"nome": "Iris com Floresta Aleatória", "modelo": "random_forest", "acuracia": 0.9474,
     "matriz": [[13, 0, 0], [0, 12, 1], [0, 1, 11]], "dias_atras": 1},
]


def _agora():
    return datetime.now(timezone.utc)


async def _semear_usuarios() -> dict:
    from app.database import colecao_usuario
    from app.security import get_senha_hash

    # Confere TODOS os e-mails antes de escrever qualquer coisa: abortar no meio deixaria
    # metade das contas criadas depois de dizer que nada foi alterado.
    existentes = {}
    for email, _nome, _papel in CONTAS:
        atual = await colecao_usuario.find_one({"email": email})
        if atual and atual.get("demo") != MARCA:
            raise SystemExit(
                f"ABORTADO: {email} já existe e NÃO é conta de demonstração. "
                "Nada foi alterado."
            )
        existentes[email] = atual

    senha_hash = get_senha_hash(SENHA)
    ids = {}
    for email, nome, papel in CONTAS:
        atual = existentes[email]
        doc = {
            "nome_usuario": nome, "email": email, "role": papel,
            "senha": senha_hash, "status": "ativo",
            "instituicao_ensino": "UFPel — banca de dissertação",
            "data_ativacao": _agora(), "token_convite": None,
            "demo": MARCA,
        }
        if atual:
            await colecao_usuario.update_one({"_id": atual["_id"]}, {"$set": doc})
            ids[papel] = str(atual["_id"])
            print(f"  usuário {email}: atualizado")
        else:
            doc["criado_em"] = _agora()
            r = await colecao_usuario.insert_one(doc)
            ids[papel] = str(r.inserted_id)
            print(f"  usuário {email}: criado")
    return ids


async def _semear_turma(ids: dict) -> str:
    from app.database import turmas

    atual = await turmas.find_one({"codigo": TURMA_CODIGO})
    doc = {
        "professor_id": ids["professor"], "nome": TURMA_NOME,
        "descricao": "Turma de demonstração para a banca (dados fictícios).",
        "codigo": TURMA_CODIGO, "alunos": [ids["aluno"]], "demo": MARCA,
    }
    if atual:
        await turmas.update_one({"_id": atual["_id"]}, {"$set": doc})
        print(f"  turma {TURMA_CODIGO}: atualizada")
        return str(atual["_id"])
    doc["criado_em"] = _agora()
    r = await turmas.insert_one(doc)
    print(f"  turma {TURMA_CODIGO}: criada")
    return str(r.inserted_id)


async def _semear_atividades(turma_id: str, ids: dict) -> dict:
    from app.database import atividades

    base = {"turma_id": turma_id, "professor_id": ids["professor"], "demo": MARCA,
            "prazo": None}
    definicoes = {
        "desafio_feito": {
            **base, "titulo": DESAFIO_TITULO, "descricao": DESAFIO_DESCRICAO,
            "tipo": "montagem", "template": {},
            "criterio": {"metrica": "accuracy_score", "ordem": "desc"},
            "gabarito": DESAFIO_GABARITO},
        "desafio_pendente": {
            **base, "titulo": DESAFIO2_TITULO, "descricao": DESAFIO2_DESCRICAO,
            "tipo": "montagem", "template": {},
            "criterio": {"metrica": "r2_score", "ordem": "desc"},
            "gabarito": DESAFIO2_GABARITO},
        "pipeline": {
            **base, "titulo": PIPELINE_TITULO, "descricao": PIPELINE_DESCRICAO,
            "tipo": "pipeline", "template": {"datasetNome": "Iris"},
            "criterio": {"metrica": "accuracy_score", "ordem": "desc"}},
    }
    resultado = {}
    for chave, doc in definicoes.items():
        atual = await atividades.find_one({"turma_id": turma_id, "titulo": doc["titulo"]})
        if atual:
            await atividades.update_one({"_id": atual["_id"]}, {"$set": doc})
            resultado[chave] = {**doc, "_id": atual["_id"]}
            print(f"  atividade '{doc['titulo']}': atualizada")
        else:
            doc = {**doc, "criado_em": _agora()}
            r = await atividades.insert_one(doc)
            resultado[chave] = {**doc, "_id": r.inserted_id}
            print(f"  atividade '{doc['titulo']}': criada")
    return resultado


async def _semear_submissoes(atividade: dict, turma_id: str, aluno_id: str) -> None:
    """Duas tentativas do aluno no desafio, corrigidas pela RUBRICA REAL.

    A nota não é inventada: monta-se o tabuleiro da tentativa (o mesmo que o aluno veria) e
    a montagem é avaliada por `avaliar_montagem`. A 1ª tentativa deixa lanes de fora, a 2ª
    usa as peças úteis — o histórico mostra evolução de verdade.
    """
    from app.database import submissoes_montagem
    from app.desafios.avaliacao import avaliar_montagem
    from app.desafios.catalogo import carregar_pecas
    from app.desafios.sorteio import montar_tabuleiro, papeis

    atividade_id = str(atividade["_id"])
    if await submissoes_montagem.count_documents(
            {"atividade_id": atividade_id, "user_id": aluno_id}):
        print("  submissões do desafio: já existem (preservadas)")
        return

    pecas = await carregar_pecas()
    for tentativa in (1, 2):
        tabuleiro = await montar_tabuleiro(atividade, aluno_id, tentativa, pecas_catalogo=pecas)
        ofertadas = papeis(tabuleiro)
        uteis = {}
        for p in tabuleiro["pecas"]:
            if ofertadas.get(p["valor"]) == "util":
                uteis.setdefault(p["lane"], []).append(p["valor"])
        if tentativa == 1:
            # Erro típico de quem está começando: só dados e modelo, sem preparar nem medir.
            montagem = {lane: valores for lane, valores in uteis.items()
                        if lane in ("coleta", "modelo")}
        else:
            montagem = uteis
        resultado = avaliar_montagem(montagem, atividade.get("gabarito") or {}, pecas, ofertadas)
        await submissoes_montagem.insert_one({
            "user_id": aluno_id, "turma_id": turma_id, "atividade_id": atividade_id,
            "tentativa": tentativa, "montagem": resultado["montagem"],
            "nota": resultado["nota"], "nota_max": resultado["nota_max"],
            "pontos": resultado["pontos"], "pontos_max": resultado["pontos_max"],
            "regras": resultado["regras"], "demo": MARCA,
            "criado_em": _agora() - timedelta(days=3 - tentativa),
        })
        print(f"  submissão do desafio (tentativa {tentativa}): nota {resultado['nota']}")


async def _semear_pipelines(atividade: dict, turma_id: str, aluno_id: str) -> None:
    from app.database import pipelines

    atividade_id = str(atividade["_id"])
    if await pipelines.count_documents({"user_id": aluno_id, "demo": MARCA}):
        print("  pipelines do aluno: já existem (preservados)")
        return

    for t in TENTATIVAS_PIPELINE:
        quando = _agora() - timedelta(days=t["dias_atras"])
        await pipelines.insert_one({
            "user_id": aluno_id,
            "nome": t["nome"],
            "descricao": "Submissão de demonstração (dados fictícios).",
            "resultadoColetaDado": {
                "nomeDataset": "Iris", "target": "species",
                "preverCategoria": True, "dadosRotulados": True,
                "atributos": ["sepal_length", "sepal_width", "petal_length", "petal_width"],
                "treino": {"nomeArquivo": "Iris.csv"},
            },
            "modeloSelecionado": {"valor": t["modelo"]},
            "metricasSelecionadas": [{"valor": "accuracy_score"}],
            "mediaMetricas": "weighted",
            "preProcessamentoConfig": None,
            "resultadoTreinamento": {"status": "concluido"},
            "resultadosDasAvaliacoes": {
                "Acurácia": {t["modelo"]: t["acuracia"]},
                "Matriz de confusão": {t["modelo"]: {"matriz": t["matriz"]}},
            },
            "status": "finalizado", "is_public": False,
            "dificuldade": "iniciante", "tags": ["demonstracao"],
            "professor_id": None, "atividade_id": atividade_id, "turma_id": turma_id,
            "demo": MARCA, "dataCriacao": quando, "dataModificacao": quando,
        })
        print(f"  pipeline '{t['nome']}': acurácia {t['acuracia']}")


async def _remover() -> None:
    from app.database import (atividades, colecao_usuario, historico_chat, pipelines,
                              submissoes_montagem, turmas)

    emails = [c[0] for c in CONTAS]
    ids = [str(u["_id"]) async for u in colecao_usuario.find({"email": {"$in": emails}})]
    # O que a banca produzir durante os testes não tem o marcador, mas é dessas contas.
    for colecao, campo, nome in (
        (pipelines, "user_id", "pipelines"),
        (submissoes_montagem, "user_id", "submissões de desafio"),
        (historico_chat, "usuario_id", "conversas do tutor"),
    ):
        r = await colecao.delete_many({"$or": [{campo: {"$in": ids}}, {"demo": MARCA}]})
        print(f"  {nome}: {r.deleted_count} removidos")
    turma = await turmas.find_one({"codigo": TURMA_CODIGO})
    if turma:
        r = await atividades.delete_many({"turma_id": str(turma["_id"])})
        print(f"  atividades da turma: {r.deleted_count} removidas")
    r = await turmas.delete_many({"$or": [{"codigo": TURMA_CODIGO}, {"demo": MARCA}]})
    print(f"  turmas: {r.deleted_count} removidas")
    r = await colecao_usuario.delete_many({"email": {"$in": emails}, "demo": MARCA})
    print(f"  usuários: {r.deleted_count} removidos")


async def _main(remover: bool) -> None:
    if remover:
        print("Removendo dados de demonstração da banca…")
        await _remover()
        print("Pronto.")
        return

    print("Semeando dados de demonstração da banca…")
    ids = await _semear_usuarios()
    turma_id = await _semear_turma(ids)
    ativs = await _semear_atividades(turma_id, ids)
    await _semear_submissoes(ativs["desafio_feito"], turma_id, ids["aluno"])
    await _semear_pipelines(ativs["pipeline"], turma_id, ids["aluno"])
    print("\nContas (senha única):")
    for email, _nome, papel in CONTAS:
        print(f"  {papel:<9} {email}   senha: {SENHA}")
    print(f"\nTurma '{TURMA_NOME}' — código {TURMA_CODIGO}")
    print("Depois da defesa, rode com --remover.")


if __name__ == "__main__":
    asyncio.run(_main("--remover" in sys.argv[1:]))
