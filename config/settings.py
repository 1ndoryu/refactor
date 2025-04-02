# config/settings.py
import os
import logging
from dotenv import load_dotenv

# Cargar variables de entorno desde .env al inicio
load_dotenv()

# --- Constantes para Rotación de Clave API Google Gemini ---
API_KEY_BASE_NAME = "GEMINI_API_KEY"
NUM_API_KEYS = 1 # O el número que tengas configurado
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_STATE_FILE = os.path.join(_CONFIG_DIR, '.api_key_last_index.txt')

# --- Función para leer el último índice usado (Google Gemini) ---
def _read_last_key_index(state_file, num_keys):
    # ... (tu código existente sin cambios) ...
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


# --- Función para escribir el índice actual (Google Gemini) ---
def _write_current_key_index(state_file, current_index):
    # ... (tu código existente sin cambios) ...
    try:
        # Asegura que el directorio 'config' existe (aunque debería por estar este archivo)
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, 'w') as f:
            f.write(str(current_index))
        # print(f"settings: Guardado índice actual ({current_index}) en {state_file}") # Debug
    except Exception as e:
        # No es crítico si falla, la próxima vez reintentará desde -1, pero avisamos
        print(f"settings: ERROR - No se pudo guardar el estado del índice de API key en '{state_file}': {e}")


# --- Función para obtener el nombre de la variable de entorno de la clave (Google Gemini) ---
def _get_key_env_var_name(base_name, index):
    # ... (tu código existente sin cambios) ...
    if index == 0:
        return base_name
    else:
        return f"{base_name}{index}"

# --- Lógica de Selección de Clave API Google Gemini ---
print(f"settings: Iniciando selección de API Key Google Gemini...")
GEMINIAPIKEY = None # Inicializar a None
key_actually_used_index = -1 # Para saber cuál guardar al final
if NUM_API_KEYS > 0: # Solo ejecutar si hay claves Gemini configuradas
    last_used_index = _read_last_key_index(API_KEY_STATE_FILE, NUM_API_KEYS)
    current_key_index = (last_used_index + 1) % NUM_API_KEYS
    selected_key_name = _get_key_env_var_name(API_KEY_BASE_NAME, current_key_index)

    print(f"settings: Intentando usar Google Gemini API Key index {current_key_index} ('{selected_key_name}')")
    GEMINIAPIKEY = os.getenv(selected_key_name)

    # Fallback: Si la clave seleccionada no existe, intentar las siguientes
    if not GEMINIAPIKEY:
        print(f"settings: WARN - Clave Google Gemini '{selected_key_name}' no encontrada en .env. Buscando la siguiente disponible...")
        found_key = False
        # Empezar a buscar desde la siguiente a la que tocaba
        for i in range(1, NUM_API_KEYS): # Probar las N-1 restantes
            fallback_index = (current_key_index + i) % NUM_API_KEYS
            fallback_key_name = _get_key_env_var_name(API_KEY_BASE_NAME, fallback_index)
            key_value = os.getenv(fallback_key_name)
            if key_value:
                print(f"settings: Usando clave Google Gemini fallback encontrada: '{fallback_key_name}' (Index: {fallback_index})")
                GEMINIAPIKEY = key_value
                key_actually_used_index = fallback_index # Esta es la que realmente usaremos
                found_key = True
                break # Dejar de buscar
        if not found_key:
            print(f"settings: CRITICAL WARNING - ¡Ninguna clave API de Google Gemini ({API_KEY_BASE_NAME} a {API_KEY_BASE_NAME}{NUM_API_KEYS-1}) fue encontrada en .env!")
            # GEMINIAPIKEY permanecerá None
    else:
        # Si la clave seleccionada directamente funcionó
        key_actually_used_index = current_key_index

    # Guardar el índice de la clave que REALMENTE se usó para la próxima ejecución
    # Solo guardar si efectivamente cargamos una clave
    if GEMINIAPIKEY and key_actually_used_index != -1:
        _write_current_key_index(API_KEY_STATE_FILE, key_actually_used_index)
    elif key_actually_used_index != -1 : # Si se intentó usar una pero no se encontró
         print(f"settings: No se guarda estado de Google Gemini API key porque no se cargó ninguna clave válida.")
else:
    print(f"settings: NUM_API_KEYS es 0, no se buscarán claves Google Gemini.")


# --- NUEVO: Configuración OpenRouter ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "") # Tu clave por defecto o desde .env
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# Asegúrate de tener estas variables en tu .env o pon los valores directamente aquí si son fijos
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "<YOUR_SITE_URL>") # Reemplaza o pon en .env
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE", "<YOUR_SITE_NAME>")   # Reemplaza o pon en .env
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-pro-exp-03-25:free") # El modelo gratuito que mencionaste


# --- Configuracion Esencial ---
REPOSITORIOURL = "git@github.com:2upra/v4.git"

# --- Configuracion de Rutas ---
RUTA_BASE_PROYECTO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
RUTACLON = os.path.join(RUTA_BASE_PROYECTO, 'clonProyecto')
RUTAHISTORIAL = os.path.join(RUTA_BASE_PROYECTO, 'historial_refactor.log')

# --- Configuracion de Git ---
RAMATRABAJO = "refactor-test-19"

# --- Configuracion de Modelos (Nombres/Identificadores) ---
# Modelo Google Gemini (usado si no se activa --openrouter)
MODELO_GOOGLE_GEMINI = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-exp-03-25") # Mantenemos el nombre configurable para Google
# Modelo OpenRouter (usado si se activa --openrouter) - Ya definido arriba como OPENROUTER_MODEL

N_HISTORIAL_CONTEXTO = 30

# --- Configuracion de Analisis ---
EXTENSIONESPERMITIDAS = ['.php', '.js', '.py', '.md']
DIRECTORIOS_IGNORADOS = ['vendor', 'node_modules', '.git', '.github', 'docs', 'assets', 'Tests', 'languages'] # Añadidos los de tu ejemplo

# --- Logging de Configuracion ---
print(f"settings: Cargando configuración...")
# Google Gemini
if not GEMINIAPIKEY and NUM_API_KEYS > 0:
    # Este mensaje ya debería haber sido mostrado en la lógica de selección si falló
    print("settings: WARNING - Google GEMINI_API_KEY no encontrada/cargada. Se usará OpenRouter si se activa, de lo contrario fallará.")
elif GEMINIAPIKEY:
    print(f"settings: Google Gemini API Key Index usado en esta ejecución: {key_actually_used_index}")
    print(f"settings: Google Gemini API Key cargada (parcial: ...{GEMINIAPIKEY[-4:]}).")
    print(f"settings: Modelo Google Gemini: {MODELO_GOOGLE_GEMINI}")

# OpenRouter
if not OPENROUTER_API_KEY:
     print("settings: WARNING - OPENROUTER_API_KEY no encontrada. La opción --openrouter fallará si se usa.")
else:
     # Oculta la clave por defecto si sigue siendo la de ejemplo
     or_key_display = f"...{OPENROUTER_API_KEY[-4:]}" if OPENROUTER_API_KEY != "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" else "(Clave Ejemplo)"
     print(f"settings: OpenRouter API Key cargada: {or_key_display}")
     print(f"settings: OpenRouter Base URL: {OPENROUTER_BASE_URL}")
     print(f"settings: OpenRouter Referer: {OPENROUTER_REFERER}")
     print(f"settings: OpenRouter Title: {OPENROUTER_TITLE}")
     print(f"settings: OpenRouter Model: {OPENROUTER_MODEL}")


print(f"settings: Repositorio URL: {REPOSITORIOURL}")
print(f"settings: Ruta Clon: {RUTACLON}")
print(f"settings: Ruta Historial: {RUTAHISTORIAL}")
print(f"settings: Rama de Trabajo: {RAMATRABAJO}")
print(f"settings: Entradas de Historial para Contexto: {N_HISTORIAL_CONTEXTO}")

log = logging.getLogger(__name__)
log.info("settings: Configuración cargada (mensajes anteriores vía print).")
if GEMINIAPIKEY:
    log.info(f"settings: Usando índice de Google Gemini API Key: {key_actually_used_index}")
if OPENROUTER_API_KEY:
    log.info("settings: Configuración de OpenRouter lista.")