# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import codecs # <--- RESTAURADO

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
        # Advertir aquí, el error se maneja donde se llama
        log.warning(f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (de '{rutaRelativa}')")
        return None # Indicar fallo si se requiere existencia
    log.debug(f"{logPrefix} Ruta validada y normalizada a: '{rutaAbs}'")
    return rutaAbs


# --- FUNCIÓN PRINCIPAL (RESTAURANDO DECODIFICACIÓN UNICODE_ESCAPE + LOGGING) ---
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
                    try:
                        os.remove(archivoAbs)
                        log.info(f"{logPrefix} Archivo '{archivoRel}' eliminado correctamente.")
                        return True, None
                    except Exception as e:
                        err = f"Error al eliminar archivo '{archivoRel}': {e}"
                        log.error(f"{logPrefix} {err}", exc_info=True)
                        return False, err
                else:
                    err = f"La ruta a eliminar '{archivoRel}' existe pero no es un archivo."
                    log.error(f"{logPrefix} {err}")
                    return False, err
            else:
                log.warning(f"{logPrefix} Archivo a eliminar '{archivoRel}' no encontrado. Considerando éxito.")
                return True, None # Ya no existe

        elif accionOriginal == "crear_directorio":
            dirRel = paramsOriginal.get("directorio")
            if not dirRel: return False, "Falta 'directorio' en parámetros para crear_directorio."
            dirAbs = _validar_y_normalizar_ruta(dirRel, rutaBaseNorm, asegurar_existencia=False)
            if not dirAbs: return False, f"Ruta inválida para crear directorio: '{dirRel}'"

            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Creando directorio {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs):
                    log.warning(f"{logPrefix} Directorio '{dirRel}' ya existe. Considerando éxito.")
                    return True, None
                else:
                    err = f"Ya existe un archivo en la ruta del directorio a crear: '{dirRel}'"
                    log.error(f"{logPrefix} {err}")
                    return False, err
            else:
                try:
                    os.makedirs(dirAbs, exist_ok=True)
                    log.info(f"{logPrefix} Directorio '{dirRel}' creado correctamente.")
                    return True, None
                except Exception as e:
                    err = f"Error al crear directorio '{dirRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    return False, err

    # --- Manejar acciones que SÍ implican escribir contenido ---
    if not isinstance(archivos_con_contenido, dict):
         return False, "El argumento 'archivos_con_contenido' debe ser un diccionario."

    if not archivos_con_contenido:
         if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             log.warning(f"{logPrefix} El diccionario 'archivos_con_contenido' está vacío para la acción '{accionOriginal}' que normalmente requiere contenido. Esto podría ser un error de Gemini en Paso 2.")
         else:
             log.debug(f"{logPrefix} El diccionario 'archivos_con_contenido' está vacío para la acción '{accionOriginal}'.")
         return True, None # No hay nada que escribir

    log.info(f"{logPrefix} Sobrescribiendo/Creando {len(archivos_con_contenido)} archivo(s)...")
    archivosProcesados = []

    try:
        for rutaRel, nuevoContenido in archivos_con_contenido.items():
            archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
            if not archivoAbs:
                raise ValueError(f"Ruta de archivo inválida proporcionada por Gemini (Paso 2): '{rutaRel}'")

            # Asegurarse de que es una cadena Python Unicode
            if not isinstance(nuevoContenido, str):
                 log.warning(f"{logPrefix} Contenido para '{rutaRel}' no es string (tipo {type(nuevoContenido)}). Se convertirá a string.")
                 nuevoContenido = str(nuevoContenido)

            log.debug(f"{logPrefix} Procesando: {rutaRel} (Abs: {archivoAbs})")
            dirPadre = os.path.dirname(archivoAbs)
            if not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif not os.path.isdir(dirPadre):
                 raise ValueError(f"La ruta padre '{dirPadre}' para el archivo '{rutaRel}' existe pero no es un directorio.")

            # --- Diagnóstico: Mostrar repr ANTES de decodificar ---
            log.debug(f"{logPrefix} Contenido RECIBIDO para '{rutaRel}' (repr): {repr(nuevoContenido[:200])}...")

            # --- INICIO BLOQUE RESTAURADO ---
            # Intentar decodificar escapes literales (ej: \uXXXX, \n) que
            # puedan haber quedado en la cadena después del parseo JSON.
            contenido_procesado = nuevoContenido # Default si falla la decodificación
            try:
                # codecs.decode interpreta las secuencias de escape DENTRO de la cadena Python
                contenido_decodificado = codecs.decode(nuevoContenido, 'unicode_escape')
                # Loguear solo si hubo un cambio real para evitar ruido
                if contenido_decodificado != nuevoContenido:
                    log.info(f"{logPrefix} Secuencias de escape literales (ej: \\uXXXX, \\n) decodificadas para '{rutaRel}'.")
                    contenido_procesado = contenido_decodificado # Usar el resultado decodificado
                else:
                    log.debug(f"{logPrefix} No se encontraron/decodificaron secuencias de escape literales en '{rutaRel}'.")
                    # contenido_procesado ya es nuevoContenido
            except UnicodeDecodeError as e_decode:
                 # Error común si hay una barra invertida suelta que no forma parte de un escape válido
                 log.warning(f"{logPrefix} Falló la decodificación 'unicode_escape' para '{rutaRel}': {e_decode}. Se usará el contenido tal como se recibió (después del parseo JSON).")
                 # contenido_procesado ya es nuevoContenido
            except Exception as e_decode_inesperado:
                 # Otros errores inesperados durante la decodificación
                 log.warning(f"{logPrefix} Error inesperado durante 'unicode_escape' para '{rutaRel}': {e_decode_inesperado}. Se usará el contenido tal como se recibió.", exc_info=True)
                 # contenido_procesado ya es nuevoContenido
            # --- FIN BLOQUE RESTAURADO ---

            # --- Diagnóstico: Mostrar repr DESPUÉS de decodificar (o fallback) ---
            log.debug(f"{logPrefix} Contenido A ESCRIBIR para '{rutaRel}' (repr): {repr(contenido_procesado[:200])}...")

            # Escribir (sobrescribir) el archivo con el contenido procesado y UTF-8
            log.debug(f"{logPrefix} Escribiendo {len(contenido_procesado)} caracteres en {archivoAbs} con UTF-8")
            try:
                # Asegurar que la escritura final SIEMPRE sea en UTF-8
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido_procesado) # <-- Escribe el contenido potencialmente decodificado
                log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito correctamente.")
                archivosProcesados.append(rutaRel)
            except Exception as e_write:
                 log.error(f"{logPrefix} Error al escribir en archivo '{rutaRel}': {e_write}")
                 raise ValueError(f"Error escribiendo archivo '{rutaRel}': {e_write}") from e_write

        log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados.")
        return True, None # Éxito

    except Exception as e:
        err_msg = f"Error aplicando cambios (sobrescritura) para acción '{accionOriginal}': {e}"
        log.error(f"{logPrefix} {err_msg}", exc_info=True)
        return False, err_msg