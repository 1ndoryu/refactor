# principal.py

import logging
import sys
import os
import json
import argparse
import subprocess # No se usa directamente aquí, pero podría ser usado por sub-funciones
import time
import signal
from datetime import datetime, timedelta # timedelta para gestionar tokens
from config import settings
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios
from nucleo import manejadorHistorial

# --- Nuevas Constantes y Variables Globales ---
# Estas podrían ir en settings.py o definirse aquí si son específicas de la lógica principal
REGISTRO_ARCHIVOS_ANALIZADOS_PATH = os.path.join(settings.RUTA_BASE_PROYECTO, "registro_archivos_analizados.json")
MISION_ORION_MD = "misionOrion.md"
TOKEN_LIMIT_PER_MINUTE = getattr(settings, 'TOKEN_LIMIT_PER_MINUTE', 250000) # Definir en settings.py
token_usage_window = [] # Lista de tuplas (timestamp, tokens_usados) para la ventana de 60s

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
    logging.debug(f"{logPrefix} Tokens usados en los últimos 60s: {tokens_usados_en_ventana}. A usar: {tokens_a_usar_estimados}")

    if tokens_usados_en_ventana + tokens_a_usar_estimados > TOKEN_LIMIT_PER_MINUTE:
        segundos_a_esperar = 60 - (ahora - token_usage_window[0][0]).total_seconds() if token_usage_window else 60
        segundos_a_esperar = max(1, int(segundos_a_esperar) + 1) # Esperar al menos 1s más para estar seguros
        logging.info(f"{logPrefix} Límite de tokens ({TOKEN_LIMIT_PER_MINUTE}/min) excedería. "
                     f"Usados: {tokens_usados_en_ventana}. A usar: {tokens_a_usar_estimados}. "
                     f"Pausando por {segundos_a_esperar} segundos...")
        time.sleep(segundos_a_esperar)
        # Re-evaluar después de la pausa (recursivo o recalcular)
        return gestionar_limite_tokens(tokens_a_usar_estimados, proveedor_api) # Simple recursión para re-evaluar

    # Registrar el uso actual (se añade después de la llamada real para más precisión, pero aquí para la lógica)
    # En la práctica, añadirías los tokens DESPUÉS de la llamada exitosa a la API.
    # Por ahora, lo añadimos aquí asumiendo que la llamada se hará.
    # token_usage_window.append((ahora, tokens_a_usar_estimados)) # Esto se moverá a después de la llamada real a la API
    logging.info(f"{logPrefix} OK para proceder con {tokens_a_usar_estimados} tokens.")
    return True

def registrar_tokens_usados(tokens_usados: int):
    """Registra los tokens después de una llamada exitosa a la API."""
    global token_usage_window
    token_usage_window.append((datetime.now(), tokens_usados))
    logging.debug(f"Registrados {tokens_usados} tokens. Ventana actual: {sum(c for _,c in token_usage_window if datetime.now() - _ < timedelta(seconds=60))}")


# --- Funciones para el registro de archivos analizados (NUEVO) ---
def cargar_registro_archivos():
    if os.path.exists(REGISTRO_ARCHIVOS_ANALIZADOS_PATH):
        try:
            with open(REGISTRO_ARCHIVOS_ANALIZADOS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.error(f"Error decodificando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}. Se creará uno nuevo.")
        except Exception as e:
            logging.error(f"Error cargando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}: {e}. Se creará uno nuevo.")
    return {} # { "ruta_relativa_archivo": "timestamp_iso_ultima_seleccion" }

def guardar_registro_archivos(registro):
    try:
        with open(REGISTRO_ARCHIVOS_ANALIZADOS_PATH, 'w', encoding='utf-8') as f:
            json.dump(registro, f, indent=4)
    except Exception as e:
        logging.error(f"Error guardando {REGISTRO_ARCHIVOS_ANALIZADOS_PATH}: {e}")

def seleccionar_archivo_mas_antiguo(ruta_proyecto, registro_archivos):
    logPrefix = "seleccionar_archivo_mas_antiguo:"
    archivos_proyecto = analizadorCodigo.listarArchivosProyecto(
        ruta_proyecto,
        extensionesPermitidas=settings.EXTENSIONESPERMITIDAS,
        directoriosIgnorados=settings.DIRECTORIOS_IGNORADOS
    )
    if not archivos_proyecto:
        logging.warning(f"{logPrefix} No se encontraron archivos en el proyecto.")
        return None

    archivo_seleccionado = None
    timestamp_mas_antiguo = datetime.max.isoformat()

    archivos_proyecto_relativos = []
    for abs_path in archivos_proyecto:
        try:
            rel_path = os.path.relpath(abs_path, ruta_proyecto).replace(os.sep, '/')
            archivos_proyecto_relativos.append(rel_path)
        except ValueError:
            logging.warning(f"{logPrefix} No se pudo obtener ruta relativa para {abs_path} respecto a {ruta_proyecto}")
            continue


    for ruta_rel_archivo in archivos_proyecto_relativos:
        timestamp_ultima_seleccion = registro_archivos.get(ruta_rel_archivo)
        if timestamp_ultima_seleccion is None: # Nunca seleccionado
            archivo_seleccionado = ruta_rel_archivo
            logging.info(f"{logPrefix} Archivo '{archivo_seleccionado}' nunca antes seleccionado.")
            break
        if timestamp_ultima_seleccion < timestamp_mas_antiguo:
            timestamp_mas_antiguo = timestamp_ultima_seleccion
            archivo_seleccionado = ruta_rel_archivo

    if archivo_seleccionado:
        logging.info(f"{logPrefix} Archivo seleccionado: {archivo_seleccionado} (Última vez: {registro_archivos.get(archivo_seleccionado, 'Nunca')})")
        registro_archivos[archivo_seleccionado] = datetime.now().isoformat()
    else:
        logging.warning(f"{logPrefix} No se pudo seleccionar un archivo (todos ya procesados o lista vacía).")
        # Podrías resetear el registro aquí o tener otra lógica
        # Por ahora, si no hay, no hay.

    return archivo_seleccionado
# --- Fin funciones registro ---


def orchestrarEjecucionScript(args):
    api_provider_seleccionado = "openrouter" if args.openrouter else "google"
    logging.info(f"Iniciando lógica de orquestación ADAPTATIVA. Proveedor API: {api_provider_seleccionado.upper()}. Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    if api_provider_seleccionado == 'google' and not settings.GEMINIAPIKEY:
        logging.critical("Error: Google Gemini seleccionado pero GEMINI_API_KEY no configurada. Abortando.")
        return 2
    elif api_provider_seleccionado == 'openrouter' and not settings.OPENROUTER_API_KEY:
        logging.critical("Error: OpenRouter seleccionado pero OPENROUTER_API_KEY no configurada. Abortando.")
        return 2

    if hasattr(signal, 'SIGALRM'):
        logging.info(f"Configurando timeout de ejecución a {settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS} segundos.")
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS)
    else:
        logging.warning("signal.alarm no disponible. Timeout general no activo.")

    exit_code = 1
    try:
        # Llamamos a la nueva función principal del ciclo adaptativo
        ciclo_exitoso_general = ejecutarCicloAdaptativo(api_provider_seleccionado, args.modo_test)

        if ciclo_exitoso_general: # El significado de "exitoso" aquí es que el ciclo terminó limpiamente, no necesariamente que hizo un commit.
            logging.info("Ciclo adaptativo completado.")
            exit_code = 0 # Consideramos un ciclo completado como éxito 0
        else:
            logging.warning("Ciclo adaptativo finalizó con problemas o interrupciones. Ver logs.")
            exit_code = 1

    except TimeoutException:
        logging.critical(f"TIMEOUT: Script terminado por exceder límite de {settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS}s.")
        # Guardar estado de misión si es posible
        exit_code = 124
    except Exception as e:
        logging.critical(f"Error fatal no manejado en orquestación: {e}", exc_info=True)
        # Guardar estado de misión si es posible
        exit_code = 2
    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        guardar_registro_archivos(cargar_registro_archivos()) # Asegurar que se guarde el registro al final
    return exit_code


def _validarConfiguracionEsencial(api_provider: str) -> bool:
    # (Sin cambios respecto a tu versión original, pero asegurar que settings.REPOSITORIOURL exista)
    logPrefix = f"_validarConfiguracionEsencial({api_provider.upper()}):"
    configuracion_ok = False
    if api_provider == 'google':
        if settings.GEMINIAPIKEY and settings.REPOSITORIOURL:
            configuracion_ok = True
        else:
            logging.critical(
                f"{logPrefix} Configuración Google Gemini faltante (GEMINIAPIKEY o REPOSITORIOURL). Abortando.")
    elif api_provider == 'openrouter':
        if settings.OPENROUTER_API_KEY and settings.REPOSITORIOURL:
            configuracion_ok = True
        else:
            logging.critical(
                f"{logPrefix} Configuración OpenRouter faltante (OPENROUTER_API_KEY o REPOSITORIOURL). Abortando.")
    else:
        logging.critical(
            f"{logPrefix} Proveedor API desconocido: '{api_provider}'. Abortando.")
        return False

    if not configuracion_ok:
        logging.critical(
            f"{logPrefix} Configuración esencial faltante para proveedor '{api_provider}' o REPOSITORIOURL. Abortando.")
        return False

    logging.info(
        f"{logPrefix} Configuración esencial validada para proveedor '{api_provider}'.")
    return True


def _timeout_handler(signum, frame):
    logging.error("¡Tiempo límite de ejecución alcanzado!")
    raise TimeoutException("El script excedió el tiempo máximo de ejecución.")


def configurarLogging():
    # (Sin cambios respecto a tu versión original)
    log_raiz = logging.getLogger()
    if log_raiz.handlers: # Evitar duplicar handlers si se llama múltiples veces
        return
    nivelLog = logging.INFO # O DEBUG para más detalle
    formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'
    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    log_raiz.addHandler(consolaHandler)
    try:
        rutaLogArchivo = os.path.join(settings.RUTA_BASE_PROYECTO, "refactor_adaptativo.log") # Nuevo nombre de log
        os.makedirs(os.path.dirname(rutaLogArchivo), exist_ok=True)
        archivoHandler = logging.FileHandler(rutaLogArchivo, encoding='utf-8')
        archivoHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
        log_raiz.addHandler(archivoHandler)
    except Exception as e:
        log_raiz.error(f"configurarLogging: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}")
    log_raiz.setLevel(nivelLog)
    logging.info("="*50)
    logging.info("configurarLogging: Sistema de logging configurado para modo adaptativo.")
    logging.info(f"configurarLogging: Nivel de log: {logging.getLevelName(log_raiz.level)}")

# --- Funciones específicas para los nuevos pasos ---

def paso0_revisar_mision_local(ruta_repo):
    """
    Paso 0: Revisa si existe misionOrion.md y si tiene tareas pendientes.
    Retorna: (estado, contenido_mision, lista_archivos_contexto_mision)
             estado: "procesar_mision_existente", "crear_nueva_mision"
    """
    logPrefix = "paso0_revisar_mision_local:"
    ruta_mision_orion = os.path.join(ruta_repo, MISION_ORION_MD)
    
    # Importante: Antes de leer, asegurar que estamos en la rama correcta o
    # que misionOrion.md no está sujeto a cambios de rama si no se ha creado una misión aún.
    # Por ahora, asumimos que si existe, es relevante.
    # Se podría añadir lógica para verificar si estamos en una rama de misión.

    if os.path.exists(ruta_mision_orion):
        logging.info(f"{logPrefix} Se encontró {MISION_ORION_MD}.")
        try:
            with open(ruta_mision_orion, 'r', encoding='utf-8') as f:
                contenido_mision = f.read()
            
            # TODO: Implementar parseo de misionOrion.md para ver si hay tareas pendientes
            # y para extraer la lista de archivos de contexto.
            # Por ahora, un placeholder:
            hay_tareas_pendientes, archivos_contexto_mision = parsear_mision_orion(contenido_mision)

            if hay_tareas_pendientes:
                logging.info(f"{logPrefix} Misión con tareas pendientes. Pasando a Paso 2.")
                return "procesar_mision_existente", contenido_mision, archivos_contexto_mision
            else:
                logging.info(f"{logPrefix} Misión sin tareas pendientes o completada. Se procederá a Paso 1.1.")
                # Aquí podríamos querer eliminar o archivar el misionOrion.md completado.
                # Por ahora, simplemente se ignora y se crea una nueva.
                return "crear_nueva_mision", None, None
        except Exception as e:
            logging.error(f"{logPrefix} Error leyendo o parseando {MISION_ORION_MD}: {e}. Se intentará crear una nueva.")
            return "crear_nueva_mision", None, None
    else:
        logging.info(f"{logPrefix} No se encontró {MISION_ORION_MD}. Se procederá a Paso 1.1.")
        return "crear_nueva_mision", None, None

def parsear_mision_orion(contenido_mision: str):
    """
    Placeholder para parsear misionOrion.md.
    Debe retornar: (bool_hay_tareas_pendientes, lista_archivos_contexto)
    """
    # Ejemplo muy básico:
    # Asumir que las tareas están marcadas con "[ ]" y completadas con "[x]"
    # Asumir que los archivos de contexto están en una sección específica.
    # ESTO NECESITA UNA IMPLEMENTACIÓN ROBUSTA.
    if not contenido_mision:
        return False, []
        
    tareas_pendientes = "[ ]" in contenido_mision 
    archivos_contexto = []
    try:
        # Ejemplo: buscar una línea como "Archivos de Contexto: archivo1.py, archivo2.js"
        for line in contenido_mision.splitlines():
            if line.lower().startswith("archivos de contexto:"):
                archivos_str = line.split(":", 1)[1].strip()
                if archivos_str:
                    archivos_contexto = [f.strip() for f in archivos_str.split(',')]
                break
    except Exception as e:
        logging.error(f"Error parseando archivos de contexto de misión: {e}")

    return tareas_pendientes, archivos_contexto


def paso1_1_seleccion_y_decision_inicial(ruta_repo, api_provider, registro_archivos):
    """
    Paso 1.1: Selecciona archivo, IA decide si refactorizar y qué contexto necesita.
    Retorna: (accion, archivo_para_mision, archivos_contexto_para_mision, decision_IA_paso1_1)
             accion: "generar_mision", "reintentar_seleccion"
    """
    logPrefix = "paso1_1_seleccion_y_decision_inicial:"
    archivo_seleccionado_rel = seleccionar_archivo_mas_antiguo(ruta_repo, registro_archivos)
    guardar_registro_archivos(registro_archivos) # Guardar el timestamp actualizado

    if not archivo_seleccionado_rel:
        logging.warning(f"{logPrefix} No se pudo seleccionar ningún archivo. Terminando ciclo de creación de misión.")
        return "ciclo_terminado_sin_accion", None, None, None

    ruta_archivo_seleccionado_abs = os.path.join(ruta_repo, archivo_seleccionado_rel)
    if not os.path.exists(ruta_archivo_seleccionado_abs):
        logging.error(f"{logPrefix} Archivo seleccionado {archivo_seleccionado_rel} no existe en {ruta_archivo_seleccionado_abs}. Reintentando selección.")
        # Marcar como "no encontrado" para evitar seleccionarlo de nuevo inmediatamente
        registro_archivos[archivo_seleccionado_rel] = datetime.now().isoformat() + "_NOT_FOUND"
        guardar_registro_archivos(registro_archivos)
        return "reintentar_seleccion", None, None, None

    # Obtener estructura del proyecto
    estructura_proyecto = analizadorCodigo.generarEstructuraDirectorio(
        ruta_repo,
        directorios_ignorados=settings.DIRECTORIOS_IGNORADOS,
        max_depth=5, # Limitar profundidad para no consumir demasiados tokens
        incluir_archivos=True
    )

    # Leer contenido del archivo seleccionado para la IA
    # Usamos leerArchivos para obtener también el conteo de tokens.
    # leerArchivos espera una lista de rutas absolutas.
    resultado_lectura = analizadorCodigo.leerArchivos([ruta_archivo_seleccionado_abs], ruta_repo, api_provider=api_provider)
    contenido_archivo_seleccionado = resultado_lectura['contenido']
    tokens_contenido_archivo = resultado_lectura['tokens']
    tokens_estructura = 0 # Estimar tokens para la estructura (requiere contarla como texto)
    
    # Placeholder para la llamada a la IA de este paso
    # Debes crear una nueva función en analizadorCodigo.py para esto
    # ej: solicitar_evaluacion_archivo(contenido_archivo, estructura_proyecto, api_provider)
    # Esta función devolverá: { "necesita_refactor": bool, "necesita_contexto_adicional": bool, "archivos_contexto_sugeridos": ["ruta1", "ruta2"], "razonamiento": "..."}

    # Estimar tokens para el prompt de la IA + contenido del archivo + estructura
    # Esto es una estimación MUY burda, necesitas una mejor en analizadorCodigo.py
    tokens_prompt_paso1_1 = 500 # Estimación del prompt en sí
    if api_provider == 'google' and estructura_proyecto:
        try:
            model_struct = genai.GenerativeModel(settings.MODELO_GOOGLE_GEMINI) # Asume que ya está configurado
            tokens_estructura = model_struct.count_tokens(estructura_proyecto).total_tokens
        except Exception as e_count:
            logging.warning(f"No se pudo contar tokens para estructura proyecto: {e_count}")
            tokens_estructura = len(estructura_proyecto) // 4 # Aproximación muy general

    tokens_totales_estimados = tokens_prompt_paso1_1 + tokens_contenido_archivo + tokens_estructura
    
    gestionar_limite_tokens(tokens_totales_estimados, api_provider) # Pausa si es necesario

    # --- Llamada Real a la IA ---
    # decision_IA_paso1_1 = analizadorCodigo.solicitar_evaluacion_archivo(contenido_archivo_seleccionado, estructura_proyecto, api_provider)
    # registrar_tokens_usados(tokens_reales_consumidos_por_api) # Tokens reales consumidos
    
    # ------ INICIO PLACEHOLDER IA PASO 1.1 ------
    # Simulación de la respuesta de la IA para probar el flujo:
    logging.warning(f"{logPrefix} USANDO PLACEHOLDER para decisión IA Paso 1.1")
    time.sleep(1) # Simular llamada API
    decision_IA_paso1_1_simulada = {
        "necesita_refactor": True, # random.choice([True, False]),
        "necesita_contexto_adicional": True, # random.choice([True, False]) if necesita_refactor else False,
        "archivos_contexto_sugeridos": ["nucleo/analizadorCodigo.py", "readme.md"] if True else [], # Placeholder
        "razonamiento": "El archivo parece complejo y podría beneficiarse de refactorización. Sugiero revisar archivos relacionados para contexto.",
        "tokens_consumidos_estimados": tokens_totales_estimados # Para log
    }
    decision_IA_paso1_1 = decision_IA_paso1_1_simulada
    registrar_tokens_usados(tokens_totales_estimados) # Simular que se usaron estos tokens
    # ------ FIN PLACEHOLDER IA PASO 1.1 --------

    if not decision_IA_paso1_1 or not decision_IA_paso1_1.get("necesita_refactor"):
        logging.info(f"{logPrefix} IA decidió que '{archivo_seleccionado_rel}' no necesita refactor o hubo error. Razón: {decision_IA_paso1_1.get('razonamiento', 'N/A')}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"[PASO1.1_NO_REFACTOR]", decision=decision_IA_paso1_1)
        ])
        return "reintentar_seleccion", None, None, None # Buscar otro archivo

    logging.info(f"{logPrefix} IA decidió que '{archivo_seleccionado_rel}' SÍ necesita refactor.")
    archivos_contexto_sugeridos = decision_IA_paso1_1.get("archivos_contexto_sugeridos", [])
    
    # Validar que los archivos de contexto sugeridos existan (opcional pero bueno)
    archivos_contexto_validados = []
    for ctx_file_rel in archivos_contexto_sugeridos:
        ctx_file_abs = os.path.join(ruta_repo, ctx_file_rel)
        if os.path.exists(ctx_file_abs) and os.path.isfile(ctx_file_abs):
            archivos_contexto_validados.append(ctx_file_rel)
        else:
            logging.warning(f"{logPrefix} Archivo de contexto sugerido '{ctx_file_rel}' no existe o no es un archivo. Descartado.")
    
    return "generar_mision", archivo_seleccionado_rel, archivos_contexto_validados, decision_IA_paso1_1


def paso1_2_generar_mision(ruta_repo, archivo_a_refactorizar_rel, archivos_contexto_rel, decision_paso1_1, api_provider):
    """
    Paso 1.2: IA genera misionOrion.md.
    Retorna: (estado, contenido_mision_generada, nombre_clave_mision)
             estado: "mision_generada_ok", "error_generando_mision"
    """
    logPrefix = "paso1_2_generar_mision:"
    logging.info(f"{logPrefix} Generando misión para: {archivo_a_refactorizar_rel} con contexto: {archivos_contexto_rel}")

    # Construir el contexto completo para la IA:
    # Contenido del archivo a refactorizar + contenido de los archivos de contexto.
    todos_los_archivos_para_leer_abs = [os.path.join(ruta_repo, archivo_a_refactorizar_rel)]
    for f_rel in archivos_contexto_rel:
        todos_los_archivos_para_leer_abs.append(os.path.join(ruta_repo, f_rel))
    
    resultado_lectura = analizadorCodigo.leerArchivos(todos_los_archivos_para_leer_abs, ruta_repo, api_provider=api_provider)
    contexto_completo_para_mision = resultado_lectura['contenido']
    tokens_contexto_mision = resultado_lectura['tokens']

    # Estimar tokens para el prompt de la IA de este paso
    tokens_prompt_paso1_2 = 700 # Estimación
    tokens_totales_estimados = tokens_prompt_paso1_2 + tokens_contexto_mision
    
    gestionar_limite_tokens(tokens_totales_estimados, api_provider)

    # --- Llamada Real a la IA ---
    # contenido_mision_generado_dict = analizadorCodigo.generar_contenido_mision_orion(
    #     archivo_a_refactorizar_rel,
    #     contexto_completo_para_mision,
    #     decision_paso1_1.get("razonamiento"), # Pasar el razonamiento del paso anterior como guía
    #     api_provider
    # )
    # Esta función debería retornar un dict como:
    # { "nombre_clave_mision": "RefactorizarLoginUI", "contenido_markdown_mision": "...", "tokens_consumidos_estimados": ... }
    # registrar_tokens_usados(tokens_reales_api)
    
    # ------ INICIO PLACEHOLDER IA PASO 1.2 ------
    logging.warning(f"{logPrefix} USANDO PLACEHOLDER para generación de misión Paso 1.2")
    time.sleep(1)
    nombre_clave_simulado = f"mision_Refactor_{archivo_a_refactorizar_rel.split('/')[-1].split('.')[0]}_{int(time.time())%1000}"
    contenido_md_simulado = f"""# Misión: {nombre_clave_simulado}

**Archivo Principal a Refactorizar:** {archivo_a_refactorizar_rel}

**Archivos de Contexto:** {', '.join(archivos_contexto_rel) if archivos_contexto_rel else 'Ninguno'}

**Razón (de Paso 1.1):** {decision_paso1_1.get('razonamiento', 'N/A')}

## Tareas de Refactorización:
- [ ] Tarea 1: Analizar la función X en {archivo_a_refactorizar_rel} y proponer simplificación.
- [ ] Tarea 2: Verificar si la variable Y se usa correctamente.
- [ ] Tarea 3: Mover la función Z a un helper si aplica (considerar {archivos_contexto_rel[0] if archivos_contexto_rel else 'un_nuevo_helper.py'}).
"""
    contenido_mision_generado_dict_simulado = {
        "nombre_clave_mision": nombre_clave_simulado,
        "contenido_markdown_mision": contenido_md_simulado,
        "tokens_consumidos_estimados": tokens_totales_estimados
    }
    contenido_mision_generado_dict = contenido_mision_generado_dict_simulado
    registrar_tokens_usados(tokens_totales_estimados) # Simular
    # ------ FIN PLACEHOLDER IA PASO 1.2 --------

    if not contenido_mision_generado_dict or not contenido_mision_generado_dict.get("contenido_markdown_mision"):
        logging.error(f"{logPrefix} IA no generó contenido para la misión o hubo un error.")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"[PASO1.2_ERROR_GENERACION]", decision=decision_paso1_1, error_message="IA no generó misión")
        ])
        return "error_generando_mision", None, None

    nombre_clave_mision = contenido_mision_generado_dict["nombre_clave_mision"]
    contenido_markdown_mision = contenido_mision_generado_dict["contenido_markdown_mision"]

    # Crear rama para la misión
    rama_base = settings.RAMATRABAJO # O la rama principal del repo
    if not manejadorGit.crear_y_cambiar_a_rama(ruta_repo, nombre_clave_mision, rama_base): # Necesitas implementar esta función en manejadorGit
        logging.error(f"{logPrefix} No se pudo crear o cambiar a la rama de misión '{nombre_clave_mision}'.")
        return "error_generando_mision", None, None
    
    logging.info(f"{logPrefix} En la rama de misión: {nombre_clave_mision}")

    # Guardar misionOrion.md en la nueva rama
    ruta_mision_orion_abs = os.path.join(ruta_repo, MISION_ORION_MD)
    try:
        with open(ruta_mision_orion_abs, 'w', encoding='utf-8') as f:
            f.write(contenido_markdown_mision)
        logging.info(f"{logPrefix} {MISION_ORION_MD} guardado en {ruta_mision_orion_abs}")
    except Exception as e:
        logging.error(f"{logPrefix} Error guardando {MISION_ORION_MD}: {e}")
        # ¿Descartar rama? Por ahora, error.
        return "error_generando_mision", None, None
        
    # Hacer commit de misionOrion.md
    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Crear misión: {nombre_clave_mision}", [MISION_ORION_MD]): # Necesitas implementar
        logging.error(f"{logPrefix} No se pudo hacer commit de {MISION_ORION_MD} en la rama {nombre_clave_mision}.")
        return "error_generando_mision", None, None

    logging.info(f"{logPrefix} Misión '{nombre_clave_mision}' generada y guardada en su rama.")
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(outcome=f"[PASO1.2_MISION_GENERADA]", decision=nombre_clave_mision, result_details=MISION_ORION_MD)
    ])
    return "mision_generada_ok", contenido_markdown_mision, nombre_clave_mision


def paso2_ejecutar_tarea_mision(ruta_repo, nombre_rama_mision, contenido_mision_actual, archivos_contexto_mision, api_provider, modo_test):
    """
    Paso 2: Lee misionOrion.md, ejecuta UNA tarea.
    Retorna: (estado, contenido_mision_actualizado_o_none)
             estado: "tarea_ejecutada_continuar_mision", "mision_completada", "error_en_tarea"
    """
    logPrefix = f"paso2_ejecutar_tarea_mision (Rama: {nombre_rama_mision}):"
    logging.info(f"{logPrefix} Ejecutando tarea de la misión.")

    # Asegurarse de estar en la rama correcta
    if not manejadorGit.cambiar_a_rama_existente(ruta_repo, nombre_rama_mision): # Necesitas implementar
        logging.error(f"{logPrefix} No se pudo cambiar a la rama de misión '{nombre_rama_mision}'. Abortando tarea.")
        return "error_en_tarea", contenido_mision_actual
        
    # Parsear la misión para encontrar la PRÓXIMA tarea pendiente
    # Esta función debe ser más robusta que el placeholder
    tarea_actual_info, indice_tarea = obtener_proxima_tarea_pendiente(contenido_mision_actual)
    
    if not tarea_actual_info:
        logging.info(f"{logPrefix} No se encontraron tareas pendientes en la misión. Considerada completada.")
        return "mision_completada", contenido_mision_actual # Misión ya estaba completa

    logging.info(f"{logPrefix} Tarea a ejecutar: '{tarea_actual_info.get('descripcion', 'N/A')}'")

    # Leer archivos de contexto ESPECÍFICOS para esta tarea (podrían estar definidos en la tarea misma o ser los generales de la misión)
    # Por ahora, usamos los generales de la misión que vienen de paso0.
    contexto_para_tarea = ""
    tokens_contexto_tarea = 0
    if archivos_contexto_mision:
        archivos_abs_ctx_tarea = [os.path.join(ruta_repo, f_rel) for f_rel in archivos_contexto_mision]
        resultado_lectura = analizadorCodigo.leerArchivos(archivos_abs_ctx_tarea, ruta_repo, api_provider=api_provider)
        contexto_para_tarea = resultado_lectura['contenido']
        tokens_contexto_tarea = resultado_lectura['tokens']

    tokens_prompt_paso2 = 800 # Estimación
    tokens_totales_estimados = tokens_prompt_paso2 + tokens_contexto_tarea
    
    gestionar_limite_tokens(tokens_totales_estimados, api_provider)

    # --- Llamada Real a la IA ---
    # resultado_ejecucion_tarea = analizadorCodigo.ejecutar_tarea_especifica_mision(
    #     tarea_actual_info, # Dict con detalles de la tarea
    #     contexto_para_tarea,
    #     api_provider
    # )
    # Esta función debe retornar un dict similar al 'resultadoEjecucion' original, con 'archivos_modificados'
    # registrar_tokens_usados(tokens_reales_api)
    
    # ------ INICIO PLACEHOLDER IA PASO 2 ------
    logging.warning(f"{logPrefix} USANDO PLACEHOLDER para ejecución de tarea Paso 2")
    time.sleep(1)
    # Simular que la IA devuelve el contenido modificado para el archivo principal de la misión (si está en contexto)
    # y quizás crea un nuevo archivo.
    archivos_modificados_simulados = {}
    archivo_principal_mision = tarea_actual_info.get("archivo_principal_implicito", archivos_contexto_mision[0] if archivos_contexto_mision else "dummy.py")

    if archivo_principal_mision in archivos_contexto_mision:
        # Simular una modificación al archivo principal
        contenido_original_principal = ""
        path_principal_abs = os.path.join(ruta_repo, archivo_principal_mision)
        if os.path.exists(path_principal_abs):
            with open(path_principal_abs, "r", encoding="utf-8") as f_orig:
                contenido_original_principal = f_orig.read()
        archivos_modificados_simulados[archivo_principal_mision] = f"// Tarea '{tarea_actual_info.get('descripcion', 'N/A')}' ejecutada (simulación)\n" + contenido_original_principal
    else:
        # Simular creación de un archivo nuevo si el principal no estaba en contexto (raro pero posible)
        archivos_modificados_simulados[f"nuevo_archivo_paso2_{int(time.time())%100}.py"] = f"// Generado por tarea '{tarea_actual_info.get('descripcion', 'N/A')}' (simulación)"
    
    resultado_ejecucion_tarea_simulado = {
        "archivos_modificados": archivos_modificados_simulados,
        "tokens_consumidos_estimados": tokens_totales_estimados
        # Podría haber un campo "razonamiento_ejecucion"
    }
    resultado_ejecucion_tarea = resultado_ejecucion_tarea_simulado
    registrar_tokens_usados(tokens_totales_estimados)
    # ------ FIN PLACEHOLDER IA PASO 2 --------

    if not resultado_ejecucion_tarea or "archivos_modificados" not in resultado_ejecucion_tarea:
        logging.error(f"{logPrefix} IA no devolvió archivos modificados para la tarea o hubo error.")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"[PASO2_ERROR_TAREA]", decision=tarea_actual_info, error_message="IA no generó cambios")
        ])
        return "error_en_tarea", contenido_mision_actual

    # Aplicar los cambios
    # La acción original aquí es siempre una modificación/creación basada en la tarea.
    # No hay "eliminar_archivo" o "crear_directorio" como acciones de IA separadas en Paso 2,
    # esas serían parte de las instrucciones de una tarea.
    exito_aplicar, msg_error_aplicar = aplicadorCambios.aplicarCambiosSobrescritura(
        resultado_ejecucion_tarea["archivos_modificados"],
        ruta_repo,
        accionOriginal="modificar_segun_tarea_mision", # Un tipo genérico para este paso
        paramsOriginal=tarea_actual_info # Pasar la info de la tarea como params
    )

    if not exito_aplicar:
        logging.error(f"{logPrefix} Falló la aplicación de cambios para la tarea: {msg_error_aplicar}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"[PASO2_APPLY_FAIL]", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea, error_message=msg_error_aplicar)
        ])
        # ¿Descartar cambios de este intento de tarea?
        manejadorGit.descartarCambiosLocales(ruta_repo) # En la rama de misión
        return "error_en_tarea", contenido_mision_actual

    # Hacer commit de los cambios de la tarea
    commit_msg = f"Tarea completada: {tarea_actual_info.get('descripcion', 'Tarea de misión')}"
    if not manejadorGit.hacerCommit(ruta_repo, commit_msg): # `hacerCommit` debería hacer add -A
        logging.warning(f"{logPrefix} No se realizó commit para la tarea (quizás sin cambios efectivos o error).")
        # Si no hubo commit, podría ser que la IA no hizo cambios reales.
        # Podríamos no marcar la tarea como completada en este caso. Por ahora, la marcamos.
    
    # Marcar la tarea como completada en misionOrion.md
    contenido_mision_actualizado = marcar_tarea_como_completada(contenido_mision_actual, indice_tarea)
    try:
        with open(os.path.join(ruta_repo, MISION_ORION_MD), 'w', encoding='utf-8') as f:
            f.write(contenido_mision_actualizado)
        logging.info(f"{logPrefix} {MISION_ORION_MD} actualizado con tarea completada.")
    except Exception as e:
        logging.error(f"{logPrefix} Error actualizando {MISION_ORION_MD} localmente: {e}")
        # No se pudo guardar el progreso de la misión. Error grave.
        return "error_en_tarea", contenido_mision_actual
        
    # Hacer commit del misionOrion.md actualizado
    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Actualizar progreso misión: {nombre_rama_mision}", [MISION_ORION_MD]):
        logging.error(f"{logPrefix} No se pudo hacer commit de la actualización de {MISION_ORION_MD}.")
        # Esto también es un problema, el estado de la misión no se refleja en git.
        return "error_en_tarea", contenido_mision_actualizado # Devolver el contenido aunque no se commiteó

    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(outcome=f"[PASO2_TAREA_OK]", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("archivos_modificados"))
    ])

    # Verificar si quedan más tareas
    siguiente_tarea, _ = obtener_proxima_tarea_pendiente(contenido_mision_actualizado)
    if siguiente_tarea:
        logging.info(f"{logPrefix} Quedan más tareas en la misión. Continuando.")
        # Si es modo_test, hacer push de la rama de misión después de cada tarea? O al final?
        # Por ahora, push al final de la misión.
        return "tarea_ejecutada_continuar_mision", contenido_mision_actualizado
    else:
        logging.info(f"{logPrefix} Todas las tareas de la misión '{nombre_rama_mision}' completadas.")
        # Aquí se podría hacer el merge a la RAMATRABAJO y push si modo_test
        if manejadorGit.cambiar_a_rama_existente(ruta_repo, settings.RAMATRABAJO):
            if manejadorGit.hacerMergeRama(ruta_repo, nombre_rama_mision, settings.RAMATRABAJO): # Necesitas implementar
                logging.info(f"Merge de {nombre_rama_mision} a {settings.RAMATRABAJO} exitoso.")
                if modo_test:
                    if manejadorGit.hacerPush(ruta_repo, settings.RAMATRABAJO):
                        logging.info(f"Push de {settings.RAMATRABAJO} exitoso (modo test).")
                    else:
                        logging.error(f"Falló el push de {settings.RAMATRABAJO} (modo test).")
                
                # Opcional: eliminar rama de misión local y remota
                # manejadorGit.eliminarRama(ruta_repo, nombre_rama_mision, local=True, remota=True) # Necesitas implementar
            else:
                logging.error(f"Falló el merge de {nombre_rama_mision} a {settings.RAMATRABAJO}.")
                # La rama de misión sigue existiendo con los cambios.
        else:
            logging.error(f"No se pudo cambiar a {settings.RAMATRABAJO} para hacer merge.")

        return "mision_completada", None # None porque la misión ya no está activa.

def obtener_proxima_tarea_pendiente(contenido_mision):
    """
    Placeholder para parsear misionOrion.md y obtener la próxima tarea.
    Debe retornar: (dict_info_tarea, indice_tarea_en_lista_original) o (None, -1)
    El dict_info_tarea podría ser: {"descripcion": "...", "archivos_implicados": [...], ...}
    """
    # ESTO NECESITA UNA IMPLEMENTACIÓN ROBUSTA
    lineas = contenido_mision.splitlines()
    for i, linea in enumerate(lineas):
        linea_strip = linea.strip()
        if linea_strip.startswith("- [ ]"):
            descripcion_tarea = linea_strip[5:].strip()
            # Extraer más info si es posible (ej. de sub-items o formato especial)
            # También podrías necesitar el archivo principal al que se refiere la misión
            # para pasarlo implícitamente a la tarea.
            archivo_principal_implicito = None
            for l in lineas:
                if l.lower().startswith("**archivo principal a refactorizar:**"):
                    archivo_principal_implicito = l.split(":",1)[1].strip()
                    break
            return {"descripcion": descripcion_tarea, "archivo_principal_implicito": archivo_principal_implicito}, i
    return None, -1

def marcar_tarea_como_completada(contenido_mision, indice_linea_tarea):
    """
    Placeholder para marcar una tarea como completada en el string de misionOrion.md.
    Retorna: string contenido_mision_actualizado
    """
    # ESTO NECESITA UNA IMPLEMENTACIÓN ROBUSTA
    lineas = contenido_mision.splitlines()
    if 0 <= indice_linea_tarea < len(lineas):
        if "- [ ]" in lineas[indice_linea_tarea]:
            lineas[indice_linea_tarea] = lineas[indice_linea_tarea].replace("- [ ]", "- [x]", 1)
            logging.info(f"Marcada tarea en línea {indice_linea_tarea+1} como completada.")
        else:
            logging.warning(f"Línea {indice_linea_tarea+1} no parece ser una tarea pendiente: {lineas[indice_linea_tarea]}")
    else:
        logging.error(f"Índice de tarea {indice_linea_tarea} fuera de rango.")
    return "\n".join(lineas)


# --- Función Principal del Ciclo Adaptativo (NUEVO) ---
def ejecutarCicloAdaptativo(api_provider: str, modo_test: bool):
    logPrefix = f"ejecutarCicloAdaptativo({api_provider.upper()}):"
    logging.info(f"{logPrefix} ===== INICIO CICLO ADAPTATIVO (Proveedor: {api_provider.upper()}) =====")
    
    # Cargar estado persistente
    registro_archivos_analizados = cargar_registro_archivos()

    # Configuración inicial (Git, API keys)
    if not _validarConfiguracionEsencial(api_provider):
        return False # Falla crítica de configuración

    if api_provider == 'google' and settings.GEMINIAPIKEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINIAPIKEY)
            logging.info(f"{logPrefix} Google GenAI configurado globalmente para este ciclo.")
        except Exception as e_config_genai:
            logging.error(f"{logPrefix} Error al configurar google.generativeai: {e_config_genai}")
            # Podría ser fatal dependiendo de si es el único proveedor
            return False
            
    # Preparar repositorio (clonar/actualizar, asegurar rama de trabajo principal)
    # Asumimos que la rama de trabajo principal es donde empezamos a buscar/crear misiones.
    # Las misiones individuales se harán en sus propias ramas.
    if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
        logging.error(f"{logPrefix} Falló la preparación del repositorio en la rama de trabajo '{settings.RAMATRABAJO}'.")
        return False
    logging.info(f"{logPrefix} Repositorio listo en la rama de trabajo '{settings.RAMATRABAJO}'.")

    # --- Bucle Principal del Agente ---
    # Este bucle podría correr por un tiempo definido, o hasta que no haya más acciones, etc.
    # Por ahora, hacemos un número fijo de "intentos de misión" o un ciclo principal.
    # En una implementación real, esto sería un bucle `while True` con condiciones de salida.

    estado_agente = "revisar_mision_local" # Estado inicial
    mision_actual_contenido = None
    archivos_contexto_mision_actual = None
    nombre_rama_mision_activa = None
    decision_paso1_1_actual = None # Para pasar info de 1.1 a 1.2
    archivo_para_mision_actual = None

    # Control de bucle para evitar ejecuciones infinitas en desarrollo
    max_ciclos_principales = getattr(settings, 'MAX_CICLOS_PRINCIPALES_AGENTE', 5) 
    ciclos_ejecutados = 0

    while ciclos_ejecutados < max_ciclos_principales:
        ciclos_ejecutados += 1
        logging.info(f"\n{logPrefix} --- Inicio Iteración Principal del Agente #{ciclos_ejecutados}/{max_ciclos_principales} --- Estado: {estado_agente} ---")

        if estado_agente == "revisar_mision_local":
            # Asegurarse de estar en la rama de trabajo principal antes de buscar/crear misión
            if nombre_rama_mision_activa: # Si venimos de completar una misión
                if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                    logging.error(f"No se pudo volver a la rama {settings.RAMATRABAJO}. Abortando.")
                    break
                nombre_rama_mision_activa = None # Ya no hay misión activa
                # Limpiar misionOrion.md de la rama de trabajo (si se copió por error o quedó de un merge)
                path_mision_trabajo = os.path.join(settings.RUTACLON, MISION_ORION_MD)
                if os.path.exists(path_mision_trabajo):
                    try:
                        os.remove(path_mision_trabajo)
                        manejadorGit.hacerCommitEspecifico(settings.RUTACLON, "Limpiar misionOrion.md de rama de trabajo", [MISION_ORION_MD]) # Commit si se borró
                        logging.info(f"Limpiado {MISION_ORION_MD} de la rama de trabajo {settings.RAMATRABAJO}")
                    except Exception as e_clean_md:
                        logging.warning(f"No se pudo limpiar {MISION_ORION_MD} de {settings.RAMATRABAJO}: {e_clean_md}")


            resultado_paso0, data_mision, data_archivos_ctx = paso0_revisar_mision_local(settings.RUTACLON)
            if resultado_paso0 == "procesar_mision_existente":
                mision_actual_contenido = data_mision
                archivos_contexto_mision_actual = data_archivos_ctx
                # Necesitamos saber en qué rama está esta misión. El nombre de la rama es el nombre_clave de la misión.
                # Esto requiere parsear el nombre_clave del contenido_mision.
                nombre_rama_mision_activa = parsear_nombre_clave_de_mision(mision_actual_contenido) # Necesitas implementar
                if not nombre_rama_mision_activa:
                    logging.error("Misión existente encontrada pero no se pudo parsear el nombre clave (nombre de rama). Creando nueva misión.")
                    estado_agente = "seleccion_archivo"
                else:
                    estado_agente = "ejecutar_tarea_mision"
            elif resultado_paso0 == "crear_nueva_mision":
                estado_agente = "seleccion_archivo"
            else: # Error o estado inesperado
                logging.error(f"Resultado inesperado de paso0: {resultado_paso0}. Deteniendo.")
                break
            continue

        elif estado_agente == "seleccion_archivo": # Corresponde a Paso 1.1
            resultado_paso1_1, archivo_sel, ctx_sel, decision_ia = paso1_1_seleccion_y_decision_inicial(
                settings.RUTACLON, api_provider, registro_archivos_analizados
            )
            if resultado_paso1_1 == "generar_mision":
                archivo_para_mision_actual = archivo_sel
                archivos_contexto_mision_actual = ctx_sel # Contexto para GENERAR la misión
                decision_paso1_1_actual = decision_ia
                estado_agente = "generar_mision_md"
            elif resultado_paso1_1 == "reintentar_seleccion":
                logging.info("Reintentando selección de archivo en la próxima iteración.")
                # No cambiar estado, el bucle volverá aquí (o a revisar_mision_local si prefiere)
                # Para evitar bucles rápidos si siempre falla, añadimos un pequeño delay
                time.sleep(5) 
                estado_agente = "revisar_mision_local" # Volver al inicio del ciclo para un flujo limpio
            elif resultado_paso1_1 == "ciclo_terminado_sin_accion":
                logging.info("Paso 1.1 no encontró acción o archivo. Terminando ciclo del agente.")
                break # Termina el while
            else:
                logging.error(f"Resultado inesperado de paso1.1: {resultado_paso1_1}. Deteniendo.")
                break
            continue

        elif estado_agente == "generar_mision_md": # Corresponde a Paso 1.2
            resultado_paso1_2, mision_gen_contenido, nombre_clave = paso1_2_generar_mision(
                settings.RUTACLON,
                archivo_para_mision_actual,
                archivos_contexto_mision_actual, # Estos son los archivos que la IA en 1.1 dijo que eran útiles PARA CREAR LA MISIÓN
                decision_paso1_1_actual,
                api_provider
            )
            if resultado_paso1_2 == "mision_generada_ok":
                mision_actual_contenido = mision_gen_contenido
                nombre_rama_mision_activa = nombre_clave
                # Los archivos de contexto PARA EJECUTAR la misión vendrán del parseo de mision_actual_contenido
                _, archivos_contexto_mision_actual = parsear_mision_orion(mision_actual_contenido)
                estado_agente = "ejecutar_tarea_mision"
            elif resultado_paso1_2 == "error_generando_mision":
                logging.error("Error generando la misión. Volviendo a intentar seleccionar archivo.")
                # Limpiar la rama si se creó parcialmente?
                if nombre_clave and manejadorGit.existe_rama(settings.RUTACLON, nombre_clave): # Necesitas implementar existe_rama
                    logging.info(f"Intentando limpiar rama de misión fallida: {nombre_clave}")
                    if manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                        manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave, local=True, remota=False) # No hacer push de rama fallida
                nombre_rama_mision_activa = None
                estado_agente = "revisar_mision_local" # Empezar de nuevo
            else:
                logging.error(f"Resultado inesperado de paso1.2: {resultado_paso1_2}. Deteniendo.")
                break
            continue
            
        elif estado_agente == "ejecutar_tarea_mision": # Corresponde a Paso 2
            if not nombre_rama_mision_activa or not mision_actual_contenido:
                logging.error("Se intentó ejecutar tarea sin misión activa o contenido. Volviendo a revisar.")
                estado_agente = "revisar_mision_local"
                continue

            # Los archivos de contexto para ejecutar la tarea deberían haber sido parseados
            # al cargar o generar la misión.
            if archivos_contexto_mision_actual is None: # Si no se parsearon antes
                 _, archivos_contexto_mision_actual = parsear_mision_orion(mision_actual_contenido)


            resultado_paso2, mision_actualizada_contenido = paso2_ejecutar_tarea_mision(
                settings.RUTACLON,
                nombre_rama_mision_activa,
                mision_actual_contenido,
                archivos_contexto_mision_actual, # Archivos de contexto generales de la misión
                api_provider,
                modo_test
            )
            if resultado_paso2 == "tarea_ejecutada_continuar_mision":
                mision_actual_contenido = mision_actualizada_contenido
                # Los archivos de contexto generales de la misión no suelen cambiar entre tareas
                # a menos que una tarea los modifique explícitamente en misionOrion.md
                estado_agente = "ejecutar_tarea_mision" # Seguir en la misma misión
            elif resultado_paso2 == "mision_completada":
                logging.info(f"Misión {nombre_rama_mision_activa} completada.")
                # La lógica de merge y limpieza ya está en paso2_ejecutar_tarea_mision
                nombre_rama_mision_activa = None
                mision_actual_contenido = None
                archivos_contexto_mision_actual = None
                estado_agente = "revisar_mision_local" # Buscar nueva misión
            elif resultado_paso2 == "error_en_tarea":
                logging.error(f"Error ejecutando tarea en misión {nombre_rama_mision_activa}. Se intentará de nuevo desde la revisión de misión.")
                # Podríamos tener una lógica de reintentos para la MISMA tarea aquí.
                # Por ahora, volvemos a revisar la misión (podría retomar la misma tarea si no se marcó como completada).
                estado_agente = "revisar_mision_local" 
            else:
                logging.error(f"Resultado inesperado de paso2: {resultado_paso2}. Deteniendo.")
                break
            continue
        
        else:
            logging.error(f"Estado desconocido del agente: {estado_agente}. Deteniendo.")
            break
        
        # Pequeña pausa para evitar ciclos descontrolados y permitir que la ventana de tokens avance.
        logging.debug("Fin de iteración principal del agente, pequeña pausa.")
        time.sleep(getattr(settings, 'DELAY_ENTRE_CICLOS_AGENTE', 2))


    guardar_registro_archivos(registro_archivos_analizados) # Guardar estado al final
    logging.info(f"{logPrefix} ===== FIN CICLO ADAPTATIVO =====")
    return True # Indicar que el ciclo principal terminó (no necesariamente con éxito total de refactor)

def parsear_nombre_clave_de_mision(contenido_mision):
    """Extrae el nombre clave de la misión del contenido de misionOrion.md."""
    if not contenido_mision: return None
    for line in contenido_mision.splitlines():
        line_lower = line.lower()
        if line_lower.startswith("# misión:") or line_lower.startswith("# mision:"):
            return line.split(":",1)[1].strip()
    return None


if __name__ == "__main__":
    configurarLogging() # Configurar logging primero
    parser = argparse.ArgumentParser(
        description="Agente Adaptativo de Refactorización de Código con IA.",
        epilog="Ejecuta ciclos adaptativos de análisis, generación de misión y ejecución de tareas."
    )
    parser.add_argument(
        "--modo-test", action="store_true",
        help="Activa modo prueba: ej. intenta hacer push de ramas de misión completadas."
    )
    parser.add_argument(
        "--openrouter", action="store_true",
        help="Utilizar la API de OpenRouter en lugar de Google Gemini."
    )
    args = parser.parse_args()

    # --- Carga inicial del registro de archivos ---
    # registro_archivos_analizados se maneja ahora dentro de ejecutarCicloAdaptativo
    # y sus sub-funciones para que se actualice correctamente.

    codigo_salida = orchestrarEjecucionScript(args)

    logging.info(f"Script principal (adaptativo) finalizado con código de salida: {codigo_salida}")
    sys.exit(codigo_salida)