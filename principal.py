# principal.py
import logging
import sys
import os
import json
import argparse
import subprocess # Necesario para el check de git diff
from config import settings
# Importar módulos del núcleo
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios

# Configuración del logging (mover a una función para claridad)
def configurarLogging():
    # Usar logging.getLogger() directamente aquí para configurar el logger raíz
    log_raiz = logging.getLogger()
    if log_raiz.handlers:  # Evitar añadir handlers múltiples si ya está configurado
        logging.info("configurarLogging: Logging ya configurado.")
        return

    nivelLog = logging.INFO  # Nivel por defecto INFO
    formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'

    # Configurar salida a consola
    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    log_raiz.addHandler(consolaHandler)

    # Configurar salida a archivo
    try:
        rutaLogArchivo = os.path.join(settings.RUTA_BASE_PROYECTO, "refactor.log")
        os.makedirs(os.path.dirname(rutaLogArchivo), exist_ok=True)
        archivoHandler = logging.FileHandler(rutaLogArchivo, encoding='utf-8')
        archivoHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
        log_raiz.addHandler(archivoHandler)
    except Exception as e:
        logging.error(f"configurarLogging: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}")

    log_raiz.setLevel(nivelLog)
    logging.info("="*50)
    logging.info("configurarLogging: Sistema de logging configurado.")
    logging.info(f"configurarLogging: Nivel de log establecido a {logging.getLevelName(log_raiz.level)}")


# Funciones para manejar el historial persistente
def cargarHistorial():
    logPrefix = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    if not os.path.exists(rutaArchivoHistorial):
        logging.info(f"{logPrefix} Archivo de historial no encontrado en {rutaArchivoHistorial}. Iniciando historial vacío.")
        return historial

    try:
        with open(rutaArchivoHistorial, 'r', encoding='utf-8') as f:
            historial = [line.strip() for line in f if line.strip()]
        logging.info(f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        logging.error(f"{logPrefix} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío.")
        historial = []
    return historial


def guardarHistorial(historial):
    logPrefix = "guardarHistorial:"
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    try:
        os.makedirs(os.path.dirname(rutaArchivoHistorial), exist_ok=True)
        with open(rutaArchivoHistorial, 'w', encoding='utf-8') as f:
            for entrada in historial:
                f.write(entrada + "\n")
        logging.info(f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({len(historial)} entradas).")
        return True
    except Exception as e:
        logging.error(f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False

# Función para parsear y validar la sugerencia JSON de Gemini
def parsearSugerencia(sugerenciaJson):
    logPrefix = "parsearSugerencia:"
    accionesSoportadas = [
        "modificar_archivo", "mover_archivo", "crear_archivo",
        "eliminar_archivo", "crear_directorio", "mover_codigo", "no_accion"
    ]

    if not isinstance(sugerenciaJson, dict):
        logging.error(f"{logPrefix} La sugerencia recibida no es un diccionario JSON válido. Tipo: {type(sugerenciaJson)}. Valor: {sugerenciaJson}")
        return None

    accion = sugerenciaJson.get("accion")
    detalles = sugerenciaJson.get("detalles")
    descripcion = sugerenciaJson.get("descripcion")

    if not accion or not isinstance(detalles, dict) or not descripcion:
        logging.error(f"{logPrefix} Formato JSON inválido. Faltan 'accion', 'detalles' o 'descripcion', o 'detalles' no es un dict. JSON: {sugerenciaJson}")
        return None

    if accion not in accionesSoportadas:
        logging.error(f"{logPrefix} Acción '{accion}' NO RECONOCIDA o NO SOPORTADA. Válidas: {accionesSoportadas}. JSON: {sugerenciaJson}")
        return None

    if accion == "no_accion":
        logging.info(f"{logPrefix} Sugerencia 'no_accion' recibida y parseada.")

    logging.info(f"{logPrefix} Sugerencia parseada exitosamente. Acción: {accion}")
    return sugerenciaJson

# Función principal que orquesta el proceso de refactorización.
def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    logging.info(f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN =====")
    huboCommitExitoso = False # Inicia como False

    if not settings.GEMINIAPIKEY or not settings.REPOSITORIOURL:
        logging.critical(f"{logPrefix} Configuración esencial faltante (GEMINI_API_KEY o REPOSITORIOURL). Abortando.")
        return False

    try:
        # 2. Cargar historial
        historialRefactor = cargarHistorial()

        # 3. Preparar repositorio
        logging.info(f"{logPrefix} Preparando repositorio local en '{settings.RUTACLON}' en la rama '{settings.RAMATRABAJO}'...")
        if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(f"{logPrefix} No se pudo preparar el repositorio. Abortando ciclo.")
            return False
        logging.info(f"{logPrefix} Repositorio listo y en la rama '{settings.RAMATRABAJO}'.")

        # 4. Analizar código
        logging.info(f"{logPrefix} Analizando código del proyecto en {settings.RUTACLON}...")
        extensiones = getattr(settings, 'EXTENSIONESPERMITIDAS', None)
        ignorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', None)
        archivos = analizadorCodigo.listarArchivosProyecto(settings.RUTACLON, extensiones, ignorados)
        if archivos is None: return False # Error ya logueado
        if not archivos:
            logging.warning(f"{logPrefix} No se encontraron archivos relevantes. Terminando ciclo.")
            return False

        codigoAAnalizar = analizadorCodigo.leerArchivos(archivos, settings.RUTACLON)
        if not codigoAAnalizar: return False # Error ya logueado
        tamanoBytes = len(codigoAAnalizar.encode('utf-8'))
        tamanoKB = tamanoBytes / 1024
        logging.info(f"{logPrefix} Código fuente leído ({len(archivos)} archivos, {tamanoKB:.2f} KB).")

        # 5. Obtener sugerencia Gemini
        logging.info(f"{logPrefix} Obteniendo sugerencia de Gemini (modelo: {settings.MODELOGEMINI})...")
        historialRecienteTexto = "\n".join(historialRefactor[-settings.N_HISTORIAL_CONTEXTO:])
        sugerenciaJson = analizadorCodigo.analizarConGemini(codigoAAnalizar, historialRecienteTexto)
        if not sugerenciaJson:
            logging.error(f"{logPrefix} No se recibió sugerencia válida de Gemini. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        # 6. Parsear sugerencia
        logging.info(f"{logPrefix} Parseando sugerencia de Gemini...")
        accionParseada = parsearSugerencia(sugerenciaJson)
        if not accionParseada:
            logging.error(f"{logPrefix} Sugerencia inválida o no soportada. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        if accionParseada.get("accion") == "no_accion":
            logging.info(f"{logPrefix} Gemini sugirió 'no_accion': {accionParseada.get('descripcion', '')}. Terminando ciclo.")
            return False # No hubo commit

        # 7. Aplicar cambios
        logging.info(f"{logPrefix} Aplicando cambios sugeridos...")
        # *** CAMBIO: Capturar y verificar el resultado de aplicarCambio ***
        exitoAplicar = aplicadorCambios.aplicarCambio(accionParseada, settings.RUTACLON)
        if not exitoAplicar:
            # El error específico ya se habrá logueado dentro de aplicarCambio
            logging.error(f"{logPrefix} Falló la aplicación de cambios sugeridos por Gemini. Intentando descartar...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                logging.critical(f"{logPrefix} ¡FALLO CRÍTICO! No se aplicaron cambios Y no se pudieron descartar. ¡Revisión manual requerida en {settings.RUTACLON}!")
            else:
                logging.info(f"{logPrefix} Cambios locales (si los hubo) descartados tras fallo en aplicación.")
            return False # Indicar que el ciclo falló y no hubo commit

        # Si llegamos aquí, exitoAplicar fue True
        logging.info(f"{logPrefix} Cambios aplicados localmente con éxito.")

        # 8. Hacer commit
        logging.info(f"{logPrefix} Realizando commit en rama '{settings.RAMATRABAJO}'...")
        mensajeCommit = accionParseada.get('descripcion', 'Refactorización automática AI')
        if len(mensajeCommit.encode('utf-8')) > 4000:
             mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
             logging.warning(f"{logPrefix} Mensaje de commit truncado.")
        elif len(mensajeCommit.splitlines()[0]) > 72:
             logging.warning(f"{logPrefix} La primera línea del mensaje de commit supera los 72 caracteres.")

        # *** CAMBIO: Capturar y verificar el resultado de hacerCommit ***
        # Nota: hacerCommit devuelve True si el comando 'commit' tiene éxito O si no había nada que commitear.
        exitoCommitIntento = manejadorGit.hacerCommit(settings.RUTACLON, mensajeCommit)
        if not exitoCommitIntento:
            # Esto solo debería ocurrir si el comando 'git commit' falló (ej. config git user mal, hooks, etc.)
            # El caso "no hay cambios" es manejado por hacerCommit devolviendo True.
            logging.error(f"{logPrefix} Falló el comando 'git commit'. Intentando descartar cambios staged...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON) # Intentar limpiar
            return False # Indicar fallo

        # *** CAMBIO: Verificar explícitamente si hubo cambios reales en el commit ***
        # Usamos 'git diff HEAD~1 HEAD --quiet'. Devuelve 0 si NO hay cambios, 1 si SÍ hay cambios.
        comandoCheckDiff = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
        commitTuvoCambios = False
        try:
            # Ejecutamos sin check=True para capturar el código de retorno
            resultadoCheck = subprocess.run(comandoCheckDiff, cwd=settings.RUTACLON, capture_output=True)
            if resultadoCheck.returncode == 1:
                # Código 1 significa que SÍ hubo diferencias -> Commit efectivo
                logging.info(f"{logPrefix} Commit realizado con éxito y contiene cambios.")
                commitTuvoCambios = True
            elif resultadoCheck.returncode == 0:
                 # Código 0 significa que NO hubo diferencias -> Commit vacío o la lógica anterior falló
                 # Esto puede pasar si aplicarCambio tuvo éxito pero no cambió nada (ej. reemplazar con lo mismo)
                 # O si hacerCommit dijo que no había nada staged (aunque esto no debería pasar si exitoAplicar=True)
                 logging.warning(f"{logPrefix} Aunque 'git commit' no dio error, no se detectaron cambios efectivos en el último commit. La acción no tuvo efecto real.")
                 # Intentar deshacer el commit vacío si es posible (reset suave)
                 try:
                     manejadorGit.ejecutarComando(['git', 'reset', '--soft', 'HEAD~1'], cwd=settings.RUTACLON)
                     manejadorGit.descartarCambiosLocales(settings.RUTACLON) # Limpiar working dir
                     logging.info(f"{logPrefix} Intento de revertir commit vacío realizado.")
                 except Exception as e_revert:
                      logging.error(f"{logPrefix} No se pudo revertir el commit potencialmente vacío: {e_revert}")
                 commitTuvoCambios = False # Confirmar que no hubo éxito real
            else:
                 # Otro código de error inesperado
                 stderr_log = resultadoCheck.stderr.decode('utf-8', errors='ignore').strip()
                 logging.error(f"{logPrefix} Error inesperado al verificar diferencias del commit (código {resultadoCheck.returncode}). Stderr: {stderr_log}")
                 commitTuvoCambios = False

        except FileNotFoundError:
             logging.error(f"{logPrefix} Error: Comando 'git' no encontrado al verificar commit.")
             commitTuvoCambios = False
        except Exception as e:
             logging.error(f"{logPrefix} Error inesperado verificando el último commit: {e}")
             commitTuvoCambios = False

        # Continuar solo si el commit tuvo cambios efectivos
        if not commitTuvoCambios:
            logging.warning(f"{logPrefix} El ciclo finaliza porque no se realizó un commit con cambios efectivos.")
            # No intentar guardar historial si no hubo cambio real
            return False # Indicar fallo (o falta de acción)

        # Si llegamos aquí, commitTuvoCambios es True
        huboCommitExitoso = True

        # 9. Actualizar y guardar historial (SOLO SI huboCommitExitoso es True)
        logging.info(f"{logPrefix} Actualizando y guardando historial.")
        historialRefactor.append(accionParseada.get('descripcion', 'Acción sin descripción'))
        if not guardarHistorial(historialRefactor):
             logging.error(f"{logPrefix} Falló el guardado del historial, pero el commit ya está hecho.")
             # No devolver False aquí, el commit es lo principal

        logging.info(f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
        return True # Devuelve True solo si hubo un commit real y exitoso

    except Exception as e:
        logging.critical(f"{logPrefix} Error inesperado durante la ejecución principal: {e}", exc_info=True)
        try:
            logging.info(f"{logPrefix} Intentando descartar cambios locales debido a error inesperado...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        except Exception as e_clean:
            logging.error(f"{logPrefix} Falló intento de limpieza tras error: {e_clean}")
        return False

# Punto de entrada principal del script
if __name__ == "__main__":
    configurarLogging()

    parser = argparse.ArgumentParser(
        description="Agente de Refactorización de Código con IA (Gemini).",
        epilog="Ejecuta un ciclo de refactorización. Usa --modo-test para hacer push después de un commit exitoso."
    )
    parser.add_argument(
        "--modo-test", action="store_true",
        help="Activa modo prueba: Ejecuta un ciclo y hace push si hay commit efectivo."
    )
    args = parser.parse_args()

    logging.info(f"Iniciando script principal. Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    try:
        commitRealizado = ejecutarProcesoPrincipal() # Ahora devuelve True solo si hubo commit efectivo

        if commitRealizado:
            logging.info("Proceso principal completado: Se realizó un commit con cambios.")
            if args.modo_test:
                logging.info("Modo Test activado: Intentando hacer push a origin...")
                ramaPush = getattr(settings, 'RAMATRABAJO', 'refactor')
                if manejadorGit.hacerPush(settings.RUTACLON, ramaPush):
                    logging.info(f"Modo Test: Push a la rama '{ramaPush}' realizado con éxito.")
                    sys.exit(0) # Éxito total
                else:
                    logging.error(f"Modo Test: Falló el push a la rama '{ramaPush}'.")
                    sys.exit(1) # Salir con error (commit hecho, push falló)
            else:
                logging.info("Modo Test desactivado. Commit realizado localmente, no se hizo push.")
                sys.exit(0) # Éxito (commit local)
        else:
            # Si ejecutarProcesoPrincipal devuelve False, ya se loguearon los detalles
            logging.warning("Proceso principal finalizó sin realizar un commit efectivo.")
            sys.exit(1) # Salir con error leve/advertencia

    except Exception as e:
        logging.critical(f"Error fatal no manejado en el bloque principal: {e}", exc_info=True)
        sys.exit(2)