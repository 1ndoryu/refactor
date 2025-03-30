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
from nucleo import aplicadorCambios

# Configuración del logging (sin cambios)
def configurarLogging():
    # ... (código existente sin cambios) ...
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

# Funciones de historial (cargar sin cambios, guardar sin cambios en firma)
def cargarHistorial():
    logPrefix = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    if not os.path.exists(rutaArchivoHistorial):
        logging.info(
            f"{logPrefix} Archivo de historial no encontrado en {rutaArchivoHistorial}. Iniciando historial vacío.")
        return historial
    try:
        with open(rutaArchivoHistorial, 'r', encoding='utf-8') as f:
            # Leer como un bloque y luego dividir para manejar entradas multilínea potenciales
            contenido_historial = f.read()
            # Asumimos que cada entrada completa está separada por una línea específica o un patrón
            # Si cada entrada es una línea simple, el list comprehension original estaba bien
            # Si queremos guardar entradas multilínea, necesitamos un delimitador claro
            # Por simplicidad, mantendremos una línea por entrada por ahora.
            historial = [line.strip() for line in contenido_historial.splitlines() if line.strip()]
        logging.info(
            f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
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
                # Asegurar que la entrada sea string y quitar espacios extra al inicio/fin
                entrada_str = str(entrada).strip()
                f.write(entrada_str + "\n")
                # Podríamos añadir un separador explícito si las entradas son multilínea
                # f.write("--- FIN ENTRADA HISTORIAL ---\n")
        logging.info(
            f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({len(historial)} entradas).")
        return True
    except Exception as e:
        logging.error(
            f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False

# --- REVISADO: Función para parsear la DECISIÓN de Gemini (Paso 1) ---
def parsearDecisionGemini(decisionJson):
    logPrefix = "parsearDecisionGemini:"
    # Lista actualizada si cambian las acciones soportadas
    accionesSoportadas = [
        "mover_funcion", "mover_clase", "modificar_codigo_en_archivo",
        "crear_archivo", "eliminar_archivo", "crear_directorio", "no_accion"
    ]

    if not isinstance(decisionJson, dict):
        logging.error(
            f"{logPrefix} La decisión recibida no es un diccionario JSON válido. Tipo: {type(decisionJson)}. Valor: {decisionJson}")
        return None

    tipoAnalisis = decisionJson.get("tipo_analisis")
    accionPropuesta = decisionJson.get("accion_propuesta")
    descripcion = decisionJson.get("descripcion")
    parametrosAccion = decisionJson.get("parametros_accion")
    archivosRelevantes = decisionJson.get("archivos_relevantes")
    razonamiento = decisionJson.get("razonamiento") # Campo ahora obligatorio

    # Validaciones más estrictas basadas en el nuevo prompt
    if tipoAnalisis != "refactor_decision":
        logging.error(
            f"{logPrefix} JSON inválido. Falta o es incorrecto 'tipo_analisis'. Debe ser 'refactor_decision'. JSON: {decisionJson}")
        return None

    if not all([accionPropuesta, descripcion, isinstance(parametrosAccion, dict), isinstance(archivosRelevantes, list), razonamiento]):
        logging.error(f"{logPrefix} Formato JSON de decisión inválido. Faltan campos clave OBLIGATORIOS ('accion_propuesta', 'descripcion', 'parametros_accion', 'archivos_relevantes', 'razonamiento') o tipos incorrectos. JSON: {decisionJson}")
        return None

    if accionPropuesta not in accionesSoportadas:
        logging.error(
            f"{logPrefix} Acción propuesta '{accionPropuesta}' NO RECONOCIDA o NO SOPORTADA. Válidas: {accionesSoportadas}. JSON: {decisionJson}")
        return None

    # 'archivos_relevantes' puede estar vacío para 'crear_directorio' o si se crea un archivo nuevo sin contexto
    if accionPropuesta not in ["no_accion", "crear_directorio"] and not archivosRelevantes:
        # Podría ser válido si crea un archivo nuevo basado solo en propósito
        if accionPropuesta == "crear_archivo" and parametrosAccion.get("archivo"):
             logging.info(f"{logPrefix} Acción 'crear_archivo' sin archivos relevantes preexistentes, se creará basado en propósito.")
        elif accionPropuesta == "eliminar_archivo" and parametrosAccion.get("archivo"):
             logging.info(f"{logPrefix} Acción 'eliminar_archivo' no necesita archivos relevantes existentes.")
        else:
            logging.warning(
                f"{logPrefix} Acción '{accionPropuesta}' usualmente requiere 'archivos_relevantes' existentes, pero la lista está vacía. Esto podría ser un error en la decisión de Gemini.")
            # Considerar si fallar aquí es más seguro
            # return None

    if accionPropuesta == "no_accion":
        logging.info(
            f"{logPrefix} Decisión 'no_accion' recibida y parseada. Razón: {razonamiento or 'No proporcionada'}")
    else:
        logging.info(
            f"{logPrefix} Decisión parseada exitosamente. Acción: {accionPropuesta}. Archivos relevantes: {archivosRelevantes}. Razonamiento: {razonamiento[:100]}...") # Log corto del razonamiento

    # Devolver el diccionario completo validado
    return decisionJson

# --- REVISADO: Función para parsear el RESULTADO de Gemini (Paso 2) ---
def parsearResultadoEjecucion(resultadoJson, decisionPrevia):
    """Parsea el resultado de ejecución, validando contra la decisión previa."""
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
        # Permitir diccionario vacío para acciones como eliminar/crear_dir
        accionOriginal = decisionPrevia.get("accion_propuesta")
        if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
            logging.info(f"{logPrefix} Resultado de ejecución para '{accionOriginal}' recibido correctamente con 'archivos_modificados' vacío.")
            return {} # Devolver dict vacío es válido aquí
        else:
            logging.error(
                f"{logPrefix} Formato JSON de resultado inválido. Falta 'archivos_modificados' o no es un diccionario (y la acción '{accionOriginal}' debería modificar archivos). JSON: {resultadoJson}")
            return None

    # Validación adicional: verificar que las claves sean strings (rutas) y los valores strings (contenido)
    for ruta, contenido in archivosModificados.items():
        # Usar os.sep universalmente no es ideal, pero Gemini debería usar '/'
        # Validar que no intente salirse con '..'
        if '..' in ruta.split('/'):
             logging.error(f"{logPrefix} Ruta sospechosa '{ruta}' en 'archivos_modificados' contiene '..'. Rechazando.")
             return None
        if not isinstance(ruta, str) or not ruta:
            logging.error(f"{logPrefix} Clave inválida en 'archivos_modificados' (no es string o está vacía): {ruta}. JSON: {resultadoJson}")
            return None
        if not isinstance(contenido, str):
            # Podría ser None o '', que es aceptable para crear archivo vacío? Mejor exigir string.
            logging.error(f"{logPrefix} Valor inválido para ruta '{ruta}' en 'archivos_modificados' (no es string): Tipo {type(contenido)}. JSON: {resultadoJson}")
            return None

    num_archivos = len(archivosModificados)
    if num_archivos > 0 :
        logging.info(
            f"{logPrefix} Resultado de ejecución parseado exitosamente. {num_archivos} archivo(s) a modificar/crear.")
    # else: # Ya logueado arriba para casos específicos
    #     logging.info(f"{logPrefix} Resultado de ejecución parseado, sin archivos a modificar (acción: {decisionPrevia.get('accion_propuesta')}).")

    # Devolver solo el diccionario de archivos y su nuevo contenido
    return archivosModificados


# --- NUEVA: Función para formatear entrada de historial ---
def formatearEntradaHistorial(estado, decision, resultado=None, mensaje_error=None):
    """Crea una cadena de texto formateada para el historial."""
    partes = [f"[{estado}]"] # [ÉXITO], [ERROR], [INFO]

    if decision:
        partes.append(f"Acción Decidida: {decision.get('accion_propuesta', 'N/A')}")
        partes.append(f"Descripción: {decision.get('descripcion', 'N/A')}")
        # Incluir el razonamiento detallado
        razonamiento = decision.get('razonamiento', 'No proporcionado').strip()
        # Formatear razonamiento para mejor legibilidad en el log
        razonamiento_formateado = '\n  '.join(razonamiento.splitlines())
        partes.append(f"Razonamiento (Paso 1):\n  {razonamiento_formateado}")
        partes.append(f"Parámetros: {json.dumps(decision.get('parametros_accion', {}))}")
        partes.append(f"Archivos Relevantes (Paso 1): {decision.get('archivos_relevantes', [])}")

    if estado == "ÉXITO":
        if resultado is not None: # resultado es el dict {ruta: contenido}
             archivos_afectados = list(resultado.keys())
             partes.append(f"Resultado (Paso 2): Éxito. Archivos modificados/creados: {archivos_afectados}")
        else: # Caso de éxito sin modificación (ej. no_accion bien manejada)
             partes.append("Resultado (Paso 2): Éxito (sin cambios aplicados/commit).")

    elif estado == "ERROR" or estado == "ERROR CRÍTICO":
        if mensaje_error:
            partes.append(f"Mensaje de Error: {mensaje_error}")
        if resultado is not None:
             # Podría haber un resultado parcial antes del error
             archivos_intentados = list(resultado.keys())
             partes.append(f"Resultado Parcial/Fallido (Paso 2): Se intentó operar sobre {archivos_intentados} (si aplica).")
        else:
            partes.append("Resultado (Paso 2): Falló antes o durante la ejecución.")

    # Unir todas las partes con saltos de línea para una entrada legible
    return "\n".join(partes)


# --- REVISADO: Proceso Principal con Historial Detallado ---
def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    logging.info(
        f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN (ENFOQUE DOS PASOS DETALLADO) =====")
    cicloExitosoConCommit = False
    historialRefactor = []
    decisionParseada = None
    resultadoEjecucionParseado = None # Guardará el dict {ruta: contenido} o {}
    codigoProyectoCompleto = ""
    contextoReducido = ""
    entradaHistorialActual = "" # Para construir la entrada final

    try:
        # 1. Verificar configuración esencial (sin cambios)
        if not settings.GEMINIAPIKEY or not settings.REPOSITORIOURL:
            logging.critical(f"{logPrefix} Configuración esencial faltante. Abortando.")
            # Guardar historial si ya se cargó algo? No, error muy temprano.
            return False

        # 2. Cargar historial (sin cambios en llamada)
        historialRefactor = cargarHistorial()

        # 3. Preparar repositorio local (sin cambios en llamada)
        logging.info(f"{logPrefix} Preparando repositorio local...")
        if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(f"{logPrefix} No se pudo preparar el repositorio. Abortando ciclo.")
            # Guardar historial aquí es difícil si el repo falló
            return False
        logging.info(
            f"{logPrefix} Repositorio listo y en la rama '{settings.RAMATRABAJO}'.")

        # ---------------------------------------------------------------
        # PASO 1: ANÁLISIS Y DECISIÓN DETALLADA (GEMINI CON CONTEXTO COMPLETO)
        # ---------------------------------------------------------------
        logging.info(f"{logPrefix} --- INICIO PASO 1: ANÁLISIS Y DECISIÓN DETALLADA ---")

        # 4a. Analizar código del proyecto COMPLETO (sin cambios)
        logging.info(
            f"{logPrefix} Analizando código COMPLETO del proyecto en {settings.RUTACLON}...")
        extensiones = getattr(settings, 'EXTENSIONESPERMITIDAS', None)
        ignorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', None)
        todosLosArchivos = analizadorCodigo.listarArchivosProyecto(
            settings.RUTACLON, extensiones, ignorados)

        if todosLosArchivos is None:
            logging.error(f"{logPrefix} Error al listar archivos del proyecto. Abortando ciclo.")
            return False # No guardar historial, error básico
        if not todosLosArchivos:
            logging.warning(f"{logPrefix} No se encontraron archivos relevantes. Terminando ciclo.")
            return False # No guardar historial

        codigoProyectoCompleto = analizadorCodigo.leerArchivos(
            todosLosArchivos, settings.RUTACLON)
        if not codigoProyectoCompleto:
            logging.error(f"{logPrefix} Error al leer el contenido de los archivos. Abortando ciclo.")
            return False # No guardar historial

        tamanoKB_completo = len(codigoProyectoCompleto.encode('utf-8')) / 1024
        logging.info(
            f"{logPrefix} Código fuente completo leído ({len(todosLosArchivos)} archivos, {tamanoKB_completo:.2f} KB).")

        # 5a. Obtener DECISIÓN DETALLADA de Gemini
        logging.info(
            f"{logPrefix} Obteniendo DECISIÓN DETALLADA de Gemini (modelo: {settings.MODELOGEMINI})...")
        historialRecienteTexto = "\n---\n".join( # Usar separador claro para el historial en prompt
            historialRefactor[-settings.N_HISTORIAL_CONTEXTO:])

        decisionJson = analizadorCodigo.obtenerDecisionRefactor(
            codigoProyectoCompleto, historialRecienteTexto)

        if not decisionJson:
            # Error ya logueado en obtenerDecisionRefactor
            logging.error(f"{logPrefix} No se recibió una DECISIÓN válida de Gemini (Paso 1). Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            # Crear entrada de historial de error
            error_msg = "Paso 1: No se pudo obtener una decisión válida de Gemini."
            entradaHistorialActual = formatearEntradaHistorial("ERROR", None, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor)
            return False

        # 6a. Parsear y validar la DECISIÓN DETALLADA recibida
        logging.info(f"{logPrefix} Parseando DECISIÓN DETALLADA de Gemini...")
        decisionParseada = parsearDecisionGemini(decisionJson) # Usa la función revisada

        if not decisionParseada:
            # Error ya logueado en parsearDecisionGemini
            logging.error(f"{logPrefix} Decisión inválida, mal formada o no soportada. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            sugerencia_str = json.dumps(decisionJson)
            sugerencia_log = sugerencia_str[:500] + ('...' if len(sugerencia_str) > 500 else '')
            error_msg = f"Paso 1: Decisión de Gemini inválida o no soportada: {sugerencia_log}"
            # Intentar usar el JSON original para formatear si es posible
            entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionJson if isinstance(decisionJson, dict) else None, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor)
            return False

        # Guardar el razonamiento ahora que la decisión es válida
        razonamiento_paso1 = decisionParseada.get('razonamiento', 'No proporcionado')
        logging.info(f"{logPrefix} Razonamiento del Paso 1:\n{razonamiento_paso1}")

        # Manejar caso 'no_accion' explícito
        if decisionParseada.get("accion_propuesta") == "no_accion":
            logging.info(f"{logPrefix} Gemini decidió 'no_accion'. Terminando ciclo.")
            # Crear entrada de historial INFO
            entradaHistorialActual = formatearEntradaHistorial("INFO", decisionParseada)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor)
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False # No hubo error, pero no se hará commit

        # Decisión válida y no es 'no_accion'
        logging.info(
            f"{logPrefix} --- FIN PASO 1: Decisión válida recibida: {decisionParseada.get('accion_propuesta')} ---")

        # ---------------------------------------------------------------
        # PASO 2: EJECUCIÓN PRECISA (GEMINI CON CONTEXTO REDUCIDO)
        # ---------------------------------------------------------------
        logging.info(f"{logPrefix} --- INICIO PASO 2: EJECUCIÓN PRECISA ---")

        # 4b. Leer contenido SÓLO de archivos relevantes (lógica existente parece OK)
        archivosRelevantes = decisionParseada.get("archivos_relevantes", [])
        rutasAbsRelevantes = []
        rutasRelLeidas = [] # Para loguear qué se leyó realmente
        for rutaRel in archivosRelevantes:
            # Validar SIN asegurar existencia (puede ser un archivo a crear)
            rutaAbs = aplicadorCambios._validar_y_normalizar_ruta(
                rutaRel, settings.RUTACLON, asegurar_existencia=False)
            if rutaAbs:
                 # Leer solo si existe físicamente
                 if os.path.exists(rutaAbs) and os.path.isfile(rutaAbs):
                     rutasAbsRelevantes.append(rutaAbs)
                     rutasRelLeidas.append(rutaRel)
                 else:
                     logging.debug(f"{logPrefix} Archivo relevante '{rutaRel}' no existe localmente, no se incluirá en contexto reducido (puede ser creado en Paso 2).")
            else:
                # Error crítico si Gemini da una ruta inválida en la decisión
                logging.error(
                    f"{logPrefix} Ruta relevante inválida '{rutaRel}' proporcionada por Gemini en Paso 1. Abortando.")
                error_msg = f"Paso 2: Ruta relevante inválida '{rutaRel}' en decisión del Paso 1."
                entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionParseada, mensaje_error=error_msg)
                historialRefactor.append(entradaHistorialActual)
                guardarHistorial(historialRefactor)
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False

        # Comprobar si se necesita contexto y si se leyó algo
        accion_actual = decisionParseada.get("accion_propuesta")
        requiere_contexto = accion_actual not in ["crear_directorio", "eliminar_archivo", "crear_archivo"]
        if requiere_contexto and not rutasAbsRelevantes:
            # Si la acción necesita contexto (ej. mover, modificar) pero no encontramos archivos existentes
            logging.error(f"{logPrefix} No se encontraron archivos existentes para el contexto reducido del Paso 2. Acción: {accion_actual}. Archivos relevantes listados: {archivosRelevantes}. Abortando.")
            error_msg = f"Paso 2: No se pudieron leer archivos existentes para contexto reducido. Acción: {accion_actual}. Archivos esperados: {archivosRelevantes}"
            entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionParseada, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor)
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        # Leer el contenido reducido si hay archivos
        if rutasAbsRelevantes:
            contextoReducido = analizadorCodigo.leerArchivos(rutasAbsRelevantes, settings.RUTACLON)
            if contextoReducido is None: # Error durante la lectura
                logging.error(f"{logPrefix} Error crítico al leer el contenido de los archivos relevantes {rutasRelLeidas} para el Paso 2. Abortando ciclo.")
                error_msg = f"Paso 2: Fallo crítico leyendo contexto reducido de {rutasRelLeidas}."
                entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionParseada, mensaje_error=error_msg)
                historialRefactor.append(entradaHistorialActual)
                guardarHistorial(historialRefactor)
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False
            tamanoKB_reducido = len(contextoReducido.encode('utf-8')) / 1024
            logging.info(f"{logPrefix} Contexto reducido leído ({len(rutasRelLeidas)} archivos: {rutasRelLeidas}, {tamanoKB_reducido:.2f} KB).")
        else:
            logging.info(f"{logPrefix} Acción '{accion_actual}' no requiere leer archivos existentes para el contexto del Paso 2 (o los archivos relevantes no existían).")
            contextoReducido = "" # Vacío explícitamente

        # 5b. Obtener RESULTADO (contenido modificado) de Gemini
        logging.info(f"{logPrefix} Obteniendo RESULTADO de ejecución de Gemini (contexto reducido, siguiendo decisión)...")
        # --- LLAMADA A LA NUEVA FUNCIÓN DE EJECUCIÓN ---
        resultadoJson = analizadorCodigo.ejecutarAccionConGemini(
            decisionParseada, contextoReducido) # Pasa la decisión completa

        if not resultadoJson:
            logging.error(f"{logPrefix} No se recibió un RESULTADO válido de Gemini (Paso 2). Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            error_msg = f"Paso 2: No se pudo obtener el resultado de ejecución de Gemini."
            entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionParseada, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor)
            return False

        # 6b. Parsear y validar el RESULTADO recibido
        logging.info(f"{logPrefix} Parseando RESULTADO de ejecución de Gemini...")
        # Pasar la decisión original a la función de parseo para validación contextual
        resultadoEjecucionParseado = parsearResultadoEjecucion(resultadoJson, decisionParseada)

        if resultadoEjecucionParseado is None: # Devuelve None si hay error de formato/validación
            logging.error(f"{logPrefix} Resultado de ejecución inválido, mal formado o incoherente con la decisión. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            resultado_str = json.dumps(resultadoJson)
            resultado_log = resultado_str[:500] + ('...' if len(resultado_str) > 500 else '')
            error_msg = f"Paso 2: Resultado de ejecución de Gemini inválido o incoherente: {resultado_log}"
            # Formatear con la decisión que llevó a este resultado erróneo
            entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionParseada, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor)
            return False

        # Si llegamos aquí, tenemos el diccionario {rutaRelativa: nuevoContenido} o {}
        num_archivos_modificar = len(resultadoEjecucionParseado)
        logging.info(f"{logPrefix} --- FIN PASO 2: Resultado de ejecución válido recibido ({num_archivos_modificar} archivos a modificar/crear). ---")

        # 7. Aplicar los cambios (usando aplicadorCambios.py)
        logging.info(f"{logPrefix} Aplicando cambios generados por Gemini (Paso 2)...")
        # La función aplicarCambiosSobrescritura ya maneja acciones como delete/create_dir
        exitoAplicar, mensajeErrorAplicar = aplicadorCambios.aplicarCambiosSobrescritura(
            resultadoEjecucionParseado, # El dict {ruta: contenido} o {}
            settings.RUTACLON,
            decisionParseada.get("accion_propuesta"),
            decisionParseada.get("parametros_accion", {})
        )

        if not exitoAplicar:
            logging.error(f"{logPrefix} Falló la aplicación de cambios: {mensajeErrorAplicar}")
            error_msg = f"Aplicación fallida (Paso 2): {mensajeErrorAplicar}."
            # Formatear historial con el error específico de aplicación
            entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionParseada, resultado=resultadoEjecucionParseado, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)

            logging.info(f"{logPrefix} Intentando descartar cambios locales tras fallo de aplicación...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                logging.critical(f"{logPrefix} ¡FALLO CRÍTICO! No se aplicaron cambios Y TAMPOCO se pudieron descartar. ¡Revisión manual URGENTE!")
                # Añadir entrada crítica adicional al historial
                historialRefactor.append(formatearEntradaHistorial("ERROR CRÍTICO", decisionParseada, mensaje_error="FALLO AL DESCARTAR CAMBIOS TRAS ERROR DE APLICACIÓN (PASO 2)."))
            else:
                logging.info(f"{logPrefix} Cambios locales (si los hubo) descartados tras fallo.")

            guardarHistorial(historialRefactor)
            return False

        # --- Si llegamos aquí, exitoAplicar fue True ---
        logging.info(f"{logPrefix} Cambios aplicados localmente con éxito.")

        # 8. Hacer commit (Usa la descripción del Paso 1)
        logging.info(f"{logPrefix} Realizando commit en rama '{settings.RAMATRABAJO}'...")
        mensajeCommit = decisionParseada.get('descripcion', 'Refactorización automática por IA') # Fallback
        # Truncar mensaje si es muy largo (Git tiene límites)
        if len(mensajeCommit.encode('utf-8')) > 4000: # Límite práctico
            mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
            logging.warning(f"{logPrefix} Mensaje de commit truncado por longitud.")
        # Advertir si la primera línea es muy larga (convención Git)
        if '\n' in mensajeCommit and len(mensajeCommit.split('\n', 1)[0]) > 72:
            logging.warning(f"{logPrefix} Primera línea del mensaje de commit excede los 72 caracteres.")
        elif '\n' not in mensajeCommit and len(mensajeCommit) > 72:
             logging.warning(f"{logPrefix} Mensaje de commit (línea única) excede los 72 caracteres.")

        exitoCommitIntento = manejadorGit.hacerCommit(settings.RUTACLON, mensajeCommit)

        if not exitoCommitIntento:
            logging.error(f"{logPrefix} Falló el comando 'git commit'.")
            error_msg = "Cambios aplicados, PERO 'git commit' FALLÓ."
            entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionParseada, resultado=resultadoEjecucionParseado, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)

            logging.info(f"{logPrefix} Intentando descartar cambios locales tras fallo de commit...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                logging.critical(f"{logPrefix} ¡FALLO CRÍTICO! Commit falló Y NO SE PUDO DESCARTAR. ¡Revisión manual URGENTE!")
                historialRefactor.append(formatearEntradaHistorial("ERROR CRÍTICO", decisionParseada, mensaje_error="FALLO AL DESCARTAR CAMBIOS TRAS ERROR DE COMMIT."))
            else:
                logging.info(f"{logPrefix} Cambios locales descartados tras fallo de commit.")

            guardarHistorial(historialRefactor)
            return False

        # 9. Verificar si el commit introdujo cambios efectivos (sin cambios en lógica)
        logging.info(f"{logPrefix} Verificando si el commit introdujo cambios efectivos...")
        comandoCheckDiff = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
        commitTuvoCambios = False
        errorVerificandoCommit = False
        try:
            # check=False porque esperamos código 1 si hay cambios
            resultadoCheck = subprocess.run(
                comandoCheckDiff, cwd=settings.RUTACLON, capture_output=True, check=False)
            if resultadoCheck.returncode == 1:
                logging.info(
                    f"{logPrefix} Commit realizado con éxito y contiene cambios efectivos.")
                commitTuvoCambios = True
            elif resultadoCheck.returncode == 0:
                logging.warning(
                    f"{logPrefix} Commit ejecutado, pero no se detectaron cambios efectivos (git diff HEAD~1 HEAD --quiet devolvió 0). ¿Acción redundante o error?")
                # Intentar deshacer commit vacío (lógica existente)
                logging.info(f"{logPrefix} Intentando revertir commit sin efecto...")
                if manejadorGit.ejecutarComando(['git', 'reset', '--soft', 'HEAD~1'], cwd=settings.RUTACLON):
                    if manejadorGit.descartarCambiosLocales(settings.RUTACLON): # Descartar lo que sea que se añadió
                        logging.info(f"{logPrefix} Commit sin efecto revertido y cambios descartados.")
                    else:
                        logging.error(f"{logPrefix} Reset soft OK, pero falló descarte posterior. ¡Revisión manual recomendada!")
                        errorVerificandoCommit = True # Marcar como error para historial
                else:
                    logging.error(f"{logPrefix} No se pudo revertir commit sin efecto (reset --soft HEAD~1 falló).")
                    errorVerificandoCommit = True # Marcar como error
                commitTuvoCambios = False
            else:
                # Otro código de error
                stderr_log = resultadoCheck.stderr.decode('utf-8', errors='ignore').strip()
                logging.error(f"{logPrefix} Error inesperado verificando diff del commit (código {resultadoCheck.returncode}). Stderr: {stderr_log}")
                errorVerificandoCommit = True
                commitTuvoCambios = False

        except Exception as e:
            logging.error(f"{logPrefix} Excepción verificando diff del commit: {e}", exc_info=True)
            errorVerificandoCommit = True
            commitTuvoCambios = False

        # 10. Decidir estado final y guardar historial DETALLADO
        if commitTuvoCambios:
            cicloExitosoConCommit = True
            logging.info(f"{logPrefix} Ciclo completado con éxito. Registrando en historial.")
            # Formatear entrada de éxito
            entradaHistorialActual = formatearEntradaHistorial("ÉXITO", decisionParseada, resultado=resultadoEjecucionParseado)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor)
            logging.info(f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit efectivo realizado) =====")
            return True  # Éxito final

        else:
            # Si no hubo commit efectivo (o error verificando)
            razonFallo = "No se detectaron cambios efectivos tras el commit."
            if errorVerificandoCommit:
                razonFallo = "Error al verificar los cambios del commit o al revertir commit vacío."
            logging.warning(f"{logPrefix} Ciclo finaliza sin commit efectivo. Razón: {razonFallo}")
             # Formatear entrada de error (incluso si no fue un error 'duro')
            error_msg = f"Cambios aplicados localmente, PERO SIN commit efectivo. Razón: {razonFallo}"
            entradaHistorialActual = formatearEntradaHistorial("ERROR", decisionParseada, resultado=resultadoEjecucionParseado, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor)
            # Aunque se aplicaron cambios, si no se commitearon o se revirtieron, no es éxito.
            # Asegurarse de que los cambios fueron descartados si el commit se revirtió.
            if not errorVerificandoCommit and resultadoCheck.returncode == 0: # Caso de commit vacío revertido exitosamente
                 logging.info(f"{logPrefix} El commit vacío fue revertido y los cambios descartados, terminando ciclo sin error pero sin acción neta.")
            return False

    except Exception as e:
        logging.critical(f"{logPrefix} Error inesperado y no capturado durante la ejecución principal: {e}", exc_info=True)
        if historialRefactor is not None:
            # Intentar crear una entrada de historial lo mejor posible
            error_msg = f"Error inesperado durante el proceso: {e}"
            # Usar decisionParseada si existe para dar contexto
            entradaHistorialActual = formatearEntradaHistorial("ERROR CRÍTICO", decisionParseada, mensaje_error=error_msg)
            historialRefactor.append(entradaHistorialActual)
            guardarHistorial(historialRefactor) # Intentar guardar incluso en error crítico

        try:
            if 'settings' in locals() and hasattr(settings, 'RUTACLON'):
                logging.info(f"{logPrefix} Intentando descartar cambios locales debido a error inesperado...")
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        except Exception as e_clean:
            logging.error(f"{logPrefix} Falló el intento de limpieza tras error inesperado: {e_clean}")
        return False


# Punto de entrada principal (sin cambios significativos en lógica, solo usa la nueva ejecución)
if __name__ == "__main__":
    configurarLogging()
    parser = argparse.ArgumentParser(
        description="Agente de Refactorización de Código con IA (Gemini) - Enfoque Dos Pasos DETALLADO.",
        epilog="Ejecuta un ciclo: 1. Analiza y Decide Detalladamente, 2. Ejecuta Precisamente y Commitea. Usa --modo-test para hacer push."
    )
    parser.add_argument(
        "--modo-test", action="store_true",
        help="Activa modo prueba: Si el ciclo realiza un commit efectivo, intenta hacer push."
    )
    args = parser.parse_args()
    logging.info(
        f"Iniciando script principal (Dos Pasos Detallado). Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

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
                    # Podríamos añadir una entrada INFO al historial sobre el push exitoso
                    # historial = cargarHistorial()
                    # historial.append(f"[INFO] MODO TEST: Push exitoso a rama {ramaPush}.")
                    # guardarHistorial(historial)
                    sys.exit(0)
                else:
                    logging.error(
                        f"Modo Test: Falló el push a la rama '{ramaPush}'.")
                    historial = cargarHistorial()
                    historial.append(f"[ERROR] MODO TEST: Commit local OK, pero PUSH falló a rama {ramaPush}")
                    guardarHistorial(historial)
                    sys.exit(1)
            else:
                logging.info(
                    "Modo Test desactivado. Commit local, no se hizo push.")
                sys.exit(0)
        else:
            logging.warning(
                "Proceso principal finalizó sin realizar un commit efectivo o con errores (revisar historial).")
            sys.exit(1)

    except Exception as e:
        logging.critical(
            f"Error fatal no manejado en __main__: {e}", exc_info=True)
        try:
            # Intentar guardar un último mensaje en el historial
            historial = cargarHistorial()
            historial.append(formatearEntradaHistorial("ERROR FATAL", None, mensaje_error=f"Error no manejado en __main__: {e}"))
            guardarHistorial(historial)
        except Exception as e_hist_fatal:
            logging.error(
                f"No se pudo guardar historial del error fatal: {e_hist_fatal}")
        sys.exit(2)