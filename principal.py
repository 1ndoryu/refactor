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
    if log_raiz.handlers:
        logging.info("configurarLogging: Logging ya configurado.")
        return

    nivelLog = logging.INFO
    formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'

    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    log_raiz.addHandler(consolaHandler)

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
    logging.info("="*50)
    logging.info("="*50)
    logging.info("configurarLogging: Sistema de logging configurado.")
    logging.info(f"configurarLogging: Nivel de log establecido a {logging.getLevelName(log_raiz.level)}")


# Funciones para manejar el historial persistente
def cargarHistorial():
    # ... (no changes needed here) ...
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
    # ... (no changes needed here) ...
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
    # ... (no changes needed here) ...
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

# *** MODIFIED FUNCTION TO HANDLE ERRORS AND HISTORY ***
def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    logging.info(f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN =====")
    cicloExitosoConCommit = False # Flag for final return status
    historialRefactor = [] # Initialize here to ensure it's always available
    accionParseada = None # Initialize action info

    try:
        if not settings.GEMINIAPIKEY or not settings.REPOSITORIOURL:
            logging.critical(f"{logPrefix} Configuración esencial faltante (GEMINI_API_KEY o REPOSITORIOURL). Abortando.")
            return False # Cannot proceed

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
        if archivos is None: return False
        if not archivos:
            logging.warning(f"{logPrefix} No se encontraron archivos relevantes. Terminando ciclo.")
            return False

        codigoAAnalizar = analizadorCodigo.leerArchivos(archivos, settings.RUTACLON)
        if not codigoAAnalizar: return False
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
            # *** Record Gemini failure in history? Maybe not, as no action was attempted. ***
            # Consider adding if needed: historialRefactor.append("[ERROR] No se pudo obtener sugerencia de Gemini.")
            # guardarHistorial(historialRefactor)
            return False

        # 6. Parsear sugerencia
        logging.info(f"{logPrefix} Parseando sugerencia de Gemini...")
        accionParseada = parsearSugerencia(sugerenciaJson)
        if not accionParseada:
            logging.error(f"{logPrefix} Sugerencia inválida o no soportada. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            # *** Record Parsing failure in history? ***
            # historialRefactor.append(f"[ERROR] Sugerencia de Gemini inválida o no soportada: {sugerenciaJson}")
            # guardarHistorial(historialRefactor)
            return False

        if accionParseada.get("accion") == "no_accion":
            logging.info(f"{logPrefix} Gemini sugirió 'no_accion': {accionParseada.get('descripcion', '')}. Terminando ciclo.")
            # *** Record 'no_action' in history? Optional, can be noisy. ***
            # razonamientoNoAccion = accionParseada.get('razonamiento', 'Sin razonamiento.')
            # historialRefactor.append(f"[INFO] Acción 'no_accion' sugerida. Razón: {razonamientoNoAccion}")
            # guardarHistorial(historialRefactor)
            return False # No commit was made

        # --- Intento de Aplicación y Commit ---
        descripcionIntento = accionParseada.get('descripcion', 'Acción sin descripción')
        razonamientoIntento = accionParseada.get('razonamiento', 'Sin razonamiento proporcionado.')

        # 7. Aplicar cambios
        logging.info(f"{logPrefix} Aplicando cambios sugeridos: {descripcionIntento}")
        exitoAplicar, mensajeErrorAplicar = aplicadorCambios.aplicarCambio(accionParseada, settings.RUTACLON)

        if not exitoAplicar:
            # --- Caso: Aplicación Fallida ---
            logging.error(f"{logPrefix} Falló la aplicación de cambios: {mensajeErrorAplicar}")
            # Construir entrada de historial de error
            entradaHistorialError = f"[ERROR] Aplicación fallida: {descripcionIntento}. Razón: {mensajeErrorAplicar}. Razonamiento original: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)

            logging.info(f"{logPrefix} Intentando descartar cambios locales tras fallo...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                logging.critical(f"{logPrefix} ¡FALLO CRÍTICO! No se aplicaron cambios Y no se pudieron descartar. ¡Revisión manual requerida en {settings.RUTACLON}!")
            else:
                logging.info(f"{logPrefix} Cambios locales (si los hubo) descartados tras fallo en aplicación.")

            # Guardar historial CON el error y salir
            guardarHistorial(historialRefactor)
            return False # Indicar fallo del ciclo

        # Si llegamos aquí, exitoAplicar fue True
        logging.info(f"{logPrefix} Cambios aplicados localmente con éxito.")

        # 8. Hacer commit
        logging.info(f"{logPrefix} Realizando commit en rama '{settings.RAMATRABAJO}'...")
        mensajeCommit = descripcionIntento # Usar la descripción ya obtenida
        if len(mensajeCommit.encode('utf-8')) > 4000:
             mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
             logging.warning(f"{logPrefix} Mensaje de commit truncado.")
        elif len(mensajeCommit.splitlines()[0]) > 72:
             logging.warning(f"{logPrefix} La primera línea del mensaje de commit supera los 72 caracteres.")

        # Intentar commit
        exitoCommitIntento = manejadorGit.hacerCommit(settings.RUTACLON, mensajeCommit)

        if not exitoCommitIntento:
            # --- Caso: Comando 'git commit' falló ---
            # hacerCommit ya loguea el error
            logging.error(f"{logPrefix} Falló el comando 'git commit'.")
             # Construir entrada de historial de error
            entradaHistorialError = f"[ERROR] Cambios aplicados, pero 'git commit' falló. Intento: {descripcionIntento}. Razonamiento: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)

            logging.info(f"{logPrefix} Intentando descartar cambios locales tras fallo de commit...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON) # Intentar limpiar

             # Guardar historial CON el error y salir
            guardarHistorial(historialRefactor)
            return False # Indicar fallo del ciclo

        # Verificar si el commit tuvo cambios reales
        comandoCheckDiff = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
        commitTuvoCambios = False
        errorVerificandoCommit = False
        try:
            resultadoCheck = subprocess.run(comandoCheckDiff, cwd=settings.RUTACLON, capture_output=True)
            if resultadoCheck.returncode == 1:
                logging.info(f"{logPrefix} Commit realizado con éxito y contiene cambios.")
                commitTuvoCambios = True
            elif resultadoCheck.returncode == 0:
                 logging.warning(f"{logPrefix} Aunque 'git commit' no dio error, no se detectaron cambios efectivos en el último commit. La acción no tuvo efecto real.")
                 # Intentar deshacer el commit vacío
                 try:
                     manejadorGit.ejecutarComando(['git', 'reset', '--soft', 'HEAD~1'], cwd=settings.RUTACLON)
                     manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                     logging.info(f"{logPrefix} Intento de revertir commit vacío/sin efecto realizado.")
                 except Exception as e_revert:
                      logging.error(f"{logPrefix} No se pudo revertir el commit potencialmente vacío/sin efecto: {e_revert}")
            else:
                 stderr_log = resultadoCheck.stderr.decode('utf-8', errors='ignore').strip()
                 logging.error(f"{logPrefix} Error inesperado al verificar diferencias del commit (código {resultadoCheck.returncode}). Stderr: {stderr_log}")
                 errorVerificandoCommit = True

        except FileNotFoundError:
             logging.error(f"{logPrefix} Error: Comando 'git' no encontrado al verificar commit.")
             errorVerificandoCommit = True
        except Exception as e:
             logging.error(f"{logPrefix} Error inesperado verificando el último commit: {e}")
             errorVerificandoCommit = True

        # --- Decidir estado final y guardar historial ---
        if commitTuvoCambios:
            # --- Caso: Éxito Real ---
            cicloExitosoConCommit = True
            logging.info(f"{logPrefix} Actualizando y guardando historial de éxito.")
            entradaHistorialExito = f"[ÉXITO] {descripcionIntento}"
            if razonamientoIntento and razonamientoIntento != 'Sin razonamiento proporcionado.':
                entradaHistorialExito += f" Razonamiento: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialExito)
            guardarHistorial(historialRefactor)
            logging.info(f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
            return True # Éxito final

        else:
            # --- Caso: Cambios Aplicados pero Commit Sin Efecto o Falló Verificación ---
            razonFalloCommit = "No se detectaron cambios efectivos tras el commit."
            if errorVerificandoCommit:
                razonFalloCommit = "Error al verificar los cambios del commit."
            elif not exitoCommitIntento: # Redundante por chequeo anterior, pero seguro
                 razonFalloCommit = "El comando 'git commit' falló previamente."

            logging.warning(f"{logPrefix} El ciclo finaliza porque no se realizó un commit con cambios efectivos. Razón: {razonFalloCommit}")
            entradaHistorialError = f"[ERROR] Cambios aplicados, pero sin commit efectivo. Intento: {descripcionIntento}. Razón: {razonFalloCommit}. Razonamiento: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)

            # Guardar historial CON el error y salir
            guardarHistorial(historialRefactor)
            return False # Indicar fallo del ciclo

    except Exception as e:
        # --- Caso: Error Inesperado General ---
        logging.critical(f"{logPrefix} Error inesperado durante la ejecución principal: {e}", exc_info=True)
        # Intentar grabar un error genérico en el historial si es posible
        if historialRefactor is not None and accionParseada is not None:
             descripcionIntento = accionParseada.get('descripcion', 'Acción desconocida por error temprano')
             entradaHistorialError = f"[ERROR CRÍTICO] Error inesperado durante el proceso. Intento: {descripcionIntento}. Detalle: {e}"
             historialRefactor.append(entradaHistorialError)
             guardarHistorial(historialRefactor)
        elif historialRefactor is not None:
             historialRefactor.append(f"[ERROR CRÍTICO] Error inesperado antes de procesar acción. Detalle: {e}")
             guardarHistorial(historialRefactor)

        try:
            logging.info(f"{logPrefix} Intentando descartar cambios locales debido a error inesperado...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        except Exception as e_clean:
            logging.error(f"{logPrefix} Falló intento de limpieza tras error: {e_clean}")
        return False # Indicar fallo


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
        # ejecutarProcesoPrincipal ahora devuelve True solo si hubo commit efectivo Y guardó historial éxito
        # Devuelve False si hubo algún error (y guarda historial de error) o si no hubo commit efectivo
        commitRealizado = ejecutarProcesoPrincipal()

        if commitRealizado:
            logging.info("Proceso principal completado: Se realizó un commit con cambios y se guardó historial.")
            if args.modo_test:
                logging.info("Modo Test activado: Intentando hacer push a origin...")
                ramaPush = getattr(settings, 'RAMATRABAJO', 'refactor')
                if manejadorGit.hacerPush(settings.RUTACLON, ramaPush):
                    logging.info(f"Modo Test: Push a la rama '{ramaPush}' realizado con éxito.")
                    sys.exit(0) # Éxito total
                else:
                    logging.error(f"Modo Test: Falló el push a la rama '{ramaPush}'.")
                    # *** Considerar grabar este fallo de PUSH en historial? ***
                    # Podría ser útil, pero complica el flujo de retorno. Por ahora, solo log y exit(1).
                    # historial = cargarHistorial()
                    # historial.append(f"[ERROR] Commit realizado localmente, pero PUSH falló a rama {ramaPush}")
                    # guardarHistorial(historial)
                    sys.exit(1) # Salir con error (commit hecho, push falló)
            else:
                logging.info("Modo Test desactivado. Commit realizado localmente, no se hizo push.")
                sys.exit(0) # Éxito (commit local)
        else:
            # Si devuelve False, ya se loguearon los detalles Y se guardó historial de error/no acción
            logging.warning("Proceso principal finalizó sin realizar un commit efectivo o con errores (ver historial y logs).")
            sys.exit(1) # Salir con código de error/advertencia

    except Exception as e:
        logging.critical(f"Error fatal no manejado en el bloque principal: {e}", exc_info=True)
        # Intentar grabar historial de error fatal si es posible
        try:
            historial = cargarHistorial() # Recargar por si acaso
            historial.append(f"[ERROR FATAL] Error no manejado en __main__: {e}")
            guardarHistorial(historial)
        except:
            pass # Evitar errores al intentar loguear el error final
        sys.exit(2) # Código de error grave