# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import codecs # <--- AÑADIDO DE NUEVO: Necesario para 'unicode_escape'

# Obtener logger
log = logging.getLogger(__name__)

# Helper de rutas (sin cambios aquí)
def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
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


# --- FUNCIÓN PRINCIPAL (RESTAURANDO DECODIFICACIÓN) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):

    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Aplicando cambios para acción original '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase)

    # --- Manejar acciones que NO implican escribir contenido (sin cambios aquí) ---
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
         log.warning(f"{logPrefix} El diccionario 'archivos_con_contenido' está vacío para la acción '{accionOriginal}'. Esto podría ser esperado o un error de Gemini en Paso 2.")
         return True, None # No hay nada que escribir

    log.info(f"{logPrefix} Sobrescribiendo/Creando {len(archivos_con_contenido)} archivo(s)...")
    archivosProcesados = []

    try:
        for rutaRel, nuevoContenido in archivos_con_contenido.items():
            archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
            if not archivoAbs:
                raise ValueError(f"Ruta de archivo inválida proporcionada por Gemini (Paso 2): '{rutaRel}'")

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

            # --- INICIO BLOQUE RESTAURADO ---
            # Intentar decodificar escapes Unicode literales (\uXXXX) que puedan
            # estar presentes en la cadena recibida antes de escribir.
            try:
                # codecs.decode interpreta las secuencias de escape DENTRO de la cadena
                contenido_procesado = codecs.decode(nuevoContenido, 'unicode_escape')
                # Loguear solo si hubo un cambio real para evitar ruido
                if contenido_procesado != nuevoContenido:
                    log.info(f"{logPrefix} Secuencias de escape Unicode decodificadas para '{rutaRel}'.")
                else:
                    # Si no hubo cambios, es probable que no hubiera escapes literales que decodificar
                    log.debug(f"{logPrefix} No se encontraron/decodificaron secuencias de escape Unicode literales en '{rutaRel}'.")
            except Exception as e_decode:
                # En caso de error en la decodificación (ej. un \ suelto), loguear y usar el contenido original.
                log.warning(f"{logPrefix} Falló la decodificación 'unicode_escape' para '{rutaRel}': {e_decode}. Se usará el contenido original.")
                contenido_procesado = nuevoContenido # Usar el original como fallback

            # Escribir (sobrescribir) el archivo con el contenido procesado y UTF-8
            log.debug(f"{logPrefix} Escribiendo {len(contenido_procesado)} bytes en {archivoAbs} con UTF-8")
            try:
                # Asegurar que la escritura final SIEMPRE sea en UTF-8
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido_procesado) # <-- Escribe el contenido procesado (decodificado si fue posible)
                log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito correctamente.")
                archivosProcesados.append(rutaRel)
            except Exception as e_write:
                 # Captura errores específicos de escritura
                 log.error(f"{logPrefix} Error al escribir en archivo '{rutaRel}': {e_write}")
                 # Propagar la excepción para que el bloque exterior la capture
                 raise ValueError(f"Error escribiendo archivo '{rutaRel}': {e_write}") from e_write
            # --- FIN BLOQUE RESTAURADO ---

        log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados.")
        return True, None # Éxito

    except Exception as e:
        # Error durante el proceso (validación de ruta, creación de dir, escritura)
        err_msg = f"Error aplicando cambios (sobrescritura) para acción '{accionOriginal}': {e}"
        log.error(f"{logPrefix} {err_msg}", exc_info=True)
        # Confiar en `git reset --hard` en el flujo principal si esto falla.
        return False, err_msg