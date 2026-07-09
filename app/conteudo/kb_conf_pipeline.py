"""Base de conhecimento do assistente do admin na Configuração do Pipeline.

Fonte da verdade VERSIONADA do guia de preenchimento dos campos do
/view-admin/conf-pipeline. É semeada no MongoDB (db.tutor, pipe
'conf-pipeline') por scripts/deploy/seed_kb_conf_pipeline.py e usada como
fallback pelo GET /tutor/?pipe=conf-pipeline quando o doc ainda não existe.
O frontend injeta este texto como contexto do chat do admin.
"""

KB_CONF_PIPELINE = """
GUIA DE PREENCHIMENTO — CONFIGURAÇÃO DO PIPELINE (admin)

VISÃO GERAL
A tela /view-admin/conf-pipeline administra o catálogo que os alunos usam nas lanes:
Coleta, Pré-processamento, Modelos e Métricas. Cada item tem: um toggle Habilitado,
o painel "Campos do item" (ícone de lápis), o editor de Conteúdo educacional (ícone
de livro), o editor de Execução (ícone de ajustes) e o botão Excluir (lixeira).
Mudanças valem para os alunos ao recarregarem a página. O bloco "execucao" controla
COMO o item roda no treino e aparece no código Python gerado; o "conteudo" controla
o que o tutor mostra; os "campos do item" controlam identificação e compatibilidades.

CRIAR ELEMENTO NOVO (FAB > Criar)
- Nome (exibição/label): nome amigável mostrado ao aluno. Ex.: "Extra Trees".
- Valor (identificador): slug único em snake_case, sem espaços/acentos. Ex.:
  "extra_trees". É a chave do documento — não mude depois de criado.
- O elemento novo já abre com o editor de execução: preencha módulo, classe/função
  e hiperparâmetros antes de salvar.

BLOCO EXECUÇÃO
- Módulo Python: caminho do módulo. Só são aceitos módulos da allowlist do backend:
  "sklearn.*" (ex.: sklearn.ensemble, sklearn.preprocessing, sklearn.metrics) e
  "app.modelos_custom.*". Outros módulos são rejeitados no treino.
- Classe (modelos e pré-processadores): nome exato da classe sklearn. Ex.:
  RandomForestClassifier, StandardScaler. Confira na documentação do scikit-learn.
- Função (métricas): nome exato da função de sklearn.metrics. Ex.: accuracy_score,
  f1_score, root_mean_squared_error (sklearn >= 1.4).
- Hiperparâmetros (lista): para cada um informe
  * nome: exatamente como na assinatura do sklearn (ex.: n_estimators, max_depth);
  * tipo: int, float, str, bool ou enum;
  * default: valor padrão sugerido ao aluno — use o default REAL do sklearn;
  * min/max (só int/float): limites do controle exibido ao aluno;
  * opções (só enum): valores separados por vírgula (ex.: "gini, entropy, log_loss").
  Declare só hiperparâmetros que valham a pena o aluno mexer (3 a 6 costuma bastar).
- Pré-processamento também tem:
  * Aplica em: "Todas as features" (transforma todas as colunas de X) ou "Colunas
    escolhidas" (o aluno seleciona as colunas no modal);
  * escopo (não editável na tela): transform_X por padrão; label_encoder usa o alvo.
- Cuidado com versões: parâmetros deprecados quebram o treino (ex.: multi_class em
  LogisticRegression; use n_init="auto" no KMeans).

CAMPOS DO ITEM (painel do lápis)
- Resumo (todas as lanes): frase curta exibida no card do item para o aluno.
- Modelos:
  * Tipo de tarefa: Classificação, Regressão ou Agrupamento. Internamente vira
    prever_categoria/dados_rotulados e decide quais métricas/fluxos se aplicam.
  * Explicação: texto do tutor sobre o modelo (linguagem simples).
  * Métricas compatíveis: marque as métricas que fazem sentido para o modelo. Se
    NENHUMA for marcada, a compatibilidade é derivada automaticamente pelo grupo
    da métrica (classificacao/regressao/agrupamento) — geralmente suficiente.
- Métricas: Grupo (classificacao, regressao ou agrupamento — controla onde a
  métrica aparece) e Explicação.
- Pré-processamento: Grupo (scalers, encoders, imputers ou transformers — só
  organiza a listagem).

CONTEÚDO EDUCACIONAL (ícone de livro)
Preenche o card do tutor que o aluno vê ao clicar no "i" do item:
- titulo; descricao (aba Avançado, técnica); resumo_basico (aba Básico, linguagem
  de ensino fundamental/médio); intuicao (analogia do dia a dia); exemplo (caso
  concreto); exemplo_codigo (Python curto e executável — aparece colorido);
  formula (notação simples); conceitos (nome+descrição); quandoUsar/naoUsarQuando;
  vantagens/desvantagens; dicas; hiperparametros_doc (explicação didática de cada
  hiperparâmetro); link_sklearn e link_yellowbrick (URLs oficiais); referencias;
  midia (URLs de imagem/vídeo).
Boas práticas: confira valores e defaults na doc oficial do scikit-learn; escreva
o resumo_basico sem jargão; um exemplo_codigo de 5–10 linhas ensina mais que texto.

HABILITAR/DESABILITAR E EXCLUIR
- O toggle Habilitado esconde o item dos alunos sem apagar nada (reversível).
- Excluir remove o documento do catálogo em definitivo — prefira desabilitar.
  Excluir um modelo não apaga treinos já feitos, mas o item some das lanes.

EFEITOS PRÁTICOS
- O treino real instancia exatamente o módulo/classe/hiperparâmetros do bloco
  execução (num sklearn.Pipeline com os pré-processadores escolhidos).
- O código Python exportado pelo aluno é gerado a partir do mesmo bloco execução.
- As boas-vindas do tutor, o LLM do chat e o histórico de edições ficam na tela
  Configuração do Tutor (/view-admin/conf-tutor).
""".strip()
