# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import json
import codecs # <--- ¡Asegúrate de que esté importado!

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


# --- FUNCIÓN PRINCIPAL CON unicode_escape REINTRODUCIDO ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    """
    Aplica los cambios generados por Gemini.
    - Sobrescribe archivos existentes o crea nuevos con el contenido proporcionado.
    - Maneja acciones como eliminar_archivo y crear_directorio.
    - Intenta corregir Mojibake común (UTF-8 mal leído como Latin-1).
    - Decodifica secuencias de escape Unicode (\uXXXX) literales.
    - Escribe archivos en UTF-8.

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
    # ... (Manejo de eliminar_archivo, crear_directorio y validaciones iniciales igual que antes) ...
    rutaBaseNorm = os.path.normpath(rutaBase)

    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        # ... (código para eliminar/crear directorio igual que en la versión anterior) ...
        if accionOriginal == "eliminar_archivo":
            archivoRel = paramsOriginal.get("archivo")
            if not archivoRel: return False, "Falta 'archivo' en parámetros para eliminar_archivo."
            archivoAbs = _validar_y_normalizar_ruta(archivoRel, rutaBaseNorm, asegurar_existencia=False)
            if archivoAbs is None: return False, f"Ruta inválida o no encontrada para eliminar: '{archivoRel}'"
            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Eliminando {archivoRel}")
            if os.path.exists(archivoAbs):
                if os.path.isfile(archivoAbs):
                    try: os.remove(archivoAbs); log.info(f"{logPrefix} Archivo '{archivoRel}' eliminado."); return True, None
                    except Exception as e: err = f"Error al eliminar archivo '{archivoRel}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
                else: err = f"Ruta a eliminar '{archivoRel}' existe pero NO es un archivo."; log.error(f"{logPrefix} {err}"); return False, err
            else: log.warning(f"{logPrefix} Archivo a eliminar '{archivoRel}' no encontrado. Se considera éxito."); return True, None

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
        return True, None


    if not isinstance(archivos_con_contenido, dict):
         err = "Argumento 'archivos_con_contenido' no es un diccionario."
         log.error(f"{logPrefix} {err}")
         return False, err

    if not archivos_con_contenido:
         err = f"Se esperaba contenido en 'archivos_con_contenido' para la acción '{accionOriginal}', pero está vacío. Error probable en Paso 2."
         log.error(f"{logPrefix} {err}")
         return False, err

    log.info(f"{logPrefix} Sobrescribiendo/Creando {len(archivos_con_contenido)} archivo(s)...")
    archivosProcesados = []
    errores = []

    # --- Bucle principal para escribir archivos ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        # ... (Validación de ruta y creación de directorio padre igual que antes) ...
        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Ruta inválida o insegura ('{rutaRel}') recibida de Gemini (Paso 2). Archivo omitido."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        if not isinstance(contenido_original_json, str):
             log.warning(f"{logPrefix} Contenido para '{rutaRel}' no es string (tipo {type(contenido_original_json)}). Convirtiendo a string.")
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
             contenido_str = contenido_original_json

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
            continue

        # --- Inicio Bloque de Corrección Mojibake, Decodificación Unicode y Escritura ---
        contenido_procesado = contenido_str # Empezar con el string validado
        try:
            # --- PASO 1: Intentar corregir Mojibake (UTF-8 mal leído como Latin-1) ---
            contenido_despues_mojibake = contenido_procesado # Default si no se corrige
            try:
                bytes_probables = contenido_procesado.encode('latin-1')
                cadena_reconstruida_utf8 = bytes_probables.decode('utf-8')
                if cadena_reconstruida_utf8 != contenido_procesado:
                    # Aplicar heurística o simplemente aplicar si cambió
                    log.info(f"{logPrefix} CORRECCIÓN (Mojibake UTF-8->Latin1->UTF-8): Aplicada para '{rutaRel}'.")
                    contenido_despues_mojibake = cadena_reconstruida_utf8
            except (UnicodeDecodeError, UnicodeEncodeError) as e_moji_codec:
                 log.debug(f"{logPrefix} Mojibake check para '{rutaRel}': Falló ('{e_moji_codec}'). Contenido original probablemente no seguía el patrón.")
            except Exception as e_moji_other:
                 log.warning(f"{logPrefix} Error inesperado durante chequeo de Mojibake para '{rutaRel}': {e_moji_other}. Se usará el contenido anterior.")
            # Actualizar para el siguiente paso
            contenido_procesado = contenido_despues_mojibake

            # --- PASO 2: Decodificar escapes Unicode (\uXXXX) literales ---
            # Esto es necesario porque json.loads convierte '\\uXXXX' del JSON en '\uXXXX' literal en Python.
            contenido_despues_unicode_escape = contenido_procesado # Default si no cambia
            try:
                # Usar codecs.decode para interpretar \uXXXX, \n, etc.
                # que están LITERALMENTE en la cadena `contenido_procesado`
                cadena_decodificada = codecs.decode(contenido_procesado, 'unicode_escape')
                if cadena_decodificada != contenido_procesado:
                    log.info(f"{logPrefix} CORRECCIÓN (Escapes): Secuencias de escape literales (ej. \\uXXXX, \\n) procesadas para '{rutaRel}'.")
                    contenido_despues_unicode_escape = cadena_decodificada
                # else: # No loguear si no cambió para no llenar de ruido
                #    log.debug(f"{logPrefix} No se procesaron secuencias de escape literales para '{rutaRel}'.")

            except Exception as e_escape:
                # Si falla la decodificación de escapes, es grave, podría indicar malformación
                log.error(f"{logPrefix} ¡ERROR GRAVE! Falló el procesamiento de secuencias de escape (unicode_escape) para '{rutaRel}': {e_escape}. Se usará el contenido ANTES de este paso, pero puede ser incorrecto.", exc_info=True)
                # contenido_despues_unicode_escape mantiene el valor de contenido_procesado

            # Actualizar contenido final a escribir
            contenido_a_escribir = contenido_despues_unicode_escape

            # --- PASO 3: Diagnóstico y Escritura ---
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRel}' (inicio, repr): {repr(contenido_a_escribir[:200])}")
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRel}' (fin, repr): {repr(contenido_a_escribir[-200:])}")

            # Advertir si aún se ven patrones Mojibake (por si la corrección falló o el problema es otro)
            if 'Ã©' in contenido_a_escribir or 'Ã³' in contenido_a_escribir or 'Ã¡' in contenido_a_escribir or 'Ã±' in contenido_a_escribir:
                log.warning(f"{logPrefix} ¡ALERTA! Contenido para '{rutaRel}' TODAVÍA parece contener Mojibake ANTES de escribir.")

            # Escribir el resultado final en UTF-8
            log.debug(f"{logPrefix} Escribiendo {len(contenido_a_escribir)} caracteres en {archivoAbs} con UTF-8")
            with open(archivoAbs, 'w', encoding='utf-8') as f:
                f.write(contenido_a_escribir)
            log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito correctamente.")
            archivosProcesados.append(rutaRel)

        except Exception as e_process_write:
             # Error durante la corrección o escritura del archivo específico
             msg = f"Error procesando/escribiendo archivo '{rutaRel}': {e_process_write}"
             log.error(f"{logPrefix} {msg}", exc_info=True)
             errores.append(msg)
             # Continuar con el siguiente archivo si es posible

    # --- Fin del bucle for ---

    # --- Evaluación final (igual que antes) ---
    if errores:
        error_summary = f"Se completó el proceso pero con {len(errores)} error(es): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary
    elif not archivosProcesados and archivos_con_contenido:
         msg = "Se proporcionó contenido pero ningún archivo pudo ser procesado debido a errores previos (ver logs)."
         log.error(f"{logPrefix} {msg}")
         return False, msg
    else:
        log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados con éxito.")
        return True, None # Éxito