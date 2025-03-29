# nucleo/aplicadorCambios.py
import os
import logging
import shutil

log = logging.getLogger(__name__)

# Helper para validar rutas y evitar salida de la base
def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    logPrefix = "_validar_y_normalizar_ruta:"
    if not rutaRelativa or not isinstance(rutaRelativa, str) or '..' in rutaRelativa.split(os.sep):
        log.error(f"{logPrefix} Ruta relativa inválida o sospechosa: '{rutaRelativa}'")
        return None
    # Normalizar y unir
    rutaAbs = os.path.normpath(os.path.join(rutaBase, rutaRelativa))
    # Comprobar que sigue dentro de rutaBase
    if not rutaAbs.startswith(os.path.normpath(rutaBase) + os.sep) and rutaAbs != os.path.normpath(rutaBase):
         log.error(f"{logPrefix} Ruta calculada '{rutaAbs}' intenta salir de la base '{rutaBase}' (originó de '{rutaRelativa}')")
         return None
    # Comprobar existencia si se requiere
    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.error(f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (originó de '{rutaRelativa}')")
        return None

    # Devolver ruta absoluta normalizada
    return rutaAbs

def aplicarCambio(accion, rutaBase):
    # Aplica la acción de refactorización descrita en 'accion' dentro de 'rutaBase'.
    # Devuelve True si se aplicó con éxito, False en caso contrario.
    logPrefix = "aplicarCambio:"

    tipoAccion = accion.get("accion")
    detalles = accion.get("detalles", {})
    descripcionLog = accion.get("descripcion", "Descripción no proporcionada") # Usar get con default

    if not tipoAccion:
        log.error(f"{logPrefix} Acción inválida: falta 'accion'. Data: {accion}")
        return False
    if not isinstance(detalles, dict):
         log.error(f"{logPrefix} Acción inválida: 'detalles' no es un dict. Data: {accion}")
         return False

    log.info(f"{logPrefix} Intentando aplicar acción '{tipoAccion}': {descripcionLog}")
    rutaBaseNorm = os.path.normpath(rutaBase) # Normalizar una vez

    try:
        # --- Implementar lógica para cada tipo de acción ---

        if tipoAccion == "modificar_archivo":
            archivoRel = detalles.get("archivo")
            archivoAbs = _validar_y_normalizar_ruta(archivoRel, rutaBaseNorm, asegurar_existencia=True)
            if not archivoAbs: return False # Error ya logueado en helper

            codigoNuevo = detalles.get("codigo_nuevo")
            buscar = detalles.get("buscar")
            reemplazar = detalles.get("reemplazar") # Permitir None o vacío

            # Validar que sea un archivo
            if not os.path.isfile(archivoAbs):
                log.error(f"{logPrefix} La ruta para modificar no es un archivo: {archivoAbs}")
                return False

            if isinstance(codigoNuevo, str):
                # Opción 1: Reemplazo total (Peligroso)
                log.warning(f"{logPrefix} Modificando archivo [REEMPLAZO TOTAL]: {archivoRel}")
                try:
                    # No es necesario makedirs aquí porque el archivo ya existe
                    with open(archivoAbs, 'w', encoding='utf-8') as f:
                        f.write(codigoNuevo)
                    log.info(f"{logPrefix} Archivo sobrescrito exitosamente: {archivoRel}")
                    return True
                except Exception as e:
                    log.error(f"{logPrefix} Error al sobrescribir archivo {archivoRel}: {e}")
                    return False

            elif isinstance(buscar, str) and reemplazar is not None: # reemplazar puede ser ""
                # Opción 2: Buscar y reemplazar (Preferido)
                log.info(f"{logPrefix} Modificando archivo [buscar/reemplazar]: {archivoRel}")
                try:
                    with open(archivoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoOriginal = f.read()

                    # Realizar el reemplazo
                    contenidoModificado = contenidoOriginal.replace(buscar, reemplazar)

                    if contenidoModificado == contenidoOriginal:
                        # *** CAMBIO CLAVE: ERROR y FALLO si no hubo cambio ***
                        log.error(f"{logPrefix} Texto a buscar no encontrado o el reemplazo no cambió el contenido en {archivoRel}. La acción falló. Revisar 'buscar': '{buscar[:100]}...'")
                        # Devolver False para indicar fallo en la aplicación del cambio
                        return False
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

        # <<< INICIO: Acción mover_codigo (sin cambios respecto a la versión anterior) >>>
        elif tipoAccion == "mover_codigo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")
            codigoAMover = detalles.get("codigo_a_mover")

            # Validación de parámetros
            if not isinstance(origenRel, str) or not isinstance(destinoRel, str) or not isinstance(codigoAMover, str):
                log.error(f"{logPrefix} Faltan o son inválidos 'archivo_origen', 'archivo_destino' o 'codigo_a_mover' para mover_codigo.")
                return False
            if not codigoAMover:
                log.error(f"{logPrefix} El 'codigo_a_mover' no puede estar vacío.")
                return False

            # Validar rutas (origen debe existir, destino no necesariamente pero debe ser válida)
            origenAbs = _validar_y_normalizar_ruta(origenRel, rutaBaseNorm, asegurar_existencia=True)
            if not origenAbs: return False
            destinoAbs = _validar_y_normalizar_ruta(destinoRel, rutaBaseNorm, asegurar_existencia=False) # Destino podría no existir aún
            if not destinoAbs: return False

             # Validar que origen y destino sean archivos (o vayan a serlo)
            if not os.path.isfile(origenAbs):
                log.error(f"{logPrefix} El origen para mover_codigo no es un archivo: {origenAbs}")
                return False
            if os.path.exists(destinoAbs) and not os.path.isfile(destinoAbs):
                log.error(f"{logPrefix} El destino para mover_codigo existe pero no es un archivo: {destinoAbs}")
                return False

            log.info(f"{logPrefix} Moviendo código de '{origenRel}' a '{destinoRel}'")

            try:
                # --- Leer Origen ---
                with open(origenAbs, 'r', encoding='utf-8', errors='ignore') as f:
                    contenidoOrigen = f.read()

                # --- Verificar que el código a mover existe en origen ---
                if codigoAMover not in contenidoOrigen:
                    log.error(f"{logPrefix} El 'codigo_a_mover' NO SE ENCONTRÓ en {origenRel}. Abortando.")
                    log.debug(f"{logPrefix} Código buscado (primeros 200 chars):\n{codigoAMover[:200]}")
                    return False

                # --- Leer o preparar Destino ---
                contenidoDestino = ""
                if os.path.exists(destinoAbs):
                    with open(destinoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoDestino = f.read()
                else:
                    # Asegurar directorio destino si el archivo no existe
                    os.makedirs(os.path.dirname(destinoAbs), exist_ok=True)
                    log.info(f"{logPrefix} Archivo destino '{destinoRel}' no existe, se creará.")

                # --- Añadir código al Destino (al final, con separadores) ---
                contenidoDestinoModificado = contenidoDestino.rstrip() + "\n\n" + codigoAMover.strip() + "\n"

                # --- Eliminar código del Origen (reemplazo simple) ---
                contenidoOrigenModificado = contenidoOrigen.replace(codigoAMover, "", 1) # Reemplazar solo la primera ocurrencia

                if contenidoOrigenModificado == contenidoOrigen:
                    log.error(f"{logPrefix} ¡ERROR INESPERADO! El código se encontró pero el replace() no modificó el origen {origenRel}. Revisar código y contenido.")
                    return False

                # --- Escribir ambos archivos ---
                with open(destinoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoDestinoModificado)
                log.info(f"{logPrefix} Código añadido a {destinoRel}")

                with open(origenAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoOrigenModificado)
                log.info(f"{logPrefix} Código eliminado de {origenRel}")

                log.info(f"{logPrefix} Acción 'mover_codigo' completada exitosamente.")
                return True

            except Exception as e:
                log.error(f"{logPrefix} Error durante la acción 'mover_codigo' ({origenRel} -> {destinoRel}): {e}", exc_info=True)
                return False
        # <<< FIN: Acción mover_codigo >>>

        # ... (Resto de acciones: mover_archivo, crear_archivo, eliminar_archivo, crear_directorio - sin cambios) ...
        elif tipoAccion == "mover_archivo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")

            origenAbs = _validar_y_normalizar_ruta(origenRel, rutaBaseNorm, asegurar_existencia=True)
            if not origenAbs: return False
            destinoAbs = _validar_y_normalizar_ruta(destinoRel, rutaBaseNorm, asegurar_existencia=False)
            if not destinoAbs: return False

            if not os.path.isfile(origenAbs):
                 log.error(f"{logPrefix} El origen a mover no es un archivo: {origenAbs}")
                 return False
            if os.path.exists(destinoAbs):
                log.error(f"{logPrefix} Archivo destino ya existe, no se sobrescribirá: {destinoAbs} (rel: {destinoRel})")
                return False

            log.info(f"{logPrefix} Moviendo archivo de '{origenRel}' a '{destinoRel}'")
            try:
                os.makedirs(os.path.dirname(destinoAbs), exist_ok=True)
                shutil.move(origenAbs, destinoAbs)
                log.info(f"{logPrefix} Archivo movido exitosamente.")
                return True
            except Exception as e:
                 log.error(f"{logPrefix} Error al mover archivo {origenRel} a {destinoRel}: {e}")
                 return False

        elif tipoAccion == "crear_archivo":
            archivoRel = detalles.get("archivo")
            contenido = detalles.get("contenido", "")

            archivoAbs = _validar_y_normalizar_ruta(archivoRel, rutaBaseNorm, asegurar_existencia=False)
            if not archivoAbs: return False

            if not isinstance(contenido, str):
                 log.error(f"{logPrefix} El 'contenido' para crear_archivo debe ser una cadena.")
                 return False
            if os.path.exists(archivoAbs):
                 log.error(f"{logPrefix} Archivo a crear ya existe: {archivoAbs} (rel: {archivoRel})")
                 return False

            log.info(f"{logPrefix} Creando archivo: {archivoRel}")
            try:
                os.makedirs(os.path.dirname(archivoAbs), exist_ok=True)
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                log.info(f"{logPrefix} Archivo creado exitosamente.")
                return True
            except Exception as e:
                log.error(f"{logPrefix} Error al crear archivo {archivoRel}: {e}")
                return False

        elif tipoAccion == "eliminar_archivo":
            archivoRel = detalles.get("archivo")
            archivoAbs = _validar_y_normalizar_ruta(archivoRel, rutaBaseNorm, asegurar_existencia=False)
            if not archivoAbs: return False

            log.info(f"{logPrefix} Eliminando archivo: {archivoRel}")
            if not os.path.exists(archivoAbs):
                log.warning(f"{logPrefix} Archivo a eliminar no encontrado (¿ya borrado?): {archivoAbs} (rel: {archivoRel})")
                return True
            if not os.path.isfile(archivoAbs):
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
            dirAbs = _validar_y_normalizar_ruta(dirRel, rutaBaseNorm, asegurar_existencia=False)
            if not dirAbs: return False

            log.info(f"{logPrefix} Creando directorio: {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs):
                     log.warning(f"{logPrefix} El directorio a crear ya existe: {dirAbs} (rel: {dirRel})")
                     return True
                else:
                     log.error(f"{logPrefix} Existe un archivo con el mismo nombre que el directorio a crear: {dirAbs}")
                     return False

            try:
                os.makedirs(dirAbs, exist_ok=True)
                log.info(f"{logPrefix} Directorio creado exitosamente (o ya existía).")
                return True
            except Exception as e:
                log.error(f"{logPrefix} Error al crear directorio {dirRel}: {e}")
                return False

        elif tipoAccion == "no_accion":
            log.info(f"{logPrefix} Acción 'no_accion' recibida. No se aplican cambios.")
            return True

        else:
            log.error(f"{logPrefix} Tipo de acción NO SOPORTADO encontrado: '{tipoAccion}'. Acción completa: {accion}")
            return False

    except Exception as e:
        log.error(f"{logPrefix} Error INESPERADO aplicando acción '{tipoAccion}' en {rutaBaseNorm}: {e}", exc_info=True)
        return False