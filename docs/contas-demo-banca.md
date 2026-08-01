# Contas de demonstração para a banca

Três contas já ativas (admin, professor e aluno) com uma turma, dois desafios e histórico —
para a banca da dissertação encontrar as telas **com dados** no primeiro login.

Criadas por `scripts/deploy/seed_usuarios_demo.py`. Nada disso passa pelo convite por
e-mail: o script grava direto, com `status: "ativo"` e a senha já com hash
(`app.security.get_senha_hash`, o mesmo contexto do login).

## Credenciais

| Papel | E-mail | Senha |
|---|---|---|
| admin | `admin.banca@h2ia.demo` | (definida em `SENHA_DEMO` na criação) |
| professor | `professor.banca@h2ia.demo` | (definida em `SENHA_DEMO` na criação) |
| aluno | `aluno.banca@h2ia.demo` | (definida em `SENHA_DEMO` na criação) |

A senha **não fica no repositório**. Ela é escolhida na hora de semear e repassada
por canal seguro:
`SENHA_DEMO='...' .venv/bin/python -m scripts.deploy.seed_usuarios_demo`.
Depois da defesa, rode `--remover`.

## O que já vem pronto

- **Turma "Banca — 9º ano B"**, código **`BANCA26`**, do professor demo, com o aluno demo
  matriculado (a mesma turma pode receber outros alunos pelo código/QR).
- **Desafio de montagem (classificação)** — o aluno demo já tem **2 tentativas**, melhor
  nota **9,4**: ranking, progresso e o histórico na lista de turmas aparecem preenchidos.
  As notas **não são inventadas**: a montagem de cada tentativa é corrigida pela rubrica
  real (`avaliar_montagem`), então o retorno por regra é coerente com a nota.
- **Desafio de montagem (regressão)** — deixado **sem tentativas** de propósito: é o que
  faz aparecer o aviso "você tem um desafio para fazer" na Área de Trabalho do aluno.
- **Atividade de pipeline real** (Iris) com **duas submissões** do aluno (acurácia 0,8684 →
  0,9474, com matriz de confusão): o bloco "Sua evolução nesta base" mostra o ganho sobre a
  tentativa anterior e sobre o chute burro da base.

## Roteiro sugerido

1. **Aluno** — entra e vê o aviso do desafio pendente na Área de Trabalho; faz o desafio
   (arrasta as peças, envia, lê a nota e o retorno por regra); abre "Turmas e desafios" no
   menu do avatar; carrega o Iris pela Coleta, treina e avalia para ver a evolução na base.
2. **Professor** — abre a turma, mostra código/QR, o ranking do desafio (nota + tentativas)
   e o progresso dos alunos; cria uma atividade nova (pipeline ou desafio).
3. **Admin** — Configuração do Pipeline (habilitar item, conteúdo educacional, assistente),
   Configuração do Tutor (texto de boas-vindas), Gerenciar Usuários, Atividades (telemetria).

## Rodar

```bash
cd /home/ubuntu/ensinado-aprendizado-maquina-back
venv/bin/python -m scripts.deploy.seed_usuarios_demo            # criar/atualizar
venv/bin/python -m scripts.deploy.seed_usuarios_demo --remover  # apagar tudo
```

Idempotente: rodar de novo não duplica nada e **preserva** as submissões e os pipelines já
existentes (inclusive o que a banca produzir testando). Se um dos e-mails já pertencer a uma
conta real (sem o marcador `demo: "banca"`), o script **aborta antes de escrever**.

## Depois da defesa, remova

`--remover` apaga as contas, a turma, as atividades e o que essas contas produziram
(pipelines, submissões e conversas com o tutor). O catálogo e os dados de outros usuários
não são tocados.

Vale insistir porque o login **não verifica `status`** (`app/routers/login.py`): desativar a
conta no painel do admin **não** bloqueia o acesso. Enquanto existirem, são três contas
reais com senha compartilhada — uma delas com poder de administrador.
