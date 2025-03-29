# nucleo/aplicadorCambios.py
import os
import logging
import shutil

log = logging.getLogger(__name__)

# Helper para validar rutas y evitar salida de la base
# (No necesita cambiar su retorno, el error se genera en el llamador)


def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    logPrefix = "_validar_y_normalizar_ruta:"
    if not rutaRelativa or not isinstance(rutaRelativa, str) or '..' in rutaRelativa.split(os.sep):
        log.error(
            f"{logPrefix} Ruta relativa inválida o sospechosa: '{rutaRelativa}'")
        return None
    rutaAbs = os.path.normpath(os.path.join(rutaBase, rutaRelativa))
    if not rutaAbs.startswith(os.path.normpath(rutaBase) + os.sep) and rutaAbs != os.path.normpath(rutaBase):
        log.error(
            f"{logPrefix} Ruta calculada '{rutaAbs}' intenta salir de la base '{rutaBase}' (originó de '{rutaRelativa}')")
        return None
    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.error(
            f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (originó de '{rutaRelativa}')")
        return None
    return rutaAbs

# *** MODIFIED FUNCTION SIGNATURE AND RETURN VALUES ***


def aplicarCambio(accion, rutaBase):
    """
    Aplica la acción de refactorización descrita en 'accion' dentro de 'rutaBase'.
    Devuelve:
        (True, None) si se aplicó con éxito.
        (False, "Mensaje de error") si falló.
    """
    logPrefix = "aplicarCambio:"

    tipoAccion = accion.get("accion")
    detalles = accion.get("detalles", {})
    descripcionLog = accion.get("descripcion", "Descripción no proporcionada")

    if not tipoAccion:
        err_msg = f"Acción inválida: falta 'accion'. Data: {accion}"
        log.error(f"{logPrefix} {err_msg}")
        return False, err_msg
    if not isinstance(detalles, dict):
        err_msg = f"Acción inválida: 'detalles' no es un dict. Data: {accion}"
        log.error(f"{logPrefix} {err_msg}")
        return False, err_msg

    log.info(
        f"{logPrefix} Intentando aplicar acción '{tipoAccion}': {descripcionLog}")
    rutaBaseNorm = os.path.normpath(rutaBase)

    try:
        if tipoAccion == "modificar_archivo":
            archivoRel = detalles.get("archivo")
            archivoAbs = _validar_y_normalizar_ruta(
                archivoRel, rutaBaseNorm, asegurar_existencia=True)
            if not archivoAbs:
                err_msg = f"Ruta de archivo inválida o no encontrada: '{archivoRel}'"
                # El helper ya logueó detalles, pero retornamos mensaje aquí
                return False, err_msg

            codigoNuevo = detalles.get("codigo_nuevo")
            buscar = detalles.get("buscar")
            reemplazar = detalles.get("reemplazar")  # Permitir None o vacío

            if not os.path.isfile(archivoAbs):
                err_msg = f"La ruta para modificar no es un archivo: {archivoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            if isinstance(codigoNuevo, str):
                log.warning(
                    f"{logPrefix} Modificando archivo [REEMPLAZO TOTAL]: {archivoRel}")
                try:
                    with open(archivoAbs, 'w', encoding='utf-8') as f:
                        f.write(codigoNuevo)
                    log.info(
                        f"{logPrefix} Archivo sobrescrito exitosamente: {archivoRel}")
                    return True, None  # Success
                except Exception as e:
                    err_msg = f"Error al sobrescribir archivo {archivoRel}: {e}"
                    log.error(f"{logPrefix} {err_msg}")
                    return False, err_msg

            elif isinstance(buscar, str) and reemplazar is not None:
                log.info(
                    f"{logPrefix} Modificando archivo [buscar/reemplazar]: {archivoRel}")
                try:
                    with open(archivoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoOriginal = f.read()

                    # --- CORRECCIÓN ---
                    # Especificar '1' para reemplazar solo la primera ocurrencia
                    contenidoModificado = contenidoOriginal.replace(
                        buscar, reemplazar, 1)
                    # --- FIN CORRECCIÓN ---

                    if contenidoModificado == contenidoOriginal:
                        # Añadir un log más detallado aquí podría ser útil
                        err_msg = f"Texto a buscar no encontrado o la primera ocurrencia ya coincidía con el reemplazo en {archivoRel}. Revisar 'buscar': '{buscar[:100]}...'"
                        # Podríamos verificar si había más de una ocurrencia originalmente
                        num_ocurrencias_originales = contenidoOriginal.count(
                            buscar)
                        if num_ocurrencias_originales > 0:
                            err_msg += f" (Nota: Se encontraron {num_ocurrencias_originales} ocurrencias en total)."
                        log.error(f"{logPrefix} {err_msg}")
                        return False, err_msg
                    else:
                        # Podríamos añadir un log si se detectaron múltiples ocurrencias originalmente
                        num_ocurrencias_originales = contenidoOriginal.count(
                            buscar)
                        if num_ocurrencias_originales > 1:
                            log.warning(
                                f"{logPrefix} Se encontró el texto a buscar múltiples veces ({num_ocurrencias_originales}) en {archivoRel}, pero solo se reemplazó la primera instancia.")

                        with open(archivoAbs, 'w', encoding='utf-8') as f:
                            f.write(contenidoModificado)
                        log.info(
                            f"{logPrefix} Archivo modificado exitosamente (primera ocurrencia reemplazada): {archivoRel}")
                        return True, None
                except Exception as e:
                    err_msg = f"Error durante buscar/reemplazar (primera ocurrencia) en {archivoRel}: {e}"
                    log.error(f"{logPrefix} {err_msg}")
                    return False, err_msg
            else:
                err_msg = f"Detalles insuficientes o inválidos para modificar_archivo. Se requiere 'codigo_nuevo' o ('buscar' y 'reemplazar'). Detalles: {detalles}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

        elif tipoAccion == "mover_codigo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")
            codigoAMover = detalles.get("codigo_a_mover")

            if not isinstance(origenRel, str) or not isinstance(destinoRel, str) or not isinstance(codigoAMover, str):
                err_msg = f"Faltan o son inválidos 'archivo_origen', 'archivo_destino' o 'codigo_a_mover' para mover_codigo."
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg
            if not codigoAMover:
                err_msg = f"El 'codigo_a_mover' no puede estar vacío."
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            origenAbs = _validar_y_normalizar_ruta(
                origenRel, rutaBaseNorm, asegurar_existencia=True)
            if not origenAbs:
                return False, f"Archivo origen inválido o no encontrado: '{origenRel}'"
            destinoAbs = _validar_y_normalizar_ruta(
                destinoRel, rutaBaseNorm, asegurar_existencia=False)
            if not destinoAbs:
                return False, f"Ruta destino inválida: '{destinoRel}'"

            if not os.path.isfile(origenAbs):
                err_msg = f"El origen para mover_codigo no es un archivo: {origenAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg
            if os.path.exists(destinoAbs) and not os.path.isfile(destinoAbs):
                err_msg = f"El destino para mover_codigo existe pero no es un archivo: {destinoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            log.info(
                f"{logPrefix} Moviendo código de '{origenRel}' a '{destinoRel}'")

            try:
                with open(origenAbs, 'r', encoding='utf-8', errors='ignore') as f:
                    contenidoOrigen = f.read()

                if codigoAMover not in contenidoOrigen:
                    err_msg = f"El 'codigo_a_mover' NO SE ENCONTRÓ textualmente en {origenRel}."
                    log.error(f"{logPrefix} {err_msg}")
                    log.debug(
                        f"{logPrefix} Código buscado (primeros 200 chars):\n{codigoAMover[:200]}")
                    return False, err_msg

                contenidoDestino = ""
                if os.path.exists(destinoAbs):
                    with open(destinoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoDestino = f.read()
                else:
                    os.makedirs(os.path.dirname(destinoAbs), exist_ok=True)
                    log.info(
                        f"{logPrefix} Archivo destino '{destinoRel}' no existe, se creará.")

                contenidoDestinoModificado = contenidoDestino.rstrip() + "\n\n" + \
                    codigoAMover.strip() + "\n"
                contenidoOrigenModificado = contenidoOrigen.replace(
                    codigoAMover, "", 1)

                if contenidoOrigenModificado == contenidoOrigen:
                    # This should theoretically not happen if `codigoAMover in contenidoOrigen` was true,
                    # unless there are weird encoding/whitespace issues. Treat as error.
                    err_msg = f"¡ERROR INESPERADO! El código se encontró pero replace() no modificó el origen {origenRel}. Verificar código y contenido."
                    log.error(f"{logPrefix} {err_msg}")
                    return False, err_msg

                with open(destinoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoDestinoModificado)
                log.info(f"{logPrefix} Código añadido a {destinoRel}")

                with open(origenAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoOrigenModificado)
                log.info(f"{logPrefix} Código eliminado de {origenRel}")

                log.info(
                    f"{logPrefix} Acción 'mover_codigo' completada exitosamente.")
                return True, None  # Success

            except Exception as e:
                err_msg = f"Error durante la acción 'mover_codigo' ({origenRel} -> {destinoRel}): {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True)
                return False, err_msg

        elif tipoAccion == "mover_archivo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")

            origenAbs = _validar_y_normalizar_ruta(
                origenRel, rutaBaseNorm, asegurar_existencia=True)
            if not origenAbs:
                return False, f"Archivo origen inválido o no encontrado: '{origenRel}'"
            destinoAbs = _validar_y_normalizar_ruta(
                destinoRel, rutaBaseNorm, asegurar_existencia=False)
            if not destinoAbs:
                return False, f"Ruta destino inválida: '{destinoRel}'"

            if not os.path.isfile(origenAbs):
                err_msg = f"El origen a mover no es un archivo: {origenAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg
            if os.path.exists(destinoAbs):
                err_msg = f"Archivo destino ya existe, no se sobrescribirá: {destinoAbs} (rel: {destinoRel})"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            log.info(
                f"{logPrefix} Moviendo archivo de '{origenRel}' a '{destinoRel}'")
            try:
                os.makedirs(os.path.dirname(destinoAbs), exist_ok=True)
                shutil.move(origenAbs, destinoAbs)
                log.info(f"{logPrefix} Archivo movido exitosamente.")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al mover archivo {origenRel} a {destinoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

        elif tipoAccion == "crear_archivo":
            archivoRel = detalles.get("archivo")
            contenido = detalles.get("contenido", "")

            archivoAbs = _validar_y_normalizar_ruta(
                archivoRel, rutaBaseNorm, asegurar_existencia=False)
            if not archivoAbs:
                return False, f"Ruta de archivo inválida: '{archivoRel}'"

            if not isinstance(contenido, str):
                err_msg = f"El 'contenido' para crear_archivo debe ser una cadena."
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg
            if os.path.exists(archivoAbs):
                err_msg = f"Archivo a crear ya existe: {archivoAbs} (rel: {archivoRel})"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            log.info(f"{logPrefix} Creando archivo: {archivoRel}")
            try:
                os.makedirs(os.path.dirname(archivoAbs), exist_ok=True)
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                log.info(f"{logPrefix} Archivo creado exitosamente.")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al crear archivo {archivoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

        elif tipoAccion == "eliminar_archivo":
            archivoRel = detalles.get("archivo")
            archivoAbs = _validar_y_normalizar_ruta(
                archivoRel, rutaBaseNorm, asegurar_existencia=False)
            # No fallar si la validación inicial falla, pero sí si no existe al intentar borrar
            if not archivoAbs:
                return False, f"Ruta de archivo inválida: '{archivoRel}'"

            log.info(f"{logPrefix} Eliminando archivo: {archivoRel}")
            if not os.path.exists(archivoAbs):
                # Considerar esto éxito si el objetivo es que no exista
                log.warning(
                    f"{logPrefix} Archivo a eliminar no encontrado (¿ya borrado?): {archivoAbs} (rel: {archivoRel}). Considerando éxito.")
                return True, None
            if not os.path.isfile(archivoAbs):
                err_msg = f"La ruta a eliminar no es un archivo: {archivoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            try:
                os.remove(archivoAbs)
                log.info(f"{logPrefix} Archivo eliminado exitosamente.")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al eliminar archivo {archivoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

        elif tipoAccion == "crear_directorio":
            dirRel = detalles.get("directorio")
            dirAbs = _validar_y_normalizar_ruta(
                dirRel, rutaBaseNorm, asegurar_existencia=False)
            if not dirAbs:
                return False, f"Ruta de directorio inválida: '{dirRel}'"

            log.info(f"{logPrefix} Creando directorio: {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs):
                    log.warning(
                        f"{logPrefix} El directorio a crear ya existe: {dirAbs} (rel: {dirRel}). Considerando éxito.")
                    return True, None  # Success (already exists)
                else:
                    err_msg = f"Existe un archivo con el mismo nombre que el directorio a crear: {dirAbs}"
                    log.error(f"{logPrefix} {err_msg}")
                    return False, err_msg

            try:
                # exist_ok=True handles race conditions slightly better
                os.makedirs(dirAbs, exist_ok=True)
                log.info(
                    f"{logPrefix} Directorio creado exitosamente (o ya existía).")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al crear directorio {dirRel}: {e}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

        elif tipoAccion == "no_accion":
            log.info(
                f"{logPrefix} Acción 'no_accion' recibida. No se aplican cambios.")
            # Consider 'no_accion' a success in terms of applying the suggestion (which was to do nothing)
            # But it shouldn't lead to a commit or history entry other than maybe debug logs.
            # The caller (principal.py) should handle this.
            # For consistency, return True, None.
            return True, None  # Success (no action needed)

        else:
            err_msg = f"Tipo de acción NO SOPORTADO encontrado: '{tipoAccion}'. Acción completa: {accion}"
            log.error(f"{logPrefix} {err_msg}")
            return False, err_msg

    except Exception as e:
        err_msg = f"Error INESPERADO aplicando acción '{tipoAccion}' en {rutaBaseNorm}: {e}"
        log.error(f"{logPrefix} {err_msg}", exc_info=True)
        return False, err_msg
