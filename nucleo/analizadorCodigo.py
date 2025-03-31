# nucleo/analizadorCodigo.py
import os
import logging
import json
import google.generativeai as genai
import google.api_core.exceptions
from config import settings
# Quita la importación específica de types si ya no la usas para Schema
# from google.generativeai import types

# ... (configurarGemini, listarArchivosProyecto, leerArchivos sin cambios) ...
log = logging.getLogger(__name__)
geminiConfigurado = False


def configurarGemini():
    global geminiConfigurado
    if geminiConfigurado:
        return True
    logPrefix = "configurarGemini:"
    apiKey = settings.GEMINIAPIKEY
    if not apiKey:
        log.critical(f"{logPrefix} API Key de Gemini no configurada.")
        return False
    try:
        genai.configure(api_key=apiKey)
        log.info(f"{logPrefix} Cliente de Gemini configurado.")
        geminiConfigurado = True
        return True
    except Exception as e:
        log.critical(f"{logPrefix} Error configurando cliente de Gemini: {e}")
        return False


def listarArchivosProyecto(rutaProyecto, extensionesPermitidas=None, directoriosIgnorados=None):
    # ... (sin cambios) ...
    logPrefix = "listarArchivosProyecto:"
    archivosProyecto = []
    if extensionesPermitidas is None:
        extensionesPermitidas = getattr(settings, 'EXTENSIONESPERMITIDAS', [
                                        '.php', '.js', '.py', '.md', '.txt'])
        extensionesPermitidas = [ext.lower() for ext in extensionesPermitidas]
    if directoriosIgnorados is None:
        directoriosIgnorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', [
                                       '.git', 'vendor', 'node_modules'])
    try:
        log.info(f"{logPrefix} Listando archivos en: {rutaProyecto}")
        for raiz, dirs, archivos in os.walk(rutaProyecto, topdown=True):
            # Excluir directorios ignorados
            dirs[:] = [
                d for d in dirs if d not in directoriosIgnorados and not d.startswith('.')]

            for nombreArchivo in archivos:
                # Ignorar archivos ocultos
                if nombreArchivo.startswith('.'):
                    continue

                _, ext = os.path.splitext(nombreArchivo)
                if ext.lower() in extensionesPermitidas:
                    rutaCompleta = os.path.join(raiz, nombreArchivo)
                    # Normalizar la ruta para consistencia
                    archivosProyecto.append(os.path.normpath(rutaCompleta))

        log.info(
            f"{logPrefix} Archivos relevantes encontrados: {len(archivosProyecto)}")
        return archivosProyecto
    except Exception as e:
        log.error(
            f"{logPrefix} Error listando archivos en {rutaProyecto}: {e}", exc_info=True)
        return None


def leerArchivos(listaArchivos, rutaBase):
    # ... (sin cambios) ...
    logPrefix = "leerArchivos:"
    contenidoConcatenado = ""
    archivosLeidos = 0
    bytesTotales = 0
    archivosFallidos = []

    for rutaAbsoluta in listaArchivos:
        # Asegurarse de que la ruta base sea absoluta y normalizada para una comparación segura
        rutaBaseNorm = os.path.normpath(os.path.abspath(rutaBase))
        rutaAbsNorm = os.path.normpath(os.path.abspath(rutaAbsoluta))

        # Comprobar si la ruta del archivo está dentro de la ruta base
        if not rutaAbsNorm.startswith(rutaBaseNorm + os.sep) and rutaAbsNorm != rutaBaseNorm:
            log.error(
                f"{logPrefix} Archivo '{rutaAbsoluta}' está fuera de la ruta base '{rutaBase}'. Se omitirá.")
            archivosFallidos.append(rutaAbsoluta)
            continue
        # Comprobar si el archivo realmente existe antes de intentar leerlo
        if not os.path.exists(rutaAbsNorm) or not os.path.isfile(rutaAbsNorm):
            log.warning(
                f"{logPrefix} Archivo no encontrado o no es un archivo válido en '{rutaAbsNorm}'. Se omitirá.")
            archivosFallidos.append(rutaAbsoluta)
            continue

        try:
            # Calcular ruta relativa de forma segura
            rutaRelativa = os.path.relpath(
                rutaAbsNorm, rutaBaseNorm).replace(os.sep, '/')

            with open(rutaAbsNorm, 'r', encoding='utf-8', errors='ignore') as f:
                contenido = f.read()
                bytesArchivo = len(contenido.encode('utf-8'))
                contenidoConcatenado += f"########## START FILE: {rutaRelativa} ##########\n"
                contenidoConcatenado += contenido
                contenidoConcatenado += f"\n########## END FILE: {rutaRelativa} ##########\n\n"
                archivosLeidos += 1
                bytesTotales += bytesArchivo
        except Exception as e:
            log.error(f"{logPrefix} Error leyendo '{rutaAbsNorm}': {e}")
            archivosFallidos.append(rutaAbsoluta)

    tamanoKB = bytesTotales / 1024
    if archivosFallidos:
        # Mostrar solo algunos
        log.warning(
            f"{logPrefix} No se pudieron leer {len(archivosFallidos)} archivos: {archivosFallidos[:5]}...")

    if archivosLeidos > 0:
        log.info(
            f"{logPrefix} Leídos {archivosLeidos} archivos. Tamaño total: {tamanoKB:.2f} KB.")
        return contenidoConcatenado
    else:
        log.error(
            f"{logPrefix} No se pudo leer ningún archivo de la lista proporcionada.")
        return None


# --- PASO 1: Obtener Decisión (Prompt Modificado) ---
def obtenerDecisionRefactor(contextoCodigoCompleto, historialCambiosTexto=None):
    """
    PASO 1: Analiza código COMPLETO e historial para DECIDIR una acción DETALLADA.
    Retorna JSON con ACCIÓN, PARÁMETROS ESPECÍFICOS, RAZONAMIENTO y ARCHIVOS RELEVANTES.
    Utiliza el modo JSON de Gemini.
    """
    logPrefix = "obtenerDecisionRefactor (Paso 1):"
    if not configurarGemini():
        return None
    if not contextoCodigoCompleto:
        log.error(f"{logPrefix} No se proporcionó contexto de código.")
        return None

    nombreModelo = settings.MODELOGEMINI
    try:
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{logPrefix} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(
            f"{logPrefix} Error inicializando modelo '{nombreModelo}': {e}")
        return None

    # ### MODIFICADO ### Prompt ajustado para JSON Mode (quitando formato explícito)
    promptPartes = []
    promptPartes.append("Eres un asistente experto en refactorización de código PHP/JS (WordPress). Tu tarea es analizar TODO el código fuente y el historial, y proponer UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA. Es importante que seas detallado con la informacion que generas para que el segundo agente que realiza la accion sepa exactamente que hacer.")
    promptPartes.append("Prioriza: eliminar código muerto, simplificar lógica compleja, añadir validaciones FALTANTES y básicas (ej: `isset`, `!empty`), reducir duplicación MÍNIMA (mover funciones/clases SOLO si es obvio y mejora claramente la organización), mejorar legibilidad (nombres en español `camelCase`). EVITA cambios masivos o reestructuraciones grandes. Puedes organizar funciones, la estructura del proyecto es desordenada, es importante ordenar. No es importante ni necesario que agregues nuevos comentarios a funciones viejas para explicar lo que hacen. Puedes hacer mejoras de optimización, seguridad, simplificación sin arriesgarte a que el codigo falle.")
    promptPartes.append(
        "Considera el historial para NO repetir errores, NO deshacer trabajo anterior y mantener la consistencia.")

    promptPartes.append(
        # Ajustado
        "\n--- REGLAS ESTRICTAS PARA LA ESTRUCTURA JSON DE TU RESPUESTA (DECISIÓN) ---")
    promptPartes.append("1.  **`accion_propuesta`**: Elige UNA de: `mover_funcion`, `mover_clase`, `modificar_codigo_en_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`. Si NINGUNA acción es segura/útil/necesaria, USA `no_accion`.")
    promptPartes.append(
        "2.  **`descripcion`**: Sé MUY específico para un mensaje de commit útil (ej: 'Refactor(Seguridad): Añade isset() a $_GET['param'] en archivo.php', 'Refactor(Clean): Elimina función duplicada viejaFuncion() de utils_old.php', 'Refactor(Org): Mueve función auxiliar miHelper() de main.php a helpers/ui.php').")
    promptPartes.append(
        "3.  **`parametros_accion`**: Objeto JSON con TODA la información necesaria para ejecutar el cambio SIN DUDAS. Usa rutas RELATIVAS.")
    promptPartes.append(
        "    -   `mover_funcion`/`mover_clase`: `archivo_origen`, `archivo_destino`, `nombre_funcion`/`nombre_clase`, `eliminar_de_origen` (boolean).")
    promptPartes.append("    -   `modificar_codigo_en_archivo`: `archivo`, `descripcion_del_cambio_interno` (MUY detallado: 'Eliminar bloque if comentado entre lineas 80-95', 'Reemplazar bucle for en linea 120 por array_map', 'Añadir `global $wpdb;` al inicio de la función `miQuery()` en linea 30', 'Borrar la declaración completa de la función `funcionObsoleta(arg1)`'). NO incluyas el código aquí.")
    promptPartes.append(
        "    -   `crear_archivo`: `archivo` (ruta completa relativa), `proposito_del_archivo` (breve).")
    promptPartes.append(
        "    -   `eliminar_archivo`: `archivo` (ruta relativa).")
    promptPartes.append(
        "    -   `crear_directorio`: `directorio` (ruta relativa).")
    promptPartes.append(
        "4.  **`archivos_relevantes`**: Lista de strings [ruta1, ruta2, ...] con **TODAS** las rutas relativas de archivos que el Paso 2 NECESITARÁ LEER. ¡CRUCIAL y preciso!")
    promptPartes.append(
        "5.  **`razonamiento`**: String justificando CLARAMENTE el *por qué* de esta acción o la razón específica para `no_accion`.")
    # Añadido como regla explícita
    promptPartes.append(
        "6.  **`tipo_analisis`**: Incluye siempre el campo `tipo_analisis` con el valor fijo `\"refactor_decision\"`.")
    promptPartes.append(
        "7. Evita las tareas de legibilidad, no son importantes, no es importante agregar comentarios Añade comentario phpDoc descriptivo o cosas asi.")  # Mantenido
    # --- ELIMINADO Bloque ```json ... ``` ---

    if historialCambiosTexto:
        promptPartes.append(
            "\n--- HISTORIAL DE CAMBIOS RECIENTES (para tu contexto, EVITA REPETIR o deshacer) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")

    promptPartes.append("\n--- CÓDIGO FUENTE COMPLETO A ANALIZAR ---")
    promptPartes.append(contextoCodigoCompleto)
    promptPartes.append("--- FIN CÓDIGO ---")
    promptPartes.append(
        "\nRecuerda: Responde ÚNICAMENTE con el objeto JSON que cumple TODAS las reglas anteriores.")  # Ajustado

    promptCompleto = "\n".join(promptPartes)
    log.info(f"{logPrefix} Enviando solicitud de DECISIÓN a Gemini (MODO JSON)...")
    # --- COMENTADO Log del prompt ---
    # log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:200]}...")
    # log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-200:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(  # Asegúrate de que genai.types esté disponible o usa dict
                temperature=0.4,
                # --- AÑADIDO JSON Mode ---
                response_mime_type="application/json",
                max_output_tokens=65536
            ),
            safety_settings={
                'HATE': 'BLOCK_ONLY_HIGH',
                'HARASSMENT': 'BLOCK_ONLY_HIGH',
                'SEXUAL': 'BLOCK_ONLY_HIGH',
                'DANGEROUS': 'BLOCK_ONLY_HIGH'
            }
        )
        log.info(f"{logPrefix} Respuesta de DECISIÓN (MODO JSON) recibida.")

        # Extraer y parsear (el limpiador es robusto)
        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta:
            return None

        log.debug(
            f"{logPrefix} Texto crudo recibido de Gemini (antes de parsear JSON):\n{textoRespuesta}")

        sugerenciaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        # Validación básica
        if sugerenciaJson is None:
            log.error(f"{logPrefix} El parseo/extracción final de JSON falló.")
            return None  # Error ya logueado en _limpiarYParsearJson

        # Verificar tipo esperado
        if sugerenciaJson.get("tipo_analisis") != "refactor_decision":
            log.error(
                f"{logPrefix} Respuesta JSON no es del tipo esperado 'refactor_decision'.")
            # --- AÑADIDO Log del JSON recibido en caso de error de tipo ---
            try:
                log.error(
                    f"{logPrefix} JSON Recibido:\n{json.dumps(sugerenciaJson, indent=2, ensure_ascii=False)}")
            except Exception:  # Por si el JSON es inválido para dumps
                log.error(
                    f"{logPrefix} JSON Recibido (no se pudo formatear): {sugerenciaJson}")
            return None

        # --- AÑADIDO Log del JSON de decisión generado (formateado) ---
        log.info(
            f"{logPrefix} JSON de Decisión Generado:\n{json.dumps(sugerenciaJson, indent=2, ensure_ascii=False)}")
        # -------------------------------------------------------------
        return sugerenciaJson

    except google.api_core.exceptions.InvalidArgument as e_inv:
        log.error(f"{logPrefix} Error InvalidArgument durante la generación JSON: {e_inv}. ¿El modelo tuvo problemas para generar el JSON solicitado?", exc_info=True)
        _manejarExcepcionGemini(
            e_inv, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None
    except Exception as e:
        _manejarExcepcionGemini(
            e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None


# --- PASO 2: Ejecutar Acción (Modificado para Logging) ---
def ejecutarAccionConGemini(decisionParseada, contextoCodigoReducido):
    logPrefix = "ejecutarAccionConGemini (Paso 2):"
    if not configurarGemini():
        return None
    if not decisionParseada:
        log.error(f"{logPrefix} No se proporcionó la decisión del Paso 1.")
        return None

    nombreModelo = settings.MODELOGEMINI
    try:
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{logPrefix} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(
            f"{logPrefix} Error inicializando modelo '{nombreModelo}': {e}")
        return None

    # --- Construye el Prompt (AJUSTADO PARA ÉNFASIS EN ESCAPADO) ---
    accion = decisionParseada.get("accion_propuesta")
    descripcion = decisionParseada.get("descripcion")
    params = decisionParseada.get("parametros_accion", {})
    razonamiento_paso1 = decisionParseada.get("razonamiento")

    promptPartes = []
    promptPartes.append(
        "Eres un asistente de refactorización que EJECUTA una decisión ya tomada.")
    promptPartes.append("**FORMATO DE COMENTARIOS O CODIGO CON SALTO DE LINEAS:** Si generas comentarios multilínea que usan `//` (PHP/JS), ASEGÚRATE de que **CADA LÍNEA** del comentario comience con `//` dentro del código generado.")
    promptPartes.append(
        "Se ha decidido realizar la siguiente acción basada en el análisis previo:")
    promptPartes.append(
        "\n--- DECISIÓN DEL PASO 1 (Debes seguirla EXACTAMENTE) ---")
    promptPartes.append(f"Acción: {accion}")
    promptPartes.append(f"Descripción: {descripcion}")
    promptPartes.append(f"Parámetros Detallados: {json.dumps(params)}")
    promptPartes.append(f"Razonamiento (Contexto): {razonamiento_paso1}")
    promptPartes.append("--- FIN DECISIÓN ---")
    promptPartes.append(
        "\nSe te proporciona el contenido ACTUAL de los archivos relevantes (si aplica).")
    promptPartes.append(
        "**TU ÚNICA TAREA:** Realizar la acción descrita en los 'Parámetros Detallados'.")

    # --- INICIO: ÉNFASIS EN JSON Y ESCAPADO ---
    promptPartes.append(
        "\n**RESPUESTA ESPERADA:** Responde ÚNICAMENTE con un objeto JSON VÁLIDO que tenga la siguiente estructura:")
    promptPartes.append("""
```json
{
  "tipo_resultado": "ejecucion_cambio",
  "archivos_modificados": {
    "ruta/relativa/al/archivo1.php": "CONTENIDO COMPLETO Y FINAL DEL ARCHIVO 1...",
    "ruta/relativa/al/archivo2.js": "CONTENIDO COMPLETO Y FINAL DEL ARCHIVO 2...",
    // ... más archivos si son modificados o creados ...
    // Si la acción es eliminar_archivo o crear_directorio, este objeto debe estar vacío: {}
  }
}
```""")
    promptPartes.append(
        "\n--- REGLAS DE EJECUCIÓN Y FORMATO JSON (¡MUY IMPORTANTE!) ---")
    promptPartes.append("1.  **SIGUE LA DECISIÓN AL PIE DE LA LETRA.**")
    promptPartes.append("2.  **CONTENIDO DE ARCHIVOS:** Para CADA archivo afectado (modificado o creado), incluye su ruta relativa como clave y su contenido ÍNTEGRO final como valor string en `archivos_modificados`.")
    promptPartes.append("3.  **¡ESCAPADO CRÍTICO!** Dentro de las cadenas de texto que representan el contenido de los archivos (los valores en `archivos_modificados`), **TODAS** las comillas dobles (`\"`) literales DEBEN ser escapadas como `\\\"`. Todos los backslashes (`\\`) literales DEBEN ser escapados como `\\\\`. Los saltos de línea DEBEN ser `\\n`.")
    promptPartes.append(
        "4.  **PRESERVA CÓDIGO:** Mantén intacto el resto del código no afectado en los archivos modificados.")
    promptPartes.append(
        "5.  **MOVIMIENTOS:** Si mueves código y `eliminar_de_origen` es true, BORRA el código original del `archivo_origen`.")
    promptPartes.append(
        "6.  **MODIFICACIONES INTERNAS:** Aplica EXACTAMENTE la `descripcion_del_cambio_interno`.")
    promptPartes.append(
        "7.  **CREACIÓN:** Genera contenido inicial basado en `proposito_del_archivo`.")
    promptPartes.append(
        "8.  **SIN CONTENIDO:** Si la acción es `eliminar_archivo` o `crear_directorio`, el objeto `archivos_modificados` debe ser exactamente `{}`.")
    promptPartes.append(
        "9.  **FORMATO ESTRICTO:** Responde **SOLO** con el objeto JSON, sin ningún texto, explicación, comentario o bloque ```json antes o después.")
    # --- FIN: ÉNFASIS EN JSON Y ESCAPADO ---

    if contextoCodigoReducido:
        promptPartes.append(
            "\n--- CONTENIDO ACTUAL DE ARCHIVOS RELEVANTES ---")
        promptPartes.append(contextoCodigoReducido)
        promptPartes.append("--- FIN CONTENIDO ---")
    else:
        promptPartes.append(
            "\n(No se proporcionó contenido de archivo para esta acción específica)")

    promptCompleto = "\n".join(promptPartes)

    log.info(
        f"{logPrefix} Enviando solicitud de EJECUCIÓN a Gemini (MODO JSON)...")
    # --- COMENTADO Log del prompt ---
    # log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:200]}...")
    # log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-200:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(  # O usa dict
                temperature=0.4,  # Mantenemos una temperatura baja para seguir instrucciones
                response_mime_type="application/json",
                max_output_tokens=65536  # Asegurar suficiente espacio para código
            ),
            safety_settings={  # Configuración de seguridad estándar
                'HATE': 'BLOCK_ONLY_HIGH',
                'HARASSMENT': 'BLOCK_ONLY_HIGH',
                'SEXUAL': 'BLOCK_ONLY_HIGH',
                'DANGEROUS': 'BLOCK_ONLY_HIGH'
            }
        )
        log.info(f"{logPrefix} Respuesta de EJECUCIÓN (MODO JSON) recibida.")

        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta:
            return None

        # _limpiarYParsearJson ya es robusto encontrando el bloque {},
        # pero fallará si el *contenido* del string no está bien escapado.
        # El logging detallado que ya tiene nos dirá si el problema persiste.
        resultadoJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        if resultadoJson is None:
            log.error(
                f"{logPrefix} El parseo/extracción final de JSON falló. (Ver logs anteriores para detalles del error y JSON candidato)")
            # El error ya fue logueado extensamente por _limpiarYParsearJson
            return None

        # --- Validación del contenido del JSON (sin cambios aquí, ya era adecuada) ---
        if resultadoJson.get("tipo_resultado") != "ejecucion_cambio":
            log.warning(
                f"{logPrefix} Respuesta JSON no tiene 'tipo_resultado'=\"ejecucion_cambio\" esperado. Verificando estructura.")
            # ... (resto de validaciones igual)
            if "archivos_modificados" not in resultadoJson or not isinstance(resultadoJson.get("archivos_modificados"), dict):
                log.error(
                    f"{logPrefix} Falta 'archivos_modificados' o no es un diccionario.")
                try:
                    log.error(
                        f"{logPrefix} JSON Recibido:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
                except Exception:
                    log.error(
                        f"{logPrefix} JSON Recibido (no se pudo formatear): {resultadoJson}")
                return None
            # Intentar corregir si falta solo eso
            resultadoJson["tipo_resultado"] = "ejecucion_cambio"

        accion_sin_contenido = accion in [
            "eliminar_archivo", "crear_directorio"]
        archivos_mod = resultadoJson.get("archivos_modificados")

        if archivos_mod is None:
            log.error(
                f"{logPrefix} La clave 'archivos_modificados' falta en la respuesta JSON.")
            try:
                log.error(
                    f"{logPrefix} JSON Recibido:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
            except Exception:
                log.error(
                    f"{logPrefix} JSON Recibido (no se pudo formatear): {resultadoJson}")
            return None

        if accion_sin_contenido and archivos_mod != {}:
            log.warning(
                f"{logPrefix} Se esperaba 'archivos_modificados' vacío para la acción '{accion}', pero se recibió: {list(archivos_mod.keys())}. Se procederá con dict vacío.")
            resultadoJson["archivos_modificados"] = {}
        elif not accion_sin_contenido and not isinstance(archivos_mod, dict):
            log.error(
                f"{logPrefix} Se esperaba un diccionario para 'archivos_modificados' en acción '{accion}', pero se recibió tipo {type(archivos_mod)}.")
            try:
                log.error(
                    f"{logPrefix} JSON Recibido:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
            except Exception:
                log.error(
                    f"{logPrefix} JSON Recibido (no se pudo formatear): {resultadoJson}")
            return None
        # Validación adicional: que los valores sean strings
        elif isinstance(archivos_mod, dict):
            for k, v in archivos_mod.items():
                if not isinstance(v, str):
                    log.error(
                        f"{logPrefix} El valor para la clave '{k}' en 'archivos_modificados' NO es un string (tipo: {type(v)}). JSON inválido.")
                    try:
                        log.error(
                            f"{logPrefix} JSON Recibido:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
                    except Exception:
                        log.error(
                            f"{logPrefix} JSON Recibido (no se pudo formatear): {resultadoJson}")
                    return None

        log.info(
            f"{logPrefix} Respuesta JSON (MODO JSON) parseada y validada correctamente.")
        # Loguear el resultado es útil, pero puede ser muy largo. Se mantiene.
        log.info(
            f"{logPrefix} JSON de Ejecución Generado:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
        return resultadoJson

    except google.api_core.exceptions.InvalidArgument as e_inv:
        # Este error puede ocurrir si el *prompt* es inválido O si el modelo falla en generar JSON válido.
        log.error(f"{logPrefix} Error InvalidArgument durante la generación JSON: {e_inv}. ¿El modelo tuvo problemas para generar el JSON solicitado O hubo contenido bloqueado?", exc_info=True)
        _manejarExcepcionGemini(
            e_inv, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None
    except Exception as e:
        _manejarExcepcionGemini(
            e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None

# --- Helpers Internos ---
# _extraerTextoRespuesta, _limpiarYParsearJson, _manejarExcepcionGemini
# (Sin cambios necesarios en los helpers, _limpiarYParsearJson ya es robusto
# y el logging del JSON se hace después de llamarlo con éxito)

# ... (resto de _extraerTextoRespuesta, _limpiarYParsearJson, _manejarExcepcionGemini igual) ...


def _extraerTextoRespuesta(respuesta, logPrefix):
    """Extrae el texto de la respuesta de Gemini de forma robusta."""
    textoRespuesta = ""
    try:
        # Intentar varias formas comunes de acceder al texto
        if hasattr(respuesta, 'text') and respuesta.text:
            textoRespuesta = respuesta.text
        elif hasattr(respuesta, 'parts') and respuesta.parts:
            # Comprobar si parts es iterable y no vacío
            if isinstance(respuesta.parts, (list, tuple)) and respuesta.parts:
                # MODIFICACIÓN: Si se usa response_mime_type="application/json"
                # el texto puede no estar en part.text directamente, pero sí en respuesta.text
                # Así que priorizamos respuesta.text si existe.
                if hasattr(respuesta, 'text') and respuesta.text:
                    textoRespuesta = respuesta.text
                else:
                    # Fallback a concatenar partes si respuesta.text no está
                    textoRespuesta = "".join(
                        part.text for part in respuesta.parts if hasattr(part, 'text'))
        elif hasattr(respuesta, 'candidates') and respuesta.candidates:
            # Comprobar si candidates es iterable y no vacío
            if isinstance(respuesta.candidates, (list, tuple)) and respuesta.candidates:
                # Similar al caso de 'parts', priorizar respuesta.text si existe
                if hasattr(respuesta, 'text') and respuesta.text:
                    textoRespuesta = respuesta.text
                else:
                    # Fallback a la lógica anterior del candidate
                    candidate = respuesta.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts') and candidate.content.parts:
                        if isinstance(candidate.content.parts, (list, tuple)) and candidate.content.parts:
                            textoRespuesta = "".join(
                                part.text for part in candidate.content.parts if hasattr(part, 'text'))

        if not textoRespuesta:
            finish_reason_str = "N/A"
            safety_ratings_str = "N/A"
            block_reason_str = "N/A"

            # Intentar obtener detalles del bloqueo o finalización
            if hasattr(respuesta, 'prompt_feedback'):
                feedback = respuesta.prompt_feedback
                if hasattr(feedback, 'block_reason'):
                    block_reason_str = str(feedback.block_reason)
                if hasattr(feedback, 'safety_ratings'):
                    safety_ratings_str = str(feedback.safety_ratings)

            if hasattr(respuesta, 'candidates') and isinstance(respuesta.candidates, (list, tuple)) and respuesta.candidates:
                candidate = respuesta.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    finish_reason_str = str(candidate.finish_reason)
                # A veces los ratings están en el candidate
                if hasattr(candidate, 'safety_ratings') and safety_ratings_str == "N/A":
                    safety_ratings_str = str(candidate.safety_ratings)

            log.error(f"{logPrefix} Respuesta de Gemini vacía o no se pudo extraer texto. "
                      f"FinishReason: {finish_reason_str}, BlockReason: {block_reason_str}, SafetyRatings: {safety_ratings_str}")
            log.debug(f"{logPrefix} Respuesta completa (objeto): {respuesta}")
            return None

        return textoRespuesta.strip()  # Devolver texto limpio

    except (AttributeError, IndexError, ValueError, TypeError) as e:
        log.error(
            f"{logPrefix} Error extrayendo texto de la respuesta: {e}. Respuesta obj: {respuesta}", exc_info=True)
        return None
    except Exception as e:  # Captura genérica
        log.error(
            f"{logPrefix} Error inesperado extrayendo texto: {e}", exc_info=True)
        return None


def _limpiarYParsearJson(textoRespuesta, logPrefix):
    """Limpia ```json ... ``` y parsea el JSON."""
    textoLimpio = textoRespuesta.strip()

    # Eliminar bloques de código Markdown ```json ... ``` o ``` ... ```
    # Aunque JSON mode *debería* evitar esto, lo mantenemos por robustez
    if textoLimpio.startswith("```"):
        # Encontrar el primer salto de línea después de ```
        first_newline = textoLimpio.find('\n')
        if first_newline != -1:
            # Comprobar si la primera línea es solo ```json o ```
            first_line = textoLimpio[:first_newline].strip()
            if first_line == "```json" or first_line == "```":
                textoLimpio = textoLimpio[first_newline + 1:]
        # Eliminar el ``` final si existe
        if textoLimpio.endswith("```"):
            textoLimpio = textoLimpio[:-3].strip()

    # A veces Gemini añade texto antes o después del JSON real incluso en JSON mode
    # Intentar encontrar el '{' inicial y el '}' final que forman un bloque válido
    start_brace = textoLimpio.find('{')
    end_brace = textoLimpio.rfind('}')

    if start_brace == -1 or end_brace == -1 or start_brace >= end_brace:
        log.error(
            f"{logPrefix} Respuesta de Gemini no parece contener un bloque JSON válido {{...}}. Respuesta (limpia inicial): {textoLimpio[:500]}...")
        log.debug(f"{logPrefix} Respuesta Original Completa:\n{textoRespuesta}")
        return None

    json_candidate = textoLimpio[start_brace: end_brace + 1]

    try:
        log.debug(
            f"{logPrefix} Intentando parsear JSON candidato (tamaño: {len(json_candidate)})...")
        resultadoJson = json.loads(json_candidate)
        # Ajuste leve msg
        log.info(
            f"{logPrefix} JSON parseado correctamente (previo a validación de contenido).")
        return resultadoJson
    except json.JSONDecodeError as e:
        # ### MEJORADO ### Loguear más contexto alrededor del error
        contexto_inicio = max(0, e.pos - 150)
        contexto_fin = min(len(json_candidate), e.pos + 150)
        contexto_error = json_candidate[contexto_inicio:contexto_fin]
        # Escapar caracteres no imprimibles para el log
        contexto_error_repr = repr(contexto_error)

        log.error(f"{logPrefix} Error crítico parseando JSON de Gemini: {e}")
        log.error(f"{logPrefix} Posición del error: {e.pos}")
        log.error(
            f"{logPrefix} Contexto alrededor del error ({contexto_inicio}-{contexto_fin}):\n{contexto_error_repr}")
        # Loguear más del candidato si es posible (ej. primeros y últimos 1000 caracteres)
        log.error(
            f"{logPrefix} JSON Candidato (inicio):\n{json_candidate[:1000]}...")
        log.error(
            f"{logPrefix} JSON Candidato (fin):...{json_candidate[-1000:]}")
        log.debug(f"{logPrefix} Respuesta Original Completa:\n{textoRespuesta}")
        return None
    except Exception as e:  # Captura errores inesperados durante el parseo
        log.error(
            f"{logPrefix} Error inesperado parseando JSON: {e}", exc_info=True)
        return None


def _manejarExcepcionGemini(e, logPrefix, respuesta=None):
    """Maneja y loguea excepciones comunes de la API de Gemini."""
    if isinstance(e, google.api_core.exceptions.ResourceExhausted):
        log.error(
            f"{logPrefix} Error de cuota API Gemini (ResourceExhausted): {e}")
    elif isinstance(e, google.api_core.exceptions.InvalidArgument):
        # Esto a menudo incluye errores por contenido inválido en el prompt (no solo tamaño)
        # O problemas del modelo generando el formato JSON solicitado
        # Añadido exc_info
        log.error(f"{logPrefix} Error argumento inválido API Gemini (InvalidArgument): {e}. ¿Prompt mal formado, contenido bloqueado o fallo en generación JSON?", exc_info=True)
    elif isinstance(e, google.api_core.exceptions.PermissionDenied):
        log.error(
            f"{logPrefix} Error de permiso API Gemini (PermissionDenied): {e}. ¿API Key incorrecta o sin permisos?")
    elif isinstance(e, google.api_core.exceptions.ServiceUnavailable):
        log.error(
            f"{logPrefix} Error servicio no disponible API Gemini (ServiceUnavailable): {e}. Reintentar más tarde.")
    # Intentar manejo específico de excepciones de bloqueo si están disponibles
    # Añadido ResponseBlockedError
    elif type(e).__name__ in ['BlockedPromptException', 'StopCandidateException', 'ResponseBlockedError']:
        log.error(
            f"{logPrefix} Prompt bloqueado o generación detenida/bloqueada por Gemini: {e}")
        # Intentar extraer info del objeto respuesta si se pasó
        finish_reason = "Desconocida"
        safety_ratings = "No disponibles"
        if respuesta:
            if hasattr(respuesta, 'prompt_feedback'):
                feedback = respuesta.prompt_feedback
                if hasattr(feedback, 'block_reason'):
                    finish_reason = f"BlockReason: {feedback.block_reason}"
                if hasattr(feedback, 'safety_ratings'):
                    safety_ratings = str(feedback.safety_ratings)
            if hasattr(respuesta, 'candidates') and respuesta.candidates:
                # Puede que candidates esté vacío si la respuesta fue bloqueada
                try:
                    candidate = respuesta.candidates[0]
                    if hasattr(candidate, 'finish_reason'):
                        # Sobreescribir si hay finish_reason más específico
                        finish_reason = f"FinishReason: {candidate.finish_reason}"
                    if hasattr(candidate, 'safety_ratings'):
                        safety_ratings = str(candidate.safety_ratings)
                except IndexError:
                    log.debug(
                        f"{logPrefix} No se encontraron candidates en la respuesta (probablemente bloqueada).")

        log.error(
            f"{logPrefix} Razón: {finish_reason}, Safety: {safety_ratings}")

    else:
        # Error genérico de la API o del cliente
        log.error(
            f"{logPrefix} Error inesperado en llamada API Gemini: {type(e).__name__} - {e}", exc_info=True)
        if respuesta:
            try:
                feedback = getattr(respuesta, 'prompt_feedback', None)
                if feedback:
                    log.error(
                        f"{logPrefix} Prompt Feedback (si disponible): {feedback}")
            except Exception as e_fb:
                log.debug(
                    f"Error al intentar obtener feedback de la respuesta: {e_fb}")
