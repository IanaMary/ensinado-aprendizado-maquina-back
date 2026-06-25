import sys
import json
import logging
from loguru import logger

# Intercepta os logs padrão do FastAPI/Uvicorn para o Loguru
class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

def setup_logging():
    # Remove o handler padrão
    logger.remove()
    
    # Adiciona log pro console (mais legível)
    logger.add(sys.stdout, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    
    # Adiciona log serializado para arquivo (bom para consultar depois)
    logger.add("logs/backend.log", serialize=True, rotation="10 MB", retention="1 month")
    
    # Configura os loggers nativos para usarem o InterceptHandler
    logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
    logging.getLogger("uvicorn.error").handlers = [InterceptHandler()]
    logging.getLogger("fastapi").handlers = [InterceptHandler()]
    
    # Suprime alguns logs muito verbosos se quiser:
    # logging.getLogger("motor").setLevel(logging.ERROR)

def get_last_logs(lines=100):
    try:
        with open("logs/backend.log", "r") as f:
            all_lines = f.readlines()
            # Retorna as últimas N linhas do arquivo de log invertidas (mais recentes primeiro)
            recent_logs = [json.loads(line) for line in reversed(all_lines[-lines:])]
            return recent_logs
    except FileNotFoundError:
        return []
