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
            buffer = ""
            for line in f:
                if line.strip() == "--- END ENTRY ---":
                    if buffer:
                        historial.append(buffer.strip())
                        buffer = ""
                else:
                    buffer += line
            if buffer:
                historial.append(buffer.strip())
        log.info(
            f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        log.error(
            f"{logPrefix} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío.")
        historial = []
    return historial


def guardarHistorial(historial):
    logPrefix = "guardarHistorial:"
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    try:
        os.makedirs(os.path.dirname(rutaArchivoHistorial), exist_ok=True)
        entradas_filtradas_paso1 = 0
        with open(rutaArchivoHistorial, 'w', encoding='utf-8') as f:
            for entrada in historial:
                if "[[ERROR_PASO1]]" in entrada:
                    entradas_filtradas_paso1 += 1
                    pass
                else:
                    f.write(entrada.strip() + "\n")
                    f.write("--- END ENTRY ---\n")

        num_entradas_originales = len(historial)
        num_entradas_guardadas = num_entradas_originales - entradas_filtradas_paso1

        if entradas_filtradas_paso1 > 0:
            log.warning(
                f"{logPrefix} **TEMPORALMENTE** se filtraron y NO se guardaron {entradas_filtradas_paso1} entradas con '[[ERROR_PASO1]]'.")

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
