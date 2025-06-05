import logging
import time
from datetime import datetime, timedelta
from config import settings

# Variable global para registrar el uso de tokens en una ventana de tiempo
token_usage_window = []

def gestionar_limite_tokens(tokens_a_usar_estimados: int, proveedor_api: str):
    global token_usage_window
    logPrefix = "token_manager.gestionar_limite_tokens:"
    ahora = datetime.now()
    # Limpiar la ventana de uso de tokens, manteniendo solo los de los últimos 60 segundos
    token_usage_window = [
        (ts, count) for ts, count in token_usage_window if ahora - ts < timedelta(seconds=60)
    ]
    tokens_usados_en_ventana = sum(count for _, count in token_usage_window)
    logging.debug(
        f"{logPrefix} Tokens usados en los últimos 60s: {tokens_usados_en_ventana}. A usar: {tokens_a_usar_estimados}")

    # Obtener el límite de tokens por minuto desde settings
    TOKEN_LIMIT_PER_MINUTE = getattr(settings, 'TOKEN_LIMIT_PER_MINUTE', 250000)

    if tokens_usados_en_ventana + tokens_a_usar_estimados > TOKEN_LIMIT_PER_MINUTE:
        # Calcular cuánto tiempo queda en la ventana actual o esperar 60 segundos si la ventana está vacía
        segundos_a_esperar = 60 - \
            (ahora - token_usage_window[0][0]
             ).total_seconds() if token_usage_window else 60
        segundos_a_esperar = max(1, int(segundos_a_esperar) + 1) # Asegurar al menos 1 segundo de espera
        logging.info(f"{logPrefix} Límite de tokens ({TOKEN_LIMIT_PER_MINUTE}/min) excedería. "
                     f"Usados: {tokens_usados_en_ventana}. A usar: {tokens_a_usar_estimados}. "
                     f"Pausando por {segundos_a_esperar} segundos...")
        time.sleep(segundos_a_esperar)
        # Recursivamente llamar de nuevo después de la espera
        return gestionar_limite_tokens(tokens_a_usar_estimados, proveedor_api)
    logging.info(
        f"{logPrefix} OK para proceder con {tokens_a_usar_estimados} tokens (estimados).")
    return True

def registrar_tokens_usados(tokens_usados: int):
    global token_usage_window
    token_usage_window.append((datetime.now(), tokens_usados))
    ahora = datetime.now()
    # Limpiar la ventana de uso de tokens, manteniendo solo los de los últimos 60 segundos
    token_usage_window = [
        (ts, count) for ts, count in token_usage_window if ahora - ts < timedelta(seconds=60)
    ]
    tokens_usados_en_ventana_actual = sum(
        count for _, count in token_usage_window)
    # Obtener el límite de tokens por minuto desde settings para el mensaje de log
    TOKEN_LIMIT_PER_MINUTE = getattr(settings, 'TOKEN_LIMIT_PER_MINUTE', 250000)
    logging.debug(
        f"token_manager.registrar_tokens_usados: Registrados {tokens_usados} tokens. Ventana actual ({TOKEN_LIMIT_PER_MINUTE}/min): {tokens_usados_en_ventana_actual} tokens usados.")
