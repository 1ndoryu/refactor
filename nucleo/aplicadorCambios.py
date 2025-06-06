# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import json
import codecs
import re
from difflib import unified_diff
from typing import Optional

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

# Informacion importante: esta funcion funciona con unicode escape a diferencia de la futura V2, agregar informacion de diferencias aca
def aplicarCambiosSobrescrituraV1noUse(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    logPrefix = "aplicarCambiosSobrescrituraV1:"
    log.info(f"{logPrefix} Iniciando para acción original '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase)

    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        targetRel = paramsOriginal.get("archivo") or paramsOriginal.get("directorio")
        if not targetRel:
            msg = f"Parámetro objetivo ('archivo' o 'directorio') faltante para {accionOriginal}."
            log.error(f"{logPrefix} {msg}")
            return False, msg
        targetAbs = _validar_y_normalizar_ruta(targetRel, rutaBaseNorm, asegurar_existencia=False)
        if targetAbs is None:
            msg = f"Ruta inválida o insegura proporcionada para {accionOriginal}: '{targetRel}'"
            log.error(f"{logPrefix} {msg}")
            return False, msg

        if accionOriginal == "eliminar_archivo":
            log.info(f"{logPrefix} Ejecutando '{accionOriginal}': Objetivo '{targetRel}' (Abs: {targetAbs})")
            if os.path.exists(targetAbs):
                try:
                    if os.path.isfile(targetAbs) or os.path.islink(targetAbs):
                        os.remove(targetAbs)
                        log.info(f"{logPrefix} Archivo/Enlace '{targetRel}' eliminado.")
                    elif os.path.isdir(targetAbs):
                        try:
                            os.rmdir(targetAbs) 
                            log.info(f"{logPrefix} Directorio vacío '{targetRel}' eliminado.")
                        except OSError:
                             err = f"Directorio '{targetRel}' no está vacío. No se puede eliminar."
                             log.error(f"{logPrefix} {err}")
                             return False, err
                    else:
                        err = f"Objetivo '{targetRel}' existe pero no es archivo, enlace o directorio."
                        log.error(f"{logPrefix} {err}")
                        return False, err
                    return True, None
                except Exception as e:
                    err = f"Error eliminando '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    return False, err
            else:
                log.warning(f"{logPrefix} Objetivo '{targetRel}' no encontrado para eliminación. Se considera exitoso.")
                return True, None

        elif accionOriginal == "crear_directorio":
            log.info(f"{logPrefix} Ejecutando '{accionOriginal}': Creando directorio '{targetRel}' (Abs: {targetAbs})")
            exito_creacion = False
            error_creacion = None
            if os.path.exists(targetAbs):
                if os.path.isdir(targetAbs):
                    log.warning(f"{logPrefix} Directorio '{targetRel}' ya existe.")
                    exito_creacion = True 
                else:
                    err = f"Ruta '{targetRel}' existe pero no es un directorio. No se puede crear directorio."
                    log.error(f"{logPrefix} {err}")
                    error_creacion = err
                    exito_creacion = False
            else:
                try:
                    os.makedirs(targetAbs, exist_ok=True)
                    log.info(f"{logPrefix} Directorio '{targetRel}' creado.")
                    exito_creacion = True
                except Exception as e:
                    err = f"Error creando directorio '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    error_creacion = err
                    exito_creacion = False

            if exito_creacion:
                gitkeep_path = os.path.join(targetAbs, '.gitkeep')
                if not os.path.exists(gitkeep_path): 
                    try:
                        with open(gitkeep_path, 'w', encoding='utf-8') as gk:
                            pass 
                        log.info(f"{logPrefix} Archivo .gitkeep creado en '{targetRel}'.")
                    except Exception as e_gk:
                        log.warning(f"{logPrefix} No se pudo crear .gitkeep en '{targetRel}': {e_gk}")
                else:
                    log.debug(f"{logPrefix} Archivo .gitkeep ya existe en '{targetRel}'.")
            
            return exito_creacion, error_creacion 
    
    if not isinstance(archivos_con_contenido, list):
         err = f"Argumento 'archivos_con_contenido' no es una lista. Tipo recibido: {type(archivos_con_contenido)}"
         log.error(f"{logPrefix} {err}")
         return False, err
    
    if not archivos_con_contenido and accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
        log.info(f"{logPrefix} 'archivos_con_contenido' está vacío para la acción '{accionOriginal}'. No se escribirán archivos.")
        return True, None 

    log.info(f"{logPrefix} Procesando {len(archivos_con_contenido)} entradas de archivo para escritura/modificación...")
    archivosProcesadosConCambio = 0
    archivosProcesadosSinCambio = 0
    errores = []

    for item_archivo in archivos_con_contenido:
        if not isinstance(item_archivo, dict) or "nombre" not in item_archivo or "contenido" not in item_archivo:
            msg = f"Item inválido en 'archivos_con_contenido'. Esperado dict con 'nombre' y 'contenido'. Recibido: {item_archivo!r}"
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        rutaRel = item_archivo["nombre"]
        contenido_ia_original = item_archivo["contenido"]

        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Ruta inválida o insegura ('{rutaRel}') recibida. Archivo omitido."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        if not isinstance(contenido_ia_original, str):
             log.warning(f"{logPrefix} Contenido para '{rutaRel}' no es string (tipo {type(contenido_ia_original)}). Convirtiendo a JSON string.")
             try:
                 contenido_ia_str = json.dumps(contenido_ia_original, indent=2, ensure_ascii=False)
             except Exception as e_conv:
                  log.error(f"{logPrefix} No se pudo convertir contenido no-string a string para '{rutaRel}': {e_conv}. Omitiendo archivo.")
                  errores.append(f"Contenido no-string inválido para {rutaRel}")
                  continue
        else:
             contenido_ia_str = contenido_ia_original

        dirPadre = os.path.dirname(archivoAbs)
        try:
            if dirPadre and not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif dirPadre and not os.path.isdir(dirPadre):
                 raise ValueError(f"Ruta padre '{dirPadre}' para archivo '{rutaRel}' existe pero NO es un directorio.")
        except Exception as e_dir:
            msg = f"Error creando/validando directorio padre '{dirPadre}' para '{rutaRel}': {e_dir}. Archivo omitido."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue
        
        contenido_nuevo_procesado = contenido_ia_str
        log.debug(f"{logPrefix} Contenido IA (raw) para '{rutaRel}': {repr(contenido_nuevo_procesado[:200])}...")

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

        log.debug(f"{logPrefix} Contenido post unicode_escape para '{rutaRel}': {repr(contenido_nuevo_procesado[:200])}...")

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
                    log.debug(f"{logPrefix} Reemplazado Mojibake: {repr(mojibake_str)} -> {repr(correct)} en '{rutaRel}'")
                    replacements_made_mojibake = True
                    temp_contenido_mojibake = new_temp_contenido_mojibake
        
        if replacements_made_mojibake:
            contenido_final_ia = temp_contenido_mojibake
        
        log.debug(f"{logPrefix} Contenido final procesado IA para '{rutaRel}': {repr(contenido_final_ia[:200])}...")

        contenido_original_disco = None
        es_archivo_nuevo = not os.path.exists(archivoAbs)

        if not es_archivo_nuevo:
            try:
                with open(archivoAbs, 'r', encoding='utf-8') as f_orig:
                    contenido_original_disco = f_orig.read()
            except Exception as e_read_orig:
                msg = f"Error leyendo archivo original '{rutaRel}' para comparación: {e_read_orig}. Se tratará como nuevo."
                log.warning(f"{logPrefix} {msg}", exc_info=True)
                es_archivo_nuevo = True

        escribir_archivo = False
        if es_archivo_nuevo:
            log.info(f"{logPrefix} Archivo '{rutaRel}' es NUEVO. Se escribirá.")
            escribir_archivo = True
        elif contenido_original_disco is None: 
            log.warning(f"{logPrefix} No se pudo leer contenido original de '{rutaRel}' (existente). Se escribirá contenido IA.")
            escribir_archivo = True
        elif contenido_original_disco == contenido_final_ia:
            log.info(f"{logPrefix} Archivo '{rutaRel}' sin cambios. No se sobrescribirá.")
            archivosProcesadosSinCambio += 1
        else:
            log.info(f"{logPrefix} Archivo '{rutaRel}' CAMBIADO. Se sobrescribirá.")
            escribir_archivo = True
            if contenido_original_disco is not None: 
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
                        log.warning(f"{logPrefix} Contenido para '{rutaRel}' no era string al escribir (post-IA), se usó repr().")
                
                log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito exitosamente.")
                archivosProcesadosConCambio += 1
            except Exception as e_process_write:
                 msg = f"Error final escribiendo archivo '{rutaRel}': {e_process_write}"
                 log.error(f"{logPrefix} {msg}", exc_info=True)
                 errores.append(msg)

    if errores:
        error_summary = f"Proceso completado con {len(errores)} error(es): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary
    
    total_procesados_efectivamente = archivosProcesadosConCambio + archivosProcesadosSinCambio
    log.info(f"{logPrefix} Procesamiento finalizado. {archivosProcesadosConCambio} archivos escritos/modificados.")
    log.info(f"{logPrefix} {archivosProcesadosSinCambio} archivos no necesitaron cambios.")
    log.info(f"{logPrefix} Total de entradas de archivo procesadas efectivamente: {total_procesados_efectivamente} de {len(archivos_con_contenido) if archivos_con_contenido else 0}.")

    return True, None

###Este parece mejor
def aplicarCambiosSobrescrituraV2(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    logPrefix = "aplicarCambiosSobrescrituraV2:"
    log.info(f"{logPrefix} Iniciando para acción original '{accionOriginal}' (V2 - no unicode_escape)...")
    rutaBaseNorm = os.path.normpath(rutaBase)

    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        targetRel = paramsOriginal.get("archivo") or paramsOriginal.get("directorio")
        if not targetRel:
            msg = f"Parámetro objetivo ('archivo' o 'directorio') faltante para {accionOriginal}."
            log.error(f"{logPrefix} {msg}")
            return False, msg
        targetAbs = _validar_y_normalizar_ruta(targetRel, rutaBaseNorm, asegurar_existencia=False)
        if targetAbs is None:
            msg = f"Ruta inválida o insegura proporcionada para {accionOriginal}: '{targetRel}'"
            log.error(f"{logPrefix} {msg}")
            return False, msg

        if accionOriginal == "eliminar_archivo":
            log.info(f"{logPrefix} Ejecutando '{accionOriginal}': Objetivo {targetRel} (Abs: {targetAbs})")
            if os.path.exists(targetAbs):
                try:
                    if os.path.isfile(targetAbs) or os.path.islink(targetAbs):
                        os.remove(targetAbs)
                        log.info(f"{logPrefix} Archivo/Enlace '{targetRel}' eliminado.")
                    elif os.path.isdir(targetAbs):
                        try:
                            os.rmdir(targetAbs)
                            log.info(f"{logPrefix} Directorio vacío '{targetRel}' eliminado.")
                        except OSError:
                             err = f"Directorio '{targetRel}' no está vacío. No se puede eliminar."
                             log.error(f"{logPrefix} {err}")
                             return False, err
                    else:
                        err = f"Objetivo '{targetRel}' existe pero no es archivo, enlace o directorio."
                        log.error(f"{logPrefix} {err}")
                        return False, err
                    return True, None
                except Exception as e:
                    err = f"Error eliminando '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    return False, err
            else:
                log.warning(f"{logPrefix} Objetivo '{targetRel}' no encontrado para eliminación. Se considera exitoso.")
                return True, None

        elif accionOriginal == "crear_directorio":
            log.info(f"{logPrefix} Ejecutando '{accionOriginal}': Creando directorio {targetRel} (Abs: {targetAbs})")
            exito_creacion = False
            error_creacion = None
            if os.path.exists(targetAbs):
                if os.path.isdir(targetAbs):
                    log.warning(f"{logPrefix} Directorio '{targetRel}' ya existe.")
                    exito_creacion = True
                else:
                    err = f"Ruta '{targetRel}' existe pero no es un directorio. No se puede crear directorio."
                    log.error(f"{logPrefix} {err}")
                    error_creacion = err
                    exito_creacion = False
            else:
                try:
                    os.makedirs(targetAbs, exist_ok=True)
                    log.info(f"{logPrefix} Directorio '{targetRel}' creado.")
                    exito_creacion = True
                except Exception as e:
                    err = f"Error creando directorio '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    error_creacion = err
                    exito_creacion = False

            if exito_creacion:
                gitkeep_path = os.path.join(targetAbs, '.gitkeep')
                if not os.path.exists(gitkeep_path):
                    try:
                        with open(gitkeep_path, 'w', encoding='utf-8') as gk:
                            pass
                        log.info(f"{logPrefix} Archivo .gitkeep creado en '{targetRel}'.")
                    except Exception as e_gk:
                        log.warning(f"{logPrefix} No se pudo crear .gitkeep en '{targetRel}': {e_gk}")
                else:
                    log.debug(f"{logPrefix} Archivo .gitkeep ya existe en '{targetRel}'.")

            return exito_creacion, error_creacion

    if not isinstance(archivos_con_contenido, list):
         err = f"Argumento 'archivos_con_contenido' no es una lista. Tipo recibido: {type(archivos_con_contenido)}"
         log.error(f"{logPrefix} {err}")
         return False, err

    if not archivos_con_contenido and accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
        log.info(f"{logPrefix} 'archivos_con_contenido' está vacío para la acción '{accionOriginal}'. No se escribirán archivos.")
        return True, None

    log.info(f"{logPrefix} Procesando {len(archivos_con_contenido)} entradas de archivo para escritura/modificación...")
    archivosProcesadosConCambio = 0
    archivosProcesadosSinCambio = 0
    errores = []

    for item_archivo in archivos_con_contenido:
        if not isinstance(item_archivo, dict) or "nombre" not in item_archivo or "contenido" not in item_archivo:
            msg = f"Item inválido en 'archivos_con_contenido'. Esperado dict con 'nombre' y 'contenido'. Recibido: {item_archivo!r}"
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        rutaRel = item_archivo["nombre"]
        contenido_ia_original = item_archivo["contenido"]

        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Ruta inválida o insegura ('{rutaRel}') recibida. Archivo omitido."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        if not isinstance(contenido_ia_original, str):
             log.warning(f"{logPrefix} Contenido para '{rutaRel}' no es string (tipo {type(contenido_ia_original)}). Convirtiendo a JSON string.")
             try:
                 contenido_ia_str = json.dumps(contenido_ia_original, indent=2, ensure_ascii=False)
             except Exception as e_conv:
                  log.error(f"{logPrefix} No se pudo convertir contenido no-string a string para '{rutaRel}': {e_conv}. Omitiendo archivo.")
                  errores.append(f"Contenido no-string inválido para {rutaRel}")
                  continue
        else:
             contenido_ia_str = contenido_ia_original

        dirPadre = os.path.dirname(archivoAbs)
        try:
            if dirPadre and not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif dirPadre and not os.path.isdir(dirPadre):
                 raise ValueError(f"Ruta padre '{dirPadre}' para archivo '{rutaRel}' existe pero NO es un directorio.")
        except Exception as e_dir:
            msg = f"Error creando/validando directorio padre '{dirPadre}' para '{rutaRel}': {e_dir}. Archivo omitido."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue

        contenido_nuevo_procesado = contenido_ia_str
        log.debug(f"{logPrefix} Contenido IA (raw) para '{rutaRel}': {repr(contenido_nuevo_procesado[:200])}...")

        # Bloque de codecs.decode(..., 'unicode_escape') ELIMINADO para V2

        log.debug(f"{logPrefix} Contenido IA (V2 - pre-mojibake) para '{rutaRel}': {repr(contenido_nuevo_procesado[:200])}...")

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
                    log.debug(f"{logPrefix} Reemplazado Mojibake: {repr(mojibake_str)} -> {repr(correct)} en '{rutaRel}'")
                    replacements_made_mojibake = True
                    temp_contenido_mojibake = new_temp_contenido_mojibake

        if replacements_made_mojibake:
            contenido_final_ia = temp_contenido_mojibake

        log.debug(f"{logPrefix} Contenido final procesado IA (V2) para '{rutaRel}': {repr(contenido_final_ia[:200])}...")

        contenido_original_disco = None
        es_archivo_nuevo = not os.path.exists(archivoAbs)

        if not es_archivo_nuevo:
            try:
                with open(archivoAbs, 'r', encoding='utf-8') as f_orig:
                    contenido_original_disco = f_orig.read()
            except Exception as e_read_orig:
                msg = f"Error leyendo archivo original '{rutaRel}' para comparación: {e_read_orig}. Se tratará como nuevo."
                log.warning(f"{logPrefix} {msg}", exc_info=True)
                es_archivo_nuevo = True

        escribir_archivo = False
        if es_archivo_nuevo:
            log.info(f"{logPrefix} Archivo '{rutaRel}' es NUEVO. Se escribirá.")
            escribir_archivo = True
        elif contenido_original_disco is None:
            log.warning(f"{logPrefix} No se pudo leer contenido original de '{rutaRel}' (existente). Se escribirá contenido IA.")
            escribir_archivo = True
        elif contenido_original_disco == contenido_final_ia:
            log.info(f"{logPrefix} Archivo '{rutaRel}' sin cambios. No se sobrescribirá.")
            archivosProcesadosSinCambio += 1
        else:
            log.info(f"{logPrefix} Archivo '{rutaRel}' CAMBIADO. Se sobrescribirá.")
            escribir_archivo = True
            if contenido_original_disco is not None:
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
                        log.warning(f"{logPrefix} Contenido para '{rutaRel}' no era string al escribir (post-IA), se usó repr().")

                log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito exitosamente.")
                archivosProcesadosConCambio += 1
            except Exception as e_process_write:
                 msg = f"Error final escribiendo archivo '{rutaRel}': {e_process_write}"
                 log.error(f"{logPrefix} {msg}", exc_info=True)
                 errores.append(msg)

    if errores:
        error_summary = f"Proceso completado con {len(errores)} error(es): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary

    total_procesados_efectivamente = archivosProcesadosConCambio + archivosProcesadosSinCambio
    log.info(f"{logPrefix} Procesamiento finalizado. {archivosProcesadosConCambio} archivos escritos/modificados.")
    log.info(f"{logPrefix} {archivosProcesadosSinCambio} archivos no necesitaron cambios.")
    log.info(f"{logPrefix} Total de entradas de archivo procesadas efectivamente: {total_procesados_efectivamente} de {len(archivos_con_contenido) if archivos_con_contenido else 0}.")

    return True, None

def aplicarCambiosGranulares(respuesta_ia_modificaciones: dict, ruta_base_repo: str) -> tuple[bool, Optional[str]]:
    logPrefix = "aplicarCambiosGranulares:"
    log.info(f"{logPrefix} Iniciando aplicación de cambios granulares...")

    if not isinstance(respuesta_ia_modificaciones, dict) or "modificaciones" not in respuesta_ia_modificaciones:
        msg = "Formato de respuesta IA inválido: falta la clave 'modificaciones' o no es un diccionario."
        log.error(f"{logPrefix} {msg}")
        return False, msg

    lista_operaciones = respuesta_ia_modificaciones.get("modificaciones", [])
    if not isinstance(lista_operaciones, list):
        msg = "La clave 'modificaciones' no contiene una lista de operaciones."
        log.error(f"{logPrefix} {msg}")
        return False, msg

    if not lista_operaciones:
        # Esto puede ocurrir si la IA solo devuelve una "advertencia_ejecucion" sin modificaciones.
        advertencia = respuesta_ia_modificaciones.get("advertencia_ejecucion")
        if advertencia:
            log.info(f"{logPrefix} No hay operaciones de modificación. Advertencia de la IA: {advertencia}")
        else:
            log.info(f"{logPrefix} No hay operaciones de modificación para aplicar.")
        return True, None # Éxito, no se hizo nada o solo hubo advertencia.

    errores_aplicacion = []

    for i, operacion in enumerate(lista_operaciones):
        log.info(f"{logPrefix} Procesando operación #{i+1}: {operacion.get('tipo_operacion')} en '{operacion.get('ruta_archivo')}'")

        if not isinstance(operacion, dict):
            msg = f"Operación #{i+1} no es un diccionario válido."
            log.error(f"{logPrefix} {msg}")
            errores_aplicacion.append(msg)
            continue 

        tipo_operacion = operacion.get("tipo_operacion")
        ruta_archivo_rel = operacion.get("ruta_archivo")
        # Para ELIMINAR_BLOQUE, nuevo_contenido podría no estar o ser None/vacío.
        # Si no está, get() devuelve None. Si es None, split('\n') fallará.
        # Por eso, default a "" si es None.
        nuevo_contenido_str = operacion.get("nuevo_contenido")
        if nuevo_contenido_str is None:
            nuevo_contenido_str = ""


        if not tipo_operacion or not ruta_archivo_rel:
            msg = f"Operación #{i+1} inválida: falta 'tipo_operacion' o 'ruta_archivo'."
            log.error(f"{logPrefix} {msg}")
            errores_aplicacion.append(msg)
            continue

        archivo_abs = _validar_y_normalizar_ruta(ruta_archivo_rel, ruta_base_repo, asegurar_existencia=False)
        if archivo_abs is None:
            msg = f"Operación #{i+1}: Ruta de archivo inválida o insegura '{ruta_archivo_rel}'. Se omite."
            log.error(f"{logPrefix} {msg}")
            errores_aplicacion.append(msg)
            continue
        
        es_creacion_archivo_con_reemplazar = (
            tipo_operacion == "REEMPLAZAR_BLOQUE" and
            operacion.get("linea_inicio") == 1 and
            (operacion.get("linea_fin") == 1 or operacion.get("linea_fin") == 0)
        )

        lineas_archivo_original = []
        archivo_existia = os.path.exists(archivo_abs)

        if archivo_existia:
            try:
                with open(archivo_abs, 'r', encoding='utf-8') as f:
                    lineas_archivo_original = f.readlines() 
            except Exception as e:
                msg = f"Operación #{i+1}: Error leyendo archivo existente '{ruta_archivo_rel}': {e}. Se omite."
                log.error(f"{logPrefix} {msg}", exc_info=True)
                errores_aplicacion.append(msg)
                continue
        elif not es_creacion_archivo_con_reemplazar and tipo_operacion != "REEMPLAZAR_BLOQUE": # REEMPLAZAR_BLOQUE puede crear
             # Si no es creación y el archivo no existe, es un error para AGREGAR o ELIMINAR.
             # Para REEMPLAZAR, solo es error si NO es el caso de creación.
            msg = f"Operación #{i+1}: Archivo '{ruta_archivo_rel}' no encontrado para operación '{tipo_operacion}'. Se omite."
            log.error(f"{logPrefix} {msg}")
            errores_aplicacion.append(msg)
            continue
        
        if not nuevo_contenido_str: 
            lineas_nuevo_contenido = []
        else:
            # Si nuevo_contenido_str termina con \n, split('\n') producirá un elemento vacío al final.
            # Al añadir '\n' a cada elemento, ese último elemento vacío se convertirá en '\n'.
            # Esto preserva correctamente una línea vacía final si la IA la generó.
            lineas_nuevo_contenido = [line + '\n' for line in nuevo_contenido_str.split('\n')]
            # Ejemplo: "foo\nbar\n".split('\n') -> ['foo', 'bar', '']
            # -> ['foo\n', 'bar\n', '\n'] que es correcto.
            # Ejemplo: "foo\nbar".split('\n') -> ['foo', 'bar']
            # -> ['foo\n', 'bar\n'] que es correcto.
            # Caso especial: si nuevo_contenido_str es solo "\n", split da ['', '']. Luego ['\n', '\n']. Esto es un bug.
            # Si nuevo_contenido_str es "\n", debería ser solo una línea vacía.
            if nuevo_contenido_str == "\n":
                lineas_nuevo_contenido = ["\n"]
            # Caso especial: si nuevo_contenido_str es "" (ya cubierto arriba)
            # Caso especial: si nuevo_contenido_str no tiene \n, split da [contenido]. Luego [contenido\n]. Ok.

        lineas_modificadas = list(lineas_archivo_original)

        if tipo_operacion == "REEMPLAZAR_BLOQUE":
            linea_inicio = operacion.get("linea_inicio")
            linea_fin = operacion.get("linea_fin")
            
            # Validar linea_inicio y linea_fin
            valid_indices = isinstance(linea_inicio, int) and isinstance(linea_fin, int) and linea_inicio >= 1
            if not valid_indices or (linea_fin < linea_inicio and not (linea_inicio == 1 and linea_fin == 0)): # linea_fin puede ser 0 solo si linea_inicio es 1 (creación)
                 # Si linea_inicio es 1 y linea_fin es 0, es un caso especial para creación, trataremos linea_fin como 0 para el slice
                if not (es_creacion_archivo_con_reemplazar and linea_inicio == 1 and linea_fin == 0):
                    msg = f"Operación #{i+1} (REEMPLAZAR_BLOQUE): 'linea_inicio' ({linea_inicio}) o 'linea_fin' ({linea_fin}) inválidas."
                    log.error(f"{logPrefix} {msg}")
                    errores_aplicacion.append(msg)
                    continue

            idx_inicio_slice = linea_inicio - 1
            idx_fin_slice = linea_fin if linea_fin != 0 else 0 # linea_fin 0 se trata como 0 para slice

            if idx_inicio_slice < 0: # Debería ser prevenido por linea_inicio >= 1
                idx_inicio_slice = 0

            if es_creacion_archivo_con_reemplazar or not archivo_existia :
                lineas_modificadas = lineas_nuevo_contenido
                log.info(f"{logPrefix} REEMPLAZAR_BLOQUE (creación/sobrescritura total) en '{ruta_archivo_rel}'.")
            elif idx_inicio_slice > len(lineas_modificadas) or idx_fin_slice > len(lineas_modificadas) or idx_inicio_slice > idx_fin_slice:
                msg = (f"Operación #{i+1} (REEMPLAZAR_BLOQUE): Rango de líneas [{linea_inicio}-{linea_fin}] "
                       f"(slice [{idx_inicio_slice}-{idx_fin_slice}]) fuera de los límites del archivo '{ruta_archivo_rel}' "
                       f"(total líneas: {len(lineas_modificadas)}).")
                log.error(f"{logPrefix} {msg}")
                errores_aplicacion.append(msg)
                continue
            else:
                lineas_modificadas = lineas_modificadas[:idx_inicio_slice] + \
                                     lineas_nuevo_contenido + \
                                     lineas_modificadas[idx_fin_slice:]
                log.info(f"{logPrefix} REEMPLAZAR_BLOQUE en '{ruta_archivo_rel}' líneas {linea_inicio}-{linea_fin}.")

        elif tipo_operacion == "AGREGAR_BLOQUE":
            insertar_despues_de_linea = operacion.get("insertar_despues_de_linea")
            if not isinstance(insertar_despues_de_linea, int) or insertar_despues_de_linea < 0:
                msg = f"Operación #{i+1} (AGREGAR_BLOQUE): 'insertar_despues_de_linea' inválida: {insertar_despues_de_linea}."
                log.error(f"{logPrefix} {msg}")
                errores_aplicacion.append(msg)
                continue

            idx_insercion = insertar_despues_de_linea 
            
            if idx_insercion > len(lineas_modificadas):
                msg = (f"Operación #{i+1} (AGREGAR_BLOQUE): 'insertar_despues_de_linea' ({insertar_despues_de_linea}) "
                       f"fuera de los límites del archivo '{ruta_archivo_rel}' (total líneas: {len(lineas_modificadas)}). "
                       f"Se agregará al final.")
                log.warning(f"{logPrefix} {msg}")
                idx_insercion = len(lineas_modificadas) 
            
            lineas_modificadas = lineas_modificadas[:idx_insercion] + \
                                 lineas_nuevo_contenido + \
                                 lineas_modificadas[idx_insercion:]
            log.info(f"{logPrefix} AGREGAR_BLOQUE en '{ruta_archivo_rel}' después de línea {insertar_despues_de_linea} (índice {idx_insercion}).")

        elif tipo_operacion == "ELIMINAR_BLOQUE":
            linea_inicio = operacion.get("linea_inicio")
            linea_fin = operacion.get("linea_fin")
            if not isinstance(linea_inicio, int) or not isinstance(linea_fin, int) or linea_inicio <= 0 or linea_fin < linea_inicio:
                msg = f"Operación #{i+1} (ELIMINAR_BLOQUE): 'linea_inicio' o 'linea_fin' inválidas: {linea_inicio}, {linea_fin}."
                log.error(f"{logPrefix} {msg}")
                errores_aplicacion.append(msg)
                continue

            idx_inicio_slice = linea_inicio - 1
            idx_fin_slice = linea_fin

            if idx_inicio_slice >= len(lineas_modificadas) or idx_fin_slice > len(lineas_modificadas) or idx_inicio_slice > idx_fin_slice :
                msg = (f"Operación #{i+1} (ELIMINAR_BLOQUE): Rango de líneas [{linea_inicio}-{linea_fin}] "
                       f"(slice [{idx_inicio_slice}-{idx_fin_slice}]) fuera de los límites del archivo '{ruta_archivo_rel}' "
                       f"(total líneas: {len(lineas_modificadas)}).")
                log.error(f"{logPrefix} {msg}")
                errores_aplicacion.append(msg)
                continue
            
            lineas_modificadas = lineas_modificadas[:idx_inicio_slice] + \
                                 lineas_modificadas[idx_fin_slice:]
            log.info(f"{logPrefix} ELIMINAR_BLOQUE en '{ruta_archivo_rel}' líneas {linea_inicio}-{linea_fin}.")
        
        else:
            msg = f"Operación #{i+1}: Tipo de operación desconocido o no soportado: '{tipo_operacion}'."
            log.error(f"{logPrefix} {msg}")
            errores_aplicacion.append(msg)
            continue

        try:
            dir_padre = os.path.dirname(archivo_abs)
            if dir_padre: 
                os.makedirs(dir_padre, exist_ok=True)
                
            with open(archivo_abs, 'w', encoding='utf-8') as f_write:
                f_write.writelines(lineas_modificadas)
            log.info(f"{logPrefix} Archivo '{ruta_archivo_rel}' (Abs: '{archivo_abs}') modificado y guardado exitosamente.")
        except Exception as e:
            msg = f"Operación #{i+1}: Error escribiendo archivo modificado '{ruta_archivo_rel}': {e}."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores_aplicacion.append(msg)

    if errores_aplicacion:
        error_summary = f"Proceso de aplicación granular completado con {len(errores_aplicacion)} error(es): {'; '.join(errores_aplicacion)}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary
    
    log.info(f"{logPrefix} Todas las {len(lista_operaciones)} operaciones granulares aplicadas exitosamente (o no se requirieron cambios).")
    return True, None