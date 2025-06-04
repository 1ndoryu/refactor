# principal.py

import logging
import sys
import os
import json
import argparse
import subprocess  # No se usa directamente aquí, pero podría ser usado por sub-funciones
import time
import signal
from datetime import datetime, timedelta  # timedelta para gestionar tokens
from config import settings
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios
from nucleo import manejadorHistorial

# --- Nuevas Constantes y Variables Globales ---
# Estas podrían ir en settings.py o definirse aquí si son específicas de la lógica principal
REGISTRO_ARCHIVOS_ANALIZADOS_PATH = os.path.join(
    settings.RUTA_BASE_PROYECTO, "registro_archivos_analizados.json")
MISION_ORION_MD = "misionOrion.md"
TOKEN_LIMIT_PER_MINUTE = getattr(
    settings, 'TOKEN_LIMIT_PER_MINUTE', 250000)  # Definir en settings.py
# Lista de tuplas (timestamp, tokens_usados) para la ventana de 60s
token_usage_window = []

# --- Fin Nuevas Constantes ---


class TimeoutException(Exception):
    """Excepción para indicar que el tiempo límite de ejecución fue alcanzado."""
    pass

# --- Funciones para el manejo de tokens (NUEVO) ---


def gestionar_limite_tokens(tokens_a_usar_estimados: int, proveedor_api: str):
    """
    Gestiona el límite de tokens por minuto.
    Pausa si es necesario antes de realizar una llamada a la API.
    Actualiza la ventana de uso de tokens.
    """
    global token_usage_window
    logPrefix = "gestionar_limite_tokens:"

    ahora = datetime.now()
    # Filtrar tokens usados fuera de la ventana de los últimos 60 segundos
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
        # Esperar al menos 1s más para estar seguros
        segundos_a_esperar = max(1, int(segundos_a_esperar) + 1)
        logging.info(f"{logPrefix} Límite de tokens ({TOKEN_LIMIT_PER_MINUTE}/min) excedería. "
                     f"Usados: {tokens_usados_en_ventana}. A usar: {tokens_a_usar_estimados}. "
                     f"Pausando por {segundos_a_esperar} segundos...")
        time.sleep(segundos_a_esperar)
        # Re-evaluar después de la pausa (recursivo o recalcular)
        # Simple recursión para re-evaluar
        return gestionar_limite_tokens(tokens_a_usar_estimados, proveedor_api)

    # Nota: El registro real de tokens (con `registrar_tokens_usados`) debe hacerse DESPUÉS de la llamada exitosa a la API,
    # utilizando los tokens *reales* consumidos, no solo los estimados.
    logging.info(
        f"{logPrefix} OK para proceder con {tokens_a_usar_estimados} tokens (estimados).")
    return True


def registrar_tokens_usados(tokens_usados: int):
    """Registra los tokens después de una llamada exitosa a la API."""
    global token_usage_window
    token_usage_window.append((datetime.now(), tokens_usados))
    # Recalcular tokens en ventana para el log
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
    return {}  # { "ruta_relativa_archivo": "timestamp_iso_ultima_seleccion" }


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
    # Usar un timestamp muy futuro para asegurar que cualquier archivo no registrado o antiguo sea elegido
    timestamp_mas_antiguo = datetime.max.isoformat()

    # Convertir rutas absolutas a relativas para consistencia con el registro
    archivos_proyecto_relativos = []
    for abs_path in archivos_proyecto_abs:
        try:
            rel_path = os.path.relpath(
                abs_path, ruta_proyecto).replace(os.sep, '/')
            archivos_proyecto_relativos.append(rel_path)
        except ValueError as e:  # Esto puede pasar si abs_path no está bajo ruta_proyecto
            logging.warning(
                f"{logPrefix} No se pudo obtener ruta relativa para {abs_path} respecto a {ruta_proyecto}: {e}")
            continue

    if not archivos_proyecto_relativos:
        logging.warning(
            f"{logPrefix} No quedaron archivos válidos después de convertir a rutas relativas.")
        return None

    # Buscar el archivo no registrado o el más antiguo
    for ruta_rel_archivo in archivos_proyecto_relativos:
        timestamp_ultima_seleccion = registro_archivos.get(ruta_rel_archivo)
        if timestamp_ultima_seleccion is None:  # Nunca seleccionado
            archivo_seleccionado_rel = ruta_rel_archivo
            logging.info(
                f"{logPrefix} Archivo '{archivo_seleccionado_rel}' nunca antes seleccionado.")
            break  # Elegir este y salir
        if timestamp_ultima_seleccion < timestamp_mas_antiguo:
            timestamp_mas_antiguo = timestamp_ultima_seleccion
            archivo_seleccionado_rel = ruta_rel_archivo

    if archivo_seleccionado_rel:
        logging.info(
            f"{logPrefix} Archivo seleccionado: {archivo_seleccionado_rel} (Última vez: {registro_archivos.get(archivo_seleccionado_rel, 'Nunca')})")
        # Actualizar el timestamp de este archivo en el registro (se guarda externamente)
        registro_archivos[archivo_seleccionado_rel] = datetime.now(
        ).isoformat()
    else:
        # Esto podría pasar si todos los archivos tienen el mismo timestamp_max (improbable) o si la lista quedó vacía.
        logging.warning(
            f"{logPrefix} No se pudo seleccionar un archivo (todos ya procesados con timestamp futuro o lista vacía).")
        # Opcional: Resetear el registro si todos han sido "seleccionados recientemente"
        # Por ahora, si no hay, no hay. Se podría decidir si re-procesar el más antiguo de todas formas.

    return archivo_seleccionado_rel
# --- Fin funciones registro ---


def orchestrarEjecucionScript(args):
    api_provider_seleccionado = "openrouter" if args.openrouter else "google"
    logging.info(
        f"Iniciando lógica de orquestación ADAPTATIVA. Proveedor API: {api_provider_seleccionado.upper()}. Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

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
        # Llamamos a la nueva función principal del ciclo adaptativo
        ciclo_exitoso_general = ejecutarCicloAdaptativo(
            api_provider_seleccionado, args.modo_test)

        if ciclo_exitoso_general:
            logging.info("Ciclo adaptativo completado.")
            exit_code = 0
        else:
            logging.warning(
                "Ciclo adaptativo finalizó con problemas o interrupciones. Ver logs.")
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
        # Asegurar que se guarde el registro al final, incluso si hubo errores.
        # Carga el registro actual por si se modificó en memoria y no se guardó en un paso intermedio.
        guardar_registro_archivos(cargar_registro_archivos())
        logging.info("Registro de archivos analizados guardado al finalizar.")
    return exit_code


def _validarConfiguracionEsencial(api_provider: str) -> bool:
    logPrefix = f"_validarConfiguracionEsencial({api_provider.upper()}):"
    configuracion_ok = False
    if not settings.REPOSITORIOURL:
        logging.critical(
            f"{logPrefix} REPOSITORIOURL no está configurado en settings.py. Abortando.")
        return False

    if api_provider == 'google':
        if settings.GEMINIAPIKEY:
            configuracion_ok = True
        else:
            logging.critical(
                f"{logPrefix} Google Gemini seleccionado pero GEMINI_API_KEY no configurada. Abortando.")
    elif api_provider == 'openrouter':
        if settings.OPENROUTER_API_KEY:
            configuracion_ok = True
        else:
            logging.critical(
                f"{logPrefix} OpenRouter seleccionado pero OPENROUTER_API_KEY no configurada. Abortando.")
    else:
        logging.critical(
            f"{logPrefix} Proveedor API desconocido: '{api_provider}'. Abortando.")
        return False

    # Este if es redundante si los anteriores ya retornan False, pero por claridad.
    if not configuracion_ok:
        logging.critical(
            f"{logPrefix} Configuración esencial faltante para proveedor '{api_provider}'. Abortando.")
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
        for handler in log_raiz.handlers:  # Limpiar handlers existentes para evitar duplicación
            log_raiz.removeHandler(handler)
            handler.close()

    nivelLog = logging.DEBUG  # Cambiado a DEBUG para más detalle durante desarrollo
    # Nombre del módulo
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
            rutaLogArchivo, mode='w', encoding='utf-8')  # mode='w' para nuevo log cada vez
        archivoHandler.setFormatter(
            logging.Formatter(formatoLog, fechaFormato))
        log_raiz.addHandler(archivoHandler)
    except Exception as e:
        # Si falla el log de archivo, al menos tendremos el de consola.
        # Usar print porque el logger podría no estar completamente configurado.
        print(
            f"ERROR CRITICO [configurarLogging]: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}", file=sys.stderr)

    log_raiz.setLevel(nivelLog)
    logging.info("="*50)
    logging.info("Sistema de logging configurado para modo adaptativo.")
    logging.info(f"Nivel de log: {logging.getLevelName(log_raiz.level)}")

# --- Funciones específicas para los nuevos pasos ---


def paso0_revisar_mision_local(ruta_repo):
    """
    Paso 0: Revisa si existe misionOrion.md y si tiene tareas pendientes.
    Retorna: (estado, contenido_mision, lista_archivos_contexto_mision, nombre_clave_mision_detectada)
             estado: "procesar_mision_existente", "crear_nueva_mision"
    """
    logPrefix = "paso0_revisar_mision_local:"
    ruta_mision_orion = os.path.join(ruta_repo, MISION_ORION_MD)

    if os.path.exists(ruta_mision_orion):
        logging.info(f"{logPrefix} Se encontró {MISION_ORION_MD}.")
        try:
            with open(ruta_mision_orion, 'r', encoding='utf-8') as f:
                contenido_mision = f.read()

            # Implementación robusta de parseo es necesaria aquí.
            hay_tareas_pendientes, archivos_contexto_mision = parsear_mision_orion(
                contenido_mision)
            nombre_clave = parsear_nombre_clave_de_mision(contenido_mision)

            if not nombre_clave:
                logging.warning(
                    f"{logPrefix} {MISION_ORION_MD} existe pero no se pudo extraer nombre clave. Se tratará como para crear nueva misión.")
                return "crear_nueva_mision", None, None, None

            if hay_tareas_pendientes:
                logging.info(
                    f"{logPrefix} Misión '{nombre_clave}' con tareas pendientes. Pasando a Paso 2.")
                return "procesar_mision_existente", contenido_mision, archivos_contexto_mision, nombre_clave
            else:
                logging.info(
                    f"{logPrefix} Misión '{nombre_clave}' sin tareas pendientes o completada. Se procederá a crear una nueva.")
                # Opcional: Archivar o eliminar el misionOrion.md completado aquí.
                # Por ahora, se ignora y se creará una nueva (podría sobrescribirse si el nombre es el mismo,
                # pero la generación de nombre clave debería intentar ser única).
                return "crear_nueva_mision", None, None, None
        except Exception as e:
            logging.error(
                f"{logPrefix} Error leyendo o parseando {MISION_ORION_MD}: {e}. Se intentará crear una nueva.")
            return "crear_nueva_mision", None, None, None
    else:
        logging.info(
            f"{logPrefix} No se encontró {MISION_ORION_MD}. Se procederá a crear una nueva misión.")
        return "crear_nueva_mision", None, None, None


def parsear_mision_orion(contenido_mision: str):
    """
    Placeholder para parsear misionOrion.md.
    Debe retornar: (bool_hay_tareas_pendientes, lista_archivos_contexto)
    NECESITA IMPLEMENTACIÓN ROBUSTA.
    """
    if not contenido_mision:
        return False, []

    tareas_pendientes = "[ ]" in contenido_mision
    archivos_contexto = []
    try:
        # Ejemplo muy básico: buscar una línea como "Archivos de Contexto: archivo1.py, archivo2.js"
        # Esto es propenso a errores y necesita un formato de misión más estructurado.
        for line in contenido_mision.splitlines():
            line_lower = line.lower()
            # Más flexible
            if line_lower.startswith("**archivos de contexto") and ":" in line_lower:
                archivos_str = line.split(":", 1)[1].strip()
                if archivos_str and archivos_str.lower() != "ninguno":
                    archivos_contexto = [
                        f.strip() for f in archivos_str.split(',') if f.strip()]
                break
    except Exception as e:
        logging.error(
            f"Error (placeholder) parseando archivos de contexto de misión: {e}")

    return tareas_pendientes, archivos_contexto


def paso1_1_seleccion_y_decision_inicial(ruta_repo, api_provider, registro_archivos):
    """
    Paso 1.1: Selecciona archivo, IA decide si refactorizar y qué contexto necesita.
    Retorna: (accion, archivo_para_mision, archivos_contexto_para_mision, decision_IA_paso1_1)
             accion: "generar_mision", "reintentar_seleccion", "ciclo_terminado_sin_accion"
    """
    logPrefix = "paso1_1_seleccion_y_decision_inicial:"
    archivo_seleccionado_rel = seleccionar_archivo_mas_antiguo(
        ruta_repo, registro_archivos)
    # Guardar el registro_archivos inmediatamente después de actualizar el timestamp en seleccionar_archivo_mas_antiguo
    guardar_registro_archivos(registro_archivos)

    if not archivo_seleccionado_rel:
        logging.warning(
            f"{logPrefix} No se pudo seleccionar ningún archivo. Terminando ciclo de creación de misión.")
        return "ciclo_terminado_sin_accion", None, None, None

    ruta_archivo_seleccionado_abs = os.path.join(
        ruta_repo, archivo_seleccionado_rel)
    if not os.path.exists(ruta_archivo_seleccionado_abs):
        logging.error(
            f"{logPrefix} Archivo seleccionado '{archivo_seleccionado_rel}' (Abs: {ruta_archivo_seleccionado_abs}) no existe. Reintentando selección.")
        # Marcar como "no encontrado" para evitar seleccionarlo de nuevo inmediatamente
        registro_archivos[archivo_seleccionado_rel] = datetime.now(
        ).isoformat() + "_NOT_FOUND"
        guardar_registro_archivos(registro_archivos)
        return "reintentar_seleccion", None, None, None

    estructura_proyecto = analizadorCodigo.generarEstructuraDirectorio(
        ruta_repo,
        directorios_ignorados=settings.DIRECTORIOS_IGNORADOS,
        max_depth=5,
        incluir_archivos=True
    )

    resultado_lectura_archivo = analizadorCodigo.leerArchivos(
        [ruta_archivo_seleccionado_abs], ruta_repo, api_provider=api_provider)
    contenido_archivo_seleccionado = resultado_lectura_archivo['contenido']
    tokens_contenido_archivo = resultado_lectura_archivo['tokens']

    tokens_estructura_proyecto = 0
    if estructura_proyecto:
        tokens_estructura_proyecto = analizadorCodigo.contarTokensTexto(
            estructura_proyecto, api_provider)

    # Estimación de tokens para el prompt de la IA (esto es muy aproximado, la función de IA debe calcularlo mejor)
    tokens_prompt_paso1_1_base = 500  # Estimación del prompt base de la IA
    tokens_totales_estimados = tokens_prompt_paso1_1_base + \
        tokens_contenido_archivo + tokens_estructura_proyecto

    gestionar_limite_tokens(tokens_totales_estimados, api_provider)

    # --- INICIO LLAMADA REAL (o placeholder) a analizadorCodigo.solicitar_evaluacion_archivo ---
    # En producción, esta sería la llamada a la IA.
    # decision_IA_paso1_1 = analizadorCodigo.solicitar_evaluacion_archivo(
    #     archivo_seleccionado_rel, # Pasar ruta relativa
    #     contenido_archivo_seleccionado,
    #     estructura_proyecto,
    #     api_provider,
    #     reglas_refactor="" # Añadir reglas si las tienes
    # )
    # tokens_reales_consumidos = decision_IA_paso1_1.get("tokens_consumidos_api", tokens_totales_estimados) # La IA debe devolver esto
    # registrar_tokens_usados(tokens_reales_consumidos)
    # ------ FIN LLAMADA REAL ---

    # ------ INICIO PLACEHOLDER IA PASO 1.1 (Simulación actual) ------
    logging.warning(
        f"{logPrefix} USANDO PLACEHOLDER para decisión IA Paso 1.1 para '{archivo_seleccionado_rel}'")
    time.sleep(0.5)  # Simular llamada API
    necesita_refactor_sim = True  # random.choice([True, False])
    # random.choice([True, False])
    necesita_ctx_sim = True if necesita_refactor_sim else False

    archivos_sugeridos_sim = []
    if necesita_ctx_sim:
        # Intentar sugerir archivos del mismo directorio o relacionados
        dir_archivo_sel = os.path.dirname(archivo_seleccionado_rel)
        archivos_en_dir = [f for f in registro_archivos.keys() if f.startswith(
            dir_archivo_sel) and f != archivo_seleccionado_rel and not "_NOT_FOUND" in registro_archivos[f]]
        if archivos_en_dir:
            archivos_sugeridos_sim = archivos_en_dir[:2]  # Tomar hasta 2
        elif "principal.py" != archivo_seleccionado_rel:  # No sugerir el mismo si es el target
            archivos_sugeridos_sim.append("principal.py")  # Un default

    decision_IA_paso1_1_simulada = {
        "necesita_refactor": necesita_refactor_sim,
        "necesita_contexto_adicional": necesita_ctx_sim,
        "archivos_contexto_sugeridos": archivos_sugeridos_sim,
        "razonamiento": f"Simulación: El archivo '{archivo_seleccionado_rel}' {'parece necesitar' if necesita_refactor_sim else 'NO parece necesitar'} refactor. {'Se sugiere' if necesita_ctx_sim else 'No se sugiere'} contexto adicional.",
        # Simulación de tokens consumidos
        "tokens_consumidos_api": tokens_totales_estimados
    }
    decision_IA_paso1_1 = decision_IA_paso1_1_simulada
    registrar_tokens_usados(decision_IA_paso1_1.get(
        "tokens_consumidos_api", tokens_totales_estimados))
    # ------ FIN PLACEHOLDER IA PASO 1.1 --------

    if not decision_IA_paso1_1 or not decision_IA_paso1_1.get("necesita_refactor"):
        logging.info(f"{logPrefix} IA decidió que '{archivo_seleccionado_rel}' no necesita refactor o hubo error. Razón: {decision_IA_paso1_1.get('razonamiento', 'N/A') if decision_IA_paso1_1 else 'Error en IA'}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO1.1_NO_REFACTOR:{archivo_seleccionado_rel}", decision_details=decision_IA_paso1_1)
        ])
        return "reintentar_seleccion", None, None, None

    logging.info(
        f"{logPrefix} IA decidió que '{archivo_seleccionado_rel}' SÍ necesita refactor. Razón: {decision_IA_paso1_1.get('razonamiento')}")
    archivos_contexto_sugeridos_rel = decision_IA_paso1_1.get(
        "archivos_contexto_sugeridos", [])

    archivos_contexto_validados_rel = []
    if decision_IA_paso1_1.get("necesita_contexto_adicional"):
        for ctx_file_rel in archivos_contexto_sugeridos_rel:
            if not ctx_file_rel or ctx_file_rel == archivo_seleccionado_rel:  # No incluirse a sí mismo
                continue
            ctx_file_abs = os.path.join(ruta_repo, ctx_file_rel)
            if os.path.exists(ctx_file_abs) and os.path.isfile(ctx_file_abs):
                archivos_contexto_validados_rel.append(ctx_file_rel)
            else:
                logging.warning(
                    f"{logPrefix} Archivo de contexto sugerido '{ctx_file_rel}' no existe o no es un archivo. Descartado.")

    return "generar_mision", archivo_seleccionado_rel, archivos_contexto_validados_rel, decision_IA_paso1_1


def paso1_2_generar_mision(ruta_repo, archivo_a_refactorizar_rel, archivos_contexto_rel, decision_paso1_1, api_provider):
    """
    Paso 1.2: IA genera misionOrion.md.
    Retorna: (estado, contenido_mision_generada, nombre_clave_mision)
             estado: "mision_generada_ok", "error_generando_mision"
    """
    logPrefix = "paso1_2_generar_mision:"
    logging.info(
        f"{logPrefix} Generando misión para: '{archivo_a_refactorizar_rel}' con contexto: {archivos_contexto_rel}")

    archivos_para_leer_abs = [os.path.join(
        ruta_repo, archivo_a_refactorizar_rel)]
    for f_rel in archivos_contexto_rel:
        archivos_para_leer_abs.append(os.path.join(ruta_repo, f_rel))

    # Asegurarse de no tener duplicados (aunque relpath debería haberlo prevenido si las rutas son iguales)
    archivos_para_leer_abs_unicos = sorted(list(set(archivos_para_leer_abs)))

    resultado_lectura_ctx = analizadorCodigo.leerArchivos(
        archivos_para_leer_abs_unicos, ruta_repo, api_provider=api_provider)
    contexto_completo_para_mision = resultado_lectura_ctx['contenido']
    tokens_contexto_mision = resultado_lectura_ctx['tokens']

    tokens_prompt_paso1_2_base = 700
    tokens_totales_estimados = tokens_prompt_paso1_2_base + tokens_contexto_mision

    gestionar_limite_tokens(tokens_totales_estimados, api_provider)

    # --- INICIO LLAMADA REAL (o placeholder) a analizadorCodigo.generar_contenido_mision_orion ---
    # contenido_mision_generado_dict = analizadorCodigo.generar_contenido_mision_orion(
    #     archivo_a_refactorizar_rel,
    #     contexto_completo_para_mision,
    #     decision_paso1_1.get("razonamiento"),
    #     api_provider
    # )
    # tokens_reales_consumidos = contenido_mision_generado_dict.get("tokens_consumidos_api", tokens_totales_estimados)
    # registrar_tokens_usados(tokens_reales_consumidos)
    # ------ FIN LLAMADA REAL ---

    # ------ INICIO PLACEHOLDER IA PASO 1.2 (Simulación actual) ------
    logging.warning(
        f"{logPrefix} USANDO PLACEHOLDER para generación de misión Paso 1.2")
    time.sleep(0.5)
    # Limpiar nombre de archivo para usarlo en nombre clave
    nombre_base_archivo = os.path.splitext(
        os.path.basename(archivo_a_refactorizar_rel))[0]
    nombre_base_archivo_limpio = ''.join(
        c if c.isalnum() else '_' for c in nombre_base_archivo)
    nombre_clave_simulado = f"Mision_{nombre_base_archivo_limpio}_{int(time.time()*100) % 10000}"

    contenido_md_simulado = f"""# Misión: {nombre_clave_simulado}

**Archivo Principal a Refactorizar:** {archivo_a_refactorizar_rel}

**Archivos de Contexto (leídos para esta misión):** {', '.join(archivos_contexto_rel) if archivos_contexto_rel else 'Ninguno'}

**Razón General (de Paso 1.1):** {decision_paso1_1.get('razonamiento', 'N/A')}

## Tareas de Refactorización (Pequeñas y Atómicas):
- [ ] Tarea 1: Analizar la función X en '{archivo_a_refactorizar_rel}' y proponer simplificación (Simulación).
- [ ] Tarea 2: Verificar si la variable Y se usa correctamente en '{archivo_a_refactorizar_rel}' (Simulación).
"""
    if archivos_contexto_rel:
        contenido_md_simulado += f"- [ ] Tarea 3: Mover la función Z de '{archivo_a_refactorizar_rel}' a un helper (considerar '{archivos_contexto_rel[0]}') (Simulación).\n"
    else:
        contenido_md_simulado += f"- [ ] Tarea 3: Crear un nuevo archivo helper y mover la función Z de '{archivo_a_refactorizar_rel}' allí (Simulación).\n"

    contenido_mision_generado_dict_simulado = {
        "nombre_clave_mision": nombre_clave_simulado,
        "contenido_markdown_mision": contenido_md_simulado,
        "tokens_consumidos_api": tokens_totales_estimados
    }
    contenido_mision_generado_dict = contenido_mision_generado_dict_simulado
    registrar_tokens_usados(contenido_mision_generado_dict.get(
        "tokens_consumidos_api", tokens_totales_estimados))
    # ------ FIN PLACEHOLDER IA PASO 1.2 --------

    if not contenido_mision_generado_dict or \
       not contenido_mision_generado_dict.get("nombre_clave_mision") or \
       not contenido_mision_generado_dict.get("contenido_markdown_mision"):
        logging.error(
            f"{logPrefix} IA no generó contenido válido para la misión o hubo un error. Respuesta: {contenido_mision_generado_dict}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO1.2_ERROR_GENERACION", decision_details=decision_paso1_1, error_message="IA no generó misión válida")
        ])
        return "error_generando_mision", None, None

    nombre_clave_mision = contenido_mision_generado_dict["nombre_clave_mision"]
    contenido_markdown_mision = contenido_mision_generado_dict["contenido_markdown_mision"]

    # Crear rama para la misión (esta función debe implementarse en manejadorGit.py)
    # La rama base es la rama de trabajo principal (ej. main, master, o la configurada en settings.RAMATRABAJO)
    # Si estamos en una rama de misión de una ejecución anterior y falló, deberíamos volver a la rama base primero.
    # Esta lógica está en ejecutarCicloAdaptativo. Aquí asumimos que estamos en la rama correcta para crear una nueva.
    rama_base_para_nueva_mision = manejadorGit.obtener_rama_actual(
        # Usar rama actual o la de settings como fallback
        ruta_repo) or settings.RAMATRABAJO

    if not manejadorGit.crear_y_cambiar_a_rama(ruta_repo, nombre_clave_mision, rama_base_para_nueva_mision):
        logging.error(
            f"{logPrefix} No se pudo crear o cambiar a la rama de misión '{nombre_clave_mision}' desde '{rama_base_para_nueva_mision}'.")
        return "error_generando_mision", None, None

    logging.info(
        f"{logPrefix} En la rama de misión: '{nombre_clave_mision}' (creada desde '{rama_base_para_nueva_mision}')")

    ruta_mision_orion_abs = os.path.join(ruta_repo, MISION_ORION_MD)
    try:
        with open(ruta_mision_orion_abs, 'w', encoding='utf-8') as f:
            f.write(contenido_markdown_mision)
        logging.info(
            f"{logPrefix} {MISION_ORION_MD} guardado en '{ruta_mision_orion_abs}' en la rama '{nombre_clave_mision}'")
    except Exception as e:
        logging.error(f"{logPrefix} Error guardando {MISION_ORION_MD}: {e}")
        # Opcional: Intentar eliminar la rama creada si falla el guardado
        manejadorGit.cambiar_a_rama_existente(
            ruta_repo, rama_base_para_nueva_mision)  # Volver a base
        manejadorGit.eliminarRama(
            ruta_repo, nombre_clave_mision, local=True)  # Eliminar localmente
        return "error_generando_mision", None, None

    # Hacer commit de misionOrion.md (esta función debe implementarse en manejadorGit.py)
    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Crear misión: {nombre_clave_mision}", [MISION_ORION_MD]):
        logging.error(
            f"{logPrefix} No se pudo hacer commit de {MISION_ORION_MD} en la rama '{nombre_clave_mision}'.")
        # Opcional: Intentar eliminar la rama creada si falla el commit
        manejadorGit.cambiar_a_rama_existente(
            ruta_repo, rama_base_para_nueva_mision)
        manejadorGit.eliminarRama(ruta_repo, nombre_clave_mision, local=True)
        return "error_generando_mision", None, None

    logging.info(
        f"{logPrefix} Misión '{nombre_clave_mision}' generada y commiteada en su rama.")
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(
            outcome=f"PASO1.2_MISION_GENERADA:{nombre_clave_mision}", result_details=f"Archivo: {MISION_ORION_MD}")
    ])
    return "mision_generada_ok", contenido_markdown_mision, nombre_clave_mision


def paso2_ejecutar_tarea_mision(ruta_repo, nombre_rama_mision, contenido_mision_actual, archivos_contexto_mision_original, api_provider, modo_test):
    """
    Paso 2: Lee misionOrion.md, ejecuta UNA tarea.
    Retorna: (estado, contenido_mision_actualizado_o_none)
             estado: "tarea_ejecutada_continuar_mision", "mision_completada_con_merge", "mision_completada_sin_merge", "error_en_tarea"
    """
    logPrefix = f"paso2_ejecutar_tarea_mision (Rama: {nombre_rama_mision}):"
    logging.info(f"{logPrefix} Iniciando ejecución de tarea de la misión.")

    if not manejadorGit.cambiar_a_rama_existente(ruta_repo, nombre_rama_mision):
        logging.error(
            f"{logPrefix} No se pudo cambiar a la rama de misión '{nombre_rama_mision}'. Abortando tarea.")
        # Si no podemos cambiar a la rama, es un error grave para este paso.
        return "error_en_tarea", contenido_mision_actual

    # Volver a parsear la misión para asegurar que tenemos los archivos de contexto correctos definidos DENTRO de la misión
    # y no los que se usaron para crearla (podrían ser diferentes).
    _, archivos_contexto_para_ejecucion = parsear_mision_orion(
        contenido_mision_actual)

    tarea_actual_info, indice_tarea = obtener_proxima_tarea_pendiente(
        contenido_mision_actual)  # NECESITA IMPLEMENTACIÓN ROBUSTA

    if not tarea_actual_info:
        logging.info(
            f"{logPrefix} No se encontraron tareas pendientes en la misión '{nombre_rama_mision}'. Considerada completada.")
        # No hay merge aquí, se maneja en el bucle principal si es necesario después de este retorno.
        return "mision_completada_sin_merge", contenido_mision_actual

    logging.info(
        f"{logPrefix} Tarea a ejecutar (índice {indice_tarea}): '{tarea_actual_info.get('descripcion', 'N/A')}'")

    contexto_para_tarea_str = ""
    tokens_contexto_tarea = 0
    archivos_leidos_para_tarea = []

    # Si la tarea tiene archivos específicos, usarlos. Sino, los generales de la misión.
    archivos_especificos_tarea = tarea_actual_info.get(
        "archivos_implicados", archivos_contexto_para_ejecucion)

    if archivos_especificos_tarea:
        archivos_abs_ctx_tarea = [os.path.join(
            ruta_repo, f_rel) for f_rel in archivos_especificos_tarea if f_rel]  # Filtrar vacíos
        archivos_abs_ctx_tarea_unicos = sorted(
            list(set(archivos_abs_ctx_tarea)))

        resultado_lectura_tarea_ctx = analizadorCodigo.leerArchivos(
            archivos_abs_ctx_tarea_unicos, ruta_repo, api_provider=api_provider)
        contexto_para_tarea_str = resultado_lectura_tarea_ctx['contenido']
        tokens_contexto_tarea = resultado_lectura_tarea_ctx['tokens']
        archivos_leidos_para_tarea = [os.path.relpath(
            p, ruta_repo) for p in archivos_abs_ctx_tarea_unicos]
        logging.info(
            f"{logPrefix} Contexto para tarea leído de: {archivos_leidos_para_tarea}")

    tokens_prompt_paso2_base = 800
    # El token de la descripción de la tarea y la misión completa también cuenta
    tokens_mision_y_tarea_desc = analizadorCodigo.contarTokensTexto(
        contenido_mision_actual + tarea_actual_info.get('descripcion', ''), api_provider)
    tokens_totales_estimados = tokens_prompt_paso2_base + \
        tokens_contexto_tarea + tokens_mision_y_tarea_desc

    gestionar_limite_tokens(tokens_totales_estimados, api_provider)

    # --- INICIO LLAMADA REAL (o placeholder) a analizadorCodigo.ejecutar_tarea_especifica_mision ---
    # resultado_ejecucion_tarea = analizadorCodigo.ejecutar_tarea_especifica_mision(
    #     tarea_actual_info,
    #     contenido_mision_actual, # Pasar la misión completa para contexto general
    #     contexto_para_tarea_str,
    #     api_provider
    # )
    # tokens_reales_consumidos = resultado_ejecucion_tarea.get("tokens_consumidos_api", tokens_totales_estimados)
    # registrar_tokens_usados(tokens_reales_consumidos)
    # ------ FIN LLAMADA REAL ---

    # ------ INICIO PLACEHOLDER IA PASO 2 (Simulación actual) ------
    logging.warning(
        f"{logPrefix} USANDO PLACEHOLDER para ejecución de tarea Paso 2: '{tarea_actual_info.get('descripcion')}'")
    time.sleep(0.5)
    archivos_modificados_simulados = {}
    # Determinar el archivo principal implicado en la tarea
    # Esto es una heurística, la IA debería ser más explícita o la tarea definirlo mejor
    archivo_principal_tarea = tarea_actual_info.get(
        "archivo_principal_implicito")
    if not archivo_principal_tarea and archivos_leidos_para_tarea:
        # Tomar el primero de la lista de contexto
        archivo_principal_tarea = archivos_leidos_para_tarea[0]
    # Fallback al contexto original de la misión
    elif not archivo_principal_tarea and archivos_contexto_mision_original:
        archivo_principal_tarea = archivos_contexto_mision_original[
            0] if archivos_contexto_mision_original else None

    if archivo_principal_tarea:
        path_principal_abs_sim = os.path.join(
            ruta_repo, archivo_principal_tarea)
        contenido_original_principal_sim = ""
        if os.path.exists(path_principal_abs_sim):
            with open(path_principal_abs_sim, "r", encoding="utf-8") as f_orig_sim:
                contenido_original_principal_sim = f_orig_sim.read()
        archivos_modificados_simulados[archivo_principal_tarea] = \
            f"// Tarea SIMULADA: '{tarea_actual_info.get('descripcion', 'N/A')}' ejecutada\n" + \
            f"// Timestamp: {datetime.now().isoformat()}\n" + \
            contenido_original_principal_sim
    else:
        # Si no se pudo determinar un archivo principal, crear uno nuevo como simulación
        nuevo_archivo_sim = f"simulacion_paso2_{nombre_rama_mision}_{int(time.time()*100) % 1000}.py"
        archivos_modificados_simulados[
            nuevo_archivo_sim] = f"// Generado por tarea SIMULADA '{tarea_actual_info.get('descripcion', 'N/A')}'\n// Timestamp: {datetime.now().isoformat()}"
        logging.info(
            f"{logPrefix} Simulación: Se creará archivo '{nuevo_archivo_sim}' ya que no se determinó archivo principal.")

    resultado_ejecucion_tarea_simulado = {
        "archivos_modificados": archivos_modificados_simulados,
        "advertencia_ejecucion": None,  # "Simulación: Todo OK"
        "tokens_consumidos_api": tokens_totales_estimados
    }
    resultado_ejecucion_tarea = resultado_ejecucion_tarea_simulado
    registrar_tokens_usados(resultado_ejecucion_tarea.get(
        "tokens_consumidos_api", tokens_totales_estimados))
    # ------ FIN PLACEHOLDER IA PASO 2 --------

    if not resultado_ejecucion_tarea or "archivos_modificados" not in resultado_ejecucion_tarea:
        logging.error(
            f"{logPrefix} IA no devolvió 'archivos_modificados' para la tarea o hubo error. Respuesta: {resultado_ejecucion_tarea}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(
                outcome=f"PASO2_ERROR_TAREA:{nombre_rama_mision}", decision_details=tarea_actual_info, error_message="IA no generó cambios válidos")
        ])
        return "error_en_tarea", contenido_mision_actual

    if resultado_ejecucion_tarea.get("advertencia_ejecucion"):
        logging.warning(
            f"{logPrefix} IA devolvió advertencia para la tarea: {resultado_ejecucion_tarea['advertencia_ejecucion']}")
        # Si hay advertencia Y no hay archivos modificados, podríamos tratarlo como un error o una tarea "saltada".
        if not resultado_ejecucion_tarea.get("archivos_modificados"):
            logging.info(
                f"{logPrefix} Tarea no resultó en cambios debido a advertencia de la IA. Marcando como completada y continuando.")
            # No aplicar cambios, pero sí marcar la tarea como completada para avanzar.
            contenido_mision_actualizado = marcar_tarea_como_completada(
                contenido_mision_actual, indice_tarea)  # NECESITA IMPLEMENTACIÓN ROBUSTA
            try:
                with open(os.path.join(ruta_repo, MISION_ORION_MD), 'w', encoding='utf-8') as f:
                    f.write(contenido_mision_actualizado)
                logging.info(
                    f"{logPrefix} {MISION_ORION_MD} actualizado (tarea saltada por advertencia).")
                if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Actualizar misión (tarea saltada): {tarea_actual_info.get('descripcion', 'Tarea')[:50]}", [MISION_ORION_MD]):
                    logging.error(
                        f"{logPrefix} No se pudo hacer commit de la actualización de {MISION_ORION_MD} (tarea saltada). Esto es un problema de estado.")
                    return "error_en_tarea", contenido_mision_actualizado
            except Exception as e:
                logging.error(
                    f"{logPrefix} Error actualizando {MISION_ORION_MD} localmente (tarea saltada): {e}")
                return "error_en_tarea", contenido_mision_actual

            manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                manejadorHistorial.formatearEntradaHistorial(
                    outcome=f"PASO2_TAREA_SALTADA:{nombre_rama_mision}", decision_details=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("advertencia_ejecucion"))
            ])
            # Verificar si quedan más tareas
            siguiente_tarea_info, _ = obtener_proxima_tarea_pendiente(
                contenido_mision_actualizado)
            if siguiente_tarea_info:
                return "tarea_ejecutada_continuar_mision", contenido_mision_actualizado
            else:  # Misión completada porque la última tarea fue saltada
                # No hay merge, la misión terminó "vacía"
                return "mision_completada_sin_merge", None

    # Aplicar los cambios si los hay
    if resultado_ejecucion_tarea.get("archivos_modificados"):
        exito_aplicar, msg_error_aplicar = aplicadorCambios.aplicarCambiosSobrescritura(
            resultado_ejecucion_tarea["archivos_modificados"],
            ruta_repo,
            accionOriginal=f"modificar_segun_tarea_mision:{nombre_rama_mision}",
            paramsOriginal=tarea_actual_info
        )

        if not exito_aplicar:
            logging.error(
                f"{logPrefix} Falló la aplicación de cambios para la tarea: {msg_error_aplicar}")
            manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                manejadorHistorial.formatearEntradaHistorial(
                    outcome=f"PASO2_APPLY_FAIL:{nombre_rama_mision}", decision_details=tarea_actual_info, result_details=resultado_ejecucion_tarea, error_message=msg_error_aplicar)
            ])
            manejadorGit.descartarCambiosLocales(ruta_repo)
            return "error_en_tarea", contenido_mision_actual

        commit_msg = f"Tarea completada (Misión {nombre_rama_mision}): {tarea_actual_info.get('descripcion', 'Tarea de misión')[:100]}"
        if not manejadorGit.hacerCommit(ruta_repo, commit_msg):
            logging.warning(
                f"{logPrefix} No se realizó commit para la tarea (quizás sin cambios efectivos o error en commit).")
            # Si no hubo commit, podría ser que la IA no hizo cambios reales o git falló.
            # Considerar si esto es un error o si se debe marcar la tarea como completada de todas formas.
            # Por ahora, se procede a marcarla, pero es un punto a revisar.
    else:
        logging.info(
            f"{logPrefix} La IA no especificó archivos modificados para la tarea. Asumiendo que no hubo cambios.")

    contenido_mision_actualizado = marcar_tarea_como_completada(
        contenido_mision_actual, indice_tarea)  # NECESITA IMPLEMENTACIÓN ROBUSTA
    try:
        with open(os.path.join(ruta_repo, MISION_ORION_MD), 'w', encoding='utf-8') as f:
            f.write(contenido_mision_actualizado)
        logging.info(
            f"{logPrefix} {MISION_ORION_MD} actualizado con tarea completada.")
    except Exception as e:
        logging.error(
            f"{logPrefix} Error actualizando {MISION_ORION_MD} localmente: {e}")
        return "error_en_tarea", contenido_mision_actual

    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Actualizar progreso misión: {tarea_actual_info.get('descripcion', 'Tarea')[:50]}", [MISION_ORION_MD]):
        logging.error(
            f"{logPrefix} No se pudo hacer commit de la actualización de {MISION_ORION_MD}.")
        return "error_en_tarea", contenido_mision_actualizado

    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(
            outcome=f"PASO2_TAREA_OK:{nombre_rama_mision}", decision_details=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("archivos_modificados"))
    ])

    siguiente_tarea_info, _ = obtener_proxima_tarea_pendiente(
        contenido_mision_actualizado)
    if siguiente_tarea_info:
        logging.info(
            f"{logPrefix} Quedan más tareas en la misión '{nombre_rama_mision}'. Continuando.")
        return "tarea_ejecutada_continuar_mision", contenido_mision_actualizado
    else:
        logging.info(
            f"{logPrefix} Todas las tareas de la misión '{nombre_rama_mision}' completadas.")
        # La lógica de merge se manejará en el bucle principal de `ejecutarCicloAdaptativo`
        # para mantener este paso enfocado en la tarea.
        # Se devuelve un estado que indica que la misión está lista para el merge.
        # Misión completada, contenido ya no es relevante aquí
        return "mision_completada_para_merge", None


def obtener_proxima_tarea_pendiente(contenido_mision):
    """
    Placeholder para parsear misionOrion.md y obtener la próxima tarea.
    Debe retornar: (dict_info_tarea, indice_linea_tarea) o (None, -1)
    El dict_info_tarea podría ser: {"descripcion": "...", "archivos_implicados": [...], ...}
    NECESITA IMPLEMENTACIÓN ROBUSTA.
    """
    if not contenido_mision:
        return None, -1
    lineas = contenido_mision.splitlines()
    tarea_descripcion = None
    archivos_implicados_tarea = []  # Futuro: parsear archivos específicos para la tarea

    for i, linea in enumerate(lineas):
        linea_strip = linea.strip()
        # Busca la primera tarea no completada
        if linea_strip.startswith("- [ ]"):
            tarea_descripcion = linea_strip[5:].strip()

            # Heurística para extraer archivo principal de la misión si no está en la tarea
            archivo_principal_mision = None
            for l_mision in lineas:  # Volver a iterar para buscar el archivo principal de la misión
                if l_mision.lower().startswith("**archivo principal a refactorizar:**"):
                    archivo_principal_mision = l_mision.split(":", 1)[
                        1].strip()
                    break

            # Aquí se podrían añadir más lógicas para parsear sub-items o detalles de la tarea
            # Por ejemplo, si una tarea dice: "- [ ] Modificar archivos: [fileA.py, fileB.py]"

            return {"descripcion": tarea_descripcion,
                    "archivo_principal_implicito": archivo_principal_mision,
                    "archivos_implicados": archivos_implicados_tarea  # Vacío por ahora
                    }, i
    return None, -1


def marcar_tarea_como_completada(contenido_mision, indice_linea_tarea):
    """
    Placeholder para marcar una tarea como completada en el string de misionOrion.md.
    Retorna: string contenido_mision_actualizado
    NECESITA IMPLEMENTACIÓN ROBUSTA.
    """
    if not contenido_mision:
        return ""
    lineas = contenido_mision.splitlines()
    if 0 <= indice_linea_tarea < len(lineas):
        if "- [ ]" in lineas[indice_linea_tarea]:
            lineas[indice_linea_tarea] = lineas[indice_linea_tarea].replace(
                "- [ ]", "- [x]", 1)
            logging.info(
                f"Marcada tarea en línea {indice_linea_tarea+1} como completada.")
        else:
            logging.warning(
                f"Línea {indice_linea_tarea+1} no parece ser una tarea pendiente (ya marcada o formato incorrecto): '{lineas[indice_linea_tarea]}'")
    else:
        logging.error(
            f"Índice de tarea {indice_linea_tarea} fuera de rango para marcar como completada.")
    return "\n".join(lineas)


# --- Función Principal del Ciclo Adaptativo (NUEVO) ---
def ejecutarCicloAdaptativo(api_provider: str, modo_test: bool):
    logPrefix = f"ejecutarCicloAdaptativo({api_provider.upper()}):"
    logging.info(
        f"{logPrefix} ===== INICIO CICLO ADAPTATIVO (Proveedor: {api_provider.upper()}) =====")

    registro_archivos_analizados = cargar_registro_archivos()

    if not _validarConfiguracionEsencial(api_provider):
        return False

    # Configurar genai una vez si es el proveedor
    if api_provider == 'google' and settings.GEMINIAPIKEY:
        if not analizadorCodigo.configurarGemini():  # Usar la función de configuración de analizadorCodigo
            logging.critical(
                f"{logPrefix} Falló la configuración de Google GenAI. Abortando.")
            return False

    # Preparar repositorio: clonar/actualizar y asegurar que estamos en la RAMATRABAJO
    # Esta RAMATRABAJO es la base desde donde se crean las ramas de misión.
    if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
        logging.error(
            f"{logPrefix} Falló la preparación inicial del repositorio en la rama '{settings.RAMATRABAJO}'.")
        return False
    logging.info(
        f"{logPrefix} Repositorio listo en la rama de trabajo base: '{settings.RAMATRABAJO}'.")

    estado_agente = "revisar_mision_local"
    mision_actual_contenido = None
    # Archivos definidos DENTRO de la misión para su ejecución
    archivos_contexto_mision_actual = None
    nombre_rama_mision_activa = None
    decision_paso1_1_actual = None
    # Archivo principal seleccionado en 1.1 para crear la misión
    archivo_para_mision_actual = None
    # Archivos de contexto seleccionados en 1.1 para CREAR la misión
    archivos_contexto_para_crear_mision = None

    max_ciclos_principales = getattr(
        settings, 'MAX_CICLOS_PRINCIPALES_AGENTE', 5)
    ciclos_ejecutados = 0

    while ciclos_ejecutados < max_ciclos_principales:
        ciclos_ejecutados += 1
        logging.info(f"\n{logPrefix} --- Iteración Principal Agente #{ciclos_ejecutados}/{max_ciclos_principales} | Estado: {estado_agente} | Misión Activa: {nombre_rama_mision_activa or 'Ninguna'} ---")

        if estado_agente == "revisar_mision_local":
            # Asegurarse de estar en la RAMATRABAJO (la principal) antes de buscar/crear misión.
            # Esto es crucial si una misión anterior falló o se completó.
            logging.info(
                f"{logPrefix} Estado: {estado_agente}. Asegurando estar en rama '{settings.RAMATRABAJO}'.")
            if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                logging.error(
                    f"{logPrefix} No se pudo volver a la rama de trabajo '{settings.RAMATRABAJO}'. Abortando ciclo.")
                break

            # Limpiar variables de misión anterior
            nombre_rama_mision_activa = None
            mision_actual_contenido = None
            archivos_contexto_mision_actual = None
            decision_paso1_1_actual = None
            archivo_para_mision_actual = None
            archivos_contexto_para_crear_mision = None

            # Limpiar misionOrion.md de la rama de trabajo si existe (podría ser de un merge anterior)
            path_mision_trabajo_abs = os.path.join(
                settings.RUTACLON, MISION_ORION_MD)
            if os.path.exists(path_mision_trabajo_abs):
                try:
                    os.remove(path_mision_trabajo_abs)
                    logging.info(
                        f"{logPrefix} Eliminado {MISION_ORION_MD} de la rama de trabajo '{settings.RAMATRABAJO}'.")
                    # Hacer commit de esta eliminación para mantener la rama limpia
                    if manejadorGit.hacerCommitEspecifico(settings.RUTACLON, f"Limpiar {MISION_ORION_MD} de {settings.RAMATRABAJO}", [MISION_ORION_MD]):
                        logging.info(
                            f"{logPrefix} Commit realizado para la eliminación de {MISION_ORION_MD} en '{settings.RAMATRABAJO}'.")
                    else:
                        logging.warning(
                            f"{logPrefix} No se pudo hacer commit de la eliminación de {MISION_ORION_MD} en '{settings.RAMATRABAJO}' (quizás no había cambios).")
                except Exception as e_clean_md:
                    logging.warning(
                        f"{logPrefix} No se pudo limpiar {MISION_ORION_MD} de '{settings.RAMATRABAJO}': {e_clean_md}")

            # Ahora sí, revisar si hay una misión en la rama actual (que debería ser RAMATRABAJO)
            resultado_paso0, data_mision, data_archivos_ctx, nombre_clave_detectado = paso0_revisar_mision_local(
                settings.RUTACLON)

            if resultado_paso0 == "procesar_mision_existente":
                mision_actual_contenido = data_mision
                archivos_contexto_mision_actual = data_archivos_ctx  # Para ejecutar
                nombre_rama_mision_activa = nombre_clave_detectado
                # No necesitamos cambiar de rama aquí, porque paso2 se encargará de ello.
                logging.info(
                    f"{logPrefix} Misión existente '{nombre_rama_mision_activa}' detectada en '{settings.RAMATRABAJO}'. Procediendo a ejecutar tarea.")
                estado_agente = "ejecutar_tarea_mision"
            elif resultado_paso0 == "crear_nueva_mision":
                logging.info(
                    f"{logPrefix} No hay misión activa en '{settings.RAMATRABAJO}'. Procediendo a seleccionar archivo para nueva misión.")
                estado_agente = "seleccion_archivo"
            else:
                logging.error(
                    f"{logPrefix} Resultado inesperado de paso0: {resultado_paso0}. Deteniendo.")
                break
            # No continuar el bucle while aquí, dejar que fluya al siguiente estado.

        elif estado_agente == "seleccion_archivo":
            logging.info(f"{logPrefix} Estado: {estado_agente}.")
            resultado_paso1_1, archivo_sel, ctx_sel_para_crear, decision_ia = paso1_1_seleccion_y_decision_inicial(
                settings.RUTACLON, api_provider, registro_archivos_analizados
            )
            if resultado_paso1_1 == "generar_mision":
                archivo_para_mision_actual = archivo_sel
                archivos_contexto_para_crear_mision = ctx_sel_para_crear
                decision_paso1_1_actual = decision_ia
                logging.info(
                    f"{logPrefix} Archivo '{archivo_sel}' seleccionado. Preparando para generar misión.")
                estado_agente = "generar_mision_md"
            elif resultado_paso1_1 == "reintentar_seleccion":
                logging.info(
                    f"{logPrefix} Paso 1.1 solicitó reintentar selección. Volviendo a revisar misión local para un ciclo limpio.")
                estado_agente = "revisar_mision_local"
            elif resultado_paso1_1 == "ciclo_terminado_sin_accion":
                logging.info(
                    f"{logPrefix} Paso 1.1 no encontró acción o archivo. Terminando ciclo del agente.")
                break
            else:
                logging.error(
                    f"{logPrefix} Resultado inesperado de paso1.1: {resultado_paso1_1}. Deteniendo.")
                break

        elif estado_agente == "generar_mision_md":
            logging.info(f"{logPrefix} Estado: {estado_agente}.")
            resultado_paso1_2, mision_gen_contenido, nombre_clave = paso1_2_generar_mision(
                settings.RUTACLON,
                archivo_para_mision_actual,
                archivos_contexto_para_crear_mision,
                decision_paso1_1_actual,
                api_provider
            )
            if resultado_paso1_2 == "mision_generada_ok":
                mision_actual_contenido = mision_gen_contenido
                nombre_rama_mision_activa = nombre_clave
                # Parsear la misión recién generada para obtener los archivos de contexto PARA EJECUTARLA
                _, archivos_contexto_mision_actual = parsear_mision_orion(
                    mision_actual_contenido)
                logging.info(
                    f"{logPrefix} Misión '{nombre_rama_mision_activa}' generada. Procediendo a ejecutar tarea.")
                estado_agente = "ejecutar_tarea_mision"
            elif resultado_paso1_2 == "error_generando_mision":
                logging.error(
                    f"{logPrefix} Error generando la misión. Volviendo a revisar misión local.")
                # La limpieza de la rama fallida (si se creó) ya se maneja en paso1_2_generar_mision.
                # Asegurarse de estar en RAMATRABAJO antes de reintentar.
                manejadorGit.cambiar_a_rama_existente(
                    settings.RUTACLON, settings.RAMATRABAJO)
                nombre_rama_mision_activa = None  # Limpiar
                estado_agente = "revisar_mision_local"
            else:
                logging.error(
                    f"{logPrefix} Resultado inesperado de paso1.2: {resultado_paso1_2}. Deteniendo.")
                break

        elif estado_agente == "ejecutar_tarea_mision":
            logging.info(f"{logPrefix} Estado: {estado_agente}.")
            if not nombre_rama_mision_activa or not mision_actual_contenido:
                logging.error(
                    f"{logPrefix} Se intentó ejecutar tarea sin nombre de rama de misión activa ('{nombre_rama_mision_activa}') o contenido de misión. Volviendo a revisar.")
                estado_agente = "revisar_mision_local"
                continue  # Importante para re-evaluar desde el inicio del bucle

            # Los archivos de contexto para ejecutar la tarea se obtienen de `archivos_contexto_mision_actual`
            # que fue parseado al cargar/generar la misión.
            if archivos_contexto_mision_actual is None:
                logging.warning(
                    f"{logPrefix} Archivos de contexto para ejecutar misión no estaban definidos, re-parseando misión.")
                _, archivos_contexto_mision_actual = parsear_mision_orion(
                    mision_actual_contenido)

            resultado_paso2, mision_actualizada_contenido = paso2_ejecutar_tarea_mision(
                settings.RUTACLON,
                nombre_rama_mision_activa,
                mision_actual_contenido,
                archivos_contexto_mision_actual,
                api_provider,
                modo_test
            )
            if resultado_paso2 == "tarea_ejecutada_continuar_mision":
                mision_actual_contenido = mision_actualizada_contenido
                # Los archivos de contexto generales de la misión no suelen cambiar entre tareas
                # a menos que una tarea los modifique explícitamente en misionOrion.md
                logging.info(
                    f"{logPrefix} Tarea ejecutada en '{nombre_rama_mision_activa}'. Quedan más tareas.")
                estado_agente = "ejecutar_tarea_mision"  # Seguir en la misma misión

            elif resultado_paso2 == "mision_completada_para_merge":
                logging.info(
                    f"{logPrefix} Misión '{nombre_rama_mision_activa}' completada y lista para merge.")
                # Proceder a mergear la rama de misión a RAMATRABAJO
                if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                    logging.error(
                        f"{logPrefix} No se pudo cambiar a '{settings.RAMATRABAJO}' para hacer merge de '{nombre_rama_mision_activa}'. Misión no mergeada.")
                # NECESITA IMPLEMENTACIÓN ROBUSTA
                elif manejadorGit.hacerMergeRama(settings.RUTACLON, nombre_rama_mision_activa, settings.RAMATRABAJO):
                    logging.info(
                        f"{logPrefix} Merge de '{nombre_rama_mision_activa}' a '{settings.RAMATRABAJO}' exitoso.")
                    if modo_test:
                        # Push de RAMATRABAJO
                        if manejadorGit.hacerPush(settings.RUTACLON, settings.RAMATRABAJO):
                            logging.info(
                                f"{logPrefix} Push de '{settings.RAMATRABAJO}' exitoso (modo test).")
                        else:
                            logging.error(
                                f"{logPrefix} Falló el push de '{settings.RAMATRABAJO}' (modo test).")

                    # Opcional: eliminar rama de misión local y remota
                    # if manejadorGit.eliminarRama(settings.RUTACLON, nombre_rama_mision_activa, local=True, remota=modo_test): # Solo remota si modo_test
                    #    logging.info(f"{logPrefix} Rama de misión '{nombre_rama_mision_activa}' eliminada.")
                else:
                    logging.error(
                        f"{logPrefix} Falló el merge de '{nombre_rama_mision_activa}' a '{settings.RAMATRABAJO}'. La rama de misión sigue existiendo con los cambios.")

                # Independientemente del merge, la misión terminó. Volver a revisar.
                nombre_rama_mision_activa = None
                mision_actual_contenido = None
                estado_agente = "revisar_mision_local"

            elif resultado_paso2 == "mision_completada_sin_merge":  # Caso donde no hubo tareas o se saltaron
                logging.info(
                    f"{logPrefix} Misión '{nombre_rama_mision_activa}' completada (sin tareas ejecutadas o saltadas, no requiere merge).")
                # Opcional: Limpiar rama de misión si no tuvo cambios significativos
                # if manejadorGit.eliminarRama(settings.RUTACLON, nombre_rama_mision_activa, local=True, remota=False):
                #    logging.info(f"{logPrefix} Rama de misión '{nombre_rama_mision_activa}' (sin merge) eliminada.")
                nombre_rama_mision_activa = None
                mision_actual_contenido = None
                estado_agente = "revisar_mision_local"

            elif resultado_paso2 == "error_en_tarea":
                logging.error(
                    f"{logPrefix} Error ejecutando tarea en misión '{nombre_rama_mision_activa}'. Volviendo a revisar misión local.")
                # La rama de misión y misionOrion.md quedan como están. La próxima revisión podría retomar la tarea.
                estado_agente = "revisar_mision_local"
            else:
                logging.error(
                    f"{logPrefix} Resultado inesperado de paso2: {resultado_paso2}. Deteniendo.")
                break

        else:
            logging.error(
                f"{logPrefix} Estado desconocido del agente: {estado_agente}. Deteniendo.")
            break

        # Pausa entre ciclos principales para evitar consumo rápido de API en bucles de error y dar tiempo a la ventana de tokens
        # Default 3 segundos
        delay_ciclo = getattr(settings, 'DELAY_ENTRE_CICLOS_AGENTE', 3)
        logging.debug(
            f"{logPrefix} Fin de iteración principal del agente. Pausando por {delay_ciclo}s.")
        time.sleep(delay_ciclo)

    guardar_registro_archivos(registro_archivos_analizados)
    logging.info(
        f"{logPrefix} ===== FIN CICLO ADAPTATIVO (Total iteraciones: {ciclos_ejecutados}) =====")
    return True


def parsear_nombre_clave_de_mision(contenido_mision):
    """
    Extrae el nombre clave de la misión del contenido de misionOrion.md.
    NECESITA IMPLEMENTACIÓN ROBUSTA.
    """
    if not contenido_mision:
        return None
    # Buscar una línea que empiece con "# Misión:" o "# Mision:" (case-insensitive para "Mision")
    # y extraer lo que sigue después de los dos puntos.
    for line in contenido_mision.splitlines():
        line_strip = line.strip()
        # Más específico
        if line_strip.startswith("# Misión:") or line_strip.startswith("# Mision:"):
            parts = line_strip.split(":", 1)
            if len(parts) > 1:
                nombre_clave = parts[1].strip()
                if nombre_clave:  # Asegurarse de que no esté vacío
                    return nombre_clave
    logging.warning(
        "No se pudo parsear el nombre clave de la misión desde el contenido.")
    return None


if __name__ == "__main__":
    configurarLogging()
    parser = argparse.ArgumentParser(
        description="Agente Adaptativo de Refactorización de Código con IA.",
        epilog="Ejecuta ciclos adaptativos de análisis, generación de misión y ejecución de tareas."
    )
    parser.add_argument(
        "--modo-test", action="store_true",
        help="Activa modo prueba: ej. intenta hacer push de ramas de misión completadas y ramas de trabajo."
    )
    parser.add_argument(
        "--openrouter", action="store_true",
        help="Utilizar la API de OpenRouter en lugar de Google Gemini."
    )
    args = parser.parse_args()

    codigo_salida = orchestrarEjecucionScript(args)

    logging.info(
        f"Script principal (adaptativo) finalizado con código de salida: {codigo_salida}")
    sys.exit(codigo_salida)
