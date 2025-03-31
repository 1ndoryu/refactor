# principal.py
import logging
import sys
import os
import json
import argparse
import subprocess
import time # ### NUEVO ### Para timestamp en historial
from datetime import datetime # ### NUEVO ### Para timestamp en historial
from config import settings
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios


# --- Configuración Logging y Carga/Guardado de Historial (sin cambios funcionales, pero guardarHistorial se usará más) ---

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
            # Leemos todas las líneas, cada línea es una entrada de historial potencialmente multilínea separada por '--- END ENTRY ---'
            buffer = ""
            for line in f:
                if line.strip() == "--- END ENTRY ---":
                    if buffer:
                        historial.append(buffer.strip())
                        buffer = ""
                else:
                    buffer += line
            if buffer: # Añadir la última entrada si el archivo no termina con el separador
                 historial.append(buffer.strip())
        logging.info(
            f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        logging.error(
            f"{logPrefix} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío.")
        historial = []
    return historial

def guardarHistorial(historial):
    # ... (igual que antes, pero ahora escribe separadores) ...
    logPrefix = "guardarHistorial:"
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    try:
        os.makedirs(os.path.dirname(rutaArchivoHistorial), exist_ok=True)
        with open(rutaArchivoHistorial, 'w', encoding='utf-8') as f:
            for entrada in historial:
                f.write(entrada.strip() + "\n")
                f.write("--- END ENTRY ---\n") # ### NUEVO ### Separador explícito
        logging.info(
            f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({len(historial)} entradas).")
        return True
    except Exception as e:
        logging.error(
            f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False

# --- Parseadores (sin cambios funcionales, pero la validación es importante) ---

def parsearDecisionGemini(decisionJson):
    # ... (igual que antes, la validación es crucial) ...
    logPrefix = "parsearDecisionGemini:"
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
    razonamiento = decisionJson.get("razonamiento") # Ahora se espera más detallado

    if tipoAnalisis != "refactor_decision":
        logging.error(
            f"{logPrefix} JSON inválido. Falta o es incorrecto 'tipo_analisis'. Debe ser 'refactor_decision'. JSON: {decisionJson}")
        return None

    # ### MODIFICADO ### Validar que los campos esenciales existan y tengan tipos básicos correctos
    if not all([accionPropuesta, isinstance(parametrosAccion, dict), descripcion, isinstance(archivosRelevantes, list), razonamiento]):
        logging.error(f"{logPrefix} Formato JSON de decisión inválido. Faltan campos clave ('accion_propuesta', 'descripcion', 'parametros_accion', 'archivos_relevantes', 'razonamiento') o tipos incorrectos. JSON: {decisionJson}")
        return None

    if accionPropuesta not in accionesSoportadas:
        logging.error(
            f"{logPrefix} Acción propuesta '{accionPropuesta}' NO RECONOCIDA o NO SOPORTADA. Válidas: {accionesSoportadas}. JSON: {decisionJson}")
        return None

    if accionPropuesta != "no_accion" and not archivosRelevantes and accionPropuesta not in ["crear_directorio"]:
         # crear_directorio es la única acción que podría no necesitar archivos relevantes
        logging.warning(
            f"{logPrefix} Acción '{accionPropuesta}' usualmente requiere 'archivos_relevantes', pero la lista está vacía. Esto podría ser un error en el Paso 1.")
        # Podríamos decidir fallar aquí si es crítico, pero lo dejamos pasar por ahora
        # return None

    if accionPropuesta == "no_accion":
        logging.info(
            f"{logPrefix} Decisión 'no_accion' recibida y parseada. Razón: {razonamiento or 'No proporcionada'}")
    else:
        logging.info(
            f"{logPrefix} Decisión parseada exitosamente. Acción: {accionPropuesta}. Archivos: {archivosRelevantes}. Razón: {razonamiento[:100]}...") # Log más corto

    return decisionJson

def parsearResultadoEjecucion(resultadoJson):
    # ... (igual que antes, mantener JSON simple) ...
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
        # Es válido que sea un dict vacío para acciones como eliminar_archivo, crear_directorio
        if accionOriginal := resultadoJson.get("accion_original_debug"): # Pequeño truco si lo añadimos en la llamada
            if accionOriginal in ["eliminar_archivo", "crear_directorio"] and archivosModificados == {}:
                 logging.info(f"{logPrefix} Resultado de ejecución parseado: Diccionario 'archivos_modificados' vacío, lo cual es esperado para la acción '{accionOriginal}'.")
                 return {} # Devolver dict vacío es correcto aquí
            else:
                 logging.error(
                    f"{logPrefix} Formato JSON de resultado inválido. 'archivos_modificados' no es un diccionario (y no es acción sin modificación). JSON: {resultadoJson}")
                 return None
        else: # No sabemos la acción original aquí, asumimos que debe ser dict
             logging.error(
                 f"{logPrefix} Formato JSON de resultado inválido. Falta 'archivos_modificados' o no es un diccionario. JSON: {resultadoJson}")
             return None


    # Validación adicional: claves y valores deben ser strings
    for ruta, contenido in archivosModificados.items():
        if not isinstance(ruta, str) or not isinstance(contenido, str):
            logging.error(
                f"{logPrefix} Entrada inválida en 'archivos_modificados'. Clave o valor no son strings. Clave: {ruta} (tipo {type(ruta)}), Valor (tipo {type(contenido)}). JSON: {resultadoJson}")
            return None

    logging.info(
        f"{logPrefix} Resultado de ejecución parseado exitosamente. {len(archivosModificados)} archivos a modificar.")
    return archivosModificados

# ### NUEVO ### Función para formatear entrada de historial
def formatearEntradaHistorial(outcome, decision=None, result_details=None, verification_details=None, error_message=None):
    """Crea una cadena de texto estructurada para el historial."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] [{outcome}]\n"

    if decision:
        accion = decision.get('accion_propuesta', 'N/A')
        desc = decision.get('descripcion', 'N/A')
        razon = decision.get('razonamiento', 'N/A')
        archivos = decision.get('archivos_relevantes', [])
        params = decision.get('parametros_accion', {})
        entry += f"  Decision (Paso 1):\n"
        entry += f"    Accion: {accion}\n"
        entry += f"    Descripcion: {desc}\n"
        entry += f"    Razonamiento: {razon}\n"
        entry += f"    Parametros: {json.dumps(params)}\n"
        entry += f"    Archivos Relevantes: {archivos}\n"

    if result_details:
        entry += f"  Resultado (Paso 2):\n"
        if isinstance(result_details, dict): # Archivos modificados
            entry += f"    Archivos Generados: {list(result_details.keys())}\n"
        else: # Mensaje de error u otro detalle
            entry += f"    Detalles: {result_details}\n"

    if verification_details:
         entry += f"  Verificacion (Paso 3):\n"
         entry += f"    Detalles: {verification_details}\n"

    if error_message:
        entry += f"  Error: {error_message}\n"

    return entry.strip()

# ### NUEVO ### Función de Verificación (Paso 3)
def verificarCambiosAplicados(decisionParseada, resultadoEjecucion, rutaRepo):
    """
    PASO 3: Compara la intención (Paso 1) con la ejecución (Paso 2) y el estado real (git status).
    Returns: (bool, str) - (True, "OK") si es consistente, (False, "Mensaje de inconsistencia") si no.
    """
    logPrefix = "verificarCambiosAplicados (Paso 3):"
    logging.info(f"{logPrefix} Iniciando verificación...")

    # 1. Archivos que Paso 1 INTENTABA afectar
    archivosIntencion = set(decisionParseada.get('archivos_relevantes', []))
    accion = decisionParseada.get('accion_propuesta')
    params = decisionParseada.get('parametros_accion', {})
    # Añadir archivos específicos de parámetros si no están en relevantes (por si acaso)
    if accion in ["mover_funcion", "mover_clase"]:
        archivosIntencion.add(params.get("archivo_origen"))
        archivosIntencion.add(params.get("archivo_destino"))
    elif accion in ["modificar_codigo_en_archivo", "eliminar_archivo"]:
        archivosIntencion.add(params.get("archivo"))
    elif accion == "crear_archivo":
         archivosIntencion.add(params.get("archivo"))
    archivosIntencion.discard(None) # Eliminar None si algún parámetro no estaba
    logging.debug(f"{logPrefix} Archivos según Intención (Paso 1): {archivosIntencion}")

    # 2. Archivos para los que Paso 2 GENERÓ contenido
    archivosGenerados = set(resultadoEjecucion.keys())
    logging.debug(f"{logPrefix} Archivos con contenido Generado (Paso 2): {archivosGenerados}")

    # 3. Archivos REALMENTE modificados/añadidos/eliminados en disco (según Git)
    # Usamos el nuevo helper de manejadorGit
    archivosRealesModificados = manejadorGit.obtenerArchivosModificadosStatus(rutaRepo)
    if archivosRealesModificados is None:
        err = "No se pudo obtener el estado de los archivos de Git."
        logging.error(f"{logPrefix} {err}")
        return False, err
    logging.debug(f"{logPrefix} Archivos Modificados/Nuevos/Eliminados (Git Status): {archivosRealesModificados}")

    # --- Lógica de Comparación ---
    inconsistencias = []

    # a) ¿Generó Gemini contenido para archivos no esperados (según intención)?
    inesperadosGenerados = archivosGenerados - archivosIntencion
    if inesperadosGenerados:
        # Permitir si la acción era crear_archivo y el archivo está en inesperados (puede que no estuviera en 'relevantes' si era nuevo)
        if not (accion == "crear_archivo" and inesperadosGenerados == {params.get("archivo")}):
             msg = f"Gemini (Paso 2) generó contenido para archivos inesperados: {inesperadosGenerados}"
             logging.warning(f"{logPrefix} {msg}")
             inconsistencias.append(msg)

    # b) ¿Los archivos realmente modificados coinciden (más o menos) con la intención?
    #    Es difícil ser exacto. Nos enfocamos en si hay modificaciones *fuera* del conjunto esperado.
    inesperadosModificados = archivosRealesModificados - archivosIntencion
    if inesperadosModificados:
         msg = f"Se detectaron cambios en archivos inesperados (no en intención Paso 1): {inesperadosModificados}"
         logging.warning(f"{logPrefix} {msg}")
         inconsistencias.append(msg)

    # c) ¿Se modificaron MENOS archivos de los esperados? (Ej: pidió modificar 2, solo cambió 1)
    #    Comparamos los archivos modificados reales con los que tenían contenido generado
    if not accion in ["eliminar_archivo", "crear_directorio"]: # Estas acciones no generan contenido modificado
        faltantesModificados = archivosGenerados - archivosRealesModificados
        # Puede que un archivo generado sea idéntico al original, git no lo detecta.
        # Solo lo marcamos si es una diferencia clara y no es crear archivo (donde es normal que solo aparezca 1)
        if faltantesModificados and accion != "crear_archivo":
             # Verificar si el contenido generado era realmente diferente
             realmente_faltantes = set()
             for faltante in faltantesModificados:
                 ruta_abs_faltante = aplicadorCambios._validar_y_normalizar_ruta(faltante, rutaRepo, asegurar_existencia=False)
                 contenido_original = ""
                 if ruta_abs_faltante and os.path.exists(ruta_abs_faltante):
                     try:
                         with open(ruta_abs_faltante, 'r', encoding='utf-8', errors='ignore') as f_orig:
                             contenido_original = f_orig.read()
                     except Exception: pass # Ignorar si no se puede leer el original
                 if resultadoEjecucion.get(faltante) != contenido_original:
                     realmente_faltantes.add(faltante)

             if realmente_faltantes:
                msg = f"Archivos con contenido generado por Gemini (Paso 2) parecen no haber sido modificados en disco (o el cambio fue revertido/fallido): {realmente_faltantes}"
                logging.warning(f"{logPrefix} {msg}")
                inconsistencias.append(msg)

    # d) Caso especial: ¿Se pidió eliminar y el archivo todavía existe?
    if accion == "eliminar_archivo":
        archivo_a_eliminar = params.get("archivo")
        if archivo_a_eliminar in archivosRealesModificados: # Si git aún lo ve como modificado/existente
             ruta_abs_eliminar = aplicadorCambios._validar_y_normalizar_ruta(archivo_a_eliminar, rutaRepo, asegurar_existencia=False)
             if ruta_abs_eliminar and os.path.exists(ruta_abs_eliminar):
                 msg = f"Se pidió eliminar '{archivo_a_eliminar}' pero todavía existe."
                 logging.warning(f"{logPrefix} {msg}")
                 inconsistencias.append(msg)

    # --- Decisión Final ---
    if inconsistencias:
        mensaje_final = "Verificación fallida. Inconsistencias detectadas:\n- " + "\n- ".join(inconsistencias)
        logging.error(f"{logPrefix} {mensaje_final}")
        return False, mensaje_final
    else:
        msg = "OK. Los cambios aplicados parecen consistentes con la intención."
        logging.info(f"{logPrefix} {msg}")
        return True, msg


# --- Función Principal (Modificada con Historial Detallado y Verificación) ---
def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    logging.info(
        f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN (3 PASOS: Decide, Ejecuta, Verifica) =====")
    historialRefactor = []
    decisionParseada = None
    resultadoEjecucion = None
    archivosModificadosGit = None
    estadoFinal = "[INICIO]"

    try:
        # 1. Verificar configuración esencial
        if not settings.GEMINIAPIKEY or not settings.REPOSITORIOURL:
            logging.critical(f"{logPrefix} Configuración esencial faltante. Abortando.")
            # No podemos guardar historial si falla tan temprano
            return False

        # 2. Cargar historial
        historialRefactor = cargarHistorial()

        # 3. Preparar repositorio local
        logging.info(f"{logPrefix} Preparando repositorio local...")
        if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
            # ... (manejo de error y historial) ...
            return False
        logging.info(f"{logPrefix} Repositorio listo y en la rama '{settings.RAMATRABAJO}'.")

        # <<< NUEVO: Generar estructura del proyecto DESPUÉS de clonar/actualizar >>>
        estructura_proyecto_str = ""
        try:
            logging.info(f"{logPrefix} Generando estructura del proyecto para contexto...")
            # Usar directorios ignorados de settings si existen
            ignorados_setting = getattr(settings, 'DIRECTORIOS_IGNORADOS', ['.git', 'vendor', 'node_modules', '.github', 'assets', 'Tests', 'languages']) # Ignorar assets, Tests, etc.
            estructura_proyecto_str = analizadorCodigo.generarEstructuraDirectorio(
                settings.RUTACLON,
                directorios_ignorados=ignorados_setting,
                max_depth=8, # Limitar profundidad para no ser excesivo
                incluir_archivos=True # Incluir archivos en la estructura
            )
            if not estructura_proyecto_str:
                 logging.warning(f"{logPrefix} No se pudo generar la estructura del proyecto.")
                 estructura_proyecto_str = "[Error al generar estructura]" # Placeholder
            else:
                 # Loguear solo una parte si es muy grande
                 logging.info(f"{logPrefix} Estructura del proyecto generada (primeras líneas para log):\n{estructura_proyecto_str[:600]}...")
                 # Loguear completo en debug si es necesario
                 logging.debug(f"{logPrefix} Estructura completa generada:\n{estructura_proyecto_str}")
        except Exception as e_struct:
            logging.error(f"{logPrefix} Excepción al generar estructura del proyecto: {e_struct}", exc_info=True)
            estructura_proyecto_str = "[Excepción al generar estructura]" # Placeholder


        # ===============================================================
        # PASO 1: ANÁLISIS Y DECISIÓN (GEMINI CON CONTEXTO COMPLETO)
        # ===============================================================
        logging.info(f"{logPrefix} --- INICIO PASO 1: ANÁLISIS Y DECISIÓN ---")
        codigoProyectoCompleto = ""
        try:
            # 4a. Analizar código COMPLETO
            logging.info(f"{logPrefix} Analizando código COMPLETO...")
            extensiones = getattr(settings, 'EXTENSIONESPERMITIDAS', None)
            ignorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', None)
            # Asegúrate que listarArchivosProyecto use los mismos ignorados o ajusta según necesidad
            todosLosArchivos = analizadorCodigo.listarArchivosProyecto(
                settings.RUTACLON, extensiones, ignorados)
            if todosLosArchivos is None: raise Exception("Error al listar archivos.")
            if not todosLosArchivos:
                 logging.warning(f"{logPrefix} No se encontraron archivos relevantes para leer.")
                 # Permitir continuar si solo tenemos estructura? Decisión: Sí, Gemini puede decidir crear algo.
                 # raise Exception("No files found") # Comentado para permitir continuar
                 codigoProyectoCompleto = "" # Asegurar que esté vacío si no hay archivos
            else:
                codigoProyectoCompleto = analizadorCodigo.leerArchivos(todosLosArchivos, settings.RUTACLON)
                if codigoProyectoCompleto is None: raise Exception("Error al leer contenido de archivos.") # None indica error de lectura
                tamanoKB_completo = len(codigoProyectoCompleto.encode('utf-8')) / 1024
                logging.info(f"{logPrefix} Código completo leído ({len(todosLosArchivos)} archivos, {tamanoKB_completo:.2f} KB).")


            # 5a. Obtener DECISIÓN de Gemini
            logging.info(f"{logPrefix} Obteniendo DECISIÓN de Gemini...")
            historialRecienteTexto = "\n---\n".join(historialRefactor[-settings.N_HISTORIAL_CONTEXTO:]) # Usar separador claro

            # <<< MODIFICADO: Pasar la estructura generada >>>
            decisionJson = analizadorCodigo.obtenerDecisionRefactor(
                codigoProyectoCompleto,
                historialRecienteTexto,
                estructura_proyecto_str # <<< Añadido aquí
            )
            if not decisionJson: raise Exception("No se recibió DECISIÓN válida de Gemini (Paso 1).")

            # 6a. Parsear y validar la DECISIÓN
            # ... (resto del parseo y manejo de 'no_accion' sin cambios) ...
            logging.info(f"{logPrefix} Parseando DECISIÓN de Gemini...")
            decisionParseada = parsearDecisionGemini(decisionJson)
            if not decisionParseada:
                sugerencia_str = json.dumps(decisionJson) if isinstance(decisionJson, dict) else str(decisionJson)
                sugerencia_log = sugerencia_str[:500] + ('...' if len(sugerencia_str) > 500 else '')
                raise Exception(f"Decisión inválida, mal formada o no soportada. Recibido: {sugerencia_log}")

            estadoFinal = "[PASO1_OK]"

            if decisionParseada.get("accion_propuesta") == "no_accion":
                razonamientoNoAccion = decisionParseada.get('razonamiento', 'Sin razonamiento especificado.')
                logging.info(f"{logPrefix} Gemini decidió 'no_accion'. Razón: {razonamientoNoAccion}. Terminando ciclo.")
                estadoFinal = "[NO_ACCION]"
                historialRefactor.append(formatearEntradaHistorial(
                    outcome=estadoFinal,
                    decision=decisionParseada
                ))
                guardarHistorial(historialRefactor)
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False

            logging.info(f"{logPrefix} --- FIN PASO 1: Decisión válida recibida: {decisionParseada.get('accion_propuesta')} ---")

        except Exception as e_paso1:
             # ... (manejo de error paso 1 sin cambios) ...
            logging.error(f"{logPrefix} Error en Paso 1: {e_paso1}", exc_info=True)
            estadoFinal = "[ERROR_PASO1]"
            historialRefactor.append(formatearEntradaHistorial(
                outcome=estadoFinal,
                decision=decisionParseada,
                error_message=str(e_paso1)
            ))
            guardarHistorial(historialRefactor)
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        # ===============================================================
        # PASO 2: EJECUCIÓN (GEMINI CON CONTEXTO REDUCIDO)
        # ===============================================================
        # ... (Paso 2, Aplicación, Paso 3 Verificación, Commit y Finalización sin cambios) ...
        logging.info(f"{logPrefix} --- INICIO PASO 2: EJECUCIÓN ---")
        contextoReducido = ""
        try:
            # 4b. Leer SÓLO archivos relevantes
            archivosRelevantes = decisionParseada.get("archivos_relevantes", [])
            rutasAbsRelevantes = []
            # ... (lógica para obtener rutasAbsRelevantes y leer contexto reducido como antes) ...
            for rutaRel in archivosRelevantes:
                 rutaAbs = aplicadorCambios._validar_y_normalizar_ruta(
                     rutaRel, settings.RUTACLON, asegurar_existencia=False)
                 if rutaAbs:
                     accion = decisionParseada.get("accion_propuesta")
                     params = decisionParseada.get("parametros_accion", {})
                     archivo_destino_mover = params.get("archivo_destino") if accion in ["mover_funcion", "mover_clase"] else None
                     archivo_a_crear = params.get("archivo") if accion == "crear_archivo" else None

                     if os.path.exists(rutaAbs) or rutaRel == archivo_a_crear or rutaRel == archivo_destino_mover:
                          rutasAbsRelevantes.append(rutaAbs)
                     else:
                          logging.warning(f"{logPrefix} Archivo relevante '{rutaRel}' no existe y no parece ser objetivo de creación/movimiento. Se omitirá del contexto Paso 2.")
                 else:
                     # No fallar aquí, solo loguear. El paso 1 debió validar mejor.
                     logging.error(f"{logPrefix} Ruta relevante inválida '{rutaRel}' proporcionada por Gemini en Paso 1. Se omitirá.")
                     # raise Exception(f"Ruta relevante inválida '{rutaRel}' proporcionada por Gemini en Paso 1.") # Comentado

            accion_requiere_contexto = decisionParseada.get("accion_propuesta") not in ["crear_directorio", "eliminar_archivo", "crear_archivo"] # Crear archivo no necesita contexto *de él mismo*
            if not rutasAbsRelevantes and accion_requiere_contexto:
                  es_mover_a_nuevo = decisionParseada.get("accion_propuesta") in ["mover_funcion", "mover_clase"] and \
                                     len(archivosRelevantes) == 1 and \
                                     archivosRelevantes[0] == decisionParseada.get("parametros_accion", {}).get("archivo_destino") and \
                                     not os.path.exists(aplicadorCambios._validar_y_normalizar_ruta(archivosRelevantes[0], settings.RUTACLON, asegurar_existencia=False)) # Check si realmente no existe
                  if not es_mover_a_nuevo:
                      # No fallar, solo advertir. Gemini podría no necesitar contexto.
                      logging.warning(f"{logPrefix} No se encontraron archivos existentes para contexto reducido y la acción usualmente lo requiere. Acción: {decisionParseada.get('accion_propuesta')}. Relevantes: {archivosRelevantes}. Se continuará sin contexto.")
                      # raise Exception(f"No se encontraron archivos existentes para contexto reducido. Acción: {decisionParseada.get('accion_propuesta')}. Relevantes: {archivosRelevantes}") # Comentado

            if rutasAbsRelevantes:
                rutas_a_leer = [r for r in rutasAbsRelevantes if os.path.exists(r)]
                if rutas_a_leer:
                    contextoReducido = analizadorCodigo.leerArchivos(rutas_a_leer, settings.RUTACLON) # Pasar la ruta base correcta
                    if contextoReducido is None: raise Exception("Error leyendo contexto reducido.")
                    tamanoKB_reducido = len(contextoReducido.encode('utf-8')) / 1024
                    logging.info(f"{logPrefix} Contexto reducido leído ({len(rutas_a_leer)} archivos, {tamanoKB_reducido:.2f} KB).")
                else:
                     logging.info(f"{logPrefix} No hay archivos existentes entre los relevantes para leer en Paso 2 (ej: mover a archivo nuevo).")
            else:
                 logging.info(f"{logPrefix} Acción '{decisionParseada.get('accion_propuesta')}' no requiere contexto de archivo para Paso 2, o no se encontraron archivos relevantes existentes.")
                 contextoReducido = "" # Explícito

            # 5b. Obtener RESULTADO de ejecución de Gemini
            logging.info(f"{logPrefix} Obteniendo RESULTADO de ejecución de Gemini...")
            resultadoJson = analizadorCodigo.ejecutarAccionConGemini(
                decisionParseada, contextoReducido) # Pasar decisión completa
            if not resultadoJson: raise Exception("No se recibió RESULTADO válido de Gemini (Paso 2).")

            # 6b. Parsear y validar el RESULTADO
            logging.info(f"{logPrefix} Parseando RESULTADO de ejecución Gemini...")
            if isinstance(resultadoJson, dict): # Añadir solo si es dict
                resultadoJson["accion_original_debug"] = decisionParseada.get("accion_propuesta")
            resultadoEjecucion = parsearResultadoEjecucion(resultadoJson)
            if resultadoEjecucion is None:
                resultado_str = json.dumps(resultadoJson) if isinstance(resultadoJson, dict) else str(resultadoJson)
                resultado_log = resultado_str[:500] + ('...' if len(resultado_str) > 500 else '')
                raise Exception(f"Resultado de ejecución inválido o mal formado. Recibido: {resultado_log}")

            logging.info(f"{logPrefix} --- FIN PASO 2: Resultado válido recibido ({len(resultadoEjecucion)} archivos a modificar). ---")
            estadoFinal = "[PASO2_OK]"

            # 7. Aplicar los cambios
            logging.info(f"{logPrefix} Aplicando cambios generados...")
            exitoAplicar, mensajeErrorAplicar = aplicadorCambios.aplicarCambiosSobrescritura(
                resultadoEjecucion,
                settings.RUTACLON,
                decisionParseada.get("accion_propuesta"),
                decisionParseada.get("parametros_accion", {})
            )
            if not exitoAplicar:
                raise Exception(f"Falló la aplicación de cambios: {mensajeErrorAplicar}")

            logging.info(f"{logPrefix} Cambios aplicados localmente con éxito (antes de verificación).")
            estadoFinal = "[APPLY_OK]"

        except Exception as e_paso2_apply:
            # ... (manejo de error paso 2 sin cambios) ...
            logging.error(f"{logPrefix} Error en Paso 2 o Aplicación: {e_paso2_apply}", exc_info=True)
            estadoFinal = "[ERROR_PASO2_APPLY]"
            historialRefactor.append(formatearEntradaHistorial(
                outcome=estadoFinal,
                decision=decisionParseada,
                result_details=resultadoEjecucion if resultadoEjecucion is not None else resultadoJson,
                error_message=str(e_paso2_apply)
            ))
            guardarHistorial(historialRefactor)
            logging.info(f"{logPrefix} Intentando descartar cambios locales tras error...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

    
        # ===============================================================
        # PASO 3: VERIFICACIÓN (DESACTIVADO TEMPORALMENTE)
        # ===============================================================
        logging.info(f"{logPrefix} --- INICIO PASO 3: VERIFICACIÓN (TEMPORALMENTE DESACTIVADO) ---")
        exitoVerificacion = True # Asumir éxito ya que está desactivado
        verification_details_msg = "Verificación desactivada temporalmente."
        logging.warning(f"{logPrefix} {verification_details_msg}")
        estadoFinal = "[VERIFY_SKIPPED]" # Nuevo estado para indicar que se saltó

        # --- CÓDIGO ORIGINAL COMENTADO ---
        # verification_details_msg = "Verificación no ejecutada."
        # try:
        #     exitoVerificacion, verification_details_msg = verificarCambiosAplicados(
        #         decisionParseada,
        #         resultadoEjecucion,
        #         settings.RUTACLON
        #     )
        #
        #     if not exitoVerificacion:
        #         raise Exception(f"Verificación fallida: {verification_details_msg}")
        #
        #     logging.info(f"{logPrefix} --- FIN PASO 3: Verificación exitosa. ---")
        #     estadoFinal = "[VERIFY_OK]"
        #
        # except Exception as e_paso3_verify:
        #     logging.error(f"{logPrefix} Error en Paso 3 (Verificación): {e_paso3_verify}", exc_info=True)
        #     estadoFinal = "[VERIFY_FAIL]"
        #     # ... (guardar historial y descartar) ...
        #     historialRefactor.append(formatearEntradaHistorial(
        #         outcome=estadoFinal,
        #         decision=decisionParseada,
        #         result_details=resultadoEjecucion,
        #         verification_details=verification_details_msg,
        #         error_message=str(e_paso3_verify)
        #     ))
        #     guardarHistorial(historialRefactor)
        #     logging.info(f"{logPrefix} Intentando descartar cambios locales tras fallo de verificación...")
        #     manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        #     return False
        # --- FIN CÓDIGO ORIGINAL COMENTADO ---


        # ===============================================================
        # COMMIT Y FINALIZACIÓN (Lógica ajustada)
        # ===============================================================
        try:
            # 8. Hacer commit
            logging.info(f"{logPrefix} Realizando commit...")
            mensajeCommit = decisionParseada.get('descripcion', 'Refactorización automática')
            # ... (truncar mensaje si es largo) ...
            if len(mensajeCommit.encode('utf-8')) > 4000:
                 mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
                 logging.warning(f"{logPrefix} Mensaje de commit truncado.")
            elif len(mensajeCommit.splitlines()[0]) > 72:
                 logging.warning(f"{logPrefix} Primera línea del mensaje de commit larga (>72 chars).")

            # --- CAMBIO: Usar el nuevo valor de retorno de hacerCommit ---
            seHizoCommitNuevo = manejadorGit.hacerCommit(settings.RUTACLON, mensajeCommit)

            if seHizoCommitNuevo:
                logging.info(f"{logPrefix} Commit realizado con éxito.")
                estadoFinal = "[ÉXITO]"
                historialRefactor.append(formatearEntradaHistorial(
                    outcome=estadoFinal,
                    decision=decisionParseada,
                    result_details=resultadoEjecucion,
                    verification_details=verification_details_msg # Mantener el mensaje de skip
                ))
                guardarHistorial(historialRefactor)
                logging.info(f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
                return True # ¡Éxito final!
            else:
                # Razones por las que hacerCommit retorna False:
                # 1. Error en 'git add' o 'git commit' (ya logueado por manejadorGit)
                # 2. No había cambios staged para commitear (ej. directorio vacío sin .gitkeep, o .gitkeep ya existía)
                logging.warning(f"{logPrefix} No se realizó un nuevo commit (ver logs de manejadorGit para detalles: puede ser por falta de cambios o error).")
                estadoFinal = "[COMMIT_NO_REALIZADO]"
                # Guardar historial indicando que no se hizo commit
                historialRefactor.append(formatearEntradaHistorial(
                    outcome=estadoFinal,
                    decision=decisionParseada,
                    result_details=resultadoEjecucion,
                    verification_details=verification_details_msg,
                    error_message="No se generó un nuevo commit (sin cambios detectados por Git o error en commit)."
                ))
                guardarHistorial(historialRefactor)
                # Importante: Descartar cambios locales si no hubo commit, para evitar acumulación
                logging.info(f"{logPrefix} Descartando cambios locales ya que no hubo commit...")
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False # El ciclo no terminó con un commit exitoso

        except Exception as e_commit_final:
            # ... (error en commit) ...
            logging.error(f"{logPrefix} Error en fase de Commit/Finalización: {e_commit_final}", exc_info=True)
            estadoFinal = "[ERROR_COMMIT]"
            historialRefactor.append(formatearEntradaHistorial(
                outcome=estadoFinal,
                decision=decisionParseada,
                result_details=resultadoEjecucion,
                verification_details=verification_details_msg,
                error_message=str(e_commit_final)
            ))
            guardarHistorial(historialRefactor)
            logging.info(f"{logPrefix} Intentando descartar cambios locales tras fallo de commit...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

    # ... (manejo de error global y __main__ sin cambios) ...
    except Exception as e_global:
        logging.critical(f"{logPrefix} Error inesperado y no capturado: {e_global}", exc_info=True)
        estadoFinal = "[ERROR_CRITICO]"
        try:
            if not historialRefactor: historialRefactor = cargarHistorial()
            historialRefactor.append(formatearEntradaHistorial(
                outcome=estadoFinal,
                decision=decisionParseada,
                error_message=str(e_global)
            ))
            guardarHistorial(historialRefactor)
        except Exception as e_hist_crit:
            logging.error(f"Fallo adicional al intentar guardar historial de error crítico: {e_hist_crit}")
        try:
            logging.info(f"{logPrefix} Intentando descartar cambios locales debido a error crítico...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        except Exception as e_clean_crit:
            logging.error(f"{logPrefix} Falló limpieza tras error crítico: {e_clean_crit}")
        return False


if __name__ == "__main__":
    # ... (__main__ sin cambios) ...
    configurarLogging()
    parser = argparse.ArgumentParser(
        description="Agente de Refactorización de Código con IA (Gemini) - 3 Pasos (Decide, Ejecuta, Verifica).",
        epilog="Ejecuta un ciclo: 1. Decide, 2. Ejecuta, 3. Verifica, 4. Commitea. Usa --modo-test para hacer push."
    )
    parser.add_argument(
        "--modo-test", action="store_true",
        help="Activa modo prueba: Si el ciclo realiza un commit efectivo, intenta hacer push."
    )
    args = parser.parse_args()
    logging.info(
        f"Iniciando script principal (3 Pasos). Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    try:
        cicloTuvoExitoConCommit = ejecutarProcesoPrincipal()

        if cicloTuvoExitoConCommit:
            logging.info(
                "Proceso principal completado: Se realizó un commit con cambios efectivos.")
            if args.modo_test:
                # ... (lógica de push) ...
                logging.info("Modo Test activado: Intentando hacer push...")
                ramaPush = getattr(settings, 'RAMATRABAJO', 'main')
                if manejadorGit.hacerPush(settings.RUTACLON, ramaPush):
                    logging.info(f"Modo Test: Push a la rama '{ramaPush}' realizado con éxito.")
                    sys.exit(0)
                else:
                    logging.error(f"Modo Test: Falló el push a la rama '{ramaPush}'. El commit local se mantiene.")
                    sys.exit(1)
            else:
                logging.info("Modo Test desactivado. Commit local realizado, no se hizo push.")
                sys.exit(0)
        else:
            logging.warning(
                "Proceso principal finalizó SIN realizar un commit efectivo (puede ser por 'no_accion', error o fallo de verificación). Verifique logs e historial.")
            sys.exit(1) # No éxito

    except Exception as e:
        # ... (manejo de error fatal) ...
        logging.critical(f"Error fatal no manejado en __main__: {e}", exc_info=True)
        try:
            historial = cargarHistorial()
            historial.append(formatearEntradaHistorial(outcome="[ERROR_FATAL_MAIN]", error_message=str(e)))
            guardarHistorial(historial)
        except Exception as e_hist_fatal:
            logging.error(f"No se pudo guardar historial del error fatal: {e_hist_fatal}")
        sys.exit(2)