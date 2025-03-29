# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import codecs  # Para decodificar escapes unicode
# Importar settings para poder guardar logs de debug en la base del proyecto
from config import settings

# Obtener el logger configurado en principal.py
log = logging.getLogger(__name__)

# --- Helper para rutas (sin cambios, solo añadir logging debug) ---


def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    logPrefix = "_validar_y_normalizar_ruta:"
    log.debug(f"{logPrefix} Validando rutaRelativa='{rutaRelativa}', rutaBase='{rutaBase}', asegurar_existencia={asegurar_existencia}")

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
    if not rutaRelativaNorm:  # Si quedó vacía después de lstrip
        log.error(
            f"{logPrefix} Ruta relativa resultó vacía después de normalizar/limpiar: original='{rutaRelativa}'")
        return None

    # Unir la ruta base normalizada con la relativa normalizada
    rutaAbs = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    # Normalizar el resultado final
    rutaAbs = os.path.normpath(rutaAbs)

    # Verificar que la ruta absoluta resultante esté dentro de la ruta base
    # Comprobar startswith con el separador para evitar falsos positivos (ej: /base/abc vs /base/a)
    if not rutaAbs.startswith(rutaBaseNorm + os.sep) and rutaAbs != rutaBaseNorm:
        log.error(
            f"{logPrefix} Ruta calculada '{rutaAbs}' intenta salir de la base '{rutaBaseNorm}' (originó de '{rutaRelativa}')")
        return None
    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.error(
            f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (originó de '{rutaRelativa}')")
        return None

    log.debug(f"{logPrefix} Ruta validada y normalizada a: '{rutaAbs}'")
    return rutaAbs


# --- Función principal para aplicar cambios ---
def aplicarCambio(accion, rutaBase):
    """
    Aplica la acción de refactorización descrita en 'accion' dentro de 'rutaBase'.
    Devuelve:
        (True, None) si se aplicó con éxito.
        (False, "Mensaje de error") si falló.
    """
    logPrefix = "aplicarCambio:"

    # --- Logging Inicial Detallado ---
    log.debug(f"{logPrefix} === INICIO APLICACIÓN CAMBIO ===")
    # Loguear toda la acción
    log.debug(f"{logPrefix} Acción recibida (raw): {accion}")

    tipoAccion = accion.get("accion")
    detalles = accion.get("detalles", {})
    descripcionLog = accion.get("descripcion", "Descripción no proporcionada")
    razonamientoLog = accion.get(
        "razonamiento", "Razonamiento no proporcionado")  # Loguear también

    if not tipoAccion:
        err_msg = f"Acción inválida: falta 'accion'. Data: {accion}"
        log.error(f"{logPrefix} {err_msg}")
        log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
        return False, err_msg
    if not isinstance(detalles, dict):
        err_msg = f"Acción inválida: 'detalles' no es un dict. Data: {accion}"
        log.error(f"{logPrefix} {err_msg}")
        log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
        return False, err_msg

    log.info(
        f"{logPrefix} Intentando aplicar acción '{tipoAccion}': {descripcionLog}")
    log.debug(f"{logPrefix} Razonamiento para la acción: {razonamientoLog}")
    # Loguear detalles específicos
    log.debug(f"{logPrefix} Detalles recibidos: {detalles}")

    rutaBaseNorm = os.path.normpath(rutaBase)
    log.debug(f"{logPrefix} Ruta base normalizada: {rutaBaseNorm}")

    try:
        # ==================================
        # ===   modificar_archivo        ===
        # ==================================
        if tipoAccion == "modificar_archivo":
            archivoRel = detalles.get("archivo")
            archivoAbs = _validar_y_normalizar_ruta(
                archivoRel, rutaBaseNorm, asegurar_existencia=True)  # Asegurar que existe
            if not archivoAbs:
                # El helper ya loguea el error específico
                err_msg = f"Ruta de archivo inválida o no encontrada: '{archivoRel}'"
                # No necesita log.error aquí, ya lo hizo el helper
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            codigoNuevo = detalles.get("codigo_nuevo")
            buscar = detalles.get("buscar")
            reemplazar = detalles.get("reemplazar")  # Permitir None o vacío

            if not os.path.isfile(archivoAbs):
                err_msg = f"La ruta para modificar no es un archivo: {archivoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            # --- Loguear parámetros específicos de esta acción ---
            log.debug(f"{logPrefix} -> Parametros 'modificar_archivo':")
            log.debug(f"{logPrefix}    archivoRel: '{archivoRel}'")
            log.debug(f"{logPrefix}    archivoAbs: '{archivoAbs}'")
            if isinstance(codigoNuevo, str):
                log.debug(
                    f"{logPrefix}    codigoNuevo: (Presente, len={len(codigoNuevo)})")
                log.debug(
                    f"{logPrefix}    codigoNuevo (primeros 200): {codigoNuevo[:200]}{'...' if len(codigoNuevo) > 200 else ''}")
            else:
                log.debug(
                    f"{logPrefix}    codigoNuevo: No proporcionado o no es string (tipo: {type(codigoNuevo)})")
            if isinstance(buscar, str):
                log.debug(
                    f"{logPrefix}    buscar: (Presente, len={len(buscar)})")
                log.debug(
                    f"{logPrefix}    buscar (repr, primeros 200): {repr(buscar[:200])}{'...' if len(buscar) > 200 else ''}")
            else:
                log.debug(
                    f"{logPrefix}    buscar: No proporcionado o no es string (tipo: {type(buscar)})")
            if reemplazar is not None:
                log.debug(
                    f"{logPrefix}    reemplazar: (Presente, len={len(reemplazar)})")
                log.debug(
                    f"{logPrefix}    reemplazar (repr, primeros 200): {repr(reemplazar[:200])}{'...' if len(reemplazar) > 200 else ''}")
            else:
                log.debug(
                    f"{logPrefix}    reemplazar: No proporcionado (None)")

            # --- Lógica de Modificación ---
            if isinstance(codigoNuevo, str):
                # Usar 'codigo_nuevo' para sobrescribir completamente
                log.info(
                    f"{logPrefix} Modificando archivo [REEMPLAZO TOTAL]: {archivoRel}")
                try:
                    with open(archivoAbs, 'w', encoding='utf-8') as f:
                        f.write(codigoNuevo)
                    log.info(
                        f"{logPrefix} Archivo sobrescrito exitosamente: {archivoRel}")
                    log.debug(
                        f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO) ===")
                    return True, None  # Success
                except Exception as e:
                    err_msg = f"Error al sobrescribir archivo {archivoRel}: {e}"
                    # exc_info para traceback
                    log.error(f"{logPrefix} {err_msg}", exc_info=True)
                    log.debug(
                        f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                    return False, err_msg

            elif isinstance(buscar, str) and reemplazar is not None:
                # Usar 'buscar'/'reemplazar' para modificación específica (primera ocurrencia)
                log.info(
                    f"{logPrefix} Modificando archivo [buscar/reemplazar - 1ra ocurrencia]: {archivoRel}")
                contenidoOriginal = None  # Inicializar
                try:
                    # Leer contenido original
                    log.debug(
                        f"{logPrefix} Leyendo contenido original de: {archivoAbs}")
                    with open(archivoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoOriginal = f.read()
                    log.debug(
                        f"{logPrefix} Lectura de contenido original completada (len={len(contenidoOriginal)}).")

                    # --- VERIFICACIÓN PREVIA y LOGGING DE CONTEXTO ---
                    log.debug(
                        f"{logPrefix} Buscando EXACTAMENTE (repr): {repr(buscar)}")
                    indice_encontrado = contenidoOriginal.find(buscar)

                    if indice_encontrado == -1:
                        # --- ¡NO ENCONTRADO! Loguear extensamente ---
                        err_msg = f"Texto EXACTO a buscar no fue encontrado en el archivo '{archivoRel}'. Operación abortada."
                        log.error(f"{logPrefix} {err_msg}")
                        log.error(
                            f"{logPrefix} Texto buscado (repr, completo): {repr(buscar)}")

                        # --- Guardar en archivos de debug ---
                        try:
                            base_debug_path = os.path.join(
                                settings.RUTA_BASE_PROYECTO, "debug_logs")
                            os.makedirs(base_debug_path, exist_ok=True)
                            # Crear nombres de archivo únicos o descriptivos
                            filename_safe = "".join(
                                c if c.isalnum() else "_" for c in archivoRel)
                            path_buscado = os.path.join(
                                base_debug_path, f"modificar_buscar_{filename_safe}.txt")
                            path_contenido = os.path.join(
                                base_debug_path, f"modificar_contenido_{filename_safe}.txt")

                            with open(path_buscado, "w", encoding="utf-8") as f_search:
                                f_search.write(
                                    "--- TEXTO BUSCADO (repr) ---\n")
                                f_search.write(repr(buscar))
                                f_search.write(
                                    "\n\n--- TEXTO BUSCADO (literal) ---\n")
                                f_search.write(buscar)
                            with open(path_contenido, "w", encoding="utf-8") as f_content:
                                f_content.write(contenidoOriginal)

                            log.warning(
                                f"{logPrefix} Contexto de debug guardado en:")
                            log.warning(
                                f"{logPrefix}   - Texto buscado: {path_buscado}")
                            log.warning(
                                f"{logPrefix}   - Contenido archivo: {path_contenido}")
                        except Exception as e_dbg:
                            log.error(
                                f"{logPrefix} No se pudo guardar el contexto de debug: {e_dbg}", exc_info=True)
                        # --- Fin Guardar Debug ---

                        log.debug(
                            f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                        return False, err_msg
                    else:
                        # Si se encontró, loguearlo antes de intentar el replace
                        log.info(
                            f"{logPrefix} Texto EXACTO de 'buscar' encontrado en índice {indice_encontrado} de '{archivoRel}'. Procediendo con replace().")

                    # Intentar reemplazar SOLO la primera ocurrencia
                    log.debug(
                        f"{logPrefix} Ejecutando contenidoOriginal.replace(buscar, reemplazar, 1)")
                    contenidoModificado = contenidoOriginal.replace(
                        buscar, reemplazar, 1)

                    # Verificar si el contenido realmente cambió
                    if contenidoModificado == contenidoOriginal:
                        # Esto significa que buscar == reemplazar, o algún problema raro.
                        err_msg_detail = f"La operación replace() no modificó el contenido en '{archivoRel}'."
                        num_ocurrencias = contenidoOriginal.count(buscar)
                        if buscar == reemplazar:
                            err_msg_detail += " Causa probable: El texto a buscar y el de reemplazo son idénticos."
                        err_msg_detail += f" (Ocurrencias totales de 'buscar': {num_ocurrencias}). Revisar 'buscar' y 'reemplazar'."
                        log.error(f"{logPrefix} {err_msg_detail}")
                        log.error(f"{logPrefix} Buscar (repr): {repr(buscar)}")
                        log.error(
                            f"{logPrefix} Reemplazar (repr): {repr(reemplazar)}")
                        log.debug(
                            f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                        return False, err_msg_detail  # Fallo porque no hubo cambio efectivo

                    else:
                        # El contenido cambió, escribirlo de vuelta
                        log.info(
                            f"{logPrefix} El contenido fue modificado. Intentando escribir en: {archivoAbs}")
                        num_ocurrencias_originales = contenidoOriginal.count(
                            buscar)
                        if num_ocurrencias_originales > 1:
                            log.warning(
                                f"{logPrefix} Se encontraron {num_ocurrencias_originales} ocurrencias del texto a buscar en {archivoRel}, pero solo se reemplazó la primera instancia como se solicitó.")

                        with open(archivoAbs, 'w', encoding='utf-8') as f:
                            f.write(contenidoModificado)
                        log.info(
                            f"{logPrefix} Archivo modificado exitosamente (primera ocurrencia reemplazada): {archivoRel}")
                        log.debug(
                            f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO) ===")
                        return True, None  # Success
                except Exception as e:
                    # Captura errores de lectura o escritura
                    err_msg = f"Error durante buscar/reemplazar (primera ocurrencia) en {archivoRel}: {e}"
                    log.error(f"{logPrefix} {err_msg}", exc_info=True)
                    if contenidoOriginal is None:
                        log.error(
                            f"{logPrefix} El error ocurrió probablemente durante la LECTURA inicial del archivo.")
                    else:
                        log.error(
                            f"{logPrefix} El error ocurrió probablemente durante la ESCRITURA del archivo modificado.")
                    log.debug(
                        f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                    return False, err_msg
            else:
                # Caso donde ni 'codigo_nuevo' ni ('buscar' y 'reemplazar') válidos fueron proporcionados
                err_msg = f"Detalles insuficientes o inválidos para modificar_archivo. Se requiere 'codigo_nuevo' o ('buscar' y 'reemplazar' válidos)."
                log.error(
                    f"{logPrefix} {err_msg} Detalles recibidos: {detalles}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

        # ==================================
        # ===      mover_codigo          ===
        # ==================================
        elif tipoAccion == "mover_codigo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")
            # Original, puede tener escapes
            codigoAMover = detalles.get("codigo_a_mover")

            # --- Validación de Parámetros ---
            if not isinstance(origenRel, str) or not isinstance(destinoRel, str) or not isinstance(codigoAMover, str):
                err_msg = f"Faltan o son inválidos 'archivo_origen', 'archivo_destino' o 'codigo_a_mover' para mover_codigo."
                log.error(f"{logPrefix} {err_msg}")
                log.debug(
                    f"{logPrefix}   Origen: {type(origenRel)}, Destino: {type(destinoRel)}, Codigo: {type(codigoAMover)}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg
            if not codigoAMover:  # El código a mover no puede estar vacío
                err_msg = f"El 'codigo_a_mover' no puede estar vacío."
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            # --- Loguear parámetros ---
            log.debug(f"{logPrefix} -> Parametros 'mover_codigo':")
            log.debug(f"{logPrefix}    origenRel: '{origenRel}'")
            log.debug(f"{logPrefix}    destinoRel: '{destinoRel}'")
            log.debug(
                f"{logPrefix}    codigoAMover (original, len={len(codigoAMover)})")
            log.debug(
                f"{logPrefix}    codigoAMover (repr, primeros 200): {repr(codigoAMover[:200])}{'...' if len(codigoAMover) > 200 else ''}")

            # --- Decodificar Escapes Unicode ---
            # Usar una nueva variable para el código que realmente se buscará/moverá
            codigo_a_buscar_y_reemplazar = codigoAMover  # Usar la original por defecto
            try:
                codigoAMoverDecoded = codecs.decode(
                    codigoAMover, 'unicode_escape')
                if codigoAMoverDecoded != codigoAMover:
                    log.info(
                        f"{logPrefix} Decodificando secuencias de escape Unicode en 'codigo_a_mover'.")
                    log.debug(
                        f"{logPrefix}    Original (repr, primeros 200): {repr(codigoAMover[:200])}{'...' if len(codigoAMover) > 200 else ''}")
                    # <--- ACTUALIZAR variable a usar
                    codigo_a_buscar_y_reemplazar = codigoAMoverDecoded
                    log.debug(
                        f"{logPrefix}    Decodificado (repr, primeros 200): {repr(codigo_a_buscar_y_reemplazar[:200])}{'...' if len(codigo_a_buscar_y_reemplazar) > 200 else ''}")
                else:
                    log.debug(
                        f"{logPrefix} No se detectaron secuencias de escape Unicode que requirieran decodificación.")
            except Exception as e_decode:
                # ¡Importante! Si falla la decodificación, seguir con el original pero advertir.
                log.warning(
                    f"{logPrefix} Falló el intento de decodificar secuencias Unicode en 'codigo_a_mover': {e_decode}. Se usará el valor original.", exc_info=True)
            # A partir de aquí, SIEMPRE usar 'codigo_a_buscar_y_reemplazar' para buscar y reemplazar

            # --- Validar Rutas ---
            origenAbs = _validar_y_normalizar_ruta(
                origenRel, rutaBaseNorm, asegurar_existencia=True)  # Origen debe existir
            if not origenAbs:
                err_msg = f"Archivo origen inválido o no encontrado: '{origenRel}'"
                # log ya hecho por helper
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            destinoAbs = _validar_y_normalizar_ruta(
                destinoRel, rutaBaseNorm, asegurar_existencia=False)  # Destino puede no existir aún
            if not destinoAbs:
                err_msg = f"Ruta destino inválida: '{destinoRel}'"
                # log ya hecho por helper
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            log.debug(f"{logPrefix}    origenAbs: '{origenAbs}'")
            log.debug(f"{logPrefix}    destinoAbs: '{destinoAbs}'")

            # --- Validar Tipos de Archivo ---
            if not os.path.isfile(origenAbs):
                err_msg = f"El origen para mover_codigo no es un archivo: {origenAbs}"
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg
            # Si el destino existe, debe ser un archivo (para añadirle contenido)
            if os.path.exists(destinoAbs) and not os.path.isfile(destinoAbs):
                err_msg = f"El destino para mover_codigo existe pero no es un archivo: {destinoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            # --- Lógica de Mover Código ---
            log.info(
                f"{logPrefix} Moviendo código de '{origenRel}' a '{destinoRel}'")
            contenidoOrigen = None  # Inicializar
            contenidoDestino = ""  # Inicializar

            try:
                # 1. Leer origen
                log.debug(
                    f"{logPrefix} Leyendo contenido de origen: {origenAbs}")
                with open(origenAbs, 'r', encoding='utf-8', errors='ignore') as f:
                    contenidoOrigen = f.read()
                log.debug(
                    f"{logPrefix} Lectura de origen completada (len={len(contenidoOrigen)}).")

                # 2. Verificar si el código a mover existe EXACTAMENTE en el origen
                log.debug(
                    f"{logPrefix} Buscando código a mover (decodificado si aplica)...")
                log.debug(
                    f"{logPrefix}    Código buscado (repr, primeros 200): {repr(codigo_a_buscar_y_reemplazar[:200])}{'...' if len(codigo_a_buscar_y_reemplazar) > 200 else ''}")

                # --- ¡¡USA LA VARIABLE CORRECTA (potencialmente decodificada)!! ---
                if codigo_a_buscar_y_reemplazar not in contenidoOrigen:
                    # --- ¡NO ENCONTRADO! Loguear extensamente ---
                    err_msg = f"El 'codigo_a_mover' (después de decodificar escapes si hubo) NO SE ENCONTRÓ textualmente en el archivo origen '{origenRel}'."
                    log.error(f"{logPrefix} {err_msg}")
                    # Log completo en error
                    log.error(
                        f"{logPrefix} Código buscado (repr, completo): {repr(codigo_a_buscar_y_reemplazar)}")

                    # --- Guardar en archivos de debug ---
                    try:
                        base_debug_path = os.path.join(
                            settings.RUTA_BASE_PROYECTO, "debug_logs")
                        os.makedirs(base_debug_path, exist_ok=True)
                        filename_safe_orig = "".join(
                            c if c.isalnum() else "_" for c in origenRel)
                        path_codigo = os.path.join(
                            base_debug_path, f"mover_codigo_buscado_{filename_safe_orig}.txt")
                        path_contenido = os.path.join(
                            base_debug_path, f"mover_codigo_origen_contenido_{filename_safe_orig}.txt")

                        with open(path_codigo, "w", encoding="utf-8") as f_code:
                            f_code.write("--- CODIGO BUSCADO (repr) ---\n")
                            f_code.write(repr(codigo_a_buscar_y_reemplazar))
                            f_code.write(
                                "\n\n--- CODIGO BUSCADO (literal) ---\n")
                            f_code.write(codigo_a_buscar_y_reemplazar)
                        with open(path_contenido, "w", encoding="utf-8") as f_content:
                            f_content.write(contenidoOrigen)

                        log.warning(
                            f"{logPrefix} Contexto de debug guardado en:")
                        log.warning(
                            f"{logPrefix}   - Código buscado: {path_codigo}")
                        log.warning(
                            f"{logPrefix}   - Contenido origen: {path_contenido}")
                    except Exception as e_dbg:
                        log.error(
                            f"{logPrefix} No se pudo guardar el contexto de debug: {e_dbg}", exc_info=True)
                    # --- Fin Guardar Debug ---

                    log.debug(
                        f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                    return False, err_msg
                else:
                    log.info(
                        f"{logPrefix} Código a mover encontrado en archivo origen '{origenRel}'.")

                # 3. Leer destino (si existe) o preparar para crear
                if os.path.exists(destinoAbs):
                    log.debug(
                        f"{logPrefix} Leyendo contenido de destino existente: {destinoAbs}")
                    with open(destinoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoDestino = f.read()
                    log.debug(
                        f"{logPrefix} Lectura de destino completada (len={len(contenidoDestino)}).")
                else:
                    # Asegurarse de que el directorio padre del destino exista
                    log.debug(
                        f"{logPrefix} Archivo destino '{destinoRel}' no existe. Asegurando directorio padre: {os.path.dirname(destinoAbs)}")
                    os.makedirs(os.path.dirname(destinoAbs), exist_ok=True)
                    log.info(
                        f"{logPrefix} Archivo destino '{destinoRel}' no existía, se creará.")

                # 4. Preparar nuevo contenido para el destino (añadir al final con separador)
                # Usar strip() en codigoAMover para evitar dobles saltos de línea si ya los tiene
                # --- ¡¡USA LA VARIABLE CORRECTA!! ---
                codigoLimpioParaAnadir = codigo_a_buscar_y_reemplazar.strip()
                contenidoDestinoModificado = contenidoDestino.rstrip() + "\n\n" + \
                    codigoLimpioParaAnadir + "\n"
                log.debug(
                    f"{logPrefix} Contenido preparado para destino (len={len(contenidoDestinoModificado)}).")

                # 5. Preparar nuevo contenido para el origen (eliminar primera ocurrencia)
                # --- ¡¡USA LA VARIABLE CORRECTA!! ---
                log.debug(
                    f"{logPrefix} Preparando contenido de origen modificado (eliminando primera ocurrencia).")
                contenidoOrigenModificado = contenidoOrigen.replace(
                    codigo_a_buscar_y_reemplazar, "", 1)

                # 6. Doble check: si no cambió el origen, algo fue mal (no debería pasar si 'in' fue True)
                if contenidoOrigenModificado == contenidoOrigen:
                    # Esto es inesperado y probablemente un bug o problema de caracteres muy raro
                    err_msg = f"¡ERROR INESPERADO! 'codigo_a_mover' se encontró pero replace() no modificó el contenido del origen '{origenRel}'. Verificar codificación o caracteres extraños."
                    log.error(f"{logPrefix} {err_msg}")
                    log.error(
                        f"{logPrefix} Código buscado (repr): {repr(codigo_a_buscar_y_reemplazar)}")
                    log.debug(
                        f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                    return False, err_msg
                else:
                    log.debug(
                        f"{logPrefix} Contenido de origen modificado preparado (len={len(contenidoOrigenModificado)}).")
                    num_ocurrencias_origen = contenidoOrigen.count(
                        codigo_a_buscar_y_reemplazar)
                    if num_ocurrencias_origen > 1:
                        log.warning(
                            f"{logPrefix} Se encontraron {num_ocurrencias_origen} ocurrencias del código a mover en '{origenRel}', solo se eliminó la primera.")

                # 7. Escribir cambios (primero destino, luego origen)
                log.debug(
                    f"{logPrefix} Escribiendo contenido modificado en destino: {destinoAbs}")
                with open(destinoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoDestinoModificado)
                log.info(
                    f"{logPrefix} Código añadido al archivo destino: {destinoRel}")

                log.debug(
                    f"{logPrefix} Escribiendo contenido modificado en origen: {origenAbs}")
                with open(origenAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoOrigenModificado)
                log.info(
                    f"{logPrefix} Código eliminado del archivo origen: {origenRel}")

                log.info(
                    f"{logPrefix} Acción 'mover_codigo' completada exitosamente.")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO) ===")
                return True, None  # Success

            except Exception as e:
                # Captura errores de lectura, escritura, creación de directorio, etc.
                err_msg = f"Error durante la acción 'mover_codigo' ({origenRel} -> {destinoRel}): {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True)
                if contenidoOrigen is None:
                    log.error(
                        f"{logPrefix} El error ocurrió probablemente durante la LECTURA del origen o la preparación del destino.")
                # Podríamos añadir más lógica para saber si falló al escribir destino u origen
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

        # ==================================
        # ===      mover_archivo         ===
        # ==================================
        elif tipoAccion == "mover_archivo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")

            if not isinstance(origenRel, str) or not isinstance(destinoRel, str):
                err_msg = f"Faltan o son inválidos 'archivo_origen' o 'archivo_destino' para mover_archivo."
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            log.debug(f"{logPrefix} -> Parametros 'mover_archivo':")
            log.debug(f"{logPrefix}    origenRel: '{origenRel}'")
            log.debug(f"{logPrefix}    destinoRel: '{destinoRel}'")

            origenAbs = _validar_y_normalizar_ruta(
                origenRel, rutaBaseNorm, asegurar_existencia=True)  # Origen debe existir
            if not origenAbs:
                err_msg = f"Archivo origen inválido o no encontrado: '{origenRel}'"
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            destinoAbs = _validar_y_normalizar_ruta(
                destinoRel, rutaBaseNorm, asegurar_existencia=False)  # Destino no debe existir
            if not destinoAbs:
                err_msg = f"Ruta destino inválida: '{destinoRel}'"
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            log.debug(f"{logPrefix}    origenAbs: '{origenAbs}'")
            log.debug(f"{logPrefix}    destinoAbs: '{destinoAbs}'")

            if not os.path.isfile(origenAbs):
                err_msg = f"El origen a mover no es un archivo: {origenAbs}"
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg
            if os.path.exists(destinoAbs):
                err_msg = f"Archivo destino ya existe, no se sobrescribirá: {destinoAbs} (rel: {destinoRel})"
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            log.info(
                f"{logPrefix} Moviendo archivo de '{origenRel}' a '{destinoRel}'")
            try:
                # Crear directorio padre del destino si no existe
                destinoDirPadre = os.path.dirname(destinoAbs)
                log.debug(
                    f"{logPrefix} Asegurando directorio padre del destino: {destinoDirPadre}")
                os.makedirs(destinoDirPadre, exist_ok=True)

                log.debug(
                    f"{logPrefix} Ejecutando shutil.move('{origenAbs}', '{destinoAbs}')")
                shutil.move(origenAbs, destinoAbs)
                log.info(f"{logPrefix} Archivo movido exitosamente.")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO) ===")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al mover archivo {origenRel} a {destinoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True)
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

        # ==================================
        # ===      crear_archivo         ===
        # ==================================
        elif tipoAccion == "crear_archivo":
            archivoRel = detalles.get("archivo")
            # Contenido es opcional, por defecto vacío
            contenido = detalles.get("contenido", "")

            if not isinstance(archivoRel, str):
                err_msg = f"Falta o es inválido 'archivo' para crear_archivo."
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            log.debug(f"{logPrefix} -> Parametros 'crear_archivo':")
            log.debug(f"{logPrefix}    archivoRel: '{archivoRel}'")
            log.debug(f"{logPrefix}    contenido (tipo): {type(contenido)}")
            if isinstance(contenido, str):
                log.debug(f"{logPrefix}    contenido (len): {len(contenido)}")
                log.debug(
                    f"{logPrefix}    contenido (primeros 200): {contenido[:200]}{'...' if len(contenido) > 200 else ''}")
            else:
                log.warning(
                    f"{logPrefix} El 'contenido' para crear_archivo no era string, se convertirá.")
                contenido = str(contenido)  # Forzar a string

            archivoAbs = _validar_y_normalizar_ruta(
                archivoRel, rutaBaseNorm, asegurar_existencia=False)  # No debe existir
            if not archivoAbs:
                err_msg = f"Ruta de archivo inválida: '{archivoRel}'"
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg
            log.debug(f"{logPrefix}    archivoAbs: '{archivoAbs}'")

            if os.path.exists(archivoAbs):
                err_msg = f"Archivo a crear ya existe: {archivoAbs} (rel: {archivoRel})"
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            log.info(f"{logPrefix} Creando archivo: {archivoRel}")
            try:
                # Crear directorio padre si no existe
                archivoDirPadre = os.path.dirname(archivoAbs)
                log.debug(
                    f"{logPrefix} Asegurando directorio padre: {archivoDirPadre}")
                os.makedirs(archivoDirPadre, exist_ok=True)

                log.debug(
                    f"{logPrefix} Escribiendo contenido en: {archivoAbs}")
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                log.info(f"{logPrefix} Archivo creado exitosamente.")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO) ===")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al crear archivo {archivoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True)
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

        # ==================================
        # ===      eliminar_archivo      ===
        # ==================================
        elif tipoAccion == "eliminar_archivo":
            archivoRel = detalles.get("archivo")

            if not isinstance(archivoRel, str):
                err_msg = f"Falta o es inválido 'archivo' para eliminar_archivo."
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            log.debug(f"{logPrefix} -> Parametros 'eliminar_archivo':")
            log.debug(f"{logPrefix}    archivoRel: '{archivoRel}'")

            archivoAbs = _validar_y_normalizar_ruta(
                archivoRel, rutaBaseNorm, asegurar_existencia=False)  # No asegurar aquí
            # Si la ruta es inválida (sale de base), fallar
            if not archivoAbs:
                err_msg = f"Ruta de archivo inválida: '{archivoRel}'"
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg
            log.debug(f"{logPrefix}    archivoAbs: '{archivoAbs}'")

            log.info(f"{logPrefix} Eliminando archivo: {archivoRel}")
            # Verificar existencia ANTES de intentar borrar
            if not os.path.exists(archivoAbs):
                # Si el objetivo es eliminarlo y ya no existe, considerar éxito.
                log.warning(
                    f"{logPrefix} Archivo a eliminar no encontrado: {archivoAbs} (rel: {archivoRel}). Considerando la acción exitosa (ya no existe).")
                log.debug(
                    f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO - NO OP) ===")
                return True, None  # Success (already done)

            if not os.path.isfile(archivoAbs):
                # Si existe pero no es un archivo, es un error.
                err_msg = f"La ruta a eliminar existe pero no es un archivo: {archivoAbs}"
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            try:
                log.debug(f"{logPrefix} Ejecutando os.remove('{archivoAbs}')")
                os.remove(archivoAbs)
                log.info(f"{logPrefix} Archivo eliminado exitosamente.")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO) ===")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al eliminar archivo {archivoRel}: {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True)
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

        # ==================================
        # ===      crear_directorio      ===
        # ==================================
        elif tipoAccion == "crear_directorio":
            dirRel = detalles.get("directorio")

            if not isinstance(dirRel, str):
                err_msg = f"Falta o es inválido 'directorio' para crear_directorio."
                log.error(f"{logPrefix} {err_msg}")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

            log.debug(f"{logPrefix} -> Parametros 'crear_directorio':")
            log.debug(f"{logPrefix}    dirRel: '{dirRel}'")

            dirAbs = _validar_y_normalizar_ruta(
                # No debe existir (o ser dir)
                dirRel, rutaBaseNorm, asegurar_existencia=False)
            if not dirAbs:
                err_msg = f"Ruta de directorio inválida: '{dirRel}'"
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg
            log.debug(f"{logPrefix}    dirAbs: '{dirAbs}'")

            log.info(f"{logPrefix} Creando directorio: {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs):
                    # Si ya existe COMO directorio, considerar éxito.
                    log.warning(
                        f"{logPrefix} El directorio a crear ya existe: {dirAbs} (rel: {dirRel}). Considerando éxito.")
                    log.debug(
                        f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO - NO OP) ===")
                    return True, None  # Success (already exists)
                else:
                    # Si existe pero NO es directorio, es un error.
                    err_msg = f"Existe un archivo con el mismo nombre que el directorio a crear: {dirAbs}"
                    log.error(f"{logPrefix} {err_msg}")
                    log.debug(
                        f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                    return False, err_msg

            try:
                # exist_ok=True previene errores si se crea entre el check y la llamada (race condition)
                # y también maneja el caso de que ya exista como directorio.
                log.debug(
                    f"{logPrefix} Ejecutando os.makedirs('{dirAbs}', exist_ok=True)")
                os.makedirs(dirAbs, exist_ok=True)
                log.info(
                    f"{logPrefix} Directorio creado exitosamente (o ya existía).")
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO) ===")
                return True, None  # Success
            except Exception as e:
                err_msg = f"Error al crear directorio {dirRel}: {e}"
                log.error(f"{logPrefix} {err_msg}", exc_info=True)
                log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
                return False, err_msg

        # ==================================
        # ===         no_accion          ===
        # ==================================
        elif tipoAccion == "no_accion":
            log.info(
                f"{logPrefix} Acción 'no_accion' recibida. No se aplican cambios.")
            log.debug(
                f"{logPrefix} Razonamiento para 'no_accion': {razonamientoLog}")
            # El flujo principal debe manejar esto, pero para esta función, no hacer nada es "éxito".
            log.debug(
                f"{logPrefix} === FIN APLICACIÓN CAMBIO (ÉXITO - NO OP) ===")
            return True, None  # Success (no action needed)

        # ==================================
        # ===     Acción Desconocida     ===
        # ==================================
        else:
            err_msg = f"Tipo de acción NO SOPORTADO encontrado: '{tipoAccion}'. Acción completa: {accion}"
            log.error(f"{logPrefix} {err_msg}")
            log.debug(f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR) ===")
            return False, err_msg

    # ==================================
    # ===   Error General Inesperado ===
    # ==================================
    except Exception as e:
        err_msg = f"Error INESPERADO aplicando acción '{tipoAccion}' en {rutaBaseNorm}: {e}"
        # Usar CRITICAL aquí porque es un fallo no previsto en la lógica específica de cada acción
        # exc_info para tracebacks completos
        log.critical(f"{logPrefix} {err_msg}", exc_info=True)
        log.debug(
            f"{logPrefix} === FIN APLICACIÓN CAMBIO (ERROR INESPERADO) ===")
        return False, err_msg
