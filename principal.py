# principal.py

import logging
import sys
import os
import json
import argparse
import subprocess
import time
import signal
import re # Para parseo robusto de misionOrion.md
from datetime import datetime, timedelta
from config import settings
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios
from nucleo import manejadorHistorial

# --- Nuevas Constantes y Variables Globales ---
REGISTRO_ARCHIVOS_ANALIZADOS_PATH = os.path.join(
    settings.RUTA_BASE_PROYECTO, "registro_archivos_analizados.json")
MISION_ORION_MD = "misionOrion.md"
TOKEN_LIMIT_PER_MINUTE = getattr(
    settings, 'TOKEN_LIMIT_PER_MINUTE', 250000)
token_usage_window = []

# --- Archivo para persistir el estado de la misión activa ---
ACTIVE_MISSION_STATE_FILE = os.path.join(settings._CONFIG_DIR if hasattr(settings, '_CONFIG_DIR') else os.path.join(settings.RUTA_BASE_PROYECTO, 'config'), '.active_mission')

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
                    logging.info(f"{logPrefix} Misión activa encontrada: '{nombre_clave_mision}'")
                    return nombre_clave_mision
                else:
                    logging.warning(f"{logPrefix} Archivo de estado de misión vacío.")
                    os.remove(ACTIVE_MISSION_STATE_FILE) # Limpiar si está vacío
                    return None
        except Exception as e:
            logging.error(f"{logPrefix} Error cargando estado de misión activa: {e}", exc_info=True)
            return None
    logging.info(f"{logPrefix} No se encontró archivo de estado de misión activa.")
    return None

def guardar_estado_mision_activa(nombre_clave_mision: str):
    logPrefix = "guardar_estado_mision_activa:"
    try:
        os.makedirs(os.path.dirname(ACTIVE_MISSION_STATE_FILE), exist_ok=True)
        with open(ACTIVE_MISSION_STATE_FILE, 'w', encoding='utf-8') as f:
            f.write(nombre_clave_mision)
        logging.info(f"{logPrefix} Estado de misión activa '{nombre_clave_mision}' guardado.")
    except Exception as e:
        logging.error(f"{logPrefix} Error guardando estado de misión activa '{nombre_clave_mision}': {e}", exc_info=True)

def limpiar_estado_mision_activa():
    logPrefix = "limpiar_estado_mision_activa:"
    if os.path.exists(ACTIVE_MISSION_STATE_FILE):
        try:
            os.remove(ACTIVE_MISSION_STATE_FILE)
            logging.info(f"{logPrefix} Estado de misión activa limpiado.")
        except Exception as e:
            logging.error(f"{logPrefix} Error limpiando estado de misión activa: {e}", exc_info=True)
    else:
        logging.info(f"{logPrefix} No había estado de misión activa para limpiar.")

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
        # En lugar de un ciclo, ahora se ejecuta una "fase"
        fase_exitosa = ejecutarFaseDelAgente(
            api_provider_seleccionado, args.modo_test)
        if fase_exitosa: # fase_exitosa ahora significa que la fase se completó sin error crítico del agente
            logging.info("Fase del agente completada.")
            exit_code = 0 # El script sale con 0 si la fase fue OK, se reiniciará para la siguiente fase
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
        guardar_registro_archivos(cargar_registro_archivos()) # Guardar registro de archivos siempre
        logging.info("Registro de archivos analizados guardado al finalizar script.")
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


# --- Funciones de Parseo Robustas para misionOrion.md ---

def _parse_tarea_individual(tarea_buffer: dict):
    logPrefix = "_parse_tarea_individual:"
    if not tarea_buffer or not tarea_buffer.get("raw_lines"):
        return None
    
    lineas_tarea = tarea_buffer["raw_lines"]
    tarea_dict = {
        "id": None, "titulo": None, "estado": "PENDIENTE", 
        "descripcion": "", "archivos_implicados_especificos": [], "intentos": 0,
        "raw_lines": lineas_tarea,
        "line_start_index": tarea_buffer.get("line_start_index", -1),
        "line_end_index": tarea_buffer.get("line_start_index", -1) + len(lineas_tarea) -1 if tarea_buffer.get("line_start_index", -1) != -1 else -1
    }
    descripcion_parts = []
    in_descripcion = False

    match_titulo_linea = lineas_tarea[0] if lineas_tarea else ""
    # Regex para extraer ID y Título de la línea de encabezado de la tarea
    # Ejemplo: ### Tarea MI-ID-123: Implementar nueva funcionalidad
    match_titulo_encabezado = re.match(r"###\s*Tarea\s*([\w.-]+):\s*(.+)", match_titulo_linea, re.IGNORECASE) # ID puede tener guiones y puntos
    if match_titulo_encabezado:
        tarea_dict["id_titulo"] = match_titulo_encabezado.group(1).strip() # Guardar temporalmente el ID del título
        tarea_dict["titulo"] = match_titulo_encabezado.group(2).strip()
    else:
        logging.warning(f"{logPrefix} No se pudo parsear ID/Título del encabezado de la tarea: '{match_titulo_linea}'")

    id_del_campo_encontrado = None

    for linea_original_tarea in lineas_tarea[1:]: # Empezar desde la segunda línea para los campos
        linea_strip = linea_original_tarea.strip()
        
        # Regex para extraer el ID de un campo específico "- **ID:** MI-ID-CAMPO"
        match_id_campo_explicito = re.match(r"-\s*\*\*ID:\*\*\s*([\w.-]+)", linea_original_tarea, re.IGNORECASE)
        if match_id_campo_explicito: 
            id_del_campo_encontrado = match_id_campo_explicito.group(1).strip()
            in_descripcion = False # Salir del modo descripción si se encuentra otro campo
            continue # Procesar el resto de los campos

        match_estado = re.match(r"-\s*\*\*Estado:\*\*\s*(PENDIENTE|COMPLETADA|SALTADA|FALLIDA_TEMPORALMENTE)", linea_original_tarea, re.IGNORECASE)
        if match_estado: 
            tarea_dict["estado"] = match_estado.group(1).upper().strip()
            in_descripcion = False
            continue
        
        match_intentos = re.match(r"-\s*\*\*Intentos:\*\*\s*(\d+)", linea_original_tarea, re.IGNORECASE)
        if match_intentos: 
            tarea_dict["intentos"] = int(match_intentos.group(1).strip())
            in_descripcion = False
            continue

        match_aie = re.match(r"-\s*\*\*Archivos Implicados .*:\*\*\s*(.+)", linea_original_tarea, re.IGNORECASE)
        if match_aie:
            archivos_str = match_aie.group(1).strip()
            if archivos_str and archivos_str.lower() not in ["ninguno", "opcional:", "ninguno."]:
                tarea_dict["archivos_implicados_especificos"] = [a.strip() for a in archivos_str.split(',') if a.strip()]
            in_descripcion = False
            continue
            
        match_desc_start = re.match(r"-\s*\*\*Descripción:\*\*\s*(.*)", linea_original_tarea, re.IGNORECASE)
        if match_desc_start:
            in_descripcion = True
            desc_first_line = match_desc_start.group(1).strip()
            if desc_first_line: 
                descripcion_parts.append(desc_first_line)
            continue

        if in_descripcion and not re.match(r"-\s*\*\*\w+:\*\*", linea_original_tarea): # Si estamos en descripción y no es otro campo
             descripcion_parts.append(linea_original_tarea.strip()) # Mantener indentación original o .strip()? Por ahora .strip()

    # --- Lógica de asignación y validación de ID ---
    id_del_titulo = tarea_dict.pop("id_titulo", None) # Recuperar y quitar el id_titulo temporal

    if id_del_titulo and id_del_campo_encontrado:
        # Ambos IDs existen, deben coincidir
        if id_del_titulo == id_del_campo_encontrado:
            tarea_dict["id"] = id_del_titulo # o id_del_campo_encontrado, son iguales
            logging.debug(f"{logPrefix} ID del título y del campo coinciden: '{tarea_dict['id']}'.")
        else:
            # ¡DISCREPANCIA! -> Error de formato, más estricto.
            logging.error(f"{logPrefix} ¡DISCREPANCIA FATAL DE ID! ID en encabezado de tarea ('{id_del_titulo}') "
                          f"difiere de ID en campo '- **ID:**' ('{id_del_campo_encontrado}'). "
                          f"Formato de misión inválido para la tarea en líneas {tarea_dict['line_start_index']}-{tarea_dict['line_end_index']}. Tarea ignorada.")
            return None # No se parsea la tarea
    elif id_del_titulo:
        # Solo existe el ID del título
        tarea_dict["id"] = id_del_titulo
        logging.debug(f"{logPrefix} Usando ID del encabezado de tarea: '{id_del_titulo}'.")
    elif id_del_campo_encontrado:
        # Solo existe el ID del campo (el encabezado no tenía formato ID o no había encabezado de tarea)
        tarea_dict["id"] = id_del_campo_encontrado
        logging.debug(f"{logPrefix} Usando ID del campo '- **ID:**': '{id_del_campo_encontrado}'.")
    else:
        # No se encontró ID ni en título ni en campo
        logging.error(f"{logPrefix} Tarea parseada SIN ID. No se encontró ID en el encabezado (### Tarea ID: Título) ni en un campo '- **ID:** ID'. Líneas: {tarea_dict['raw_lines']}")
        return None

    tarea_dict["descripcion"] = "\n".join(descripcion_parts).strip()
    
    # Verificación final: ¿Tenemos un ID? (Ya debería estar cubierto por la lógica anterior)
    if not tarea_dict["id"]:
        logging.error(f"{logPrefix} Error Lógico: Tarea finalizada sin ID a pesar de las validaciones. Esto no debería ocurrir. Líneas: {tarea_dict['raw_lines']}")
        return None
        
    logging.debug(f"{logPrefix} Tarea parseada exitosamente. ID: '{tarea_dict['id']}', Título: '{tarea_dict['titulo']}', Estado: '{tarea_dict['estado']}'")
    return tarea_dict

def parsear_mision_orion(contenido_mision: str):
    logPrefix = "parsear_mision_orion:"
    if not contenido_mision: return None, [], False
    metadatos = {"nombre_clave": None, "archivo_principal": None, "archivos_contexto_generacion": [],
                 "archivos_contexto_ejecucion": [], "razon_paso1_1": None, "estado_general": "PENDIENTE"}
    tareas, hay_tareas_pendientes = [], False
    lineas = contenido_mision.splitlines()
    seccion_actual, tarea_actual_buffer = None, None

    try:
        for i, linea_orig in enumerate(lineas):
            linea = linea_orig.strip()
            if linea.startswith("# Misión:"): continue
            if linea.lower() == "**metadatos de la misión:**": seccion_actual = "metadatos"; continue
            elif linea.lower() == "## tareas de refactorización:":
                seccion_actual = "tareas"
                if tarea_actual_buffer: parsed = _parse_tarea_individual(tarea_actual_buffer); tarea_actual_buffer = None; (tareas.append(parsed) if parsed else None)
                continue
            if linea.startswith("---") and seccion_actual == "tareas":
                if tarea_actual_buffer: parsed = _parse_tarea_individual(tarea_actual_buffer); (tareas.append(parsed) if parsed else None)
                tarea_actual_buffer = {"raw_lines": [], "line_start_index": i + 1}; continue

            if seccion_actual == "metadatos":
                m_nk = re.match(r"-\s*\*\*Nombre Clave:\*\*\s*(.+)", linea_orig, re.I); m_ap = re.match(r"-\s*\*\*Archivo Principal:\*\*\s*(.+)", linea_orig, re.I)
                m_acg = re.match(r"-\s*\*\*Archivos de Contexto \(Generación\):\*\*\s*(.+)", linea_orig, re.I); m_ace = re.match(r"-\s*\*\*Archivos de Contexto \(Ejecución\):\*\*\s*(.+)", linea_orig, re.I)
                m_r11 = re.match(r"-\s*\*\*Razón \(Paso 1.1\):\*\*\s*(.+)", linea_orig, re.I); m_eg = re.match(r"-\s*\*\*Estado:\*\*\s*(PENDIENTE|EN_PROGRESO|COMPLETADA|FALLIDA)", linea_orig, re.I)
                if m_nk: metadatos["nombre_clave"] = m_nk.group(1).strip(); continue
                if m_ap: metadatos["archivo_principal"] = m_ap.group(1).strip(); continue
                if m_r11: metadatos["razon_paso1_1"] = m_r11.group(1).strip(); continue
                if m_eg: metadatos["estado_general"] = m_eg.group(1).upper().strip(); continue
                
                for m, key in [(m_acg, "archivos_contexto_generacion"), (m_ace, "archivos_contexto_ejecucion")]:
                    if m:
                        s = m.group(1).strip()
                        # Eliminar corchetes si están al principio y al final de la LISTA COMPLETA de archivos
                        if s.startswith('[') and s.endswith(']'):
                            s = s[1:-1].strip()
                        
                        rutas_finales = []
                        # Solo procesar si hay algo después de quitar corchetes de la lista y no es "ninguno"
                        if s and s.lower() not in ["ninguno", "ninguno."]:
                            rutas_individuales_str = s.split(',')
                            for ruta_str_orig in rutas_individuales_str:
                                ruta_procesada = ruta_str_orig.strip()

                                # 1. Eliminar completamente los caracteres '[' y ']' de la ruta.
                                #    Esto es más agresivo que solo al principio/final.
                                ruta_procesada = ruta_procesada.replace('[', '').replace(']', '')
                                
                                # 2. Eliminar barra inclinada inicial (federal o invertida) si existe 
                                #    DESPUÉS de quitar corchetes.
                                #    Esto previene rutas como '/app/file.py' o '\app\file.py' 
                                #    volviéndose absolutas erróneamente si se unen con os.path.join más tarde.
                                if ruta_procesada.startswith('/') or ruta_procesada.startswith('\\'):
                                    ruta_procesada = ruta_procesada[1:]
                                
                                # Strip final para quitar espacios que pudieron quedar después de reemplazos
                                ruta_procesada = ruta_procesada.strip() 

                                # Solo añadir si después de toda la limpieza, la ruta es válida (no vacía)
                                # y no es explícitamente "ninguno".
                                if ruta_procesada and ruta_procesada.lower() not in ["ninguno", "ninguno."]:
                                    rutas_finales.append(ruta_procesada)
                                elif ruta_procesada: # Log si se descarta algo que no era "ninguno" pero quedó vacío
                                    logging.debug(f"{logPrefix} Ruta individual '{ruta_str_orig}' descartada después de limpieza (quedó vacía pero no era 'ninguno').")

                        metadatos[key] = rutas_finales
                        continue
            elif seccion_actual == "tareas" and tarea_actual_buffer is not None: tarea_actual_buffer["raw_lines"].append(linea_orig)
        
        if tarea_actual_buffer: parsed = _parse_tarea_individual(tarea_actual_buffer); (tareas.append(parsed) if parsed else None)
        for t in tareas: 
            if t and t.get("estado", "").upper() == "PENDIENTE": hay_tareas_pendientes = True; break
        
        if not metadatos["nombre_clave"]:
            m_title = re.match(r"#\s*Misi[oó]n:\s*(.+)", lineas[0] if lineas else "", re.I)
            if m_title: metadatos["nombre_clave"] = m_title.group(1).strip(); logging.info(f"{logPrefix} Nombre Clave de fallback: {metadatos['nombre_clave']}")
            else: logging.error(f"{logPrefix} Error crítico: Nombre Clave no encontrado."); return None, [], False
        logging.info(f"{logPrefix} Misión parseada. Clave: {metadatos['nombre_clave']}. Tareas: {len(tareas)}. Pendientes: {hay_tareas_pendientes}.")
        return metadatos, tareas, hay_tareas_pendientes
    except Exception as e: logging.error(f"{logPrefix} Excepción: {e}", exc_info=True); return None, [], False

def parsear_nombre_clave_de_mision(contenido_mision: str):
    logPrefix = "parsear_nombre_clave_de_mision:"
    metadatos, _, _ = parsear_mision_orion(contenido_mision)
    if metadatos and metadatos.get("nombre_clave"): return metadatos["nombre_clave"]
    logging.warning(f"{logPrefix} No se pudo parsear nombre clave."); return None

def obtener_proxima_tarea_pendiente(contenido_mision_o_lista_tareas):
    logPrefix = "obtener_proxima_tarea_pendiente:"
    MAX_REINTENTOS_FALLA_TEMPORAL = 3  # Número máximo de reintentos para tareas fallidas temporalmente

    lista_tareas = []
    if isinstance(contenido_mision_o_lista_tareas, str):
        _, lista_tareas, _ = parsear_mision_orion(contenido_mision_o_lista_tareas)
    elif isinstance(contenido_mision_o_lista_tareas, list):
        lista_tareas = contenido_mision_o_lista_tareas
    else:
        logging.error(f"{logPrefix} Entrada inválida. Tipo: {type(contenido_mision_o_lista_tareas)}")
        return None, -1

    if lista_tareas is None:  # parsear_mision_orion puede devolver None para lista_tareas si hay error
        logging.error(f"{logPrefix} Lista de tareas es None (posiblemente por error de parseo previo).")
        return None, -1

    # Primera pasada: Buscar tareas FALLIDA_TEMPORALMENTE con reintentos pendientes
    for i, tarea in enumerate(lista_tareas):
        if isinstance(tarea, dict) and tarea.get("estado", "").upper() == "FALLIDA_TEMPORALMENTE":
            intentos_realizados = tarea.get("intentos", 0)
            if intentos_realizados < MAX_REINTENTOS_FALLA_TEMPORAL:
                logging.info(f"{logPrefix} Próxima tarea (REINTENTO): ID '{tarea.get('id', 'N/A')}' - Título: '{tarea.get('titulo', 'N/A')}' (Intentos: {intentos_realizados}/{MAX_REINTENTOS_FALLA_TEMPORAL})")
                return tarea, i
            else:
                logging.info(f"{logPrefix} Tarea FALLIDA_TEMPORALMENTE ID '{tarea.get('id', 'N/A')}' ha alcanzado el límite de reintentos ({intentos_realizados}/{MAX_REINTENTOS_FALLA_TEMPORAL}). Se omite.")

    # Segunda pasada: Buscar tareas PENDIENTE
    for i, tarea in enumerate(lista_tareas):
        if isinstance(tarea, dict) and tarea.get("estado", "").upper() == "PENDIENTE":
            logging.info(f"{logPrefix} Próxima tarea (PENDIENTE): ID '{tarea.get('id', 'N/A')}' - Título: '{tarea.get('titulo', 'N/A')}'")
            return tarea, i

    logging.info(f"{logPrefix} No hay más tareas elegibles (FALLIDA_TEMPORALMENTE con reintentos o PENDIENTE).")
    return None, -1

def marcar_tarea_como_completada(contenido_mision_md_original: str, id_tarea_a_marcar: str, nuevo_estado: str = "COMPLETADA", incrementar_intentos_si_fallida_temp: bool = False):
    logPrefix = "marcar_tarea_como_completada:"
    if not contenido_mision_md_original or not id_tarea_a_marcar:
        logging.error(f"{logPrefix} Faltan argumentos: contenido_mision_md_original o id_tarea_a_marcar.")
        return None
    
    nuevo_estado_valido = nuevo_estado.upper()
    estados_permitidos = ["COMPLETADA", "SALTADA", "PENDIENTE", "FALLIDA_TEMPORALMENTE", "FALLIDA_PERMANENTEMENTE"] # Añadido FALLIDA_PERMANENTEMENTE
    if nuevo_estado_valido not in estados_permitidos:
        logging.error(f"{logPrefix} Estado '{nuevo_estado}' no válido. Permitidos: {estados_permitidos}")
        return None
    
    _, tareas_originales, _ = parsear_mision_orion(contenido_mision_md_original)
    if not tareas_originales:
        logging.warning(f"{logPrefix} No se parsearon tareas del contenido original. Devolviendo original.")
        return contenido_mision_md_original # O None si es mejor un error duro
    
    lineas_originales = list(contenido_mision_md_original.splitlines())
    tarea_encontrada_y_modificada = False

    for tarea_dict in tareas_originales:
        if tarea_dict and tarea_dict.get("id") == id_tarea_a_marcar:
            line_start_abs = tarea_dict.get("line_start_index", -1) # Índice absoluto en lineas_originales
            # raw_lines son las líneas originales de la tarea, tal cual están en el MD
            raw_lines_tarea = tarea_dict.get("raw_lines", []) 
            if not (0 <= line_start_abs < len(lineas_originales)) or not raw_lines_tarea:
                logging.error(f"{logPrefix} Índices inválidos o raw_lines vacías para tarea ID '{id_tarea_a_marcar}'. Start: {line_start_abs}, Len Raw: {len(raw_lines_tarea)}")
                continue

            # --- Modificar Estado ---
            estado_line_idx_rel = -1 # Relativo al inicio de raw_lines_tarea
            for idx_rel, linea_tarea_raw in enumerate(raw_lines_tarea):
                if re.match(r"-\s*\*\*Estado:\*\*", linea_tarea_raw, re.I):
                    estado_line_idx_rel = idx_rel
                    break
            
            if estado_line_idx_rel != -1:
                estado_line_idx_abs = line_start_abs + estado_line_idx_rel
                linea_estado_antigua = lineas_originales[estado_line_idx_abs]
                match_prefijo = re.match(r"(.*-\s*\*\*Estado:\*\*\s*)(?:[A-Z_]+)(.*)", linea_estado_antigua, re.IGNORECASE)
                if match_prefijo:
                    prefijo_estado = match_prefijo.group(1)
                    sufijo_estado = match_prefijo.group(2)
                    lineas_originales[estado_line_idx_abs] = f"{prefijo_estado}{nuevo_estado_valido}{sufijo_estado}"
                    logging.info(f"{logPrefix} Estado de Tarea ID '{id_tarea_a_marcar}' actualizado a '{nuevo_estado_valido}' en línea {estado_line_idx_abs + 1}.")
                    tarea_encontrada_y_modificada = True # Marcar que al menos el estado se intentó/modificó
                else:
                    logging.warning(f"{logPrefix} No se pudo parsear prefijo/sufijo de estado para Tarea ID '{id_tarea_a_marcar}'. Reemplazo simple.")
                    lineas_originales[estado_line_idx_abs] = re.sub(r"(PENDIENTE|COMPLETADA|SALTADA|FALLIDA_TEMPORALMENTE|FALLIDA_PERMANENTEMENTE)", nuevo_estado_valido, linea_estado_antigua, flags=re.IGNORECASE)
                    tarea_encontrada_y_modificada = True
            else:
                logging.warning(f"{logPrefix} No se encontró línea de 'Estado:' para tarea ID '{id_tarea_a_marcar}'. Estado no modificado.")

            # --- Modificar Intentos si aplica ---
            if incrementar_intentos_si_fallida_temp and nuevo_estado_valido == "FALLIDA_TEMPORALMENTE":
                intentos_line_idx_rel = -1
                intentos_actuales = tarea_dict.get("intentos", 0) # Tomar de la tarea parseada

                for idx_rel, linea_tarea_raw in enumerate(raw_lines_tarea):
                    if re.match(r"-\s*\*\*Intentos:\*\*", linea_tarea_raw, re.I):
                        intentos_line_idx_rel = idx_rel
                        break
                
                nuevos_intentos = intentos_actuales + 1
                if intentos_line_idx_rel != -1:
                    intentos_line_idx_abs = line_start_abs + intentos_line_idx_rel
                    linea_intentos_antigua = lineas_originales[intentos_line_idx_abs]
                    match_prefijo_intentos = re.match(r"(.*-\s*\*\*Intentos:\*\*\s*)(\d+)(.*)", linea_intentos_antigua, re.IGNORECASE)
                    if match_prefijo_intentos:
                        prefijo_intentos = match_prefijo_intentos.group(1)
                        sufijo_intentos = match_prefijo_intentos.group(3)
                        lineas_originales[intentos_line_idx_abs] = f"{prefijo_intentos}{nuevos_intentos}{sufijo_intentos}"
                        logging.info(f"{logPrefix} Intentos para Tarea ID '{id_tarea_a_marcar}' incrementados a {nuevos_intentos} en línea {intentos_line_idx_abs + 1}.")
                    else:
                        logging.warning(f"{logPrefix} No se pudo parsear prefijo/sufijo de intentos para Tarea ID '{id_tarea_a_marcar}'. Intentos no modificados en MD directamente.")
                else: # Si no existe la línea de Intentos, pero tenemos la tarea parseada, es raro.
                      # Podríamos considerar añadirla, pero es más seguro asumir que el formato está.
                    logging.warning(f"{logPrefix} No se encontró línea de '- **Intentos:**' para Tarea ID '{id_tarea_a_marcar}'. Intentos no actualizados en el Markdown, aunque el valor parseado era {intentos_actuales}.")
            
            if tarea_encontrada_y_modificada: # Si se modificó algo (al menos el estado)
                break # Salir del bucle de tareas_originales, ya encontramos y procesamos la tarea.
    
    if not tarea_encontrada_y_modificada:
        logging.warning(f"{logPrefix} Tarea ID '{id_tarea_a_marcar}' no encontrada o no modificada. Devolviendo contenido original.")
        return contenido_mision_md_original # o None, si es un error que deba detener el flujo
        
    return "\n".join(lineas_originales)


# --- Funciones específicas para los nuevos pasos ---

def paso0_revisar_mision_local(ruta_repo):
    """
    Paso 0: Revisa si existe misionOrion.md EN LA RAMA ACTUAL.
    Se espera que esta función sea llamada cuando el agente ya está en una rama de misión
    potencial, o en la rama de trabajo principal si no hay misión activa.
    """
    logPrefix = "paso0_revisar_mision_local:"
    rama_actual = manejadorGit.obtener_rama_actual(ruta_repo)
    logging.info(f"{logPrefix} Revisando {MISION_ORION_MD} en rama actual: '{rama_actual}'")
    ruta_mision_orion = os.path.join(ruta_repo, MISION_ORION_MD)

    if os.path.exists(ruta_mision_orion):
        logging.info(f"{logPrefix} Se encontró {MISION_ORION_MD} en '{rama_actual}'.")
        try:
            with open(ruta_mision_orion, 'r', encoding='utf-8') as f:
                contenido_mision = f.read()
            
            metadatos, lista_tareas, hay_tareas_pendientes = parsear_mision_orion(contenido_mision)

            if not metadatos or not metadatos.get("nombre_clave"):
                logging.warning(f"{logPrefix} {MISION_ORION_MD} existe pero no se pudo extraer metadatos/nombre clave. Se tratará como para crear nueva misión.")
                return "ignorar_mision_actual_y_crear_nueva", None, None, None # metadatos, lista_tareas, nombre_clave

            nombre_clave_parseado = metadatos["nombre_clave"]
            estado_general_mision = metadatos.get("estado_general", "PENDIENTE")

            # Validar si el nombre clave en el archivo coincide con el esperado de la rama activa (si aplica)
            # Esta validación es más para consistencia.

            if hay_tareas_pendientes and estado_general_mision not in ["COMPLETADA", "FALLIDA"]:
                logging.info(f"{logPrefix} Misión '{nombre_clave_parseado}' con tareas pendientes y estado '{estado_general_mision}'. Lista para procesar.")
                return "procesar_mision_existente", metadatos, lista_tareas, nombre_clave_parseado
            else:
                logging.info(f"{logPrefix} Misión '{nombre_clave_parseado}' sin tareas pendientes o en estado '{estado_general_mision}'. Se considera completada o fallida.")
                return "mision_existente_finalizada", metadatos, lista_tareas, nombre_clave_parseado
        except Exception as e:
            logging.error(f"{logPrefix} Error leyendo o parseando {MISION_ORION_MD}: {e}. Se intentará crear una nueva.", exc_info=True)
            return "ignorar_mision_actual_y_crear_nueva", None, None, None
    else:
        logging.info(f"{logPrefix} No se encontró {MISION_ORION_MD} en rama '{rama_actual}'.")
        return "no_hay_mision_local", None, None, None


def paso1_1_seleccion_y_decision_inicial(ruta_repo, api_provider, registro_archivos):
    logPrefix = "paso1_1_seleccion_y_decision_inicial:"
    archivo_seleccionado_rel = seleccionar_archivo_mas_antiguo(ruta_repo, registro_archivos)
    guardar_registro_archivos(registro_archivos)

    if not archivo_seleccionado_rel:
        logging.warning(f"{logPrefix} No se pudo seleccionar ningún archivo.")
        return "ciclo_terminado_sin_accion", None, None, None

    ruta_archivo_seleccionado_abs = os.path.join(ruta_repo, archivo_seleccionado_rel)
    if not os.path.exists(ruta_archivo_seleccionado_abs):
        logging.error(f"{logPrefix} Archivo seleccionado '{archivo_seleccionado_rel}' no existe. Reintentando.")
        registro_archivos[archivo_seleccionado_rel] = datetime.now().isoformat() + "_NOT_FOUND"
        guardar_registro_archivos(registro_archivos)
        return "reintentar_seleccion", None, None, None

    estructura_proyecto = analizadorCodigo.generarEstructuraDirectorio(
        ruta_repo, directorios_ignorados=settings.DIRECTORIOS_IGNORADOS, max_depth=5, incluir_archivos=True)
    
    resultado_lectura = analizadorCodigo.leerArchivos([ruta_archivo_seleccionado_abs], ruta_repo, api_provider=api_provider)
    contenido_archivo = resultado_lectura['contenido']
    tokens_contenido = resultado_lectura['tokens']
    tokens_estructura = analizadorCodigo.contarTokensTexto(estructura_proyecto or "", api_provider)
    tokens_estimados = 500 + tokens_contenido + tokens_estructura # 500 para prompt base

    gestionar_limite_tokens(tokens_estimados, api_provider)
    
    decision_IA_paso1_1 = analizadorCodigo.solicitar_evaluacion_archivo(
        archivo_seleccionado_rel, contenido_archivo, estructura_proyecto, api_provider, "" # reglas_refactor vacío por ahora
    )
    registrar_tokens_usados(decision_IA_paso1_1.get("tokens_consumidos_api", tokens_estimados) if decision_IA_paso1_1 else tokens_estimados)

    if not decision_IA_paso1_1 or not decision_IA_paso1_1.get("necesita_refactor"):
        logging.info(f"{logPrefix} IA decidió que '{archivo_seleccionado_rel}' no necesita refactor. Razón: {decision_IA_paso1_1.get('razonamiento', 'N/A') if decision_IA_paso1_1 else 'Error IA'}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO1.1_NO_REFACTOR:{archivo_seleccionado_rel}", decision=decision_IA_paso1_1)
        ])
        return "reintentar_seleccion", None, None, None

    logging.info(f"{logPrefix} IA decidió SÍ refactorizar '{archivo_seleccionado_rel}'. Razón: {decision_IA_paso1_1.get('razonamiento')}")
    archivos_ctx_sugeridos_rel = decision_IA_paso1_1.get("archivos_contexto_sugeridos", [])
    archivos_ctx_validados_rel = []
    if decision_IA_paso1_1.get("necesita_contexto_adicional"):
        for f_rel in archivos_ctx_sugeridos_rel:
            if not f_rel or f_rel == archivo_seleccionado_rel: continue
            if os.path.exists(os.path.join(ruta_repo, f_rel)) and os.path.isfile(os.path.join(ruta_repo, f_rel)):
                archivos_ctx_validados_rel.append(f_rel)
            else: logging.warning(f"{logPrefix} Archivo de contexto sugerido '{f_rel}' no existe. Descartado.")
    
    return "generar_mision", archivo_seleccionado_rel, archivos_ctx_validados_rel, decision_IA_paso1_1


def paso1_2_generar_mision(ruta_repo, archivo_a_refactorizar_rel, archivos_contexto_para_crear_mision_rel, decision_paso1_1, api_provider):
    logPrefix = "paso1_2_generar_mision:"
    logging.info(f"{logPrefix} Generando misión para: '{archivo_a_refactorizar_rel}' con contexto gen: {archivos_contexto_para_crear_mision_rel}")

    archivos_para_leer_abs = [os.path.join(ruta_repo, archivo_a_refactorizar_rel)]
    for f_rel in archivos_contexto_para_crear_mision_rel:
        archivos_para_leer_abs.append(os.path.join(ruta_repo, f_rel))
    archivos_para_leer_abs_unicos = sorted(list(set(archivos_para_leer_abs)))

    resultado_lectura_ctx = analizadorCodigo.leerArchivos(archivos_para_leer_abs_unicos, ruta_repo, api_provider=api_provider)
    contexto_completo_para_mision = resultado_lectura_ctx['contenido']
    tokens_contexto_mision = resultado_lectura_ctx['tokens']
    tokens_estimados = 700 + tokens_contexto_mision # 700 para prompt base

    gestionar_limite_tokens(tokens_estimados, api_provider)

    contenido_mision_generado_dict = analizadorCodigo.generar_contenido_mision_orion(
        archivo_a_refactorizar_rel, contexto_completo_para_mision,
        decision_paso1_1.get("razonamiento"), api_provider,
        archivos_contexto_generacion_rel_list=archivos_contexto_para_crear_mision_rel
    )
    registrar_tokens_usados(contenido_mision_generado_dict.get("tokens_consumidos_api", tokens_estimados) if contenido_mision_generado_dict else tokens_estimados)

    if not contenido_mision_generado_dict or \
       not contenido_mision_generado_dict.get("nombre_clave_mision") or \
       not contenido_mision_generado_dict.get("contenido_markdown_mision"):
        logging.error(f"{logPrefix} IA no generó contenido válido. Respuesta: {contenido_mision_generado_dict}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO1.2_ERROR_GENERACION", decision=decision_paso1_1, error_message="IA no generó misión válida")
        ])
        return "error_generando_mision", None, None

    nombre_clave_mision = contenido_mision_generado_dict["nombre_clave_mision"]
    contenido_markdown_mision = contenido_mision_generado_dict["contenido_markdown_mision"]
    
    rama_base = manejadorGit.obtener_rama_actual(ruta_repo) or settings.RAMATRABAJO
    if not manejadorGit.crear_y_cambiar_a_rama(ruta_repo, nombre_clave_mision, rama_base):
        logging.error(f"{logPrefix} No se pudo crear o cambiar a rama '{nombre_clave_mision}' desde '{rama_base}'.")
        return "error_generando_mision", None, None
    logging.info(f"{logPrefix} En rama de misión: '{nombre_clave_mision}' (desde '{rama_base}')")

    try:
        with open(os.path.join(ruta_repo, MISION_ORION_MD), 'w', encoding='utf-8') as f: f.write(contenido_markdown_mision)
        logging.info(f"{logPrefix} {MISION_ORION_MD} guardado en rama '{nombre_clave_mision}'")
    except Exception as e:
        logging.error(f"{logPrefix} Error guardando {MISION_ORION_MD}: {e}", exc_info=True)
        manejadorGit.cambiar_a_rama_existente(ruta_repo, rama_base); manejadorGit.eliminarRama(ruta_repo, nombre_clave_mision, local=True)
        return "error_generando_mision", None, None

    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Crear misión: {nombre_clave_mision}", [MISION_ORION_MD]):
        logging.error(f"{logPrefix} No se pudo hacer commit de {MISION_ORION_MD} en '{nombre_clave_mision}'.")
        # No eliminar la rama si el commit falló pero el archivo se creó, podría ser útil para debug manual
        # manejadorGit.cambiar_a_rama_existente(ruta_repo, rama_base); manejadorGit.eliminarRama(ruta_repo, nombre_clave_mision, local=True)
        return "error_generando_mision", None, None # Error si el commit del MD falla

    logging.info(f"{logPrefix} Misión '{nombre_clave_mision}' generada y commiteada.")
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO1.2_MISION_GENERADA:{nombre_clave_mision}", result_details=f"Archivo: {MISION_ORION_MD}")
    ])
    return "mision_generada_ok", contenido_markdown_mision, nombre_clave_mision


def paso2_ejecutar_tarea_mision(ruta_repo, nombre_rama_mision, api_provider, modo_test):
    # Esta función ahora es llamada cuando ya se está en la rama de la misión.
    # El contenido de la misión (metadatos, lista_tareas) se carga desde el archivo en la rama.
    logPrefix = f"paso2_ejecutar_tarea_mision (Rama: {nombre_rama_mision}):"
    logging.info(f"{logPrefix} Iniciando ejecución de tarea.")
    
    # Asegurar estar en la rama correcta (doble check)
    if manejadorGit.obtener_rama_actual(ruta_repo) != nombre_rama_mision:
        logging.warning(f"{logPrefix} No se estaba en la rama '{nombre_rama_mision}'. Intentando cambiar...")
        if not manejadorGit.cambiar_a_rama_existente(ruta_repo, nombre_rama_mision):
            logging.error(f"{logPrefix} No se pudo cambiar a rama '{nombre_rama_mision}'. Abortando tarea.")
            return "error_critico_git", None # Retorna (estado_final_fase, contenido_mision_actualizado_o_none)

    ruta_mision_actual_md = os.path.join(ruta_repo, MISION_ORION_MD)
    contenido_mision_actual_md = ""
    if os.path.exists(ruta_mision_actual_md):
        with open(ruta_mision_actual_md, 'r', encoding='utf-8') as f:
            contenido_mision_actual_md = f.read()
    else:
        logging.error(f"{logPrefix} {MISION_ORION_MD} no encontrado en la rama '{nombre_rama_mision}'. Abortando tarea.")
        return "error_critico_mision_no_encontrada", None

    metadatos_mision, lista_tareas_mision, _ = parsear_mision_orion(contenido_mision_actual_md)
    if not metadatos_mision:
         logging.error(f"{logPrefix} Fallo al re-parsear {MISION_ORION_MD} desde la rama. Abortando tarea.")
         return "error_critico_parseo_mision", contenido_mision_actual_md

    tarea_actual_info, _ = obtener_proxima_tarea_pendiente(lista_tareas_mision)

    if not tarea_actual_info:
        logging.info(f"{logPrefix} No se encontraron tareas pendientes en '{nombre_rama_mision}'. Considerada completada.")
        return "mision_completada", contenido_mision_actual_md

    tarea_id = tarea_actual_info.get("id", "N/A_ID")
    tarea_titulo = tarea_actual_info.get("titulo", "N/A_Titulo")
    logging.info(f"{logPrefix} Tarea a ejecutar: ID '{tarea_id}', Título: '{tarea_titulo}'")

    # --- INICIO: Limpieza de rutas de archivo ---
    def limpiar_lista_rutas(lista_rutas_crudas, origen_rutas_log=""):
        rutas_limpias_final = []
        if not lista_rutas_crudas:
            return rutas_limpias_final
        
        for ruta_cruda in lista_rutas_crudas:
            if not isinstance(ruta_cruda, str) or not ruta_cruda.strip():
                logging.warning(f"{logPrefix} Ruta inválida o vacía encontrada en {origen_rutas_log}: '{ruta_cruda}'. Se ignora.")
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
                    logging.debug(f"{logPrefix} Ruta '{ruta_procesada}' de {origen_rutas_log} validada y añadida para contexto.")
                else:
                    logging.warning(f"{logPrefix} Ruta '{ruta_procesada}' (original: '{ruta_cruda}') de {origen_rutas_log} no existe o no es un archivo. Se ignora.")
            elif ruta_procesada:
                 logging.debug(f"{logPrefix} Ruta individual '{ruta_cruda}' de {origen_rutas_log} descartada después de limpieza (quedó vacía o como 'ninguno').")
        return rutas_limpias_final

    archivos_ctx_ejecucion_mision_crudos = metadatos_mision.get("archivos_contexto_ejecucion", [])
    archivos_especificos_tarea_crudos = tarea_actual_info.get("archivos_implicados_especificos", [])
    archivo_principal_mision_crudo = metadatos_mision.get("archivo_principal")

    archivos_ctx_ejecucion_limpios = limpiar_lista_rutas(archivos_ctx_ejecucion_mision_crudos, "metadatos[archivos_contexto_ejecucion]")
    archivos_especificos_tarea_limpios = limpiar_lista_rutas(archivos_especificos_tarea_crudos, f"tarea ID '{tarea_id}'[archivos_implicados_especificos]")
    
    # El archivo principal también se limpia y valida, aunque es uno solo
    archivos_principal_limpios = []
    if archivo_principal_mision_crudo:
        archivos_principal_limpios = limpiar_lista_rutas([archivo_principal_mision_crudo], "metadatos[archivo_principal]")
    # --- FIN: Limpieza de rutas de archivo ---

    archivos_para_leer_rel = []
    if archivos_principal_limpios: # Será una lista con 0 o 1 elemento
        archivos_para_leer_rel.extend(archivos_principal_limpios)
    archivos_para_leer_rel.extend(archivos_ctx_ejecucion_limpios)
    archivos_para_leer_rel.extend(archivos_especificos_tarea_limpios)
    
    # Eliminar duplicados y ordenar (aunque el orden no es crítico para leerArchivos)
    archivos_para_leer_rel = sorted(list(set(archivos_para_leer_rel)))
    
    contexto_para_tarea_str, tokens_contexto_tarea = "", 0
    archivos_leidos_para_tarea_rel = []

    if archivos_para_leer_rel:
        # Las rutas en archivos_para_leer_rel ya son relativas, limpias y validadas (existen)
        archivos_abs_ctx_tarea = [os.path.join(ruta_repo, f_rel) for f_rel in archivos_para_leer_rel]
        
        # leerArchivos internamente también valida existencia, pero aquí ya lo hemos hecho.
        resultado_lectura_ctx = analizadorCodigo.leerArchivos(archivos_abs_ctx_tarea, ruta_repo, api_provider=api_provider)
        contexto_para_tarea_str = resultado_lectura_ctx['contenido']
        tokens_contexto_tarea = resultado_lectura_ctx['tokens']
        # archivos_leidos_para_tarea_rel se puede reconstruir desde las rutas que sí se leyeron
        # o asumir que todas las de archivos_para_leer_rel se leyeron porque ya las validamos.
        # Para ser precisos, podríamos obtenerlo de resultado_lectura_ctx si leerArchivos lo devuelve.
        # Por ahora, usamos nuestra lista validada:
        archivos_leidos_para_tarea_rel = archivos_para_leer_rel
        logging.info(f"{logPrefix} Contexto para tarea leído de {len(archivos_leidos_para_tarea_rel)} archivo(s) validados: {archivos_leidos_para_tarea_rel}")
    else: 
        logging.info(f"{logPrefix} No se definieron o validaron archivos para leer como contexto para la tarea.")

    tokens_mision_y_tarea_desc = analizadorCodigo.contarTokensTexto(
        contenido_mision_actual_md + tarea_actual_info.get('descripcion', ''), api_provider)
    tokens_estimados = 800 + tokens_contexto_tarea + tokens_mision_y_tarea_desc

    gestionar_limite_tokens(tokens_estimados, api_provider)
    
    resultado_ejecucion_tarea = analizadorCodigo.ejecutar_tarea_especifica_mision(
        tarea_actual_info, contenido_mision_actual_md, contexto_para_tarea_str, api_provider
    )
    registrar_tokens_usados(resultado_ejecucion_tarea.get("tokens_consumidos_api", tokens_estimados) if resultado_ejecucion_tarea else tokens_estimados)

    contenido_mision_post_tarea = contenido_mision_actual_md # Inicializar

    if not resultado_ejecucion_tarea or "archivos_modificados" not in resultado_ejecucion_tarea:
        logging.error(f"{logPrefix} IA no devolvió 'archivos_modificados'. Respuesta: {resultado_ejecucion_tarea}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO2_ERROR_TAREA_IA:{nombre_rama_mision}", decision=tarea_actual_info, error_message="IA no generó cambios válidos")
        ])
        # Marcar tarea como fallida temporalmente
        contenido_mision_post_tarea = marcar_tarea_como_completada(
            contenido_mision_actual_md, 
            tarea_id, 
            "FALLIDA_TEMPORALMENTE", 
            incrementar_intentos_si_fallida_temp=True
        )
        if not contenido_mision_post_tarea: return "error_critico_actualizando_mision", contenido_mision_actual_md
        try:
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' FALLIDA_TEMPORALMENTE (IA)", [MISION_ORION_MD]):
                logging.error(f"{logPrefix} No se pudo commitear {MISION_ORION_MD} (tarea fallida IA).")
        except Exception as e: logging.error(f"{logPrefix} Error guardando/commiteando {MISION_ORION_MD} (tarea fallida IA): {e}"); return "error_critico_actualizando_mision", contenido_mision_actual_md
        return "tarea_fallida", contenido_mision_post_tarea


    if resultado_ejecucion_tarea.get("advertencia_ejecucion") and not resultado_ejecucion_tarea.get("archivos_modificados"):
        logging.warning(f"{logPrefix} IA advirtió: {resultado_ejecucion_tarea['advertencia_ejecucion']}. Tarea no resultó en cambios. Marcando como SALTADA.")
        contenido_mision_post_tarea = marcar_tarea_como_completada(contenido_mision_actual_md, tarea_id, "SALTADA")
        if not contenido_mision_post_tarea: return "error_critico_actualizando_mision", contenido_mision_actual_md 
        try: 
            with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
            if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' SALTADA", [MISION_ORION_MD]):
                 logging.error(f"{logPrefix} No se pudo commitear {MISION_ORION_MD} (tarea saltada).") # No crítico para el flujo
        except Exception as e: logging.error(f"{logPrefix} Error guardando {MISION_ORION_MD} (tarea saltada): {e}"); # No crítico
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO2_TAREA_SALTADA:{nombre_rama_mision}", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("advertencia_ejecucion"))
        ])
        _, _, hay_pendientes_despues_salto = parsear_mision_orion(contenido_mision_post_tarea) 
        return "mision_completada" if not hay_pendientes_despues_salto else "tarea_ejecutada_continuar_mision", contenido_mision_post_tarea


    if resultado_ejecucion_tarea.get("archivos_modificados"):
        exito_aplicar, msg_err_aplicar = aplicadorCambios.aplicarCambiosSobrescritura(
            resultado_ejecucion_tarea["archivos_modificados"], ruta_repo,
            accionOriginal=f"modificar_segun_tarea_mision:{nombre_rama_mision}", paramsOriginal=tarea_actual_info
        )
        if not exito_aplicar:
            logging.error(f"{logPrefix} Falló aplicación de cambios: {msg_err_aplicar}")
            manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO2_APPLY_FAIL:{nombre_rama_mision}", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea, error_message=msg_err_aplicar)
            ])
            manejadorGit.descartarCambiosLocales(ruta_repo) # Descartar cambios fallidos de ESTA tarea
            contenido_mision_post_tarea = marcar_tarea_como_completada(
                contenido_mision_actual_md, 
                tarea_id, 
                "FALLIDA_TEMPORALMENTE",
                incrementar_intentos_si_fallida_temp=True
            )
            if not contenido_mision_post_tarea: return "error_critico_actualizando_mision", contenido_mision_actual_md
            try:
                with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
                if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' FALLIDA_TEMPORALMENTE (apply)", [MISION_ORION_MD]):
                    logging.error(f"{logPrefix} No se pudo commitear {MISION_ORION_MD} (tarea fallida apply).")
            except Exception as e: logging.error(f"{logPrefix} Error guardando/commiteando {MISION_ORION_MD} (tarea fallida apply): {e}")
            return "tarea_fallida", contenido_mision_post_tarea
        
        commit_msg = f"Tarea ID {tarea_id} ({tarea_titulo[:50]}) completada (Misión {nombre_rama_mision})"
        if not manejadorGit.hacerCommit(ruta_repo, commit_msg): 
             logging.warning(f"{logPrefix} No se realizó commit para tarea (quizás sin cambios efectivos o fallo en git add/commit). AÚN ASÍ, la tarea se marca como COMPLETADA en el MD.")
    else: 
        logging.info(f"{logPrefix} IA no especificó archivos modificados (y no fue manejado por advertencia). Asumiendo tarea sin efecto.")

    contenido_mision_post_tarea = marcar_tarea_como_completada(contenido_mision_actual_md, tarea_id, "COMPLETADA")
    if not contenido_mision_post_tarea: return "error_critico_actualizando_mision", contenido_mision_actual_md

    try:
        with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
    except Exception as e: logging.error(f"{logPrefix} Error guardando {MISION_ORION_MD}: {e}"); return "error_critico_actualizando_mision", contenido_mision_actual_md

    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Actualizar Misión '{nombre_rama_mision}', Tarea '{tarea_id}' completada", [MISION_ORION_MD]):
        logging.error(f"{logPrefix} No se pudo commitear actualización de {MISION_ORION_MD}.") # No crítico para el flujo principal de tarea
    
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO2_TAREA_OK:{nombre_rama_mision}", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("archivos_modificados"))
    ])

    _, _, hay_pendientes_actualizada = parsear_mision_orion(contenido_mision_post_tarea)
    return "mision_completada" if not hay_pendientes_actualizada else "tarea_ejecutada_continuar_mision", contenido_mision_post_tarea


# --- Función Principal de Fase del Agente (MODIFICADO) ---
def ejecutarFaseDelAgente(api_provider: str, modo_test: bool):
    logPrefix = f"ejecutarFaseDelAgente({api_provider.upper()}):"
    logging.info(f"{logPrefix} ===== INICIO FASE AGENTE =====")
    
    if not _validarConfiguracionEsencial(api_provider): return False
    if api_provider == 'google' and settings.GEMINIAPIKEY and not analizadorCodigo.configurarGemini():
        logging.critical(f"{logPrefix} Falló config Google GenAI."); return False

    if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
        logging.error(f"{logPrefix} Falló preparación de repo en '{settings.RAMATRABAJO}'. Saliendo."); return False
    logging.info(f"{logPrefix} Repositorio listo en rama de trabajo principal: '{settings.RAMATRABAJO}'.")

    nombre_clave_mision_activa = cargar_estado_mision_activa()
    registro_archivos_analizados = cargar_registro_archivos() # Cargar siempre
    
    # --- PROCESAR MISIÓN EXISTENTE ---
    if nombre_clave_mision_activa and manejadorGit.existe_rama(settings.RUTACLON, nombre_clave_mision_activa, local_only=True):
        logging.info(f"{logPrefix} Misión activa detectada por estado: '{nombre_clave_mision_activa}'. Cambiando a su rama.")
        if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, nombre_clave_mision_activa):
            logging.error(f"{logPrefix} No se pudo cambiar a la rama de misión activa '{nombre_clave_mision_activa}'. Limpiando estado y procediendo a crear nueva misión.")
            limpiar_estado_mision_activa()
            # Flujo continúa para crear nueva misión
        else: # Se pudo cambiar a la rama de misión activa
            res_paso0, meta_mision, _, _ = paso0_revisar_mision_local(settings.RUTACLON) # Revisa mision.md en la rama actual
            
            if res_paso0 == "procesar_mision_existente":
                logging.info(f"{logPrefix} Misión '{nombre_clave_mision_activa}' confirmada en rama, procesando tarea.")
                res_paso2, _ = paso2_ejecutar_tarea_mision(settings.RUTACLON, nombre_clave_mision_activa, api_provider, modo_test)
                
                if res_paso2 == "tarea_ejecutada_continuar_mision":
                    logging.info(f"{logPrefix} Tarea ejecutada en '{nombre_clave_mision_activa}', quedan más. Script se detendrá.")
                    if modo_test: manejadorGit.hacerPush(settings.RUTACLON, nombre_clave_mision_activa)
                    return True # Fase OK, script sale, se reiniciará
                
                elif res_paso2 == "mision_completada":
                    logging.info(f"{logPrefix} Misión '{nombre_clave_mision_activa}' completada. Procediendo a merge y limpieza.")
                    if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                        logging.error(f"{logPrefix} No se pudo cambiar a '{settings.RAMATRABAJO}' para merge. Misión no mergeada."); return False
                    if manejadorGit.hacerMergeRama(settings.RUTACLON, nombre_clave_mision_activa, settings.RAMATRABAJO):
                        logging.info(f"{logPrefix} Merge de '{nombre_clave_mision_activa}' a '{settings.RAMATRABAJO}' exitoso.")
                        if modo_test:
                             if manejadorGit.hacerPush(settings.RUTACLON, settings.RAMATRABAJO):
                                logging.info(f"{logPrefix} Push de '{settings.RAMATRABAJO}' exitoso (modo test).")
                                # Solo eliminar rama remota si el push de la rama de trabajo fue exitoso
                                # manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_mision_activa, local=False, remota=True)
                        manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_mision_activa, local=True)
                    else: logging.error(f"{logPrefix} Falló merge de '{nombre_clave_mision_activa}' a '{settings.RAMATRABAJO}'. Rama de misión persiste.")
                    limpiar_estado_mision_activa()
                    return True # Fase OK, script sale
                
                elif res_paso2 == "tarea_fallida":
                    logging.error(f"{logPrefix} Tarea falló en misión '{nombre_clave_mision_activa}'. Script se detendrá.")
                    if modo_test: manejadorGit.hacerPush(settings.RUTACLON, nombre_clave_mision_activa) # Push con la tarea marcada como fallida
                    return True # Fase técnicamente OK (error manejado), script sale
                
                else: # Errores críticos en paso2 (ej. mision no encontrada, parseo)
                    logging.error(f"{logPrefix} Error crítico durante paso2 para misión '{nombre_clave_mision_activa}': {res_paso2}. Limpiando estado.")
                    limpiar_estado_mision_activa() # Podría ser muy agresivo, pero evita bucles si la misión está corrupta
                    manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO) # Volver a base
                    return False # Fase falló

            elif res_paso0 == "mision_existente_finalizada":
                 logging.info(f"{logPrefix} Misión '{nombre_clave_mision_activa}' en rama ya estaba finalizada (sin tareas pendientes). Limpiando estado y procediendo a crear nueva.")
                 manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO) # Asegurar volver
                 # No se hace merge aquí porque se asume que ya fue mergeada o no era necesaria
                 manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_mision_activa, local=True)
                 limpiar_estado_mision_activa()
                 # Flujo continúa para crear nueva misión
            
            else: # no_hay_mision_local en la rama activa, o ignorar_mision_actual...
                logging.warning(f"{logPrefix} {MISION_ORION_MD} no encontrado o inválido en rama activa '{nombre_clave_mision_activa}' (Resultado paso0: {res_paso0}). Limpiando estado y procediendo a crear nueva.")
                manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO)
                manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_mision_activa, local=True) # Limpiar rama si el MD no está
                limpiar_estado_mision_activa()
                # Flujo continúa para crear nueva misión

    # --- CREAR NUEVA MISIÓN (si no había activa o se limpió la anterior) ---
    # Asegurar estar en la rama de trabajo principal
    if manejadorGit.obtener_rama_actual(settings.RUTACLON) != settings.RAMATRABAJO:
        if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(f"{logPrefix} No se pudo cambiar a '{settings.RAMATRABAJO}' para iniciar nueva misión. Saliendo."); return False
    
    logging.info(f"{logPrefix} No hay misión activa válida. Procediendo a crear una nueva.")
    res_paso1_1, archivo_sel, ctx_sel, decision_ia_1_1 = paso1_1_seleccion_y_decision_inicial(
        settings.RUTACLON, api_provider, registro_archivos_analizados)

    if res_paso1_1 == "generar_mision":
        logging.info(f"{logPrefix} Archivo '{archivo_sel}' seleccionado. Generando misión.")
        res_paso1_2, _, nombre_clave_generado = paso1_2_generar_mision(
            settings.RUTACLON, archivo_sel, ctx_sel, decision_ia_1_1, api_provider)
        
        if res_paso1_2 == "mision_generada_ok" and nombre_clave_generado:
            # --- VALIDACIÓN ADICIONAL: La misión generada DEBE tener tareas si Paso 1.1 dijo "necesita_refactor" ---
            ruta_mision_generada_md = os.path.join(settings.RUTACLON, MISION_ORION_MD) # En la rama de misión
            contenido_mision_generada_md = ""
            if os.path.exists(ruta_mision_generada_md):
                with open(ruta_mision_generada_md, 'r', encoding='utf-8') as f: contenido_mision_generada_md = f.read()
            
            _, tareas_gen, hay_pendientes_gen = parsear_mision_orion(contenido_mision_generada_md)
            se_espera_refactor = decision_ia_1_1.get("necesita_refactor", False)

            if se_espera_refactor and (not tareas_gen or not hay_pendientes_gen):
                logging.error(f"{logPrefix} ERROR DE GENERACIÓN: Paso 1.1 indicó refactor para '{archivo_sel}' pero misión '{nombre_clave_generado}' NO TIENE TAREAS PENDIENTES.")
                manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                    manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO1.2_ERROR_MISION_SIN_TAREAS", decision=decision_ia_1_1, 
                                                                 error_message=f"Misión '{nombre_clave_generado}' generada sin tareas.")
                ])
                manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO)
                manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_generado, local=True)
                logging.info(f"{logPrefix} Rama de misión '{nombre_clave_generado}' eliminada. Saliendo.")
                return False # Fase falló críticamente
            # --- FIN VALIDACIÓN ---

            guardar_estado_mision_activa(nombre_clave_generado)
            logging.info(f"{logPrefix} Nueva misión '{nombre_clave_generado}' creada y estado guardado. Script se detendrá.")
            if modo_test: manejadorGit.hacerPush(settings.RUTACLON, nombre_clave_generado, setUpstream=True) # Primera vez, set upstream
            return True # Fase OK
        
        else: # error_generando_mision
            logging.error(f"{logPrefix} Error generando misión (IA o Git). Saliendo.")
            # paso1_2 debe intentar limpiar la rama si la creó y falló. Asegurar volver a base.
            manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO)
            # Si nombre_clave_generado existe (incluso si falló el contenido), intentar limpiar la rama
            if nombre_clave_generado and manejadorGit.existe_rama(settings.RUTACLON, nombre_clave_generado, local_only=True):
                 manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_generado, local=True)
            return False # Fase falló
    
    elif res_paso1_1 == "reintentar_seleccion":
        logging.info(f"{logPrefix} Paso 1.1 no seleccionó archivo o IA no vio refactor. Script se detendrá.")
        return True # Fase OK (sin acción pero no error de agente)
    
    elif res_paso1_1 == "ciclo_terminado_sin_accion":
        logging.info(f"{logPrefix} Paso 1.1 no encontró acción (ej. no hay archivos). Script se detendrá.")
        return True # Fase OK
    
    else: # Error inesperado de paso1.1
        logging.error(f"{logPrefix} Resultado inesperado de paso1.1: {res_paso1_1}. Saliendo.")
        return False # Fase falló


if __name__ == "__main__":
    configurarLogging()
    parser = argparse.ArgumentParser(
        description="Agente Adaptativo de Refactorización de Código con IA.",
        epilog="Ejecuta una fase del ciclo adaptativo (crear misión o ejecutar tarea) y luego se detiene."
    )
    parser.add_argument("--modo-test", action="store_true", help="Activa modo prueba (hace push a Git).")
    parser.add_argument("--openrouter", action="store_true", help="Utilizar OpenRouter como proveedor de IA.")
    args = parser.parse_args()
    
    codigo_salida = orchestrarEjecucionScript(args)
    
    logging.info(f"Script principal (adaptativo) finalizado con código: {codigo_salida}")
    sys.exit(codigo_salida)