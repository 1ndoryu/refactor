# principal.py

import logging
import sys
import os
import json
import argparse
import subprocess
import time
import signal
import re  # Para parseo robusto de misionOrion.md
from datetime import datetime, timedelta
from config import settings
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios
from nucleo import manejadorHistorial
from nucleo import manejadorMision

# --- Nuevas Constantes y Variables Globales ---
REGISTRO_ARCHIVOS_ANALIZADOS_PATH = os.path.join(
    settings.RUTA_BASE_PROYECTO, "registro_archivos_analizados.json")
MISION_ORION_MD = "misionOrion.md"
TOKEN_LIMIT_PER_MINUTE = getattr(
    settings, 'TOKEN_LIMIT_PER_MINUTE', 250000)
token_usage_window = []

# --- Archivo para persistir el estado de la misión activa ---
ACTIVE_MISSION_STATE_FILE = os.path.join(settings._CONFIG_DIR if hasattr(
    settings, '_CONFIG_DIR') else os.path.join(settings.RUTA_BASE_PROYECTO, 'config'), '.active_mission')

# --- Fin Nuevas Constantes ---


class TimeoutException(Exception):
    """Excepción para indicar que el tiempo límite de ejecución fue alcanzado."""
    pass

# --- Funciones para el manejo de tokens (NUEVO) ---


def gestionar_limite_tokens(tokens_a_usar_estimados: int, proveedor_api: str):
    global token_usage_window
    logPrefix = "gestionar_limite_tokens:"
    ahora = datetime.now()
    token_usage_window = [
        (ts, count) for ts, count in token_usage_window if ahora - ts < timedelta(seconds=60)
    ]
    tokens_usados_en_ventana = sum(count for _, count in token_usage_window)
    logging.debug(
        f"{logPrefix} Tokens usados en los últimos 60s: {tokens_usados_en_ventana}. A usar: {tokens_a_usar_estimados}")

    if tokens_usados_en_ventana + tokens_a_usar_estimados > TOKEN_LIMIT_PER_MINUTE:
        segundos_a_esperar = 60 - \
            (ahora - token_usage_window[0][0]
             ).total_seconds() if token_usage_window else 60
        segundos_a_esperar = max(1, int(segundos_a_esperar) + 1)
        logging.info(f"{logPrefix} Límite de tokens ({TOKEN_LIMIT_PER_MINUTE}/min) excedería. "
                     f"Usados: {tokens_usados_en_ventana}. A usar: {tokens_a_usar_estimados}. "
                     f"Pausando por {segundos_a_esperar} segundos...")
        time.sleep(segundos_a_esperar)
        return gestionar_limite_tokens(tokens_a_usar_estimados, proveedor_api)
    logging.info(
        f"{logPrefix} OK para proceder con {tokens_a_usar_estimados} tokens (estimados).")
    return True


def registrar_tokens_usados(tokens_usados: int):
    global token_usage_window
    token_usage_window.append((datetime.now(), tokens_usados))
    ahora = datetime.now()
    token_usage_window = [
        (ts, count) for ts, count in token_usage_window if ahora - ts < timedelta(seconds=60)
    ]
    tokens_usados_en_ventana_actual = sum(
        count for _, count in token_usage_window)
    logging.debug(
        f"Registrados {tokens_usados} tokens. Ventana actual ({TOKEN_LIMIT_PER_MINUTE}/min): {tokens_usados_en_ventana_actual} tokens usados.")


# --- Funciones para el registro de archivos analizados (NUEVO) ---
def cargar_registro_archivos():
    if os.path.exists(REGISTRO_ARCHIVOS_ANALIZADOS_PATH):
        try:
            with open(REGISTRO_ARCHIVOS_ANALIZADOS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.error(
                f"Error decodificando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}. Se creará uno nuevo.")
        except Exception as e:
            logging.error(
                f"Error cargando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}: {e}. Se creará uno nuevo.")
    return {}


def guardar_registro_archivos(registro):
    try:
        with open(REGISTRO_ARCHIVOS_ANALIZADOS_PATH, 'w', encoding='utf-8') as f:
            json.dump(registro, f, indent=4)
    except Exception as e:
        logging.error(
            f"Error guardando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}: {e}")


def seleccionar_archivo_mas_antiguo(ruta_proyecto, registro_archivos):
    logPrefix = "seleccionar_archivo_mas_antiguo:"
    archivos_proyecto_abs = analizadorCodigo.listarArchivosProyecto(
        ruta_proyecto,
        extensionesPermitidas=settings.EXTENSIONESPERMITIDAS,
        directoriosIgnorados=settings.DIRECTORIOS_IGNORADOS
    )
    if not archivos_proyecto_abs:
        logging.warning(
            f"{logPrefix} No se encontraron archivos en el proyecto que coincidan con los criterios.")
        return None

    archivo_seleccionado_rel = None
    timestamp_mas_antiguo = datetime.max.isoformat()
    archivos_proyecto_relativos = []
    for abs_path in archivos_proyecto_abs:
        try:
            rel_path = os.path.relpath(
                abs_path, ruta_proyecto).replace(os.sep, '/')
            archivos_proyecto_relativos.append(rel_path)
        except ValueError as e:
            logging.warning(
                f"{logPrefix} No se pudo obtener ruta relativa para {abs_path} respecto a {ruta_proyecto}: {e}")
            continue

    if not archivos_proyecto_relativos:
        logging.warning(
            f"{logPrefix} No quedaron archivos válidos después de convertir a rutas relativas.")
        return None

    for ruta_rel_archivo in archivos_proyecto_relativos:
        timestamp_ultima_seleccion = registro_archivos.get(ruta_rel_archivo)
        if timestamp_ultima_seleccion is None:
            archivo_seleccionado_rel = ruta_rel_archivo
            logging.info(
                f"{logPrefix} Archivo '{archivo_seleccionado_rel}' nunca antes seleccionado.")
            break
        if timestamp_ultima_seleccion < timestamp_mas_antiguo:
            timestamp_mas_antiguo = timestamp_ultima_seleccion
            archivo_seleccionado_rel = ruta_rel_archivo

    if archivo_seleccionado_rel:
        logging.info(
            f"{logPrefix} Archivo seleccionado: {archivo_seleccionado_rel} (Última vez: {registro_archivos.get(archivo_seleccionado_rel, 'Nunca')})")
        registro_archivos[archivo_seleccionado_rel] = datetime.now(
        ).isoformat()
    else:
        logging.warning(
            f"{logPrefix} No se pudo seleccionar un archivo.")
    return archivo_seleccionado_rel

# --- Funciones para el manejo del estado de la misión activa ---


def cargar_estado_mision_activa():
    logPrefix = "cargar_estado_mision_activa:"
    if os.path.exists(ACTIVE_MISSION_STATE_FILE):
        try:
            with open(ACTIVE_MISSION_STATE_FILE, 'r', encoding='utf-8') as f:
                nombre_clave_mision = f.read().strip()
                if nombre_clave_mision:
                    logging.info(
                        f"{logPrefix} Misión activa encontrada: '{nombre_clave_mision}'")
                    return nombre_clave_mision
                else:
                    logging.warning(
                        f"{logPrefix} Archivo de estado de misión vacío.")
                    # Limpiar si está vacío
                    os.remove(ACTIVE_MISSION_STATE_FILE)
                    return None
        except Exception as e:
            logging.error(
                f"{logPrefix} Error cargando estado de misión activa: {e}", exc_info=True)
            return None
    logging.info(
        f"{logPrefix} No se encontró archivo de estado de misión activa.")
    return None


def guardar_estado_mision_activa(nombre_clave_mision: str):
    logPrefix = "guardar_estado_mision_activa:"
    try:
        os.makedirs(os.path.dirname(ACTIVE_MISSION_STATE_FILE), exist_ok=True)
        with open(ACTIVE_MISSION_STATE_FILE, 'w', encoding='utf-8') as f:
            f.write(nombre_clave_mision)
        logging.info(
            f"{logPrefix} Estado de misión activa '{nombre_clave_mision}' guardado.")
    except Exception as e:
        logging.error(
            f"{logPrefix} Error guardando estado de misión activa '{nombre_clave_mision}': {e}", exc_info=True)


def limpiar_estado_mision_activa():
    logPrefix = "limpiar_estado_mision_activa:"
    if os.path.exists(ACTIVE_MISSION_STATE_FILE):
        try:
            os.remove(ACTIVE_MISSION_STATE_FILE)
            logging.info(f"{logPrefix} Estado de misión activa limpiado.")
        except Exception as e:
            logging.error(
                f"{logPrefix} Error limpiando estado de misión activa: {e}", exc_info=True)
    else:
        logging.info(
            f"{logPrefix} No había estado de misión activa para limpiar.")


def orchestrarEjecucionScript(args):
    api_provider_seleccionado = "openrouter" if args.openrouter else "google"
    logging.info(
        f"Iniciando lógica de orquestación ADAPTATIVA. Proveedor API: {api_provider_seleccionado.upper()}. Modo Automático: {'Activado' if args.modo_automatico else 'Desactivado'}")

    if api_provider_seleccionado == 'google' and not settings.GEMINIAPIKEY:
        logging.critical(
            "Error: Google Gemini seleccionado pero GEMINI_API_KEY no configurada. Abortando.")
        return 2
    elif api_provider_seleccionado == 'openrouter' and not settings.OPENROUTER_API_KEY:
        logging.critical(
            "Error: OpenRouter seleccionado pero OPENROUTER_API_KEY no configurada. Abortando.")
        return 2

    if hasattr(signal, 'SIGALRM'):
        logging.info(
            f"Configurando timeout de ejecución a {settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS} segundos.")
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS)
    else:
        logging.warning(
            "signal.alarm no disponible. Timeout general no activo.")

    exit_code = 1
    try:
        # En lugar de un ciclo, ahora se ejecuta una "fase"
        fase_exitosa = ejecutarFaseDelAgente(
            api_provider_seleccionado, args.modo_automatico)
        if fase_exitosa:  # fase_exitosa ahora significa que la fase se completó sin error crítico del agente
            logging.info("Fase del agente completada.")
            exit_code = 0  # El script sale con 0 si la fase fue OK, se reiniciará para la siguiente fase
        else:
            logging.warning(
                "Fase del agente finalizó con problemas o interrupciones. Ver logs.")
            exit_code = 1
    except TimeoutException:
        logging.critical(
            f"TIMEOUT: Script terminado por exceder límite de {settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS}s.")
        exit_code = 124
    except Exception as e:
        logging.critical(
            f"Error fatal no manejado en orquestación: {e}", exc_info=True)
        exit_code = 2
    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        # Guardar registro de archivos siempre
        guardar_registro_archivos(cargar_registro_archivos())
        logging.info(
            "Registro de archivos analizados guardado al finalizar script.")
    return exit_code


def _validarConfiguracionEsencial(api_provider: str) -> bool:
    logPrefix = f"_validarConfiguracionEsencial({api_provider.upper()}):"
    if not settings.REPOSITORIOURL:
        logging.critical(
            f"{logPrefix} REPOSITORIOURL no está configurado en settings.py. Abortando.")
        return False
    if api_provider == 'google':
        if not settings.GEMINIAPIKEY:
            logging.critical(
                f"{logPrefix} Google Gemini seleccionado pero GEMINI_API_KEY no configurada. Abortando.")
            return False
    elif api_provider == 'openrouter':
        if not settings.OPENROUTER_API_KEY:
            logging.critical(
                f"{logPrefix} OpenRouter seleccionado pero OPENROUTER_API_KEY no configurada. Abortando.")
            return False
    else:
        logging.critical(
            f"{logPrefix} Proveedor API desconocido: '{api_provider}'. Abortando.")
        return False
    logging.info(
        f"{logPrefix} Configuración esencial validada para proveedor '{api_provider}'.")
    return True


def _timeout_handler(signum, frame):
    logging.error("¡Tiempo límite de ejecución alcanzado!")
    raise TimeoutException("El script excedió el tiempo máximo de ejecución.")


def configurarLogging():
    log_raiz = logging.getLogger()
    if log_raiz.handlers:
        for handler in log_raiz.handlers[:]:
            log_raiz.removeHandler(handler)
            handler.close()
    nivelLog = logging.DEBUG
    formatoLog = '%(asctime)s - %(levelname)s - [%(name)s] %(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'
    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    log_raiz.addHandler(consolaHandler)
    try:
        rutaLogArchivo = os.path.join(
            settings.RUTA_BASE_PROYECTO, "refactor_adaptativo.log")
        os.makedirs(os.path.dirname(rutaLogArchivo), exist_ok=True)
        archivoHandler = logging.FileHandler(
            rutaLogArchivo, mode='w', encoding='utf-8')
        archivoHandler.setFormatter(
            logging.Formatter(formatoLog, fechaFormato))
        log_raiz.addHandler(archivoHandler)
    except Exception as e:
        print(
            f"ERROR CRITICO [configurarLogging]: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}", file=sys.stderr)
    log_raiz.setLevel(nivelLog)
    logging.info("="*50)
    logging.info("Sistema de logging configurado para modo adaptativo.")
    logging.info(f"Nivel de log: {logging.getLevelName(log_raiz.level)}")


# --- Funciones específicas para los nuevos pasos ---

def paso0_revisar_mision_local(ruta_repo):
    """
    Paso 0: Revisa si existe misionOrion.md EN LA RAMA ACTUAL.
    Se espera que esta función sea llamada cuando el agente ya está en una rama de misión
    potencial, o en la rama de trabajo principal si no hay misión activa.
    """
    logPrefix = "paso0_revisar_mision_local:"
    rama_actual = manejadorGit.obtener_rama_actual(ruta_repo)
    logging.info(
        f"{logPrefix} Revisando {MISION_ORION_MD} en rama actual: '{rama_actual}'")
    ruta_mision_orion = os.path.join(ruta_repo, MISION_ORION_MD)

    if os.path.exists(ruta_mision_orion):
        logging.info(
            f"{logPrefix} Se encontró {MISION_ORION_MD} en '{rama_actual}'.")
        try:
            with open(ruta_mision_orion, 'r', encoding='utf-8') as f:
                contenido_mision = f.read()

            metadatos, lista_tareas, hay_tareas_pendientes = manejadorMision.parsear_mision_orion(
                contenido_mision)

            if not metadatos or not metadatos.get("nombre_clave"):
                logging.warning(
                    f"{logPrefix} {MISION_ORION_MD} existe pero no se pudo extraer metadatos/nombre clave. Se tratará como para crear nueva misión.")
                # metadatos, lista_tareas, nombre_clave
                return "ignorar_mision_actual_y_crear_nueva", None, None, None

            nombre_clave_parseado = metadatos["nombre_clave"]
            estado_general_mision = metadatos.get(
                "estado_general", "PENDIENTE")

            # Validar si el nombre clave en el archivo coincide con el esperado de la rama activa (si aplica)
            # Esta validación es más para consistencia.

            if hay_tareas_pendientes and estado_general_mision not in ["COMPLETADA", "FALLIDA"]:
                logging.info(
                    f"{logPrefix} Misión '{nombre_clave_parseado}' con tareas pendientes y estado '{estado_general_mision}'. Lista para procesar.")
                return "procesar_mision_existente", metadatos, lista_tareas, nombre_clave_parseado
            else:
                logging.info(
                    f"{logPrefix} Misión '{nombre_clave_parseado}' sin tareas pendientes o en estado '{estado_general_mision}'. Se considera completada o fallida.")
                return "mision_existente_finalizada", metadatos, lista_tareas, nombre_clave_parseado
        except Exception as e:
            logging.error(
                f"{logPrefix} Error leyendo o parseando {MISION_ORION_MD}: {e}. Se intentará crear una nueva.", exc_info=True)
            return "ignorar_mision_actual_y_crear_nueva", None, None, None
    else:
        logging.info(
            f"{logPrefix} No se encontró {MISION_ORION_MD} en rama '{rama_actual}'.")
        return "no_hay_mision_local", None, None, None


def paso1_1_seleccion_y_decision_inicial(ruta_repo, api_provider, registro_archivos):
    logPrefix = "paso1_1_seleccion_y_decision_inicial:"
    archivo_seleccionado_rel = seleccionar_archivo_mas_antiguo(
        ruta_repo, registro_archivos)
    guardar_registro_archivos(registro_archivos)

    if not archivo_seleccionado_rel:
        logging.warning(f"{logPrefix} No se pudo seleccionar ningún archivo.")
        return "ciclo_terminado_sin_accion", None, None, None

    ruta_archivo_seleccionado_abs = os.path.join(
        ruta_repo, archivo_seleccionado_rel)
    if not os.path.exists(ruta_archivo_seleccionado_abs):
        logging.error(
            f"{logPrefix} Archivo seleccionado '{archivo_seleccionado_rel}' no existe. Reintentando.")
        registro_archivos[archivo_seleccionado_rel] = datetime.now(
        ).isoformat() + "_NOT_FOUND"
        guardar_registro_archivos(registro_archivos)
        return "reintentar_seleccion", None, None, None

    estructura_proyecto = analizadorCodigo.generarEstructuraDirectorio(
        ruta_repo, directorios_ignorados=settings.DIRECTORIOS_IGNORADOS, max_depth=5, incluir_archivos=True)

    resultado_lectura = analizadorCodigo.leerArchivos(
        [ruta_archivo_seleccionado_abs], ruta_repo, api_provider=api_provider)
    contenido_archivo = resultado_lectura['contenido']
    tokens_contenido = resultado_lectura['tokens']
    tokens_estructura = analizadorCodigo.contarTokensTexto(
        estructura_proyecto or "", api_provider)
    tokens_estimados = 500 + tokens_contenido + \
        tokens_estructura  # 500 para prompt base

    gestionar_limite_tokens(tokens_estimados, api_provider)

    decision_IA_paso1_1 = analizadorCodigo.solicitar_evaluacion_archivo(
        # reglas_refactor vacío por ahora
        archivo_seleccionado_rel, contenido_archivo, estructura_proyecto, api_provider, ""
    )
    registrar_tokens_usados(decision_IA_paso1_1.get(
        "tokens_consumidos_api", tokens_estimados) if decision_IA_paso1_1 else tokens_estimados)

    if not decision_IA_paso1_1 or not decision_IA_paso1_1.get("necesita_refactor"):
        logging.info(f"{logPrefix} IA decidió que '{archivo_seleccionado_rel}' no necesita refactor. Razón: {decision_IA_paso1_1.get('razonamiento', 'N/A') if decision_IA_paso1_1 else 'Error IA'}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO1.1_NO_REFACTOR:{archivo_seleccionado_rel}", decision=decision_IA_paso1_1)
        ])
        return "reintentar_seleccion", None, None, None

    logging.info(
        f"{logPrefix} IA decidió SÍ refactorizar '{archivo_seleccionado_rel}'. Razón: {decision_IA_paso1_1.get('razonamiento')}")
    archivos_ctx_sugeridos_rel = decision_IA_paso1_1.get(
        "archivos_contexto_sugeridos", [])
    archivos_ctx_validados_rel = []
    if decision_IA_paso1_1.get("necesita_contexto_adicional"):
        for f_rel in archivos_ctx_sugeridos_rel:
            if not f_rel or f_rel == archivo_seleccionado_rel:
                continue
            if os.path.exists(os.path.join(ruta_repo, f_rel)) and os.path.isfile(os.path.join(ruta_repo, f_rel)):
                archivos_ctx_validados_rel.append(f_rel)
            else:
                logging.warning(
                    f"{logPrefix} Archivo de contexto sugerido '{f_rel}' no existe. Descartado.")

    return "generar_mision", archivo_seleccionado_rel, archivos_ctx_validados_rel, decision_IA_paso1_1


def paso1_2_generar_mision(ruta_repo, archivo_a_refactorizar_rel, archivos_contexto_para_crear_mision_rel, decision_paso1_1, api_provider):
    logPrefix = "paso1_2_generar_mision:"
    logging.info(
        f"{logPrefix} Generando misión para: '{archivo_a_refactorizar_rel}' con contexto gen: {archivos_contexto_para_crear_mision_rel}")

    archivos_para_leer_abs = [os.path.join(
        ruta_repo, archivo_a_refactorizar_rel)]
    for f_rel in archivos_contexto_para_crear_mision_rel:
        archivos_para_leer_abs.append(os.path.join(ruta_repo, f_rel))
    archivos_para_leer_abs_unicos = sorted(list(set(archivos_para_leer_abs)))

    resultado_lectura_ctx = analizadorCodigo.leerArchivos(
        archivos_para_leer_abs_unicos, ruta_repo, api_provider=api_provider)
    contexto_completo_para_mision = resultado_lectura_ctx['contenido']
    tokens_contexto_mision = resultado_lectura_ctx['tokens']
    tokens_estimados = 700 + tokens_contexto_mision  # 700 para prompt base

    gestionar_limite_tokens(tokens_estimados, api_provider)

    contenido_mision_generado_dict = analizadorCodigo.generar_contenido_mision_orion(
        archivo_a_refactorizar_rel, contexto_completo_para_mision,
        decision_paso1_1.get("razonamiento"), api_provider,
        archivos_contexto_generacion_rel_list=archivos_contexto_para_crear_mision_rel
    )
    registrar_tokens_usados(contenido_mision_generado_dict.get(
        "tokens_consumidos_api", tokens_estimados) if contenido_mision_generado_dict else tokens_estimados)

    if not contenido_mision_generado_dict or \
       not contenido_mision_generado_dict.get("nombre_clave_mision") or \
       not contenido_mision_generado_dict.get("contenido_markdown_mision"):
        logging.error(
            f"{logPrefix} IA no generó contenido válido. Respuesta: {contenido_mision_generado_dict}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO1.2_ERROR_GENERACION", decision=decision_paso1_1, error_message="IA no generó misión válida")
        ])
        return "error_generando_mision", None, None

    nombre_clave_mision = contenido_mision_generado_dict["nombre_clave_mision"]
    contenido_markdown_mision = contenido_mision_generado_dict["contenido_markdown_mision"]

    rama_base = manejadorGit.obtener_rama_actual(
        ruta_repo) or settings.RAMATRABAJO
    if not manejadorGit.crear_y_cambiar_a_rama(ruta_repo, nombre_clave_mision, rama_base):
        logging.error(
            f"{logPrefix} No se pudo crear o cambiar a rama '{nombre_clave_mision}' desde '{rama_base}'.")
        return "error_generando_mision", None, None
    logging.info(
        f"{logPrefix} En rama de misión: '{nombre_clave_mision}' (desde '{rama_base}')")

    try:
        with open(os.path.join(ruta_repo, MISION_ORION_MD), 'w', encoding='utf-8') as f:
            f.write(contenido_markdown_mision)
        logging.info(
            f"{logPrefix} {MISION_ORION_MD} guardado en rama '{nombre_clave_mision}'")
    except Exception as e:
        logging.error(
            f"{logPrefix} Error guardando {MISION_ORION_MD}: {e}", exc_info=True)
        manejadorGit.cambiar_a_rama_existente(ruta_repo, rama_base)
        manejadorGit.eliminarRama(ruta_repo, nombre_clave_mision, local=True)
        return "error_generando_mision", None, None

    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Crear misión: {nombre_clave_mision}", [MISION_ORION_MD]):
        logging.error(
            f"{logPrefix} No se pudo hacer commit de {MISION_ORION_MD} en '{nombre_clave_mision}'.")
        # No eliminar la rama si el commit falló pero el archivo se creó, podría ser útil para debug manual
        # manejadorGit.cambiar_a_rama_existente(ruta_repo, rama_base); manejadorGit.eliminarRama(ruta_repo, nombre_clave_mision, local=True)
        return "error_generando_mision", None, None  # Error si el commit del MD falla

    logging.info(
        f"{logPrefix} Misión '{nombre_clave_mision}' generada y commiteada.")
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(
            outcome=f"PASO1.2_MISION_GENERADA:{nombre_clave_mision}", result_details=f"Archivo: {MISION_ORION_MD}")
    ])
    return "mision_generada_ok", contenido_markdown_mision, nombre_clave_mision


def paso2_ejecutar_tarea_mision(ruta_repo, nombre_rama_mision, api_provider, modo_automatico):
    # Esta función ahora es llamada cuando ya se está en la rama de la misión.
    # El contenido de la misión (metadatos, lista_tareas) se carga desde el archivo en la rama.
    logPrefix = f"paso2_ejecutar_tarea_mision (Rama: {nombre_rama_mision}):"
    logging.info(f"{logPrefix} Iniciando ejecución de tarea.")

    # Asegurar estar en la rama correcta (doble check)
    if manejadorGit.obtener_rama_actual(ruta_repo) != nombre_rama_mision:
        logging.warning(
            f"{logPrefix} No se estaba en la rama '{nombre_rama_mision}'. Intentando cambiar...")
        if not manejadorGit.cambiar_a_rama_existente(ruta_repo, nombre_rama_mision):
            logging.error(
                f"{logPrefix} No se pudo cambiar a rama '{nombre_rama_mision}'. Abortando tarea.")
            # Retorna (estado_final_fase, contenido_mision_actualizado_o_none)
            return "error_critico_git", None

    ruta_mision_actual_md = os.path.join(ruta_repo, MISION_ORION_MD)
    contenido_mision_actual_md = ""
    if os.path.exists(ruta_mision_actual_md):
        with open(ruta_mision_actual_md, 'r', encoding='utf-8') as f:
            contenido_mision_actual_md = f.read()
    else:
        logging.error(
            f"{logPrefix} {MISION_ORION_MD} no encontrado en la rama '{nombre_rama_mision}'. Abortando tarea.")
        return "error_critico_mision_no_encontrada", None

    metadatos_mision, lista_tareas_mision, _ = manejadorMision.parsear_mision_orion(
        contenido_mision_actual_md)
    if not metadatos_mision:
        logging.error(
            f"{logPrefix} Fallo al re-parsear {MISION_ORION_MD} desde la rama. Abortando tarea.")
        return "error_critico_parseo_mision", contenido_mision_actual_md

    tarea_actual_info, _ = manejadorMision.obtener_proxima_tarea_pendiente(
        lista_tareas_mision)

    if not tarea_actual_info:
        logging.info(
            f"{logPrefix} No se encontraron tareas pendientes en '{nombre_rama_mision}'. Considerada completada.")
        return "mision_completada", contenido_mision_actual_md

    tarea_id = tarea_actual_info.get("id", "N/A_ID")
    tarea_titulo = tarea_actual_info.get("titulo", "N/A_Titulo")
    logging.info(
        f"{logPrefix} Tarea a ejecutar: ID '{tarea_id}', Título: '{tarea_titulo}'")

    # --- INICIO: Limpieza de rutas de archivo ---
    def limpiar_lista_rutas(lista_rutas_crudas, origen_rutas_log=""):
        rutas_limpias_final = []
        if not lista_rutas_crudas:
            return rutas_limpias_final

        for ruta_cruda in lista_rutas_crudas:
            if not isinstance(ruta_cruda, str) or not ruta_cruda.strip():
                logging.warning(
                    f"{logPrefix} Ruta inválida o vacía encontrada en {origen_rutas_log}: '{ruta_cruda}'. Se ignora.")
                continue

            # Aplicar misma lógica de limpieza que en parsear_mision_orion (parte metadatos)
            ruta_procesada = ruta_cruda.strip()
            ruta_procesada = ruta_procesada.replace('[', '').replace(']', '')
            if ruta_procesada.startswith('/') or ruta_procesada.startswith('\\'):
                ruta_procesada = ruta_procesada[1:]
            ruta_procesada = ruta_procesada.strip()

            if ruta_procesada and ruta_procesada.lower() not in ["ninguno", "ninguno."]:
                # Validar que la ruta realmente exista después de la limpieza y antes de añadirla
                ruta_abs_candidata = os.path.join(ruta_repo, ruta_procesada)
                if os.path.exists(ruta_abs_candidata) and os.path.isfile(ruta_abs_candidata):
                    rutas_limpias_final.append(ruta_procesada)
                    logging.debug(
                        f"{logPrefix} Ruta '{ruta_procesada}' de {origen_rutas_log} validada y añadida para contexto.")
                else:
                    logging.warning(
                        f"{logPrefix} Ruta '{ruta_procesada}' (original: '{ruta_cruda}') de {origen_rutas_log} no existe o no es un archivo. Se ignora.")
            elif ruta_procesada:
                logging.debug(
                    f"{logPrefix} Ruta individual '{ruta_cruda}' de {origen_rutas_log} descartada después de limpieza (quedó vacía o como 'ninguno').")
        return rutas_limpias_final

    archivos_ctx_ejecucion_mision_crudos = metadatos_mision.get(
        "archivos_contexto_ejecucion", [])
    archivos_especificos_tarea_crudos = tarea_actual_info.get(
        "archivos_implicados_especificos", [])
    archivo_principal_mision_crudo = metadatos_mision.get("archivo_principal")

    archivos_ctx_ejecucion_limpios = limpiar_lista_rutas(
        archivos_ctx_ejecucion_mision_crudos, "metadatos[archivos_contexto_ejecucion]")
    archivos_especificos_tarea_limpios = limpiar_lista_rutas(
        archivos_especificos_tarea_crudos, f"tarea ID '{tarea_id}'[archivos_implicados_especificos]")

    # El archivo principal también se limpia y valida, aunque es uno solo
    archivos_principal_limpios = []
    if archivo_principal_mision_crudo:
        archivos_principal_limpios = limpiar_lista_rutas(
            [archivo_principal_mision_crudo], "metadatos[archivo_principal]")
    # --- FIN: Limpieza de rutas de archivo ---

    archivos_para_leer_rel = []
    if archivos_principal_limpios:  # Será una lista con 0 o 1 elemento
        archivos_para_leer_rel.extend(archivos_principal_limpios)
    archivos_para_leer_rel.extend(archivos_ctx_ejecucion_limpios)
    archivos_para_leer_rel.extend(archivos_especificos_tarea_limpios)

    # Eliminar duplicados y ordenar (aunque el orden no es crítico para leerArchivos)
    archivos_para_leer_rel = sorted(list(set(archivos_para_leer_rel)))

    contexto_para_tarea_str, tokens_contexto_tarea = "", 0
    archivos_leidos_para_tarea_rel = []

    if archivos_para_leer_rel:
        # Las rutas en archivos_para_leer_rel ya son relativas, limpias y validadas (existen)
        archivos_abs_ctx_tarea = [os.path.join(
            ruta_repo, f_rel) for f_rel in archivos_para_leer_rel]

        # leerArchivos internamente también valida existencia, pero aquí ya lo hemos hecho.
        resultado_lectura_ctx = analizadorCodigo.leerArchivos(
            archivos_abs_ctx_tarea, ruta_repo, api_provider=api_provider)
        contexto_para_tarea_str = resultado_lectura_ctx['contenido']
        tokens_contexto_tarea = resultado_lectura_ctx['tokens']
        # archivos_leidos_para_tarea_rel se puede reconstruir desde las rutas que sí se leyeron
        # o asumir que todas las de archivos_para_leer_rel se leyeron porque ya las validamos.
        # Para ser precisos, podríamos obtenerlo de resultado_lectura_ctx si leerArchivos lo devuelve.
        # Por ahora, usamos nuestra lista validada:
        archivos_leidos_para_tarea_rel = archivos_para_leer_rel
        logging.info(
            f"{logPrefix} Contexto para tarea leído de {len(archivos_leidos_para_tarea_rel)} archivo(s) validados: {archivos_leidos_para_tarea_rel}")
    else:
        logging.info(
            f"{logPrefix} No se definieron o validaron archivos para leer como contexto para la tarea.")

    tokens_mision_y_tarea_desc = analizadorCodigo.contarTokensTexto(
        contenido_mision_actual_md + tarea_actual_info.get('descripcion', ''), api_provider)
    tokens_estimados = 800 + tokens_contexto_tarea + tokens_mision_y_tarea_desc

    gestionar_limite_tokens(tokens_estimados, api_provider)

    resultado_ejecucion_tarea = analizadorCodigo.ejecutar_tarea_especifica_mision(
        tarea_actual_info, contenido_mision_actual_md, contexto_para_tarea_str, api_provider
    )
    registrar_tokens_usados(resultado_ejecucion_tarea.get(
        "tokens_consumidos_api", tokens_estimados) if resultado_ejecucion_tarea else tokens_estimados)

    contenido_mision_post_tarea = contenido_mision_actual_md  # Inicializar

    if not resultado_ejecucion_tarea or "archivos_modificados" not in resultado_ejecucion_tarea:
        logging.error(
            f"{logPrefix} IA no devolvió 'archivos_modificados'. Respuesta: {resultado_ejecucion_tarea}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO2_ERROR_TAREA_IA:{nombre_rama_mision}", decision=tarea_actual_info, error_message="IA no generó cambios válidos")
        ])
        # Marcar tarea como fallida temporalmente
        contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
            contenido_mision_actual_md,
            tarea_id,
            "FALLIDA_TEMPORALMENTE",
            incrementar_intentos_si_fallida_temp=True
        )
        if not contenido_mision_post_tarea:
            return "error_critico_actualizando_mision", contenido_mision_actual_md
        try:
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f:
                f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' FALLIDA_TEMPORALMENTE (IA)", [MISION_ORION_MD]):
                logging.error(
                    f"{logPrefix} No se pudo commitear {MISION_ORION_MD} (tarea fallida IA).")
        except Exception as e:
            logging.error(
                f"{logPrefix} Error guardando/commiteando {MISION_ORION_MD} (tarea fallida IA): {e}")
            return "error_critico_actualizando_mision", contenido_mision_actual_md
        return "tarea_fallida", contenido_mision_post_tarea

    if resultado_ejecucion_tarea.get("advertencia_ejecucion") and not resultado_ejecucion_tarea.get("archivos_modificados"):
        logging.warning(
            f"{logPrefix} IA advirtió: {resultado_ejecucion_tarea['advertencia_ejecucion']}. Tarea no resultó en cambios. Marcando como SALTADA.")
        contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
            contenido_mision_actual_md, tarea_id, "SALTADA")
        if not contenido_mision_post_tarea:
            return "error_critico_actualizando_mision", contenido_mision_actual_md
        try:
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f:
                f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' SALTADA", [MISION_ORION_MD]):
                # No crítico para el flujo
                logging.error(
                    f"{logPrefix} No se pudo commitear {MISION_ORION_MD} (tarea saltada).")
        except Exception as e:
            # No crítico
            logging.error(
                f"{logPrefix} Error guardando {MISION_ORION_MD} (tarea saltada): {e}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO2_TAREA_SALTADA:{nombre_rama_mision}", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("advertencia_ejecucion"))
        ])
        _, _, hay_pendientes_despues_salto = manejadorMision.parsear_mision_orion(
            contenido_mision_post_tarea)
        return "mision_completada" if not hay_pendientes_despues_salto else "tarea_ejecutada_continuar_mision", contenido_mision_post_tarea

    if resultado_ejecucion_tarea.get("archivos_modificados"):
        exito_aplicar, msg_err_aplicar = aplicadorCambios.aplicarCambiosSobrescrituraV2(
            resultado_ejecucion_tarea["archivos_modificados"], ruta_repo,
            accionOriginal=f"modificar_segun_tarea_mision:{nombre_rama_mision}", paramsOriginal=tarea_actual_info
        )
        if not exito_aplicar:
            logging.error(
                f"{logPrefix} Falló aplicación de cambios: {msg_err_aplicar}")
            manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                manejadorHistorial.formatearEntradaHistorial(
                    outcome=f"PASO2_APPLY_FAIL:{nombre_rama_mision}", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea, error_message=msg_err_aplicar)
            ])
            # Descartar cambios fallidos de ESTA tarea
            manejadorGit.descartarCambiosLocales(ruta_repo)
            contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
                contenido_mision_actual_md,
                tarea_id,
                "FALLIDA_TEMPORALMENTE",
                incrementar_intentos_si_fallida_temp=True
            )
            if not contenido_mision_post_tarea:
                return "error_critico_actualizando_mision", contenido_mision_actual_md
            try:
                with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f:
                    f.write(contenido_mision_post_tarea)
                if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' FALLIDA_TEMPORALMENTE (apply)", [MISION_ORION_MD]):
                    logging.error(
                        f"{logPrefix} No se pudo commitear {MISION_ORION_MD} (tarea fallida apply).")
            except Exception as e:
                logging.error(
                    f"{logPrefix} Error guardando/commiteando {MISION_ORION_MD} (tarea fallida apply): {e}")
            return "tarea_fallida", contenido_mision_post_tarea

        commit_msg = f"Tarea ID {tarea_id} ({tarea_titulo[:50]}) completada (Misión {nombre_rama_mision})"
        if not manejadorGit.hacerCommit(ruta_repo, commit_msg):
            logging.warning(
                f"{logPrefix} No se realizó commit para tarea (quizás sin cambios efectivos o fallo en git add/commit). AÚN ASÍ, la tarea se marca como COMPLETADA en el MD.")
    else:
        logging.info(
            f"{logPrefix} IA no especificó archivos modificados (y no fue manejado por advertencia). Asumiendo tarea sin efecto.")

    contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
        contenido_mision_actual_md, tarea_id, "COMPLETADA")
    if not contenido_mision_post_tarea:
        return "error_critico_actualizando_mision", contenido_mision_actual_md

    try:
        with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f:
            f.write(contenido_mision_post_tarea)
    except Exception as e:
        logging.error(f"{logPrefix} Error guardando {MISION_ORION_MD}: {e}")
        return "error_critico_actualizando_mision", contenido_mision_actual_md

    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Actualizar Misión '{nombre_rama_mision}', Tarea '{tarea_id}' completada", [MISION_ORION_MD]):
        # No crítico para el flujo principal de tarea
        logging.error(
            f"{logPrefix} No se pudo commitear actualización de {MISION_ORION_MD}.")

    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(
            outcome=f"PASO2_TAREA_OK:{nombre_rama_mision}", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("archivos_modificados"))
    ])

    _, _, hay_pendientes_actualizada = manejadorMision.parsear_mision_orion(
        contenido_mision_post_tarea)
    return "mision_completada" if not hay_pendientes_actualizada else "tarea_ejecutada_continuar_mision", contenido_mision_post_tarea


# --- Función Principal de Fase del Agente (MODIFICADO) ---
def _crearNuevaMision(api_provider: str, modo_automatico: bool, registro_archivos_analizados: dict):
    logPrefix = "_crearNuevaMision:"
    logging.info(f"{logPrefix} Iniciando proceso de creación de nueva misión.")

    # Asegurar estar en RAMATRABAJO antes de cualquier intento de crear nueva misión.
    # Esto debería ser garantizado por el llamador (ejecutarFaseDelAgente)
    if manejadorGit.obtener_rama_actual(settings.RUTACLON) != settings.RAMATRABAJO:
        logging.info(
            f"{logPrefix} No se está en '{settings.RAMATRABAJO}'. Intentando cambiar...")
        if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(
                f"{logPrefix} No se pudo cambiar a '{settings.RAMATRABAJO}'. Abortando creación de misión.")
            return False

    mision_desde_todo_creada_ok = False
    if modo_automatico:
        logging.info(
            f"{logPrefix} Modo automático activo. Verificando TODO.md para nueva misión.")
        ruta_todo_md = os.path.join(settings.RUTACLON, "TODO.md")
        if os.path.exists(ruta_todo_md) and os.path.isfile(ruta_todo_md):
            try:
                with open(ruta_todo_md, 'r', encoding='utf-8') as f_todo:
                    contenido_todo_md = f_todo.read().strip()
                if contenido_todo_md:
                    logging.info(
                        f"{logPrefix} TODO.md encontrado con contenido. Intentando generar misión.")

                    tokens_contenido_todo = analizadorCodigo.contarTokensTexto(
                        contenido_todo_md, api_provider)
                    tokens_estimados_todo = 700 + tokens_contenido_todo
                    gestionar_limite_tokens(
                        tokens_estimados_todo, api_provider)

                    contenido_mision_generado_dict_todo = analizadorCodigo.generar_contenido_mision_desde_texto_guia(
                        settings.RUTACLON,
                        contenido_todo_md,
                        "TODO.md",
                        api_provider
                    )
                    registrar_tokens_usados(contenido_mision_generado_dict_todo.get(
                        "tokens_consumidos_api", tokens_estimados_todo) if contenido_mision_generado_dict_todo else tokens_estimados_todo)

                    if contenido_mision_generado_dict_todo and \
                       contenido_mision_generado_dict_todo.get("nombre_clave_mision") and \
                       contenido_mision_generado_dict_todo.get("contenido_markdown_mision"):

                        nombre_clave_mision_todo = contenido_mision_generado_dict_todo[
                            "nombre_clave_mision"]
                        contenido_markdown_mision_todo = contenido_mision_generado_dict_todo[
                            "contenido_markdown_mision"]
                        rama_base_todo = manejadorGit.obtener_rama_actual(
                            settings.RUTACLON) or settings.RAMATRABAJO

                        if not manejadorGit.crear_y_cambiar_a_rama(settings.RUTACLON, nombre_clave_mision_todo, rama_base_todo):
                            logging.error(
                                f"{logPrefix} No se pudo crear o cambiar a rama '{nombre_clave_mision_todo}' (desde TODO.md) desde '{rama_base_todo}'.")
                        else:
                            logging.info(
                                f"{logPrefix} En rama de misión (desde TODO.md): '{nombre_clave_mision_todo}' (desde '{rama_base_todo}')")
                            try:
                                with open(os.path.join(settings.RUTACLON, MISION_ORION_MD), 'w', encoding='utf-8') as f_mision_todo:
                                    f_mision_todo.write(
                                        contenido_markdown_mision_todo)
                                logging.info(
                                    f"{logPrefix} {MISION_ORION_MD} (desde TODO.md) guardado en rama '{nombre_clave_mision_todo}'")

                                _, tareas_gen_todo, hay_pendientes_gen_todo = manejadorMision.parsear_mision_orion(
                                    contenido_markdown_mision_todo)
                                if not tareas_gen_todo or not hay_pendientes_gen_todo:
                                    logging.error(
                                        f"{logPrefix} ERROR DE GENERACIÓN (TODO.md): Misión '{nombre_clave_mision_todo}' generada SIN TAREAS PENDIENTES a partir de TODO.md.")
                                    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                                        manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO_TODO_ERROR_MISION_SIN_TAREAS",
                                                                                     error_message=f"Misión '{nombre_clave_mision_todo}' (desde TODO.md) generada sin tareas.")])
                                    manejadorGit.cambiar_a_rama_existente(
                                        settings.RUTACLON, rama_base_todo)
                                    manejadorGit.eliminarRama(
                                        settings.RUTACLON, nombre_clave_mision_todo, local=True)
                                    logging.info(
                                        f"{logPrefix} Rama de misión (desde TODO.md) '{nombre_clave_mision_todo}' eliminada. Procediendo con flujo normal.")
                                else:
                                    if not manejadorGit.hacerCommitEspecifico(settings.RUTACLON, f"Crear misión desde TODO.md: {nombre_clave_mision_todo}", [MISION_ORION_MD]):
                                        logging.error(
                                            f"{logPrefix} No se pudo hacer commit de {MISION_ORION_MD} (desde TODO.md) en '{nombre_clave_mision_todo}'.")
                                    else:
                                        logging.info(
                                            f"{logPrefix} Misión (desde TODO.md) '{nombre_clave_mision_todo}' generada y commiteada.")
                                        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                                            manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO_TODO_MISION_GENERADA:{nombre_clave_mision_todo}", result_details=f"Fuente: TODO.md")])
                                        guardar_estado_mision_activa(
                                            nombre_clave_mision_todo)
                                        if modo_automatico:
                                            manejadorGit.hacerPush(
                                                settings.RUTACLON, nombre_clave_mision_todo, setUpstream=True)
                                        mision_desde_todo_creada_ok = True
                            except Exception as e_write_todo_mision:
                                logging.error(
                                    f"{logPrefix} Error guardando {MISION_ORION_MD} (desde TODO.md): {e_write_todo_mision}", exc_info=True)
                                manejadorGit.cambiar_a_rama_existente(
                                    settings.RUTACLON, rama_base_todo)
                                manejadorGit.eliminarRama(
                                    settings.RUTACLON, nombre_clave_mision_todo, local=True)
                    else:
                        logging.warning(
                            f"{logPrefix} IA no generó contenido válido para misión desde TODO.md. Respuesta: {contenido_mision_generado_dict_todo}")
                        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                            manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO_TODO_ERROR_GENERACION", error_message="IA no generó misión válida desde TODO.md")])
                else:
                    logging.info(
                        f"{logPrefix} TODO.md está vacío. Se ignorará.")
            except Exception as e_todo_read:
                logging.error(
                    f"{logPrefix} Error leyendo TODO.md: {e_todo_read}. Se ignorará.", exc_info=True)
        else:
            logging.info(
                f"{logPrefix} Archivo TODO.md no encontrado en la raíz del repositorio.")

    if mision_desde_todo_creada_ok:
        logging.info(
            f"{logPrefix} Misión creada desde TODO.md. Fase completada. Script se detendrá para procesarla.")
        return True  # Fase OK, el script principal se detendrá y reiniciará para procesar la nueva misión

    # Si no se creó misión desde TODO.md (o no modo_automatico, o TODO.md no existe/vacío, o falló creación)
    # continuar con el flujo normal de selección de archivo:
    logging.info(
        f"{logPrefix} Procediendo con selección de archivo estándar para refactorización...")
    res_paso1_1, archivo_sel, ctx_sel, decision_ia_1_1 = paso1_1_seleccion_y_decision_inicial(
        settings.RUTACLON, api_provider, registro_archivos_analizados)

    if res_paso1_1 == "generar_mision":
        logging.info(
            f"{logPrefix} Archivo '{archivo_sel}' seleccionado para refactor por IA. Generando misión.")
        res_paso1_2, _, nombre_clave_generado = paso1_2_generar_mision(
            settings.RUTACLON, archivo_sel, ctx_sel, decision_ia_1_1, api_provider)

        if res_paso1_2 == "mision_generada_ok" and nombre_clave_generado:
            ruta_mision_generada_md = os.path.join(
                settings.RUTACLON, MISION_ORION_MD)
            contenido_mision_generada_md = ""
            if os.path.exists(ruta_mision_generada_md):
                with open(ruta_mision_generada_md, 'r', encoding='utf-8') as f:
                    contenido_mision_generada_md = f.read()

            _, tareas_gen, hay_pendientes_gen = manejadorMision.parsear_mision_orion(
                contenido_mision_generada_md)
            se_espera_refactor = decision_ia_1_1.get(
                "necesita_refactor", False)

            if se_espera_refactor and (not tareas_gen or not hay_pendientes_gen):
                logging.error(
                    f"{logPrefix} ERROR DE GENERACIÓN: Paso 1.1 indicó refactor para '{archivo_sel}' pero misión '{nombre_clave_generado}' NO TIENE TAREAS PENDIENTES.")
                manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                    manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO1.2_ERROR_MISION_SIN_TAREAS", decision=decision_ia_1_1,
                                                                 error_message=f"Misión '{nombre_clave_generado}' generada sin tareas.")
                ])
                manejadorGit.cambiar_a_rama_existente(
                    settings.RUTACLON, settings.RAMATRABAJO)
                manejadorGit.eliminarRama(
                    settings.RUTACLON, nombre_clave_generado, local=True)
                logging.info(
                    f"{logPrefix} Rama de misión '{nombre_clave_generado}' eliminada. Fase de creación fallida.")
                return False  # Falló la fase de creación

            guardar_estado_mision_activa(nombre_clave_generado)
            logging.info(
                f"{logPrefix} Nueva misión estándar '{nombre_clave_generado}' creada y estado guardado. Script se detendrá para procesarla.")
            if modo_automatico:
                manejadorGit.hacerPush(
                    settings.RUTACLON, nombre_clave_generado, setUpstream=True)
            return True  # Fase OK, misión creada, script se detendrá

        else:  # Error en paso1_2_generar_mision (error_generando_mision)
            logging.error(
                f"{logPrefix} Error generando misión estándar (IA o Git). Fase de creación fallida.")
            manejadorGit.cambiar_a_rama_existente(
                settings.RUTACLON, settings.RAMATRABAJO)  # Asegurar estar en rama principal
            if nombre_clave_generado and manejadorGit.existe_rama(settings.RUTACLON, nombre_clave_generado, local_only=True):
                manejadorGit.eliminarRama(
                    settings.RUTACLON, nombre_clave_generado, local=True)
            return False  # Falló la fase de creación

    elif res_paso1_1 == "reintentar_seleccion":
        logging.info(
            f"{logPrefix} Paso 1.1 no seleccionó archivo o IA no vio refactor. Script se detendrá. Fase OK.")
        return True  # Fase OK, el script se detendrá y reintentará en la próxima ejecución

    elif res_paso1_1 == "ciclo_terminado_sin_accion":
        logging.info(
            f"{logPrefix} Paso 1.1 no encontró acción (ej. no hay archivos válidos). Script se detendrá. Fase OK.")
        return True  # Fase OK, el script se detendrá

    else:  # Resultado inesperado de paso1_1_seleccion_y_decision_inicial
        logging.error(
            f"{logPrefix} Resultado inesperado de paso1.1: {res_paso1_1}. Fase de creación fallida.")
        return False  # Falló la fase de creación


def ejecutarFaseDelAgente(api_provider: str, modo_automatico: bool):
    logPrefix = f"ejecutarFaseDelAgente({api_provider.upper()}):"
    logging.info(f"{logPrefix} ===== INICIO FASE AGENTE =====")

    if not _validarConfiguracionEsencial(api_provider):
        return False
    if api_provider == 'google' and settings.GEMINIAPIKEY and not analizadorCodigo.configurarGemini():
        logging.critical(f"{logPrefix} Falló config Google GenAI.")
        return False

    if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
        logging.error(
            f"{logPrefix} Falló preparación de repo en '{settings.RAMATRABAJO}'. Saliendo.")
        return False
    logging.info(
        f"{logPrefix} Repositorio listo en rama de trabajo principal: '{settings.RAMATRABAJO}'.")

    nombre_clave_mision_activa = cargar_estado_mision_activa()
    registro_archivos_analizados = cargar_registro_archivos()

    # --- PROCESAR MISIÓN EXISTENTE (SI HAY) ---
    if nombre_clave_mision_activa:
        estado_proc_mision, exito_fase_mision_existente = _procesarMisionExistente(
            nombre_clave_mision_activa, api_provider, modo_automatico
        )

        if estado_proc_mision == "PROCEDER_A_CREAR_NUEVA_MISION":
            # La misión activa no era procesable, o se completó/finalizó y se limpió el estado.
            # _procesarMisionExistente ya se encargó de limpiar .active_mission y cambiar a RAMATRABAJO.
            logging.info(f"{logPrefix} Se procederá a crear una nueva misión.")
            # La ejecución continúa al bloque de creación de nueva misión.
        elif estado_proc_mision in ["CONTINUAR_PROCESAMIENTO_MISION", "MISION_COMPLETADA_O_FINALIZADA"]:
            # La misión activa fue procesada (tarea ejecutada, o misión completada).
            # El script debe detenerse para la siguiente fase o porque la misión terminó.
            return exito_fase_mision_existente  # Debería ser True
        elif estado_proc_mision == "ERROR_PROCESANDO_MISION":
            logging.error(
                f"{logPrefix} Error crítico procesando la misión existente '{nombre_clave_mision_activa}'.")
            return False  # exito_fase_mision_existente debería ser False
        else:  # Estado inesperado
            logging.error(
                f"{logPrefix} Estado inesperado '{estado_proc_mision}' de _procesarMisionExistente. Tratando como error.")
            return False

    # --- CREAR NUEVA MISIÓN ---
    # Se llega aquí si no había misión activa al inicio, o si _procesarMisionExistente indicó
    # que se debe proceder a crear una nueva.
    # _procesarMisionExistente ya debería haber asegurado que estamos en RAMATRABAJO.
    # Como doble chequeo, o para el caso donde no había misión activa desde el inicio:
    if manejadorGit.obtener_rama_actual(settings.RUTACLON) != settings.RAMATRABAJO:
        logging.info(
            f"{logPrefix} Verificación: No se está en '{settings.RAMATRABAJO}'. Intentando cambiar...")
        if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(
                f"{logPrefix} CRÍTICO: No se pudo cambiar a '{settings.RAMATRABAJO}' antes de intentar crear nueva misión. Abortando.")
            return False

    logging.info(
        f"{logPrefix} Procediendo a la lógica de creación de nueva misión.")
    exito_fase_creacion = _crearNuevaMision(
        api_provider, modo_automatico, registro_archivos_analizados)
    return exito_fase_creacion


def realizarReseteoAgente():
    logPrefix = "realizarReseteoAgente:"
    logging.info(f"{logPrefix} Iniciando reseteo del estado del agente...")

    # Es importante asegurarse que las configuraciones básicas como RUTACLON estén disponibles.
    # Esto normalmente ocurre cuando se importa settings, pero una verificación no hace daño.
    if not hasattr(settings, 'RUTACLON') or not hasattr(settings, 'RAMATRABAJO'):
        logging.critical(
            f"{logPrefix} Configuraciones esenciales (RUTACLON, RAMATRABAJO) no disponibles. Abortando reseteo.")
        return False  # Indicar fallo

    nombre_mision_activa = cargar_estado_mision_activa()

    if nombre_mision_activa:
        logging.info(
            f"{logPrefix} Misión activa encontrada según el archivo de estado: '{nombre_mision_activa}'.")
        ruta_repo_git = os.path.join(settings.RUTACLON, '.git')
        if not os.path.isdir(ruta_repo_git):
            logging.warning(
                f"{logPrefix} El directorio de clonación '{settings.RUTACLON}' no parece ser un repositorio Git válido (falta '{ruta_repo_git}'). No se puede gestionar la rama de misión '{nombre_mision_activa}'.")
        else:
            logging.info(
                f"{logPrefix} Intentando limpiar la rama de misión local '{nombre_mision_activa}'.")
            rama_actual_repo = manejadorGit.obtener_rama_actual(
                settings.RUTACLON)

            if rama_actual_repo == nombre_mision_activa:
                logging.info(
                    f"{logPrefix} Actualmente en la rama de misión '{nombre_mision_activa}'. Cambiando a la rama de trabajo principal '{settings.RAMATRABAJO}' antes de eliminar.")
                if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                    logging.error(
                        f"{logPrefix} No se pudo cambiar a la rama de trabajo '{settings.RAMATRABAJO}'. La rama de misión '{nombre_mision_activa}' no será eliminada. Puede requerir intervención manual.")
                else:
                    # No eliminar remota por defecto
                    if not manejadorGit.eliminarRama(settings.RUTACLON, nombre_mision_activa, local=True, remota=False):
                        logging.warning(
                            f"{logPrefix} No se pudo eliminar la rama de misión local '{nombre_mision_activa}'. Puede que necesite intervención manual.")
                    else:
                        logging.info(
                            f"{logPrefix} Rama de misión local '{nombre_mision_activa}' eliminada.")
            elif manejadorGit.existe_rama(settings.RUTACLON, nombre_mision_activa, local_only=True):
                # No estamos en la rama de misión, pero existe localmente
                logging.info(
                    f"{logPrefix} La rama de misión '{nombre_mision_activa}' existe localmente (pero no es la actual). Procediendo a eliminarla.")
                if not manejadorGit.eliminarRama(settings.RUTACLON, nombre_mision_activa, local=True, remota=False):
                    logging.warning(
                        f"{logPrefix} No se pudo eliminar la rama de misión local '{nombre_mision_activa}'.")
                else:
                    logging.info(
                        f"{logPrefix} Rama de misión local '{nombre_mision_activa}' eliminada.")
            else:
                logging.info(
                    f"{logPrefix} La rama de misión '{nombre_mision_activa}' (indicada en el estado activo) no existe localmente. No se requiere eliminación de rama.")
    else:
        logging.info(
            f"{logPrefix} No hay misión activa registrada en el archivo de estado. No se requiere limpieza de rama de misión específica por estado.")

    limpiar_estado_mision_activa()  # Esto borra .active_mission

    # Opcional: Limpiar registro de archivos analizados. Por ahora, nos limitamos a lo solicitado.
    # if os.path.exists(REGISTRO_ARCHIVOS_ANALIZADOS_PATH):
    #     try:
    #         os.remove(REGISTRO_ARCHIVOS_ANALIZADOS_PATH)
    #         logging.info(f"{logPrefix} Archivo de registro de análisis '{REGISTRO_ARCHIVOS_ANALIZADOS_PATH}' eliminado.")
    #     except Exception as e:
    #         logging.error(f"{logPrefix} Error eliminando '{REGISTRO_ARCHIVOS_ANALIZADOS_PATH}': {e}")

    # Opcional: Limpiar el archivo de logging. El FileHandler actual en modo 'w' ya lo trunca/sobrescribe.
    # logging.info(f"{logPrefix} El archivo de log principal se truncará/sobrescribirá en la próxima ejecución normal debido al modo 'w' del FileHandler.")

    logging.info(
        f"{logPrefix} Reseteo del estado del agente (archivo .active_mission y rama de misión local asociada si existía) completado.")
    return True  # Indicar éxito


def _procesarMisionExistente(nombreClaveMisionActiva: str, proveedorApi: str, modoAutomatico: bool):
    logPrefix = f"_procesarMisionExistente({nombreClaveMisionActiva}):"
    logging.info(
        f"{logPrefix} Procesando misión existente '{nombreClaveMisionActiva}'.")

    # Asegurar estar en la rama de la misión activa
    if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, nombreClaveMisionActiva):
        logging.error(
            f"{logPrefix} No se pudo cambiar a la rama de misión activa '{nombreClaveMisionActiva}'. Limpiando estado.")
        limpiar_estado_mision_activa()
        # Si no se puede cambiar a la rama de la misión, se considera que se debe proceder a crear una nueva.
        # El cambio a RAMATRABAJO se gestionará en el flujo principal de ejecutarFaseDelAgente si es necesario antes de crear una nueva.
        return "PROCEDER_A_CREAR_NUEVA_MISION", True

    # Se está en la rama de la misión activa. Revisar el misionOrion.md local.
    resultadoPaso0, _, _, _ = paso0_revisar_mision_local(settings.RUTACLON)

    if resultadoPaso0 == "procesar_mision_existente":
        logging.info(
            f"{logPrefix} Misión '{nombreClaveMisionActiva}' confirmada en rama, procesando tarea.")
        resultadoPaso2, _ = paso2_ejecutar_tarea_mision(
            settings.RUTACLON, nombreClaveMisionActiva, proveedorApi, modoAutomatico)

        if resultadoPaso2 == "tarea_ejecutada_continuar_mision":
            logging.info(
                f"{logPrefix} Tarea ejecutada en '{nombreClaveMisionActiva}', quedan más tareas pendientes en la misión.")
            if modoAutomatico:
                manejadorGit.hacerPush(
                    settings.RUTACLON, nombreClaveMisionActiva)
            # La fase se considera exitosa, el script principal terminará y se reiniciará para la siguiente tarea.
            return "CONTINUAR_PROCESAMIENTO_MISION", True

        elif resultadoPaso2 == "mision_completada":
            logging.info(
                f"{logPrefix} Misión '{nombreClaveMisionActiva}' completada (todas las tareas procesadas).")
            if modoAutomatico:
                logging.info(
                    f"{logPrefix} Modo automático: Haciendo push de la rama de misión '{nombreClaveMisionActiva}' completada.")
                manejadorGit.hacerPush(
                    settings.RUTACLON, nombreClaveMisionActiva)

            limpiar_estado_mision_activa()
            logging.info(
                f"{logPrefix} Cambiando a la rama de trabajo principal '{settings.RAMATRABAJO}'.")
            if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                logging.error(
                    f"{logPrefix} CRÍTICO: No se pudo cambiar a '{settings.RAMATRABAJO}' después de completar la misión '{nombreClaveMisionActiva}'.")
                # Aunque esto es un error, la misión en sí fue procesada.
                # El script principal saldrá, y en la próxima ejecución, clonarOActualizarRepo debería intentar arreglar la rama.
                # Se retorna True para la fase porque la lógica de la misión concluyó.
            return "MISION_COMPLETADA_O_FINALIZADA", True

        elif resultadoPaso2 == "tarea_fallida":
            # Una tarea falló (ej. FALLIDA_TEMPORALMENTE y se actualizaron intentos, o error de la IA).
            # El estado de la misión se actualizó en misionOrion.md.
            logging.error(
                f"{logPrefix} Una tarea falló en la misión '{nombreClaveMisionActiva}'. El script se detendrá.")
            if modoAutomatico:
                manejadorGit.hacerPush(
                    settings.RUTACLON, nombreClaveMisionActiva)
            # La fase se considera exitosa en términos de que el agente realizó su ciclo,
            # el script principal terminará y se reiniciará. La lógica de reintentos o manejo de fallos
            # se aplicará en la siguiente ejecución al seleccionar la próxima tarea.
            return "CONTINUAR_PROCESAMIENTO_MISION", True

        else:
            # Casos como: "error_critico_actualizando_mision", "error_critico_mision_no_encontrada", "error_critico_parseo_mision"
            logging.error(
                f"{logPrefix} Error crítico durante la ejecución de la tarea (paso2) para la misión '{nombreClaveMisionActiva}': {resultadoPaso2}.")
            limpiar_estado_mision_activa()
            # Intentar volver a un estado seguro
            manejadorGit.cambiar_a_rama_existente(
                settings.RUTACLON, settings.RAMATRABAJO)
            return "ERROR_PROCESANDO_MISION", False

    elif resultadoPaso0 == "mision_existente_finalizada":
        logging.info(f"{logPrefix} Misión '{nombreClaveMisionActiva}' encontrada en la rama, pero ya estaba finalizada (sin tareas pendientes o marcada como completada). Limpiando estado.")
        limpiar_estado_mision_activa()
        manejadorGit.cambiar_a_rama_existente(
            settings.RUTACLON, settings.RAMATRABAJO)
        return "PROCEDER_A_CREAR_NUEVA_MISION", True

    else:  # Casos de paso0: "no_hay_mision_local", "ignorar_mision_actual_y_crear_nueva"
        logging.warning(f"{logPrefix} El archivo {MISION_ORION_MD} no fue encontrado o no es válido en la rama de misión activa '{nombreClaveMisionActiva}' (resultado de paso0: {resultadoPaso0}). Limpiando estado y procediendo a crear nueva misión.")
        limpiar_estado_mision_activa()
        manejadorGit.cambiar_a_rama_existente(
            settings.RUTACLON, settings.RAMATRABAJO)
        return "PROCEDER_A_CREAR_NUEVA_MISION", True


if __name__ == "__main__":
    configurarLogging()  # Configurar logging primero para todas las operaciones
    parser = argparse.ArgumentParser(
        description="Agente Adaptativo de Refactorización de Código con IA.",
        epilog="Ejecuta una fase del ciclo adaptativo (crear misión o ejecutar tarea) y luego se detiene, o resetea el estado del agente."
    )
    parser.add_argument("--modo-automatico", action="store_true",
                        help="Activa modo automatico (hace push a Git).")
    parser.add_argument("--openrouter", action="store_true",
                        help="Utilizar OpenRouter como proveedor de IA.")
    parser.add_argument("--reset", action="store_true",
                        help="Formatea el estado del agente (borra misión activa, rama de misión local asociada, etc.) y sale.")

    args = parser.parse_args()

    if args.reset:
        logging.info(
            "Opción --reset detectada. Iniciando reseteo del agente...")
        # La función realizarReseteoAgente ya está definida en este archivo (principal.py)
        # y utiliza cargar_estado_mision_activa, limpiar_estado_mision_activa de este mismo archivo.
        # También utiliza manejadorGit y settings.
        reset_exitoso = realizarReseteoAgente()
        if reset_exitoso:
            logging.info("Reseteo del agente completado con éxito.")
            sys.exit(0)
        else:
            logging.error("Reseteo del agente falló. Revise los logs.")
            sys.exit(1)
    else:
        # Proceder con la orquestación normal si no es --reset
        codigo_salida = orchestrarEjecucionScript(args)
        logging.info(
            f"Script principal (adaptativo) finalizado con código: {codigo_salida}")
        # Proceder con la orquestación normal si no es --reset
        sys.exit(codigo_salida)
        codigo_salida = orchestrarEjecucionScript(args)
        logging.info(
            f"Script principal (adaptativo) finalizado con código: {codigo_salida}")
        sys.exit(codigo_salida)
