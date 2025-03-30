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
    rutaBaseNorm = os.path.normpath(rutaBase)
    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    if rutaRelativaNorm.startswith(('..', os.sep, '/')):
        rutaRelativaNorm = rutaRelativaNorm.lstrip(os.sep).lstrip('/')
    if not rutaRelativaNorm:
        log.error(f"{logPrefix} Ruta relativa vacía tras normalizar: original='{rutaRelativa}'")
        return None
    rutaAbs = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbs = os.path.normpath(rutaAbs)
    if not rutaAbs.startswith(rutaBaseNorm + os.sep) and rutaAbs != rutaBaseNorm:
        log.error(f"{logPrefix} Ruta '{rutaAbs}' intenta salir de la base '{rutaBaseNorm}' (de '{rutaRelativa}')")
        return None
    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.warning(f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (de '{rutaRelativa}')")
        return None
    log.debug(f"{logPrefix} Ruta validada y normalizada a: '{rutaAbs}'")
    return rutaAbs


# --- FUNCIÓN PRINCIPAL (CON CORRECCIÓN DE MOJIBAKE Y ESCAPES) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):

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
            else: log.warning(f"{logPrefix} Archivo a eliminar '{archivoRel}' no encontrado."); return True, None

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

    # --- Manejar acciones que SÍ implican escribir contenido ---
    if not isinstance(archivos_con_contenido, dict):
         return False, "El argumento 'archivos_con_contenido' debe ser un diccionario."

    if not archivos_con_contenido:
         if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             log.warning(f"{logPrefix} El diccionario 'archivos_con_contenido' vacío para acción '{accionOriginal}' que requiere contenido. Error de Gemini?")
         else: log.debug(f"{logPrefix} Diccionario 'archivos_con_contenido' vacío para acción '{accionOriginal}'.")
         return True, None

    log.info(f"{logPrefix} Sobrescribiendo/Creando {len(archivos_con_contenido)} archivo(s)...")
    archivosProcesados = []

    try:
        for rutaRel, nuevoContenido in archivos_con_contenido.items():
            archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
            if not archivoAbs:
                raise ValueError(f"Ruta inválida de Gemini (Paso 2): '{rutaRel}'")

            if not isinstance(nuevoContenido, str):
                 log.warning(f"{logPrefix} Contenido para '{rutaRel}' no es string (tipo {type(nuevoContenido)}). Convirtiendo.")
                 nuevoContenido = str(nuevoContenido)

            log.debug(f"{logPrefix} Procesando: {rutaRel} (Abs: {archivoAbs})")
            dirPadre = os.path.dirname(archivoAbs)
            if not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif not os.path.isdir(dirPadre):
                 raise ValueError(f"Ruta padre '{dirPadre}' para '{rutaRel}' no es directorio.")

            # --- Diagnóstico: Mostrar repr ANTES de cualquier corrección ---
            log.debug(f"{logPrefix} Contenido RECIBIDO para '{rutaRel}' (repr): {repr(nuevoContenido[:200])}...")

            contenido_corregido = nuevoContenido
            # --- PASO 1: Intentar corregir Mojibake (UTF-8 leído como Latin-1) ---
            try:
                # Intenta revertir la decodificación incorrecta común
                bytes_originales_prob = nuevoContenido.encode('latin-1')
                cadena_reconstruida_utf8 = bytes_originales_prob.decode('utf-8')
                # Si la reconstrucción funcionó y cambió la cadena, úsala
                if cadena_reconstruida_utf8 != nuevoContenido:
                    log.info(f"{logPrefix} CORRECCIÓN: Mojibake (UTF-8 mal decodificado como Latin-1) detectado y corregido para '{rutaRel}'.")
                    contenido_corregido = cadena_reconstruida_utf8
                else:
                    log.debug(f"{logPrefix} No se detectó Mojibake (tipo UTF-8->Latin-1) para '{rutaRel}'.")
            except UnicodeError:
                # La secuencia de bytes no era válida como UTF-8 después de encodear a Latin-1.
                # Esto significa que o la cadena original estaba bien, o tenía un problema diferente.
                log.warning(f"{logPrefix} Intento de corrección de Mojibake falló para '{rutaRel}'. La cadena podría estar bien o tener otro problema de codificación.", exc_info=False) # No mostrar traceback completo normalmente
                # Se continúa con 'contenido_corregido' que aún es 'nuevoContenido'

            # --- PASO 2: Procesar escapes literales (\uXXXX, \n) en la cadena (posiblemente ya corregida) ---
            contenido_final = contenido_corregido # Default si este paso falla
            try:
                # Interpreta secuencias como \n, \t, \uXXXX dentro de la cadena Python
                cadena_decodificada_escapes = codecs.decode(contenido_corregido, 'unicode_escape')
                if cadena_decodificada_escapes != contenido_corregido:
                    log.info(f"{logPrefix} CORRECCIÓN: Secuencias de escape literales (\\uXXXX, \\n, etc.) procesadas para '{rutaRel}'.")
                    contenido_final = cadena_decodificada_escapes
                else:
                    log.debug(f"{logPrefix} No se encontraron/procesaron secuencias de escape literales para '{rutaRel}'.")
            except Exception as e_escape:
                log.warning(f"{logPrefix} Error procesando secuencias de escape para '{rutaRel}': {e_escape}. Usando contenido después del chequeo de Mojibake.", exc_info=False)
                # 'contenido_final' se queda como 'contenido_corregido'

            # --- Diagnóstico: Mostrar repr DESPUÉS de todas las correcciones ---
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRel}' (repr): {repr(contenido_final[:200])}...")

            # --- Escribir el resultado final ---
            log.debug(f"{logPrefix} Escribiendo {len(contenido_final)} caracteres en {archivoAbs} con UTF-8")
            try:
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido_final)
                log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito correctamente.")
                archivosProcesados.append(rutaRel)
            except Exception as e_write:
                 log.error(f"{logPrefix} Error al escribir archivo '{rutaRel}': {e_write}")
                 raise ValueError(f"Error escribiendo archivo '{rutaRel}': {e_write}") from e_write

        log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados.")
        return True, None # Éxito

    except Exception as e:
        err_msg = f"Error aplicando cambios (sobrescritura) para acción '{accionOriginal}': {e}"
        log.error(f"{logPrefix} {err_msg}", exc_info=True)
        return False, err_msg