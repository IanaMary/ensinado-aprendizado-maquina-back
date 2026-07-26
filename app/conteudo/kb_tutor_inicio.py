"""Boas-vindas do tutor — o que o aluno lê antes de clicar em qualquer coisa.

Fonte da verdade VERSIONADA do estado inicial do painel do tutor na Área de Trabalho.
É semeada no MongoDB (db.tutor, pipe 'inicio', campo `texto_pipe`) por
scripts/deploy/seed_tutor_inicio.py e usada como fallback pelo GET /tutor/?pipe=inicio
quando o documento ainda não existe. O admin pode editar em conf-tutor → Início; o seed
NÃO sobrescreve edição do admin.

O conteúdo resume o Manual do Aluno (`/manual?tipo=aluno`, seções Carregar Dados →
Pré-processamento → Treinar e Avaliar → Exportar): aqui fica o essencial para dar o
primeiro passo, o manual tem o detalhe.

Formato: HTML simples. O front renderiza com [innerHTML] passando pelo sanitizer do
Angular — use apenas h4/p/b/i/ul/ol/li. `style`, `script` e handlers são removidos.
"""

TUTOR_INICIO_HTML = """
<h4>Olá! Eu sou o seu tutor. 👋</h4>
<p>Nesta tela você monta um <b>pipeline de Aprendizado de Máquina</b> completo — dos dados
até a avaliação — e eu explico cada passo. Você treina modelos de verdade
(scikit-learn), compara resultados e pode levar embora o código Python.</p>
<p><b>Comece por aqui — são 4 passos, na ordem das colunas:</b></p>
<ol>
<li><b>Coleta:</b> clique no item da coluna <i>Coleta</i> para trazer os dados — um arquivo
(CSV, Excel, JSON), o link de um CSV público ou um <i>dataset de exemplo</i> (Iris, Wine…).
Depois escolha o <b>tipo de predição</b> (categoria ou número), o <b>rótulo</b> (a coluna a
prever) e confira a <b>divisão treino/teste</b>.</li>
<li><b>Pré-processamento</b> (opcional): prepare os dados — colocar as colunas numéricas na
mesma escala, transformar texto em número, preencher valores faltantes. O que você
configurar aqui é aplicado de verdade no treino.</li>
<li><b>Treinamento:</b> arraste um modelo (KNN, Árvore de Decisão, Floresta Aleatória…),
ajuste os hiperparâmetros se quiser e clique em <b>Treinar</b>. Quer comparar? Arraste
outro modelo: eu treino os dois com os mesmos dados.</li>
<li><b>Métricas:</b> escolha as métricas, clique em <b>Gerar avaliações</b> e veja como o
modelo se saiu — números e gráficos (matriz de confusão, resíduos e outros).</li>
</ol>
<p><b>Onde pedir ajuda:</b> o ícone <b>ⓘ</b> de cada item abre a explicação aqui neste
painel, em modo <i>Básico</i> ou <i>Avançado</i>. Se a dúvida for sobre o <i>seu</i>
pipeline, pergunte no <b>chat</b> logo abaixo — eu vejo os seus dados, o seu modelo e as
suas métricas.</p>
<p><b>Onde ficam as outras coisas:</b></p>
<ul>
<li><b>Turmas e desafios</b> (menu do seu avatar, no canto da tela): as atividades da sua
turma, incluindo os <b>desafios de montagem</b> — quebra-cabeças em que você monta o
pipeline e recebe uma nota com o retorno de cada ponto. Quando houver desafio novo, um
aviso aparece aqui no topo da tela.</li>
<li><b>Meus Projetos e Galeria</b> (no mesmo menu): salve o seu pipeline para continuar
depois e veja exemplos compartilhados.</li>
<li><b>Exportar</b>: ao final você baixa o <b>código Python</b> pronto para rodar, o
<b>modelo treinado</b> e um <b>relatório em PDF</b>.</li>
<li><b>Manual completo</b>: no menu do seu avatar → <b>Manual</b>, com o passo a passo
ilustrado de cada tela.</li>
</ul>
<p>Pode começar sem medo de errar: dá para recomeçar, trocar de modelo e tentar de novo
quantas vezes quiser. 😊</p>
""".strip()

# Texto de uma frase gravado pelo seed antigo (seed-mongodb.sh). O seed idempotente
# reconhece esse valor para poder substituí-lo sem pisar em edição feita pelo admin.
TUTOR_INICIO_LEGADO = "Bem-vindo ao tutor de Aprendizado de Máquina!"
