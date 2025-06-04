# principal.py

import logging
import sys
import os
import json
import argparse
import subprocess
import time
import signal
from datetime import datetime
from config import settings
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios
from nucleo import manejadorHistorial


class TimeoutException(Exception):
    """Excepción para indicar que el tiempo límite de ejecución fue alcanzado."""
    pass


def orchestrarEjecucionScript(args):
    api_provider_seleccionado = "openrouter" if args.openrouter else "google"

    logging.info(
        f"Iniciando lógica de orquestación. Proveedor API: {api_provider_seleccionado.upper()}. Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    if api_provider_seleccionado == 'google' and not settings.GEMINIAPIKEY:
        logging.critical(
            "Error: Se seleccionó Google Gemini pero GEMINI_API_KEY no está configurada en .env o settings.py. Abortando.")
        return 2
    elif api_provider_seleccionado == 'openrouter' and not settings.OPENROUTER_API_KEY:
        logging.critical(
            "Error: Se seleccionó OpenRouter (--openrouter) pero OPENROUTER_API_KEY no está configurada en .env o settings.py. Abortando.")
        return 2

    # TIMEOUT_SECONDS ahora viene de settings
    if hasattr(signal, 'SIGALRM'):
        logging.info(
            f"Configurando timeout de ejecución a {settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS} segundos usando signal.alarm.")
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS)
    else:
        logging.warning(
            "signal.alarm no está disponible en este sistema operativo (ej. Windows). El timeout de ejecución general no estará activo.")

    exit_code = 1

    try:
        cicloTuvoExitoConCommit = ejecutarProcesoPrincipal(
            api_provider=api_provider_seleccionado)

        if cicloTuvoExitoConCommit:
            logging.info(
                "Proceso principal completado: Se realizó un commit con cambios efectivos.")
            if args.modo_test:
                logging.info("Modo Test activado: Intentando hacer push...")
                ramaPush = getattr(settings, 'RAMATRABAJO', 'main')
                if manejadorGit.hacerPush(settings.RUTACLON, ramaPush):
                    logging.info(
                        f"Modo Test: Push a la rama '{ramaPush}' realizado con éxito.")
                    exit_code = 0
                else:
                    logging.error(
                        f"Modo Test: Falló el push a la rama '{ramaPush}'. El commit local se mantiene.")
                    exit_code = 1
            else:
                logging.info(
                    "Modo Test desactivado. Commit local realizado, no se hizo push.")
                exit_code = 0
        else:
            logging.warning(
                "Proceso principal finalizó SIN realizar un commit efectivo (puede ser por 'no_accion', error, fallo de verificación, API inestable o commit sin cambios). Verifique logs e historial.")
            exit_code = 1

    except TimeoutException as e:
        logging.critical(
            f"TIMEOUT: El script fue terminado porque excedió el límite de {settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS} segundos.")
        try:
            historial = manejadorHistorial.cargarHistorial()
            historial.append(manejadorHistorial.formatearEntradaHistorial(
                outcome="[TIMEOUT]", error_message=str(e)))
            manejadorHistorial.guardarHistorial(historial)
            logging.info(
                "Intentando guardar historial tras timeout (puede fallar).")
        except Exception as e_hist_timeout:
            logging.error(
                f"Fallo al guardar historial durante manejo de timeout: {e_hist_timeout}")
        exit_code = 124

    except Exception as e:
        logging.critical(
            f"Error fatal no manejado en orquestación: {e}", exc_info=True)
        try:
            historial = manejadorHistorial.cargarHistorial()
            historial.append(manejadorHistorial.formatearEntradaHistorial(
                outcome="[ERROR_FATAL_ORQUESTRACION]", error_message=str(e)))
            manejadorHistorial.guardarHistorial(historial)
        except Exception as e_hist_fatal:
            logging.error(
                f"No se pudo guardar historial del error fatal: {e_hist_fatal}")
        exit_code = 2

    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
            logging.debug("Alarma de timeout cancelada.")

    return exit_code


def _validarConfiguracionEsencial(api_provider: str) -> bool:
    """Valida que la configuración esencial (API Keys, Repo URL) esté presente."""
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
        return False  # Proveedor desconocido es un fallo de configuración

    if not configuracion_ok:
        # Este log es un poco redundante si ya se logueó arriba, pero confirma el fallo.
        logging.critical(
            f"{logPrefix} Configuración esencial faltante para proveedor '{api_provider}' o REPOSITORIOURL. Abortando.")
        return False

    logging.info(
        f"{logPrefix} Configuración esencial validada para proveedor '{api_provider}'.")
    return True


def _timeout_handler(signum, frame):
    """Manejador para la señal SIGALRM. Lanza TimeoutException."""
    logging.error("¡Tiempo límite de ejecución alcanzado!")
    raise TimeoutException("El script excedió el tiempo máximo de ejecución.")


def configurarLogging():
    log_raiz = logging.getLogger()
    if log_raiz.handlers:
        return
    nivelLog = logging.INFO
    formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'
    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    log_raiz.addHandler(consolaHandler)
    try:
        rutaLogArchivo = os.path.join(
            settings.RUTA_BASE_PROYECTO, "refactor.log")
        os.makedirs(os.path.dirname(rutaLogArchivo), exist_ok=True)
        archivoHandler = logging.FileHandler(rutaLogArchivo, encoding='utf-8')
        archivoHandler.setFormatter(
            logging.Formatter(formatoLog, fechaFormato))
        log_raiz.addHandler(archivoHandler)
    except Exception as e:
        log_raiz.error(
            f"configurarLogging: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}")
    log_raiz.setLevel(nivelLog)
    logging.info("="*50)
    logging.info("configurarLogging: Sistema de logging configurado.")
    logging.info(
        f"configurarLogging: Nivel de log establecido a {logging.getLevelName(log_raiz.level)}")


def parsearDecisionGemini(decisionJson):
    logPrefix = "parsearDecision:"
    accionesSoportadas = [
        "mover_funcion", "mover_clase", "modificar_codigo_en_archivo",
        "crear_archivo", "eliminar_archivo", "crear_directorio", "no_accion"
    ]

    if not isinstance(decisionJson, dict):
        logging.error(
            f"{logPrefix} La decisión recibida no es un diccionario JSON válido. Tipo: {type(decisionJson)}. Valor: {decisionJson}")
        return None

    tipoAnalisis = decisionJson.get("tipo_analisis")
    accionPropuesta = decisionJson.get("accion_propuesta")
    descripcion = decisionJson.get("descripcion")
    parametrosAccion = decisionJson.get("parametros_accion")
    archivosRelevantes = decisionJson.get("archivos_relevantes")
    razonamiento = decisionJson.get("razonamiento")

    if tipoAnalisis != "refactor_decision":
        logging.error(
            f"{logPrefix} JSON inválido. Falta o es incorrecto 'tipo_analisis'. Debe ser 'refactor_decision'. JSON: {decisionJson}")
        return None

    if not all([accionPropuesta, isinstance(parametrosAccion, dict), descripcion, isinstance(archivosRelevantes, list), razonamiento]):
        logging.error(f"{logPrefix} Formato JSON de decisión inválido. Faltan campos clave ('accion_propuesta', 'descripcion', 'parametros_accion', 'archivos_relevantes', 'razonamiento') o tipos incorrectos. JSON: {decisionJson}")
        return None

    if accionPropuesta not in accionesSoportadas:
        logging.error(
            f"{logPrefix} Acción propuesta '{accionPropuesta}' NO RECONOCIDA o NO SOPORTADA. Válidas: {accionesSoportadas}. JSON: {decisionJson}")
        return None

    if accionPropuesta != "no_accion" and not archivosRelevantes and accionPropuesta not in ["crear_directorio"]:
        logging.warning(
            f"{logPrefix} Acción '{accionPropuesta}' usualmente requiere 'archivos_relevantes', pero la lista está vacía. Esto podría ser un error en el Paso 1.")

    if accionPropuesta == "no_accion":
        logging.info(
            f"{logPrefix} Decisión 'no_accion' recibida y parseada. Razón: {razonamiento or 'No proporcionada'}")
    else:
        logging.info(
            f"{logPrefix} Decisión parseada exitosamente. Acción: {accionPropuesta}. Archivos: {archivosRelevantes}. Razón: {razonamiento[:100]}...")

    return decisionJson


def parsearResultadoEjecucion(resultadoJson):
    logPrefix = "parsearResultadoEjecucion:"

    if not isinstance(resultadoJson, dict):
        logging.error(
            f"{logPrefix} El resultado recibido no es un diccionario JSON válido. Tipo: {type(resultadoJson)}. Valor: {resultadoJson}")
        return None

    tipoResultado = resultadoJson.get("tipo_resultado")
    archivosModificados = resultadoJson.get("archivos_modificados")

    if tipoResultado != "ejecucion_cambio":
        logging.error(
            f"{logPrefix} JSON inválido. Falta o es incorrecto 'tipo_resultado'. Debe ser 'ejecucion_cambio'. JSON: {resultadoJson}")
        return None

    if not isinstance(archivosModificados, dict):
        if accionOriginal := resultadoJson.get("accion_original_debug"):
            if accionOriginal in ["eliminar_archivo", "crear_directorio"] and archivosModificados == {}:
                logging.info(
                    f"{logPrefix} Resultado de ejecución parseado: Diccionario 'archivos_modificados' vacío, lo cual es esperado para la acción '{accionOriginal}'.")
                return {}
            else:
                logging.error(
                    f"{logPrefix} Formato JSON de resultado inválido. 'archivos_modificados' no es un diccionario (y no es acción sin modificación). JSON: {resultadoJson}")
                return None
        else:
            logging.error(
                f"{logPrefix} Formato JSON de resultado inválido. Falta 'archivos_modificados' o no es un diccionario. JSON: {resultadoJson}")
            return None

    for ruta, contenido in archivosModificados.items():
        if not isinstance(ruta, str) or not isinstance(contenido, str):
            logging.error(
                f"{logPrefix} Entrada inválida en 'archivos_modificados'. Clave o valor no son strings. Clave: {ruta} (tipo {type(ruta)}), Valor (tipo {type(contenido)}). JSON: {resultadoJson}")
            return None

    logging.info(
        f"{logPrefix} Resultado de ejecución parseado exitosamente. {len(archivosModificados)} archivos a modificar.")
    return archivosModificados


def verificarCambiosAplicados(decisionParseada, resultadoEjecucion, rutaRepo):
    logPrefix = "verificarCambiosAplicados (Paso 3):"
    logging.info(f"{logPrefix} Iniciando verificación...")

    archivosIntencion = set(decisionParseada.get('archivos_relevantes', []))
    accion = decisionParseada.get('accion_propuesta')
    params = decisionParseada.get('parametros_accion', {})
    if accion in ["mover_funcion", "mover_clase"]:
        archivosIntencion.add(params.get("archivo_origen"))
        archivosIntencion.add(params.get("archivo_destino"))
    elif accion in ["modificar_codigo_en_archivo", "eliminar_archivo"]:
        archivosIntencion.add(params.get("archivo"))
    elif accion == "crear_archivo":
        archivosIntencion.add(params.get("archivo"))
    archivosIntencion.discard(None)
    logging.debug(
        f"{logPrefix} Archivos según Intención (Paso 1): {archivosIntencion}")

    archivosGenerados = set(resultadoEjecucion.keys())
    logging.debug(
        f"{logPrefix} Archivos con contenido Generado (Paso 2): {archivosGenerados}")

    archivosRealesModificados = manejadorGit.obtenerArchivosModificadosStatus(
        rutaRepo)
    if archivosRealesModificados is None:
        err = "No se pudo obtener el estado de los archivos de Git."
        logging.error(f"{logPrefix} {err}")
        return False, err
    logging.debug(
        f"{logPrefix} Archivos Modificados/Nuevos/Eliminados (Git Status): {archivosRealesModificados}")

    inconsistencias = []

    inesperadosGenerados = archivosGenerados - archivosIntencion
    if inesperadosGenerados:
        if not (accion == "crear_archivo" and inesperadosGenerados == {params.get("archivo")}):
            msg = f"IA (Paso 2) generó contenido para archivos inesperados: {inesperadosGenerados}"
            logging.warning(f"{logPrefix} {msg}")
            inconsistencias.append(msg)

    inesperadosModificados = archivosRealesModificados - archivosIntencion
    if inesperadosModificados:
        msg = f"Se detectaron cambios en archivos inesperados (no en intención Paso 1): {inesperadosModificados}"
        logging.warning(f"{logPrefix} {msg}")
        inconsistencias.append(msg)

    if not accion in ["eliminar_archivo", "crear_directorio"]:
        faltantesModificados = archivosGenerados - archivosRealesModificados
        if faltantesModificados and accion != "crear_archivo":
            realmente_faltantes = set()
            for faltante in faltantesModificados:
                ruta_abs_faltante = aplicadorCambios._validar_y_normalizar_ruta(
                    faltante, rutaRepo, asegurar_existencia=False)
                contenido_original = ""
                if ruta_abs_faltante and os.path.exists(ruta_abs_faltante):
                    try:
                        with open(ruta_abs_faltante, 'r', encoding='utf-8', errors='ignore') as f_orig:
                            contenido_original = f_orig.read()
                    except Exception:
                        pass
                if resultadoEjecucion.get(faltante) != contenido_original:
                    realmente_faltantes.add(faltante)

            if realmente_faltantes:
                msg = f"Archivos con contenido generado por IA (Paso 2) parecen no haber sido modificados en disco (o el cambio fue revertido/fallido): {realmente_faltantes}"
                logging.warning(f"{logPrefix} {msg}")
                inconsistencias.append(msg)

    if accion == "eliminar_archivo":
        archivo_a_eliminar = params.get("archivo")
        if archivo_a_eliminar in archivosRealesModificados:
            ruta_abs_eliminar = aplicadorCambios._validar_y_normalizar_ruta(
                archivo_a_eliminar, rutaRepo, asegurar_existencia=False)
            if ruta_abs_eliminar and os.path.exists(ruta_abs_eliminar):
                msg = f"Se pidió eliminar '{archivo_a_eliminar}' pero todavía existe."
                logging.warning(f"{logPrefix} {msg}")
                inconsistencias.append(msg)

    if inconsistencias:
        mensaje_final = "Verificación fallida. Inconsistencias detectadas:\n- " + \
            "\n- ".join(inconsistencias)
        logging.error(f"{logPrefix} {mensaje_final}")
        return False, mensaje_final
    else:
        msg = "OK. Los cambios aplicados parecen consistentes con la intención."
        logging.info(f"{logPrefix} {msg}")
        return True, msg


def ejecutarProcesoPrincipal(api_provider: str):
    logPrefix = f"ejecutarProcesoPrincipal({api_provider.upper()}):"
    logging.info(
        f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN (Proveedor: {api_provider.upper()}) =====")
    historialRefactor = []
    decisionParseada = None
    resultadoEjecucion = None
    # archivosModificadosGit = None # Esta variable no se usa, la comento/elimino
    estadoFinal = "[INICIO]"

    try:
        if not _validarConfiguracionEsencial(api_provider):
            return False

        # Configurar Gemini globalmente si es el proveedor y la clave está disponible
        if api_provider == 'google':
            if settings.GEMINIAPIKEY:
                try:
                    import google.generativeai as genai # Asegurar importación local si no está global
                    genai.configure(api_key=settings.GEMINIAPIKEY)
                    logging.info(f"{logPrefix} Google GenAI configurado globalmente para este ciclo.")
                except ImportError:
                    logging.error(f"{logPrefix} No se pudo importar google.generativeai. El conteo de tokens y las llamadas a Gemini fallarán.")
                except Exception as e_config_genai:
                    logging.error(f"{logPrefix} Error al configurar google.generativeai globalmente: {e_config_genai}")
            else:
                logging.warning(f"{logPrefix} Proveedor es Google, pero GEMINIAPIKEY no está disponible. El conteo de tokens y llamadas a Gemini podrían fallar.")


        historialRefactor = manejadorHistorial.cargarHistorial()

        logging.info(f"{logPrefix} Preparando repositorio local...")
        if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(f"{logPrefix} Falló la preparación del repositorio.")
            estadoFinal = "[ERROR_GIT_SETUP]"
            historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                outcome=estadoFinal,
                error_message="Fallo al clonar o actualizar repositorio."
            ))
            manejadorHistorial.guardarHistorial(historialRefactor)
            return False
        logging.info(
            f"{logPrefix} Repositorio listo y en la rama '{settings.RAMATRABAJO}'.")

        estructura_proyecto_str = ""
        try:
            logging.info(
                f"{logPrefix} Generando estructura del proyecto para contexto...")
            ignorados_setting = getattr(settings, 'DIRECTORIOS_IGNORADOS', [
                                        '.git', 'vendor', 'node_modules', '.github', 'assets', 'Tests', 'languages'])
            estructura_proyecto_str = analizadorCodigo.generarEstructuraDirectorio(
                settings.RUTACLON,
                directorios_ignorados=ignorados_setting,
                max_depth=8,
                incluir_archivos=True
            )
            if not estructura_proyecto_str:
                logging.warning(
                    f"{logPrefix} No se pudo generar la estructura del proyecto.")
                estructura_proyecto_str = "[Error al generar estructura]"
            else:
                logging.info(
                    f"{logPrefix} Estructura del proyecto generada (primeras líneas para log):\n{estructura_proyecto_str[:600]}...")
                logging.debug(
                    f"{logPrefix} Estructura completa generada:\n{estructura_proyecto_str}")
        except Exception as e_struct:
            logging.error(
                f"{logPrefix} Excepción al generar estructura del proyecto: {e_struct}", exc_info=True)
            estructura_proyecto_str = "[Excepción al generar estructura]"

        # PASO 1: ANÁLISIS Y DECISIÓN
        logging.info(f"{logPrefix} --- INICIO PASO 1: ANÁLISIS Y DECISIÓN ---")
        codigoProyectoCompleto = ""
        try:
            logging.info(f"{logPrefix} Analizando código COMPLETO...")
            extensiones = getattr(settings, 'EXTENSIONESPERMITIDAS', None)
            ignorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', None)
            todosLosArchivos = analizadorCodigo.listarArchivosProyecto(
                settings.RUTACLON, extensiones, ignorados)
            if todosLosArchivos is None:
                raise Exception("Error al listar archivos.")
            if not todosLosArchivos:
                logging.warning(
                    f"{logPrefix} No se encontraron archivos relevantes para leer.")
                codigoProyectoCompleto = ""
            else:
                resultadoLectura = analizadorCodigo.leerArchivos(
                    todosLosArchivos, settings.RUTACLON, api_provider=api_provider)

                if resultadoLectura is None or resultadoLectura.get('contenido') is None:
                    raise Exception(f"Error al leer contenido de archivos o resultado de lectura inválido. Proveedor: {api_provider}")

                codigoProyectoCompleto = resultadoLectura['contenido']
                bytesTotales = resultadoLectura.get('bytes', 0)
                tokensTotales = resultadoLectura.get('tokens', 0)
                archivosLeidosCount = resultadoLectura.get('archivos_leidos', len(todosLosArchivos))

                logging.info(
                    f"{logPrefix} Código completo leído ({archivosLeidosCount} archivos, {bytesTotales / 1024:.2f} KB, {tokensTotales} tokens).")

            logging.info(
                f"{logPrefix} Obteniendo DECISIÓN de IA ({api_provider.upper()})...")
            historialRecienteTexto = "\n---\n".join(
                historialRefactor[-settings.N_HISTORIAL_CONTEXTO:])

            decisionJson = analizadorCodigo.obtenerDecisionRefactor(
                codigoProyectoCompleto,
                historialRecienteTexto,
                estructura_proyecto_str,
                api_provider=api_provider
            )
            if not decisionJson:
                raise Exception(
                    f"No se recibió DECISIÓN válida de IA ({api_provider.upper()}) (Paso 1).")

            logging.info(f"{logPrefix} Parseando DECISIÓN de IA...")
            decisionParseada = parsearDecisionGemini(decisionJson)
            if not decisionParseada:
                sugerencia_str = json.dumps(decisionJson) if isinstance(
                    decisionJson, dict) else str(decisionJson)
                sugerencia_log = sugerencia_str[:500] + \
                    ('...' if len(sugerencia_str) > 500 else '')
                raise Exception(
                    f"Decisión inválida, mal formada o no soportada. Recibido: {sugerencia_log}")

            estadoFinal = "[PASO1_OK]"

            if decisionParseada.get("accion_propuesta") == "no_accion":
                razonamientoNoAccion = decisionParseada.get(
                    'razonamiento', 'Sin razonamiento especificado.')
                logging.info(
                    f"{logPrefix} IA ({api_provider.upper()}) decidió 'no_accion'. Razón: {razonamientoNoAccion}. Terminando ciclo.")
                estadoFinal = "[NO_ACCION]"
                historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                    outcome=estadoFinal,
                    decision=decisionParseada
                ))
                manejadorHistorial.guardarHistorial(historialRefactor)
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False

            logging.info(
                f"{logPrefix} --- FIN PASO 1: Decisión válida recibida: {decisionParseada.get('accion_propuesta')} ---")

        except Exception as e_paso1:
            logging.error(
                f"{logPrefix} Error en Paso 1: {e_paso1}", exc_info=True)
            estadoFinal = "[ERROR_PASO1]"
            historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                outcome=estadoFinal,
                decision=decisionParseada,
                error_message=str(e_paso1)
            ))
            manejadorHistorial.guardarHistorial(historialRefactor)
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        # PASO 2: EJECUCIÓN
        logging.info(f"{logPrefix} --- INICIO PASO 2: EJECUCIÓN ---")
        contextoReducido = ""
        resultadoJson = None
        try:
            archivosRelevantes = decisionParseada.get(
                "archivos_relevantes", [])
            rutasAbsRelevantes = []
            for rutaRel in archivosRelevantes:
                rutaAbs = aplicadorCambios._validar_y_normalizar_ruta(
                    rutaRel, settings.RUTACLON, asegurar_existencia=False)
                if rutaAbs:
                    accion = decisionParseada.get("accion_propuesta")
                    params = decisionParseada.get("parametros_accion", {})
                    archivo_destino_mover = params.get("archivo_destino") if accion in [
                        "mover_funcion", "mover_clase"] else None
                    archivo_a_crear = params.get(
                        "archivo") if accion == "crear_archivo" else None

                    es_destino_o_creacion = (
                        rutaRel == archivo_destino_mover or rutaRel == archivo_a_crear)
                    if os.path.exists(rutaAbs) or es_destino_o_creacion:
                        if os.path.exists(rutaAbs):
                            rutasAbsRelevantes.append(rutaAbs)
                    else:
                        logging.warning(
                            f"{logPrefix} Archivo relevante '{rutaRel}' no existe y no parece ser objetivo de creación/movimiento. Se omitirá del contexto Paso 2.")
                else:
                    logging.error(
                        f"{logPrefix} Ruta relevante inválida '{rutaRel}' proporcionada por IA en Paso 1. Se omitirá.")

            accion_requiere_contexto = decisionParseada.get("accion_propuesta") not in [
                "crear_directorio", "eliminar_archivo", "crear_archivo"]
            if not rutasAbsRelevantes and accion_requiere_contexto:
                es_mover_a_nuevo = decisionParseada.get("accion_propuesta") in ["mover_funcion", "mover_clase"] and \
                    len(archivosRelevantes) >= 1 and \
                    decisionParseada.get("parametros_accion", {}).get("archivo_destino") in archivosRelevantes and \
                    not os.path.exists(aplicadorCambios._validar_y_normalizar_ruta(decisionParseada.get(
                        "parametros_accion").get("archivo_destino"), settings.RUTACLON, asegurar_existencia=False))

                if not es_mover_a_nuevo:
                    logging.warning(f"{logPrefix} No se encontraron archivos existentes para contexto reducido y la acción usualmente lo requiere. Acción: {decisionParseada.get('accion_propuesta')}. Relevantes (solicitados): {archivosRelevantes}. Se continuará sin contexto.")

            if rutasAbsRelevantes:
                contextoReducido = analizadorCodigo.leerArchivos(
                    rutasAbsRelevantes, settings.RUTACLON)
                if contextoReducido is None:
                    raise Exception("Error leyendo contexto reducido.")
                tamanoKB_reducido = len(
                    contextoReducido.encode('utf-8')) / 1024
                logging.info(
                    f"{logPrefix} Contexto reducido leído ({len(rutasAbsRelevantes)} archivos, {tamanoKB_reducido:.2f} KB).")
            else:
                logging.info(
                    f"{logPrefix} Acción '{decisionParseada.get('accion_propuesta')}' no requiere contexto de archivo para Paso 2, o no se encontraron archivos relevantes existentes.")
                contextoReducido = ""

            logging.info(
                f"{logPrefix} Obteniendo RESULTADO de ejecución de IA ({api_provider.upper()})...")

            MAX_RETRIES_PASO2 = 7
            RETRY_DELAY_SECONDS_PASO2 = 5
            resultadoJson = None

            for intento in range(MAX_RETRIES_PASO2):
                try:
                    logging.info(
                        f"{logPrefix} Intento {intento + 1}/{MAX_RETRIES_PASO2} para obtener resultado de ejecución...")

                    resultadoJson = analizadorCodigo.ejecutarAccionConGemini(
                        decisionParseada, contextoReducido,
                        api_provider=api_provider
                    )

                    if resultadoJson is not None:
                        logging.info(
                            f"{logPrefix} Resultado obtenido con éxito en intento {intento + 1}.")
                        break
                    else:
                        logging.warning(
                            f"{logPrefix} Intento {intento + 1} fallido (API devolvió None o respuesta inválida).")

                except Exception as e_api_call:
                    logging.error(
                        f"{logPrefix} Excepción durante el intento {intento + 1} de llamada API (Paso 2): {e_api_call}", exc_info=True)
                    resultadoJson = None

                if resultadoJson is None and intento < MAX_RETRIES_PASO2 - 1:
                    logging.info(
                        f"{logPrefix} Esperando {RETRY_DELAY_SECONDS_PASO2} segundos antes del reintento...")
                    time.sleep(RETRY_DELAY_SECONDS_PASO2)
                elif resultadoJson is None and intento == MAX_RETRIES_PASO2 - 1:
                    logging.error(
                        f"{logPrefix} Fallaron todos los {MAX_RETRIES_PASO2} intentos para obtener el resultado de ejecución (Paso 2).")

            if resultadoJson is None:
                raise Exception(
                    f"Fallaron todos los {MAX_RETRIES_PASO2} intentos para obtener el resultado de ejecución de IA (Paso 2). La API puede estar inestable o la solicitud es inválida.")

            logging.info(f"{logPrefix} Parseando RESULTADO de ejecución IA...")
            if isinstance(resultadoJson, dict):
                resultadoJson["accion_original_debug"] = decisionParseada.get(
                    "accion_propuesta")
            resultadoEjecucion = parsearResultadoEjecucion(resultadoJson)
            if resultadoEjecucion is None:
                resultado_str = json.dumps(resultadoJson) if isinstance(
                    resultadoJson, dict) else str(resultadoJson)
                resultado_log = resultado_str[:500] + \
                    ('...' if len(resultado_str) > 500 else '')
                raise Exception(
                    f"Resultado de ejecución inválido o mal formado tras obtenerlo de la API. Recibido: {resultado_log}")

            logging.info(
                f"{logPrefix} --- FIN PASO 2: Resultado válido recibido ({len(resultadoEjecucion)} archivos a modificar). ---")
            estadoFinal = "[PASO2_OK]"

            logging.info(f"{logPrefix} Aplicando cambios generados...")
            exitoAplicar, mensajeErrorAplicar = aplicadorCambios.aplicarCambiosSobrescritura(
                resultadoEjecucion,
                settings.RUTACLON,
                decisionParseada.get("accion_propuesta"),
                decisionParseada.get("parametros_accion", {})
            )
            if not exitoAplicar:
                raise Exception(
                    f"Falló la aplicación de cambios: {mensajeErrorAplicar}")

            logging.info(
                f"{logPrefix} Cambios aplicados localmente con éxito (antes de verificación).")
            estadoFinal = "[APPLY_OK]"

        except Exception as e_paso2_apply:
            logging.error(
                f"{logPrefix} Error en Paso 2 o Aplicación: {e_paso2_apply}", exc_info=True)
            estadoFinal = "[ERROR_PASO2_APPLY]"
            historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                outcome=estadoFinal,
                decision=decisionParseada,
                result_details=resultadoEjecucion if resultadoEjecucion is not None else resultadoJson,
                error_message=str(e_paso2_apply)
            ))
            guardarHistorial(historialRefactor)
            logging.info(
                f"{logPrefix} Intentando descartar cambios locales tras error...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

        # PASO 3: VERIFICACIÓN
        VERIFICACION_ACTIVADA = False
        logging.info(
            f"{logPrefix} --- INICIO PASO 3: VERIFICACIÓN ({'ACTIVADA' if VERIFICACION_ACTIVADA else 'DESACTIVADA'}) ---")
        exitoVerificacion = True
        verification_details_msg = "Verificación desactivada."
        estadoFinalTemporal = "[VERIFY_SKIPPED]"

        if VERIFICACION_ACTIVADA:
            verification_details_msg = "Verificación no ejecutada aún."
            try:
                exitoVerificacion, verification_details_msg = verificarCambiosAplicados(
                    decisionParseada,
                    resultadoEjecucion,
                    settings.RUTACLON
                )
                if not exitoVerificacion:
                    raise Exception(
                        f"Verificación fallida: {verification_details_msg}")
                logging.info(
                    f"{logPrefix} --- FIN PASO 3: Verificación exitosa. ---")
                estadoFinalTemporal = "[VERIFY_OK]"

            except Exception as e_paso3_verify:
                logging.error(
                    f"{logPrefix} Error en Paso 3 (Verificación): {e_paso3_verify}", exc_info=True)
                estadoFinal = "[VERIFY_FAIL]"
                historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                    outcome=estadoFinal,
                    decision=decisionParseada,
                    result_details=resultadoEjecucion,
                    verification_details=verification_details_msg,
                    error_message=str(e_paso3_verify)
                ))
                guardarHistorial(historialRefactor)
                logging.info(
                    f"{logPrefix} Intentando descartar cambios locales tras fallo de verificación...")
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False
        else:
            logging.warning(f"{logPrefix} {verification_details_msg}")
            estadoFinal = estadoFinalTemporal

        if VERIFICACION_ACTIVADA and exitoVerificacion:
            estadoFinal = estadoFinalTemporal

        # COMMIT Y FINALIZACIÓN
        try:
            logging.info(f"{logPrefix} Realizando commit...")
            mensajeCommit = decisionParseada.get(
                'descripcion', 'Refactorización automática')
            if len(mensajeCommit.encode('utf-8')) > 4000:
                mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
                logging.warning(f"{logPrefix} Mensaje de commit truncado.")
            elif len(mensajeCommit.splitlines()[0]) > 72:
                logging.warning(
                    f"{logPrefix} Primera línea del mensaje de commit larga (>72 chars).")

            seHizoCommitNuevo = manejadorGit.hacerCommit(
                settings.RUTACLON, mensajeCommit)

            if seHizoCommitNuevo:
                logging.info(f"{logPrefix} Commit realizado con éxito.")
                estadoFinal = "[ÉXITO]"
                historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                    outcome=estadoFinal,
                    decision=decisionParseada,
                    result_details=resultadoEjecucion,
                    verification_details=verification_details_msg
                ))
                manejadorHistorial.guardarHistorial(historialRefactor)
                logging.info(
                    f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
                return True
            else:
                logging.warning(
                    f"{logPrefix} No se realizó un nuevo commit (ver logs de manejadorGit: puede ser por falta de cambios o error).")
                estadoFinal = "[COMMIT_NO_REALIZADO]"
                historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                    outcome=estadoFinal,
                    decision=decisionParseada,
                    result_details=resultadoEjecucion,
                    verification_details=verification_details_msg,
                    error_message="No se generó un nuevo commit (sin cambios detectados por Git o error en commit)."
                ))
                manejadorHistorial.guardarHistorial(historialRefactor)
                logging.info(
                    f"{logPrefix} Descartando cambios locales ya que no hubo commit...")
                manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                return False

        except Exception as e_commit_final:
            logging.error(
                f"{logPrefix} Error en fase de Commit/Finalización: {e_commit_final}", exc_info=True)
            estadoFinal = "[ERROR_COMMIT]"
            historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                outcome=estadoFinal,
                decision=decisionParseada,
                result_details=resultadoEjecucion,
                verification_details=verification_details_msg,
                error_message=str(e_commit_final)
            ))
            manejadorHistorial.guardarHistorial(historialRefactor)
            logging.info(
                f"{logPrefix} Intentando descartar cambios locales tras fallo de commit...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            return False

    except Exception as e_global:
        logging.critical(
            f"{logPrefix} Error inesperado y no capturado: {e_global}", exc_info=True)
        estadoFinal = "[ERROR_CRITICO]"
        try:
            if not historialRefactor:  # Cargar solo si está vacío
                historialRefactor = manejadorHistorial.cargarHistorial()
            historialRefactor.append(manejadorHistorial.formatearEntradaHistorial(
                outcome=estadoFinal,
                decision=decisionParseada,  # Puede ser None si el error es muy temprano
                error_message=str(e_global)
            ))
            manejadorHistorial.guardarHistorial(historialRefactor)
        except Exception as e_hist_crit:
            logging.error(
                f"Fallo adicional al intentar guardar historial de error crítico: {e_hist_crit}")
        try:
            logging.info(
                f"{logPrefix} Intentando descartar cambios locales debido a error crítico...")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        except Exception as e_clean_crit:
            logging.error(
                f"{logPrefix} Falló limpieza tras error crítico: {e_clean_crit}")
        return False


if __name__ == "__main__":
    configurarLogging()
    parser = argparse.ArgumentParser(
        description="Agente de Refactorización de Código con IA (Google Gemini / OpenRouter) - 3 Pasos.",
        epilog="Ejecuta un ciclo: 1. Decide, 2. Ejecuta (con reintentos), [3. Verifica], 4. Commitea. Usa --modo-test para hacer push, --openrouter para usar OpenRouter."
    )
    parser.add_argument(
        "--modo-test", action="store_true",
        help="Activa modo prueba: Si el ciclo realiza un commit efectivo, intenta hacer push."
    )
    parser.add_argument(
        "--openrouter", action="store_true",
        help="Utilizar la API de OpenRouter en lugar de la API de Google Gemini por defecto."
    )
    args = parser.parse_args()

    codigo_salida = orchestrarEjecucionScript(args)

    logging.info(
        f"Script principal finalizado con código de salida: {codigo_salida}")
    sys.exit(codigo_salida)
