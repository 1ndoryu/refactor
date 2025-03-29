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
    # Normalizar ruta base y relativa antes de unir para mayor robustez
    rutaBaseNorm = os.path.normpath(rutaBase)
    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    # Asegurarse de que la ruta relativa normalizada no empiece con separadores o '..'
    if rutaRelativaNorm.startswith(('..', os.sep, '/')):
        # Eliminar separadores iniciales si existen después de normalizar
         rutaRelativaNorm = rutaRelativaNorm.lstrip(os.sep).lstrip('/')

    # Unir la ruta base normalizada con la relativa normalizada
    rutaAbs = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    # Normalizar el resultado final
    rutaAbs = os.path.normpath(rutaAbs)

    # Verificar que la ruta absoluta resultante esté dentro de la ruta base
    if not rutaAbs.startswith(rutaBaseNorm + os.sep) and rutaAbs != rutaBaseNorm:
        log.error(
            f"{logPrefix} Ruta calculada '{rutaAbs}' intenta salir de la base '{rutaBaseNorm}' (originó de '{rutaRelativa}')")
        return None
    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.error(
            f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (originó de '{rutaRelativa}')")
        return None
    return rutaAbs


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
                # El helper ya loguea el error específico
                err_msg = f"Ruta de archivo inválida o no encontrada: '{archivoRel}'"
                return False, err_msg

            codigoNuevo = detalles.get("codigo_nuevo")
            buscar = detalles.get("buscar")
            reemplazar = detalles.get("reemplazar")  # Permitir None o vacío

            if not os.path.isfile(archivoAbs):
                err_msg = f"La ruta para modificar no es un archivo: {archivoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            # --- INICIO LOGGING ADICIONAL ---
            # Loguear detalles ANTES de intentar la modificación
            log.debug(f"{logPrefix} Detalles recibidos para modificar_archivo:")
            log.debug(f"  Archivo Relativo: {archivoRel}")
            log.debug(f"  Archivo Absoluto: {archivoAbs}")
            if isinstance(buscar, str):
                # Loguear 'buscar' truncado y su representación para ver caracteres especiales/espacios
                log.debug(f"  Buscar (len={len(buscar)}): '{buscar[:500]}{'...' if len(buscar)>500 else ''}'")
                log.debug(f"  Buscar (repr): {repr(buscar[:500])}{'...' if len(buscar)>500 else ''}")
            else:
                log.debug(f"  Buscar: NO PROPORCIONADO o no es string ({type(buscar)})")

            if reemplazar is not None:
                # Loguear 'reemplazar' truncado y su representación
                log.debug(f"  Reemplazar (len={len(reemplazar)}): '{reemplazar[:500]}{'...' if len(reemplazar)>500 else ''}'")
                log.debug(f"  Reemplazar (repr): {repr(reemplazar[:500])}{'...' if len(reemplazar)>500 else ''}")
            else:
                 log.debug(f"  Reemplazar: NO PROPORCIONADO (será None)")

            if isinstance(codigoNuevo, str):
                 log.debug(f"  CodigoNuevo: SÍ proporcionado (len={len(codigoNuevo)})")
            else:
                 log.debug(f"  CodigoNuevo: NO proporcionado o no es string ({type(codigoNuevo)})")
            # --- FIN LOGGING ADICIONAL ---


            if isinstance(codigoNuevo, str):
                # Usar 'codigo_nuevo' para sobrescribir completamente
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
                    log.error(f"{logPrefix} {err_msg}", exc_info=True) # Añadir exc_info
                    return False, err_msg

            elif isinstance(buscar, str) and reemplazar is not None:
                # Usar 'buscar'/'reemplazar' para modificación específica
                log.info(
                    f"{logPrefix} Modificando archivo [buscar/reemplazar]: {archivoRel}")
                try:
                    # Leer contenido original
                    with open(archivoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoOriginal = f.read()

                    # --- INICIO VERIFICACIÓN PREVIA y LOGGING DE CONTEXTO ---
                    indice_encontrado = contenidoOriginal.find(buscar)

                    if indice_encontrado == -1:
                        log.warning(f"{logPrefix} VERIFICACIÓN PREVIA FALLIDA: El texto EXACTO de 'buscar' NO FUE ENCONTRADO en el contenido actual de '{archivoRel}'.")
                        # Intentar mostrar un snippet del archivo para ayudar al diagnóstico manual
                        try:
                             # Intentar encontrar una parte pequeña del inicio de 'buscar' para dar contexto
                             parte_buscar_contexto = buscar.strip()[:30] # Tomar los primeros 30 caracteres no vacíos
                             if parte_buscar_contexto:
                                 indice_contexto_aprox = contenidoOriginal.find(parte_buscar_contexto)
                                 if indice_contexto_aprox != -1:
                                     inicio_snippet = max(0, indice_contexto_aprox - 150)
                                     fin_snippet = min(len(contenidoOriginal), indice_contexto_aprox + len(parte_buscar_contexto) + 150)
                                     snippet = contenidoOriginal[inicio_snippet:fin_snippet]
                                     log.warning(f"{logPrefix} Snippet del archivo cerca de donde podría estar '{parte_buscar_contexto}' (aproximado):\n---\n{snippet}\n---")
                                 else:
                                     log.warning(f"{logPrefix} No se pudo encontrar ni siquiera la parte inicial ('{parte_buscar_contexto}...') de 'buscar' para mostrar contexto en el archivo.")
                             else:
                                 log.warning(f"{logPrefix} 'buscar' parece estar vacío o solo contener espacios, no se buscó contexto.")
                        except Exception as e_snippet:
                             log.error(f"{logPrefix} Error intentando obtener snippet de contexto del archivo: {e_snippet}")
                    else:
                        # Si se encontró, loguearlo antes de intentar el replace
                        log.info(f"{logPrefix} VERIFICACIÓN PREVIA OK: El texto EXACTO de 'buscar' FUE ENCONTRADO en el índice {indice_encontrado} de '{archivoRel}'. Procediendo con replace().")
                    # --- FIN VERIFICACIÓN PREVIA y LOGGING DE CONTEXTO ---


                    # Intentar reemplazar SOLO la primera ocurrencia
                    contenidoModificado = contenidoOriginal.replace(
                        buscar, reemplazar, 1)

                    # Verificar si el contenido realmente cambió
                    if contenidoModificado == contenidoOriginal:
                        # Si la verificación previa falló, este es el resultado esperado.
                        # Si la verificación previa tuvo éxito, significa que buscar == reemplazar,
                        # o hubo algún problema muy raro con el replace.
                        estado_verificacion = 'falló' if indice_encontrado == -1 else 'tuvo éxito pero replace no alteró el contenido'
                        err_msg = f"Texto a buscar no encontrado (verif. previa {estado_verificacion}) o la primera ocurrencia ya coincidía con el reemplazo en {archivoRel}. Revisar 'buscar': '{buscar[:100]}...'"

                        # Añadir contexto sobre ocurrencias totales y si buscar == reemplazar
                        num_ocurrencias_originales = contenidoOriginal.count(buscar)
                        if num_ocurrencias_originales > 0:
                             err_msg += f" (Nota: Se encontraron {num_ocurrencias_originales} ocurrencias en total en el archivo)."
                             if buscar == reemplazar:
                                 err_msg += " Además, 'buscar' y 'reemplazar' son idénticos."

                        log.error(f"{logPrefix} {err_msg}")
                        return False, err_msg # Fallo porque no hubo cambio efectivo o el texto no estaba
                    else:
                        # El contenido cambió, escribirlo de vuelta
                        # Loguear si había múltiples ocurrencias pero solo se cambió la primera
                        num_ocurrencias_originales = contenidoOriginal.count(buscar)
                        if num_ocurrencias_originales > 1:
                            log.warning(
                                f"{logPrefix} Se encontró el texto a buscar múltiples veces ({num_ocurrencias_originales}) en {archivoRel}, pero solo se reemplazó la primera instancia como se solicitó.")

                        with open(archivoAbs, 'w', encoding='utf-8') as f:
                            f.write(contenidoModificado)
                        log.info(
                            f"{logPrefix} Archivo modificado exitosamente (primera ocurrencia reemplazada): {archivoRel}")
                        return True, None # Success
                except Exception as e:
                    err_msg = f"Error durante buscar/reemplazar (primera ocurrencia) en {archivoRel}: {e}"
                    log.error(f"{logPrefix} {err_msg}", exc_info=True) # Añadir exc_info
                    return False, err_msg
            else:
                # Caso donde ni 'codigo_nuevo' ni ('buscar' y 'reemplazar') válidos fueron proporcionados
                err_msg = f"Detalles insuficientes o inválidos para modificar_archivo. Se requiere 'codigo_nuevo' o ('buscar' y 'reemplazar' válidos). Detalles recibidos: {detalles}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

        elif tipoAccion == "mover_codigo":
            # --- mover_codigo ---
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")
            codigoAMover = detalles.get("codigo_a_mover")

            if not isinstance(origenRel, str) or not isinstance(destinoRel, str) or not isinstance(codigoAMover, str):
                err_msg = f"Faltan o son inválidos 'archivo_origen', 'archivo_destino' o 'codigo_a_mover' para mover_codigo."
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg
            if not codigoAMover: # El código a mover no puede estar vacío
                err_msg = f"El 'codigo_a_mover' no puede estar vacío."
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            origenAbs = _validar_y_normalizar_ruta(
                origenRel, rutaBaseNorm, asegurar_existencia=True)
            if not origenAbs:
                return False, f"Archivo origen inválido o no encontrado: '{origenRel}'"
            destinoAbs = _validar_y_normalizar_ruta(
                destinoRel, rutaBaseNorm, asegurar_existencia=False) # Destino puede no existir aún
            if not destinoAbs:
                return False, f"Ruta destino inválida: '{destinoRel}'"

            if not os.path.isfile(origenAbs):
                err_msg = f"El origen para mover_codigo no es un archivo: {origenAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg
            # Si el destino existe, debe ser un archivo (para añadirle contenido)
            if os.path.exists(destinoAbs) and not os.path.isfile(destinoAbs):
                err_msg = f"El destino para mover_codigo existe pero no es un archivo: {destinoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            log.info(
                f"{logPrefix} Moviendo código de '{origenRel}' a '{destinoRel}'")
            log.debug(f"{logPrefix} Código a mover (primeros 200 chars):\n{codigoAMover[:200]}{'...' if len(codigoAMover)>200 else ''}")

            try:
                # Leer origen
                with open(origenAbs, 'r', encoding='utf-8', errors='ignore') as f:
                    contenidoOrigen = f.read()

                # Verificar si el código a mover existe EXACTAMENTE en el origen
                if codigoAMover not in contenidoOrigen:
                    # --- LOGGING MEJORADO PARA 'codigoAMover' NO ENCONTRADO ---
                    err_msg = f"El 'codigo_a_mover' NO SE ENCONTRÓ textualmente en el archivo origen '{origenRel}'."
                    log.error(f"{logPrefix} {err_msg}")
                    log.debug(f"{logPrefix} Código buscado (repr, primeros 200): {repr(codigoAMover[:200])}{'...' if len(codigoAMover)>200 else ''}")
                    # Intentar mostrar snippet del origen donde podría estar
                    try:
                         parte_codigo_contexto = codigoAMover.strip()[:30]
                         if parte_codigo_contexto:
                             indice_contexto_aprox = contenidoOrigen.find(parte_codigo_contexto)
                             if indice_contexto_aprox != -1:
                                 inicio_snippet = max(0, indice_contexto_aprox - 150)
                                 fin_snippet = min(len(contenidoOrigen), indice_contexto_aprox + len(parte_codigo_contexto) + 150)
                                 snippet = contenidoOrigen[inicio_snippet:fin_snippet]
                                 log.warning(f"{logPrefix} Snippet del archivo origen cerca de '{parte_codigo_contexto}' (aprox):\n---\n{snippet}\n---")
                             else:
                                 log.warning(f"{logPrefix} No se pudo encontrar la parte inicial ('{parte_codigo_contexto}...') de 'codigo_a_mover' en el archivo origen.")
                         else:
                             log.warning(f"{logPrefix} 'codigo_a_mover' vacío o solo espacios, no se buscó contexto.")
                    except Exception as e_snippet_mv:
                         log.error(f"{logPrefix} Error intentando obtener snippet de contexto del archivo origen: {e_snippet_mv}")
                    # --- FIN LOGGING MEJORADO ---
                    return False, err_msg

                # Leer destino (si existe) o preparar para crear
                contenidoDestino = ""
                if os.path.exists(destinoAbs):
                    with open(destinoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoDestino = f.read()
                else:
                    # Asegurarse de que el directorio padre del destino exista
                    os.makedirs(os.path.dirname(destinoAbs), exist_ok=True)
                    log.info(
                        f"{logPrefix} Archivo destino '{destinoRel}' no existe, se creará.")

                # Preparar nuevo contenido para el destino (añadir al final con separador)
                # Usar strip() en codigoAMover para evitar dobles saltos de línea si ya los tiene
                contenidoDestinoModificado = contenidoDestino.rstrip() + "\n\n" + \
                    codigoAMover.strip() + "\n"

                # Preparar nuevo contenido para el origen (eliminar primera ocurrencia)
                contenidoOrigenModificado = contenidoOrigen.replace(
                    codigoAMover, "", 1)

                # Doble check: si no cambió, algo fue mal (no debería pasar si 'in' fue True)
                if contenidoOrigenModificado == contenidoOrigen:
                    err_msg = f"¡ERROR INESPERADO! 'codigo_a_mover' se encontró pero replace() no modificó el origen '{origenRel}'. Verificar codificación o caracteres extraños."
                    log.error(f"{logPrefix} {err_msg}")
                    return False, err_msg

                # Escribir cambios
                with open(destinoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoDestinoModificado)
                log.info(f"{logPrefix} Código añadido al archivo destino: {destinoRel}")

                with open(origenAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoOrigenModificado)
                log.info(f"{logPrefix} Código eliminado del archivo origen: {origenRel}")

                log.info(
                    f"{logPrefix} Acción 'mover_codigo' completada exitosamente.")
                return True, None  # Success

            except Exception as e:
                err_msg = f"Error durante la acción 'mover_codigo' ({origenRel} -> {destinoRel}): {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True) # Añadir exc_info
                return False, err_msg

        elif tipoAccion == "mover_archivo":
            # --- mover_archivo ---
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")

            if not isinstance(origenRel, str) or not isinstance(destinoRel, str):
                 err_msg = f"Faltan o son inválidos 'archivo_origen' o 'archivo_destino' para mover_archivo."
                 log.error(f"{logPrefix} {err_msg}")
                 return False, err_msg

            origenAbs = _validar_y_normalizar_ruta(
                origenRel, rutaBaseNorm, asegurar_existencia=True)
            if not origenAbs:
                return False, f"Archivo origen inválido o no encontrado: '{origenRel}'"
            destinoAbs = _validar_y_normalizar_ruta(
                destinoRel, rutaBaseNorm, asegurar_existencia=False) # Destino no debe existir
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
                # Crear directorio padre del destino si no existe
                os.makedirs(os.path.dirname(destinoAbs), exist_ok=True)
                shutil.move(origenAbs, destinoAbs)
                log.info(f"{logPrefix} Archivo movido exitosamente.")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al mover archivo {origenRel} a {destinoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True) # Añadir exc_info
                return False, err_msg

        elif tipoAccion == "crear_archivo":
            # --- crear_archivo ---
            archivoRel = detalles.get("archivo")
            contenido = detalles.get("contenido", "") # Contenido es opcional, por defecto vacío

            if not isinstance(archivoRel, str):
                 err_msg = f"Falta o es inválido 'archivo' para crear_archivo."
                 log.error(f"{logPrefix} {err_msg}")
                 return False, err_msg

            archivoAbs = _validar_y_normalizar_ruta(
                archivoRel, rutaBaseNorm, asegurar_existencia=False) # No debe existir
            if not archivoAbs:
                return False, f"Ruta de archivo inválida: '{archivoRel}'"

            if not isinstance(contenido, str):
                # Forzar contenido a string si no lo es (aunque no debería pasar con JSON)
                log.warning(f"{logPrefix} El 'contenido' para crear_archivo no era string ({type(contenido)}), se convertirá.")
                contenido = str(contenido)

            if os.path.exists(archivoAbs):
                err_msg = f"Archivo a crear ya existe: {archivoAbs} (rel: {archivoRel})"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            log.info(f"{logPrefix} Creando archivo: {archivoRel}")
            try:
                 # Crear directorio padre si no existe
                os.makedirs(os.path.dirname(archivoAbs), exist_ok=True)
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                log.info(f"{logPrefix} Archivo creado exitosamente.")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al crear archivo {archivoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True) # Añadir exc_info
                return False, err_msg

        elif tipoAccion == "eliminar_archivo":
            # --- eliminar_archivo ---
            archivoRel = detalles.get("archivo")

            if not isinstance(archivoRel, str):
                 err_msg = f"Falta o es inválido 'archivo' para eliminar_archivo."
                 log.error(f"{logPrefix} {err_msg}")
                 return False, err_msg

            archivoAbs = _validar_y_normalizar_ruta(
                archivoRel, rutaBaseNorm, asegurar_existencia=False) # No asegurar existencia aquí
            # Si la ruta es inválida (sale de base), fallar
            if not archivoAbs:
                return False, f"Ruta de archivo inválida: '{archivoRel}'"

            log.info(f"{logPrefix} Eliminando archivo: {archivoRel}")
            # Verificar existencia ANTES de intentar borrar
            if not os.path.exists(archivoAbs):
                # Si el objetivo es eliminarlo y ya no existe, considerar éxito.
                log.warning(
                    f"{logPrefix} Archivo a eliminar no encontrado: {archivoAbs} (rel: {archivoRel}). Considerando la acción exitosa.")
                return True, None # Success (already done)
            if not os.path.isfile(archivoAbs):
                # Si existe pero no es un archivo, es un error.
                err_msg = f"La ruta a eliminar existe pero no es un archivo: {archivoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                return False, err_msg

            try:
                os.remove(archivoAbs)
                log.info(f"{logPrefix} Archivo eliminado exitosamente.")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al eliminar archivo {archivoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True) # Añadir exc_info
                return False, err_msg

        elif tipoAccion == "crear_directorio":
            # --- crear_directorio ---
            dirRel = detalles.get("directorio")

            if not isinstance(dirRel, str):
                 err_msg = f"Falta o es inválido 'directorio' para crear_directorio."
                 log.error(f"{logPrefix} {err_msg}")
                 return False, err_msg

            dirAbs = _validar_y_normalizar_ruta(
                dirRel, rutaBaseNorm, asegurar_existencia=False) # No debe existir (o ser dir)
            if not dirAbs:
                return False, f"Ruta de directorio inválida: '{dirRel}'"

            log.info(f"{logPrefix} Creando directorio: {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs):
                    # Si ya existe COMO directorio, considerar éxito.
                    log.warning(
                        f"{logPrefix} El directorio a crear ya existe: {dirAbs} (rel: {dirRel}). Considerando éxito.")
                    return True, None  # Success (already exists)
                else:
                    # Si existe pero NO es directorio, es un error.
                    err_msg = f"Existe un archivo con el mismo nombre que el directorio a crear: {dirAbs}"
                    log.error(f"{logPrefix} {err_msg}")
                    return False, err_msg

            try:
                # exist_ok=True previene errores si se crea entre el check y la llamada (race condition)
                # y también maneja el caso de que ya exista como directorio.
                os.makedirs(dirAbs, exist_ok=True)
                log.info(
                    f"{logPrefix} Directorio creado exitosamente (o ya existía).")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al crear directorio {dirRel}: {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True) # Añadir exc_info
                return False, err_msg

        elif tipoAccion == "no_accion":
            # --- no_accion ---
            log.info(
                f"{logPrefix} Acción 'no_accion' recibida. No se aplican cambios.")
            # El flujo principal debe manejar esto, pero para esta función, no hacer nada es "éxito".
            return True, None  # Success (no action needed)

        else:
            # --- Acción desconocida ---
            err_msg = f"Tipo de acción NO SOPORTADO encontrado: '{tipoAccion}'. Acción completa: {accion}"
            log.error(f"{logPrefix} {err_msg}")
            return False, err_msg

    except Exception as e:
        # --- Error inesperado general ---
        err_msg = f"Error INESPERADO aplicando acción '{tipoAccion}' en {rutaBaseNorm}: {e}"
        log.error(f"{logPrefix} {err_msg}", exc_info=True) # Añadir exc_info para tracebacks completos
        return False, err_msg