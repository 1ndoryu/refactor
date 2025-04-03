# config/settings.py
import os
import logging
from dotenv import load_dotenv

# Cargar variables de entorno desde .env al inicio
load_dotenv()

# --- Constantes Comunes ---
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Constantes para Rotación de Clave API Google Gemini ---
GEMINI_API_KEY_BASE_NAME = "GEMINI_API_KEY"
GEMINI_NUM_API_KEYS = 5 # O el número que tengas configurado para Gemini
GEMINI_API_KEY_STATE_FILE = os.path.join(_CONFIG_DIR, '.api_key_last_index.txt')

# --- NUEVO: Constantes para Rotación de Clave API OpenRouter ---
OPENROUTER_API_KEY_BASE_NAME = "OPENROUTER_API_KEY"
OPENROUTER_NUM_API_KEYS = 4 # Número de claves OpenRouter que tienes (0 a 3)
OPENROUTER_API_KEY_STATE_FILE = os.path.join(_CONFIG_DIR, '.openrouter_api_key_last_index.txt') # Archivo de estado DIFERENTE

# --- Funciones Auxiliares GENERALIZADAS ---

def _read_last_key_index(state_file, num_keys, provider_name):
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
            # print(f"settings ({provider_name}): Archivo de estado {state_file} no encontrado. Empezando desde el principio.") # Debug
            pass # Silencioso si no existe
    except Exception as e:
        print(f"settings ({provider_name}): WARN - Error leyendo estado de API key '{state_file}': {e}. Reiniciando.")
    # Si hay error, no existe, o es inválido, empezamos como si no se hubiera usado ninguna
    return -1

def _write_current_key_index(state_file, current_index, provider_name):
    """Escribe el índice de la clave actual en el archivo de estado."""
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, 'w') as f:
            f.write(str(current_index))
        # print(f"settings ({provider_name}): Guardado índice actual ({current_index}) en {state_file}") # Debug
    except Exception as e:
        print(f"settings ({provider_name}): ERROR - No se pudo guardar el estado del índice de API key en '{state_file}': {e}")

def _get_key_env_var_name(base_name, index):
    """Obtiene el nombre de la variable de entorno para un índice dado."""
    if index == 0:
        return base_name
    else:
        return f"{base_name}{index}"

# --- Lógica de Selección de Clave API Google Gemini (SIN CAMBIOS EN SU LÓGICA INTERNA) ---
print(f"settings: Iniciando selección de API Key Google Gemini...")
GEMINIAPIKEY = None # Inicializar a None
gemini_key_actually_used_index = -1
if GEMINI_NUM_API_KEYS > 0:
    last_used_index = _read_last_key_index(GEMINI_API_KEY_STATE_FILE, GEMINI_NUM_API_KEYS, "Gemini")
    current_key_index = (last_used_index + 1) % GEMINI_NUM_API_KEYS
    selected_key_name = _get_key_env_var_name(GEMINI_API_KEY_BASE_NAME, current_key_index)

    print(f"settings (Gemini): Intentando usar índice {current_key_index} ('{selected_key_name}')")
    GEMINIAPIKEY = os.getenv(selected_key_name)

    if not GEMINIAPIKEY:
        print(f"settings (Gemini): WARN - Clave '{selected_key_name}' no encontrada. Buscando la siguiente...")
        found_key = False
        for i in range(1, GEMINI_NUM_API_KEYS):
            fallback_index = (current_key_index + i) % GEMINI_NUM_API_KEYS
            fallback_key_name = _get_key_env_var_name(GEMINI_API_KEY_BASE_NAME, fallback_index)
            key_value = os.getenv(fallback_key_name)
            if key_value:
                print(f"settings (Gemini): Usando clave fallback encontrada: '{fallback_key_name}' (Index: {fallback_index})")
                GEMINIAPIKEY = key_value
                gemini_key_actually_used_index = fallback_index
                found_key = True
                break
        if not found_key:
            print(f"settings (Gemini): CRITICAL WARNING - ¡Ninguna clave API de Google Gemini encontrada!")
    else:
        gemini_key_actually_used_index = current_key_index

    if GEMINIAPIKEY and gemini_key_actually_used_index != -1:
        _write_current_key_index(GEMINI_API_KEY_STATE_FILE, gemini_key_actually_used_index, "Gemini")
    elif gemini_key_actually_used_index != -1 :
         print(f"settings (Gemini): No se guarda estado porque no se cargó clave válida.")
else:
    print(f"settings: GEMINI_NUM_API_KEYS es 0, no se buscarán claves Google Gemini.")


# --- NUEVO: Lógica de Selección de Clave API OpenRouter ---
print(f"settings: Iniciando selección de API Key OpenRouter...")
OPENROUTER_API_KEY = None # Inicializar a None (se sobreescribirá si se encuentra una)
openrouter_key_actually_used_index = -1
if OPENROUTER_NUM_API_KEYS > 0:
    # Usa las funciones generalizadas con las constantes de OpenRouter
    last_used_index_or = _read_last_key_index(OPENROUTER_API_KEY_STATE_FILE, OPENROUTER_NUM_API_KEYS, "OpenRouter")
    current_key_index_or = (last_used_index_or + 1) % OPENROUTER_NUM_API_KEYS
    selected_key_name_or = _get_key_env_var_name(OPENROUTER_API_KEY_BASE_NAME, current_key_index_or)

    print(f"settings (OpenRouter): Intentando usar índice {current_key_index_or} ('{selected_key_name_or}')")
    # Intenta cargar la clave seleccionada
    openrouter_api_key_selected_temp = os.getenv(selected_key_name_or)

    if not openrouter_api_key_selected_temp:
        print(f"settings (OpenRouter): WARN - Clave '{selected_key_name_or}' no encontrada. Buscando la siguiente...")
        found_key_or = False
        # Bucle de fallback
        for i in range(1, OPENROUTER_NUM_API_KEYS):
            fallback_index_or = (current_key_index_or + i) % OPENROUTER_NUM_API_KEYS
            fallback_key_name_or = _get_key_env_var_name(OPENROUTER_API_KEY_BASE_NAME, fallback_index_or)
            key_value_or = os.getenv(fallback_key_name_or)
            if key_value_or:
                print(f"settings (OpenRouter): Usando clave fallback encontrada: '{fallback_key_name_or}' (Index: {fallback_index_or})")
                openrouter_api_key_selected_temp = key_value_or
                openrouter_key_actually_used_index = fallback_index_or # Esta es la que realmente usaremos
                found_key_or = True
                break # Dejar de buscar
        if not found_key_or:
            print(f"settings (OpenRouter): CRITICAL WARNING - ¡Ninguna clave API de OpenRouter ({OPENROUTER_API_KEY_BASE_NAME} a {OPENROUTER_API_KEY_BASE_NAME}{OPENROUTER_NUM_API_KEYS-1}) fue encontrada en .env!")
            # openrouter_api_key_selected_temp permanecerá None
    else:
        # Si la clave seleccionada directamente funcionó
        openrouter_key_actually_used_index = current_key_index_or

    # Asignar la clave encontrada (o None) a la variable principal
    OPENROUTER_API_KEY = openrouter_api_key_selected_temp

    # Guardar el índice de la clave que REALMENTE se usó para la próxima ejecución
    # Solo guardar si efectivamente cargamos una clave
    if OPENROUTER_API_KEY and openrouter_key_actually_used_index != -1:
        _write_current_key_index(OPENROUTER_API_KEY_STATE_FILE, openrouter_key_actually_used_index, "OpenRouter")
    elif openrouter_key_actually_used_index != -1 : # Si se intentó usar una pero no se encontró
         print(f"settings (OpenRouter): No se guarda estado porque no se cargó clave válida.")
else:
    print(f"settings: OPENROUTER_NUM_API_KEYS es 0, no se buscarán claves OpenRouter.")


# --- Configuración OpenRouter (Resto de variables sin cambios) ---
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "<YOUR_SITE_URL>") # Reemplaza o pon en .env
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE", "<YOUR_SITE_NAME>")   # Reemplaza o pon en .env
# OPENROUTER_MODEL ya no se define aquí, se toma de la variable de entorno
# OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-1.5-pro-preview:free") # Modelo por defecto si no está en .env
# -- CORRECCIÓN: Mantener la definición del modelo como estaba antes --
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-pro-exp-03-25:free") # Modelo por defecto si no está en .env


# --- Configuracion Esencial (sin cambios) ---
REPOSITORIOURL = "git@github.com:2upra/v4.git"

# --- Configuracion de Rutas (sin cambios) ---
RUTA_BASE_PROYECTO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
RUTACLON = os.path.join(RUTA_BASE_PROYECTO, 'clonProyecto')
RUTAHISTORIAL = os.path.join(RUTA_BASE_PROYECTO, 'historial_refactor.log')

# --- Configuracion de Git (sin cambios) ---
RAMATRABAJO = "develop" # Cambia a tu rama real

# --- Configuracion de Modelos (Nombres/Identificadores) ---
MODELO_GOOGLE_GEMINI = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-exp-03-25") # Modelo Gemini
# MODELO_OPENROUTER ahora está en OPENROUTER_MODEL arriba

N_HISTORIAL_CONTEXTO = 30

# --- Configuracion de Analisis (sin cambios) ---
EXTENSIONESPERMITIDAS = ['.php', '.js', '.py', '.md']
DIRECTORIOS_IGNORADOS = ['vendor', 'node_modules', '.git', '.github', 'docs', 'assets', 'Tests', 'languages']

# --- Logging de Configuracion (Adaptado para mostrar estado de claves rotativas) ---
print(f"settings: Cargando configuración...")
# Google Gemini
if GEMINI_NUM_API_KEYS > 0:
    if not GEMINIAPIKEY:
        print("settings: WARNING - Google GEMINI_API_KEY no encontrada/cargada. Gemini no funcionará.")
    else:
        print(f"settings: Google Gemini API Key Index usado en esta ejecución: {gemini_key_actually_used_index}")
        print(f"settings: Google Gemini API Key cargada (parcial: ...{GEMINIAPIKEY[-4:]}).")
    print(f"settings: Modelo Google Gemini: {MODELO_GOOGLE_GEMINI}")

# OpenRouter
if OPENROUTER_NUM_API_KEYS > 0:
    if not OPENROUTER_API_KEY:
        print("settings: WARNING - OPENROUTER_API_KEY no encontrada/cargada. OpenRouter (--openrouter) no funcionará.")
    else:
        or_key_display = f"...{OPENROUTER_API_KEY[-4:]}"
        print(f"settings: OpenRouter API Key Index usado en esta ejecución: {openrouter_key_actually_used_index}")
        print(f"settings: OpenRouter API Key cargada: {or_key_display}")
    print(f"settings: OpenRouter Base URL: {OPENROUTER_BASE_URL}")
    print(f"settings: OpenRouter Referer: {OPENROUTER_REFERER}")
    print(f"settings: OpenRouter Title: {OPENROUTER_TITLE}")
    print(f"settings: OpenRouter Model: {OPENROUTER_MODEL}")

# Resto de logs sin cambios
print(f"settings: Repositorio URL: {REPOSITORIOURL}")
print(f"settings: Ruta Clon: {RUTACLON}")
print(f"settings: Ruta Historial: {RUTAHISTORIAL}")
print(f"settings: Rama de Trabajo: {RAMATRABAJO}")
print(f"settings: Entradas de Historial para Contexto: {N_HISTORIAL_CONTEXTO}")

log = logging.getLogger(__name__)
log.info("settings: Configuración cargada (mensajes anteriores vía print).")
if GEMINIAPIKEY:
    log.info(f"settings: Usando índice de Google Gemini API Key: {gemini_key_actually_used_index}")
if OPENROUTER_API_KEY:
    log.info(f"settings: Usando índice de OpenRouter API Key: {openrouter_key_actually_used_index}")
    log.info("settings: Configuración de OpenRouter lista.")