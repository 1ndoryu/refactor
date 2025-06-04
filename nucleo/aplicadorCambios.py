# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import json
import codecs
import re
from difflib import unified_diff

# Obtener logger
log = logging.getLogger(__name__)


def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    """
    Validates that a relative path stays within the base path and normalizes it.
    Prevents path traversal. Returns the absolute, normalized path if safe, else None.
    """
    logPrefix = "_validar_y_normalizar_ruta:"
    if not rutaRelativa or not isinstance(rutaRelativa, str):
        log.error(f"{logPrefix} Invalid relative path received (None or not string): {rutaRelativa!r}")
        return None

    rutaBaseAbs = os.path.abspath(rutaBase)
    rutaBaseNorm = os.path.normpath(rutaBaseAbs)

    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    if os.path.isabs(rutaRelativaNorm) or '..' in rutaRelativaNorm.split(os.sep):
        log.error(f"{logPrefix} Invalid or suspicious relative path (absolute or contains '..'): '{rutaRelativa}' -> '{rutaRelativaNorm}'")
        return None

    rutaAbsCandidata = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbsNorm = os.path.normpath(rutaAbsCandidata)

    try:
        rutaBaseReal = os.path.realpath(rutaBaseNorm)
        rutaAbsReal = os.path.realpath(rutaAbsNorm)
        if not os.path.isdir(rutaBaseReal):
             log.error(f"{logPrefix} Real base path is not a directory: '{rutaBaseReal}' (from '{rutaBase}')")
             return None

        if os.path.commonpath([rutaBaseReal, rutaAbsReal]) == rutaBaseReal:
            if asegurar_existencia and not os.path.exists(rutaAbsReal):
                log.warning(f"{logPrefix} Path validated but does not exist (existence required): '{rutaAbsNorm}'")
                return None
            log.debug(f"{logPrefix} Path validated and normalized to: '{rutaAbsNorm}'")
            return rutaAbsNorm
        else:
            log.error(f"{logPrefix} Path Traversal Attempt! Relative path '{rutaRelativa}' exits base '{rutaBaseNorm}'. Result: '{rutaAbsNorm}', Real Result: '{rutaAbsReal}', Real Base: '{rutaBaseReal}'")
            return None
    except Exception as e:
        log.error(f"{logPrefix} Error during path validation/realpath check for '{rutaRelativa}' in '{rutaBase}': {e}", exc_info=True)
        return None


MOJIBAKE_REPLACEMENTS = {
    b'\xc3\xa1'.decode('latin-1', errors='ignore'): "á",  # Ã¡ -> á
    b'\xc3\xa9'.decode('latin-1', errors='ignore'): "é",  # Ã© -> é
    b'\xc3\xad'.decode('latin-1', errors='ignore'): "í",  # Ã­ -> í
    b'\xc3\xb3'.decode('latin-1', errors='ignore'): "ó",  # Ã³ -> ó
    b'\xc3\xba'.decode('latin-1', errors='ignore'): "ú",  # Ãº -> ú
    b'\xc3\xbc'.decode('latin-1', errors='ignore'): "ü",  # Ã¼ -> ü
    b'\xc3\x81'.decode('latin-1', errors='ignore'): "Á",  # Ã -> Á
    b'\xc3\x89'.decode('latin-1', errors='ignore'): "É",  # Ã‰ -> É
    b'\xc3\x8d'.decode('latin-1', errors='ignore'): "Í",  # Ã -> Í
    b'\xc3\x93'.decode('latin-1', errors='ignore'): "Ó",  # Ã“ -> Ó
    b'\xc3\x9a'.decode('latin-1', errors='ignore'): "Ú",  # Ãš -> Ú
    b'\xc3\x9c'.decode('latin-1', errors='ignore'): "Ü",  # Ãœ -> Ü
    b'\xc3\xb1'.decode('latin-1', errors='ignore'): "ñ",  # Ã± -> ñ
    b'\xc3\x91'.decode('latin-1', errors='ignore'): "Ñ",  # Ã‘ -> Ñ
    b'\xc2\xa1'.decode('latin-1', errors='ignore'): "¡",  # Â¡ -> ¡
    b'\xc2\xbf'.decode('latin-1', errors='ignore'): "¿",  # Â¿ -> ¿
    b'\xc2\xaa'.decode('latin-1', errors='ignore'): "ª",  # Âª -> ª
    b'\xc2\xba'.decode('latin-1', errors='ignore'): "º",  # Âº -> º
    b'\xc2\xab'.decode('latin-1', errors='ignore'): "«",  # Â« -> «
    b'\xc2\xbb'.decode('latin-1', errors='ignore'): "»",  # Â» -> »
    b'\xe2\x82\xac'.decode('latin-1', errors='ignore'): "€", # â‚¬ -> €
    b'\xe2\x84\xa2'.decode('latin-1', errors='ignore'): "™", # â„¢ -> ™
    b'\xe2\x80\x99'.decode('latin-1', errors='ignore'): "’", # â€™ -> ’
    b'\xe2\x80\x98'.decode('latin-1', errors='ignore'): "‘", # â€˜ -> ‘
    b'\xe2\x80\x9c'.decode('latin-1', errors='ignore'): "“", # â€œ -> “
    b'\xe2\x80\x9d'.decode('latin-1', errors='ignore'): "”", # â€ -> ”
    b'\xe2\x80\xa6'.decode('latin-1', errors='ignore'): "…", # â€¦ -> …
    b'\xe2\x80\x93'.decode('latin-1', errors='ignore'): "–", # â€“ -> – 
    b'\xe2\x80\x94'.decode('latin-1', errors='ignore'): "—", # â€” -> —
}

def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Applying changes for original action '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase)

    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        targetRel = paramsOriginal.get("archivo") or paramsOriginal.get("directorio")
        if not targetRel:
            return False, f"Missing target parameter ('archivo' or 'directorio') for {accionOriginal}."
        targetAbs = _validar_y_normalizar_ruta(targetRel, rutaBaseNorm, asegurar_existencia=False)
        if targetAbs is None:
            return False, f"Invalid or unsafe path provided for {accionOriginal}: '{targetRel}'"

        if accionOriginal == "eliminar_archivo":
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Targeting {targetRel} (Abs: {targetAbs})")
            if os.path.exists(targetAbs):
                try:
                    if os.path.isfile(targetAbs) or os.path.islink(targetAbs):
                        os.remove(targetAbs)
                        log.info(f"{logPrefix} File/Link '{targetRel}' deleted.")
                    elif os.path.isdir(targetAbs):
                        try:
                            os.rmdir(targetAbs) 
                            log.info(f"{logPrefix} Empty directory '{targetRel}' deleted.")
                        except OSError:
                             err = f"Directory '{targetRel}' is not empty. Cannot delete."
                             log.error(f"{logPrefix} {err}")
                             return False, err
                    else:
                        err = f"Target '{targetRel}' exists but is not a file, link, or directory."
                        log.error(f"{logPrefix} {err}")
                        return False, err
                    return True, None
                except Exception as e:
                    err = f"Error deleting '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    return False, err
            else:
                log.warning(f"{logPrefix} Target '{targetRel}' not found for deletion. Considering successful.")
                return True, None

        elif accionOriginal == "crear_directorio":
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Creating directory {targetRel} (Abs: {targetAbs})")
            exito_creacion = False
            error_creacion = None
            if os.path.exists(targetAbs):
                if os.path.isdir(targetAbs):
                    log.warning(f"{logPrefix} Directory '{targetRel}' already exists.")
                    exito_creacion = True 
                else:
                    err = f"Path '{targetRel}' exists but is not a directory. Cannot create directory."
                    log.error(f"{logPrefix} {err}")
                    error_creacion = err
                    exito_creacion = False
            else:
                try:
                    os.makedirs(targetAbs, exist_ok=True)
                    log.info(f"{logPrefix} Directory '{targetRel}' created.")
                    exito_creacion = True
                except Exception as e:
                    err = f"Error creating directory '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    error_creacion = err
                    exito_creacion = False

            if exito_creacion:
                gitkeep_path = os.path.join(targetAbs, '.gitkeep')
                if not os.path.exists(gitkeep_path): 
                    try:
                        with open(gitkeep_path, 'w', encoding='utf-8') as gk:
                            pass 
                        log.info(f"{logPrefix} Archivo .gitkeep creado en '{targetRel}' para rastreo de Git.")
                    except Exception as e_gk:
                        log.warning(f"{logPrefix} No se pudo crear .gitkeep en '{targetRel}': {e_gk}")
                else:
                    log.debug(f"{logPrefix} Archivo .gitkeep ya existe en '{targetRel}'.")
            
            return exito_creacion, error_creacion 
    
    if not isinstance(archivos_con_contenido, list):
         err = f"Argument 'archivos_con_contenido' is not a list. Type received: {type(archivos_con_contenido)}"
         log.error(f"{logPrefix} {err}")
         return False, err
    
    if not archivos_con_contenido and accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
        log.info(f"{logPrefix} 'archivos_con_contenido' está vacío para la acción '{accionOriginal}'. No se escribirán archivos.")
        return True, None 

    log.info(f"{logPrefix} Processing {len(archivos_con_contenido)} file entry/entries for writing/modification...")
    archivosProcesadosConCambio = 0
    archivosProcesadosSinCambio = 0
    errores = []

    for item_archivo in archivos_con_contenido:
        if not isinstance(item_archivo, dict) or "nombre" not in item_archivo or "contenido" not in item_archivo:
            msg = f"Invalid item in 'archivos_con_contenido' list. Expected dict with 'nombre' and 'contenido'. Got: {item_archivo!r}"
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        rutaRel = item_archivo["nombre"]
        contenido_ia_original = item_archivo["contenido"]

        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Invalid or unsafe path ('{rutaRel}') received. File skipped."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        if not isinstance(contenido_ia_original, str):
             log.warning(f"{logPrefix} Content for '{rutaRel}' is not string (type {type(contenido_ia_original)}). Converting to JSON string.")
             try:
                 contenido_ia_str = json.dumps(contenido_ia_original, indent=2, ensure_ascii=False)
             except Exception as e_conv:
                  log.error(f"{logPrefix} Could not convert non-string content to string for '{rutaRel}': {e_conv}. Skipping file.")
                  errores.append(f"Invalid non-string content for {rutaRel}")
                  continue
        else:
             contenido_ia_str = contenido_ia_original

        dirPadre = os.path.dirname(archivoAbs)
        try:
            if dirPadre and not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creating necessary parent directory: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif dirPadre and not os.path.isdir(dirPadre):
                 raise ValueError(f"Parent path '{dirPadre}' for file '{rutaRel}' exists but is NOT a directory.")
        except Exception as e_dir:
            msg = f"Error creating/validating parent directory '{dirPadre}' for '{rutaRel}': {e_dir}. File skipped."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue
        
        contenido_nuevo_procesado = contenido_ia_str
        log.debug(f"{logPrefix} Content FROM IA for '{rutaRel}' (raw, repr): {repr(contenido_nuevo_procesado[:200])}...")

        if '\\' in contenido_nuevo_procesado:
            log.debug(f"{logPrefix} Aplicando codecs.decode(..., 'unicode_escape') para '{rutaRel}'")
            try:
                contenido_decodificado_escape = codecs.decode(contenido_nuevo_procesado, 'unicode_escape', errors='backslashreplace')
                if contenido_decodificado_escape != contenido_nuevo_procesado:
                    log.info(f"{logPrefix} CORRECCIÓN (unicode_escape): Secuencias de escape decodificadas para '{rutaRel}'.")
                contenido_nuevo_procesado = contenido_decodificado_escape
            except Exception as e_esc_decode:
                 log.warning(f"{logPrefix} Error durante 'unicode_escape' para '{rutaRel}': {e_esc_decode}. Usando contenido previo a este paso.")
        else:
            log.debug(f"{logPrefix} No se encontraron barras invertidas; se omite 'unicode_escape' para '{rutaRel}'.")

        log.debug(f"{logPrefix} Content AFTER unicode_escape para '{rutaRel}' (repr): {repr(contenido_nuevo_procesado[:200])}...")

        contenido_final_ia = contenido_nuevo_procesado
        replacements_made_mojibake = False
        temp_contenido_mojibake = contenido_nuevo_procesado

        for mojibake, correct in MOJIBAKE_REPLACEMENTS.items():
            if isinstance(temp_contenido_mojibake, str): 
                mojibake_str = str(mojibake) if not isinstance(mojibake, str) else mojibake
                new_temp_contenido_mojibake = temp_contenido_mojibake.replace(mojibake_str, correct)
                if new_temp_contenido_mojibake != temp_contenido_mojibake:
                    if not replacements_made_mojibake:
                        log.info(f"{logPrefix} CORRECCIÓN (Mojibake Replace): Se reemplazarán secuencias Mojibake para '{rutaRel}'.")
                    log.debug(f"{logPrefix}   Reemplazado Mojibake: {repr(mojibake_str)} -> {repr(correct)}")
                    replacements_made_mojibake = True
                    temp_contenido_mojibake = new_temp_contenido_mojibake
        
        if replacements_made_mojibake:
            contenido_final_ia = temp_contenido_mojibake
        
        log.debug(f"{logPrefix} FINAL PROCESSED content from IA for '{rutaRel}' (repr): {repr(contenido_final_ia[:200])}...")

        contenido_original_disco = None
        es_archivo_nuevo = not os.path.exists(archivoAbs)

        if not es_archivo_nuevo:
            try:
                with open(archivoAbs, 'r', encoding='utf-8') as f_orig:
                    contenido_original_disco = f_orig.read()
            except Exception as e_read_orig:
                msg = f"Error leyendo archivo original '{rutaRel}' para comparación: {e_read_orig}. Se tratará como creación."
                log.warning(f"{logPrefix} {msg}", exc_info=True)
                es_archivo_nuevo = True

        escribir_archivo = False
        if es_archivo_nuevo:
            log.info(f"{logPrefix} Archivo '{rutaRel}' es NUEVO. Se escribirá.")
            escribir_archivo = True
        elif contenido_original_disco is None: # Si falló la lectura del original pero existía, mejor escribir.
            log.warning(f"{logPrefix} No se pudo leer el contenido original de '{rutaRel}' (existente). Se procederá a escribir el contenido de la IA.")
            escribir_archivo = True
        elif contenido_original_disco == contenido_final_ia:
            log.info(f"{logPrefix} Archivo '{rutaRel}' no ha cambiado. No se sobrescribirá.")
            archivosProcesadosSinCambio += 1
        else:
            log.info(f"{logPrefix} Archivo '{rutaRel}' HA CAMBIADO. Se sobrescribirá.")
            escribir_archivo = True
            if contenido_original_disco is not None: # Solo loguear diff si tenemos original
                diff_output = unified_diff(
                    contenido_original_disco.splitlines(keepends=True),
                    contenido_final_ia.splitlines(keepends=True),
                    fromfile=f"a/{rutaRel}",
                    tofile=f"b/{rutaRel}",
                    lineterm="" 
                )
                log.debug(f"{logPrefix} Diff para '{rutaRel}':\n" + "".join(diff_output))

        if escribir_archivo:
            try:
                with open(archivoAbs, 'w', encoding='utf-8') as f_write:
                    if isinstance(contenido_final_ia, str):
                        f_write.write(contenido_final_ia)
                    else: 
                        f_write.write(repr(contenido_final_ia))
                        log.warning(f"{logPrefix} Contenido para '{rutaRel}' no era string al escribir (después de procesamiento IA), se usó repr().")
                
                log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito exitosamente.")
                archivosProcesadosConCambio += 1
            except Exception as e_process_write:
                 msg = f"Error final escribiendo archivo '{rutaRel}': {e_process_write}"
                 log.error(f"{logPrefix} {msg}", exc_info=True)
                 errores.append(msg)

    if errores:
        error_summary = f"Proceso completado con {len(errores)} error(s): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary
    
    total_procesados_efectivamente = archivosProcesadosConCambio + archivosProcesadosSinCambio
    log.info(f"{logPrefix} Procesamiento finalizado. {archivosProcesadosConCambio} archivos escritos/modificados.")
    log.info(f"{logPrefix} {archivosProcesadosSinCambio} archivos no necesitaron cambios.")
    log.info(f"{logPrefix} Total de entradas de archivo procesadas efectivamente: {total_procesados_efectivamente} de {len(archivos_con_contenido)}.")

    return True, None