# nucleo/analizadorCodigo.py
import os
import logging
import json
import google.generativeai as genai
import google.api_core.exceptions
from config import settings

# ... (configurarGemini, listarArchivosProyecto, leerArchivos sin cambios) ...
log = logging.getLogger(__name__)
geminiConfigurado = False
def configurarGemini():
    global geminiConfigurado
    if geminiConfigurado: return True
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
        extensionesPermitidas = getattr(settings, 'EXTENSIONESPERMITIDAS', ['.php', '.js', '.py', '.md', '.txt'])
        extensionesPermitidas = [ext.lower() for ext in extensionesPermitidas]
    if directoriosIgnorados is None:
        directoriosIgnorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', ['.git', 'vendor', 'node_modules'])
    try:
        log.info(f"{logPrefix} Listando archivos en: {rutaProyecto}")
        for raiz, dirs, archivos in os.walk(rutaProyecto, topdown=True):
            # Excluir directorios ignorados
            dirs[:] = [d for d in dirs if d not in directoriosIgnorados and not d.startswith('.')]

            for nombreArchivo in archivos:
                # Ignorar archivos ocultos
                if nombreArchivo.startswith('.'):
                    continue

                _, ext = os.path.splitext(nombreArchivo)
                if ext.lower() in extensionesPermitidas:
                    rutaCompleta = os.path.join(raiz, nombreArchivo)
                    # Normalizar la ruta para consistencia
                    archivosProyecto.append(os.path.normpath(rutaCompleta))

        log.info(f"{logPrefix} Archivos relevantes encontrados: {len(archivosProyecto)}")
        return archivosProyecto
    except Exception as e:
        log.error(f"{logPrefix} Error listando archivos en {rutaProyecto}: {e}", exc_info=True)
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
             log.error(f"{logPrefix} Archivo '{rutaAbsoluta}' está fuera de la ruta base '{rutaBase}'. Se omitirá.")
             archivosFallidos.append(rutaAbsoluta)
             continue
        # Comprobar si el archivo realmente existe antes de intentar leerlo
        if not os.path.exists(rutaAbsNorm) or not os.path.isfile(rutaAbsNorm):
            log.warning(f"{logPrefix} Archivo no encontrado o no es un archivo válido en '{rutaAbsNorm}'. Se omitirá.")
            archivosFallidos.append(rutaAbsoluta)
            continue

        try:
            # Calcular ruta relativa de forma segura
            rutaRelativa = os.path.relpath(rutaAbsNorm, rutaBaseNorm).replace(os.sep, '/')

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
         log.warning(f"{logPrefix} No se pudieron leer {len(archivosFallidos)} archivos: {archivosFallidos[:5]}...") # Mostrar solo algunos

    if archivosLeidos > 0:
        log.info(f"{logPrefix} Leídos {archivosLeidos} archivos. Tamaño total: {tamanoKB:.2f} KB.")
        return contenidoConcatenado
    else:
         log.error(f"{logPrefix} No se pudo leer ningún archivo de la lista proporcionada.")
         return None


# --- PASO 1: Obtener Decisión (Prompt Modificado) ---
def obtenerDecisionRefactor(contextoCodigoCompleto, historialCambiosTexto=None):
    """
    PASO 1: Analiza código COMPLETO e historial para DECIDIR una acción DETALLADA.
    Retorna JSON con ACCIÓN, PARÁMETROS ESPECÍFICOS, RAZONAMIENTO y ARCHIVOS RELEVANTES.
    """
    logPrefix = "obtenerDecisionRefactor (Paso 1):"
    # ... (configuración de Gemini igual) ...
    if not configurarGemini(): return None
    if not contextoCodigoCompleto:
        log.error(f"{logPrefix} No se proporcionó contexto de código.")
        return None

    nombreModelo = settings.MODELOGEMINI
    try:
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{logPrefix} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(f"{logPrefix} Error inicializando modelo '{nombreModelo}': {e}")
        return None

    # ### MODIFICADO ### Prompt más exigente para Paso 1
    promptPartes = []
    promptPartes.append("Eres un asistente experto en refactorización de código PHP/JS (WordPress). Tu tarea es analizar TODO el código fuente y el historial, y proponer UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA.")
    promptPartes.append("Prioriza: eliminar código muerto, simplificar lógica compleja, añadir validaciones FALTANTES y básicas (ej: `isset`, `!empty`), reducir duplicación MÍNIMA (mover funciones/clases SOLO si es obvio y mejora claramente la organización), mejorar legibilidad (nombres en español `camelCase`). EVITA cambios masivos o reestructuraciones grandes. Puedes organizar funciones, la estructura del proyecto es desordenada, es importante ordenar. No es importante ni necesario que agregues nuevos comentarios a funciones viejas para explicar lo que hacen. Puedes hacer mejoras de optimización, seguridad, simplificación sin arriesgarte a que el codigo falle.")
    promptPartes.append("Considera el historial para NO repetir errores, NO deshacer trabajo anterior y mantener la consistencia.")

    promptPartes.append("\n--- REGLAS ESTRICTAS PARA TU RESPUESTA (DECISIÓN) ---")
    promptPartes.append("1.  **IDENTIFICA LA ACCIÓN**: Elige UNA de: `mover_funcion`, `mover_clase`, `modificar_codigo_en_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`. Si NINGUNA acción es segura/útil/necesaria, USA `no_accion`.")
    promptPartes.append("2.  **DESCRIBE CLARAMENTE**: En `descripcion`, sé MUY específico para un mensaje de commit útil (ej: 'Refactor(Seguridad): Añade isset() a $_GET['param'] en archivo.php', 'Refactor(Clean): Elimina función duplicada viejaFuncion() de utils_old.php', 'Refactor(Org): Mueve función auxiliar miHelper() de main.php a helpers/ui.php').")
    promptPartes.append("3.  **DETALLA PARÁMETROS SIN AMBIGÜEDAD**: En `parametros_accion`, incluye TODA la información necesaria para que OTRO proceso (Paso 2) realice el cambio SIN DUDAS. Usa rutas RELATIVAS.")
    promptPartes.append("    -   `mover_funcion`/`mover_clase`: `archivo_origen`, `archivo_destino`, `nombre_funcion`/`nombre_clase`. **IMPORTANTE**: Indica si la función/clase debe ser **BORRADA** del origen.")
    promptPartes.append("    -   `modificar_codigo_en_archivo`: `archivo`, `descripcion_del_cambio_interno` (MUY detallado: 'Eliminar bloque if comentado entre lineas 80-95', 'Reemplazar bucle for en linea 120 por array_map', 'Añadir `global $wpdb;` al inicio de la función `miQuery()` en linea 30', 'Borrar la declaración completa de la función `funcionObsoleta(arg1)`'). **NO incluyas el código a buscar/reemplazar aquí**, solo la instrucción CLARA.")
    promptPartes.append("    -   `crear_archivo`: `archivo` (ruta completa relativa), `proposito_del_archivo` (breve, ej: 'Clase para manejar la API externa X').")
    promptPartes.append("    -   `eliminar_archivo`: `archivo` (ruta relativa).")
    promptPartes.append("    -   `crear_directorio`: `directorio` (ruta relativa).")
    promptPartes.append("4.  **LISTA ARCHIVOS RELEVANTES COMPLETAMENTE**: En `archivos_relevantes`, incluye **TODAS** las rutas relativas de archivos que el Paso 2 **NECESITARÁ LEER** para ejecutar la acción (origen, destino, archivos que usan lo movido si aplica y es fácil de determinar, etc.). ¡Esto es CRUCIAL y debe ser preciso!")
    promptPartes.append("5.  **EXPLICA TU RAZONAMIENTO DETALLADAMENTE**: En `razonamiento`, justifica CLARAMENTE el *por qué* de esta acción (beneficio, problema que resuelve) o la razón específica para `no_accion` (ej: 'Código ya optimizado', 'No se encontraron mejoras seguras', 'Requiere análisis manual').")
    promptPartes.append("6.  **FORMATO JSON ESTRICTO**: Responde **ÚNICAMENTE** con el JSON. SIN texto introductorio ni explicaciones fuera del JSON.")
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
        promptPartes.append("\n--- HISTORIAL DE CAMBIOS RECIENTES (para tu contexto, EVITA REPETIR o deshacer) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")

    promptPartes.append("\n--- CÓDIGO FUENTE COMPLETO A ANALIZAR ---")
    promptPartes.append(contextoCodigoCompleto)
    promptPartes.append("--- FIN CÓDIGO ---")
    promptPartes.append("\nRecuerda: JSON estricto, UNA acción pequeña y segura, parámetros DETALLADOS, razonamiento CLARO, archivos relevantes COMPLETOS.")

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
                temperature=0.3, # Un poco más determinista para la decisión
                # max_output_tokens=1024 # Limitar tamaño de respuesta si es necesario
                ),
            safety_settings={ # Ser un poco más permisivo si bloquea código legítimo
                 'HATE': 'BLOCK_ONLY_HIGH',
                 'HARASSMENT': 'BLOCK_ONLY_HIGH',
                 'SEXUAL' : 'BLOCK_ONLY_HIGH',
                 'DANGEROUS' : 'BLOCK_ONLY_HIGH'
            }
        )
        log.info(f"{logPrefix} Respuesta de DECISIÓN recibida.")
        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta: return None # Error ya logueado

        sugerenciaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)
        if sugerenciaJson and sugerenciaJson.get("tipo_analisis") != "refactor_decision":
            log.error(f"{logPrefix} Respuesta JSON no es del tipo esperado 'refactor_decision'. JSON: {sugerenciaJson}")
            return None
        return sugerenciaJson

    except Exception as e:
        _manejarExcepcionGemini(e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None


# --- PASO 2: Ejecutar Acción (Prompt Modificado) ---
def ejecutarAccionConGemini(decisionParseada, contextoCodigoReducido):
    """
    PASO 2: Recibe la DECISIÓN DETALLADA del Paso 1 y el CONTEXTO REDUCIDO.
    Pide a Gemini generar el CONTENIDO FINAL de los archivos afectados SIGUIENDO LA DECISIÓN.
    Retorna JSON simple {ruta: nuevoContenidoCompleto}.
    """
    logPrefix = "ejecutarAccionConGemini (Paso 2):"
    # ... (configuración de Gemini igual) ...
    if not configurarGemini(): return None
    if not decisionParseada:
        log.error(f"{logPrefix} No se proporcionó la decisión del Paso 1.")
        return None

    nombreModelo = settings.MODELOGEMINI
    try:
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{logPrefix} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(f"{logPrefix} Error inicializando modelo '{nombreModelo}': {e}")
        return None

    # Extraer info clave de la decisión
    accion = decisionParseada.get("accion_propuesta")
    descripcion = decisionParseada.get("descripcion")
    params = decisionParseada.get("parametros_accion", {})
    razonamiento_paso1 = decisionParseada.get("razonamiento") # Info extra de contexto

    # ### MODIFICADO ### Prompt más directivo para Paso 2
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
    promptPartes.append("**TU ÚNICA TAREA:** Generar el CONTENIDO COMPLETO Y FINAL para CADA archivo que resulte modificado o creado por esta acción. Debes aplicar los cambios descritos en los 'Parámetros Detallados' de la decisión.")

    promptPartes.append("\n--- REGLAS DE EJECUCIÓN ---")
    promptPartes.append("1.  **SIGUE LA DECISIÓN AL PIE DE LA LETRA**: Aplica la `accion` usando los `parametros_accion` especificados.")
    promptPartes.append("2.  **CONTENIDO COMPLETO**: Para CADA archivo afectado (modificado o creado), proporciona su contenido ÍNTEGRO final.")
    promptPartes.append("3.  **PRESERVA EL RESTO**: En archivos modificados, NO alteres código no relacionado con la acción.")
    promptPartes.append("4.  **MOVIMIENTOS**: Si mueves código (`mover_funcion`/`mover_clase` y `eliminar_de_origen` es true), BORRA el código original del `archivo_origen` y añádelo correctamente (formato, saltos de línea) en `archivo_destino`.")
    promptPartes.append("5.  **MODIFICACIONES INTERNAS**: Si es `modificar_codigo_en_archivo`, aplica EXACTAMENTE la `descripcion_del_cambio_interno`.")
    promptPartes.append("6.  **CREACIÓN**: Si es `crear_archivo`, genera contenido inicial basado en `proposito_del_archivo` (puede ser una estructura básica de clase/archivo PHP).")
    promptPartes.append("7.  **CONVENCIONES DE CÓDIGO**: Respeta las convenciones del código existente (ej: usa `<?` si es lo predominante, no `<?php`). Evita errores comunes como `<?` duplicados o mal cerrados. Usa `<? echo` si aplica.")
    promptPartes.append("8.  **(Opcional)** Añade un comentario simple como `// Refactor IA: [Descripción corta]` cerca del cambio.")
    promptPartes.append("9.  Evita las tareas de legibilidad, no son importantes, ejemplo, Refactor(Legibilidad): Añade comentario")

    promptPartes.append("\n--- FORMATO DE RESPUESTA (JSON ESTRICTO) ---")
    promptPartes.append("Responde **ÚNICAMENTE** con un JSON que mapea la ruta RELATIVA del archivo a su **nuevo contenido COMPLETO**.")
    promptPartes.append("Si la acción es `eliminar_archivo` o `crear_directorio`, responde con el diccionario `archivos_modificados` VACÍO.")
    promptPartes.append("""
```json
{
  "tipo_resultado": "ejecucion_cambio",
  "archivos_modificados": {
    "ruta/relativa/archivo_modificado1.php": "<?php\\n/* NUEVO CONTENIDO COMPLETO DEL ARCHIVO 1 */\\n?>",
    "ruta/relativa/archivo_creado2.php": "<?php\\n/* CONTENIDO INICIAL DEL ARCHIVO 2 */\\n?>"
    // Incluir una entrada por CADA archivo afectado (modificado o creado)
    // o {} si es eliminar_archivo / crear_directorio
  }
}
```""")

    if contextoCodigoReducido:
        promptPartes.append("\n--- CONTENIDO ACTUAL DE ARCHIVOS RELEVANTES ---")
        promptPartes.append(contextoCodigoReducido)
        promptPartes.append("--- FIN CONTENIDO ---")
    else:
        promptPartes.append("\n(No se proporcionó contenido de archivo para esta acción específica, ej: crear archivo nuevo, crear directorio)")

    promptPartes.append("\nRecuerda: Sigue la decisión, genera contenido completo, formato JSON estricto.")

    promptCompleto = "\n".join(promptPartes)
    # ... (llamada a Gemini y parseo igual que antes, pero quizás temperatura más baja) ...
    log.info(f"{logPrefix} Enviando solicitud de EJECUCIÓN a Gemini...")
    log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:200]}...")
    log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-200:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2, # Más determinista para la ejecución
                # max_output_tokens=8000 # Ajustar si se espera contenido muy largo
                ),
             safety_settings={ # Ser un poco más permisivo si bloquea código legítimo
                 'HATE': 'BLOCK_ONLY_HIGH',
                 'HARASSMENT': 'BLOCK_ONLY_HIGH',
                 'SEXUAL' : 'BLOCK_ONLY_HIGH',
                 'DANGEROUS' : 'BLOCK_ONLY_HIGH'
             }
        )
        log.info(f"{logPrefix} Respuesta de EJECUCIÓN recibida.")
        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta: return None

        resultadoJson = _limpiarYParsearJson(textoRespuesta, logPrefix)
        # Validación básica del tipo y estructura ya hecha en _limpiarYParsearJson y el llamador (principal.py)
        if resultadoJson and resultadoJson.get("tipo_resultado") != "ejecucion_cambio":
             log.error(f"{logPrefix} Respuesta JSON no es del tipo esperado 'ejecucion_cambio'. JSON: {resultadoJson}")
             return None

        # Validación extra: ¿Las claves del JSON coinciden (más o menos) con los archivos relevantes esperados?
        # Esta validación se hace mejor en el Paso 3 (Verificación) en principal.py
        # Aquí solo retornamos el JSON parseado.

        return resultadoJson

    except Exception as e:
        _manejarExcepcionGemini(e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None


# --- Helpers Internos (sin cambios) ---
# _extraerTextoRespuesta, _limpiarYParsearJson, _manejarExcepcionGemini
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
                 textoRespuesta = "".join(part.text for part in respuesta.parts if hasattr(part, 'text'))
        elif hasattr(respuesta, 'candidates') and respuesta.candidates:
             # Comprobar si candidates es iterable y no vacío
             if isinstance(respuesta.candidates, (list, tuple)) and respuesta.candidates:
                 candidate = respuesta.candidates[0]
                 if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts') and candidate.content.parts:
                     if isinstance(candidate.content.parts, (list, tuple)) and candidate.content.parts:
                         textoRespuesta = "".join(part.text for part in candidate.content.parts if hasattr(part, 'text'))

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

        return textoRespuesta.strip() # Devolver texto limpio

    except (AttributeError, IndexError, ValueError, TypeError) as e:
        log.error(f"{logPrefix} Error extrayendo texto de la respuesta: {e}. Respuesta obj: {respuesta}", exc_info=True)
        return None
    except Exception as e: # Captura genérica
        log.error(f"{logPrefix} Error inesperado extrayendo texto: {e}", exc_info=True)
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
        log.error(f"{logPrefix} Respuesta de Gemini no parece contener un bloque JSON válido {{...}}. Respuesta (limpia inicial): {textoLimpio[:500]}...")
        log.debug(f"{logPrefix} Respuesta Original Completa:\n{textoRespuesta}")
        return None

    json_candidate = textoLimpio[start_brace : end_brace + 1]

    try:
        log.debug(f"{logPrefix} Intentando parsear JSON candidato:\n{json_candidate[:500]}...")
        resultadoJson = json.loads(json_candidate)
        log.info(f"{logPrefix} JSON parseado correctamente.")
        return resultadoJson
    except json.JSONDecodeError as e:
        log.error(f"{logPrefix} Error crítico parseando JSON de Gemini: {e}")
        log.error(f"{logPrefix} JSON Candidato que falló:\n{json_candidate[:1000]}...") # Loguear más para depurar
        log.debug(f"{logPrefix} Respuesta Original Completa:\n{textoRespuesta}")
        return None
    except Exception as e: # Captura errores inesperados durante el parseo
        log.error(f"{logPrefix} Error inesperado parseando JSON: {e}", exc_info=True)
        return None


def _manejarExcepcionGemini(e, logPrefix, respuesta=None):
    """Maneja y loguea excepciones comunes de la API de Gemini."""
    if isinstance(e, google.api_core.exceptions.ResourceExhausted):
        log.error(f"{logPrefix} Error de cuota API Gemini (ResourceExhausted): {e}")
    elif isinstance(e, google.api_core.exceptions.InvalidArgument):
        # Esto a menudo incluye errores por contenido inválido en el prompt (no solo tamaño)
        log.error(f"{logPrefix} Error argumento inválido API Gemini (InvalidArgument): {e}. ¿Prompt mal formado o contenido bloqueado implícitamente?")
    elif isinstance(e, google.api_core.exceptions.PermissionDenied):
         log.error(f"{logPrefix} Error de permiso API Gemini (PermissionDenied): {e}. ¿API Key incorrecta o sin permisos?")
    elif isinstance(e, google.api_core.exceptions.ServiceUnavailable):
         log.error(f"{logPrefix} Error servicio no disponible API Gemini (ServiceUnavailable): {e}. Reintentar más tarde.")
    # Intentar manejo específico de excepciones de bloqueo si están disponibles
    elif type(e).__name__ in ['BlockedPromptException', 'StopCandidateException']:
         log.error(f"{logPrefix} Prompt bloqueado o generación detenida por Gemini: {e}")
         # Intentar extraer info del objeto respuesta si se pasó
         finish_reason = "Desconocida"
         safety_ratings = "No disponibles"
         if respuesta:
              if hasattr(respuesta, 'prompt_feedback'):
                   feedback = respuesta.prompt_feedback
                   if hasattr(feedback, 'block_reason'): finish_reason = f"BlockReason: {feedback.block_reason}"
                   if hasattr(feedback, 'safety_ratings'): safety_ratings = str(feedback.safety_ratings)
              if hasattr(respuesta, 'candidates') and respuesta.candidates:
                   candidate = respuesta.candidates[0]
                   if hasattr(candidate, 'finish_reason'): finish_reason = f"FinishReason: {candidate.finish_reason}"
                   if hasattr(candidate, 'safety_ratings'): safety_ratings = str(candidate.safety_ratings)
         log.error(f"{logPrefix} Razón: {finish_reason}, Safety: {safety_ratings}")

    else:
        # Error genérico de la API o del cliente
        log.error(f"{logPrefix} Error inesperado en llamada API Gemini: {type(e).__name__} - {e}", exc_info=True)
        if respuesta:
            try:
                feedback = getattr(respuesta, 'prompt_feedback', None)
                if feedback: log.error(f"{logPrefix} Prompt Feedback (si disponible): {feedback}")
            except Exception as e_fb:
                 log.debug(f"Error al intentar obtener feedback de la respuesta: {e_fb}")