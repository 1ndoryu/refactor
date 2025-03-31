# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import json # Necesario para el posible log de contenido en error

# Obtener logger
log = logging.getLogger(__name__)

# Helper de rutas (sin cambios necesarios aquí, asumiendo que funciona)
def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    logPrefix = "_validar_y_normalizar_ruta:"
    # Añadir un check inicial para None o no string
    if not rutaRelativa or not isinstance(rutaRelativa, str):
        log.error(f"{logPrefix} Se recibió una ruta relativa inválida (None o no string): {rutaRelativa!r}")
        return None
    # Resto de la función como estaba...
    log.debug(f"{logPrefix} Validando rutaRelativa='{rutaRelativa}', rutaBase='{rutaBase}', asegurar_existencia={asegurar_existencia}")
    if '..' in rutaRelativa.split(os.sep):
        log.error(f"{logPrefix} Ruta relativa inválida o sospechosa (contiene '..'): '{rutaRelativa}'")
        return None
    rutaBaseNorm = os.path.normpath(os.path.abspath(rutaBase))
    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    if os.path.isabs(rutaRelativaNorm):
         log.error(f"{logPrefix} Ruta relativa '{rutaRelativa}' parece ser absoluta tras normalizar: '{rutaRelativaNorm}'. Rechazada.")
         return None
    rutaAbs = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbs = os.path.normpath(rutaAbs)

    # Comprobación de seguridad estricta
    # Asegurarse que la base termine con separador para evitar falsos positivos (ej /base vs /base_otro)
    base_con_sep = rutaBaseNorm if rutaBaseNorm.endswith(os.sep) else rutaBaseNorm + os.sep
    if not os.path.abspath(rutaAbs).startswith(os.path.abspath(base_con_sep)) and \
       os.path.abspath(rutaAbs) != os.path.abspath(rutaBaseNorm):
        log.error(f"{logPrefix} Ruta calculada '{os.path.abspath(rutaAbs)}' intenta salir de la base '{os.path.abspath(rutaBaseNorm)}' (originada de '{rutaRelativa}')")
        return None

    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.warning(f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (de '{rutaRelativa}')")
        # Cambiado a False, si se pide asegurar existencia y no existe, es un fallo en ese contexto
        return None # O podría ser True dependiendo de la lógica que llama

    log.debug(f"{logPrefix} Ruta validada y normalizada a: '{rutaAbs}'")
    return rutaAbs


# --- FUNCIÓN PRINCIPAL REVISADA ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    """
    Aplica los cambios generados por Gemini.
    - Sobrescribe archivos existentes o crea nuevos con el contenido proporcionado.
    - Maneja acciones como eliminar_archivo y crear_directorio.
    - Intenta corregir Mojibake común (UTF-8 mal leído como Latin-1).
    - Escribe archivos en UTF-8.
    - NO usa `codecs.decode('unicode_escape')`. Confía en `json.loads` para los escapes JSON.

    Args:
        archivos_con_contenido (dict): Diccionario {ruta_relativa: contenido_string}.
        rutaBase (str): Ruta base absoluta del repositorio clonado.
        accionOriginal (str): La acción decidida por Gemini (ej: 'modificar_codigo_en_archivo').
        paramsOriginal (dict): Los parámetros asociados a la acción original.

    Returns:
        tuple[bool, str | None]: (True, None) en éxito, (False, mensaje_error) en fallo.
    """
    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Aplicando cambios para acción original '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase)

    # --- Manejar acciones que NO implican escribir contenido ---
    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        if accionOriginal == "eliminar_archivo":
            archivoRel = paramsOriginal.get("archivo")
            if not archivoRel: return False, "Falta 'archivo' en parámetros para eliminar_archivo."
            archivoAbs = _validar_y_normalizar_ruta(archivoRel, rutaBaseNorm, asegurar_existencia=False)
            # _validar_y_normalizar_ruta ahora devuelve None si falla la validación o asegurar_existencia
            if archivoAbs is None: return False, f"Ruta inválida o no encontrada (si se requirió) para eliminar: '{archivoRel}'"

            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Eliminando {archivoRel}")
            if os.path.exists(archivoAbs):
                if os.path.isfile(archivoAbs):
                    try: os.remove(archivoAbs); log.info(f"{logPrefix} Archivo '{archivoRel}' eliminado."); return True, None
                    except Exception as e: err = f"Error al eliminar archivo '{archivoRel}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
                else: err = f"Ruta a eliminar '{archivoRel}' existe pero NO es un archivo."; log.error(f"{logPrefix} {err}"); return False, err
            else: log.warning(f"{logPrefix} Archivo a eliminar '{archivoRel}' no encontrado. Se considera éxito (ya no existe)."); return True, None # No es un error si no existe

        elif accionOriginal == "crear_directorio":
            dirRel = paramsOriginal.get("directorio")
            if not dirRel: return False, "Falta 'directorio' en parámetros para crear_directorio."
            dirAbs = _validar_y_normalizar_ruta(dirRel, rutaBaseNorm, asegurar_existencia=False)
            if dirAbs is None: return False, f"Ruta inválida para crear directorio: '{dirRel}'"

            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Creando directorio {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs): log.warning(f"{logPrefix} Directorio '{dirRel}' ya existe."); return True, None
                else: err = f"Ya existe un ARCHIVO en la ruta del directorio a crear: '{dirRel}'"; log.error(f"{logPrefix} {err}"); return False, err
            else:
                try: os.makedirs(dirAbs, exist_ok=True); log.info(f"{logPrefix} Directorio '{dirRel}' creado."); return True, None
                except Exception as e: err = f"Error al crear directorio '{dirRel}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
        # Retornar aquí para estas acciones (nunca debería llegar aquí, pero por si acaso)
        return True, None

    # --- Validaciones para acciones que SÍ implican escribir contenido ---
    if not isinstance(archivos_con_contenido, dict):
         err = "Argumento 'archivos_con_contenido' no es un diccionario."
         log.error(f"{logPrefix} {err}")
         return False, err

    # Permitir dict vacío solo si la acción original era una de las de arriba (que ya retornaron)
    # Si llegamos aquí, se esperaba contenido.
    if not archivos_con_contenido:
         err = f"Se esperaba contenido en 'archivos_con_contenido' para la acción '{accionOriginal}', pero está vacío. Error probable en Paso 2."
         log.error(f"{logPrefix} {err}")
         return False, err

    log.info(f"{logPrefix} Sobrescribiendo/Creando {len(archivos_con_contenido)} archivo(s)...")
    archivosProcesados = []
    errores = []

    # --- Bucle principal para escribir archivos ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Ruta inválida o insegura ('{rutaRel}') recibida de Gemini (Paso 2). Archivo omitido."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue # Saltar al siguiente archivo

        if not isinstance(contenido_original_json, str):
             log.warning(f"{logPrefix} Contenido para '{rutaRel}' no es string (tipo {type(contenido_original_json)}). Convirtiendo a string, pero podría indicar un problema previo.")
             # Convertir a string, intentando con json.dumps si es dict/list para mejor representación
             try:
                 if isinstance(contenido_original_json, (dict, list)):
                     contenido_str = json.dumps(contenido_original_json, indent=2, ensure_ascii=False)
                 else:
                     contenido_str = str(contenido_original_json)
             except Exception as e_conv:
                  log.error(f"{logPrefix} No se pudo convertir el contenido no-string a string para '{rutaRel}': {e_conv}. Omitiendo archivo.")
                  errores.append(f"Contenido no string inválido para {rutaRel}")
                  continue
        else:
             contenido_str = contenido_original_json # Ya era string

        log.debug(f"{logPrefix} Procesando archivo: {rutaRel} (Abs: {archivoAbs})")
        dirPadre = os.path.dirname(archivoAbs)
        try:
            if not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif not os.path.isdir(dirPadre):
                 raise ValueError(f"La ruta padre '{dirPadre}' para el archivo '{rutaRel}' existe pero NO es un directorio.")
        except Exception as e_dir:
            msg = f"Error creando/validando directorio padre '{dirPadre}' para '{rutaRel}': {e_dir}. Archivo omitido."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue # Saltar al siguiente archivo

        # --- Inicio Bloque de Corrección Mojibake y Escritura ---
        contenido_a_escribir = contenido_str # Empezar con el string validado
        try:
            # --- PASO 1: Intentar corregir Mojibake (UTF-8 mal leído como Latin-1) ---
            contenido_corregido_mojibake = contenido_a_escribir # Default si no se corrige
            try:
                # Intenta revertir la decodificación incorrecta común
                bytes_probables = contenido_a_escribir.encode('latin-1')
                cadena_reconstruida_utf8 = bytes_probables.decode('utf-8')

                # Aplicar solo si cambió y parece una mejora (heurística)
                if cadena_reconstruida_utf8 != contenido_a_escribir:
                    # Heurística simple: ¿Había caracteres sospechosos y ahora hay menos o normales?
                    # Cuenta caracteres comunes de Mojibake vs caracteres acentuados UTF-8
                    original_suspicious_chars = sum(1 for char in contenido_a_escribir if ord(char) > 127 and char not in 'áéíóúüñÁÉÍÓÚÜÑ¿¡')
                    corrected_normal_chars = sum(1 for char in cadena_reconstruida_utf8 if char in 'áéíóúüñÁÉÍÓÚÜÑ¿¡')

                    # Aplicar si había sospechosos y ahora hay normales, o si simplemente cambió (caso menos seguro)
                    if original_suspicious_chars > 0 and corrected_normal_chars >= 0: # Si había basura y ahora parece más normal
                         log.info(f"{logPrefix} CORRECCIÓN (Mojibake UTF-8->Latin1->UTF-8): Aplicada para '{rutaRel}'.")
                         contenido_corregido_mojibake = cadena_reconstruida_utf8
                    elif original_suspicious_chars == 0 and cadena_reconstruida_utf8 != contenido_a_escribir:
                        # Cambió pero no había caracteres sospechosos claros, loguear con warning
                        log.warning(f"{logPrefix} CORRECCIÓN (Mojibake UTF-8->Latin1->UTF-8): Aplicada para '{rutaRel}', aunque no se detectaron chars Mojibake obvios previamente.")
                        contenido_corregido_mojibake = cadena_reconstruida_utf8
                    # else: No aplicar si no cambió o no pareció mejorar

            except UnicodeDecodeError:
                 log.warning(f"{logPrefix} Mojibake check para '{rutaRel}': Falló la reconstrucción UTF-8 (decode). La cadena original podría estar bien o tener otro problema de codificación.")
            except UnicodeEncodeError:
                 log.debug(f"{logPrefix} Mojibake check para '{rutaRel}': Falló la codificación a Latin-1 (encode). El contenido original probablemente no era Latin-1.")
            except Exception as e_moji:
                 log.warning(f"{logPrefix} Error inesperado durante chequeo de Mojibake para '{rutaRel}': {e_moji}. Se usará el contenido original.")

            # Actualizar contenido_a_escribir con el resultado de la corrección Mojibake
            contenido_a_escribir = contenido_corregido_mojibake

            # --- PASO 2: ELIMINADO - Ya no usamos codecs.decode('unicode_escape') ---

            # --- PASO 3: Diagnóstico y Escritura ---
            # Loguear inicio y fin para depuración
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRel}' (inicio, repr): {repr(contenido_a_escribir[:200])}")
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRel}' (fin, repr): {repr(contenido_a_escribir[-200:])}")

            # Opcional: Advertir si todavía se ven patrones Mojibake comunes
            if 'Ã©' in contenido_a_escribir or 'Ã³' in contenido_a_escribir or 'Ã¡' in contenido_a_escribir or 'Ã±' in contenido_a_escribir or 'Â¿' in contenido_a_escribir:
                log.warning(f"{logPrefix} ¡ALERTA! Contenido para '{rutaRel}' TODAVÍA parece contener Mojibake ANTES de escribir.")
            # Opcional: Advertir si hay saltos de línea literales dentro de comillas (heurística simple)
            # Esto es muy básico y puede dar falsos positivos/negativos
            # if '"\n"' in repr(contenido_a_escribir) or "'\n'" in repr(contenido_a_escribir):
            #    log.warning(f"{logPrefix} ¡ALERTA! Se detectó un salto de línea literal '\\n' dentro de comillas en el contenido para '{rutaRel}' ANTES de escribir. Podría causar error de sintaxis.")

            # Escribir el resultado final en UTF-8
            log.debug(f"{logPrefix} Escribiendo {len(contenido_a_escribir)} caracteres en {archivoAbs} con UTF-8")
            with open(archivoAbs, 'w', encoding='utf-8') as f:
                f.write(contenido_a_escribir)
            log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito correctamente.")
            archivosProcesados.append(rutaRel)

        except Exception as e_write:
             # Error durante la corrección o escritura del archivo específico
             msg = f"Error procesando/escribiendo archivo '{rutaRel}': {e_write}"
             log.error(f"{logPrefix} {msg}", exc_info=True)
             errores.append(msg)
             # Continuar con el siguiente archivo si es posible

    # --- Fin del bucle for ---

    # --- Evaluación final ---
    if errores:
        # Si hubo errores en algunos archivos, la operación general falló
        error_summary = f"Se completó el proceso pero con {len(errores)} error(es) en archivos individuales: {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary
    elif not archivosProcesados and archivos_con_contenido:
         # Si se proporcionó contenido pero no se procesó ningún archivo (quizás todos tuvieron error de ruta/directorio/escritura)
         msg = "Se proporcionó contenido pero ningún archivo pudo ser procesado debido a errores previos (ver logs)."
         log.error(f"{logPrefix} {msg}")
         return False, msg
    else:
        log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados con éxito.")
        return True, None # Éxito

# Nota: No he incluido el helper _validar_y_normalizar_ruta aquí de nuevo,
# asegúrate de que esté definido antes en el mismo archivo o importado.