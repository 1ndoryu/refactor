# nucleo/aplicadorCambios.py
import os
import logging
import shutil
# import codecs # <--- ELIMINADO OTRA VEZ

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


# --- FUNCIÓN PRINCIPAL (SIMPLIFICADA + LOGGING DIAGNÓSTICO) ---
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
         # Si la acción original SÍ esperaba contenido, esto es raro.
         if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             log.warning(f"{logPrefix} El diccionario 'archivos_con_contenido' está vacío para la acción '{accionOriginal}' que normalmente requiere contenido. Esto podría ser un error de Gemini en Paso 2.")
         else:
             # Esto es normal para eliminar/crear dir si Gemini responde así por error
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
            # Crear directorio padre si no existe
            dirPadre = os.path.dirname(archivoAbs)
            if not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif not os.path.isdir(dirPadre):
                 raise ValueError(f"La ruta padre '{dirPadre}' para el archivo '{rutaRel}' existe pero no es un directorio.")

            # --- Diagnóstico: Mostrar la representación de la cadena ANTES de escribir ---
            # repr() muestra cómo Python ve la cadena, incluyendo escapes si los hubiera.
            # Si aquí ves 'páginas', la cadena es correcta. Si ves 'pÃ¡ginas', está corrupta.
            log.debug(f"{logPrefix} Contenido a escribir para '{rutaRel}' (repr): {repr(nuevoContenido[:200])}...") # Loguea los primeros 200 caracteres

            # Escribir (sobrescribir) el archivo directamente con UTF-8
            log.debug(f"{logPrefix} Escribiendo {len(nuevoContenido)} caracteres en {archivoAbs} con UTF-8")
            try:
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(nuevoContenido) # Escribe la cadena Unicode directamente
                log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito correctamente.")
                archivosProcesados.append(rutaRel)
            except Exception as e_write:
                 log.error(f"{logPrefix} Error al escribir en archivo '{rutaRel}': {e_write}")
                 raise ValueError(f"Error escribiendo archivo '{rutaRel}': {e_write}") from e_write

        log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados.")
        return True, None # Éxito

    except Exception as e:
        # Error durante el proceso (validación de ruta, creación de dir, escritura)
        err_msg = f"Error aplicando cambios (sobrescritura) para acción '{accionOriginal}': {e}"
        log.error(f"{logPrefix} {err_msg}", exc_info=True)
        return False, err_msg