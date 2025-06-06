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
    settings.RUTACLON, ".orion_meta", "registro_archivos_analizados.json")
TOKEN_LIMIT_PER_MINUTE = getattr(
    settings, 'TOKEN_LIMIT_PER_MINUTE', 250000)
token_usage_window = []

# --- Archivo para persistir el estado de la misión activa ---
ACTIVE_MISSION_STATE_FILE = os.path.join(
    settings.RUTACLON, ".orion_meta", ".active_mission")

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
        # Asegura que el directorio .orion_meta exista ANTES de intentar abrir el archivo.
        # REGISTRO_ARCHIVOS_ANALIZADOS_PATH se asume que ya apunta a la nueva ubicación
        # (settings.RUTACLON/.orion_meta/registro_archivos_analizados.json).
        os.makedirs(os.path.dirname(
            REGISTRO_ARCHIVOS_ANALIZADOS_PATH), exist_ok=True)
        with open(REGISTRO_ARCHIVOS_ANALIZADOS_PATH, 'w', encoding='utf-8') as f:
            json.dump(registro, f, indent=4)
    except Exception as e:
        # El mensaje de error utilizará el valor actualizado de REGISTRO_ARCHIVOS_ANALIZADOS_PATH
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
        # Tarea: Mover el log principal (`historial_refactor_adaptativo.log`)
        # al directorio del repositorio clonado (settings.RUTACLON),
        # dentro de una subcarpeta dedicada (ej. .orion_meta/).
        rutaLogArchivo = os.path.join(
            # MODIFICADO para nueva ruta y nombre según tarea
            settings.RUTACLON, ".orion_meta", "historial_refactor_adaptativo.log")
        # Crea .orion_meta/ si no existe
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

def paso0_revisar_mision_local(ruta_repo: str, nombre_clave_mision_activa: str):
    """
    Paso 0: Revisa si existe un archivo de misión específico (ej. <nombre_clave_mision_activa>.md) EN LA RAMA ACTUAL.
    Se espera que esta función sea llamada cuando el agente ya está en una rama de misión
    potencial, o en la rama de trabajo principal si no hay misión activa.
    El nombre_clave_mision_activa se usa para determinar el nombre del archivo a buscar.
    """
    logPrefix = "paso0_revisar_mision_local:"

    if not nombre_clave_mision_activa:  # Validación de seguridad
        logging.error(
            f"{logPrefix} Se requiere nombre_clave_mision_activa. No se puede buscar archivo de misión.")
        return "ignorar_mision_actual_y_crear_nueva", None, None, None

    nombre_archivo_mision = f"{nombre_clave_mision_activa}.md"

    rama_actual = manejadorGit.obtener_rama_actual(ruta_repo)
    logging.info(
        f"{logPrefix} Revisando archivo de misión '{nombre_archivo_mision}' en rama actual: '{rama_actual}'")

    ruta_mision_especifica = os.path.join(ruta_repo, nombre_archivo_mision)

    if os.path.exists(ruta_mision_especifica):
        logging.info(
            f"{logPrefix} Se encontró archivo de misión '{nombre_archivo_mision}' en '{rama_actual}'.")
        try:
            with open(ruta_mision_especifica, 'r', encoding='utf-8') as f:
                contenido_mision = f.read()

            metadatos, lista_tareas, hay_tareas_pendientes = manejadorMision.parsear_mision_orion(
                contenido_mision)

            if not metadatos or not metadatos.get("nombre_clave"):
                logging.warning(
                    f"{logPrefix} Archivo '{nombre_archivo_mision}' existe pero no se pudo extraer metadatos/nombre clave. Se tratará como para crear nueva misión.")
                return "ignorar_mision_actual_y_crear_nueva", None, None, None

            nombre_clave_parseado_del_contenido = metadatos["nombre_clave"]

            if nombre_clave_parseado_del_contenido != nombre_clave_mision_activa:
                logging.warning(
                    f"{logPrefix} ¡INCONSISTENCIA! El nombre clave en el contenido de '{nombre_archivo_mision}' ('{nombre_clave_parseado_del_contenido}') "
                    f"no coincide con el nombre clave esperado del archivo ('{nombre_clave_mision_activa}'). "
                    f"Se procederá con el nombre clave del contenido, pero esto podría indicar un problema."
                )

            estado_general_mision = metadatos.get(
                "estado_general", "PENDIENTE")

            if hay_tareas_pendientes and estado_general_mision not in ["COMPLETADA", "FALLIDA"]:
                logging.info(
                    f"{logPrefix} Misión '{nombre_clave_parseado_del_contenido}' (del archivo '{nombre_archivo_mision}') con tareas pendientes y estado '{estado_general_mision}'. Lista para procesar.")
                return "procesar_mision_existente", metadatos, lista_tareas, nombre_clave_parseado_del_contenido
            else:
                logging.info(
                    f"{logPrefix} Misión '{nombre_clave_parseado_del_contenido}' (del archivo '{nombre_archivo_mision}') sin tareas pendientes o en estado '{estado_general_mision}'. Se considera completada o fallida.")
                return "mision_existente_finalizada", metadatos, lista_tareas, nombre_clave_parseado_del_contenido
        except Exception as e:
            logging.error(
                f"{logPrefix} Error leyendo o parseando '{nombre_archivo_mision}': {e}. Se intentará crear una nueva.", exc_info=True)
            return "ignorar_mision_actual_y_crear_nueva", None, None, None
    else:
        logging.info(
            f"{logPrefix} No se encontró archivo de misión '{nombre_archivo_mision}' en rama '{rama_actual}'.")
        return "no_hay_mision_local", None, None, None


def paso1_1_seleccion_y_decision_inicial(ruta_repo, api_provider, registro_archivos):
    logPrefix = "paso1_1_seleccion_y_decision_inicial:"
    archivo_seleccionado_rel = seleccionar_archivo_mas_antiguo(
        ruta_repo, registro_archivos)
    # No es estrictamente necesario guardar aquí, ya que se guarda al final del script,
    # pero no causa daño. Lo mantenemos por ahora.
    guardar_registro_archivos(registro_archivos)

    if not archivo_seleccionado_rel:
        logging.warning(f"{logPrefix} No se pudo seleccionar ningún archivo.")
        return "ciclo_terminado_sin_accion", None, None, None

    ruta_archivo_seleccionado_abs = os.path.join(
        ruta_repo, archivo_seleccionado_rel)
    if not os.path.exists(ruta_archivo_seleccionado_abs):
        logging.error(
            f"{logPrefix} Archivo seleccionado '{archivo_seleccionado_rel}' no existe. Reintentando.")
        # Marcar en el registro para evitar reintentos infinitos si el archivo fue eliminado
        registro_archivos[archivo_seleccionado_rel] = datetime.now(
        ).isoformat() + "_NOT_FOUND"
        guardar_registro_archivos(registro_archivos)
        return "reintentar_seleccion", None, None, None

    estructura_proyecto = analizadorCodigo.generarEstructuraDirectorio(
        ruta_repo, directorios_ignorados=settings.DIRECTORIOS_IGNORADOS, max_depth=5, incluir_archivos=True)

    resultado_lectura = analizadorCodigo.leerArchivos(
        [ruta_archivo_seleccionado_abs], ruta_repo, api_provider=api_provider)
    contenido_archivo = resultado_lectura['contenido']

    # --- MEJORA INTEGRADA: Chequeo de archivo vacío ---
    if not contenido_archivo.strip():
        logging.info(
            f"{logPrefix} El archivo '{archivo_seleccionado_rel}' está vacío o no se pudo leer. Se saltará y reintentará en la próxima ejecución.")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO1.1_NO_REFACTOR_VACIO:{archivo_seleccionado_rel}", decision={"necesita_refactor": False, "razonamiento": "Archivo vacío o no legible."})
        ])
        # Se devuelve 'reintentar' para que el registro (actualizado al seleccionar) persista y no se elija de nuevo inmediatamente.
        return "reintentar_seleccion", None, None, None
    # --- FIN MEJORA ---

    tokens_contenido = resultado_lectura['tokens']
    tokens_estructura = analizadorCodigo.contarTokensTexto(
        estructura_proyecto or "", api_provider)
    tokens_estimados = 500 + tokens_contenido + \
        tokens_estructura

    gestionar_limite_tokens(tokens_estimados, api_provider)

    decision_IA_paso1_1 = analizadorCodigo.solicitar_evaluacion_archivo(
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

    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(
            outcome=f"PASO1.1_REFACTOR_APROBADO:{archivo_seleccionado_rel}", decision=decision_IA_paso1_1)
    ])

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
    nombre_archivo_mision = f"{nombre_clave_mision}.md"

    rama_base = manejadorGit.obtener_rama_actual(
        ruta_repo) or settings.RAMATRABAJO
    if not manejadorGit.crear_y_cambiar_a_rama(ruta_repo, nombre_clave_mision, rama_base):
        logging.error(
            f"{logPrefix} No se pudo crear o cambiar a rama '{nombre_clave_mision}' desde '{rama_base}'.")
        return "error_generando_mision", None, None
    logging.info(
        f"{logPrefix} En rama de misión: '{nombre_clave_mision}' (desde '{rama_base}')")

    try:
        with open(os.path.join(ruta_repo, nombre_archivo_mision), 'w', encoding='utf-8') as f:
            f.write(contenido_markdown_mision)
        logging.info(
            f"{logPrefix} Archivo de misión '{nombre_archivo_mision}' guardado en rama '{nombre_clave_mision}'")
    except Exception as e:
        logging.error(
            f"{logPrefix} Error guardando '{nombre_archivo_mision}': {e}", exc_info=True)
        manejadorGit.cambiar_a_rama_existente(ruta_repo, rama_base)
        manejadorGit.eliminarRama(ruta_repo, nombre_clave_mision, local=True)
        return "error_generando_mision", None, None

    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Crear misión: {nombre_clave_mision}", [nombre_archivo_mision]):
        logging.error(
            f"{logPrefix} No se pudo hacer commit de '{nombre_archivo_mision}' en '{nombre_clave_mision}'.")
        # No eliminar la rama si el commit falló pero el archivo se creó, podría ser útil para debug manual
        # manejadorGit.cambiar_a_rama_existente(ruta_repo, rama_base); manejadorGit.eliminarRama(ruta_repo, nombre_clave_mision, local=True)
        return "error_generando_mision", None, None  # Error si el commit del MD falla

    logging.info(
        f"{logPrefix} Misión '{nombre_clave_mision}' generada y commiteada (archivo: {nombre_archivo_mision}).")
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(
            outcome=f"PASO1.2_MISION_GENERADA:{nombre_clave_mision}", result_details=f"Archivo: {nombre_archivo_mision}")
    ])
    return "mision_generada_ok", contenido_markdown_mision, nombre_clave_mision

def paso2_ejecutar_tarea_mision(ruta_repo, nombre_rama_mision, api_provider, modo_automatico):
    # Esta función ahora es llamada cuando ya se está en la rama de la misión.
    # El contenido de la misión (metadatos, lista_tareas) se carga desde el archivo en la rama.
    logPrefix = f"paso2_ejecutar_tarea_mision (Rama: {nombre_rama_mision}):"
    logging.info(f"{logPrefix} Iniciando ejecución de tarea.")

    # Nombre del archivo de misión dinámico
    nombre_archivo_mision = f"{nombre_rama_mision}.md"

    # Asegurar estar en la rama correcta (doble check)
    if manejadorGit.obtener_rama_actual(ruta_repo) != nombre_rama_mision:
        logging.warning(
            f"{logPrefix} No se estaba en la rama '{nombre_rama_mision}'. Intentando cambiar...")
        if not manejadorGit.cambiar_a_rama_existente(ruta_repo, nombre_rama_mision):
            logging.error(
                f"{logPrefix} No se pudo cambiar a rama '{nombre_rama_mision}'. Abortando tarea.")
            return "error_critico_git", None

    ruta_mision_actual_md = os.path.join(ruta_repo, nombre_archivo_mision)
    contenido_mision_actual_md = ""
    if os.path.exists(ruta_mision_actual_md):
        with open(ruta_mision_actual_md, 'r', encoding='utf-8') as f:
            contenido_mision_actual_md = f.read()
    else:
        logging.error(
            f"{logPrefix} Archivo de misión '{nombre_archivo_mision}' no encontrado en la rama '{nombre_rama_mision}'. Abortando tarea.")
        return "error_critico_mision_no_encontrada", None

    metadatos_mision, lista_tareas_mision, _ = manejadorMision.parsear_mision_orion(
        contenido_mision_actual_md)
    if not metadatos_mision:
        logging.error(
            f"{logPrefix} Fallo al re-parsear '{nombre_archivo_mision}' desde la rama. Abortando tarea.")
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
            ruta_procesada = ruta_cruda.strip().replace('[', '').replace(']', '')
            if ruta_procesada.startswith('/') or ruta_procesada.startswith('\\'):
                ruta_procesada = ruta_procesada[1:]
            ruta_procesada = ruta_procesada.strip()

            if ruta_procesada and ruta_procesada.lower() not in ["ninguno", "ninguno."]:
                ruta_abs_candidata = os.path.join(ruta_repo, ruta_procesada)
                if os.path.exists(ruta_abs_candidata) and os.path.isfile(ruta_abs_candidata):
                    rutas_limpias_final.append(ruta_procesada)
                else:
                    logging.warning(
                        f"{logPrefix} Ruta '{ruta_procesada}' (original: '{ruta_cruda}') de {origen_rutas_log} no existe o no es un archivo. Se ignora.")
            elif ruta_procesada: # Loguear si se descarta algo que no era "ninguno"
                 logging.debug(f"{logPrefix} Ruta '{ruta_cruda}' de {origen_rutas_log} descartada (vacía o 'ninguno').")
        return rutas_limpias_final

    archivos_ctx_ejecucion_mision_crudos = metadatos_mision.get("archivos_contexto_ejecucion", [])
    archivos_especificos_tarea_crudos = tarea_actual_info.get("archivos_implicados_especificos", [])
    archivo_principal_mision_crudo = metadatos_mision.get("archivo_principal")

    archivos_ctx_ejecucion_limpios = limpiar_lista_rutas(archivos_ctx_ejecucion_mision_crudos, "metadatos[archivos_contexto_ejecucion]")
    archivos_especificos_tarea_limpios = limpiar_lista_rutas(archivos_especificos_tarea_crudos, f"tarea ID '{tarea_id}'[archivos_implicados_especificos]")
    archivos_principal_limpios = []
    if archivo_principal_mision_crudo:
        archivos_principal_limpios = limpiar_lista_rutas([archivo_principal_mision_crudo], "metadatos[archivo_principal]")
    
    # --- Preparación de contexto para la IA ---
    bloques_codigo_objetivo_tarea = tarea_actual_info.get("bloques_codigo_objetivo", [])
    bloques_codigo_input_para_ia = []
    rutas_archivos_para_leer_bloques = set() 

    if bloques_codigo_objetivo_tarea:
        logging.info(f"{logPrefix} La tarea tiene {len(bloques_codigo_objetivo_tarea)} bloque(s) de código objetivo definidos.")
        for bloque_info_md in bloques_codigo_objetivo_tarea:
            ruta_archivo_bloque_rel = bloque_info_md.get("archivo")
            nombre_bloque_md = bloque_info_md.get("nombre_bloque")
            linea_inicio_md = bloque_info_md.get("linea_inicio")
            linea_fin_md = bloque_info_md.get("linea_fin")

            if not all([ruta_archivo_bloque_rel, nombre_bloque_md, isinstance(linea_inicio_md, int), isinstance(linea_fin_md, int)]):
                logging.warning(f"{logPrefix} Bloque de código objetivo en MD para tarea '{tarea_id}' mal formado o incompleto: {bloque_info_md}. Se omite este bloque.")
                continue
            
            ruta_archivo_bloque_abs_validada = analizadorCodigo._validar_y_normalizar_ruta(ruta_archivo_bloque_rel, ruta_repo, asegurar_existencia=False) # No asegurar existencia aquí, se hará al leer
            if not ruta_archivo_bloque_abs_validada:
                logging.warning(f"{logPrefix} Ruta de archivo para bloque '{nombre_bloque_md}' ('{ruta_archivo_bloque_rel}') inválida. Se omite este bloque.")
                continue
            
            rutas_archivos_para_leer_bloques.add(ruta_archivo_bloque_abs_validada)

    contenido_archivos_bloques_leidos = {} 
    if rutas_archivos_para_leer_bloques:
        for ruta_abs_leer_bloque in rutas_archivos_para_leer_bloques:
            if not os.path.exists(ruta_abs_leer_bloque): # Chequeo de existencia antes de leer
                # Si el archivo no existe, es posible que sea para creación.
                # Se pasa un contenido vacío (o lista de líneas vacía).
                logging.info(f"{logPrefix} Archivo '{ruta_abs_leer_bloque}' para bloque no existe. Se asume creación o se pasará vacío.")
                contenido_archivos_bloques_leidos[ruta_abs_leer_bloque] = [] # Lista de líneas vacía
                continue
            try:
                with open(ruta_abs_leer_bloque, 'r', encoding='utf-8') as f_bloque:
                    contenido_crudo = f_bloque.read()
                contenido_archivos_bloques_leidos[ruta_abs_leer_bloque] = contenido_crudo.splitlines(keepends=True) 
            except Exception as e_leer_b:
                logging.error(f"{logPrefix} Error leyendo archivo '{ruta_abs_leer_bloque}' para extraer bloques: {e_leer_b}")
                contenido_archivos_bloques_leidos[ruta_abs_leer_bloque] = None # Marcar como no leído

    if bloques_codigo_objetivo_tarea: # No necesita 'and contenido_archivos_bloques_leidos' porque puede ser creación
        for bloque_info_md in bloques_codigo_objetivo_tarea:
            ruta_rel = bloque_info_md.get("archivo")
            nombre_b = bloque_info_md.get("nombre_bloque")
            l_ini = bloque_info_md.get("linea_inicio")
            l_fin = bloque_info_md.get("linea_fin")
            
            ruta_abs_correspondiente = os.path.normpath(os.path.join(ruta_repo, ruta_rel))

            if ruta_abs_correspondiente not in contenido_archivos_bloques_leidos:
                # Esto puede pasar si _validar_y_normalizar_ruta falló antes para esta ruta_rel.
                # O si la lectura del archivo falló (contenido_archivos_bloques_leidos[ruta_abs_correspondiente] es None).
                if ruta_abs_correspondiente in contenido_archivos_bloques_leidos and contenido_archivos_bloques_leidos[ruta_abs_correspondiente] is None:
                    error_msg_contenido = f"// ERROR: No se pudo leer el archivo '{ruta_rel}' para extraer este bloque."
                else: # El archivo no estaba en el set para leer o falló validación inicial.
                    error_msg_contenido = f"// ERROR: Ruta de archivo '{ruta_rel}' no válida o no se pudo acceder para este bloque."
                
                bloques_codigo_input_para_ia.append({
                    "ruta_archivo": ruta_rel, "nombre_bloque": nombre_b,
                    "linea_inicio_original": l_ini, "linea_fin_original": l_fin,
                    "contenido_actual_bloque": error_msg_contenido
                })
                logging.warning(f"{logPrefix} Archivo '{ruta_rel}' para bloque '{nombre_b}' no se pudo leer o no fue validado. Se envía con error a IA.")
                continue

            lineas_del_archivo = contenido_archivos_bloques_leidos[ruta_abs_correspondiente] # Puede ser [] si el archivo no existía
            
            if not (1 <= l_ini <= l_fin <= len(lineas_del_archivo) or (l_ini == 1 and l_fin == 1 and not lineas_del_archivo)): # Última condición para creación
                if l_ini == 1 and (l_fin == 1 or l_fin == 0) and not os.path.exists(ruta_abs_correspondiente): # l_fin 0 también es válido para IA en creación
                     bloques_codigo_input_para_ia.append({
                        "ruta_archivo": ruta_rel,
                        "nombre_bloque": nombre_b,
                        "linea_inicio_original": l_ini,
                        "linea_fin_original": l_fin,
                        "contenido_actual_bloque": "" 
                    })
                     logging.info(f"{logPrefix} Preparado bloque para CREACIÓN: Archivo '{ruta_rel}', Bloque '{nombre_b}' (L{l_ini}-{l_fin}).")
                else:
                    logging.warning(f"{logPrefix} Rango de líneas [{l_ini}-{l_fin}] para bloque '{nombre_b}' en '{ruta_rel}' "
                                    f"inválido o fuera de los límites (total líneas: {len(lineas_del_archivo)}). Se envía con error a IA.")
                    bloques_codigo_input_para_ia.append({
                        "ruta_archivo": ruta_rel, "nombre_bloque": nombre_b,
                        "linea_inicio_original": l_ini, "linea_fin_original": l_fin,
                        "contenido_actual_bloque": f"// ERROR: Rango de líneas [{l_ini}-{l_fin}] inválido para archivo con {len(lineas_del_archivo)} líneas."
                    })
                continue
            
            contenido_bloque_extraido = "".join(lineas_del_archivo[l_ini-1:l_fin])
            bloques_codigo_input_para_ia.append({
                "ruta_archivo": ruta_rel,
                "nombre_bloque": nombre_b,
                "linea_inicio_original": l_ini, 
                "linea_fin_original": l_fin,
                "contenido_actual_bloque": contenido_bloque_extraido
            })
            logging.debug(f"{logPrefix} Preparado bloque: Archivo '{ruta_rel}', Bloque '{nombre_b}' (L{l_ini}-{l_fin}).")
    
    archivos_para_leer_contexto_general_rel = []
    if archivos_principal_limpios: archivos_para_leer_contexto_general_rel.extend(archivos_principal_limpios)
    archivos_para_leer_contexto_general_rel.extend(archivos_ctx_ejecucion_limpios)
    archivos_para_leer_contexto_general_rel.extend(archivos_especificos_tarea_limpios)
    archivos_para_leer_contexto_general_rel = sorted(list(set(archivos_para_leer_contexto_general_rel)))
    
    contexto_general_archivos_str = ""
    tokens_contexto_general = 0
    if archivos_para_leer_contexto_general_rel:
        archivos_abs_ctx_general = [os.path.join(ruta_repo, f_rel) for f_rel in archivos_para_leer_contexto_general_rel]
        resultado_lectura_ctx_general = analizadorCodigo.leerArchivos(archivos_abs_ctx_general, ruta_repo, api_provider=api_provider)
        contexto_general_archivos_str = resultado_lectura_ctx_general['contenido'] # No se usa en el prompt granular, pero sí para tokens
        tokens_contexto_general = resultado_lectura_ctx_general['tokens']
        logging.info(f"{logPrefix} Contexto general leído de {len(archivos_para_leer_contexto_general_rel)} archivo(s) para cálculo de tokens.")
    else:
        logging.info(f"{logPrefix} No se definieron archivos para contexto general.")

    tokens_mision_y_tarea_desc = analizadorCodigo.contarTokensTexto(contenido_mision_actual_md + tarea_actual_info.get('descripcion', ''), api_provider)
    tokens_bloques_objetivo = analizadorCodigo.contarTokensTexto(json.dumps(bloques_codigo_input_para_ia), api_provider)
    tokens_estimados = 800 + tokens_contexto_general + tokens_mision_y_tarea_desc + tokens_bloques_objetivo

    gestionar_limite_tokens(tokens_estimados, api_provider)

    resultado_ejecucion_tarea = analizadorCodigo.ejecutar_tarea_especifica_mision(
        tarea_actual_info, 
        contenido_mision_actual_md, 
        bloques_codigo_input_para_ia, 
        api_provider
    )
    registrar_tokens_usados(resultado_ejecucion_tarea.get("tokens_consumidos_api", tokens_estimados) if resultado_ejecucion_tarea else tokens_estimados)

    contenido_mision_post_tarea = contenido_mision_actual_md  

    # --- INICIO NUEVA LÓGICA DE ENRUTAMIENTO Y APLICACIÓN ---
    exito_aplicar = False # Solo relevante para el aplicador granular
    msg_err_aplicar = None # Solo relevante para el aplicador granular
    aplicador_usado = None 

    if not resultado_ejecucion_tarea or not isinstance(resultado_ejecucion_tarea, dict):
        logging.error(f"{logPrefix} IA no generó una respuesta de cambios válida (nula o no es dict). Respuesta: {resultado_ejecucion_tarea}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO2_ERROR_TAREA_IA_FORMATO:{nombre_rama_mision}", decision=tarea_actual_info, 
                error_message="IA no generó respuesta válida (nula o no dict)",
                result_details={"respuesta_ia_raw": resultado_ejecucion_tarea, "aplicador_usado": aplicador_usado})
        ])
        contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
            contenido_mision_actual_md, tarea_id, "FALLIDA_TEMPORALMENTE", incrementar_intentos_si_fallida_temp=True
        )
        try:
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' FALLIDA_TEMPORALMENTE (IA_FORMATO)", [nombre_archivo_mision]):
                logging.error(f"{logPrefix} No se pudo commitear {nombre_archivo_mision} (tarea fallida IA_FORMATO).")
        except Exception as e:
            logging.error(f"{logPrefix} Error guardando/commiteando {nombre_archivo_mision} (tarea fallida IA_FORMATO): {e}")
            return "error_critico_actualizando_mision", contenido_mision_actual_md 
        return "tarea_fallida", contenido_mision_post_tarea

    adv = resultado_ejecucion_tarea.get("advertencia_ejecucion")
    tiene_modificaciones_granulares = "modificaciones" in resultado_ejecucion_tarea and \
                                      isinstance(resultado_ejecucion_tarea["modificaciones"], list) and \
                                      len(resultado_ejecucion_tarea["modificaciones"]) > 0
    
    # Chequeo si 'archivos_modificados' existe y es un dict no vacío
    archivos_modificados_dict = resultado_ejecucion_tarea.get("archivos_modificados")
    tiene_archivos_sobrescribir = isinstance(archivos_modificados_dict, dict) and bool(archivos_modificados_dict)


    if adv and not tiene_modificaciones_granulares and not tiene_archivos_sobrescribir:
        logging.warning(f"{logPrefix} IA advirtió: {adv}. Tarea no resultó en cambios propuestos. Marcando como SALTADA.")
        contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
            contenido_mision_actual_md, tarea_id, "SALTADA")
        if not contenido_mision_post_tarea: return "error_critico_actualizando_mision", contenido_mision_actual_md
        try:
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' SALTADA (IA advirtió sin cambios)", [nombre_archivo_mision]):
                logging.error(f"{logPrefix} No se pudo commitear {nombre_archivo_mision} (tarea saltada).")
        except Exception as e:
            logging.error(f"{logPrefix} Error guardando {nombre_archivo_mision} (tarea saltada): {e}")
        
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO2_TAREA_SALTADA_IA_ADV:{nombre_rama_mision}", decision=tarea_actual_info, 
                result_details={"advertencia": adv, "aplicador_usado": aplicador_usado})
        ])
        _, _, hay_pendientes_despues_salto = manejadorMision.parsear_mision_orion(contenido_mision_post_tarea)
        return "mision_completada" if not hay_pendientes_despues_salto else "tarea_ejecutada_continuar_mision", contenido_mision_post_tarea
    
    if tiene_modificaciones_granulares:
        aplicador_usado = "granular"
        logging.info(f"{logPrefix} Respuesta de IA contiene 'modificaciones' ({len(resultado_ejecucion_tarea['modificaciones'])} ops). Usando aplicador granular.")
        exito_aplicar, msg_err_aplicar = aplicadorCambios.aplicarCambiosGranulares(
            resultado_ejecucion_tarea, ruta_repo
        )
    elif tiene_archivos_sobrescribir:
        # --- INICIO MODIFICACIÓN C.3 ---
        aplicador_usado = "ninguno_protocolo_violado" 
        logging.critical(f"{logPrefix} ADVERTENCIA SEVERA: IA violó protocolo granular. Devolvió 'archivos_modificados' en lugar de 'modificaciones'. Tarea ID: {tarea_id}. Contenido de 'archivos_modificados': {str(archivos_modificados_dict)[:200]}...")
        
        contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
            contenido_mision_actual_md, tarea_id, "FALLIDA_TEMPORALMENTE", incrementar_intentos_si_fallida_temp=True
        )
        if not contenido_mision_post_tarea:
            logging.error(f"{logPrefix} Error crítico actualizando misión MD tras violación de protocolo IA.")
            return "error_critico_actualizando_mision", contenido_mision_actual_md

        try:
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f:
                f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(
                ruta_repo, 
                f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' FALLIDA_TEMPORALMENTE (IA_PROTOCOLO_SOBRESCRITURA_NO_PERMITIDO)", 
                [nombre_archivo_mision] 
            ):
                logging.error(f"{logPrefix} No se pudo commitear {nombre_archivo_mision} (tarea fallida IA_PROTOCOLO_SOBRESCRITURA).")
        except Exception as e:
            logging.error(f"{logPrefix} Error guardando/commiteando {nombre_archivo_mision} (tarea fallida IA_PROTOCOLO_SOBRESCRITURA): {e}")
            return "error_critico_actualizando_mision", contenido_mision_actual_md
        
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO2_TAREA_FALLIDA_IA_PROTOCOLO_SOBRESCRITURA:{nombre_rama_mision}", 
                decision=tarea_actual_info, 
                error_message="IA devolvió 'archivos_modificados' en lugar de 'modificaciones'. No se aplicaron cambios.",
                result_details={"respuesta_ia_raw": resultado_ejecucion_tarea, "aplicador_usado": aplicador_usado}
            )
        ])
        return "tarea_fallida", contenido_mision_post_tarea
        # --- FIN MODIFICACIÓN C.3 ---
    else:
        logging.error(f"{logPrefix} IA devolvió un diccionario pero sin 'modificaciones' (lista no vacía) ni 'archivos_modificados' (dict no vacío). Respuesta: {resultado_ejecucion_tarea}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO2_ERROR_TAREA_IA_NO_CAMBIOS_RECONOCIDOS:{nombre_rama_mision}", decision=tarea_actual_info,
                error_message="IA devolvió dict pero sin formato de cambios reconocido.",
                result_details={"respuesta_ia_raw": resultado_ejecucion_tarea, "aplicador_usado": aplicador_usado})
        ])
        contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
            contenido_mision_actual_md, tarea_id, "FALLIDA_TEMPORALMENTE", incrementar_intentos_si_fallida_temp=True
        )
        try:
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' FALLIDA_TEMPORALMENTE (IA_NO_CAMBIOS)", [nombre_archivo_mision]):
                logging.error(f"{logPrefix} No se pudo commitear {nombre_archivo_mision} (tarea fallida IA_NO_CAMBIOS).")
        except Exception as e:
            logging.error(f"{logPrefix} Error guardando/commiteando {nombre_archivo_mision} (tarea fallida IA_NO_CAMBIOS): {e}")
            return "error_critico_actualizando_mision", contenido_mision_actual_md
        return "tarea_fallida", contenido_mision_post_tarea

    # Esta sección solo se alcanza si aplicador_usado == "granular"
    if not exito_aplicar:
        logging.error(f"{logPrefix} Falló aplicación de cambios ({aplicador_usado}): {msg_err_aplicar}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO2_APPLY_FAIL:{nombre_rama_mision}", decision=tarea_actual_info, 
                result_details={"aplicador_usado": aplicador_usado, "respuesta_ia_raw": resultado_ejecucion_tarea}, 
                error_message=msg_err_aplicar)
        ])
        manejadorGit.descartarCambiosLocales(ruta_repo)
        contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
            contenido_mision_actual_md, tarea_id, "FALLIDA_TEMPORALMENTE", incrementar_intentos_si_fallida_temp=True
        )
        try:
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' FALLIDA_TEMPORALMENTE (apply_{aplicador_usado})", [nombre_archivo_mision]):
                logging.error(f"{logPrefix} No se pudo commitear {nombre_archivo_mision} (tarea fallida apply).")
        except Exception as e:
            logging.error(f"{logPrefix} Error guardando/commiteando {nombre_archivo_mision} (tarea fallida apply): {e}")
            return "error_critico_actualizando_mision", contenido_mision_actual_md
        return "tarea_fallida", contenido_mision_post_tarea

    # Éxito en la aplicación (solo si aplicador_usado == "granular")
    logging.info(f"{logPrefix} Cambios de IA aplicados exitosamente usando aplicador '{aplicador_usado}'.")
    if adv: 
        logging.warning(f"{logPrefix} Advertencia de IA (aunque los cambios se aplicaron): {adv}")

    commit_msg = f"Tarea ID {tarea_id} ({tarea_titulo[:50]}) completada (Misión {nombre_rama_mision})"
    if not manejadorGit.hacerCommit(ruta_repo, commit_msg):
        logging.warning(f"{logPrefix} No se realizó commit de los cambios de código para la tarea (quizás sin cambios efectivos después de aplicar, o fallo en git add/commit).")
    
    contenido_mision_post_tarea = manejadorMision.marcar_tarea_como_completada(
        contenido_mision_actual_md, tarea_id, "COMPLETADA")
    if not contenido_mision_post_tarea: return "error_critico_actualizando_mision", contenido_mision_actual_md

    try:
        with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
    except Exception as e:
        logging.error(f"{logPrefix} Error guardando {nombre_archivo_mision} (estado completado): {e}")
        return "error_critico_actualizando_mision", contenido_mision_actual_md

    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Actualizar Misión '{nombre_rama_mision}', Tarea '{tarea_id}' a COMPLETADA", [nombre_archivo_mision]):
        logging.error(f"{logPrefix} No se pudo commitear actualización de {nombre_archivo_mision} (estado completado).")

    detalles_resultado_historial = {"aplicador_usado": aplicador_usado, "advertencia_ia": adv if adv else "Ninguna"}
    if aplicador_usado == "granular": # Única opción que llega aquí con éxito
        detalles_resultado_historial["operaciones_solicitadas"] = len(resultado_ejecucion_tarea.get("modificaciones", []))
    
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(
            outcome=f"PASO2_TAREA_OK:{nombre_rama_mision}", decision=tarea_actual_info, 
            result_details=detalles_resultado_historial)
    ])

    _, _, hay_pendientes_actualizada = manejadorMision.parsear_mision_orion(contenido_mision_post_tarea)
    return "mision_completada" if not hay_pendientes_actualizada else "tarea_ejecutada_continuar_mision", contenido_mision_post_tarea
# --- Función Principal de Fase del Agente (MODIFICADO) ---
def _intentarCrearMisionDesdeTodoMD(api_provider: str, modo_automatico: bool):
    logPrefix = "_intentarCrearMisionDesdeTodoMD:"
    if not modo_automatico:
        logging.info(f"{logPrefix} Modo no automático, se omite la revisión de TODO.md.")
        return False

    logging.info(f"{logPrefix} Modo automático activo. Verificando TODO.md para nueva misión.")
    ruta_todo_md = os.path.join(settings.RUTACLON, "TODO.md")
    
    if not os.path.exists(ruta_todo_md) or not os.path.isfile(ruta_todo_md) or os.path.getsize(ruta_todo_md) == 0:
        logging.info(f"{logPrefix} Archivo TODO.md no encontrado, no es un archivo o está vacío. Se omite.")
        return False

    try:
        with open(ruta_todo_md, 'r', encoding='utf-8') as f_todo:
            contenido_todo_md = f_todo.read().strip()
        if not contenido_todo_md:
            logging.info(f"{logPrefix} TODO.md está vacío. Se omite.")
            return False
        
        logging.info(f"{logPrefix} TODO.md con contenido. Intentando generar misión.")
        tokens_estimados = 700 + analizadorCodigo.contarTokensTexto(contenido_todo_md, api_provider)
        gestionar_limite_tokens(tokens_estimados, api_provider)

        mision_dict = analizadorCodigo.generar_contenido_mision_desde_texto_guia(
            settings.RUTACLON, contenido_todo_md, "TODO.md", api_provider
        )
        registrar_tokens_usados(mision_dict.get("tokens_consumidos_api", tokens_estimados) if mision_dict else tokens_estimados)

        if not mision_dict or not mision_dict.get("nombre_clave_mision") or not mision_dict.get("contenido_markdown_mision"):
            logging.warning(f"{logPrefix} IA no generó misión válida desde TODO.md. Respuesta: {mision_dict}")
            manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO_TODO_ERROR_GENERACION_IA", error_message="IA no generó misión válida desde TODO.md")])
            return False

        nombre_clave = mision_dict["nombre_clave_mision"]
        contenido_md = mision_dict["contenido_markdown_mision"]
        
        # --- INICIO VALIDACIÓN GRANULAR (A.4.2) ---
        logging.info(f"{logPrefix} Validando estructura granular de la misión '{nombre_clave}' generada desde TODO.md.")
        _, lista_tareas_val, _ = manejadorMision.parsear_mision_orion(contenido_md)
        
        validacion_granular_exitosa = True
        detalle_error_validacion = "Error desconocido durante validación granular."
        tarea_fallida_id_val = None
        bloque_fallido_nombre_val = None

        if not lista_tareas_val:
            if "### Tarea" in contenido_md:
                validacion_granular_exitosa = False
                detalle_error_validacion = "El parser de misiones no pudo extraer tareas, aunque el MD parece contenerlas."
                logging.error(f"{logPrefix} {detalle_error_validacion} Misión: {nombre_clave}")
            # Si no hay '### Tarea' y lista_tareas_val es vacía, es un fallo para misión desde TODO.md que siempre debe tener tareas.
            else:
                validacion_granular_exitosa = False
                detalle_error_validacion = "Misión generada desde TODO.md no contiene ninguna sección '### Tarea'."
                logging.error(f"{logPrefix} {detalle_error_validacion} Misión: {nombre_clave}")
                
        for tarea_info in lista_tareas_val if lista_tareas_val else []: # Bucle solo si lista_tareas_val no es None/vacío
            if not isinstance(tarea_info, dict):
                validacion_granular_exitosa = False
                detalle_error_validacion = f"Elemento en lista_tareas no es un diccionario. Tarea: {tarea_info}"
                tarea_fallida_id_val = "N/A (formato incorrecto)"
                break
            
            tarea_fallida_id_val = tarea_info.get("id", "ID_DESCONOCIDO")

            if 'bloques_codigo_objetivo' not in tarea_info:
                validacion_granular_exitosa = False
                detalle_error_validacion = "Clave 'bloques_codigo_objetivo' ausente en la tarea."
                break
            if not isinstance(tarea_info['bloques_codigo_objetivo'], list):
                validacion_granular_exitosa = False
                detalle_error_validacion = "'bloques_codigo_objetivo' no es una lista."
                break
            if not tarea_info['bloques_codigo_objetivo']: # Lista vacía es error
                validacion_granular_exitosa = False
                detalle_error_validacion = "'bloques_codigo_objetivo' está vacía."
                break

            for bloque in tarea_info['bloques_codigo_objetivo']:
                bloque_fallido_nombre_val = bloque.get("nombre_bloque", "NOMBRE_BLOQUE_DESCONOCIDO")
                if not isinstance(bloque, dict):
                    validacion_granular_exitosa = False
                    detalle_error_validacion = "Elemento en 'bloques_codigo_objetivo' no es un diccionario."
                    break
                
                campos_requeridos_bloque = {
                    "archivo": (str, True), "nombre_bloque": (str, True),
                    "linea_inicio": (int, lambda x: x >= 1),
                    "linea_fin": (int, None) 
                }
                for campo, (tipo_esperado, validacion_extra) in campos_requeridos_bloque.items():
                    if campo not in bloque:
                        validacion_granular_exitosa = False
                        detalle_error_validacion = f"Bloque '{bloque_fallido_nombre_val}' no tiene clave '{campo}'."
                        break
                    if not isinstance(bloque[campo], tipo_esperado):
                        validacion_granular_exitosa = False
                        detalle_error_validacion = f"Clave '{campo}' en bloque '{bloque_fallido_nombre_val}' no es de tipo {tipo_esperado.__name__} (es {type(bloque[campo]).__name__})."
                        break
                    if isinstance(validacion_extra, bool) and validacion_extra and not bloque[campo]:
                        validacion_granular_exitosa = False
                        detalle_error_validacion = f"Clave '{campo}' (string) en bloque '{bloque_fallido_nombre_val}' está vacía."
                        break
                    if callable(validacion_extra) and not validacion_extra(bloque[campo]):
                        validacion_granular_exitosa = False
                        detalle_error_validacion = f"Clave '{campo}' en bloque '{bloque_fallido_nombre_val}' no pasó validación específica ({bloque[campo]})."
                        break
                if not validacion_granular_exitosa: break
                
                linea_inicio_val = bloque['linea_inicio']
                linea_fin_val = bloque['linea_fin']
                if not (linea_fin_val >= linea_inicio_val):
                    validacion_granular_exitosa = False
                    detalle_error_validacion = f"En bloque '{bloque_fallido_nombre_val}', linea_fin ({linea_fin_val}) debe ser >= linea_inicio ({linea_inicio_val})."
                    break
            if not validacion_granular_exitosa: break
        
        if not validacion_granular_exitosa:
            logging.critical(f"{logPrefix} VALIDACIÓN GRANULAR FALLIDA para misión '{nombre_clave}' (desde TODO.md). Razón: {detalle_error_validacion}. Tarea ID (aprox): {tarea_fallida_id_val}, Bloque (aprox): {bloque_fallido_nombre_val}")
            
            # Acción Correctiva: NO crear rama, NO guardar misión/estado.
            manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                manejadorHistorial.formatearEntradaHistorial(
                    outcome=f"PASO_TODO_ERROR_VALIDACION_GRANULAR:{nombre_clave}",
                    error_message="La misión generada desde TODO.md no cumple con la estructura granular esperada.",
                    result_details={"tarea_fallida_id": tarea_fallida_id_val, 
                                    "bloque_fallido_nombre": bloque_fallido_nombre_val, 
                                    "detalle_error_validacion": detalle_error_validacion,
                                    "fuente_mision": "TODO.md"
                                    }
                )
            ])
            return False # Falla la creación de misión desde TODO.md
        else:
            logging.info(f"{logPrefix} Validación granular de misión '{nombre_clave}' (desde TODO.md) EXITOSA.")
        # --- FIN VALIDACIÓN GRANULAR ---

        nombre_archivo_mision = f"{nombre_clave}.md"
        rama_base = manejadorGit.obtener_rama_actual(settings.RUTACLON) or settings.RAMATRABAJO

        if not manejadorGit.crear_y_cambiar_a_rama(settings.RUTACLON, nombre_clave, rama_base):
            logging.error(f"{logPrefix} No se pudo crear/cambiar a rama '{nombre_clave}' desde '{rama_base}'.")
            return False

        try:
            with open(os.path.join(settings.RUTACLON, nombre_archivo_mision), 'w', encoding='utf-8') as f:
                f.write(contenido_md)
        except Exception as e_write_md:
            logging.error(f"{logPrefix} Error guardando archivo de misión '{nombre_archivo_mision}': {e_write_md}")
            # Intentar volver a la rama base y eliminar la rama de misión si se creó
            manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, rama_base)
            manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave, local=True)
            return False

        # Verificar si hay tareas pendientes después de la validación granular (que ya valida si lista_tareas_val existe y tiene elementos)
        # Si la validación granular pasó, y lista_tareas_val no era vacía, hay_pendientes debería ser true si alguna tarea está PENDIENTE.
        _, _, hay_pendientes = manejadorMision.parsear_mision_orion(contenido_md) # Re-parsear por si acaso
        if not hay_pendientes: # Esto también cubriría el caso de que la validación granular pasara con lista_tareas_val vacía (lo cual no debería ocurrir por la lógica de validación)
            logging.error(f"{logPrefix} ERROR: Misión '{nombre_clave}' desde TODO.md generada SIN TAREAS PENDIENTES (o ninguna tarea en absoluto después de validación). Limpiando.")
            manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, rama_base)
            manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave, local=True)
            manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                manejadorHistorial.formatearEntradaHistorial(
                    outcome=f"PASO_TODO_ERROR_MISION_SIN_TAREAS_PENDIENTES:{nombre_clave}",
                    error_message="Misión generada desde TODO.md no tiene tareas pendientes (o ninguna tarea en absoluto).",
                    result_details={"fuente_mision": "TODO.md"}
                )
            ])
            return False
        
        if not manejadorGit.hacerCommitEspecifico(settings.RUTACLON, f"Crear misión desde TODO.md: {nombre_clave}", [nombre_archivo_mision]):
            logging.error(f"{logPrefix} No se pudo hacer commit de {nombre_archivo_mision}.")
            # No se limpia la rama para debug manual si el commit falla pero el archivo se creó.
            return False

        logging.info(f"{logPrefix} Misión '{nombre_clave}' generada, validada y commiteada desde TODO.md.")
        guardar_estado_mision_activa(nombre_clave)
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO_TODO_MISION_GENERADA:{nombre_clave}",
                result_details={"archivo_mision": nombre_archivo_mision}
            )
        ])
        if modo_automatico: # Solo hacer push si el modo automático está activo
            manejadorGit.hacerPush(settings.RUTACLON, nombre_clave, setUpstream=True)
        return True # Misión creada exitosamente

    except Exception as e:
        logging.error(f"{logPrefix} Error procesando TODO.md: {e}", exc_info=True)
        # Limpieza de rama si se creó antes de una excepción no manejada
        nombre_clave_potencial = locals().get("nombre_clave")
        if nombre_clave_potencial and manejadorGit.obtener_rama_actual(settings.RUTACLON) == nombre_clave_potencial:
            rama_base_local = locals().get("rama_base", settings.RAMATRABAJO)
            manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, rama_base_local)
            manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_potencial, local=True)
        return False
    
def _intentarCrearMisionDesdeSeleccionArchivo(api_provider: str, modo_automatico: bool, registro_archivos_analizados: dict):
    logPrefix = "_intentarCrearMisionDesdeSeleccionArchivo:"
    MAX_INTENTOS_SELECCION = 5

    for intento in range(1, MAX_INTENTOS_SELECCION + 1):
        logging.info(f"{logPrefix} Iniciando intento de selección de archivo #{intento}/{MAX_INTENTOS_SELECCION}...")

        res_paso1_1, archivo_sel, ctx_sel, decision_ia_1_1 = paso1_1_seleccion_y_decision_inicial(
            settings.RUTACLON, api_provider, registro_archivos_analizados)

        if res_paso1_1 == "generar_mision":
            logging.info(f"{logPrefix} Archivo '{archivo_sel}' seleccionado. Generando misión...")
            res_paso1_2, contenido_mision_generada_md, nombre_clave_generado = paso1_2_generar_mision(
                settings.RUTACLON, archivo_sel, ctx_sel, decision_ia_1_1, api_provider)

            if res_paso1_2 == "mision_generada_ok" and nombre_clave_generado and contenido_mision_generada_md:
                # --- INICIO VALIDACIÓN GRANULAR (A.4) ---
                logging.info(f"{logPrefix} Validando estructura granular de la misión '{nombre_clave_generado}'.")
                _, lista_tareas_val, _ = manejadorMision.parsear_mision_orion(contenido_mision_generada_md)
                
                validacion_granular_exitosa = True
                detalle_error_validacion = "Error desconocido durante validación granular."
                tarea_fallida_id_val = None
                bloque_fallido_nombre_val = None

                if not lista_tareas_val: # Si parsear_mision_orion devolvió una lista vacía o None para tareas
                    if "### Tarea" in contenido_mision_generada_md: # Si el MD parece tener tareas pero el parser no las sacó
                        validacion_granular_exitosa = False
                        detalle_error_validacion = "El parser de misiones no pudo extraer tareas, aunque el MD parece contenerlas."
                        logging.error(f"{logPrefix} {detalle_error_validacion} Misión: {nombre_clave_generado}")
                    # Si no hay '### Tarea' y lista_tareas_val es vacía, podría ser una misión sin tareas (ej. solo metadatos), lo cual es raro pero no necesariamente un fallo *granular*.
                    # La lógica más abajo (decision_ia_1_1.get("necesita_refactor") and not hay_pendientes) lo capturaría si se esperaba refactor.
                    # Para la validación granular, si no hay tareas, no hay bloques que validar.
                    
                for tarea_info in lista_tareas_val if lista_tareas_val else []:
                    if not isinstance(tarea_info, dict):
                        validacion_granular_exitosa = False
                        detalle_error_validacion = f"Elemento en lista_tareas no es un diccionario. Tarea: {tarea_info}"
                        tarea_fallida_id_val = "N/A (formato incorrecto)"
                        break
                    
                    tarea_fallida_id_val = tarea_info.get("id", "ID_DESCONOCIDO")

                    if 'bloques_codigo_objetivo' not in tarea_info:
                        validacion_granular_exitosa = False
                        detalle_error_validacion = "Clave 'bloques_codigo_objetivo' ausente en la tarea."
                        break
                    if not isinstance(tarea_info['bloques_codigo_objetivo'], list):
                        validacion_granular_exitosa = False
                        detalle_error_validacion = "'bloques_codigo_objetivo' no es una lista."
                        break
                    if not tarea_info['bloques_codigo_objetivo']: # Lista vacía
                        validacion_granular_exitosa = False
                        detalle_error_validacion = "'bloques_codigo_objetivo' está vacía."
                        break

                    for bloque in tarea_info['bloques_codigo_objetivo']:
                        bloque_fallido_nombre_val = bloque.get("nombre_bloque", "NOMBRE_BLOQUE_DESCONOCIDO")
                        if not isinstance(bloque, dict):
                            validacion_granular_exitosa = False
                            detalle_error_validacion = "Elemento en 'bloques_codigo_objetivo' no es un diccionario."
                            break
                        
                        campos_requeridos_bloque = {
                            "archivo": (str, True), "nombre_bloque": (str, True),
                            "linea_inicio": (int, lambda x: x >= 1),
                            "linea_fin": (int, None) # Validado con linea_inicio después
                        }
                        for campo, (tipo_esperado, validacion_extra) in campos_requeridos_bloque.items():
                            if campo not in bloque:
                                validacion_granular_exitosa = False
                                detalle_error_validacion = f"Bloque '{bloque_fallido_nombre_val}' no tiene clave '{campo}'."
                                break
                            if not isinstance(bloque[campo], tipo_esperado):
                                validacion_granular_exitosa = False
                                detalle_error_validacion = f"Clave '{campo}' en bloque '{bloque_fallido_nombre_val}' no es de tipo {tipo_esperado.__name__} (es {type(bloque[campo]).__name__})."
                                break
                            if isinstance(validacion_extra, bool) and validacion_extra and not bloque[campo]: # Para strings no vacíos
                                validacion_granular_exitosa = False
                                detalle_error_validacion = f"Clave '{campo}' (string) en bloque '{bloque_fallido_nombre_val}' está vacía."
                                break
                            if callable(validacion_extra) and not validacion_extra(bloque[campo]):
                                validacion_granular_exitosa = False
                                detalle_error_validacion = f"Clave '{campo}' en bloque '{bloque_fallido_nombre_val}' no pasó validación específica ({bloque[campo]})."
                                break
                        if not validacion_granular_exitosa: break
                        
                        # Validación específica para linea_fin vs linea_inicio
                        linea_inicio_val = bloque['linea_inicio']
                        linea_fin_val = bloque['linea_fin']
                        if not (linea_fin_val >= linea_inicio_val):
                            validacion_granular_exitosa = False
                            detalle_error_validacion = f"En bloque '{bloque_fallido_nombre_val}', linea_fin ({linea_fin_val}) debe ser >= linea_inicio ({linea_inicio_val})."
                            break
                    if not validacion_granular_exitosa: break
                
                if not validacion_granular_exitosa:
                    logging.critical(f"{logPrefix} VALIDACIÓN GRANULAR FALLIDA para misión '{nombre_clave_generado}'. Razón: {detalle_error_validacion}. Tarea ID (aprox): {tarea_fallida_id_val}, Bloque (aprox): {bloque_fallido_nombre_val}")
                    
                    # Acción Correctiva
                    logging.info(f"{logPrefix} Revirtiendo creación de misión '{nombre_clave_generado}' debido a fallo de validación granular.")
                    rama_actual_antes_cleanup = manejadorGit.obtener_rama_actual(settings.RUTACLON)
                    if rama_actual_antes_cleanup != settings.RAMATRABAJO:
                        if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                            logging.error(f"{logPrefix} CRÍTICO: No se pudo cambiar a RAMATRABAJO ('{settings.RAMATRABAJO}') para limpiar la rama fallida '{nombre_clave_generado}'. Puede requerir intervención manual.")
                            # No continuar con 'continue' si esto falla, podría dejar el repo en mal estado para el siguiente ciclo.
                            # Mejor devolver False para que el script termine.
                            return False # Fallo crítico de la fase.

                    if manejadorGit.existe_rama(settings.RUTACLON, nombre_clave_generado, local_only=True):
                         if not manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_generado, local=True):
                            logging.warning(f"{logPrefix} No se pudo eliminar la rama de misión local '{nombre_clave_generado}' tras fallo de validación. Puede requerir intervención manual.")
                    else:
                        logging.info(f"{logPrefix} La rama de misión '{nombre_clave_generado}' no existía localmente para ser eliminada (o ya fue eliminada por `paso1_2_generar_mision` en un flujo de error interno no esperado).")

                    # No guardar .active_mission (ya que la misión no se considera creada)
                    # El archivo .md de la misión fue creado y commiteado por paso1_2_generar_mision,
                    # pero la rama será eliminada, por lo que el archivo MD "desaparecerá" con ella.

                    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                        manejadorHistorial.formatearEntradaHistorial(
                            outcome=f"PASO1.2_ERROR_VALIDACION_GRANULAR:{nombre_clave_generado}",
                            error_message="La misión no cumple con la estructura granular esperada.",
                            result_details={"tarea_fallida_id": tarea_fallida_id_val, 
                                            "bloque_fallido_nombre": bloque_fallido_nombre_val, 
                                            "detalle_error_validacion": detalle_error_validacion,
                                            "archivo_principal_decision": archivo_sel
                                            }
                        )
                    ])
                    logging.info(f"{logPrefix} Reintentando selección de archivo (intento {intento}/{MAX_INTENTOS_SELECCION}).")
                    continue # Al siguiente intento del bucle de MAX_INTENTOS_SELECCION
                else:
                    logging.info(f"{logPrefix} Validación granular de misión '{nombre_clave_generado}' EXITOSA.")
                # --- FIN VALIDACIÓN GRANULAR ---

                # La lógica original de _intentarCrearMisionDesdeSeleccionArchivo continúa aquí si la validación granular fue exitosa
                # No se usa el contenido_mision_generada_md leído del archivo, sino el devuelto por paso1_2
                # porque la validación ya lo usó.
                
                # Validar que la misión generada tiene tareas si se esperaba un refactor
                # Esta validación es diferente de la granular, se enfoca en si hay tareas en absoluto.
                _, _, hay_pendientes = manejadorMision.parsear_mision_orion(contenido_mision_generada_md)
                if decision_ia_1_1.get("necesita_refactor") and not hay_pendientes:
                    logging.error(f"{logPrefix} INCONSISTENCIA: IA indicó refactor para '{archivo_sel}' pero misión '{nombre_clave_generado}' no tiene tareas. Limpiando y reintentando.")
                    # Limpieza similar a la de fallo de validación granular
                    rama_actual_antes_cleanup_nopending = manejadorGit.obtener_rama_actual(settings.RUTACLON)
                    if rama_actual_antes_cleanup_nopending != settings.RAMATRABAJO:
                         if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                            logging.error(f"{logPrefix} CRÍTICO (no_pendientes): No se pudo cambiar a RAMATRABAJO. Abortando.")
                            return False
                    
                    if manejadorGit.existe_rama(settings.RUTACLON, nombre_clave_generado, local_only=True):
                        manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_generado, local=True)
                    
                    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                        manejadorHistorial.formatearEntradaHistorial(
                            outcome=f"PASO1.2_ERROR_MISION_SIN_TAREAS:{nombre_clave_generado}",
                            error_message="IA indicó refactor pero misión generada no tiene tareas.",
                            result_details={"archivo_principal_decision": archivo_sel}
                        )
                    ])
                    continue  # Siguiente intento del bucle

                guardar_estado_mision_activa(nombre_clave_generado)
                logging.info(f"{logPrefix} Nueva misión '{nombre_clave_generado}' creada y validada. Fase completada.")
                if modo_automatico:
                    manejadorGit.hacerPush(settings.RUTACLON, nombre_clave_generado, setUpstream=True)
                return True  # Misión creada exitosamente, termina la función

            else:  # Error en paso1_2_generar_mision
                logging.error(f"{logPrefix} Error generando misión para '{archivo_sel}'. Limpiando si es necesario y reintentando con otro archivo.")
                # paso1_2_generar_mision ya intenta limpiar la rama si falla ANTES de crear el commit del MD.
                # Si falla DESPUÉS de crear la rama pero ANTES del commit, nombre_clave_generado podría tener valor.
                # Es importante que el `continue` aquí no guarde estado de misión activa.
                rama_actual_antes_cleanup_errgen = manejadorGit.obtener_rama_actual(settings.RUTACLON)
                if rama_actual_antes_cleanup_errgen != settings.RAMATRABAJO:
                     if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                        logging.error(f"{logPrefix} CRÍTICO (err_generacion): No se pudo cambiar a RAMATRABAJO. Abortando.")
                        return False

                if nombre_clave_generado and manejadorGit.existe_rama(settings.RUTACLON, nombre_clave_generado, local_only=True):
                    logging.info(f"{logPrefix} Eliminando rama '{nombre_clave_generado}' debido a fallo en `paso1_2_generar_mision`.")
                    manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_generado, local=True)
                continue  # Siguiente intento del bucle

        elif res_paso1_1 == "reintentar_seleccion":
            logging.info(f"{logPrefix} Intento #{intento}: IA rechazó el archivo o era inválido. Buscando otro.")
            continue  # Siguiente intento del bucle

        elif res_paso1_1 == "ciclo_terminado_sin_accion":
            logging.warning(f"{logPrefix} No se encontraron más archivos para analizar. Finalizando fase.")
            break  # Salir del bucle for

        else: # Resultado inesperado (ej. error crítico en paso1.1)
            logging.error(f"{logPrefix} Resultado inesperado de paso1.1: {res_paso1_1}. Fase de creación fallida.")
            return False  # Fallo crítico

    logging.info(f"{logPrefix} No se generó ninguna misión nueva tras {MAX_INTENTOS_SELECCION} intentos (o se completó el ciclo). Fase completada.")
    return True # La fase es exitosa aunque no se haya creado nada.

def _crearNuevaMision(api_provider: str, modo_automatico: bool, registro_archivos_analizados: dict):
    logPrefix = "_crearNuevaMision:"
    logging.info(f"{logPrefix} Iniciando proceso de creación de nueva misión.")

    if manejadorGit.obtener_rama_actual(settings.RUTACLON) != settings.RAMATRABAJO:
        logging.info(f"{logPrefix} No se está en '{settings.RAMATRABAJO}'. Intentando cambiar...")
        if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(f"{logPrefix} No se pudo cambiar a '{settings.RAMATRABAJO}'. Abortando creación.")
            return False

    # Estrategia 1: Intentar crear misión desde TODO.md. Si tiene éxito, la fase termina.
    if _intentarCrearMisionDesdeTodoMD(api_provider, modo_automatico):
        logging.info(f"{logPrefix} Misión creada exitosamente desde TODO.md. La fase de creación ha concluido.")
        return True # Misión creada, se detiene el script para la siguiente fase.

    # Estrategia 2: Si la estrategia 1 no creó una misión, proceder con la selección de archivo.
    logging.info(f"{logPrefix} No se creó misión desde TODO.md. Procediendo con selección de archivo estándar.")
    # La función de selección de archivo ya maneja su propia lógica de fase (intentos, etc.)
    # y devuelve True si la fase se completa, con o sin una misión creada.
    # Su valor de retorno es el resultado final de nuestra fase de creación.
    return _intentarCrearMisionDesdeSeleccionArchivo(api_provider, modo_automatico, registro_archivos_analizados)

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

    # Limpiar registro de archivos analizados en su nueva ubicación
    # Esta acción depende de que REGISTRO_ARCHIVOS_ANALIZADOS_PATH esté correctamente definido
    # para apuntar a settings.RUTACLON/.orion_meta/registro_archivos_analizados.json
    if os.path.exists(REGISTRO_ARCHIVOS_ANALIZADOS_PATH):
        try:
            os.remove(REGISTRO_ARCHIVOS_ANALIZADOS_PATH)
            logging.info(
                f"{logPrefix} Archivo de registro de análisis '{REGISTRO_ARCHIVOS_ANALIZADOS_PATH}' eliminado.")
        except Exception as e:
            logging.error(
                f"{logPrefix} Error eliminando '{REGISTRO_ARCHIVOS_ANALIZADOS_PATH}': {e}", exc_info=True)
    else:
        logging.info(
            f"{logPrefix} Archivo de registro de análisis '{REGISTRO_ARCHIVOS_ANALIZADOS_PATH}' no encontrado, no se requiere eliminación.")

    # El archivo de logging principal (`historial_refactor_adaptativo.log`) se trunca/sobrescribe
    # en cada ejecución normal debido al modo 'w' del FileHandler en configurarLogging.
    # No se necesita limpiar explícitamente aquí a menos que la política cambie.

    logging.info(
        f"{logPrefix} Reseteo del estado del agente (archivo .active_mission, registro_archivos_analizados.json y rama de misión local asociada si existía) completado.")
    return True


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

    # Se está en la rama de la misión activa. Revisar el archivo de misión específico.
    # paso0_revisar_mision_local internamente usa nombreClaveMisionActiva para construir el nombre_archivo_mision.
    resultadoPaso0, _, _, _ = paso0_revisar_mision_local(
        settings.RUTACLON, nombreClaveMisionActiva)

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
            # El estado de la misión se actualizó en el archivo de misión de la rama.
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
        nombre_archivo_mision_esperado = f"{nombreClaveMisionActiva}.md"
        logging.warning(f"{logPrefix} El archivo de misión '{nombre_archivo_mision_esperado}' (esperado para la misión activa '{nombreClaveMisionActiva}') "
                        f"no fue encontrado o no es válido según paso0_revisar_mision_local (resultado: {resultadoPaso0}). "
                        f"Limpiando estado y procediendo a crear nueva misión.")
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
