# config/settings.py
import os
import logging
from dotenv import load_dotenv

# Cargar variables de entorno desde .env al inicio
load_dotenv()

# --- Constantes para Rotación de Clave API ---
API_KEY_BASE_NAME = "GEMINI_API_KEY"
NUM_API_KEYS = 5  # GEMINI_API_KEY (0), GEMINI_API_KEY1 (1), ..., GEMINI_API_KEY4 (4)
# Archivo para guardar el índice de la última clave usada (en el mismo directorio que settings.py)
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_STATE_FILE = os.path.join(_CONFIG_DIR, '.api_key_last_index.txt') # Nombre con punto para indicar que es 'privado'

# --- Función para leer el último índice usado ---
def _read_last_key_index(state_file, num_keys):
    """Lee el índice de la última clave usada desde el archivo de estado."""
    try:
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                content = f.read().strip()
                if content.isdigit():
                    index = int(content)
                    if 0 <= index < num_keys:
                        # print(f"settings: Leído último índice usado: {index}") # Debug
                        return index
                    else:
                        print(f"settings: WARN - Índice inválido ({index}) en {state_file}. Reiniciando.")
                else:
                    print(f"settings: WARN - Contenido no numérico en {state_file}. Reiniciando.")
        else:
            # print(f"settings: Archivo de estado {state_file} no encontrado. Empezando desde el principio.") # Debug
            pass # Silencioso si no existe
    except Exception as e:
        print(f"settings: WARN - Error leyendo estado de API key '{state_file}': {e}. Reiniciando.")
    # Si hay error, no existe, o es inválido, empezamos como si no se hubiera usado ninguna
    return -1

# --- Función para escribir el índice actual (que será el último para la próxima vez) ---
def _write_current_key_index(state_file, current_index):
    """Escribe el índice de la clave usada en ESTA ejecución en el archivo de estado."""
    try:
        # Asegura que el directorio 'config' existe (aunque debería por estar este archivo)
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, 'w') as f:
            f.write(str(current_index))
        # print(f"settings: Guardado índice actual ({current_index}) en {state_file}") # Debug
    except Exception as e:
        # No es crítico si falla, la próxima vez reintentará desde -1, pero avisamos
        print(f"settings: ERROR - No se pudo guardar el estado del índice de API key en '{state_file}': {e}")

# --- Función para obtener el nombre de la variable de entorno de la clave ---
def _get_key_env_var_name(base_name, index):
    """Construye el nombre de la variable de entorno (GEMINI_API_KEY, GEMINI_API_KEY1, etc.)."""
    if index == 0:
        return base_name
    else:
        return f"{base_name}{index}"

# --- Lógica de Selección de Clave API ---
print(f"settings: Iniciando selección de API Key...")
last_used_index = _read_last_key_index(API_KEY_STATE_FILE, NUM_API_KEYS)
current_key_index = (last_used_index + 1) % NUM_API_KEYS
selected_key_name = _get_key_env_var_name(API_KEY_BASE_NAME, current_key_index)

print(f"settings: Intentando usar API Key index {current_key_index} ('{selected_key_name}')")
GEMINIAPIKEY = os.getenv(selected_key_name)
key_actually_used_index = -1 # Para saber cuál guardar al final

# Fallback: Si la clave seleccionada no existe, intentar las siguientes
if not GEMINIAPIKEY:
    print(f"settings: WARN - Clave '{selected_key_name}' no encontrada en .env. Buscando la siguiente disponible...")
    found_key = False
    # Empezar a buscar desde la siguiente a la que tocaba
    for i in range(1, NUM_API_KEYS): # Probar las N-1 restantes
        fallback_index = (current_key_index + i) % NUM_API_KEYS
        fallback_key_name = _get_key_env_var_name(API_KEY_BASE_NAME, fallback_index)
        key_value = os.getenv(fallback_key_name)
        if key_value:
            print(f"settings: Usando clave fallback encontrada: '{fallback_key_name}' (Index: {fallback_index})")
            GEMINIAPIKEY = key_value
            key_actually_used_index = fallback_index # Esta es la que realmente usaremos
            found_key = True
            break # Dejar de buscar
    if not found_key:
        print(f"settings: CRITICAL ERROR - ¡Ninguna clave API de Gemini ({API_KEY_BASE_NAME} a {API_KEY_BASE_NAME}{NUM_API_KEYS-1}) fue encontrada en .env!")
        # GEMINIAPIKEY permanecerá None, el chequeo más abajo lo indicará
else:
    # Si la clave seleccionada directamente funcionó
    key_actually_used_index = current_key_index

# Guardar el índice de la clave que REALMENTE se usó para la próxima ejecución
# Solo guardar si efectivamente cargamos una clave
if GEMINIAPIKEY and key_actually_used_index != -1:
    _write_current_key_index(API_KEY_STATE_FILE, key_actually_used_index)
else:
     print(f"settings: No se guarda estado de API key porque no se cargó ninguna clave válida.")


# --- Configuracion Esencial (Usa la GEMINIAPIKEY seleccionada arriba) ---
# GEMINIAPIKEY = os.getenv("GEMINI_API_KEY") # <-- Ya no se usa esta línea directa
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
RAMATRABAJO = "refactor-test-17"  # Nombre de la rama donde se aplicarán los cambios

# --- Configuracion de Gemini ---
# MODELOGEMINI = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-exp-03-25") # Mantener configurable el modelo
MODELOGEMINI = "gemini-2.0-flash"
N_HISTORIAL_CONTEXTO = 30  # Cuántas entradas recientes del historial enviar a Gemini

# --- Configuracion de Analisis (Opcional - No se usa por ahora) ---
DIRECTORIOANALISIS = "app/" # Ejemplo: "src/mi_modulo"
# ARCHIVOSANALISIS = None # Ejemplo: ["src/main.py", "src/utils.py"]
EXTENSIONESPERMITIDAS = ['.php', '.js', '.py', '.md']
DIRECTORIOS_IGNORADOS = ['vendor', 'node_modules', '.git', '.github', 'docs']

# --- Logging de Configuracion ---
# Asegurarse que el logger se configure antes si es posible, o usar print aquí
# Idealmente, configurar logging en principal.py antes de importar settings si se quiere loguear esto.
# Usaremos print por simplicidad aquí asumiendo que logging no está listo aún.

print(f"settings: Cargando configuración...") # Mensaje ya mostrado antes, pero repetimos por contexto
if not GEMINIAPIKEY:
    # Este mensaje ya debería haber sido mostrado en la lógica de selección si falló
    print("settings: ERROR CRÍTICO - GEMINI_API_KEY no encontrada/cargada. Asegúrate que al menos una de las claves (GEMINI_API_KEY, ..., GEMINI_API_KEY4) exista en .env")
else:
    # Mostrar qué índice se usó finalmente (útil si hubo fallback)
    print(f"settings: API Key Index usado en esta ejecución: {key_actually_used_index}")
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
# El log puede configurarse más tarde, así que usamos print arriba
log.info("settings: Configuración cargada (los mensajes anteriores fueron via print).")
if GEMINIAPIKEY:
    log.info(f"settings: Usando índice de API Key: {key_actually_used_index}")