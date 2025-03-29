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
    descripcion = accion.get("descripcion", "Cambio desconocido")  # Para logs

    if not tipoAccion or not detalles:
        log.error(f"{logPrefix} Accion invalida o sin detalles: {accion}")
        return False

    log.info(f"{logPrefix} Aplicando accion '{tipoAccion}': {descripcion}")

    try:
        # --- Implementar lógica para cada tipo de acción ---

        if tipoAccion == "modificar_archivo":
            archivoRel = detalles.get("archivo")
            if not archivoRel:
                log.error(
                    f"{logPrefix} Falta 'archivo' en detalles para modificar_archivo.")
                return False
            archivoAbs = os.path.join(rutaBase, archivoRel)

            codigoNuevo = detalles.get("codigo_nuevo")
            buscar = detalles.get("buscar")
            reemplazar = detalles.get("reemplazar")

            if codigoNuevo is not None:
                # Opción 1: Reemplazar todo el contenido del archivo
                log.info(
                    f"{logPrefix} Modificando archivo (reemplazo total): {archivoRel}")
                # Asegurar que el dir existe
                os.makedirs(os.path.dirname(archivoAbs), exist_ok=True)
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(codigoNuevo)
                return True
            elif buscar is not None and reemplazar is not None:
                # Opción 2: Buscar y reemplazar
                log.info(
                    f"{logPrefix} Modificando archivo (buscar/reemplazar): {archivoRel}")
                if not os.path.exists(archivoAbs):
                    log.error(
                        f"{logPrefix} Archivo a modificar no encontrado: {archivoAbs}")
                    return False
                with open(archivoAbs, 'r', encoding='utf-8') as f:
                    contenidoOriginal = f.read()
                contenidoModificado = contenidoOriginal.replace(
                    buscar, reemplazar)
                if contenidoModificado == contenidoOriginal:
                    log.warning(
                        f"{logPrefix} El texto a buscar no se encontro en {archivoRel}. No se realizaron cambios.")
                    # Podríamos considerarlo éxito o fallo dependiendo del caso. Por ahora, éxito parcial.
                    return True  # O False si debe haber cambio sí o sí
                with open(archivoAbs, 'w', encoding='utf-8') as f:
                    f.write(contenidoModificado)
                return True
            # TODO: Añadir lógica para modificar por línea si se necesita (más complejo)
            else:
                log.error(
                    f"{logPrefix} Detalles insuficientes para modificar_archivo (falta codigo_nuevo o buscar/reemplazar).")
                return False

        elif tipoAccion == "mover_archivo":
            origenRel = detalles.get("archivo_origen")
            destinoRel = detalles.get("archivo_destino")
            if not origenRel or not destinoRel:
                log.error(
                    f"{logPrefix} Faltan 'archivo_origen' o 'archivo_destino' para mover_archivo.")
                return False
            origenAbs = os.path.join(rutaBase, origenRel)
            destinoAbs = os.path.join(rutaBase, destinoRel)
            log.info(
                f"{logPrefix} Moviendo archivo de {origenRel} a {destinoRel}")
            if not os.path.exists(origenAbs):
                log.error(
                    f"{logPrefix} Archivo origen no encontrado: {origenAbs}")
                return False
            os.makedirs(os.path.dirname(destinoAbs),
                        exist_ok=True)  # Asegurar dir destino
            shutil.move(origenAbs, destinoAbs)
            return True

        elif tipoAccion == "crear_archivo":
            archivoRel = detalles.get("archivo")
            # Contenido por defecto vacío
            contenido = detalles.get("contenido", "")
            if not archivoRel:
                log.error(
                    f"{logPrefix} Falta 'archivo' en detalles para crear_archivo.")
                return False
            archivoAbs = os.path.join(rutaBase, archivoRel)
            log.info(f"{logPrefix} Creando archivo: {archivoRel}")
            os.makedirs(os.path.dirname(archivoAbs),
                        exist_ok=True)  # Asegurar dir
            with open(archivoAbs, 'w', encoding='utf-8') as f:
                f.write(contenido)
            return True

        elif tipoAccion == "eliminar_archivo":
            archivoRel = detalles.get("archivo")
            if not archivoRel:
                log.error(
                    f"{logPrefix} Falta 'archivo' en detalles para eliminar_archivo.")
                return False
            archivoAbs = os.path.join(rutaBase, archivoRel)
            log.info(f"{logPrefix} Eliminando archivo: {archivoRel}")
            if not os.path.exists(archivoAbs):
                log.warning(
                    f"{logPrefix} Archivo a eliminar no encontrado (quizás ya borrado?): {archivoAbs}")
                return True  # Considerar éxito si ya no existe
            os.remove(archivoAbs)
            return True

        elif tipoAccion == "crear_directorio":
            dirRel = detalles.get("directorio")
            if not dirRel:
                log.error(
                    f"{logPrefix} Falta 'directorio' en detalles para crear_directorio.")
                return False
            dirAbs = os.path.join(rutaBase, dirRel)
            log.info(f"{logPrefix} Creando directorio: {dirRel}")
            # exist_ok=True hace que no falle si ya existe
            os.makedirs(dirAbs, exist_ok=True)
            return True

        elif tipoAccion == "no_accion":
            log.info(
                f"{logPrefix} Accion 'no_accion' recibida. No se aplican cambios.")
            # Esto no es un fallo, es una indicación de que no hay nada que hacer ahora.
            # La función principal debería manejar esto adecuadamente (no hacer commit).
            # Indicar que la "aplicación" (de no hacer nada) fue "exitosa".
            return True

        else:
            log.error(f"{logPrefix} Tipo de accion no soportado: {tipoAccion}")
            return False

    except Exception as e:
        log.error(
            f"{logPrefix} Error inesperado aplicando accion '{tipoAccion}' en {rutaBase}: {e}")
        # Considerar si se deben revertir cambios parciales si la operación falló a medias (complejo)
        return False
