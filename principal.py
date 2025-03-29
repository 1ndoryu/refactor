# principal.py
import logging
import sys
import os
import json
import argparse  # Para argumentos de línea de comando
from config import settings
# Importar módulos del núcleo
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios

# Configuración del logging (mover a una función para claridad)


def configurarLogging():
    log = logging.getLogger()  # Obtener el logger raíz
    if log.handlers:  # Evitar añadir handlers múltiples si ya está configurado
        log.info("configurarLogging: Logging ya configurado.")
        return

    nivelLog = logging.INFO  # Nivel por defecto INFO, se puede cambiar a DEBUG
    # Cambiar nivel si se pasa argumento --debug? (requeriría parsear args antes)
    # Por ahora, INFO fijo.
    formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'

    # Configurar salida a consola
    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    log.addHandler(consolaHandler)

    # Configurar salida a archivo
    try:
        archivoHandler = logging.FileHandler("refactor.log", encoding='utf-8')
        archivoHandler.setFormatter(
            logging.Formatter(formatoLog, fechaFormato))
        log.addHandler(archivoHandler)
    except Exception as e:
        log.error(
            f"configurarLogging: No se pudo crear el archivo de log 'refactor.log': {e}")
        # Continuar solo con log de consola si falla el archivo

    log.setLevel(nivelLog)
    # Log inicial después de configurar handlers
    log.info("="*50)
    log.info("configurarLogging: Sistema de logging configurado.")
    log.info(
        f"configurarLogging: Nivel de log establecido a {logging.getLevelName(log.level)}")


# Funciones para manejar el historial persistente
def cargarHistorial():
    logPrefix = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    if not os.path.exists(rutaArchivoHistorial):
        log.info(
            f"{logPrefix} Archivo de historial no encontrado en {rutaArchivoHistorial}. Iniciando historial vacío.")
        return historial

    try:
        with open(rutaArchivoHistorial, 'r', encoding='utf-8') as f:
            # Leer líneas, quitar espacios en blanco y saltos de línea
            historial = [line.strip() for line in f if line.strip()]
        log.info(
            f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        log.error(
            f"{logPrefix} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío.")
        historial = []  # Devolver vacío en caso de error de lectura

    return historial


def guardarHistorial(historial):
    logPrefix = "guardarHistorial:"
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    try:
        # Asegurarse que el directorio exista
        os.makedirs(os.path.dirname(rutaArchivoHistorial), exist_ok=True)
        with open(rutaArchivoHistorial, 'w', encoding='utf-8') as f:
            for entrada in historial:
                f.write(entrada + "\n")
        log.info(
            f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({len(historial)} entradas).")
        return True
    except Exception as e:
        log.error(
            f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False

# Función para parsear y validar la sugerencia JSON de Gemini


def parsearSugerencia(sugerenciaJson):
    logPrefix = "parsearSugerencia:"
    if not isinstance(sugerenciaJson, dict):
        logging.error(
            f"{logPrefix} La sugerencia recibida no es un diccionario JSON válido. Tipo: {type(sugerenciaJson)}. Valor: {sugerenciaJson}")
        return None

    # Campos obligatorios
    accion = sugerenciaJson.get("accion")
    detalles = sugerenciaJson.get("detalles")
    descripcion = sugerenciaJson.get("descripcion")

    if not accion or not isinstance(detalles, dict) or not descripcion:
        logging.error(
            f"{logPrefix} Formato JSON inválido. Faltan 'accion', 'detalles' o 'descripcion', o 'detalles' no es un dict. JSON: {sugerenciaJson}")
        return None

    # Validaciones adicionales básicas según el tipo de acción (se pueden expandir)
    accionesConDetallesObligatorios = [
        "modificar_archivo", "mover_archivo", "crear_archivo", "eliminar_archivo", "crear_directorio"]
    if accion in accionesConDetallesObligatorios and not detalles:
        logging.error(
            f"{logPrefix} Acción '{accion}' requiere detalles no vacíos, pero 'detalles' está vacío o ausente. JSON: {sugerenciaJson}")
        return None
    elif accion == "no_accion":
        logging.info(
            f"{logPrefix} Sugerencia 'no_accion' recibida y parseada.")
        # No necesita más validación aquí
    elif accion not in accionesConDetallesObligatorios:
        logging.warning(
            f"{logPrefix} Acción '{accion}' no reconocida o no soportada explícitamente. Se procederá, pero verificar implementación en aplicadorCambios.")
        # Permitir continuar pero advertir

    logging.info(
        f"{logPrefix} Sugerencia parseada exitosamente. Acción: {accion}")
    return sugerenciaJson  # Devolver el diccionario validado si pasa las comprobaciones

# Función principal que orquesta el proceso de refactorización.
# Devuelve True si se completó un ciclo con commit exitoso, False en caso de error o si no hubo commit.


def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    logging.info(f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN =====")
    huboCommitExitoso = False  # Para rastrear si llegamos a hacer commit

    # 1. Validar configuración esencial (API Key y Repo URL ya se validan/loguean en settings.py)
    if not settings.GEMINIAPIKEY or not settings.REPOSITORIOURL:
        logging.critical(
            f"{logPrefix} Configuración esencial faltante (GEMINI_API_KEY o REPOSITORIOURL). Verifique .env y config/settings.py. Abortando.")
        return False

    # Advertencia sobre URL de ejemplo
    if "github.com/usuario/repo.git" in settings.REPOSITORIOURL or "github.com/2upra/v4.git" == settings.REPOSITORIOURL:  # Añadir el repo por defecto también
        logging.warning(
            f"{logPrefix} La URL del repositorio parece ser la de ejemplo ('{settings.REPOSITORIOURL}'). Asegúrese que es correcta.")
        # Permitir continuar pero advertir

    # 2. Cargar historial de cambios previos
    historialRefactor = cargarHistorial()

    # 3. Clonar o actualizar el repositorio de trabajo y cambiar a la rama correcta
    logging.info(
        f"{logPrefix} Preparando repositorio local en '{settings.RUTACLON}' en la rama '{settings.RAMATRABAJO}'...")
    if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
        logging.error(
            f"{logPrefix} No se pudo clonar/actualizar el repositorio o cambiar a la rama de trabajo. Abortando ciclo.")
        return False
    logging.info(
        f"{logPrefix} Repositorio listo y en la rama '{settings.RAMATRABAJO}'.")

    # 4. Analizar el código: Listar archivos y leer contenido
    logging.info(
        f"{logPrefix} Analizando código del proyecto en {settings.RUTACLON}...")
    # Usar valores de settings si existen, o None para usar defaults internos de la función
    extensiones = getattr(settings, 'EXTENSIONESPERMITIDAS', None)
    ignorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', None)
    archivos = analizadorCodigo.listarArchivosProyecto(
        settings.RUTACLON, extensiones, ignorados)

    if archivos is None:  # Error durante el listado
        logging.error(
            f"{logPrefix} Hubo un error al listar los archivos del proyecto. Abortando ciclo.")
        return False
    if not archivos:  # No se encontraron archivos relevantes
        logging.warning(
            f"{logPrefix} No se encontraron archivos relevantes para analizar en el proyecto con la configuración actual. Terminando ciclo.")
        # Considerar esto un éxito vacío o un fallo? Por ahora, fallo para indicar que no se hizo nada.
        return False

    # Leer contenido de los archivos encontrados
    # ¡ADVERTENCIA! Esto puede consumir mucha memoria y exceder límites de API si el proyecto es grande
    codigoAAnalizar = analizadorCodigo.leerArchivos(
        archivos, settings.RUTACLON)
    if not codigoAAnalizar:
        logging.error(
            f"{logPrefix} No se pudo leer el contenido de los archivos listados o el contenido total es vacío. Abortando ciclo.")
        return False
    # Loguear tamaño aquí de nuevo por si acaso
    tamanoBytes = len(codigoAAnalizar.encode('utf-8'))
    logging.info(
        f"{logPrefix} Código fuente leído ({len(archivos)} archivos, {tamanoBytes / 1024:.2f} KB).")
    if tamanoBytes == 0:
        logging.warning(
            f"{logPrefix} El contenido total leído tiene 0 bytes. Gemini probablemente no podrá analizar esto.")
        # ¿Abortar aquí o dejar que Gemini falle? Dejemos que falle por ahora.

    # 5. Interactuar con Gemini para obtener sugerencia
    logging.info(
        f"{logPrefix} Obteniendo sugerencia de refactorización de Gemini (modelo: {settings.MODELOGEMINI})...")
    # Pasar solo las últimas N entradas del historial
    historialRecienteTexto = "\n".join(
        historialRefactor[-settings.N_HISTORIAL_CONTEXTO:])
    sugerenciaJson = analizadorCodigo.analizarConGemini(
        codigoAAnalizar, historialRecienteTexto)

    if not sugerenciaJson:
        logging.error(
            f"{logPrefix} No se recibió sugerencia válida de Gemini o hubo un error en la API. Abortando ciclo.")
        # Aquí podría ser útil intentar descartar cambios si algo se modificó antes (aunque no debería)
        # manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        return False

    # 6. Parsear y validar la sugerencia
    logging.info(f"{logPrefix} Parseando y validando sugerencia de Gemini...")
    accionParseada = parsearSugerencia(sugerenciaJson)
    if not accionParseada:
        logging.error(
            f"{logPrefix} La sugerencia de Gemini no pudo ser parseada o es inválida. Abortando ciclo.")
        # Podríamos guardar la respuesta inválida para depuración
        # with open("invalid_gemini_response.json", "w") as f: json.dump(sugerenciaJson, f)
        return False

    # Verificar si la acción es "no_accion" antes de intentar aplicar
    if accionParseada.get("accion") == "no_accion":
        descripcionNoAccion = accionParseada.get(
            'descripcion', 'No se identificaron acciones.')
        logging.info(
            f"{logPrefix} Gemini sugirió 'no_accion': {descripcionNoAccion}. Terminando ciclo sin cambios.")
        # Devolver False porque no hubo commit, pero log indica éxito relativo.
        return False  # Indicar que no hubo commit/cambio

    # 7. Aplicar los cambios al clon local
    logging.info(f"{logPrefix} Aplicando cambios sugeridos por Gemini...")
    exitoAplicar = aplicadorCambios.aplicarCambio(
        accionParseada, settings.RUTACLON)
    if not exitoAplicar:
        logging.error(
            f"{logPrefix} Falló la aplicación de los cambios sugeridos. Intentando descartar cambios locales...")
        # ¡Importante! Intentar revertir para no dejar el repo sucio
        if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
            logging.critical(
                f"{logPrefix} ¡¡FALLO CRÍTICO!! No se pudieron aplicar los cambios Y TAMPOCO descartarlos. El repositorio en {settings.RUTACLON} está en estado inconsistente y requiere intervención manual.")
        else:
            logging.info(
                f"{logPrefix} Cambios locales descartados tras fallo de aplicación.")
        return False  # Fallo general del ciclo
    logging.info(f"{logPrefix} Cambios aplicados localmente con éxito.")

    # 8. Hacer commit de los cambios en la rama de trabajo
    logging.info(
        f"{logPrefix} Realizando commit de los cambios en la rama '{settings.RAMATRABAJO}'...")
    # Usar la descripción de la acción parseada como mensaje de commit
    mensajeCommit = accionParseada.get(
        'descripcion', 'Refactorización automática AI')
    # Asegurar que el mensaje no sea excesivamente largo (Git suele tener límites prácticos)
    if len(mensajeCommit) > 150:
        mensajeCommit = mensajeCommit[:147] + "..."
        logging.warning(
            f"{logPrefix} Mensaje de commit truncado por longitud excesiva.")

    exitoCommit = manejadorGit.hacerCommit(settings.RUTACLON, mensajeCommit)
    if not exitoCommit:
        logging.error(
            f"{logPrefix} Falló el commit de los cambios. Los cambios están aplicados pero no commiteados.")
        # ¿Intentar descartar cambios aquí también? Podría ser peligroso si el commit falló por otra razón.
        # Mejor dejar los cambios y que el usuario revise.
        return False  # Indicar que el ciclo falló en el commit

    # Si llegamos aquí, el commit fue exitoso
    huboCommitExitoso = True
    logging.info(f"{logPrefix} Commit realizado con éxito.")

    # 9. Actualizar y guardar historial (solo si el commit fue exitoso)
    logging.info(
        f"{logPrefix} Actualizando y guardando historial de refactorización.")
    # Añadir el mensaje de commit al historial
    historialRefactor.append(mensajeCommit)
    guardarHistorial(historialRefactor)  # Guardar el historial actualizado

    logging.info(
        f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
    return huboCommitExitoso  # Devolver True porque hubo un commit


# Punto de entrada principal del script
if __name__ == "__main__":
    # Configurar logging lo antes posible
    configurarLogging()

    # Configurar ArgumentParser para manejar --modo-test
    parser = argparse.ArgumentParser(
        description="Agente de Refactorización de Código con IA (Gemini).",
        epilog="Ejecuta un ciclo de análisis y refactorización. Usa --modo-test para hacer push después de un commit exitoso."
    )
    parser.add_argument(
        "--modo-test",
        action="store_true",  # Crea una bandera booleana, default es False
        help="Activa el modo de prueba: Ejecuta un ciclo y, si hay un commit exitoso, intenta hacer push a la rama de trabajo en origin."
    )
    # Podríamos añadir más argumentos aquí (ej. --debug para cambiar nivel de log)
    args = parser.parse_args()

    logging.info(
        f"Iniciando script principal. Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    # Ejecutar el proceso principal
    commitRealizado = ejecutarProcesoPrincipal()

    # Evaluar resultado y actuar según modo test
    if commitRealizado:
        logging.info("Proceso principal completado: Se realizó un commit.")
        if args.modo_test:
            logging.info(
                "Modo Test activado: Intentando hacer push a origin...")
            if manejadorGit.hacerPush(settings.RUTACLON, settings.RAMATRABAJO):
                logging.info(
                    f"Modo Test: Push a la rama '{settings.RAMATRABAJO}' realizado con éxito.")
                sys.exit(0)  # Salir con éxito total
            else:
                logging.error(
                    f"Modo Test: Falló el push a la rama '{settings.RAMATRABAJO}'. El commit se realizó localmente pero no se subió.")
                sys.exit(1)  # Salir con error porque el push falló
        else:
            # Éxito, pero no en modo test, así que no hacemos push
            sys.exit(0)  # Salir con éxito

    else:
        # ejecutarProcesoPrincipal devolvió False
        logging.error(
            "El proceso principal de refactorización finalizó sin realizar un commit (debido a error, 'no_accion' de Gemini, o falta de cambios).")
        sys.exit(1)  # Salir con código de error
