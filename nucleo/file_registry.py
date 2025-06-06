import os
import json
import logging
from datetime import datetime
from config import settings
from nucleo import analizadorCodigo

# --- Constantes y Variables Globales ---
REGISTRO_ARCHIVOS_ANALIZADOS_PATH = os.path.join(
    settings.RUTACLON, ".orion_meta", "registro_archivos_analizados.json")

# --- Funciones para el registro de archivos analizados ---
def cargar_registro_archivos():
    if os.path.exists(REGISTRO_ARCHIVOS_ANALIZADOS_PATH):
        try:
            with open(REGISTRO_ARCHIVOS_ANALIZADOS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.error(
                f"Error decodificando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}. Se creará uno nuevo.")
        except Exception as e:
            logging.error(
                f"Error cargando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}: {e}. Se creará uno nuevo.")
    return {}


def guardar_registro_archivos(registro):
    try:
        os.makedirs(os.path.dirname(
            REGISTRO_ARCHIVOS_ANALIZADOS_PATH), exist_ok=True)
        with open(REGISTRO_ARCHIVOS_ANALIZADOS_PATH, 'w', encoding='utf-8') as f:
            json.dump(registro, f, indent=4)
    except Exception as e:
        logging.error(
            f"Error guardando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}: {e}")


def seleccionar_archivo_mas_antiguo(ruta_proyecto, registro_archivos):
    logPrefix = "seleccionar_archivo_mas_antiguo:"
    archivos_proyecto_abs = analizadorCodigo.listarArchivosProyecto(
        ruta_proyecto,
        extensionesPermitidas=settings.EXTENSIONESPERMITIDAS,
        directoriosIgnorados=settings.DIRECTORIOS_IGNORADOS
    )
    if not archivos_proyecto_abs:
        logging.warning(
            f"{logPrefix} No se encontraron archivos en el proyecto que coincidan con los criterios.")
        return None

    archivo_seleccionado_rel = None
    timestamp_mas_antiguo = datetime.max.isoformat()
    archivos_proyecto_relativos = []
    for abs_path in archivos_proyecto_abs:
        try:
            rel_path = os.path.relpath(
                abs_path, ruta_proyecto).replace(os.sep, '/')
            archivos_proyecto_relativos.append(rel_path)
        except ValueError as e:
            logging.warning(
                f"{logPrefix} No se pudo obtener ruta relativa para {abs_path} respecto a {ruta_proyecto}: {e}")
            continue

    if not archivos_proyecto_relativos:
        logging.warning(
            f"{logPrefix} No quedaron archivos válidos después de convertir a rutas relativas.")
        return None

    for ruta_rel_archivo in archivos_proyecto_relativos:
        timestamp_ultima_seleccion = registro_archivos.get(ruta_rel_archivo)
        if timestamp_ultima_seleccion is None:
            archivo_seleccionado_rel = ruta_rel_archivo
            logging.info(
                f"{logPrefix} Archivo '{archivo_seleccionado_rel}' nunca antes seleccionado.")
            break
        if timestamp_ultima_seleccion < timestamp_mas_antiguo:
            timestamp_mas_antiguo = timestamp_ultima_seleccion
            archivo_seleccionado_rel = ruta_rel_archivo

    if archivo_seleccionado_rel:
        logging.info(
            f"{logPrefix} Archivo seleccionado: {archivo_seleccionado_rel} (Última vez: {registro_archivos.get(archivo_seleccionado_rel, 'Nunca')})")
        registro_archivos[archivo_seleccionado_rel] = datetime.now(
        ).isoformat()
    else:
        logging.warning(
            f"{logPrefix} No se pudo seleccionar un archivo.")
    return archivo_seleccionado_rel
