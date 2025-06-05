import os
import logging
import json
from datetime import datetime
from config import settings

log = logging.getLogger(__name__)


def cargarHistorial():
    logPrefix = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    if not os.path.exists(rutaArchivoHistorial):
        log.info(
            f"{logPrefix} Archivo de historial no encontrado en {rutaArchivoHistorial}. Iniciando historial vacío.")
        return historial
    try:
        with open(rutaArchivoHistorial, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                # Ignorar el antiguo delimitador si todavía existe en el archivo
                if stripped_line == "--- END ENTRY ---":
                    log.debug(f"{logPrefix} Saltando delimitador de entrada antiguo en línea {line_num}.")
                    continue
                try:
                    entry = json.loads(stripped_line)
                    historial.append(entry)
                except json.JSONDecodeError as e:
                    log.warning(
                        f"{logPrefix} Error parseando línea {line_num} como JSON en {rutaArchivoHistorial}: {e}. Línea: '{stripped_line[:100]}...' (Esta línea será ignorada).")
                    continue
        log.info(
            f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas JSON)."
        )
    except Exception as e:
        log.error(
            f"{logPrefix} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío."
        )
        historial = []
    return historial


def guardarHistorial(historial):
    logPrefix = "guardarHistorial:"
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    try:
        os.makedirs(os.path.dirname(rutaArchivoHistorial), exist_ok=True)
        entradas_filtradas_error = 0
        with open(rutaArchivoHistorial, 'w', encoding='utf-8') as f:
            for entrada_dict in historial:
                # Check for the specific error status in the 'outcome' field
                if entrada_dict.get("outcome") == "[[ERROR_PASO1]]":
                    entradas_filtradas_error += 1
                    log.debug(f"{logPrefix} Filtrando entrada con outcome '[[ERROR_PASO1]]'.")
                    continue # Skip saving this entry
                else:
                    # If not filtered, serialize the dict back to a JSON string and write it
                    f.write(json.dumps(entrada_dict, ensure_ascii=False) + "\n")

        num_entradas_originales = len(historial)
        num_entradas_guardadas = num_entradas_originales - entradas_filtradas_error

        if entradas_filtradas_error > 0:
            log.warning(
                f"{logPrefix} Se filtraron y NO se guardaron {entradas_filtradas_error} entradas con '[[ERROR_PASO1]]' en el campo 'outcome'.")

        log.info(
            f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({num_entradas_guardadas} entradas escritas de {num_entradas_originales} originales).")
        return True
    except Exception as e:
        log.error(
            f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False


def formatearEntradaHistorial(outcome, decision=None, result_details=None, verification_details=None, error_message=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry_data = {
        "timestamp": timestamp,
        "outcome": outcome,
        "decision": None,
        "result_details": None,
        "verification_details": None,
        "error_message": None
    }

    if decision is not None:
        entry_data["decision"] = decision

    if result_details is not None:
        entry_data["result_details"] = result_details

    if verification_details is not None:
        entry_data["verification_details"] = verification_details

    if error_message is not None:
        entry_data["error_message"] = error_message

    return json.dumps(entry_data, ensure_ascii=False)
