import os
import logging
import json  # Para formatearEntradaHistorial
from datetime import datetime  # Para formatearEntradaHistorial
from config import settings

log = logging.getLogger(__name__)


def cargarHistorial():
    logPrefix = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    if not os.path.exists(rutaArchivoHistorial):
        logging.info(
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
        logging.info(
            f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        logging.error(
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
            logging.warning(
                f"{logPrefix} **TEMPORALMENTE** se filtraron y NO se guardaron {entradas_filtradas_paso1} entradas con '[[ERROR_PASO1]]'.")

        logging.info(
            f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({num_entradas_guardadas} entradas escritas de {num_entradas_originales} originales).")
        return True
    except Exception as e:
        logging.error(
            f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False


def formatearEntradaHistorial(outcome, decision=None, result_details=None, verification_details=None, error_message=None):
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
        if isinstance(result_details, dict):
            keys_only = list(result_details.keys())
            entry += f"    Archivos Generados/Modificados: {keys_only}\n"
        else:
            entry += f"    Detalles: {result_details}\n"

    if verification_details:
        entry += f"  Verificacion (Paso 3):\n"
        entry += f"    Detalles: {verification_details}\n"

    if error_message:
        entry += f"  Error: {error_message}\n"

    return entry.strip()
