from .coleta_dados_csv import router as coleta_dados_csv_router
from .coleta_dados_xlxs import router as coleta_dados_xlxs_router
from .coleta_dados_url import router as coleta_dados_url_router
from .configuracao_treinamento import router as configuracao_treinamento_router

routers = [
  coleta_dados_csv_router,
  coleta_dados_xlxs_router,
  coleta_dados_url_router,
  configuracao_treinamento_router,
]


