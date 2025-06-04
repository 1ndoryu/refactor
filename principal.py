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
        guardar_registro_archivos(cargar_registro_archivos())
        logging.info("Registro de archivos analizados guardado al finalizar.")
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
    match_titulo = re.match(r"###\s*Tarea\s*([\w-]+):\s*(.+)", match_titulo_linea, re.IGNORECASE) # ID puede tener guiones
    if match_titulo:
        tarea_dict["id"] = match_titulo.group(1).strip()
        tarea_dict["titulo"] = match_titulo.group(2).strip()
    else:
        logging.warning(f"{logPrefix} No se pudo parsear ID/Título de la tarea: '{match_titulo_linea}'")

    for linea_original_tarea in lineas_tarea[1:]:
        linea_strip = linea_original_tarea.strip()
        
        match_id_field = re.match(r"-\s*\*\*ID:\*\*\s*([\w-]+)", linea_original_tarea, re.IGNORECASE)
        if match_id_field: 
            # Priorizar ID de campo si existe y difiere del de título (aunque no debería)
            parsed_id_field = match_id_field.group(1).strip()
            if not tarea_dict["id"]: tarea_dict["id"] = parsed_id_field
            elif tarea_dict["id"] != parsed_id_field:
                 logging.warning(f"{logPrefix} ID de tarea en título ('{tarea_dict['id']}') difiere de ID en campo ('{parsed_id_field}'). Usando ID de campo.")
                 tarea_dict["id"] = parsed_id_field
            in_descripcion = False; continue

        match_estado = re.match(r"-\s*\*\*Estado:\*\*\s*(PENDIENTE|COMPLETADA|SALTADA|FALLIDA_TEMPORALMENTE)", linea_original_tarea, re.IGNORECASE)
        if match_estado: tarea_dict["estado"] = match_estado.group(1).upper().strip(); in_descripcion = False; continue
        
        match_intentos = re.match(r"-\s*\*\*Intentos:\*\*\s*(\d+)", linea_original_tarea, re.IGNORECASE)
        if match_intentos: tarea_dict["intentos"] = int(match_intentos.group(1).strip()); in_descripcion = False; continue

        match_aie = re.match(r"-\s*\*\*Archivos Implicados .*:\*\*\s*(.+)", linea_original_tarea, re.IGNORECASE)
        if match_aie:
            archivos_str = match_aie.group(1).strip()
            if archivos_str and archivos_str.lower() not in ["ninguno", "opcional:", "ninguno."]:
                tarea_dict["archivos_implicados_especificos"] = [a.strip() for a in archivos_str.split(',') if a.strip()]
            in_descripcion = False; continue
            
        match_desc_start = re.match(r"-\s*\*\*Descripción:\*\*\s*(.*)", linea_original_tarea, re.IGNORECASE)
        if match_desc_start:
            in_descripcion = True
            desc_first_line = match_desc_start.group(1).strip()
            if desc_first_line: descripcion_parts.append(desc_first_line)
            continue

        if in_descripcion and not re.match(r"-\s*\*\*\w+:\*\*", linea_original_tarea):
             descripcion_parts.append(linea_original_tarea.strip())

    tarea_dict["descripcion"] = "\n".join(descripcion_parts).strip()
    if not tarea_dict["id"]:
        logging.error(f"{logPrefix} Tarea parseada sin ID. Buffer: {tarea_dict['raw_lines']}")
        return None
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
                    if m: s = m.group(1).strip(); metadatos[key] = [a.strip() for a in s.split(',') if a.strip() and s.lower() not in ["ninguno", "ninguno."]]; continue
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
    lista_tareas = []
    if isinstance(contenido_mision_o_lista_tareas, str): _, lista_tareas, _ = parsear_mision_orion(contenido_mision_o_lista_tareas)
    elif isinstance(contenido_mision_o_lista_tareas, list): lista_tareas = contenido_mision_o_lista_tareas
    else: logging.error(f"{logPrefix} Entrada inválida."); return None, -1
    if lista_tareas is None: logging.error(f"{logPrefix} Lista de tareas es None."); return None, -1
    for i, tarea in enumerate(lista_tareas):
        if isinstance(tarea, dict) and tarea.get("estado", "").upper() == "PENDIENTE":
            logging.info(f"{logPrefix} Próxima tarea: ID '{tarea.get('id', 'N/A')}' - Título: '{tarea.get('titulo', 'N/A')}'")
            return tarea, i
    logging.info(f"{logPrefix} No hay más tareas pendientes."); return None, -1

def marcar_tarea_como_completada(contenido_mision_md_original: str, id_tarea_a_marcar: str, nuevo_estado: str = "COMPLETADA"):
    logPrefix = "marcar_tarea_como_completada:"
    if not contenido_mision_md_original or not id_tarea_a_marcar: logging.error(f"{logPrefix} Faltan argumentos."); return None
    nuevo_estado_valido = nuevo_estado.upper()
    if nuevo_estado_valido not in ["COMPLETADA", "SALTADA", "PENDIENTE", "FALLIDA_TEMPORALMENTE"]: logging.error(f"{logPrefix} Estado '{nuevo_estado}' no válido."); return None
    
    _, tareas_originales, _ = parsear_mision_orion(contenido_mision_md_original)
    if not tareas_originales: logging.warning(f"{logPrefix} No se parsearon tareas."); return contenido_mision_md_original
    
    lineas_originales = list(contenido_mision_md_original.splitlines())
    tarea_encontrada_y_modificada = False

    for tarea_dict in tareas_originales:
        if tarea_dict and tarea_dict.get("id") == id_tarea_a_marcar:
            line_start = tarea_dict.get("line_start_index", -1); line_end = tarea_dict.get("line_end_index", -1)
            if not (0 <= line_start <= line_end < len(lineas_originales)):
                logging.error(f"{logPrefix} Índices inválidos para tarea ID '{id_tarea_a_marcar}'."); continue

            estado_line_idx_rel = -1
            for idx_rel, linea_tarea_raw in enumerate(tarea_dict.get("raw_lines", [])):
                if re.match(r"-\s*\*\*Estado:\*\*", linea_tarea_raw, re.I): estado_line_idx_rel = idx_rel; break
            
            if estado_line_idx_rel != -1:
                estado_line_idx_abs = line_start + estado_line_idx_rel
                linea_estado_antigua = lineas_originales[estado_line_idx_abs]
                # Extraer el prefijo (todo hasta el valor del estado) para preservar indentación y formato.
                match_prefijo = re.match(r"(.*-\s*\*\*Estado:\*\*\s*)(?:PENDIENTE|COMPLETADA|SALTADA|FALLIDA_TEMPORALMENTE)(.*)", linea_estado_antigua, re.IGNORECASE)
                if match_prefijo:
                    prefijo_estado = match_prefijo.group(1)
                    sufijo_estado = match_prefijo.group(2) # Podría haber algo después, como comentarios
                    lineas_originales[estado_line_idx_abs] = f"{prefijo_estado}{nuevo_estado_valido}{sufijo_estado}"
                    logging.info(f"{logPrefix} Tarea ID '{id_tarea_a_marcar}' marcada como '{nuevo_estado_valido}' en línea {estado_line_idx_abs + 1}.")
                    tarea_encontrada_y_modificada = True; break 
                else: # Fallback si el regex de prefijo falla, menos preciso
                    logging.warning(f"{logPrefix} No se pudo parsear prefijo de estado para Tarea ID '{id_tarea_a_marcar}'. Usando reemplazo simple.")
                    lineas_originales[estado_line_idx_abs] = re.sub(r"(PENDIENTE|COMPLETADA|SALTADA|FALLIDA_TEMPORALMENTE)", nuevo_estado_valido, linea_estado_antigua, flags=re.IGNORECASE)
                    logging.info(f"{logPrefix} Tarea ID '{id_tarea_a_marcar}' marcada como '{nuevo_estado_valido}' (reemplazo simple).")
                    tarea_encontrada_y_modificada = True; break
            else: logging.warning(f"{logPrefix} No se encontró línea de 'Estado:' para tarea ID '{id_tarea_a_marcar}'.")
    
    if not tarea_encontrada_y_modificada: logging.warning(f"{logPrefix} Tarea ID '{id_tarea_a_marcar}' no encontrada o no modificada."); return contenido_mision_md_original
    return "\n".join(lineas_originales)

# --- Funciones específicas para los nuevos pasos ---

def paso0_revisar_mision_local(ruta_repo):
    logPrefix = "paso0_revisar_mision_local:"
    ruta_mision_orion = os.path.join(ruta_repo, MISION_ORION_MD)

    if os.path.exists(ruta_mision_orion):
        logging.info(f"{logPrefix} Se encontró {MISION_ORION_MD}.")
        try:
            with open(ruta_mision_orion, 'r', encoding='utf-8') as f:
                contenido_mision = f.read()
            
            metadatos, lista_tareas, hay_tareas_pendientes = parsear_mision_orion(contenido_mision)

            if not metadatos or not metadatos.get("nombre_clave"):
                logging.warning(f"{logPrefix} {MISION_ORION_MD} existe pero no se pudo extraer metadatos/nombre clave. Se tratará como para crear nueva misión.")
                return "crear_nueva_mision", None, None, None # metadatos, lista_tareas, nombre_clave

            nombre_clave = metadatos["nombre_clave"]
            estado_general_mision = metadatos.get("estado_general", "PENDIENTE")

            if hay_tareas_pendientes and estado_general_mision not in ["COMPLETADA", "FALLIDA"]: # FALLIDA podría necesitar revisión manual
                logging.info(f"{logPrefix} Misión '{nombre_clave}' con tareas pendientes y estado '{estado_general_mision}'. Pasando a Paso 2.")
                return "procesar_mision_existente", metadatos, lista_tareas, nombre_clave
            else:
                logging.info(f"{logPrefix} Misión '{nombre_clave}' sin tareas pendientes o en estado '{estado_general_mision}'. Se procederá a crear una nueva.")
                return "crear_nueva_mision", None, None, None
        except Exception as e:
            logging.error(f"{logPrefix} Error leyendo o parseando {MISION_ORION_MD}: {e}. Se intentará crear una nueva.", exc_info=True)
            return "crear_nueva_mision", None, None, None
    else:
        logging.info(f"{logPrefix} No se encontró {MISION_ORION_MD}. Se procederá a crear una nueva misión.")
        return "crear_nueva_mision", None, None, None


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
    # # Simulación:
    # logging.warning(f"{logPrefix} USANDO PLACEHOLDER para decisión IA Paso 1.1 para '{archivo_seleccionado_rel}'")
    # time.sleep(0.1)
    # necesita_refactor_sim = True 
    # necesita_ctx_sim = True if necesita_refactor_sim else False
    # archivos_sugeridos_sim = ["nucleo/manejadorGit.py", "config/settings.py"] if archivo_seleccionado_rel == "principal.py" else []
    # decision_IA_paso1_1 = {
    #     "necesita_refactor": necesita_refactor_sim,
    #     "necesita_contexto_adicional": necesita_ctx_sim,
    #     "archivos_contexto_sugeridos": archivos_sugeridos_sim,
    #     "razonamiento": f"Simulación: El archivo '{archivo_seleccionado_rel}' necesita refactor y contexto.",
    #     "tokens_consumidos_api": tokens_estimados
    # }
    # # Fin Simulación

    # Asumiendo que la función de IA devuelve 'tokens_consumidos_api' o lo estimamos nosotros si no lo hace.
    # Si no lo devuelve, el 'tokens_estimados' es una buena proxy.
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
        decision_paso1_1.get("razonamiento"), api_provider
    )
    # # Simulación:
    # logging.warning(f"{logPrefix} USANDO PLACEHOLDER para generación de misión Paso 1.2")
    # time.sleep(0.1)
    # nombre_base_limpio = ''.join(c if c.isalnum() else '_' for c in os.path.splitext(os.path.basename(archivo_a_refactorizar_rel))[0])
    # nombre_clave_simulado = f"Mision_{nombre_base_limpio}_{int(time.time()*100) % 10000}"
    # archivos_ctx_ejecucion_sim = list(set([archivo_a_refactorizar_rel] + archivos_contexto_para_crear_mision_rel))

    # contenido_md_simulado = f"""# Misión: {nombre_clave_simulado}

# **Metadatos de la Misión:**
# - **Nombre Clave:** {nombre_clave_simulado}
# - **Archivo Principal:** {archivo_a_refactorizar_rel}
# - **Archivos de Contexto (Generación):** {', '.join(archivos_contexto_para_crear_mision_rel) if archivos_contexto_para_crear_mision_rel else 'Ninguno'}
# - **Archivos de Contexto (Ejecución):** {', '.join(archivos_ctx_ejecucion_sim) if archivos_ctx_ejecucion_sim else 'Ninguno'}
# - **Razón (Paso 1.1):** {decision_paso1_1.get('razonamiento', 'N/A')}
# - **Estado:** PENDIENTE

# ## Tareas de Refactorización:
# ---
# ### Tarea 1: Simular análisis de función X
# - **ID:** T1
# - **Estado:** PENDIENTE
# - **Descripción:** Analizar la función X en '{archivo_a_refactorizar_rel}' y proponer simplificación (Simulación).
# - **Intentos:** 0
# ---
# ### Tarea 2: Simular verificación de variable Y
# - **ID:** T2
# - **Estado:** PENDIENTE
# - **Descripción:** Verificar si la variable Y se usa correctamente en '{archivo_a_refactorizar_rel}' (Simulación).
# - **Intentos:** 0
# ---
# """
    # contenido_mision_generado_dict = {
    #     "nombre_clave_mision": nombre_clave_simulado,
    #     "contenido_markdown_mision": contenido_md_simulado,
    #     "tokens_consumidos_api": tokens_estimados
    # }
    # # Fin Simulación
    
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
        manejadorGit.cambiar_a_rama_existente(ruta_repo, rama_base); manejadorGit.eliminarRama(ruta_repo, nombre_clave_mision, local=True)
        return "error_generando_mision", None, None

    logging.info(f"{logPrefix} Misión '{nombre_clave_mision}' generada y commiteada.")
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO1.2_MISION_GENERADA:{nombre_clave_mision}", result_details=f"Archivo: {MISION_ORION_MD}")
    ])
    return "mision_generada_ok", contenido_markdown_mision, nombre_clave_mision


def paso2_ejecutar_tarea_mision(ruta_repo, metadatos_mision, lista_tareas_mision, nombre_rama_mision, api_provider, modo_test):
    logPrefix = f"paso2_ejecutar_tarea_mision (Rama: {nombre_rama_mision}):"
    logging.info(f"{logPrefix} Iniciando ejecución de tarea.")

    if not manejadorGit.cambiar_a_rama_existente(ruta_repo, nombre_rama_mision):
        logging.error(f"{logPrefix} No se pudo cambiar a rama '{nombre_rama_mision}'. Abortando tarea.")
        return "error_en_tarea", None # Retorna (estado, contenido_mision_actualizado_o_none)

    # Recargar mision.md desde el archivo en la rama actual para asegurar estado más reciente
    ruta_mision_actual_md = os.path.join(ruta_repo, MISION_ORION_MD)
    contenido_mision_actual_md = ""
    if os.path.exists(ruta_mision_actual_md):
        with open(ruta_mision_actual_md, 'r', encoding='utf-8') as f:
            contenido_mision_actual_md = f.read()
        # Re-parsear para obtener la lista de tareas más actualizada
        metadatos_mision_parseados_recientemente, lista_tareas_mision_parseadas_recientemente, _ = parsear_mision_orion(contenido_mision_actual_md)
        if not metadatos_mision_parseados_recientemente: # Fallo de parseo
             logging.error(f"{logPrefix} Fallo al re-parsear {MISION_ORION_MD} desde la rama. Abortando tarea.")
             return "error_en_tarea", contenido_mision_actual_md
        # Actualizar las variables con los datos recién parseados
        metadatos_mision = metadatos_mision_parseados_recientemente
        lista_tareas_mision = lista_tareas_mision_parseadas_recientemente
    else:
        logging.error(f"{logPrefix} {MISION_ORION_MD} no encontrado en la rama '{nombre_rama_mision}'. Abortando tarea.")
        return "error_en_tarea", None


    tarea_actual_info, _ = obtener_proxima_tarea_pendiente(lista_tareas_mision)

    if not tarea_actual_info:
        logging.info(f"{logPrefix} No se encontraron tareas pendientes en '{nombre_rama_mision}'. Considerada completada.")
        return "mision_completada_sin_merge", contenido_mision_actual_md

    tarea_id = tarea_actual_info.get("id", "N/A_ID")
    tarea_titulo = tarea_actual_info.get("titulo", "N/A_Titulo")
    logging.info(f"{logPrefix} Tarea a ejecutar: ID '{tarea_id}', Título: '{tarea_titulo}'")

    archivos_ctx_ejecucion_mision = metadatos_mision.get("archivos_contexto_ejecucion", [])
    archivos_especificos_tarea = tarea_actual_info.get("archivos_implicados_especificos", [])
    
    archivos_para_leer_rel = list(set(archivos_ctx_ejecucion_mision + archivos_especificos_tarea))
    contexto_para_tarea_str, tokens_contexto_tarea = "", 0
    archivos_leidos_para_tarea_rel = []

    if archivos_para_leer_rel:
        archivos_abs_ctx_tarea = [os.path.join(ruta_repo, f_rel) for f_rel in archivos_para_leer_rel if f_rel]
        archivos_abs_ctx_tarea_unicos = sorted(list(set(archivos_abs_ctx_tarea)))
        resultado_lectura_ctx = analizadorCodigo.leerArchivos(archivos_abs_ctx_tarea_unicos, ruta_repo, api_provider=api_provider)
        contexto_para_tarea_str = resultado_lectura_ctx['contenido']
        tokens_contexto_tarea = resultado_lectura_ctx['tokens']
        archivos_leidos_para_tarea_rel = [os.path.relpath(p, ruta_repo).replace(os.sep, '/') for p in archivos_abs_ctx_tarea_unicos]
        logging.info(f"{logPrefix} Contexto para tarea leído de: {archivos_leidos_para_tarea_rel}")

    tokens_mision_y_tarea_desc = analizadorCodigo.contarTokensTexto(
        contenido_mision_actual_md + tarea_actual_info.get('descripcion', ''), api_provider)
    tokens_estimados = 800 + tokens_contexto_tarea + tokens_mision_y_tarea_desc # 800 para prompt base

    gestionar_limite_tokens(tokens_estimados, api_provider)
    
    resultado_ejecucion_tarea = analizadorCodigo.ejecutar_tarea_especifica_mision(
        tarea_actual_info, contenido_mision_actual_md, contexto_para_tarea_str, api_provider
    )
    # # Simulación:
    # logging.warning(f"{logPrefix} USANDO PLACEHOLDER para ejecución de tarea Paso 2: '{tarea_titulo}'")
    # time.sleep(0.1)
    # archivos_modificados_simulados = {}
    # archivo_principal_mision = metadatos_mision.get("archivo_principal")
    # if archivo_principal_mision:
    #     path_principal_abs_sim = os.path.join(ruta_repo, archivo_principal_mision)
    #     contenido_orig_sim = ""
    #     if os.path.exists(path_principal_abs_sim):
    #         with open(path_principal_abs_sim, "r", encoding="utf-8") as f_sim: contenido_orig_sim = f_sim.read()
    #     archivos_modificados_simulados[archivo_principal_mision] = f"// Tarea SIMULADA: '{tarea_titulo}' ejecutada en {archivo_principal_mision}\n" + \
    #                                                             f"// Timestamp: {datetime.now().isoformat()}\n" + contenido_orig_sim
    # else: # Crear uno nuevo si no hay principal
    #     nuevo_archivo_sim = f"sim_paso2_{nombre_rama_mision}_{tarea_id}.py"
    #     archivos_modificados_simulados[nuevo_archivo_sim] = f"// Generado por tarea SIMULADA '{tarea_titulo}' (ID: {tarea_id})\n// Timestamp: {datetime.now().isoformat()}"
    #     logging.info(f"{logPrefix} Simulación: Creará '{nuevo_archivo_sim}'")
    
    # resultado_ejecucion_tarea = {
    #     "archivos_modificados": archivos_modificados_simulados,
    #     "advertencia_ejecucion": None,
    #     "tokens_consumidos_api": tokens_estimados
    # }
    # # Fin Simulación

    registrar_tokens_usados(resultado_ejecucion_tarea.get("tokens_consumidos_api", tokens_estimados) if resultado_ejecucion_tarea else tokens_estimados)

    if not resultado_ejecucion_tarea or "archivos_modificados" not in resultado_ejecucion_tarea:
        logging.error(f"{logPrefix} IA no devolvió 'archivos_modificados'. Respuesta: {resultado_ejecucion_tarea}")
        manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
            manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO2_ERROR_TAREA:{nombre_rama_mision}", decision=tarea_actual_info, error_message="IA no generó cambios válidos")
        ])
        return "error_en_tarea", contenido_mision_actual_md
    
    contenido_mision_post_tarea = contenido_mision_actual_md # Por si hay advertencia y no cambios

    if resultado_ejecucion_tarea.get("advertencia_ejecucion"):
        logging.warning(f"{logPrefix} IA advirtió: {resultado_ejecucion_tarea['advertencia_ejecucion']}")
        if not resultado_ejecucion_tarea.get("archivos_modificados"): # Si hay advertencia Y NO HAY CAMBIOS
            logging.info(f"{logPrefix} Tarea no resultó en cambios debido a advertencia. Marcando como SALTADA.")
            contenido_mision_post_tarea = marcar_tarea_como_completada(contenido_mision_actual_md, tarea_id, "SALTADA")
            if not contenido_mision_post_tarea: return "error_en_tarea", contenido_mision_actual_md # Error marcando

            try: # Guardar y commitear el mision.md actualizado
                with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
                logging.info(f"{logPrefix} {MISION_ORION_MD} actualizado (tarea saltada).")
                if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Misión '{nombre_rama_mision}' Tarea '{tarea_id}' SALTADA", [MISION_ORION_MD]):
                    logging.error(f"{logPrefix} No se pudo commitear {MISION_ORION_MD} (tarea saltada).")
                    # No es fatal para el estado del ciclo, pero la misión en disco puede no reflejar el estado.
                    # Podríamos decidir retornar error_en_tarea aquí. Por ahora, continuamos y se re-evaluará.
            except Exception as e: logging.error(f"{logPrefix} Error guardando {MISION_ORION_MD} (tarea saltada): {e}"); return "error_en_tarea", contenido_mision_actual_md
            
            manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
                manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO2_TAREA_SALTADA:{nombre_rama_mision}", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("advertencia_ejecucion"))
            ])
            
            # Re-parsear para ver si quedan tareas después de saltar
            _, _, hay_pendientes_despues_salto = parsear_mision_orion(contenido_mision_post_tarea) 
            if not hay_pendientes_despues_salto:
                 logging.info(f"{logPrefix} No quedan más tareas después de saltar. Misión completada (sin merge).")
                 return "mision_completada_sin_merge", contenido_mision_post_tarea # Devolver contenido por si acaso
            return "tarea_ejecutada_continuar_mision", contenido_mision_post_tarea


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
            manejadorGit.descartarCambiosLocales(ruta_repo)
            return "error_en_tarea", contenido_mision_actual_md
        
        commit_msg = f"Tarea ID {tarea_id} ({tarea_titulo[:50]}) completada (Misión {nombre_rama_mision})"
        if not manejadorGit.hacerCommit(ruta_repo, commit_msg): 
             logging.warning(f"{logPrefix} No se realizó commit para tarea (quizás sin cambios efectivos o fallo en git add/commit).")
             # Podría ser que los "archivos_modificados" por la IA no resultaran en cambios reales en disco.
             # O un fallo en `hacerCommit` que no es crítico para el flujo de la tarea.
    else:
        # Esto puede pasar si la IA devuelve advertencia Y archivos_modificados vacío.
        # Ya se manejó arriba si la advertencia implicaba saltar la tarea.
        # Si llegamos aquí sin "archivos_modificados" y sin advertencia que salte, es un estado anómalo.
        logging.info(f"{logPrefix} IA no especificó archivos modificados. Asumiendo sin cambios o ya manejado por advertencia.")

    contenido_mision_post_tarea = marcar_tarea_como_completada(contenido_mision_actual_md, tarea_id, "COMPLETADA")
    if not contenido_mision_post_tarea: return "error_en_tarea", contenido_mision_actual_md

    try:
        with open(ruta_mision_actual_md, 'w', encoding='utf-8') as f: f.write(contenido_mision_post_tarea)
        logging.info(f"{logPrefix} {MISION_ORION_MD} actualizado con tarea completada.")
    except Exception as e: logging.error(f"{logPrefix} Error guardando {MISION_ORION_MD}: {e}"); return "error_en_tarea", contenido_mision_actual_md

    if not manejadorGit.hacerCommitEspecifico(ruta_repo, f"Actualizar Misión '{nombre_rama_mision}', Tarea '{tarea_id}' completada", [MISION_ORION_MD]):
        logging.error(f"{logPrefix} No se pudo commitear actualización de {MISION_ORION_MD}.")
        # Similar a antes, no necesariamente fatal para el ciclo, pero el estado en disco puede no ser el esperado.
    
    manejadorHistorial.guardarHistorial(manejadorHistorial.cargarHistorial() + [
        manejadorHistorial.formatearEntradaHistorial(outcome=f"PASO2_TAREA_OK:{nombre_rama_mision}", decision=tarea_actual_info, result_details=resultado_ejecucion_tarea.get("archivos_modificados"))
    ])

    _, _, hay_pendientes_actualizada = parsear_mision_orion(contenido_mision_post_tarea)
    if hay_pendientes_actualizada:
        logging.info(f"{logPrefix} Quedan más tareas en misión '{nombre_rama_mision}'.")
        return "tarea_ejecutada_continuar_mision", contenido_mision_post_tarea
    else:
        logging.info(f"{logPrefix} Todas las tareas de misión '{nombre_rama_mision}' completadas.")
        # Devolvemos el contenido del mision.md por si es útil para el merge o log final
        return "mision_completada_para_merge", contenido_mision_post_tarea


# --- Función Principal del Ciclo Adaptativo (NUEVO) ---
def ejecutarCicloAdaptativo(api_provider: str, modo_test: bool):
    logPrefix = f"ejecutarCicloAdaptativo({api_provider.upper()}):"
    logging.info(f"{logPrefix} ===== INICIO CICLO ADAPTATIVO =====")
    registro_archivos_analizados = cargar_registro_archivos()
    if not _validarConfiguracionEsencial(api_provider): return False
    if api_provider == 'google' and settings.GEMINIAPIKEY and not analizadorCodigo.configurarGemini():
        logging.critical(f"{logPrefix} Falló config Google GenAI."); return False

    if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
        logging.error(f"{logPrefix} Falló preparación de repo en '{settings.RAMATRABAJO}'."); return False
    logging.info(f"{logPrefix} Repositorio listo en rama base: '{settings.RAMATRABAJO}'.")

    estado_agente = "revisar_mision_local"
    # Almacenarán los datos de la misión activa
    metadatos_mision_activa = None
    lista_tareas_mision_activa = None # Lista de dicts de tareas
    nombre_clave_mision_activa = None # El nombre clave, usado para la rama
    
    # Para la creación de misión
    decision_paso1_1_actual = None
    archivo_para_mision_actual = None
    archivos_contexto_para_crear_mision = None

    max_ciclos = getattr(settings, 'MAX_CICLOS_PRINCIPALES_AGENTE', 5)
    ciclos = 0

    while ciclos < max_ciclos:
        ciclos += 1
        logging.info(f"\n{logPrefix} --- Iteración Agente #{ciclos}/{max_ciclos} | Estado: {estado_agente} | Misión Activa: {nombre_clave_mision_activa or 'Ninguna'} ---")

        if estado_agente == "revisar_mision_local":
            logging.info(f"{logPrefix} Asegurando estar en '{settings.RAMATRABAJO}'.")
            if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                logging.error(f"{logPrefix} No se pudo volver a '{settings.RAMATRABAJO}'. Abortando."); break
            
            # Limpiar variables de misión previa
            metadatos_mision_activa, lista_tareas_mision_activa, nombre_clave_mision_activa = None, None, None
            decision_paso1_1_actual, archivo_para_mision_actual, archivos_contexto_para_crear_mision = None, None, None

            path_mision_trabajo_abs = os.path.join(settings.RUTACLON, MISION_ORION_MD)
            if os.path.exists(path_mision_trabajo_abs):
                try:
                    # Primero, intentar commitear si hay cambios (por si quedó de un ciclo anterior)
                    # Esto es opcional y depende de si queremos que sea tan robusto.
                    # Por ahora, lo eliminaremos directamente para simplificar, asumiendo que el estado es limpio.
                    os.remove(path_mision_trabajo_abs)
                    logging.info(f"{logPrefix} Eliminado {MISION_ORION_MD} de '{settings.RAMATRABAJO}' (si existía).")
                    # Intentar un commit si la eliminación causó un cambio.
                    # `hacerCommitEspecifico` devolverá False si no hay nada que commitear.
                    if manejadorGit.hacerCommitEspecifico(settings.RUTACLON, f"Limpiar {MISION_ORION_MD} de {settings.RAMATRABAJO}", [MISION_ORION_MD]):
                        logging.info(f"{logPrefix} Commit de limpieza de {MISION_ORION_MD} en '{settings.RAMATRABAJO}'.")
                    else: 
                        logging.debug(f"{logPrefix} No se hizo commit de limpieza (o no había {MISION_ORION_MD} para limpiar del staging).")
                except Exception as e_clean: logging.warning(f"{logPrefix} No se pudo limpiar {MISION_ORION_MD} de '{settings.RAMATRABAJO}': {e_clean}")
            
            res_paso0, meta, tareas, nombre_clave = paso0_revisar_mision_local(settings.RUTACLON)
            if res_paso0 == "procesar_mision_existente":
                metadatos_mision_activa, lista_tareas_mision_activa, nombre_clave_mision_activa = meta, tareas, nombre_clave
                logging.info(f"{logPrefix} Misión '{nombre_clave_mision_activa}' detectada. Ejecutando tarea.")
                estado_agente = "ejecutar_tarea_mision"
            elif res_paso0 == "crear_nueva_mision":
                logging.info(f"{logPrefix} No hay misión activa. Seleccionando archivo.")
                estado_agente = "seleccion_archivo"
            else: logging.error(f"{logPrefix} Resultado inesperado de paso0: {res_paso0}. Deteniendo."); break

        elif estado_agente == "seleccion_archivo":
            res_paso1_1, archivo_sel, ctx_sel, decision_ia = paso1_1_seleccion_y_decision_inicial(
                settings.RUTACLON, api_provider, registro_archivos_analizados)
            if res_paso1_1 == "generar_mision":
                archivo_para_mision_actual, archivos_contexto_para_crear_mision, decision_paso1_1_actual = archivo_sel, ctx_sel, decision_ia
                logging.info(f"{logPrefix} Archivo '{archivo_sel}' seleccionado. Generando misión.")
                estado_agente = "generar_mision_md"
            elif res_paso1_1 == "reintentar_seleccion":
                logging.info(f"{logPrefix} Paso 1.1 solicitó reintentar. Volviendo a revisar.")
                estado_agente = "revisar_mision_local" # Para un ciclo limpio
            elif res_paso1_1 == "ciclo_terminado_sin_accion":
                logging.info(f"{logPrefix} Paso 1.1 no encontró acción. Terminando agente."); break
            else: logging.error(f"{logPrefix} Resultado inesperado de paso1.1: {res_paso1_1}. Deteniendo."); break

        elif estado_agente == "generar_mision_md":
            res_paso1_2, mision_gen_contenido_md, nombre_clave = paso1_2_generar_mision(
                settings.RUTACLON, archivo_para_mision_actual,
                archivos_contexto_para_crear_mision, decision_paso1_1_actual, api_provider)
            if res_paso1_2 == "mision_generada_ok":
                # Parsear la misión recién generada para obtener metadatos y tareas estructuradas
                meta, tareas, _ = parsear_mision_orion(mision_gen_contenido_md)
                if not meta or not meta.get("nombre_clave"):
                    logging.error(f"{logPrefix} Misión generada pero no se pudo parsear correctamente. Abortando misión.")
                    manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO) # Volver a base
                    manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave, local=True) # Eliminar rama creada
                    estado_agente = "revisar_mision_local"; continue
                
                metadatos_mision_activa, lista_tareas_mision_activa, nombre_clave_mision_activa = meta, tareas, nombre_clave
                logging.info(f"{logPrefix} Misión '{nombre_clave_mision_activa}' generada. Ejecutando tarea.")
                estado_agente = "ejecutar_tarea_mision"
            elif res_paso1_2 == "error_generando_mision":
                logging.error(f"{logPrefix} Error generando misión. Volviendo a revisar.")
                manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO)
                nombre_clave_mision_activa = None # Limpiar estado de misión fallida
                estado_agente = "revisar_mision_local"
            else: logging.error(f"{logPrefix} Resultado inesperado de paso1.2: {res_paso1_2}. Deteniendo."); break
        
        elif estado_agente == "ejecutar_tarea_mision":
            if not nombre_clave_mision_activa or not metadatos_mision_activa or lista_tareas_mision_activa is None: # lista_tareas_mision_activa puede ser []
                logging.error(f"{logPrefix} Falta info de misión activa ('{nombre_clave_mision_activa}'). Volviendo a revisar.")
                estado_agente = "revisar_mision_local"; continue

            res_paso2, mision_actualizada_contenido_md = paso2_ejecutar_tarea_mision(
                settings.RUTACLON, metadatos_mision_activa, lista_tareas_mision_activa,
                nombre_clave_mision_activa, api_provider, modo_test
            )
            
            if res_paso2 == "tarea_ejecutada_continuar_mision":
                if mision_actualizada_contenido_md: # Asegurarse que no sea None
                    meta, tareas, _ = parsear_mision_orion(mision_actualizada_contenido_md)
                    if not meta: # Si falla el parseo, algo está mal
                        logging.error(f"{logPrefix} Misión actualizada no pudo ser parseada. Error de estado. Volviendo a revisar.")
                        estado_agente = "revisar_mision_local"; continue
                    metadatos_mision_activa, lista_tareas_mision_activa = meta, tareas
                else: # mision_actualizada_contenido_md fue None, error de estado
                    logging.error(f"{logPrefix} Contenido de misión fue None después de tarea. Error de estado. Volviendo a revisar.")
                    estado_agente = "revisar_mision_local"; continue

                logging.info(f"{logPrefix} Tarea ejecutada en '{nombre_clave_mision_activa}'. Quedan más.")
                estado_agente = "ejecutar_tarea_mision" # Continuar en la misma misión
            
            elif res_paso2 == "mision_completada_para_merge":
                logging.info(f"{logPrefix} Misión '{nombre_clave_mision_activa}' completada, lista para merge.")
                if not manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO):
                    logging.error(f"{logPrefix} No se pudo cambiar a '{settings.RAMATRABAJO}' para merge. Misión no mergeada.");
                elif manejadorGit.hacerMergeRama(settings.RUTACLON, nombre_clave_mision_activa, settings.RAMATRABAJO):
                    logging.info(f"{logPrefix} Merge de '{nombre_clave_mision_activa}' a '{settings.RAMATRABAJO}' exitoso.")
                    if modo_test:
                        # Antes de pushear, asegurar que la rama de trabajo esté actualizada con origin
                        logging.info(f"{logPrefix} Modo Test: Actualizando '{settings.RAMATRABAJO}' con su contraparte remota antes de push.")
                        # Comentado: Esta lógica podría ser compleja si RAMATRABAJO divergió. Un simple pull puede fallar.
                        # Por ahora, asumimos que el merge local es suficiente para el test y hacemos push directo.
                        # if not ejecutarComando(['git', 'pull', 'origin', settings.RAMATRABAJO], cwd=settings.RUTACLON, check=False):
                        #    logging.warning(f"{logPrefix} Falló pull de 'origin/{settings.RAMATRABAJO}'. Push podría fallar si hay divergencia.")

                        if manejadorGit.hacerPush(settings.RUTACLON, settings.RAMATRABAJO):
                            logging.info(f"{logPrefix} Push de '{settings.RAMATRABAJO}' exitoso (modo test).")
                            # Opcional: eliminar rama de misión remota si el push de la rama base fue exitoso
                            # if manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_mision_activa, local=False, remota=True):
                            #     logging.info(f"{logPrefix} Rama de misión '{nombre_clave_mision_activa}' eliminada remotamente.")
                    # Eliminar rama de misión local después de merge exitoso (o intento de push en modo test)
                    if manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_mision_activa, local=True, remota=False):
                         logging.info(f"{logPrefix} Rama de misión local '{nombre_clave_mision_activa}' eliminada.")
                else:
                    logging.error(f"{logPrefix} Falló merge de '{nombre_clave_mision_activa}' a '{settings.RAMATRABAJO}'. Rama de misión persiste.")
                
                nombre_clave_mision_activa = None; metadatos_mision_activa = None; lista_tareas_mision_activa = None
                estado_agente = "revisar_mision_local"

            elif res_paso2 == "mision_completada_sin_merge":
                logging.info(f"{logPrefix} Misión '{nombre_clave_mision_activa}' completada (sin tareas o todas saltadas, no requiere merge).")
                # Asegurar volver a la rama de trabajo principal
                manejadorGit.cambiar_a_rama_existente(settings.RUTACLON, settings.RAMATRABAJO)
                # Opcional: Limpiar rama de misión si no se va a mergear.
                if manejadorGit.eliminarRama(settings.RUTACLON, nombre_clave_mision_activa, local=True, remota=False):
                    logging.info(f"{logPrefix} Rama de misión '{nombre_clave_mision_activa}' eliminada localmente (sin merge).")
                
                nombre_clave_mision_activa = None; metadatos_mision_activa = None; lista_tareas_mision_activa = None
                estado_agente = "revisar_mision_local"

            elif res_paso2 == "error_en_tarea":
                logging.error(f"{logPrefix} Error ejecutando tarea en '{nombre_clave_mision_activa}'. Volviendo a revisar (la rama y misión persisten).")
                estado_agente = "revisar_mision_local"
            else:
                logging.error(f"{logPrefix} Resultado inesperado de paso2: {res_paso2}. Deteniendo."); break
        else:
            logging.error(f"{logPrefix} Estado desconocido: {estado_agente}. Deteniendo."); break

        delay_ciclo = getattr(settings, 'DELAY_ENTRE_CICLOS_AGENTE', 1)
        logging.debug(f"{logPrefix} Fin iteración. Pausando {delay_ciclo}s.")
        time.sleep(delay_ciclo)

    guardar_registro_archivos(registro_archivos_analizados)
    logging.info(f"{logPrefix} ===== FIN CICLO ADAPTATIVO (Iteraciones: {ciclos}) =====")
    return True


if __name__ == "__main__":
    configurarLogging()
    parser = argparse.ArgumentParser(
        description="Agente Adaptativo de Refactorización de Código con IA.",
        epilog="Ejecuta ciclos adaptativos de análisis, generación de misión y ejecución de tareas."
    )
    parser.add_argument("--modo-test", action="store_true", help="Activa modo prueba.")
    parser.add_argument("--openrouter", action="store_true", help="Utilizar OpenRouter.")
    args = parser.parse_args()
    codigo_salida = orchestrarEjecucionScript(args)
    logging.info(f"Script principal (adaptativo) finalizado con código: {codigo_salida}")
    sys.exit(codigo_salida)