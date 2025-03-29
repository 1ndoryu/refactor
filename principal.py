# principal.py
import logging
import sys
import json  # Para parsear la sugerencia
from config import settings
# Importar los nuevos módulos y funciones específicas
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios

# Variable global simple para historial (o cargar/guardar de archivo)
# TODO: Implementar persistencia real del historial
historialRefactor = []

# Configura el logging básico para la aplicación.


def configurarLogging():
    log = logging.getLogger()  # Obtener el logger raíz
    # Evitar añadir handlers múltiples si se llama varias veces
    if not log.handlers:
        nivelLog = logging.INFO
        formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
        fechaFormato = '%Y-%m-%d %H:%M:%S'

        # Configurar salida a consola
        consolaHandler = logging.StreamHandler(sys.stdout)
        consolaHandler.setFormatter(
            logging.Formatter(formatoLog, fechaFormato))
        log.addHandler(consolaHandler)

        # Configurar salida a archivo
        archivoHandler = logging.FileHandler("refactor.log", encoding='utf-8')
        archivoHandler.setFormatter(
            logging.Formatter(formatoLog, fechaFormato))
        log.addHandler(archivoHandler)

        log.setLevel(nivelLog)
        log.info("configurarLogging: Sistema de logging configurado.")
    else:
        log.info("configurarLogging: Logging ya configurado.")

# Función para parsear y validar la sugerencia JSON de Gemini


def parsearSugerencia(sugerenciaJson):
    logPrefix = "parsearSugerencia:"
    if not isinstance(sugerenciaJson, dict):
        logging.error(
            f"{logPrefix} La sugerencia no es un diccionario JSON valido.")
        return None

    accion = sugerenciaJson.get("accion")
    detalles = sugerenciaJson.get("detalles")
    descripcion = sugerenciaJson.get("descripcion")

    if not accion or not isinstance(detalles, dict) or not descripcion:
        logging.error(
            f"{logPrefix} Formato JSON invalido. Faltan 'accion', 'detalles' o 'descripcion'. JSON: {sugerenciaJson}")
        return None

    # Validaciones adicionales básicas según el tipo de acción (se pueden expandir)
    if accion != "no_accion" and not detalles:
        logging.warning(
            f"{logPrefix} Accion '{accion}' recibida pero sin detalles. Tratando como 'no_accion'.")
        return {"accion": "no_accion", "descripcion": "Acción recibida sin detalles.", "detalles": {}}

    logging.info(
        f"{logPrefix} Sugerencia parseada exitosamente. Accion: {accion}")
    return sugerenciaJson  # Devolver el diccionario validado


# Función principal que orquesta el proceso de refactorización.
def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    logging.info(
        f"{logPrefix} Iniciando ejecucion de la herramienta de refactorizacion.")

    # 1. Validar configuración esencial
    if not settings.GEMINIAPIKEY:
        logging.critical(f"{logPrefix} Falta la API Key de Gemini. Abortando.")
        return False

    if not settings.REPOSITORIOURL:
        logging.critical(
            f"{logPrefix} La URL del repositorio no esta configurada. Abortando.")
        return False
    # Validacion simple anti-placeholder
    if "github.com/usuario/repo.git" in settings.REPOSITORIOURL:
        logging.warning(
            f"{logPrefix} La URL del repositorio parece ser la de ejemplo. Verifique config/settings.py.")
        # Permitir continuar pero advertir

    # 2. Clonar o actualizar el repositorio de trabajo
    logging.info(f"{logPrefix} Preparando repositorio local...")
    if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON):
        logging.error(
            f"{logPrefix} No se pudo clonar o actualizar el repositorio. Abortando.")
        return False
    logging.info(f"{logPrefix} Repositorio listo en {settings.RUTACLON}")

    # 3. Analizar el código en settings.RUTACLON
    logging.info(f"{logPrefix} Analizando codigo del proyecto...")
    # TODO: Estrategia para manejar contexto grande. Por ahora, leemos todo (peligroso).
    #       Se podría limitar a ciertos directorios o tipos de archivo inicialmente.
    #       O implementar la estrategia de 2 pasos (identificar area -> analizar area).
    archivos = analizadorCodigo.listarArchivosProyecto(settings.RUTACLON)
    if not archivos:
        logging.error(
            f"{logPrefix} No se encontraron archivos o hubo un error al listarlos.")
        return False

    # Leer contenido de los archivos encontrados
    # ADVERTENCIA: Esto puede consumir mucha memoria y exceder límites de API si el proyecto es grande
    codigoAAnalizar = analizadorCodigo.leerArchivos(
        archivos, settings.RUTACLON)
    if not codigoAAnalizar:
        logging.error(
            f"{logPrefix} No se pudo leer el contenido de los archivos.")
        return False
    logging.info(
        f"{logPrefix} Codigo fuente leido (Tamaño aprox: {len(codigoAAnalizar)} bytes).")

    # 4. Interactuar con Gemini para obtener sugerencia
    logging.info(
        f"{logPrefix} Obteniendo sugerencia de refactorizacion de Gemini...")
    # TODO: Cargar/Pasar historial de cambios
    # Pasar solo los últimos 5 cambios, por ejemplo
    historialTexto = "\n".join(historialRefactor[-5:])
    sugerenciaJson = analizadorCodigo.analizarConGemini(
        codigoAAnalizar, historialTexto)
    if not sugerenciaJson:
        logging.error(
            f"{logPrefix} No se recibio sugerencia valida de Gemini o hubo un error en la API.")
        return False

    # 5. Parsear y validar la sugerencia
    logging.info(f"{logPrefix} Parseando sugerencia de Gemini...")
    accion = parsearSugerencia(sugerenciaJson)
    if not accion:
        logging.error(
            f"{logPrefix} La sugerencia de Gemini no pudo ser parseada o es invalida.")
        return False  # Fallo si no podemos entender la respuesta

    # Verificar si la acción es "no_accion"
    if accion.get("accion") == "no_accion":
        logging.info(
            f"{logPrefix} Gemini sugirio 'no_accion'. {accion.get('descripcion', '')}. Terminando ciclo sin cambios.")
        return True  # Terminamos bien, pero sin cambios

    # 6. Aplicar los cambios al clon
    logging.info(f"{logPrefix} Aplicando cambios sugeridos...")
    exitoAplicar = aplicadorCambios.aplicarCambio(accion, settings.RUTACLON)
    if not exitoAplicar:
        logging.error(
            f"{logPrefix} Fallo la aplicacion de los cambios sugeridos. Abortando antes de commit.")
        # TODO: Considerar revertir cambios en el repo local si falló la aplicación
        # manejadorGit.ejecutarComando(['git', 'reset', '--hard'], cwd=settings.RUTACLON)
        return False
    logging.info(f"{logPrefix} Cambios aplicados localmente con exito.")

    # 7. Hacer commit de los cambios en el clon
    logging.info(f"{logPrefix} Realizando commit de los cambios...")
    mensajeCommit = f"Refactor AI: {accion.get('descripcion', 'Cambios automaticos')}"
    exitoCommit = manejadorGit.hacerCommit(settings.RUTACLON, mensajeCommit)
    if not exitoCommit:
        logging.error(f"{logPrefix} Fallo el commit de los cambios.")
        # Los cambios aún están aplicados localmente, pero no commiteados.
        return False

    # 8. Actualizar historial (si el commit fue exitoso)
    logging.info(f"{logPrefix} Actualizando historial de refactorizacion.")
    historialRefactor.append(mensajeCommit)
    # TODO: Guardar historial en archivo persistente aquí.

    # 9. Opcional: Hacer push al repositorio remoto
    # rama = "main" # o la rama que corresponda
    # logging.info(f"{logPrefix} Haciendo push a origin/{rama}...")
    # if not manejadorGit.hacerPush(settings.RUTACLON, rama):
    #     logging.error(f"{logPrefix} Falló el push al repositorio remoto.")
    # Decidir si esto es un fallo crítico o no
    # return False
    # else:
    #      logging.info(f"{logPrefix} Push realizado con éxito.")

    logging.info(f"{logPrefix} Ejecucion completada exitosamente.")
    return True


if __name__ == "__main__":
    configurarLogging()
    # TODO: Añadir lógica para modo test (ejecutar una vez) vs modo continuo (ejecutar cada X tiempo)
    # Por ahora, solo ejecuta una vez.
    if not ejecutarProcesoPrincipal():
        logging.critical("El proceso principal de refactorizacion fallo.")
        sys.exit(1)  # Salir con código de error
    else:
        logging.info("Proceso principal completado.")
        sys.exit(0)  # Salir con éxito
