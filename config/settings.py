# config/settings.py
import os
import logging
from dotenv import load_dotenv

# Cargar variables de entorno desde .env al inicio
load_dotenv()

# --- Constantes y Directorio de Configuración ---
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Constantes para Rotación de Clave API Google Gemini ---
GEMINI_API_KEY_BASE_NAME = "GEMINI_API_KEY"
GEMINI_NUM_API_KEYS = 5 # O el número que tengas configurado para Gemini
GEMINI_API_KEY_STATE_FILE = os.path.join(_CONFIG_DIR, '.api_key_last_index.txt')

# --- NUEVO: Constantes para Rotación de Clave API OpenRouter ---
OPENROUTER_API_KEY_BASE_NAME = "OPENROUTER_API_KEY"
OPENROUTER_NUM_API_KEYS = 4 # Número de claves OpenRouter que tienes (0 a 3)
OPENROUTER_API_KEY_STATE_FILE = os.path.join(_CONFIG_DIR, '.openrouter_api_key_last_index.txt') # Archivo de estado DIFERENTE

# --- Función para leer el último índice usado (Reutilizable) ---
def _read_last_key_index(state_file, num_keys, provider_name="API"): # Añadido provider_name para logs
    """Lee el último índice de clave usado desde un archivo de estado."""
    try:
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                content = f.read().strip()
                if content.isdigit():
                    index = int(content)
                    if 0 <= index < num_keys:
                        # print(f"settings ({provider_name}): Leído último índice usado: {index}") # Debug
                        return index
                    else:
                        print(f"settings ({provider_name}): WARN - Índice inválido ({index}) en {state_file}. Reiniciando.")
                else:
                    print(f"settings ({provider_name}): WARN - Contenido no numérico en {state_file}. Reiniciando.")
        else:
            # print(f"settings ({provider_name}): Archivo de estado {state_file} no encontrado.") # Debug
            pass # Silencioso si no existe
    except Exception as e:
        print(f"settings ({provider_name}): WARN - Error leyendo estado de API key '{state_file}': {e}. Reiniciando.")
    return -1


# --- Función para escribir el índice actual (Reutilizable) ---
def _write_current_key_index(state_file, current_index, provider_name="API"): # Añadido provider_name para logs
    """Escribe el índice de la clave actual en el archivo de estado."""
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, 'w') as f:
            f.write(str(current_index))
        # print(f"settings ({provider_name}): Guardado índice actual ({current_index}) en {state_file}") # Debug
    except Exception as e:
        print(f"settings ({provider_name}): ERROR - No se pudo guardar el estado del índice de API key en '{state_file}': {e}")


# --- Función para obtener el nombre de la variable de entorno de la clave (Reutilizable) ---
def _get_key_env_var_name(base_name, index):
    """Obtiene el nombre de la variable de entorno para un índice dado."""
    if index == 0:
        return base_name
    else:
        return f"{base_name}{index}"

# --- Lógica de Selección de Clave API Google Gemini (sin cambios funcionales) ---
print(f"settings: Iniciando selección de API Key Google Gemini...")
GEMINIAPIKEY = None
gemini_key_actually_used_index = -1
if GEMINI_NUM_API_KEYS > 0:
    last_used_index_gemini = _read_last_key_index(GEMINI_API_KEY_STATE_FILE, GEMINI_NUM_API_KEYS, "Gemini")
    current_key_index_gemini = (last_used_index_gemini + 1) % GEMINI_NUM_API_KEYS
    selected_key_name_gemini = _get_key_env_var_name(GEMINI_API_KEY_BASE_NAME, current_key_index_gemini)

    print(f"settings (Gemini): Intentando usar índice {current_key_index_gemini} ('{selected_key_name_gemini}')")
    GEMINIAPIKEY = os.getenv(selected_key_name_gemini)

    if not GEMINIAPIKEY:
        print(f"settings (Gemini): WARN - Clave '{selected_key_name_gemini}' no encontrada. Buscando la siguiente...")
        found_key_gemini = False
        for i in range(1, GEMINI_NUM_API_KEYS):
            fallback_index_gemini = (current_key_index_gemini + i) % GEMINI_NUM_API_KEYS
            fallback_key_name_gemini = _get_key_env_var_name(GEMINI_API_KEY_BASE_NAME, fallback_index_gemini)
            key_value_gemini = os.getenv(fallback_key_name_gemini)
            if key_value_gemini:
                print(f"settings (Gemini): Usando clave fallback encontrada: '{fallback_key_name_gemini}' (Index: {fallback_index_gemini})")
                GEMINIAPIKEY = key_value_gemini
                gemini_key_actually_used_index = fallback_index_gemini
                found_key_gemini = True
                break
        if not found_key_gemini:
            print(f"settings (Gemini): CRITICAL WARNING - ¡Ninguna clave API de Google Gemini encontrada!")
    else:
        gemini_key_actually_used_index = current_key_index_gemini

    if GEMINIAPIKEY and gemini_key_actually_used_index != -1:
        _write_current_key_index(GEMINI_API_KEY_STATE_FILE, gemini_key_actually_used_index, "Gemini")
    elif gemini_key_actually_used_index != -1 :
         print(f"settings (Gemini): No se guarda estado porque no se cargó clave válida.")
else:
    print(f"settings: GEMINI_NUM_API_KEYS es 0, no se buscarán claves Google Gemini.")


# --- NUEVO: Lógica de Selección de Clave API OpenRouter ---
print(f"settings: Iniciando selección de API Key OpenRouter...")
# Inicializa la variable que usa el resto del código. Se sobreescribirá si encontramos una clave.
OPENROUTER_API_KEY = os.getenv(OPENROUTER_API_KEY_BASE_NAME, "") # Intenta cargar la base por defecto primero
openrouter_key_actually_used_index = -1 # Índice que realmente se usará

if OPENROUTER_NUM_API_KEYS > 0:
    # Leer el último índice USADO para OpenRouter
    last_used_index_or = _read_last_key_index(OPENROUTER_API_KEY_STATE_FILE, OPENROUTER_NUM_API_KEYS, "OpenRouter")
    # Calcular el índice que TOCA usar ahora
    current_key_index_or = (last_used_index_or + 1) % OPENROUTER_NUM_API_KEYS
    # Obtener el nombre de la variable de entorno para el índice que toca
    selected_key_name_or = _get_key_env_var_name(OPENROUTER_API_KEY_BASE_NAME, current_key_index_or)

    print(f"settings (OpenRouter): Intentando usar índice {current_key_index_or} ('{selected_key_name_or}')")
    # Intentar cargar la clave que toca
    openrouter_api_key_to_use = os.getenv(selected_key_name_or)

    # Fallback: Si la clave que tocaba no existe, buscar la siguiente
    if not openrouter_api_key_to_use:
        print(f"settings (OpenRouter): WARN - Clave '{selected_key_name_or}' no encontrada. Buscando la siguiente...")
        found_key_or = False
        # Probar las N-1 claves restantes en orden cíclico
        for i in range(1, OPENROUTER_NUM_API_KEYS):
            # Calcular el índice de la siguiente clave a probar
            fallback_index_or = (current_key_index_or + i) % OPENROUTER_NUM_API_KEYS
            fallback_key_name_or = _get_key_env_var_name(OPENROUTER_API_KEY_BASE_NAME, fallback_index_or)
            key_value_or = os.getenv(fallback_key_name_or)
            # Si encontramos una clave válida
            if key_value_or:
                print(f"settings (OpenRouter): Usando clave fallback encontrada: '{fallback_key_name_or}' (Index: {fallback_index_or})")
                openrouter_api_key_to_use = key_value_or
                openrouter_key_actually_used_index = fallback_index_or # Esta es la que realmente usaremos
                found_key_or = True
                break # Dejar de buscar
        # Si después de buscar no encontramos ninguna
        if not found_key_or:
            print(f"settings (OpenRouter): CRITICAL WARNING - ¡Ninguna clave API de OpenRouter encontrada ({OPENROUTER_API_KEY_BASE_NAME} a {OPENROUTER_API_KEY_BASE_NAME}{OPENROUTER_NUM_API_KEYS-1})!")
            openrouter_api_key_to_use = None # Asegurar que sea None
    else:
        # Si la clave que tocaba directamente funcionó
        openrouter_key_actually_used_index = current_key_index_or

    # <<< IMPORTANTE: Sobreescribir la variable OPENROUTER_API_KEY con la que se seleccionó >>>
    OPENROUTER_API_KEY = openrouter_api_key_to_use

    # Guardar el índice de la clave que REALMENTE se usó para la próxima ejecución
    # Solo guardar si efectivamente cargamos una clave
    if OPENROUTER_API_KEY and openrouter_key_actually_used_index != -1:
        _write_current_key_index(OPENROUTER_API_KEY_STATE_FILE, openrouter_key_actually_used_index, "OpenRouter")
    elif openrouter_key_actually_used_index != -1 : # Si se intentó usar una pero no se encontró
         print(f"settings (OpenRouter): No se guarda estado porque no se cargó ninguna clave válida.")
else:
    # Si no hay claves OpenRouter configuradas para rotar, mantiene el valor cargado inicialmente
    print(f"settings: OPENROUTER_NUM_API_KEYS es 0, no se aplicará rotación para OpenRouter. Usando '{OPENROUTER_API_KEY_BASE_NAME}' si existe.")
    # Verifica si la clave base (sin número) existe
    if not OPENROUTER_API_KEY:
         print(f"settings (OpenRouter): Clave base '{OPENROUTER_API_KEY_BASE_NAME}' tampoco encontrada.")


# --- Configuración OpenRouter (Resto sin cambios) ---
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "<YOUR_SITE_URL>")
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE", "<YOUR_SITE_NAME>")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-pro-exp-03-25:free") # Mantenemos tu modelo


# --- Configuracion Esencial (sin cambios) ---
REPOSITORIOURL = "git@github.com:2upra/v4.git" # Manteniendo tu configuración

# --- Configuracion de Rutas (sin cambios) ---
RUTA_BASE_PROYECTO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
RUTACLON = os.path.join(RUTA_BASE_PROYECTO, 'clonProyecto')
RUTAHISTORIAL = os.path.join(RUTA_BASE_PROYECTO, 'historial_refactor.log')

# --- Configuracion de Git (sin cambios) ---
RAMATRABAJO = "refactor-2" # Manteniendo tu configuración

# --- Configuracion de Modelos (sin cambios) ---
MODELO_GOOGLE_GEMINI = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-exp-03-25") # Manteniendo tu configuración
# OPENROUTER_MODEL ya está definido arriba

N_HISTORIAL_CONTEXTO = 30 # Manteniendo tu configuración

# --- NUEVO: Configuración del Timeout Global del Script ---
SCRIPT_EXECUTION_TIMEOUT_SECONDS = int(os.getenv("SCRIPT_EXECUTION_TIMEOUT_SECONDS", 5 * 60)) # Default 5 minutos

# --- Configuracion de Analisis (sin cambios) ---
EXTENSIONESPERMITIDAS = ['.php', '.js', '.py', '.md'] # Manteniendo tu configuración
DIRECTORIOS_IGNORADOS = ['vendor', 'node_modules', '.git', '.github', 'docs', 'assets', 'Tests', 'languages'] # Manteniendo tu configuración

# --- Logging de Configuracion (Adaptado para mostrar ambos índices) ---
print(f"settings: Cargando configuración...")
# Google Gemini
if GEMINI_NUM_API_KEYS > 0:
    if not GEMINIAPIKEY:
        print("settings: WARNING - Google GEMINI_API_KEY no encontrada/cargada. Gemini no funcionará.")
    else:
        print(f"settings (Gemini): API Key Index usado: {gemini_key_actually_used_index}")
        print(f"settings (Gemini): API Key cargada (parcial: ...{GEMINIAPIKEY[-4:]}).")
else:
    print("settings (Gemini): Rotación desactivada (NUM_API_KEYS=0).")
print(f"settings (Gemini): Modelo: {MODELO_GOOGLE_GEMINI}")


# OpenRouter
if OPENROUTER_NUM_API_KEYS > 0:
    if not OPENROUTER_API_KEY:
        # Este mensaje ya debería haber sido mostrado si falló la carga/fallback
        print("settings: WARNING - OPENROUTER_API_KEY no encontrada/cargada. OpenRouter (--openrouter) no funcionará.")
    else:
        or_key_display = f"...{OPENROUTER_API_KEY[-4:]}"
        print(f"settings (OpenRouter): API Key Index usado: {openrouter_key_actually_used_index}") # Mostrar índice usado
        print(f"settings (OpenRouter): API Key cargada: {or_key_display}")
else:
    # Si la rotación está desactivada pero la clave base SÍ existe
    if OPENROUTER_API_KEY:
         or_key_display = f"...{OPENROUTER_API_KEY[-4:]}"
         print(f"settings (OpenRouter): Rotación desactivada (NUM_API_KEYS=0). Usando clave base: {or_key_display}")
    else:
         print("settings (OpenRouter): Rotación desactivada y clave base no encontrada.")

print(f"settings (OpenRouter): Base URL: {OPENROUTER_BASE_URL}")
print(f"settings (OpenRouter): Referer: {OPENROUTER_REFERER}")
print(f"settings (OpenRouter): Title: {OPENROUTER_TITLE}")
print(f"settings (OpenRouter): Model: {OPENROUTER_MODEL}")

# Resto de logs sin cambios
print(f"settings: Repositorio URL: {REPOSITORIOURL}")
print(f"settings: Ruta Clon: {RUTACLON}")
print(f"settings: Ruta Historial: {RUTAHISTORIAL}")
print(f"settings: Rama de Trabajo: {RAMATRABAJO}")
print(f"settings: Entradas de Historial para Contexto: {N_HISTORIAL_CONTEXTO}")
print(f"settings: Timeout Global del Script: {SCRIPT_EXECUTION_TIMEOUT_SECONDS} segundos") # Log para el nuevo setting

# Configuración del logger (sin cambios)
log = logging.getLogger(__name__)
log.info("settings: Configuración cargada (mensajes anteriores vía print).")
# Añadir logs informativos finales sobre los índices
if GEMINIAPIKEY and gemini_key_actually_used_index != -1:
    log.info(f"settings: Usando índice de Google Gemini API Key: {gemini_key_actually_used_index}")
if OPENROUTER_API_KEY and openrouter_key_actually_used_index != -1:
    log.info(f"settings: Usando índice de OpenRouter API Key: {openrouter_key_actually_used_index}")
elif OPENROUTER_API_KEY and OPENROUTER_NUM_API_KEYS == 0:
    log.info("settings: Usando clave base de OpenRouter (rotación desactivada).")
log.info(f"settings: Timeout Global del Script configurado a {SCRIPT_EXECUTION_TIMEOUT_SECONDS} segundos.") # Log para el nuevo setting