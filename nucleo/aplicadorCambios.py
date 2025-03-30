# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import codecs # Necesario para unicode_escape

# Obtener logger
log = logging.getLogger(__name__)

# Helper de rutas (sin cambios aquí)
def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    # ... (código igual que antes) ...
    logPrefix = "_validar_y_normalizar_ruta:"
    log.debug(f"{logPrefix} Validando rutaRelativa='{rutaRelativa}', rutaBase='{rutaBase}', asegurar_existencia={asegurar_existencia}")
    if not rutaRelativa or not isinstance(rutaRelativa, str) or '..' in rutaRelativa.split(os.sep):
        log.error(f"{logPrefix} Ruta relativa inválida o sospechosa: '{rutaRelativa}'")
        return None
    # Asegurarse que la ruta base sea absoluta para comparaciones seguras
    rutaBaseNorm = os.path.normpath(os.path.abspath(rutaBase))
    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    # Prevenir que rutas como '/etc/passwd' se conviertan en válidas si rutaBase es '/'
    if os.path.isabs(rutaRelativaNorm):
         log.error(f"{logPrefix} Ruta relativa '{rutaRelativa}' parece ser absoluta tras normalizar: '{rutaRelativaNorm}'. Rechazada.")
         return None
    rutaAbs = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbs = os.path.normpath(rutaAbs) # Normalizar de nuevo después de join

    # Comprobación de seguridad estricta
    if not os.path.abspath(rutaAbs).startswith(os.path.abspath(rutaBaseNorm) + os.sep) and \
       os.path.abspath(rutaAbs) != os.path.abspath(rutaBaseNorm):
        log.error(f"{logPrefix} Ruta calculada '{os.path.abspath(rutaAbs)}' intenta salir de la base '{os.path.abspath(rutaBaseNorm)}' (originada de '{rutaRelativa}')")
        return None

    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.warning(f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (de '{rutaRelativa}')")
        return None # O podría ser True dependiendo de la lógica que llama

    log.debug(f"{logPrefix} Ruta validada y normalizada a: '{rutaAbs}'")
    return rutaAbs


# --- FUNCIÓN PRINCIPAL (CON CORRECCIÓN DE MOJIBAKE Y ESCAPES) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):

    # Aplica los cambios sobrescribiendo archivos.
    # Incluye pasos para intentar corregir Mojibake común (UTF-8 mal leído como Latin-1)
    # y procesar secuencias de escape literales (como \n, \uXXXX) antes de escribir.

    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Aplicando cambios para acción original '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase)

    # --- Manejar acciones que NO implican escribir contenido (sin cambios aquí) ---
    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        # ... (código igual que antes para eliminar_archivo y crear_directorio) ...
        if accionOriginal == "eliminar_archivo":
            archivoRel = paramsOriginal.get("archivo")
            if not archivoRel: return False, "Falta 'archivo' en parámetros para eliminar_archivo."
            archivoAbs = _validar_y_normalizar_ruta(archivoRel, rutaBaseNorm, asegurar_existencia=False)
            if not archivoAbs: return False, f"Ruta inválida para eliminar: '{archivoRel}'"
            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Eliminando {archivoRel}")
            if os.path.exists(archivoAbs):
                if os.path.isfile(archivoAbs):
                    try: os.remove(archivoAbs); log.info(f"{logPrefix} Archivo '{archivoRel}' eliminado."); return True, None
                    except Exception as e: err = f"Error al eliminar '{archivoRel}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
                else: err = f"Ruta a eliminar '{archivoRel}' no es archivo."; log.error(f"{logPrefix} {err}"); return False, err
            else: log.warning(f"{logPrefix} Archivo a eliminar '{archivoRel}' no encontrado."); return True, None # No es un error si no existe

        elif accionOriginal == "crear_directorio":
            dirRel = paramsOriginal.get("directorio")
            if not dirRel: return False, "Falta 'directorio' en parámetros para crear_directorio."
            dirAbs = _validar_y_normalizar_ruta(dirRel, rutaBaseNorm, asegurar_existencia=False)
            if not dirAbs: return False, f"Ruta inválida para crear directorio: '{dirRel}'"
            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Creando directorio {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs): log.warning(f"{logPrefix} Directorio '{dirRel}' ya existe."); return True, None
                else: err = f"Archivo existe en ruta de dir a crear: '{dirRel}'"; log.error(f"{logPrefix} {err}"); return False, err
            else:
                try: os.makedirs(dirAbs, exist_ok=True); log.info(f"{logPrefix} Directorio '{dirRel}' creado."); return True, None
                except Exception as e: err = f"Error al crear dir '{dirRel}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
        # Retornar aquí para estas acciones
        return True, None # Asumiendo que si llegó aquí y no falló antes, está bien

    # --- Manejar acciones que SÍ implican escribir contenido ---
    if not isinstance(archivos_con_contenido, dict):
         return False, "El argumento 'archivos_con_contenido' debe ser un diccionario."

    # Es válido tener dict vacío si la acción no lo requería (aunque ya lo manejamos arriba)
    # Pero si SÍ lo requiere (ej. modificar) y viene vacío, es un error de Gemini
    if not archivos_con_contenido and accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
         log.error(f"{logPrefix} El diccionario 'archivos_con_contenido' está vacío para la acción '{accionOriginal}' que requiere contenido. Error probable en Paso 2.")
         return False, f"Contenido vacío recibido para la acción {accionOriginal}"

    log.info(f"{logPrefix} Sobrescribiendo/Creando {len(archivos_con_contenido)} archivo(s)...")
    archivosProcesados = []
    errores = []

    try:
        for rutaRel, nuevoContenido in archivos_con_contenido.items():
            archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
            if not archivoAbs:
                # No lanzar excepción aquí, registrar el error y continuar con otros archivos si es posible
                msg = f"Ruta inválida o insegura proporcionada por Gemini (Paso 2): '{rutaRel}'. Archivo omitido."
                log.error(f"{logPrefix} {msg}")
                errores.append(msg)
                continue # Saltar al siguiente archivo

            if not isinstance(nuevoContenido, str):
                 log.warning(f"{logPrefix} Contenido para '{rutaRel}' no es string (tipo {type(nuevoContenido)}). Convirtiendo a string, pero podría indicar un problema previo.")
                 nuevoContenido = str(nuevoContenido)

            log.debug(f"{logPrefix} Procesando archivo: {rutaRel} (Abs: {archivoAbs})")
            dirPadre = os.path.dirname(archivoAbs)
            try:
                if not os.path.exists(dirPadre):
                    log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                    os.makedirs(dirPadre, exist_ok=True)
                elif not os.path.isdir(dirPadre):
                     # No es un directorio, error
                     raise ValueError(f"La ruta padre '{dirPadre}' para el archivo '{rutaRel}' existe pero no es un directorio.")
            except Exception as e_dir:
                msg = f"Error creando/validando directorio padre '{dirPadre}' para '{rutaRel}': {e_dir}. Archivo omitido."
                log.error(f"{logPrefix} {msg}", exc_info=True)
                errores.append(msg)
                continue # Saltar al siguiente archivo

            # --- Inicio Bloque de Corrección y Escritura ---
            contenido_a_escribir = nuevoContenido # Empezar con el original
            try:
                # --- PASO 1 (Opcional pero recomendado): Intentar corregir Mojibake (UTF-8 mal decodificado como Latin-1) ---
                try:
                    # Intenta revertir la decodificación incorrecta común
                    bytes_originales_prob = nuevoContenido.encode('latin-1')
                    cadena_reconstruida_utf8 = bytes_originales_prob.decode('utf-8')
                    # Si la reconstrucción funcionó Y cambió la cadena Y es diferente del original
                    if cadena_reconstruida_utf8 != nuevoContenido:
                        # Validar si la cadena reconstruida parece más razonable ( heurística simple )
                        # Contar caracteres 'Ã' comunes en Mojibake vs caracteres acentuados comunes
                        mojibake_chars = sum(1 for char in nuevoContenido if char in 'Ã©Ã±ÃºÃ³Ã¡Ã') # Algunos ejemplos
                        corrected_chars = sum(1 for char in cadena_reconstruida_utf8 if char in 'éñúóáü')
                        if mojibake_chars > 0 and corrected_chars >= mojibake_chars: # Si había mojibake y ahora hay caracteres correctos
                             log.info(f"{logPrefix} CORRECCIÓN (Mojibake): Patrón UTF-8 leído como Latin-1 detectado y corregido para '{rutaRel}'.")
                             contenido_a_escribir = cadena_reconstruida_utf8
                        # else: # No aplicar si no parece una mejora clara
                        #    log.debug(f"{logPrefix} Mojibake check para '{rutaRel}': Reconstrucción UTF-8 no pareció necesaria o no mejoró.")
                    # else: # Si no cambió, estaba bien o el problema era otro
                    #    log.debug(f"{logPrefix} Mojibake check para '{rutaRel}': Contenido original parece ser UTF-8 válido o no coincide con el patrón Latin-1.")

                except UnicodeDecodeError:
                     # Si falla el decode('utf-8'), la suposición de Latin-1 -> UTF-8 era incorrecta. La cadena original podría estar bien o tener otro problema.
                     log.warning(f"{logPrefix} Mojibake check para '{rutaRel}': Falló la reconstrucción UTF-8. La cadena original podría estar bien o tener otro problema de codificación.")
                except UnicodeEncodeError:
                     # Si falla el encode('latin-1'), la cadena original probablemente ya contenía caracteres > 255 (no era Latin-1)
                     log.debug(f"{logPrefix} Mojibake check para '{rutaRel}': El contenido original no parece ser Latin-1.")
                except Exception as e_moji:
                     log.warning(f"{logPrefix} Error inesperado durante chequeo de Mojibake para '{rutaRel}': {e_moji}")


                # --- PASO 2: Procesar escapes literales (\uXXXX, \n, etc.) en la cadena (posiblemente ya corregida) ---
                # Esto es crucial si Gemini devuelve '\\n' literal en lugar de un salto de línea dentro de la cadena JSON.
                # Usamos el contenido resultante del paso anterior (contenido_a_escribir)
                try:
                    # Interpreta secuencias como \n, \t, \uXXXX dentro de la cadena Python
                    cadena_decodificada_escapes = codecs.decode(contenido_a_escribir, 'unicode_escape')
                    if cadena_decodificada_escapes != contenido_a_escribir:
                        log.info(f"{logPrefix} CORRECCIÓN (Escapes): Secuencias de escape literales (ej. \\n, \\uXXXX) procesadas para '{rutaRel}'.")
                        contenido_a_escribir = cadena_decodificada_escapes
                    # else:
                    #    log.debug(f"{logPrefix} No se procesaron secuencias de escape literales para '{rutaRel}'.")
                except Exception as e_escape:
                    log.warning(f"{logPrefix} Error procesando secuencias de escape para '{rutaRel}': {e_escape}. Se usará el contenido después del chequeo de Mojibake (si lo hubo).", exc_info=False)
                    # 'contenido_a_escribir' se queda como estaba antes de este bloque try

                # --- Diagnóstico Final (Opcional) ---
                # log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRel}' (repr): {repr(contenido_a_escribir[:200])}...")
                
                   # --- Diagnóstico Final MEJORADO (AÑADIR ESTO) ---
                log.debug(f"{logPrefix} Contenido ANTES de escribir para '{rutaRel}' (inicio, repr): {repr(contenido_a_escribir[:200])}")
                log.debug(f"{logPrefix} Contenido ANTES de escribir para '{rutaRel}' (fin, repr): {repr(contenido_a_escribir[-200:])}")
                # Opcional: Loguear si todavía contiene el patrón problemático
                if 'Ã³' in contenido_a_escribir or 'Ã¡' in contenido_a_escribir or 'Ã±' in contenido_a_escribir:
                    log.warning(f"{logPrefix} ¡ALERTA! Contenido para '{rutaRel}' todavía parece contener Mojibake ANTES de escribir.")



                # --- Escribir el resultado final ---
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

        if errores:
            # Si hubo errores en algunos archivos, la operación general falló
            error_summary = f"Se completó el proceso pero con {len(errores)} error(es) en archivos individuales: {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
            log.error(f"{logPrefix} {error_summary}")
            return False, error_summary
        elif not archivosProcesados and archivos_con_contenido:
             # Si se proporcionó contenido pero no se procesó ningún archivo (quizás todos tuvieron error de ruta/directorio)
             msg = "Se proporcionó contenido pero ningún archivo pudo ser procesado debido a errores previos (ver logs)."
             log.error(f"{logPrefix} {msg}")
             return False, msg
        else:
            log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados con éxito.")
            return True, None # Éxito

    except Exception as e_outer:
        # Error inesperado fuera del bucle principal
        err_msg = f"Error general aplicando cambios (sobrescritura) para acción '{accionOriginal}': {e_outer}"
        log.error(f"{logPrefix} {err_msg}", exc_info=True)
        return False, err_msg