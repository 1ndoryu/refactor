# principal.py
import logging
import sys
import os
import json
import argparse
import subprocess  # Necesario para el check de git diff
from config import settings
# Importar módulos del núcleo
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios  # Ahora se usará de forma diferente

# Configuración del logging (sin cambios)


def configurarLogging():
    # ... (igual que antes) ...
    log_raiz = logging.getLogger()
    if log_raiz.handlers:
        return
    nivelLog = logging.INFO
    formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'
    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    log_raiz.addHandler(consolaHandler)
    try:
        rutaLogArchivo = os.path.join(
            settings.RUTA_BASE_PROYECTO, "refactor.log")
        os.makedirs(os.path.dirname(rutaLogArchivo), exist_ok=True)
        archivoHandler = logging.FileHandler(rutaLogArchivo, encoding='utf-8')
        archivoHandler.setFormatter(
            logging.Formatter(formatoLog, fechaFormato))
        log_raiz.addHandler(archivoHandler)
    except Exception as e:
        log_raiz.error(
            f"configurarLogging: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}")
    log_raiz.setLevel(nivelLog)
    logging.info("="*50)
    logging.info("configurarLogging: Sistema de logging configurado.")
    logging.info(
        f"configurarLogging: Nivel de log establecido a {logging.getLevelName(log_raiz.level)}")


# Funciones de historial (sin cambios)
def cargarHistorial():
    # ... (igual que antes) ...
    logPrefix = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    if not os.path.exists(rutaArchivoHistorial):
        logging.info(
            f"{logPrefix} Archivo de historial no encontrado en {rutaArchivoHistorial}. Iniciando historial vacío.")
        return historial
    try:
        with open(rutaArchivoHistorial, 'r', encoding='utf-8') as f:
            historial = [line.strip() for line in f if line.strip()]
        logging.info(
            f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        logging.error(
            f"{logPrefix} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío.")
        historial = []
    return historial


def guardarHistorial(historial):
    # ... (igual que antes) ...
    logPrefix = "guardarHistorial:"
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    try:
        os.makedirs(os.path.dirname(rutaArchivoHistorial), exist_ok=True)
        with open(rutaArchivoHistorial, 'w', encoding='utf-8') as f:
            for entrada in historial:
                f.write(entrada.strip() + "\n")
        logging.info(
            f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({len(historial)} entradas).")
        return True
    except Exception as e:
        logging.error(
            f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False

# --- NUEVA: Función para parsear la DECISIÓN de Gemini (Paso 1) ---


def parsearDecisionGemini(decisionJson):
    logPrefix = "parsearDecisionGemini:"
    accionesSoportadas = [  # Acciones de INTENCIÓN
        "mover_funcion", "mover_clase", "modificar_codigo_en_archivo",
        "crear_archivo", "eliminar_archivo", "crear_directorio", "no_accion"
        # Nota: 'mover_codigo' genérico se vuelve más específico
        # 'modificar_archivo' se renombra para claridad
    ]

    if not isinstance(decisionJson, dict):
        logging.error(
            f"{logPrefix} La decisión recibida no es un diccionario JSON válido. Tipo: {type(decisionJson)}. Valor: {decisionJson}")
        return None

    tipoAnalisis = decisionJson.get("tipo_analisis")
    accionPropuesta = decisionJson.get("accion_propuesta")
    descripcion = decisionJson.get("descripcion")
    parametrosAccion = decisionJson.get("parametros_accion")
    archivosRelevantes = decisionJson.get(
        "archivos_relevantes")  # Crucial para Paso 2
    razonamiento = decisionJson.get("razonamiento")

    if tipoAnalisis != "refactor_decision":
        logging.error(
            f"{logPrefix} JSON inválido. Falta o es incorrecto 'tipo_analisis'. Debe ser 'refactor_decision'. JSON: {decisionJson}")
        return None

    if not accionPropuesta or not isinstance(parametrosAccion, dict) or not descripcion or not isinstance(archivosRelevantes, list):
        logging.error(f"{logPrefix} Formato JSON de decisión inválido. Faltan campos clave ('accion_propuesta', 'descripcion', 'parametros_accion', 'archivos_relevantes') o tipos incorrectos. JSON: {decisionJson}")
        return None

    if accionPropuesta not in accionesSoportadas:
        logging.error(
            f"{logPrefix} Acción propuesta '{accionPropuesta}' NO RECONOCIDA o NO SOPORTADA. Válidas: {accionesSoportadas}. JSON: {decisionJson}")
        return None

    if accionPropuesta != "no_accion" and not archivosRelevantes:
        logging.warning(
            f"{logPrefix} Acción '{accionPropuesta}' requiere 'archivos_relevantes', pero la lista está vacía. Esto podría ser un error.")
        # Podríamos decidir fallar aquí si es crítico
        # return None

    if accionPropuesta == "no_accion":
        logging.info(
            f"{logPrefix} Decisión 'no_accion' recibida y parseada. Razón: {razonamiento or 'No proporcionada'}")
        # No necesitamos 'archivos_relevantes' para no_accion
    else:
        logging.info(
            f"{logPrefix} Decisión parseada exitosamente. Acción propuesta: {accionPropuesta}. Archivos relevantes: {archivosRelevantes}")

    return decisionJson  # Devolver el diccionario completo validado

# --- NUEVA: Función para parsear el RESULTADO de Gemini (Paso 2) ---


def parsearResultadoEjecucion(resultadoJson):
    logPrefix = "parsearResultadoEjecucion:"

    if not isinstance(resultadoJson, dict):
        logging.error(
            f"{logPrefix} El resultado recibido no es un diccionario JSON válido. Tipo: {type(resultadoJson)}. Valor: {resultadoJson}")
        return None

    tipoResultado = resultadoJson.get("tipo_resultado")
    archivosModificados = resultadoJson.get("archivos_modificados")

    if tipoResultado != "ejecucion_cambio":
        logging.error(
            f"{logPrefix} JSON inválido. Falta o es incorrecto 'tipo_resultado'. Debe ser 'ejecucion_cambio'. JSON: {resultadoJson}")
        return None

    if not isinstance(archivosModificados, dict):
        logging.error(
            f"{logPrefix} Formato JSON de resultado inválido. Falta 'archivos_modificados' o no es un diccionario. JSON: {resultadoJson}")
        return None

    # Validación adicional: verificar que las claves sean strings (rutas) y los valores strings (contenido)
    for ruta, contenido in archivosModificados.items():
        if not isinstance(ruta, str) or not isinstance(contenido, str):
            logging.error(
                f"{logPrefix} Entrada inválida en 'archivos_modificados'. Clave o valor no son strings. Clave: {ruta} (tipo {type(ruta)}), Valor (tipo {type(contenido)}). JSON: {resultadoJson}")
            return None

    logging.info(
        f"{logPrefix} Resultado de ejecución parseado exitosamente. {len(archivosModificados)} archivos a modificar.")
    # Devolver solo el diccionario de archivos y su nuevo contenido
    return archivosModificados


def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    logging.info(
        f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN (ENFOQUE DOS PASOS) =====")
    cicloExitosoConCommit = False
    historialRefactor = []
    decisionParseada = None
    resultadoEjecucion = None
    codigoProyectoCompleto = ""  # Contexto para Paso 1
    contextoReducido = ""  # Contexto para Paso 2

    try:
        # 1. Verificar configuración esencial (sin cambios)
        if not settings.GEMINIAPIKEY or not settings.REPOSITORIOURL:
            logging.critical(
                f"{logPrefix} Configuración esencial faltante. Abortando.")
            return False

        # 2. Cargar historial (sin cambios)
        historialRefactor = cargarHistorial()

        # 3. Preparar repositorio local (sin cambios)
        logging.info(f"{logPrefix} Preparando repositorio local...")
        if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(
                f"{logPrefix} No se pudo preparar el repositorio. Abortando ciclo.")
            return False
        logging.info(
            f"{logPrefix} Repositorio listo y en la rama '{settings.RAMATRABAJO}'.")

        # ---------------------------------------------------------------
        # PASO 1: ANÁLISIS Y DECISIÓN (GEMINI CON CONTEXTO COMPLETO)
        # ---------------------------------------------------------------
        logging.info(f"{logPrefix} --- INICIO PASO 1: ANÁLISIS Y DECISIÓN ---")

        # 4a. Analizar código del proyecto COMPLETO
        logging.info(
            f"{logPrefix} Analizando código COMPLETO del proyecto en {settings.RUTACLON}...")
        extensiones = getattr(settings, 'EXTENSIONESPERMITIDAS', None)
        ignorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', None)
        todosLosArchivos = analizadorCodigo.listarArchivosProyecto(
            settings.RUTACLON, extensiones, ignorados)

        if todosLosArchivos is None:
            logging.error(
                f"{logPrefix} Error al listar archivos del proyecto. Abortando ciclo.")
            return False
        if not todosLosArchivos:
            logging.warning(
                f"{logPrefix} No se encontraron archivos relevantes. Terminando ciclo.")
            return False

        # Leer contenido COMPLETO
        codigoProyectoCompleto = analizadorCodigo.leerArchivos(
            todosLosArchivos, settings.RUTACLON)
        if not codigoProyectoCompleto:
            logging.error(
                f"{logPrefix} Error al leer el contenido de los archivos. Abortando ciclo.")
            return False
        tamanoKB_completo = len(codigoProyectoCompleto.encode('utf-8')) / 1024
        logging.info(
            f"{logPrefix} Código fuente completo leído ({len(todosLosArchivos)} archivos, {tamanoKB_completo:.2f} KB).")

        # 5a. Obtener DECISIÓN de Gemini (usando el contexto completo)
        logging.info(
            f"{logPrefix} Obteniendo DECISIÓN de Gemini (modelo: {settings.MODELOGEMINI})...")
        historialRecienteTexto = "\n".join(
            historialRefactor[-settings.N_HISTORIAL_CONTEXTO:])

        # --- LLAMADA A LA NUEVA FUNCIÓN DE ANÁLISIS ---
        decisionJson = analizadorCodigo.obtenerDecisionRefactor(
            codigoProyectoCompleto, historialRecienteTexto)

        if not decisionJson:
            logging.error(
                f"{logPrefix} No se recibió una DECISIÓN válida de Gemini (Paso 1). Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(
                settings.RUTACLON)  # Por si acaso
            historialRefactor.append(
                "[ERROR] Paso 1: No se pudo obtener una decisión válida de Gemini.")
            guardarHistorial(historialRefactor)
            return False

        # 6a. Parsear y validar la DECISIÓN recibida
        logging.info(f"{logPrefix} Parseando DECISIÓN de Gemini...")
        decisionParseada = parsearDecisionGemini(decisionJson)

        if not decisionParseada:
            logging.error(
                f"{logPrefix} Decisión inválida, mal formada o no soportada. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            sugerencia_str = json.dumps(decisionJson)
            sugerencia_log = sugerencia_str[:500] + \
                ('...' if len(sugerencia_str) > 500 else '')
            historialRefactor.append(
                f"[ERROR] Paso 1: Decisión de Gemini inválida o no soportada: {sugerencia_log}")
            guardarHistorial(historialRefactor)
            return False

        # Manejar caso 'no_accion' explícito ya en el Paso 1
        if decisionParseada.get("accion_propuesta") == "no_accion":
            razonamientoNoAccion = decisionParseada.get(
                'razonamiento', 'Sin razonamiento especificado.')
            logging.info(
                f"{logPrefix} Gemini decidió 'no_accion'. Razón: {razonamientoNoAccion}. Terminando ciclo.")
            historialRefactor.append(
                f"[INFO] Acción 'no_accion' decidida. Razón: {razonamientoNoAccion}")
            guardarHistorial(historialRefactor)
            # Importante: descartar cambios por si la lectura/análisis inicial modificó algo (poco probable)
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False  # No hubo error, pero no se hará commit

        # Si llegamos aquí, tenemos una decisión válida y no es 'no_accion'
        logging.info(
            f"{logPrefix} --- FIN PASO 1: Decisión válida recibida: {decisionParseada.get('accion_propuesta')} ---")

        # ---------------------------------------------------------------
        # PASO 2: EJECUCIÓN (GEMINI CON CONTEXTO REDUCIDO)
        # ---------------------------------------------------------------
        logging.info(f"{logPrefix} --- INICIO PASO 2: EJECUCIÓN ---")

        # 4b. Leer contenido SÓLO de archivos relevantes para la acción
        archivosRelevantes = decisionParseada.get("archivos_relevantes", [])
        # Convertir rutas relativas a absolutas para leerlas
        rutasAbsRelevantes = []
        for rutaRel in archivosRelevantes:
            # Usar _validar_y_normalizar_ruta SIN asegurar existencia, por si se va a crear
            rutaAbs = aplicadorCambios._validar_y_normalizar_ruta(
                rutaRel, settings.RUTACLON, asegurar_existencia=False)
            if rutaAbs:
                # Solo añadir si existe o si la acción es crearla (manejar caso creación)
                accion = decisionParseada.get("accion_propuesta")
                params = decisionParseada.get("parametros_accion", {})
                # Incluir si existe o si es el archivo a crear
                if os.path.exists(rutaAbs) or \
                    (accion == "crear_archivo" and params.get("archivo") == rutaRel) or \
                    (accion == "mover_funcion" and params.get("archivo_destino") == rutaRel and not os.path.exists(rutaAbs)) or \
                        (accion == "mover_clase" and params.get("archivo_destino") == rutaRel and not os.path.exists(rutaAbs)):
                    rutasAbsRelevantes.append(rutaAbs)
                else:
                    logging.warning(
                        f"{logPrefix} Archivo relevante '{rutaRel}' no existe y no parece ser el objetivo de una acción 'crear'. Se omitirá del contexto del Paso 2.")

            else:
                logging.error(
                    f"{logPrefix} Ruta relevante inválida '{rutaRel}' proporcionada por Gemini en Paso 1. Abortando.")
                historialRefactor.append(
                    f"[ERROR] Paso 2: Ruta relevante inválida '{rutaRel}' en decisión.")
                guardarHistorial(historialRefactor)
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False

        if not rutasAbsRelevantes and decisionParseada.get("accion_propuesta") not in ["crear_directorio", "eliminar_archivo"]:
            # Si no hay archivos existentes relevantes (y no es crear dir/eliminar file), algo falló
            logging.error(f"{logPrefix} No se encontraron archivos existentes para el contexto reducido del Paso 2. Acción: {decisionParseada.get('accion_propuesta')}. Archivos intentados: {archivosRelevantes}. Abortando.")
            historialRefactor.append(
                "[ERROR] Paso 2: No se pudieron leer archivos para contexto reducido.")
            guardarHistorial(historialRefactor)
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        # Leer el contenido reducido
        if rutasAbsRelevantes:
            contextoReducido = analizadorCodigo.leerArchivos(
                rutasAbsRelevantes, settings.RUTACLON)
            if contextoReducido is None:  # Manejar error de lectura aquí también
                logging.error(
                    f"{logPrefix} Error al leer el contenido de los archivos relevantes para el Paso 2. Abortando ciclo.")
                historialRefactor.append(
                    "[ERROR] Paso 2: Fallo crítico leyendo contexto reducido.")
                guardarHistorial(historialRefactor)
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False
            tamanoKB_reducido = len(contextoReducido.encode('utf-8')) / 1024
            logging.info(
                f"{logPrefix} Contexto reducido leído ({len(rutasAbsRelevantes)} archivos, {tamanoKB_reducido:.2f} KB).")
        else:
            # Caso especial para crear_directorio o eliminar_archivo donde no se necesita contexto de archivo
            logging.info(
                f"{logPrefix} Acción '{decisionParseada.get('accion_propuesta')}' no requiere contexto de archivo para Paso 2.")
            contextoReducido = ""  # Vacío explícitamente

        # 5b. Obtener RESULTADO (contenido modificado) de Gemini
        logging.info(
            f"{logPrefix} Obteniendo RESULTADO de ejecución de Gemini (contexto reducido)...")
        # --- LLAMADA A LA NUEVA FUNCIÓN DE EJECUCIÓN ---
        # Pasamos la decisión completa y el contexto reducido
        resultadoJson = analizadorCodigo.ejecutarAccionConGemini(
            decisionParseada, contextoReducido)

        if not resultadoJson:
            logging.error(
                f"{logPrefix} No se recibió un RESULTADO válido de Gemini (Paso 2). Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            historialRefactor.append(
                f"[ERROR] Paso 2: No se pudo obtener el resultado de ejecución de Gemini para '{decisionParseada.get('descripcion')}'.")
            guardarHistorial(historialRefactor)
            return False

        # 6b. Parsear y validar el RESULTADO recibido
        logging.info(
            f"{logPrefix} Parseando RESULTADO de ejecución de Gemini...")
        # La función devuelve directamente el dict {ruta: contenido} o None
        resultadoEjecucion = parsearResultadoEjecucion(resultadoJson)

        if not resultadoEjecucion:
            # Si parsearResultadoEjecucion devuelve None, significa que el JSON era inválido o incompleto.
            logging.error(
                f"{logPrefix} Resultado de ejecución inválido o mal formado. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            resultado_str = json.dumps(resultadoJson)
            resultado_log = resultado_str[:500] + \
                ('...' if len(resultado_str) > 500 else '')
            historialRefactor.append(
                f"[ERROR] Paso 2: Resultado de ejecución de Gemini inválido: {resultado_log}")
            guardarHistorial(historialRefactor)
            return False

        # Si llegamos aquí, tenemos el diccionario {rutaRelativa: nuevoContenido}
        logging.info(
            f"{logPrefix} --- FIN PASO 2: Resultado de ejecución válido recibido. ---")

        # 7. Aplicar los cambios (¡NUEVA LÓGICA!)
        # Usaremos una función simplificada en aplicadorCambios o directamente aquí
        descripcionIntento = decisionParseada.get(
            'descripcion', 'Acción sin descripción')
        razonamientoIntento = decisionParseada.get(
            'razonamiento', 'Sin razonamiento.')  # Útil para historial

        logging.info(
            f"{logPrefix} Aplicando cambios generados por Gemini (sobrescribiendo archivos)...")
        # La nueva función espera el diccionario {rutaRel: contenido} y la ruta base
        exitoAplicar, mensajeErrorAplicar = aplicadorCambios.aplicarCambiosSobrescritura(
            resultadoEjecucion,
            settings.RUTACLON,
            # Pasar info de la acción original por si hay que crear/eliminar
            decisionParseada.get("accion_propuesta"),
            decisionParseada.get("parametros_accion", {})
        )

        if not exitoAplicar:
            # --- Caso: Aplicación Fallida ---
            logging.error(
                f"{logPrefix} Falló la aplicación de cambios (sobrescritura): {mensajeErrorAplicar}")
            entradaHistorialError = f"[ERROR] Aplicación fallida (Paso 2): {descripcionIntento}. Razón: {mensajeErrorAplicar}. Razonamiento original: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)
            logging.info(
                f"{logPrefix} Intentando descartar cambios locales tras fallo...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                logging.critical(
                    f"{logPrefix} ¡FALLO CRÍTICO! No se aplicaron cambios Y TAMPOCO se pudieron descartar. ¡Revisión manual URGENTE!")
                historialRefactor.append(
                    "[ERROR CRÍTICO] FALLO AL DESCARTAR CAMBIOS TRAS ERROR DE APLICACIÓN (PASO 2).")
            else:
                logging.info(
                    f"{logPrefix} Cambios locales (si los hubo) descartados tras fallo.")
            guardarHistorial(historialRefactor)
            return False

        # --- Si llegamos aquí, exitoAplicar fue True ---
        logging.info(
            f"{logPrefix} Cambios (sobrescritura) aplicados localmente con éxito.")

        # 8. Hacer commit de los cambios (Lógica sin cambios significativos, usa la descripción del Paso 1)
        logging.info(
            f"{logPrefix} Realizando commit en rama '{settings.RAMATRABAJO}'...")
        mensajeCommit = descripcionIntento
        if len(mensajeCommit.encode('utf-8')) > 4000:
            mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
            logging.warning(f"{logPrefix} Mensaje de commit truncado.")
        elif len(mensajeCommit.splitlines()[0]) > 72:
            logging.warning(
                f"{logPrefix} Primera línea del mensaje de commit larga.")

        exitoCommitIntento = manejadorGit.hacerCommit(
            settings.RUTACLON, mensajeCommit)

        if not exitoCommitIntento:
            # --- Caso: Comando 'git commit' falló ---
            logging.error(f"{logPrefix} Falló el comando 'git commit'.")
            entradaHistorialError = f"[ERROR] Cambios aplicados, PERO 'git commit' FALLÓ. Intento: {descripcionIntento}. Razonamiento: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)
            logging.info(
                f"{logPrefix} Intentando descartar cambios locales tras fallo de commit...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                logging.critical(
                    f"{logPrefix} ¡FALLO CRÍTICO! Commit falló Y NO SE PUDO DESCARTAR. ¡Revisión manual URGENTE!")
                historialRefactor.append(
                    "[ERROR CRÍTICO] FALLO AL DESCARTAR CAMBIOS TRAS ERROR DE COMMIT.")
            else:
                logging.info(
                    f"{logPrefix} Cambios locales descartados tras fallo de commit.")
            guardarHistorial(historialRefactor)
            return False

        # 9. Verificar si el commit introdujo cambios efectivos (Sin cambios aquí)
        logging.info(
            f"{logPrefix} Verificando si el commit introdujo cambios efectivos...")
        comandoCheckDiff = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
        commitTuvoCambios = False
        errorVerificandoCommit = False
        try:
            resultadoCheck = subprocess.run(
                comandoCheckDiff, cwd=settings.RUTACLON, capture_output=True)
            if resultadoCheck.returncode == 1:
                logging.info(
                    f"{logPrefix} Commit realizado con éxito y contiene cambios efectivos.")
                commitTuvoCambios = True
            elif resultadoCheck.returncode == 0:
                logging.warning(
                    f"{logPrefix} Commit ejecutado, pero no se detectaron cambios efectivos. ¿Acción redundante o Gemini generó contenido idéntico?")
                # Intentar deshacer commit vacío
                logging.info(
                    f"{logPrefix} Intentando revertir commit sin efecto...")
                try:
                    if manejadorGit.ejecutarComando(['git', 'reset', '--soft', 'HEAD~1'], cwd=settings.RUTACLON):
                        if manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                            logging.info(
                                f"{logPrefix} Commit sin efecto revertido y cambios descartados.")
                        else:
                            logging.error(
                                f"{logPrefix} Reset soft OK, pero falló descarte posterior.")
                    else:
                        logging.error(
                            f"{logPrefix} No se pudo revertir commit sin efecto.")
                except Exception as e_revert:
                    logging.error(
                        f"{logPrefix} Excepción al revertir commit vacío: {e_revert}")
                commitTuvoCambios = False
            else:
                stderr_log = resultadoCheck.stderr.decode(
                    'utf-8', errors='ignore').strip()
                logging.error(
                    f"{logPrefix} Error inesperado verificando diff del commit (código {resultadoCheck.returncode}). Stderr: {stderr_log}")
                errorVerificandoCommit = True
                commitTuvoCambios = False

        except Exception as e:
            logging.error(
                f"{logPrefix} Error inesperado verificando diff del commit: {e}", exc_info=True)
            errorVerificandoCommit = True
            commitTuvoCambios = False

        # 10. Decidir estado final y guardar historial
        if commitTuvoCambios:
            cicloExitosoConCommit = True
            logging.info(
                f"{logPrefix} Ciclo completado con éxito. Registrando en historial.")
            entradaHistorialExito = f"[ÉXITO] {descripcionIntento}"
            if razonamientoIntento and razonamientoIntento.lower() not in ['sin razonamiento proporcionado.', 'sin razonamiento.', 'no aplica']:
                entradaHistorialExito += f" Razonamiento: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialExito)
            guardarHistorial(historialRefactor)
            logging.info(
                f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
            return True  # Éxito final

        else:
            razonFalloCommitEfectivo = "No se detectaron cambios efectivos tras el commit."
            if errorVerificandoCommit:
                razonFalloCommitEfectivo = "Error al verificar los cambios del commit."
            logging.warning(
                f"{logPrefix} Ciclo finaliza sin commit efectivo. Razón: {razonFalloCommitEfectivo}")
            entradaHistorialError = f"[ERROR] Cambios aplicados, pero SIN commit efectivo. Intento: {descripcionIntento}. Razón: {razonFalloCommitEfectivo}. Razonamiento Gemini: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)
            guardarHistorial(historialRefactor)
            return False  # Fallo o no éxito

    except Exception as e:
        logging.critical(
            f"{logPrefix} Error inesperado y no capturado durante la ejecución principal: {e}", exc_info=True)
        if historialRefactor is not None:
            descripcionIntento = "Acción desconocida (error temprano)"
            if decisionParseada and isinstance(decisionParseada.get("descripcion"), str):
                descripcionIntento = decisionParseada.get("descripcion")
            entradaHistorialError = f"[ERROR CRÍTICO] Error inesperado durante el proceso. Intento: {descripcionIntento}. Detalle: {e}"
            historialRefactor.append(entradaHistorialError)
            guardarHistorial(historialRefactor)
        try:
            if 'settings' in locals() and hasattr(settings, 'RUTACLON'):
                logging.info(
                    f"{logPrefix} Intentando descartar cambios locales debido a error inesperado...")
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        except Exception as e_clean:
            logging.error(
                f"{logPrefix} Falló el intento de limpieza tras error inesperado: {e_clean}")
        return False


# Punto de entrada principal (sin cambios significativos)
if __name__ == "__main__":
    configurarLogging()
    parser = argparse.ArgumentParser(
        description="Agente de Refactorización de Código con IA (Gemini) - Enfoque Dos Pasos.",
        epilog="Ejecuta un ciclo: 1. Analiza y Decide, 2. Ejecuta y Commitea. Usa --modo-test para hacer push."
    )
    parser.add_argument(
        "--modo-test", action="store_true",
        help="Activa modo prueba: Si el ciclo realiza un commit efectivo, intenta hacer push."
    )
    args = parser.parse_args()
    logging.info(
        f"Iniciando script principal (Dos Pasos). Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    try:
        commitRealizadoConExito = ejecutarProcesoPrincipal()

        if commitRealizadoConExito:
            logging.info(
                "Proceso principal completado: Se realizó un commit con cambios efectivos.")
            if args.modo_test:
                logging.info("Modo Test activado: Intentando hacer push...")
                ramaPush = getattr(settings, 'RAMATRABAJO', 'main')
                if manejadorGit.hacerPush(settings.RUTACLON, ramaPush):
                    logging.info(
                        f"Modo Test: Push a la rama '{ramaPush}' realizado con éxito.")
                    sys.exit(0)
                else:
                    logging.error(
                        f"Modo Test: Falló el push a la rama '{ramaPush}'.")
                    # historial = cargarHistorial() # Opcional: añadir error de push al historial
                    # historial.append(f"[ERROR] MODO TEST: Commit local OK, pero PUSH falló a rama {ramaPush}")
                    # guardarHistorial(historial)
                    sys.exit(1)
            else:
                logging.info(
                    "Modo Test desactivado. Commit local, no se hizo push.")
                sys.exit(0)
        else:
            logging.warning(
                "Proceso principal finalizó sin realizar un commit efectivo o con errores.")
            sys.exit(1)

    except Exception as e:
        logging.critical(
            f"Error fatal no manejado en __main__: {e}", exc_info=True)
        try:
            historial = cargarHistorial()
            historial.append(
                f"[ERROR FATAL] Error no manejado en __main__: {e}")
            guardarHistorial(historial)
        except Exception as e_hist_fatal:
            logging.error(
                f"No se pudo guardar historial del error fatal: {e_hist_fatal}")
        sys.exit(2)
