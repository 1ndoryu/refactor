# nucleo/aplicadorCambios.py
import os
import logging
import shutil

log = logging.getLogger(__name__)

def aplicarCambio(accionJson, rutaBase):
    prefijoLog = "aplicarCambio:"

    tipoAccion = accionJson.get("accion")
    detalles = accionJson.get("detalles", {})
    descripcionLog = accionJson.get("descripcion", "Descripción no proporcionada")

    if not tipoAccion:
        log.error(f"{prefijoLog} Acción inválida: falta 'accion'. Data: {accionJson}")
        return False
    if not isinstance(detalles, dict):
         log.error(f"{prefijoLog} Acción inválida: 'detalles' no es un diccionario. Data: {accionJson}")
         return False

    log.info(f"{prefijoLog} Intentando aplicar acción '{tipoAccion}': {descripcionLog}")

    # --- Normalizar rutaBase para comparaciones seguras ---
    rutaBaseNormalizada = os.path.normpath(os.path.abspath(rutaBase))

    def esRutaSegura(rutaRelativa):
        """Verifica que la ruta absoluta resultante esté dentro de rutaBase."""
        if not rutaRelativa or not isinstance(rutaRelativa, str) or '..' in rutaRelativa:
            return None # Ruta inválida o sospechosa
        rutaAbsoluta = os.path.normpath(os.path.join(rutaBaseNormalizada, rutaRelativa))
        if not rutaAbsoluta.startswith(rutaBaseNormalizada):
            log.error(f"{prefijoLog} ¡Peligro! Intento de acceso fuera de la ruta base: '{rutaRelativa}'")
            return None
        return rutaAbsoluta

    try:
        if tipoAccion == "modificar_archivo":
            archivoRel = detalles.get("archivo")
            archivoAbs = esRutaSegura(archivoRel)
            if not archivoAbs:
                log.error(f"{prefijoLog} Ruta de archivo inválida o insegura para modificar: '{archivoRel}'")
                return False

            codigoNuevo = detalles.get("codigo_nuevo")
            buscar = detalles.get("buscar")
            reemplazar = detalles.get("reemplazar") # Permitido ser cadena vacía

            if not os.path.exists(archivoAbs):
                log.error(f"{prefijoLog} Archivo a modificar no encontrado: {archivoAbs} (rel: {archivoRel})")
                return False
            if not os.path.isfile(archivoAbs):
                log.error(f"{prefijoLog} La ruta a modificar no es un archivo: {archivoAbs}")
                return False

            if isinstance(codigoNuevo, str):
                log.warning(f"{prefijoLog} Modificando archivo (REEMPLAZO TOTAL): {archivoRel}")
                try:
                    with open(archivoAbs, 'w', encoding='utf-8') as f:
                        f.write(codigoNuevo)
                    log.info(f"{prefijoLog} Archivo sobrescrito exitosamente: {archivoRel}")
                    return True
                except Exception as e:
                    log.error(f"{prefijoLog} Error al sobrescribir archivo {archivoRel}: {e}")
                    return False

            elif isinstance(buscar, str) and reemplazar is not None: # reemplazar puede ser ""
                log.info(f"{prefijoLog} Modificando archivo (buscar/reemplazar): {archivoRel}")
                try:
                    with open(archivoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                        contenidoOriginal = f.read()

                    if buscar not in contenidoOriginal:
                         log.warning(f"{prefijoLog} Texto a buscar no encontrado en {archivoRel}. Puede ser un error de la IA o cambio ya aplicado. Revisar 'buscar': '{buscar[:100]}...'")
                         # Devolver True para no bloquear, pero advertir.
                         return True

                    contenidoModificado = contenidoOriginal.replace(buscar, reemplazar)

                    # Verificar si realmente cambió algo (importante si buscar == reemplazar)
                    if contenidoModificado == contenidoOriginal:
                        log.warning(f"{prefijoLog} El reemplazo no modificó el contenido en {archivoRel}. ¿Buscar y reemplazar son idénticos?")
                        return True # No fallar si no hubo cambio real

                    with open(archivoAbs, 'w', encoding='utf-8') as f:
                         f.write(contenidoModificado)
                    log.info(f"{prefijoLog} Archivo modificado exitosamente (buscar/reemplazar): {archivoRel}")
                    return True
                except Exception as e:
                    log.error(f"{prefijoLog} Error durante buscar/reemplazar en {archivoRel}: {e}")
                    return False
            else:
                log.error(f"{prefijoLog} Detalles insuficientes/inválidos para modificar_archivo. Se requiere 'codigo_nuevo' o ('buscar' y 'reemplazar'). Detalles: {detalles}")
                return False

        elif tipoAccion == "mover_archivo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")
            origenAbs = esRutaSegura(origenRel)
            destinoAbs = esRutaSegura(destinoRel)

            if not origenAbs or not destinoAbs:
                log.error(f"{prefijoLog} Ruta origen ('{origenRel}') o destino ('{destinoRel}') inválida/insegura para mover.")
                return False
            if not os.path.exists(origenAbs):
                log.error(f"{prefijoLog} Archivo origen no encontrado para mover: {origenAbs} (rel: {origenRel})")
                return False
            if not os.path.isfile(origenAbs):
                 log.error(f"{prefijoLog} Origen para mover no es un archivo: {origenAbs}")
                 return False
            if os.path.exists(destinoAbs):
                log.error(f"{prefijoLog} Archivo destino ya existe, no se sobrescribirá: {destinoAbs} (rel: {destinoRel})")
                return False

            log.info(f"{prefijoLog} Moviendo archivo de '{origenRel}' a '{destinoRel}'")
            try:
                os.makedirs(os.path.dirname(destinoAbs), exist_ok=True)
                shutil.move(origenAbs, destinoAbs)
                log.info(f"{prefijoLog} Archivo movido exitosamente.")
                return True
            except Exception as e:
                 log.error(f"{prefijoLog} Error al mover archivo {origenRel} a {destinoRel}: {e}")
                 return False

        elif tipoAccion == "crear_archivo":
            archivoRel = detalles.get("archivo")
            contenido = detalles.get("contenido", "") # Default a "" si no se provee
            archivoAbs = esRutaSegura(archivoRel)

            if not archivoAbs:
                 log.error(f"{prefijoLog} Ruta de archivo inválida/insegura para crear: '{archivoRel}'")
                 return False
            if not isinstance(contenido, str):
                 log.error(f"{prefijoLog} El 'contenido' para crear_archivo debe ser texto. Tipo: {type(contenido)}")
                 return False
            if os.path.exists(archivoAbs):
                 log.error(f"{prefijoLog} Archivo a crear ya existe: {archivoAbs} (rel: {archivoRel})")
                 return False

            log.info(f"{prefijoLog} Creando archivo: {archivoRel}")
            try:
                os.makedirs(os.path.dirname(archivoAbs), exist_ok=True)
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                log.info(f"{prefijoLog} Archivo creado exitosamente.")
                return True
            except Exception as e:
                log.error(f"{prefijoLog} Error al crear archivo {archivoRel}: {e}")
                return False

        elif tipoAccion == "eliminar_archivo":
            archivoRel = detalles.get("archivo")
            archivoAbs = esRutaSegura(archivoRel)
            if not archivoAbs:
                log.error(f"{prefijoLog} Ruta de archivo inválida/insegura para eliminar: '{archivoRel}'")
                return False

            log.info(f"{prefijoLog} Eliminando archivo: {archivoRel}")
            if not os.path.exists(archivoAbs):
                log.warning(f"{prefijoLog} Archivo a eliminar no encontrado (quizás ya borrado?): {archivoAbs}")
                return True # Considerar éxito si ya no existe
            if not os.path.isfile(archivoAbs):
                 log.error(f"{prefijoLog} La ruta a eliminar no es un archivo: {archivoAbs}")
                 return False

            try:
                os.remove(archivoAbs)
                log.info(f"{prefijoLog} Archivo eliminado exitosamente.")
                return True
            except Exception as e:
                log.error(f"{prefijoLog} Error al eliminar archivo {archivoRel}: {e}")
                return False

        elif tipoAccion == "crear_directorio":
            dirRel = detalles.get("directorio")
            dirAbs = esRutaSegura(dirRel)
            if not dirAbs:
                 log.error(f"{prefijoLog} Ruta de directorio inválida/insegura para crear: '{dirRel}'")
                 return False

            log.info(f"{prefijoLog} Creando directorio: {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs):
                     log.warning(f"{prefijoLog} Directorio a crear ya existe: {dirAbs}")
                     return True
                else:
                     log.error(f"{prefijoLog} Existe un archivo con el mismo nombre que el directorio a crear: {dirAbs}")
                     return False

            try:
                os.makedirs(dirAbs, exist_ok=True)
                log.info(f"{prefijoLog} Directorio creado exitosamente (o ya existía).")
                return True
            except Exception as e:
                log.error(f"{prefijoLog} Error al crear directorio {dirRel}: {e}")
                return False

        # --- NUEVA ACCIÓN: mover_codigo ---
        elif tipoAccion == "mover_codigo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")
            codigoAMover = detalles.get("codigo_a_mover")
            codigoAEliminar = detalles.get("codigo_a_eliminar") # Usar este para borrar

            origenAbs = esRutaSegura(origenRel)
            destinoAbs = esRutaSegura(destinoRel)

            if not origenAbs or not destinoAbs:
                 log.error(f"{prefijoLog} Ruta origen ('{origenRel}') o destino ('{destinoRel}') inválida/insegura para mover_codigo.")
                 return False
            if not codigoAMover or not isinstance(codigoAMover, str) or not codigoAEliminar or not isinstance(codigoAEliminar, str):
                 log.error(f"{prefijoLog} Falta 'codigo_a_mover' o 'codigo_a_eliminar' (deben ser texto) para mover_codigo.")
                 return False
            if not os.path.isfile(origenAbs):
                log.error(f"{prefijoLog} Archivo origen para mover_codigo no es un archivo válido: {origenAbs}")
                return False
            if not os.path.isfile(destinoAbs):
                 log.error(f"{prefijoLog} Archivo destino para mover_codigo no es un archivo válido: {destinoAbs}")
                 return False

            log.info(f"{prefijoLog} Moviendo código de '{origenRel}' a '{destinoRel}'")

            try:
                # 1. Leer ambos archivos y verificar condiciones
                with open(origenAbs, 'r', encoding='utf-8', errors='ignore') as f:
                    contenidoOrigen = f.read()
                with open(destinoAbs, 'r', encoding='utf-8', errors='ignore') as f:
                    contenidoDestino = f.read()

                if codigoAEliminar not in contenidoOrigen:
                    log.error(f"{prefijoLog} 'codigo_a_eliminar' NO encontrado en {origenRel}. Abortando.")
                    log.debug(f"{prefijoLog} Código a eliminar esperado:\n{codigoAEliminar[:200]}...")
                    return False
                if codigoAMover in contenidoDestino:
                     log.warning(f"{prefijoLog} 'codigo_a_mover' YA existe en {destinoRel}. ¿Duplicado? Se procederá a eliminar de origen igualmente.")
                     # No fallamos aquí, pero advertimos. Podríamos fallar si la duplicación es inaceptable.

                # 2. Añadir código al destino (al final por simplicidad)
                # Añadir saltos de línea para separar bien el código movido
                codigoDestinoModificado = contenidoDestino.rstrip() + "\n\n" + codigoAMover.strip() + "\n"
                with open(destinoAbs, 'w', encoding='utf-8') as f:
                    f.write(codigoDestinoModificado)
                log.info(f"{prefijoLog} Código añadido a {destinoRel}.")

                # 3. Eliminar código del origen (reemplazando solo la primera ocurrencia)
                contenidoOrigenModificado = contenidoOrigen.replace(codigoAEliminar, '', 1)

                # Verificar que el reemplazo realmente ocurrió
                if contenidoOrigenModificado == contenidoOrigen:
                     # Esto NO debería pasar si la comprobación inicial 'in' fue exitosa, pero doble chequeo
                     log.error(f"{prefijoLog} ¡FALLO INTERNO! Código a eliminar fue encontrado pero replace() no lo modificó en {origenRel}. ¿Caracteres especiales?")
                     # ¡POTENCIALMENTE DEJA CÓDIGO DUPLICADO! ¿Deshacer el paso 2? Complejo. Fallar aquí.
                     # Intentar revertir el destino sería lo ideal, pero por ahora fallamos
                     return False

                with open(origenAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoOrigenModificado)
                log.info(f"{prefijoLog} Código eliminado de {origenRel}.")

                log.info(f"{prefijoLog} Acción mover_codigo completada exitosamente.")
                return True

            except Exception as e:
                log.error(f"{prefijoLog} Error durante mover_codigo de {origenRel} a {destinoRel}: {e}")
                # Aquí podríamos intentar revertir cambios si fuera posible, pero es complejo.
                return False


        elif tipoAccion == "no_accion":
            log.info(f"{prefijoLog} Acción 'no_accion' recibida. No se aplican cambios.")
            return True # No es un fallo

        else:
            log.error(f"{prefijoLog} Tipo de acción no soportado: '{tipoAccion}'. Acción completa: {accionJson}")
            return False

    except Exception as e:
        # Captura errores inesperados en la lógica de esta función (ej. permisos)
        log.error(f"{prefijoLog} Error inesperado aplicando acción '{tipoAccion}' en {rutaBase}: {e}", exc_info=True)
        return False