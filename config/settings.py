# config/settings.py
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# --- Configuracion Esencial ---
# Mantenemos el nombre de la variable de entorno como está en .env
claveApiGemini = os.getenv("GEMINI_API_KEY")
urlRepositorio = "https://github.com/2upra/v4.git" # Ejemplo, asegúrate que sea la correcta

# --- Configuracion de Rutas ---
rutaBaseProyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rutaClon = os.path.join(rutaBaseProyecto, 'clonProyecto')
rutaHistorial = os.path.join(rutaBaseProyecto, 'historial_refactor.log')

# --- Configuracion de Git ---
ramaTrabajo = "refactor"

# --- Configuracion de Gemini ---
MODELOGEMINI = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-thinking-exp-01-21")
N_HISTORIAL_CONTEXTO = 30  # Cuántas entradas recientes del historial enviar a Gemini

# --- Configuracion de Analisis ---
# directorioAnalisis = "app/" # Ya no se usa directamente
extensionesPermitidas = ['.php', '.js', '.py', '.md'] # Mantenerlas en minúscula
directoriosIgnorados = ['vendor', 'node_modules', '.git', '.github', 'docs', 'cache', 'logs', 'tmp', 'temp'] # Lista más completa

# --- Logging de Configuracion (usando print antes de que logging esté listo) ---
print(f"settings: Cargando configuración...")
if not claveApiGemini:
    print("settings: ERROR - GEMINI_API_KEY no encontrada. Asegúrate que exista en .env")
else:
    print(f"settings: GEMINI_API_KEY cargada (parcial: ...{claveApiGemini[-4:]}).")

print(f"settings: Repositorio URL: {urlRepositorio}")
print(f"settings: Ruta Clon: {rutaClon}")
print(f"settings: Ruta Historial: {rutaHistorial}")
print(f"settings: Rama de Trabajo: {ramaTrabajo}")
print(f"settings: Modelo Gemini: {modeloGemini}")
print(f"settings: Entradas de Historial para Contexto: {numHistorialContexto}")
print(f"settings: Extensiones Permitidas: {extensionesPermitidas}")
print(f"settings: Directorios Ignorados: {directoriosIgnorados}")

# Configurar logger aquí si es necesario para mensajes posteriores de settings
# o confiar en que principal.py lo haga.
log = logging.getLogger(__name__)
# No loguear info aquí para evitar duplicados si principal.py ya lo hace.
# log.info("settings: Configuración cargada.")