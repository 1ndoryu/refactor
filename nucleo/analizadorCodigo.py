# nucleo/analizadorCodigo.py
import os
import logging
import json
import google.generativeai as genai
import google.api_core.exceptions
from config import settings
from google.generativeai import types # Asegúrate de importar types

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
    """
    logPrefix = "obtenerDecisionRefactor (Paso 1):"
    # ... (configuración de Gemini igual) ...
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

    # ### MODIFICADO ### Prompt más exigente para Paso 1
    promptPartes = []
    promptPartes.append("Eres un asistente experto en refactorización de código PHP/JS (WordPress). Tu tarea es analizar TODO el código fuente y el historial, y proponer UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA.")
    promptPartes.append("Prioriza: eliminar código muerto, simplificar lógica compleja, añadir validaciones FALTANTES y básicas (ej: `isset`, `!empty`), reducir duplicación MÍNIMA (mover funciones/clases SOLO si es obvio y mejora claramente la organización), mejorar legibilidad (nombres en español `camelCase`). EVITA cambios masivos o reestructuraciones grandes. Puedes organizar funciones, la estructura del proyecto es desordenada, es importante ordenar. No es importante ni necesario que agregues nuevos comentarios a funciones viejas para explicar lo que hacen. Puedes hacer mejoras de optimización, seguridad, simplificación sin arriesgarte a que el codigo falle.")
    promptPartes.append(
        "Considera el historial para NO repetir errores, NO deshacer trabajo anterior y mantener la consistencia.")

    promptPartes.append(
        "\n--- REGLAS ESTRICTAS PARA TU RESPUESTA (DECISIÓN) ---")
    promptPartes.append("1.  **IDENTIFICA LA ACCIÓN**: Elige UNA de: `mover_funcion`, `mover_clase`, `modificar_codigo_en_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`. Si NINGUNA acción es segura/útil/necesaria, USA `no_accion`.")
    promptPartes.append(
        "2.  **DESCRIBE CLARAMENTE**: En `descripcion`, sé MUY específico para un mensaje de commit útil (ej: 'Refactor(Seguridad): Añade isset() a $_GET['param'] en archivo.php', 'Refactor(Clean): Elimina función duplicada viejaFuncion() de utils_old.php', 'Refactor(Org): Mueve función auxiliar miHelper() de main.php a helpers/ui.php').")
    promptPartes.append(
        "3.  **DETALLA PARÁMETROS SIN AMBIGÜEDAD**: En `parametros_accion`, incluye TODA la información necesaria para que OTRO proceso (Paso 2) realice el cambio SIN DUDAS. Usa rutas RELATIVAS.")
    promptPartes.append(
        "    -   `mover_funcion`/`mover_clase`: `archivo_origen`, `archivo_destino`, `nombre_funcion`/`nombre_clase`. **IMPORTANTE**: Indica si la función/clase debe ser **BORRADA** del origen.")
    promptPartes.append("    -   `modificar_codigo_en_archivo`: `archivo`, `descripcion_del_cambio_interno` (MUY detallado: 'Eliminar bloque if comentado entre lineas 80-95', 'Reemplazar bucle for en linea 120 por array_map', 'Añadir `global $wpdb;` al inicio de la función `miQuery()` en linea 30', 'Borrar la declaración completa de la función `funcionObsoleta(arg1)`'). **NO incluyas el código a buscar/reemplazar aquí**, solo la instrucción CLARA.")
    promptPartes.append(
        "    -   `crear_archivo`: `archivo` (ruta completa relativa), `proposito_del_archivo` (breve, ej: 'Clase para manejar la API externa X').")
    promptPartes.append(
        "    -   `eliminar_archivo`: `archivo` (ruta relativa).")
    promptPartes.append(
        "    -   `crear_directorio`: `directorio` (ruta relativa).")
    promptPartes.append("4.  **LISTA ARCHIVOS RELEVANTES COMPLETAMENTE**: En `archivos_relevantes`, incluye **TODAS** las rutas relativas de archivos que el Paso 2 **NECESITARÁ LEER** para ejecutar la acción (origen, destino, archivos que usan lo movido si aplica y es fácil de determinar, etc.). ¡Esto es CRUCIAL y debe ser preciso!")
    promptPartes.append("5.  **EXPLICA TU RAZONAMIENTO DETALLADAMENTE**: En `razonamiento`, justifica CLARAMENTE el *por qué* de esta acción (beneficio, problema que resuelve) o la razón específica para `no_accion` (ej: 'Código ya optimizado', 'No se encontraron mejoras seguras', 'Requiere análisis manual').")
    promptPartes.append(
        "6. Evita las tareas de legibilidad, no son importantes, no es importante agregar comentarios Añade comentario phpDoc descriptivo o cosas asi.")
    promptPartes.append(
        "7.  **FORMATO JSON ESTRICTO**: Responde **ÚNICAMENTE** con el JSON. SIN texto introductorio ni explicaciones fuera del JSON.")
    promptPartes.append("""
```json
{
  "tipo_analisis": "refactor_decision",
  "accion_propuesta": "TIPO_ACCION",
  "descripcion": "Mensaje MUY CLARO y específico para commit.",
  "parametros_accion": {
    // --- Ejemplo mover_funcion ---
    // "archivo_origen": "ruta/relativa/origen.php",
    // "archivo_destino": "ruta/relativa/destino.php",
    // "nombre_funcion": "nombreDeLaFuncion",
    // "eliminar_de_origen": true, // O false si solo se copia
    // --- Ejemplo modificar_codigo_en_archivo ---
    // "archivo": "ruta/relativa/archivo.php",
    // "descripcion_del_cambio_interno": "Eliminar la función completa 'miFuncionVieja(arg)' que empieza cerca de la linea 50. Incluir el comentario anterior.",
    // --- Ejemplo crear_archivo ---
    // "archivo": "nueva/ruta/miClaseApi.php",
    // "proposito_del_archivo": "Contendrá la clase MiClaseApi para interactuar con servicio X"
    // ... otros ejemplos según acción...
  },
  "archivos_relevantes": [
    "ruta/relativa/origen.php", // Ejemplo mover
    "ruta/relativa/destino.php", // Ejemplo mover
    // Lista COMPLETA de archivos a leer en Paso 2
  ],
  "razonamiento": "Justificación DETALLADA del cambio o motivo claro de no_accion."
}
```""")

    if historialCambiosTexto:
        promptPartes.append(
            "\n--- HISTORIAL DE CAMBIOS RECIENTES (para tu contexto, EVITA REPETIR o deshacer) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")

    promptPartes.append("\n--- CÓDIGO FUENTE COMPLETO A ANALIZAR ---")
    promptPartes.append(contextoCodigoCompleto)
    promptPartes.append("--- FIN CÓDIGO ---")
    promptPartes.append(
        "\nRecuerda: JSON estricto, UNA acción pequeña y segura, parámetros DETALLADOS, razonamiento CLARO, archivos relevantes COMPLETOS.")

    promptCompleto = "\n".join(promptPartes)
    # ... (llamada a Gemini y parseo igual que antes) ...
    log.info(f"{logPrefix} Enviando solicitud de DECISIÓN a Gemini...")
    # Debug corto del prompt
    log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:200]}...")
    log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-200:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,  # Un poco más determinista para la decisión
                # max_output_tokens=1024 # Limitar tamaño de respuesta si es necesario
            ),
            safety_settings={  # Ser un poco más permisivo si bloquea código legítimo
                'HATE': 'BLOCK_ONLY_HIGH',
                'HARASSMENT': 'BLOCK_ONLY_HIGH',
                'SEXUAL': 'BLOCK_ONLY_HIGH',
                'DANGEROUS': 'BLOCK_ONLY_HIGH'
            }
        )
        log.info(f"{logPrefix} Respuesta de DECISIÓN recibida.")
        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta:
            return None  # Error ya logueado

        sugerenciaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)
        if sugerenciaJson and sugerenciaJson.get("tipo_analisis") != "refactor_decision":
            log.error(
                f"{logPrefix} Respuesta JSON no es del tipo esperado 'refactor_decision'. JSON: {sugerenciaJson}")
            return None
        return sugerenciaJson

    except Exception as e:
        _manejarExcepcionGemini(
            e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None


# --- PASO 2: Ejecutar Acción (Prompt Modificado) ---
def ejecutarAccionConGemini(decisionParseada, contextoCodigoReducido):
    logPrefix = "ejecutarAccionConGemini (Paso 2):"
    if not configurarGemini():
        return None
    if not decisionParseada:
        log.error(f"{logPrefix} No se proporcionó la decisión del Paso 1.")
        return None

    nombreModelo = settings.MODELOGEMINI
    try:
        # Nota: Si usas genai.Client directamente como en tu ejemplo,
        # inicialízalo aquí en lugar de usar genai.GenerativeModel.
        # Si usas genai.configure globalmente, GenerativeModel está bien.
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{logPrefix} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(f"{logPrefix} Error inicializando modelo '{nombreModelo}': {e}")
        return None

    # --- Define el Schema que esperas ---
    # Coincide con la estructura que le pedías en el prompt
    expected_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            'tipo_resultado': types.Schema(type=types.Type.STRING),
            'archivos_modificados': types.Schema(
                type=types.Type.OBJECT,
                # Permite cualquier propiedad (ruta de archivo) cuyo valor sea string (contenido)
                additional_properties=types.Schema(type=types.Type.STRING)
            )
        },
        required=['tipo_resultado', 'archivos_modificados'] # Campos obligatorios
    )

    # --- Construye el Prompt (Ahora SIN las instrucciones de formato JSON) ---
    accion = decisionParseada.get("accion_propuesta")
    descripcion = decisionParseada.get("descripcion")
    params = decisionParseada.get("parametros_accion", {})
    razonamiento_paso1 = decisionParseada.get("razonamiento")

    promptPartes = []
    promptPartes.append("Eres un asistente de refactorización que EJECUTA una decisión ya tomada.")
    promptPartes.append("Se ha decidido realizar la siguiente acción basada en el análisis previo:")
    promptPartes.append("\n--- DECISIÓN DEL PASO 1 (Debes seguirla EXACTAMENTE) ---")
    promptPartes.append(f"Acción: {accion}")
    promptPartes.append(f"Descripción: {descripcion}")
    promptPartes.append(f"Parámetros Detallados: {json.dumps(params)}")
    promptPartes.append(f"Razonamiento (Contexto): {razonamiento_paso1}")
    promptPartes.append("--- FIN DECISIÓN ---")
    promptPartes.append("\nSe te proporciona el contenido ACTUAL de los archivos relevantes (si aplica).")
    promptPartes.append("**TU ÚNICA TAREA:** Realizar la acción descrita en los 'Parámetros Detallados' y proporcionar el CONTENIDO COMPLETO Y FINAL para CADA archivo que resulte modificado o creado como resultado.")
    promptPartes.append("\n--- REGLAS DE EJECUCIÓN ---")
    promptPartes.append("1.  SIGUE LA DECISIÓN AL PIE DE LA LETRA.")
    promptPartes.append("2.  Para CADA archivo afectado (modificado o creado), proporciona su contenido ÍNTEGRO final.")
    promptPartes.append("3.  PRESERVA EL RESTO del código no afectado en archivos modificados.")
    promptPartes.append("4.  MOVIMIENTOS: Si mueves código y `eliminar_de_origen` es true, BORRA el código original del `archivo_origen`.")
    promptPartes.append("5.  MODIFICACIONES INTERNAS: Aplica EXACTAMENTE la `descripcion_del_cambio_interno`.")
    promptPartes.append("6.  CREACIÓN: Genera contenido inicial basado en `proposito_del_archivo`.")
    promptPartes.append("7.  CONVENCIONES DE CÓDIGO: Respeta las convenciones del código existente. Evita errores PHP/JS comunes.")
    promptPartes.append("8.  (Opcional) Añade un comentario simple como `// Refactor IA: [Descripción corta]` cerca del cambio.")
    # QUITAMOS las instrucciones sobre formato JSON, escapado, y el ejemplo ```json ```

    if contextoCodigoReducido:
        promptPartes.append("\n--- CONTENIDO ACTUAL DE ARCHIVOS RELEVANTES ---")
        promptPartes.append(contextoCodigoReducido)
        promptPartes.append("--- FIN CONTENIDO ---")
    else:
        promptPartes.append("\n(No se proporcionó contenido de archivo para esta acción específica)")

    promptCompleto = "\n".join(promptPartes)

    log.info(f"{logPrefix} Enviando solicitud de EJECUCIÓN a Gemini (MODO JSON)...")
    # Debug corto del prompt
    log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:200]}...")
    log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-200:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=types.GenerationConfig(
                temperature=0.4, # Puedes ajustar
                # --- ¡Aquí está la clave! ---
                response_mime_type="application/json",
                response_schema=expected_schema
                # ------------------------------
            ),
            safety_settings={ # Mantén tus safety settings
                'HATE': 'BLOCK_ONLY_HIGH',
                'HARASSMENT': 'BLOCK_ONLY_HIGH',
                'SEXUAL': 'BLOCK_ONLY_HIGH',
                'DANGEROUS': 'BLOCK_ONLY_HIGH'
            }
        )
        log.info(f"{logPrefix} Respuesta de EJECUCIÓN (MODO JSON) recibida.")

        # --- El parseo ahora debería ser más directo ---
        # La respuesta YA debería ser un objeto JSON parseable si la API funcionó bien.
        # La función _extraerTextoRespuesta puede que aún necesite usarse si la respuesta
        # viene encapsulada de alguna forma, pero idealmente .text contendría el JSON.
        # Sin embargo, la forma más directa con JSON mode es acceder a .parts[0].json
        # (o manejar el stream como en tu ejemplo y concatenar/parsear al final)

        # Intento 1: Acceso directo (si NO es streaming y la API lo soporta bien)
        try:
            # Acceder al contenido JSON directamente si la estructura de respuesta lo permite
            # Esto puede variar ligeramente según la versión de la SDK y el tipo de respuesta
            # Puede ser necesario inspeccionar el objeto 'respuesta'
            if respuesta.parts:
                 # Suponiendo que el JSON está en la primera parte
                 # Usamos getattr para seguridad
                 resultadoJson = getattr(respuesta.parts[0], 'json', None)
                 if resultadoJson is None:
                     # Fallback: Intentar parsear el texto si 'json' no está directamente
                     log.warning(f"{logPrefix} Atributo '.json' no encontrado en la parte de la respuesta. Intentando parsear .text")
                     textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
                     if not textoRespuesta: return None
                     resultadoJson = _limpiarYParsearJson(textoRespuesta, logPrefix) # Usar el limpiador como fallback
                 else:
                     log.info(f"{logPrefix} JSON obtenido directamente del atributo '.json' de la respuesta.")

            else:
                 log.error(f"{logPrefix} La respuesta no contiene 'parts'. No se pudo extraer JSON.")
                 log.debug(f"{logPrefix} Respuesta completa (objeto): {respuesta}")
                 return None

        except AttributeError as ae:
             log.warning(f"{logPrefix} Error de atributo accediendo a partes/json de la respuesta ({ae}). Intentando parsear .text")
             textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
             if not textoRespuesta: return None
             resultadoJson = _limpiarYParsearJson(textoRespuesta, logPrefix) # Usar el limpiador como fallback
        except Exception as e_parse:
             log.error(f"{logPrefix} Error inesperado extrayendo/parseando JSON de respuesta en modo JSON: {e_parse}", exc_info=True)
             log.debug(f"{logPrefix} Respuesta completa (objeto): {respuesta}")
             return None


        # --- Validación post-parseo (igual que antes) ---
        if resultadoJson and resultadoJson.get("tipo_resultado") != "ejecucion_cambio":
             log.error(f"{logPrefix} Respuesta JSON no es del tipo esperado 'ejecucion_cambio'. JSON: {resultadoJson}")
             return None
        if resultadoJson is None:
             log.error(f"{logPrefix} El parseo/extracción final de JSON falló.")
             return None

        # Si la acción es eliminar o crear directorio, Gemini debería devolver {} vacío
        # según el schema (additional_properties). Validar esto.
        accion_sin_contenido = accion in ["eliminar_archivo", "crear_directorio"]
        archivos_mod = resultadoJson.get("archivos_modificados")

        if accion_sin_contenido and archivos_mod != {}:
             log.warning(f"{logPrefix} Se esperaba 'archivos_modificados' vacío para la acción '{accion}', pero se recibió: {archivos_mod}. Se procederá con dict vacío.")
             resultadoJson["archivos_modificados"] = {}
        elif not accion_sin_contenido and not isinstance(archivos_mod, dict):
             log.error(f"{logPrefix} Se esperaba un diccionario para 'archivos_modificados' en acción '{accion}', pero se recibió tipo {type(archivos_mod)}.")
             return None

        log.info(f"{logPrefix} Respuesta JSON (MODO JSON) parseada y validada correctamente.")
        return resultadoJson

    except Exception as e:
        _manejarExcepcionGemini(e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None


# --- Helpers Internos (sin cambios en extraerTexto, manejarExcepcion; cambios en limpiarYParsear) ---
# _extraerTextoRespuesta, _manejarExcepcionGemini (sin cambios)
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
                textoRespuesta = "".join(
                    part.text for part in respuesta.parts if hasattr(part, 'text'))
        elif hasattr(respuesta, 'candidates') and respuesta.candidates:
            # Comprobar si candidates es iterable y no vacío
            if isinstance(respuesta.candidates, (list, tuple)) and respuesta.candidates:
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

    # A veces Gemini añade texto antes o después del JSON real
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
        # ### MODIFICADO ### Log de tamaño
        log.debug(
            f"{logPrefix} Intentando parsear JSON candidato (tamaño: {len(json_candidate)})...")
        resultadoJson = json.loads(json_candidate)
        log.info(f"{logPrefix} JSON parseado correctamente.")
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
        log.error(f"{logPrefix} Error argumento inválido API Gemini (InvalidArgument): {e}. ¿Prompt mal formado o contenido bloqueado implícitamente?")
    elif isinstance(e, google.api_core.exceptions.PermissionDenied):
        log.error(
            f"{logPrefix} Error de permiso API Gemini (PermissionDenied): {e}. ¿API Key incorrecta o sin permisos?")
    elif isinstance(e, google.api_core.exceptions.ServiceUnavailable):
        log.error(
            f"{logPrefix} Error servicio no disponible API Gemini (ServiceUnavailable): {e}. Reintentar más tarde.")
    # Intentar manejo específico de excepciones de bloqueo si están disponibles
    elif type(e).__name__ in ['BlockedPromptException', 'StopCandidateException']:
        log.error(
            f"{logPrefix} Prompt bloqueado o generación detenida por Gemini: {e}")
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
                candidate = respuesta.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    finish_reason = f"FinishReason: {candidate.finish_reason}"
                if hasattr(candidate, 'safety_ratings'):
                    safety_ratings = str(candidate.safety_ratings)
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
