# nucleo/aplicadorCambios.py
import os
import logging
import shutil

log = logging.getLogger(__name__)

def aplicarCambio(accion, rutaBase):
    # Aplica la acción de refactorización descrita en 'accion' dentro de 'rutaBase'.
    # Devuelve True si se aplicó con éxito, False en caso contrario.
    logPrefix = "aplicarCambio:"

    tipoAccion = accion.get("accion")
    detalles = accion.get("detalles", {})
    # Obtener descripción para logs, manejar caso None
    descripcionLog = accion.get("descripcion") or "Descripción no proporcionada"

    if not tipoAccion:
        log.error(f"{logPrefix} Acción inválida: falta el campo 'accion'. Data: {accion}")
        return False
    # 'detalles' puede ser un diccionario vacío para 'no_accion', lo cual es válido.
    if not isinstance(detalles, dict):
         log.error(f"{logPrefix} Acción inválida: el campo 'detalles' no es un diccionario. Data: {accion}")
         return False

    log.info(f"{logPrefix} Intentando aplicar acción '{tipoAccion}': {descripcionLog}")

    try:
        # --- Implementar lógica para cada tipo de acción ---

        if tipoAccion == "modificar_archivo":
            archivoRel = detalles.get("archivo")
            if not archivoRel or not isinstance(archivoRel, str):
                log.error(f"{logPrefix} Falta o es inválido el 'archivo' en detalles para modificar_archivo.")
                return False
            archivoAbs = os.path.normpath(os.path.join(rutaBase, archivoRel))
            # Validar que el path no intente salirse de rutaBase (seguridad básica)
            if not archivoAbs.startswith(os.path.normpath(rutaBase)):
                log.error(f"{logPrefix} Ruta de archivo inválida (intenta salir de la base): {archivoRel}")
                return False

            codigoNuevo = detalles.get("codigo_nuevo")
            buscar = detalles.get("buscar")
            reemplazar = detalles.get("reemplazar") # Puede ser None o vacío, es válido

            if not os.path.exists(archivoAbs):
                log.error(f"{logPrefix} Archivo a modificar no encontrado: {archivoAbs} (rel: {archivoRel})")
                return False

            if isinstance(codigoNuevo, str):
                # Opción 1: Reemplazar todo el contenido del archivo (usar con precaución)
                log.warning(f"{logPrefix} Modificando archivo (REEMPLAZO TOTAL): {archivoRel}")
                try:
                    # Asegurar que el dir existe (aunque el archivo ya existe, por si acaso)
                    os.makedirs(os.path.dirname(archivoAbs), exist_ok=True)
                    with open(archivoAbs, 'w', encoding='utf-8') as f:
                        f.write(codigoNuevo)
                    log.info(f"{logPrefix} Archivo sobrescrito exitosamente: {archivoRel}")
                    return True
                except Exception as e:
                    log.error(f"{logPrefix} Error al sobrescribir archivo {archivoRel}: {e}")
                    return False

            elif isinstance(buscar, str) and isinstance(reemplazar, str):
                # Opción 2: Buscar y reemplazar (preferida para cambios pequeños)
                log.info(f"{logPrefix} Modificando archivo (buscar/reemplazar): {archivoRel}")
                try:
                    with open(archivoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoOriginal = f.read()

                    # Realizar el reemplazo
                    contenidoModificado = contenidoOriginal.replace(buscar, reemplazar)

                    if contenidoModificado == contenidoOriginal:
                        # Podría ser un error del LLM (buscar no existe) o un cambio ya aplicado.
                        log.warning(f"{logPrefix} El texto a buscar no se encontró o el reemplazo no cambió el contenido en {archivoRel}. Revisar 'buscar': '{buscar[:100]}...'")
                        # Considerar esto éxito para no bloquear el flujo si es un falso positivo,
                        # pero advertir claramente. Podría ser un fallo si esperamos cambio sí o sí.
                        return True # Devolver True para permitir continuar, pero revisar logs.
                    else:
                        # Guardar el contenido modificado
                         with open(archivoAbs, 'w', encoding='utf-8') as f:
                             f.write(contenidoModificado)
                         log.info(f"{logPrefix} Archivo modificado exitosamente (buscar/reemplazar): {archivoRel}")
                         return True
                except Exception as e:
                    log.error(f"{logPrefix} Error durante buscar/reemplazar en {archivoRel}: {e}")
                    return False
            else:
                log.error(f"{logPrefix} Detalles insuficientes o inválidos para modificar_archivo. Se requiere 'codigo_nuevo' o ('buscar' y 'reemplazar'). Detalles: {detalles}")
                return False

        elif tipoAccion == "mover_archivo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")
            if not origenRel or not isinstance(origenRel, str) or not destinoRel or not isinstance(destinoRel, str):
                log.error(f"{logPrefix} Faltan o son inválidos 'archivo_origen' o 'archivo_destino' para mover_archivo.")
                return False

            origenAbs = os.path.normpath(os.path.join(rutaBase, origenRel))
            destinoAbs = os.path.normpath(os.path.join(rutaBase, destinoRel))

            # Validar paths
            if not origenAbs.startswith(os.path.normpath(rutaBase)) or not destinoAbs.startswith(os.path.normpath(rutaBase)):
                log.error(f"{logPrefix} Ruta de origen o destino inválida (intenta salir de la base): {origenRel} -> {destinoRel}")
                return False
            if not os.path.exists(origenAbs):
                log.error(f"{logPrefix} Archivo origen no encontrado para mover: {origenAbs} (rel: {origenRel})")
                return False
            if os.path.exists(destinoAbs):
                log.error(f"{logPrefix} Archivo destino ya existe, no se sobrescribirá: {destinoAbs} (rel: {destinoRel})")
                return False # Evitar sobrescrituras accidentales

            log.info(f"{logPrefix} Moviendo archivo de '{origenRel}' a '{destinoRel}'")
            try:
                os.makedirs(os.path.dirname(destinoAbs), exist_ok=True) # Asegurar dir destino
                shutil.move(origenAbs, destinoAbs)
                log.info(f"{logPrefix} Archivo movido exitosamente.")
                return True
            except Exception as e:
                 log.error(f"{logPrefix} Error al mover archivo {origenRel} a {destinoRel}: {e}")
                 return False

        elif tipoAccion == "crear_archivo":
            archivoRel = detalles.get("archivo")
            contenido = detalles.get("contenido") # Contenido es opcional (puede crear archivo vacío)

            if not archivoRel or not isinstance(archivoRel, str):
                log.error(f"{logPrefix} Falta o es inválido el 'archivo' en detalles para crear_archivo.")
                return False
            if contenido is None: # Permitir contenido vacío, pero no otros tipos
                contenido = ""
            elif not isinstance(contenido, str):
                 log.error(f"{logPrefix} El 'contenido' para crear_archivo debe ser una cadena de texto.")
                 return False

            archivoAbs = os.path.normpath(os.path.join(rutaBase, archivoRel))
            if not archivoAbs.startswith(os.path.normpath(rutaBase)):
                log.error(f"{logPrefix} Ruta de archivo inválida (intenta salir de la base): {archivoRel}")
                return False
            if os.path.exists(archivoAbs):
                 log.error(f"{logPrefix} Archivo a crear ya existe, no se sobrescribirá: {archivoAbs} (rel: {archivoRel})")
                 return False # Evitar sobrescrituras

            log.info(f"{logPrefix} Creando archivo: {archivoRel}")
            try:
                os.makedirs(os.path.dirname(archivoAbs), exist_ok=True) # Asegurar dir
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                log.info(f"{logPrefix} Archivo creado exitosamente.")
                return True
            except Exception as e:
                log.error(f"{logPrefix} Error al crear archivo {archivoRel}: {e}")
                return False

        elif tipoAccion == "eliminar_archivo":
            archivoRel = detalles.get("archivo")
            if not archivoRel or not isinstance(archivoRel, str):
                log.error(f"{logPrefix} Falta o es inválido el 'archivo' en detalles para eliminar_archivo.")
                return False

            archivoAbs = os.path.normpath(os.path.join(rutaBase, archivoRel))
            if not archivoAbs.startswith(os.path.normpath(rutaBase)):
                log.error(f"{logPrefix} Ruta de archivo inválida (intenta salir de la base): {archivoRel}")
                return False

            log.info(f"{logPrefix} Eliminando archivo: {archivoRel}")
            if not os.path.exists(archivoAbs):
                log.warning(f"{logPrefix} Archivo a eliminar no encontrado (quizás ya borrado?): {archivoAbs} (rel: {archivoRel})")
                return True # Considerar éxito si ya no existe
            if not os.path.isfile(archivoAbs): # Asegurarse que es un archivo
                 log.error(f"{logPrefix} La ruta a eliminar no es un archivo: {archivoAbs}")
                 return False

            try:
                os.remove(archivoAbs)
                log.info(f"{logPrefix} Archivo eliminado exitosamente.")
                return True
            except Exception as e:
                log.error(f"{logPrefix} Error al eliminar archivo {archivoRel}: {e}")
                return False

        elif tipoAccion == "crear_directorio":
            dirRel = detalles.get("directorio")
            if not dirRel or not isinstance(dirRel, str):
                log.error(f"{logPrefix} Falta o es inválido el 'directorio' en detalles para crear_directorio.")
                return False

            dirAbs = os.path.normpath(os.path.join(rutaBase, dirRel))
            if not dirAbs.startswith(os.path.normpath(rutaBase)):
                log.error(f"{logPrefix} Ruta de directorio inválida (intenta salir de la base): {dirRel}")
                return False

            log.info(f"{logPrefix} Creando directorio: {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs):
                     log.warning(f"{logPrefix} El directorio a crear ya existe: {dirAbs} (rel: {dirRel})")
                     return True # Considerar éxito si ya existe como directorio
                else:
                     log.error(f"{logPrefix} Existe un archivo con el mismo nombre que el directorio a crear: {dirAbs}")
                     return False

            try:
                # exist_ok=True hace que no falle si ya existe (ya lo comprobamos, pero es seguro)
                os.makedirs(dirAbs, exist_ok=True)
                log.info(f"{logPrefix} Directorio creado exitosamente (o ya existía).")
                return True
            except Exception as e:
                log.error(f"{logPrefix} Error al crear directorio {dirRel}: {e}")
                return False

        elif tipoAccion == "no_accion":
            log.info(f"{logPrefix} Acción 'no_accion' recibida. No se aplican cambios.")
            # Esto no es un fallo, es una indicación de que no hay nada que hacer.
            # Indicar que la "aplicación" (de no hacer nada) fue "exitosa".
            return True

        else:
            log.error(f"{logPrefix} Tipo de acción no soportado: '{tipoAccion}'. Acción completa: {accion}")
            return False

    except Exception as e:
        # Captura errores inesperados en la lógica de esta función
        log.error(f"{logPrefix} Error inesperado aplicando acción '{tipoAccion}' en {rutaBase}: {e}", exc_info=True)
        return False