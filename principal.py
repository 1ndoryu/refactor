# principal.py
import logging
import sys
import os
import json
import argparse
from config import settings
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios

def configurarLogging():
    logRaiz = logging.getLogger()
    if logRaiz.handlers:
        logging.info("configurarLogging: Sistema de logging ya configurado.")
        return

    nivelLog = logging.INFO
    formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'

    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    logRaiz.addHandler(consolaHandler)

    try:
        rutaLogArchivo = os.path.join(settings.rutaBaseProyecto, "refactor.log")
        os.makedirs(os.path.dirname(rutaLogArchivo), exist_ok=True)
        archivoHandler = logging.FileHandler(rutaLogArchivo, encoding='utf-8')
        archivoHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
        logRaiz.addHandler(archivoHandler)
    except Exception as e:
        logging.error(f"configurarLogging: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}")

    logRaiz.setLevel(nivelLog)
    logging.info("="*50)
    logging.info("configurarLogging: Sistema de logging configurado.")
    logging.info(f"configurarLogging: Nivel de log establecido a {logging.getLevelName(logRaiz.level)}")

def cargarHistorial():
    prefijoLog = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.rutaHistorial
    if not os.path.exists(rutaArchivoHistorial):
        logging.info(f"{prefijoLog} Archivo de historial no encontrado en {rutaArchivoHistorial}. Iniciando historial vacío.")
        return historial

    try:
        with open(rutaArchivoHistorial, 'r', encoding='utf-8') as f:
            historial = [linea.strip() for linea in f if linea.strip()]
        logging.info(f"{prefijoLog} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        logging.error(f"{prefijoLog} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío.")
        historial = []

    return historial

def guardarHistorial(historial):
    prefijoLog = "guardarHistorial:"
    rutaArchivoHistorial = settings.rutaHistorial
    try:
        os.makedirs(os.path.dirname(rutaArchivoHistorial), exist_ok=True)
        with open(rutaArchivoHistorial, 'w', encoding='utf-8') as f:
            for entrada in historial:
                f.write(entrada + "\n")
        logging.info(f"{prefijoLog} Historial guardado en {rutaArchivoHistorial} ({len(historial)} entradas).")
        return True
    except Exception as e:
        logging.error(f"{prefijoLog} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False

def parsearSugerencia(sugerenciaJson):
    prefijoLog = "parsearSugerencia:"
    accionesSoportadas = [
        "modificar_archivo",
        "mover_archivo",
        "crear_archivo",
        "eliminar_archivo",
        "crear_directorio",
        "mover_codigo", # Nueva acción potencial
        "no_accion"
    ]

    if not isinstance(sugerenciaJson, dict):
        logging.error(f"{prefijoLog} La sugerencia recibida no es un diccionario JSON válido. Tipo: {type(sugerenciaJson)}. Valor: {sugerenciaJson}")
        return None

    accion = sugerenciaJson.get("accion")
    detalles = sugerenciaJson.get("detalles")
    descripcion = sugerenciaJson.get("descripcion")

    if not accion or not isinstance(detalles, dict) or not descripcion:
        logging.error(f"{prefijoLog} Formato JSON inválido. Faltan 'accion', 'detalles' o 'descripcion', o 'detalles' no es un dict. JSON: {sugerenciaJson}")
        return None

    if accion not in accionesSoportadas:
        logging.error(f"{prefijoLog} Acción '{accion}' NO RECONOCIDA o NO SOPORTADA. Acciones válidas: {accionesSoportadas}. JSON: {sugerenciaJson}")
        return None

    if accion == "no_accion":
        logging.info(f"{prefijoLog} Sugerencia 'no_accion' recibida y parseada.")

    logging.info(f"{prefijoLog} Sugerencia parseada exitosamente. Acción: {accion}")
    return sugerenciaJson

def ejecutarProcesoPrincipal():
    prefijoLog = "ejecutarProcesoPrincipal:"
    logging.info(f"{prefijoLog} ===== INICIO CICLO DE REFACTORIZACIÓN =====")
    huboCommitExitoso = False

    if not settings.claveApiGemini or not settings.urlRepositorio:
        logging.critical(f"{prefijoLog} Configuración esencial faltante (claveApiGemini o urlRepositorio). Verifique .env y config/settings.py. Abortando.")
        return False

    try:
        historialRefactor = cargarHistorial()

        logging.info(f"{prefijoLog} Preparando repositorio local en '{settings.rutaClon}' en la rama '{settings.ramaTrabajo}'...")
        if not manejadorGit.clonarOActualizarRepo(settings.urlRepositorio, settings.rutaClon, settings.ramaTrabajo):
            logging.error(f"{prefijoLog} No se pudo preparar el repositorio. Abortando ciclo.")
            return False
        logging.info(f"{prefijoLog} Repositorio listo y en la rama '{settings.ramaTrabajo}'.")

        logging.info(f"{prefijoLog} Analizando código del proyecto en {settings.rutaClon}...")
        extensiones = getattr(settings, 'extensionesPermitidas', None)
        ignorados = getattr(settings, 'directoriosIgnorados', None)
        archivos = analizadorCodigo.listarArchivosProyecto(settings.rutaClon, extensiones, ignorados)

        if archivos is None:
            logging.error(f"{prefijoLog} Error al listar archivos. Abortando ciclo.")
            return False
        if not archivos:
            logging.warning(f"{prefijoLog} No se encontraron archivos relevantes. Terminando ciclo.")
            return False

        codigoAAnalizar = analizadorCodigo.leerArchivos(archivos, settings.rutaClon)
        if not codigoAAnalizar:
            logging.error(f"{prefijoLog} No se pudo leer contenido de archivos. Abortando ciclo.")
            return False
        tamanoBytes = len(codigoAAnalizar.encode('utf-8'))
        tamanoKB = tamanoBytes / 1024
        logging.info(f"{prefijoLog} Código fuente leído ({len(archivos)} archivos, {tamanoKB:.2f} KB).")

        logging.info(f"{prefijoLog} Obteniendo sugerencia de Gemini (modelo: {settings.modeloGemini})...")
        historialRecienteTexto = "\n".join(historialRefactor[-settings.numHistorialContexto:])
        sugerenciaJson = analizadorCodigo.analizarConGemini(codigoAAnalizar, historialRecienteTexto)

        if not sugerenciaJson:
            logging.error(f"{prefijoLog} No se recibió sugerencia válida de Gemini. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.rutaClon)
            return False

        logging.info(f"{prefijoLog} Parseando sugerencia de Gemini...")
        accionParseada = parsearSugerencia(sugerenciaJson)
        if not accionParseada:
            logging.error(f"{prefijoLog} Sugerencia inválida o no soportada. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.rutaClon)
            return False

        if accionParseada.get("accion") == "no_accion":
            logging.info(f"{prefijoLog} Gemini sugirió 'no_accion': {accionParseada.get('descripcion', '')}. Terminando ciclo.")
            return False

        logging.info(f"{prefijoLog} Aplicando cambios sugeridos...")
        exitoAplicar = aplicadorCambios.aplicarCambio(accionParseada, settings.rutaClon)
        if not exitoAplicar:
            logging.error(f"{prefijoLog} Falló la aplicación de cambios. Intentando descartar...")
            if not manejadorGit.descartarCambiosLocales(settings.rutaClon):
                logging.critical(f"{prefijoLog} ¡FALLO CRÍTICO! No se aplicaron cambios Y no se pudieron descartar. ¡Revisión manual requerida!")
            else:
                logging.info(f"{prefijoLog} Cambios locales descartados tras fallo.")
            return False

        logging.info(f"{prefijoLog} Cambios aplicados localmente.")

        logging.info(f"{prefijoLog} Realizando commit en rama '{settings.ramaTrabajo}'...")
        mensajeCommit = accionParseada.get('descripcion', 'Refactorización automática AI')
        if len(mensajeCommit.encode('utf-8')) > 4000:
            mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
            logging.warning(f"{prefijoLog} Mensaje de commit truncado por longitud excesiva.")
        elif len(mensajeCommit.splitlines()[0]) > 72:
            logging.warning(f"{prefijoLog} La primera línea del mensaje de commit supera los 72 caracteres.")

        exitoCommit = manejadorGit.hacerCommit(settings.rutaClon, mensajeCommit)
        if not exitoCommit:
            logging.error(f"{prefijoLog} Falló el commit o no había nada que commitear. Ver logs de manejadorGit.")
            manejadorGit.descartarCambiosLocales(settings.rutaClon)
            return False

        huboCommitExitoso = True
        logging.info(f"{prefijoLog} Commit realizado con éxito.")

        logging.info(f"{prefijoLog} Actualizando y guardando historial.")
        historialRefactor.append(accionParseada.get('descripcion', 'Acción sin descripción'))
        guardarHistorial(historialRefactor)

        logging.info(f"{prefijoLog} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
        return huboCommitExitoso

    except Exception as e:
        logging.critical(f"{prefijoLog} Error inesperado durante la ejecución principal: {e}", exc_info=True)
        try:
            logging.info(f"{prefijoLog} Intentando descartar cambios locales debido a error inesperado...")
            manejadorGit.descartarCambiosLocales(settings.rutaClon)
        except Exception as e_clean:
            logging.error(f"{prefijoLog} Falló intento de limpieza tras error: {e_clean}")
        return False

if __name__ == "__main__":
    configurarLogging()

    parser = argparse.ArgumentParser(
        description="Agente de Refactorización de Código con IA (Gemini).",
        epilog="Ejecuta un ciclo de análisis y refactorización. Usa --modo-test para hacer push después de un commit exitoso."
    )
    parser.add_argument(
        "--modo-test",
        action="store_true",
        help="Activa modo prueba: Ejecuta un ciclo y hace push si hay commit."
    )
    args = parser.parse_args()

    logging.info(f"Iniciando script principal. Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    try:
        commitRealizado = ejecutarProcesoPrincipal()

        if commitRealizado:
            logging.info("Proceso principal completado: Se realizó un commit.")
            if args.modo_test:
                logging.info("Modo Test activado: Intentando hacer push a origin...")
                ramaPush = getattr(settings, 'ramaTrabajo', 'refactor')
                if manejadorGit.hacerPush(settings.rutaClon, ramaPush):
                    logging.info(f"Modo Test: Push a la rama '{ramaPush}' realizado con éxito.")
                    sys.exit(0)
                else:
                    logging.error(f"Modo Test: Falló el push a la rama '{ramaPush}'.")
                    sys.exit(1)
            else:
                logging.info("Modo Test desactivado. Commit realizado localmente, no se hizo push.")
                sys.exit(0)
        else:
            logging.warning("Proceso principal finalizó sin realizar un commit.")
            sys.exit(1)

    except Exception as e:
        logging.critical(f"Error fatal no manejado en el bloque principal: {e}", exc_info=True)
        sys.exit(2)