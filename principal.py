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
    # Usar logging.getLogger() directamente aquí para configurar el logger raíz
    log_raiz = logging.getLogger()
    if log_raiz.handlers:  # Evitar añadir handlers múltiples si ya está configurado
        # Usar logging porque log_raiz es local a esta función
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
        # Asegurarse que la ruta base existe para el log de refactorización
        rutaLogArchivo = os.path.join(
            settings.RUTA_BASE_PROYECTO, "refactor.log")
        os.makedirs(os.path.dirname(rutaLogArchivo), exist_ok=True)
        archivoHandler = logging.FileHandler(rutaLogArchivo, encoding='utf-8')
        archivoHandler.setFormatter(
            logging.Formatter(formatoLog, fechaFormato))
        log_raiz.addHandler(archivoHandler)
    except Exception as e:
        # Usar logging aquí porque log_raiz puede no estar completamente listo si falla el archivo
        logging.error(
            f"configurarLogging: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}")

    log_raiz.setLevel(nivelLog)
    # Log inicial después de configurar handlers (usando logging)
    logging.info("="*50)
    logging.info("configurarLogging: Sistema de logging configurado.")
    logging.info(
        f"configurarLogging: Nivel de log establecido a {logging.getLevelName(log_raiz.level)}")


# Funciones para manejar el historial persistente
def cargarHistorial():
    logPrefix = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    if not os.path.exists(rutaArchivoHistorial):
        # CORRECCIÓN: Usar logging.info en lugar de log.info
        logging.info(
            f"{logPrefix} Archivo de historial no encontrado en {rutaArchivoHistorial}. Iniciando historial vacío.")
        return historial

    try:
        with open(rutaArchivoHistorial, 'r', encoding='utf-8') as f:
            historial = [line.strip() for line in f if line.strip()]
        # CORRECCIÓN: Usar logging.info en lugar de log.info
        logging.info(
            f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        # CORRECCIÓN: Usar logging.error en lugar de log.error
        logging.error(
            f"{logPrefix} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío.")
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
        # CORRECCIÓN: Usar logging.info en lugar de log.info
        logging.info(
            f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({len(historial)} entradas).")
        return True
    except Exception as e:
        # CORRECCIÓN: Usar logging.error en lugar de log.error
        logging.error(
            f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False

# Función para parsear y validar la sugerencia JSON de Gemini


def parsearSugerencia(sugerenciaJson):
    logPrefix = "parsearSugerencia:"
    # --- Lista de acciones EXPLÍCITAMENTE soportadas por aplicadorCambios.py ---
    accionesSoportadas = [
        "modificar_archivo",
        "mover_archivo",
        "crear_archivo",
        "eliminar_archivo",
        "crear_directorio",
        "no_accion"
        # Si añades más lógica en aplicadorCambios.py, añádelas aquí.
    ]

    # Aquí sí usamos logging. directamente, está bien
    if not isinstance(sugerenciaJson, dict):
        logging.error(
            f"{logPrefix} La sugerencia recibida no es un diccionario JSON válido. Tipo: {type(sugerenciaJson)}. Valor: {sugerenciaJson}")
        return None

    accion = sugerenciaJson.get("accion")
    detalles = sugerenciaJson.get("detalles")
    descripcion = sugerenciaJson.get("descripcion")

    if not accion or not isinstance(detalles, dict) or not descripcion:
        logging.error(
            f"{logPrefix} Formato JSON inválido. Faltan 'accion', 'detalles' o 'descripcion', o 'detalles' no es un dict. JSON: {sugerenciaJson}")
        return None

    # --- Validación Estricta de la Acción ---
    if accion not in accionesSoportadas:
        logging.error(
            f"{logPrefix} Acción '{accion}' NO RECONOCIDA o NO SOPORTADA por el script. Acciones válidas: {accionesSoportadas}. JSON recibido: {sugerenciaJson}")
        return None
    # ----------------------------------------

    # # (Opcional: Mantener si necesitas validación de detalles para acciones específicas)
    # accionesConDetallesObligatorios = [
    #     "modificar_archivo", "mover_archivo", "crear_archivo", "eliminar_archivo", "crear_directorio"]
    # # Si la acción requiere detalles y no los tiene (y no es 'no_accion')
    # if accion in accionesConDetallesObligatorios and not detalles and accion != "no_accion":
    #     logging.error(
    #         f"{logPrefix} Acción '{accion}' requiere 'detalles' no vacíos, pero está vacío o ausente. JSON: {sugerenciaJson}")
    #     return None

    if accion == "no_accion":
        logging.info(
            f"{logPrefix} Sugerencia 'no_accion' recibida y parseada.")
    # El warning anterior sobre acciones no reconocidas ya no es necesario
    # porque ahora las rechazamos explícitamente con el error de arriba.

    logging.info(
        f"{logPrefix} Sugerencia parseada exitosamente. Acción: {accion}")
    return sugerenciaJson

# Función principal que orquesta el proceso de refactorización.


def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    # Usar logging. directamente está bien
    logging.info(f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN =====")
    huboCommitExitoso = False

    if not settings.GEMINIAPIKEY or not settings.REPOSITORIOURL:
        logging.critical(
            f"{logPrefix} Configuración esencial faltante (GEMINI_API_KEY o REPOSITORIOURL). Verifique .env y config/settings.py. Abortando.")
        return False

    # Permitir la URL de ejemplo para pruebas iniciales, pero mantener la advertencia.
    # if "github.com/usuario/repo.git" in settings.REPOSITORIOURL:
    #     logging.warning(
    #         f"{logPrefix} La URL del repositorio parece ser la de ejemplo ('{settings.REPOSITORIOURL}'). Asegúrese que es correcta.")

    # --- PASOS DEL PROCESO ---
    try:
        # 2. Cargar historial
        historialRefactor = cargarHistorial()

        # 3. Preparar repositorio
        logging.info(
            f"{logPrefix} Preparando repositorio local en '{settings.RUTACLON}' en la rama '{settings.RAMATRABAJO}'...")
        if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(
                f"{logPrefix} No se pudo preparar el repositorio. Abortando ciclo.")
            return False
        logging.info(
            f"{logPrefix} Repositorio listo y en la rama '{settings.RAMATRABAJO}'.")

        # 4. Analizar código
        logging.info(
            f"{logPrefix} Analizando código del proyecto en {settings.RUTACLON}...")
        extensiones = getattr(settings, 'EXTENSIONESPERMITIDAS', None)
        ignorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', None)
        archivos = analizadorCodigo.listarArchivosProyecto(
            settings.RUTACLON, extensiones, ignorados)

        if archivos is None:
            logging.error(
                f"{logPrefix} Error al listar archivos. Abortando ciclo.")
            return False
        if not archivos:
            logging.warning(
                f"{logPrefix} No se encontraron archivos relevantes. Terminando ciclo.")
            return False

        codigoAAnalizar = analizadorCodigo.leerArchivos(
            archivos, settings.RUTACLON)
        if not codigoAAnalizar:
            logging.error(
                f"{logPrefix} No se pudo leer contenido de archivos. Abortando ciclo.")
            return False
        tamanoBytes = len(codigoAAnalizar.encode('utf-8'))
        tamanoKB = tamanoBytes / 1024
        logging.info(
            f"{logPrefix} Código fuente leído ({len(archivos)} archivos, {tamanoKB:.2f} KB).")

        # 5. Obtener sugerencia Gemini
        logging.info(
            f"{logPrefix} Obteniendo sugerencia de Gemini (modelo: {settings.MODELOGEMINI})...")
        historialRecienteTexto = "\n".join(
            historialRefactor[-settings.N_HISTORIAL_CONTEXTO:])
        sugerenciaJson = analizadorCodigo.analizarConGemini(
            codigoAAnalizar, historialRecienteTexto)

        if not sugerenciaJson:
            logging.error(
                f"{logPrefix} No se recibió sugerencia válida de Gemini. Abortando ciclo.")
            # Intentar descartar cambios locales por si el análisis previo modificó algo inesperado
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        # 6. Parsear sugerencia (AHORA MÁS ESTRICTO)
        logging.info(f"{logPrefix} Parseando sugerencia de Gemini...")
        accionParseada = parsearSugerencia(
            sugerenciaJson)  # Usa la versión modificada
        if not accionParseada:
            # El error ya se logueó dentro de parsearSugerencia
            logging.error(
                f"{logPrefix} Sugerencia inválida o no soportada. Abortando ciclo.")
            # Intentar descartar cambios locales
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        if accionParseada.get("accion") == "no_accion":
            logging.info(
                f"{logPrefix} Gemini sugirió 'no_accion': {accionParseada.get('descripcion', '')}. Terminando ciclo.")
            # No hubo commit, pero el ciclo terminó "correctamente" según la IA
            return False  # Devolvemos False porque no hubo commit

        # 7. Aplicar cambios
        logging.info(f"{logPrefix} Aplicando cambios sugeridos...")
        exitoAplicar = aplicadorCambios.aplicarCambio(
            accionParseada, settings.RUTACLON)
        if not exitoAplicar:
            logging.error(
                f"{logPrefix} Falló la aplicación de cambios. Intentando descartar...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                logging.critical(
                    f"{logPrefix} ¡FALLO CRÍTICO! No se aplicaron cambios Y no se pudieron descartar. ¡Revisión manual requerida!")
            else:
                logging.info(
                    f"{logPrefix} Cambios locales descartados tras fallo.")
            return False

        logging.info(f"{logPrefix} Cambios aplicados localmente.")

        # 8. Hacer commit
        logging.info(
            f"{logPrefix} Realizando commit en rama '{settings.RAMATRABAJO}'...")
        mensajeCommit = accionParseada.get(
            'descripcion', 'Refactorización automática AI')
        # Truncar mensaje si es muy largo para evitar problemas con Git
        # Límite generoso, Git suele ser más estricto con la línea del asunto
        if len(mensajeCommit.encode('utf-8')) > 4000:
            # Cortar a una longitud segura
            mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
            logging.warning(
                f"{logPrefix} Mensaje de commit truncado por longitud excesiva.")
        # Advertir si la primera línea (asunto) es larga
        elif len(mensajeCommit.splitlines()[0]) > 72:
            logging.warning(
                f"{logPrefix} La primera línea del mensaje de commit supera los 72 caracteres.")

        exitoCommit = manejadorGit.hacerCommit(
            settings.RUTACLON, mensajeCommit)
        if not exitoCommit:
            # El commit puede fallar si no hay cambios (ej. si aplicarCambio devolvió True pero no hizo nada)
            # o por otros errores (hooks, config git). hacerCommit ya loguea advertencias/errores.
            logging.error(
                f"{logPrefix} Falló el commit o no había nada que commitear. Ver logs de manejadorGit.")
            # Si falló porque no había cambios, podríamos querer continuar, pero
            # si falló por otra razón, es mejor detenerse. Por seguridad, detenemos.
            # Intentamos descartar por si 'git add' dejó algo staged aunque commit fallara
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        huboCommitExitoso = True
        logging.info(f"{logPrefix} Commit realizado con éxito.")

        # 9. Actualizar y guardar historial
        logging.info(f"{logPrefix} Actualizando y guardando historial.")
        # Guardar la descripción completa en el historial, no la truncada
        historialRefactor.append(accionParseada.get(
            'descripcion', 'Acción sin descripción'))
        guardarHistorial(historialRefactor)

        logging.info(
            f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
        return huboCommitExitoso  # Devuelve True

    except Exception as e:
        # Captura cualquier otra excepción inesperada durante el proceso
        logging.critical(
            f"{logPrefix} Error inesperado durante la ejecución principal: {e}", exc_info=True)
        # Intentar limpiar si es posible, pero con cuidado
        try:
            logging.info(
                f"{logPrefix} Intentando descartar cambios locales debido a error inesperado...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        except Exception as e_clean:
            logging.error(
                f"{logPrefix} Falló intento de limpieza tras error: {e_clean}")
        return False  # Indicar fallo


# Punto de entrada principal del script
if __name__ == "__main__":
    configurarLogging()  # Configurar logging primero

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

    logging.info(
        f"Iniciando script principal. Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    try:
        commitRealizado = ejecutarProcesoPrincipal()

        if commitRealizado:
            logging.info("Proceso principal completado: Se realizó un commit.")
            if args.modo_test:
                logging.info(
                    "Modo Test activado: Intentando hacer push a origin...")
                # Asegurarse que RAMATRABAJO está definida en settings
                # Usar default por si acaso
                ramaPush = getattr(settings, 'RAMATRABAJO', 'refactor')
                if manejadorGit.hacerPush(settings.RUTACLON, ramaPush):
                    logging.info(
                        f"Modo Test: Push a la rama '{ramaPush}' realizado con éxito.")
                    sys.exit(0)  # Éxito total
                else:
                    logging.error(
                        f"Modo Test: Falló el push a la rama '{ramaPush}'.")
                    sys.exit(1)  # Salir con error (commit hecho, push falló)
            else:
                logging.info(
                    "Modo Test desactivado. Commit realizado localmente, no se hizo push.")
                sys.exit(0)  # Éxito (commit local)
        else:
            logging.warning(
                "Proceso principal finalizó sin realizar un commit.")
            sys.exit(1)  # Salir con error leve/advertencia si no hubo commit

    except Exception as e:
        # Captura errores incluso antes de entrar a ejecutarProcesoPrincipal o después
        logging.critical(
            f"Error fatal no manejado en el bloque principal: {e}", exc_info=True)
        sys.exit(2)  # Código de error diferente para fallos muy graves
