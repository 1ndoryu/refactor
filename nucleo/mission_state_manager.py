import os
import json
import logging
from config import settings

# Configurar logger para este módulo
log = logging.getLogger(__name__)

# --- Archivo para persistir el estado de la misión activa ---
ACTIVE_MISSION_STATE_FILE = os.path.join(
    settings.RUTACLON, ".orion_meta", ".active_mission")

def cargar_estado_mision_activa():
    logPrefix = "mission_state_manager.cargar_estado_mision_activa:"
    if os.path.exists(ACTIVE_MISSION_STATE_FILE):
        try:
            with open(ACTIVE_MISSION_STATE_FILE, 'r', encoding='utf-8') as f:
                nombre_clave_mision = f.read().strip()
                if nombre_clave_mision:
                    log.info(
                        f"{logPrefix} Misión activa encontrada: '{nombre_clave_mision}'")
                    return nombre_clave_mision
                else:
                    log.warning(
                        f"{logPrefix} Archivo de estado de misión vacío.")
                    # Limpiar si está vacío
                    os.remove(ACTIVE_MISSION_STATE_FILE)
                    return None
        except Exception as e:
            log.error(
                f"{logPrefix} Error cargando estado de misión activa: {e}", exc_info=True)
            return None
    log.info(
        f"{logPrefix} No se encontró archivo de estado de misión activa.")
    return None

def guardar_estado_mision_activa(nombre_clave_mision: str):
    logPrefix = "mission_state_manager.guardar_estado_mision_activa:"
    try:
        os.makedirs(os.path.dirname(ACTIVE_MISSION_STATE_FILE), exist_ok=True)
        with open(ACTIVE_MISSION_STATE_FILE, 'w', encoding='utf-8') as f:
            f.write(nombre_clave_mision)
        log.info(
            f"{logPrefix} Estado de misión activa '{nombre_clave_mision}' guardado.")
    except Exception as e:
        log.error(
            f"{logPrefix} Error guardando estado de misión activa '{nombre_clave_mision}': {e}", exc_info=True)

def limpiar_estado_mision_activa():
    logPrefix = "mission_state_manager.limpiar_estado_mision_activa:"
    if os.path.exists(ACTIVE_MISSION_STATE_FILE):
        try:
            os.remove(ACTIVE_MISSION_STATE_FILE)
            log.info(f"{logPrefix} Estado de misión activa limpiado.")
        except Exception as e:
            log.error(
                f"{logPrefix} Error limpiando estado de misión activa: {e}", exc_info=True)
    else:
        log.info(
            f"{logPrefix} No había estado de misión activa para limpiar.")
