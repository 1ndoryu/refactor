# nucleo/manejadorMisiones.py
import logging
import re

log = logging.getLogger(__name__)


def _parse_tarea_individual(tarea_buffer: dict):
    logPrefix = "_parse_tarea_individual:"
    if not tarea_buffer or not tarea_buffer.get("raw_lines"):
        return None
    
    lineas_tarea = tarea_buffer["raw_lines"]
    tarea_dict = {
        "id": None, "titulo": None, "estado": "PENDIENTE", 
        "descripcion": "", "archivos_implicados_especificos": [], "intentos": 0,
        "bloques_codigo_objetivo": [], # Nueva lista para bloques de código
        "raw_lines": lineas_tarea,
        "line_start_index": tarea_buffer.get("line_start_index", -1),
        "line_end_index": tarea_buffer.get("line_start_index", -1) + len(lineas_tarea) -1 if tarea_buffer.get("line_start_index", -1) != -1 else -1
    }
    descripcion_parts = []
    in_descripcion = False
    parsing_bloques_codigo = False
    current_block_info = None

    match_titulo_linea = lineas_tarea[0] if lineas_tarea else ""
    match_titulo_encabezado = re.match(r"###\s*Tarea\s*([\w.-]+):\s*(.+)", match_titulo_linea, re.IGNORECASE)
    if match_titulo_encabezado:
        tarea_dict["id_titulo"] = match_titulo_encabezado.group(1).strip()
        tarea_dict["titulo"] = match_titulo_encabezado.group(2).strip()
    else:
        logging.warning(f"{logPrefix} No se pudo parsear ID/Título del encabezado de la tarea: '{match_titulo_linea}'")

    id_del_campo_encontrado = None

    for linea_original_tarea in lineas_tarea[1:]:
        linea_strip_para_campos_std = linea_original_tarea.strip()

        # Primero, verificar si estamos saliendo de la sección de bloques de código
        # o si es un campo de tarea estándar, lo cual también finaliza la sección de bloques.
        es_campo_tarea_estandar = (
            re.match(r"-\s*\*\*ID:\*\*", linea_original_tarea, re.I) or
            re.match(r"-\s*\*\*Estado:\*\*", linea_original_tarea, re.I) or
            re.match(r"-\s*\*\*Intentos:\*\*", linea_original_tarea, re.I) or
            re.match(r"-\s*\*\*Archivos Implicados .*:\*\*", linea_original_tarea, re.I) or
            re.match(r"-\s*\*\*Descripción:\*\*", linea_original_tarea, re.I)
        )

        if es_campo_tarea_estandar and parsing_bloques_codigo:
            if current_block_info:
                tarea_dict["bloques_codigo_objetivo"].append(current_block_info)
                current_block_info = None
            parsing_bloques_codigo = False
        
        # --- Procesamiento de campos de Bloques de Código Objetivo ---
        if parsing_bloques_codigo:
            match_archivo_bloque = re.match(r"\s*-\s*\*\*Archivo:\*\*\s*(.+)", linea_original_tarea, re.I)
            match_nombre_bloque = re.match(r"\s*-\s*\*\*Nombre Bloque:\*\*\s*(.+)", linea_original_tarea, re.I)
            match_linea_inicio = re.match(r"\s*-\s*\*\*Línea Inicio:\*\*\s*(\d+)", linea_original_tarea, re.I)
            match_linea_fin = re.match(r"\s*-\s*\*\*Línea Fin:\*\*\s*(\d+)", linea_original_tarea, re.I)

            if match_archivo_bloque:
                if current_block_info: # Guardar bloque anterior si existe
                    # Validar que el bloque anterior tenga los campos esperados antes de guardarlo
                    if all(k in current_block_info for k in ["archivo", "nombre_bloque", "linea_inicio", "linea_fin"]):
                        tarea_dict["bloques_codigo_objetivo"].append(current_block_info)
                    else:
                        logging.warning(f"{logPrefix} Bloque de código anterior incompleto, no se guardó: {current_block_info} en tarea ID '{tarea_dict.get('id_titulo','??')}'")
                current_block_info = {"archivo": match_archivo_bloque.group(1).strip().replace('`', '')}
                in_descripcion = False # Salir de descripción si estábamos
                continue 
            elif match_nombre_bloque and current_block_info:
                current_block_info["nombre_bloque"] = match_nombre_bloque.group(1).strip().replace('`', '')
                in_descripcion = False
                continue
            elif match_linea_inicio and current_block_info:
                try:
                    current_block_info["linea_inicio"] = int(match_linea_inicio.group(1).strip())
                except ValueError:
                    logging.warning(f"{logPrefix} Valor no entero para Línea Inicio: '{match_linea_inicio.group(1).strip()}' en tarea ID '{tarea_dict.get('id_titulo','??')}'")
                in_descripcion = False
                continue
            elif match_linea_fin and current_block_info:
                try:
                    current_block_info["linea_fin"] = int(match_linea_fin.group(1).strip())
                except ValueError:
                    logging.warning(f"{logPrefix} Valor no entero para Línea Fin: '{match_linea_fin.group(1).strip()}' en tarea ID '{tarea_dict.get('id_titulo','??')}'")
                in_descripcion = False
                continue
            elif linea_original_tarea.strip() == "": # Ignorar líneas vacías dentro de la sección de bloques
                continue
            # Si no es un campo de bloque conocido y no es una línea vacía, podría ser un error de formato o el final.
            # Si es un campo de tarea estándar, ya se manejó arriba.
            # Si es cualquier otra cosa, y estamos en parsing_bloques_codigo, es mejor terminar.
            elif not es_campo_tarea_estandar: 
                # Podría ser una línea de comentario o texto mal formateado dentro de la sección de bloques.
                # Por ahora, si no es un campo de bloque reconocido, terminamos la sección de bloques.
                if current_block_info:
                    if all(k in current_block_info for k in ["archivo", "nombre_bloque", "linea_inicio", "linea_fin"]):
                        tarea_dict["bloques_codigo_objetivo"].append(current_block_info)
                    else:
                        logging.warning(f"{logPrefix} Bloque de código al finalizar sección por línea no reconocida, incompleto: {current_block_info} en tarea ID '{tarea_dict.get('id_titulo','??')}'")
                    current_block_info = None
                parsing_bloques_codigo = False
                # No hacer 'continue' aquí, la línea podría ser un campo de tarea estándar o el inicio de descripción.
        
        # --- Procesamiento de campos de tarea estándar ---
        match_id_campo_explicito = re.match(r"-\s*\*\*ID:\*\*\s*([\w.-]+)", linea_original_tarea, re.I)
        if match_id_campo_explicito: 
            id_del_campo_encontrado = match_id_campo_explicito.group(1).strip()
            in_descripcion = False
            continue

        match_estado = re.match(r"-\s*\*\*Estado:\*\*\s*(PENDIENTE|COMPLETADA|SALTADA|FALLIDA_TEMPORALMENTE|FALLIDA_PERMANENTEMENTE)", linea_original_tarea, re.I)
        if match_estado: 
            tarea_dict["estado"] = match_estado.group(1).upper().strip()
            in_descripcion = False
            continue
        
        match_intentos = re.match(r"-\s*\*\*Intentos:\*\*\s*(\d+)", linea_original_tarea, re.I)
        if match_intentos: 
            tarea_dict["intentos"] = int(match_intentos.group(1).strip())
            in_descripcion = False
            continue

        match_aie = re.match(r"-\s*\*\*Archivos Implicados .*:\*\*\s*(.+)", linea_original_tarea, re.I)
        if match_aie:
            archivos_str = match_aie.group(1).strip()
            if archivos_str and archivos_str.lower() not in ["ninguno", "opcional:", "ninguno."]:
                tarea_dict["archivos_implicados_especificos"] = [a.strip() for a in archivos_str.split(',') if a.strip()]
            in_descripcion = False
            continue
        
        match_bloques_header = re.match(r"-\s*\*\*Bloques de Código Objetivo:\*\*\s*(.*)", linea_original_tarea, re.I)
        if match_bloques_header:
            parsing_bloques_codigo = True
            in_descripcion = False 
            if current_block_info: # Si por alguna razón ya había un bloque (no debería)
                 logging.warning(f"{logPrefix} Se encontró encabezado de Bloques de Código con un current_block_info ya existente. Descartando el previo: {current_block_info}")
                 current_block_info = None
            continue

        match_desc_start = re.match(r"-\s*\*\*Descripción:\*\*\s*(.*)", linea_original_tarea, re.I)
        if match_desc_start:
            in_descripcion = True
            # Si estábamos parseando bloques, y encontramos Descripción, finalizamos el bloque actual.
            if parsing_bloques_codigo:
                if current_block_info:
                    if all(k in current_block_info for k in ["archivo", "nombre_bloque", "linea_inicio", "linea_fin"]):
                        tarea_dict["bloques_codigo_objetivo"].append(current_block_info)
                    else:
                        logging.warning(f"{logPrefix} Bloque de código al iniciar descripción, incompleto: {current_block_info} en tarea ID '{tarea_dict.get('id_titulo','??')}'")
                    current_block_info = None
                parsing_bloques_codigo = False

            desc_first_line = match_desc_start.group(1).strip()
            if desc_first_line: 
                descripcion_parts.append(desc_first_line)
            continue

        if in_descripcion and not re.match(r"-\s*\*\*\w+:\*\*", linea_original_tarea):
             descripcion_parts.append(linea_original_tarea.strip())

    # Finalizar el último bloque de código si existe
    if current_block_info:
        if all(k in current_block_info for k in ["archivo", "nombre_bloque", "linea_inicio", "linea_fin"]):
            tarea_dict["bloques_codigo_objetivo"].append(current_block_info)
        else:
            logging.warning(f"{logPrefix} Último bloque de código al final de la tarea, incompleto: {current_block_info} en tarea ID '{tarea_dict.get('id_titulo','??')}'")
    
    id_del_titulo = tarea_dict.pop("id_titulo", None)
    if id_del_titulo and id_del_campo_encontrado:
        if id_del_titulo == id_del_campo_encontrado:
            tarea_dict["id"] = id_del_titulo
            logging.debug(f"{logPrefix} ID del título y del campo coinciden: '{tarea_dict['id']}'.")
        else:
            logging.error(f"{logPrefix} ¡DISCREPANCIA FATAL DE ID! ID en encabezado de tarea ('{id_del_titulo}') "
                          f"difiere de ID en campo '- **ID:**' ('{id_del_campo_encontrado}'). "
                          f"Formato de misión inválido para la tarea en líneas {tarea_dict['line_start_index']}-{tarea_dict['line_end_index']}. Tarea ignorada.")
            return None
    elif id_del_titulo:
        tarea_dict["id"] = id_del_titulo
        logging.debug(f"{logPrefix} Usando ID del encabezado de tarea: '{id_del_titulo}'.")
    elif id_del_campo_encontrado:
        tarea_dict["id"] = id_del_campo_encontrado
        logging.debug(f"{logPrefix} Usando ID del campo '- **ID:**': '{id_del_campo_encontrado}'.")
    else:
        logging.error(f"{logPrefix} Tarea parseada SIN ID. No se encontró ID en el encabezado (### Tarea ID: Título) ni en un campo '- **ID:** ID'. Líneas: {tarea_dict['raw_lines']}")
        return None

    tarea_dict["descripcion"] = "\n".join(descripcion_parts).strip()
    
    if not tarea_dict["id"]:
        logging.error(f"{logPrefix} Error Lógico: Tarea finalizada sin ID a pesar de las validaciones. Líneas: {tarea_dict['raw_lines']}")
        return None
        
    logging.debug(f"{logPrefix} Tarea parseada. ID: '{tarea_dict['id']}', Título: '{tarea_dict['titulo']}', Estado: '{tarea_dict['estado']}', Bloques: {len(tarea_dict['bloques_codigo_objetivo'])}")
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

