# config/settings.py
import os
import logging
from dotenv import load_dotenv


load_dotenv()

GEMINIAPIKEY = os.getenv("GEMINI_API_KEY")
REPOSITORIOURL = "git@github.com:2upra/v4.git" 

RUTACLON = os.path.join(os.path.dirname(
    os.path.dirname(__file__)), 'clonProyecto')

if not GEMINIAPIKEY:
    logging.error(
        "settings: GEMINI_API_KEY no encontrada en el entorno. Asegurate que exista en .env")
else:
    logging.info("settings: GEMINI_API_KEY cargada.")

logging.info(f"settings: URL del repositorio a clonar: {REPOSITORIOURL}")
logging.info(f"settings: Ruta local para el clon: {RUTACLON}")
