# config/settings.py
import os
import logging
from dotenv import load_dotenv

# Cargar variables de entorno desde .env al inicio
load_dotenv()

# --- Configuracion Esencial ---
GEMINIAPIKEY = os.getenv("GEMINI_API_KEY")
REPOSITORIOURL = "git@github.com:2upra/v4.git"

# --- Configuracion de Rutas ---
# __file__ es la ruta de settings.py
# os.path.dirname(__file__) es el directorio config/
# os.path.dirname(os.path.dirname(__file__)) es la raíz del proyecto 1ndoryu-refactor/
RUTA_BASE_PROYECTO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
RUTACLON = os.path.join(RUTA_BASE_PROYECTO, 'clonProyecto')
RUTAHISTORIAL = os.path.join(RUTA_BASE_PROYECTO, 'historial_refactor.log')

# --- Configuracion de Git ---
RAMATRABAJO = "refactor-test-9"  # Nombre de la rama donde se aplicarán los cambios

# --- Configuracion de Gemini ---
MODELOGEMINI = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-thinking-exp-01-21")
N_HISTORIAL_CONTEXTO = 200  # Cuántas entradas recientes del historial enviar a Gemini

# --- Configuracion de Analisis (Opcional - No se usa por ahora) ---
DIRECTORIOANALISIS = "app/" # Ejemplo: "src/mi_modulo"
# ARCHIVOSANALISIS = None # Ejemplo: ["src/main.py", "src/utils.py"]
EXTENSIONESPERMITIDAS = ['.php', '.js', '.py', '.md']
DIRECTORIOS_IGNORADOS = ['vendor', 'node_modules', '.git', '.github', 'docs'] 

# --- Logging de Configuracion ---
# Asegurarse que el logger se configure antes si es posible, o usar print aquí
# Idealmente, configurar logging en principal.py antes de importar settings si se quiere loguear esto.
# Usaremos print por simplicidad aquí asumiendo que logging no está listo aún.

print(f"settings: Cargando configuración...")
if not GEMINIAPIKEY:
    print("settings: ERROR - GEMINI_API_KEY no encontrada. Asegúrate que exista en .env")
else:
    # Solo mostrar una parte por seguridad si se loguea
    print(
        f"settings: GEMINI_API_KEY cargada (parcial: ...{GEMINIAPIKEY[-4:]}).")

print(f"settings: Repositorio URL: {REPOSITORIOURL}")
print(f"settings: Ruta Clon: {RUTACLON}")
print(f"settings: Ruta Historial: {RUTAHISTORIAL}")
print(f"settings: Rama de Trabajo: {RAMATRABAJO}")
print(f"settings: Modelo Gemini: {MODELOGEMINI}")
print(f"settings: Entradas de Historial para Contexto: {N_HISTORIAL_CONTEXTO}")

# Configurar logger aquí si es necesario para mensajes posteriores de settings
# o confiar en que principal.py lo haga. Para evitar duplicados, es mejor
# que principal.py lo configure una vez.
log = logging.getLogger(__name__)
log.info("settings: Configuración cargada (los mensajes anteriores pueden ser via print).")
