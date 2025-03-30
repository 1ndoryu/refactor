# nucleo/analizadorCodigo.py
import os
import logging
import json
import google.generativeai as genai
import google.api_core.exceptions
from config import settings

log = logging.getLogger(__name__)

geminiConfigurado = False

# Configuración de Gemini (sin cambios)
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

# Listar y Leer archivos (sin cambios)
def listarArchivosProyecto(rutaProyecto, extensionesPermitidas=None, directoriosIgnorados=None):
    # ... (igual que antes) ...
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
            dirs[:] = [d for d in dirs if d not in directoriosIgnorados and not d.startswith('.')]
            for nombreArchivo in archivos:
                if nombreArchivo.startswith('.'): continue
                _, ext = os.path.splitext(nombreArchivo)
                if ext.lower() in extensionesPermitidas:
                    rutaCompleta = os.path.join(raiz, nombreArchivo)
                    archivosProyecto.append(os.path.normpath(rutaCompleta))
        log.info(f"{logPrefix} Archivos relevantes encontrados: {len(archivosProyecto)}")
        return archivosProyecto
    except Exception as e:
        log.error(f"{logPrefix} Error listando archivos: {e}")
        return None

def leerArchivos(listaArchivos, rutaBase):
    # ... (igual que antes) ...
    logPrefix = "leerArchivos:"
    contenidoConcatenado = ""
    archivosLeidos = 0
    bytesTotales = 0
    for rutaAbsoluta in listaArchivos:
        try:
            rutaRelativa = os.path.relpath(rutaAbsoluta, rutaBase).replace(os.sep, '/')
            with open(rutaAbsoluta, 'r', encoding='utf-8', errors='ignore') as f:
                contenido = f.read()
                bytesArchivo = len(contenido.encode('utf-8'))
                contenidoConcatenado += f"########## START FILE: {rutaRelativa} ##########\n"
                contenidoConcatenado += contenido
                contenidoConcatenado += f"\n########## END FILE: {rutaRelativa} ##########\n\n"
                archivosLeidos += 1
                bytesTotales += bytesArchivo
        except Exception as e:
            log.error(f"{logPrefix} Error leyendo {rutaAbsoluta}: {e}")
    tamanoKB = bytesTotales / 1024
    log.info(f"{logPrefix} Leídos {archivosLeidos} archivos. Tamaño total: {tamanoKB:.2f} KB")
    return contenidoConcatenado if archivosLeidos > 0 else None


# --- NUEVO: Función para el Paso 1: Obtener Decisión ---
def obtenerDecisionRefactor(contextoCodigoCompleto, historialCambiosTexto=None):
    """
    PASO 1: Analiza el código COMPLETO y el historial para DECIDIR una acción.
    Retorna un JSON describiendo la ACCIÓN PROPUESTA y los ARCHIVOS RELEVANTES.
    """
    logPrefix = "obtenerDecisionRefactor (Paso 1):"
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

    # --- Prompt para Paso 1 (Enfoque en DECISIÓN) ---
    promptPartes = []
    promptPartes.append("Eres un asistente experto en refactorización de código PHP/JS (WordPress). Tu tarea es analizar TODO el código fuente proporcionado y proponer UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA.")
    promptPartes.append("Prioriza: eliminar código muerto, simplificar, añadir validaciones básicas, reducir duplicación (mover funciones/clases a archivos apropiados si mejora la organización), mejorar legibilidad (nombres en español `camelCase`, comentarios claros).")
    promptPartes.append("Considera el historial para evitar repetir errores y ser consistente.")
    promptPartes.append("\n--- REGLAS PARA TU RESPUESTA (DECISIÓN) ---")
    promptPartes.append("1.  **IDENTIFICA LA ACCIÓN**: Elige una acción como `mover_funcion`, `mover_clase`, `modificar_codigo_en_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`. Si no hay acción segura/útil, usa `no_accion`.")
    promptPartes.append("2.  **DESCRIBE LA ACCIÓN**: En `descripcion`, sé claro para un mensaje de commit (ej: 'Refactor: Mueve función miFuncion de utils.php a helpers/general.php').")
    promptPartes.append("3.  **DETALLA LOS PARÁMETROS**: En `parametros_accion`, incluye SOLO los identificadores necesarios para que OTRO proceso realice el cambio. Usa rutas RELATIVAS.")
    promptPartes.append("    -   Para `mover_funcion` o `mover_clase`: `archivo_origen`, `archivo_destino`, `nombre_funcion` o `nombre_clase`.")
    promptPartes.append("    -   Para `modificar_codigo_en_archivo`: `archivo`, `descripcion_del_cambio_interno` (ej: 'eliminar bloque if comentado en línea X', 'simplificar bucle for'). NO incluyas el código a buscar/reemplazar aquí.")
    promptPartes.append("    -   Para `crear_archivo`: `archivo` (ruta completa), `proposito_del_archivo` (ej: 'Archivo para funciones auxiliares de UI').")
    promptPartes.append("    -   Para `eliminar_archivo`: `archivo`.")
    promptPartes.append("    -   Para `crear_directorio`: `directorio`.")
    promptPartes.append("4.  **LISTA ARCHIVOS RELEVANTES**: En `archivos_relevantes`, lista TODAS las rutas relativas de los archivos que el siguiente paso necesitará LEER para ejecutar la acción (origen, destino, etc.). Es CRUCIAL para reducir el contexto después.")
    promptPartes.append("5.  **EXPLICA EL RAZONAMIENTO**: En `razonamiento`, justifica brevemente el beneficio o la razón de `no_accion`.")
    promptPartes.append("6.  **FORMATO JSON ESTRICTO**: Responde ÚNICAMENTE con el JSON, sin texto adicional.")
    promptPartes.append("""
```json
{
  "tipo_analisis": "refactor_decision",
  "accion_propuesta": "TIPO_ACCION", // mover_funcion, modificar_codigo_en_archivo, etc.
  "descripcion": "Mensaje claro para commit.",
  "parametros_accion": {
    // --- Ejemplo para mover_funcion ---
    // "archivo_origen": "ruta/relativa/origen.php",
    // "archivo_destino": "ruta/relativa/destino.php",
    // "nombre_funcion": "nombreDeLaFuncion",
    // --- Ejemplo para modificar_codigo_en_archivo ---
    // "archivo": "ruta/relativa/archivo.php",
    // "descripcion_del_cambio_interno": "Eliminar función obsoleta 'viejaFuncion' cerca de línea 50",
    // --- Ejemplo para crear_archivo ---
    // "archivo": "nueva/ruta/helpers.php",
    // "proposito_del_archivo": "Funciones de ayuda generales"
    // ... otros ejemplos según acción
  },
  "archivos_relevantes": [
    "ruta/relativa/origen.php", // Ejemplo si es mover
    "ruta/relativa/destino.php" // Ejemplo si es mover
    // Lista de TODOS los archivos a leer en el Paso 2
  ],
  "razonamiento": "Beneficio del cambio o motivo de no_accion."
}
```""")

    if historialCambiosTexto:
        promptPartes.append("\n--- HISTORIAL DE CAMBIOS RECIENTES ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")
        promptPartes.append("¡Evita repetir errores del historial!")

    promptPartes.append("\n--- CÓDIGO FUENTE COMPLETO A ANALIZAR ---")
    promptPartes.append(contextoCodigoCompleto)
    promptPartes.append("--- FIN CÓDIGO ---")

    promptCompleto = "\n".join(promptPartes)
    log.info(f"{logPrefix} Enviando solicitud de DECISIÓN a Gemini...")
    log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:300]}...")
    log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-300:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(temperature=0.4),
            # safety_settings=... # Añadir si es necesario
        )
        log.info(f"{logPrefix} Respuesta de DECISIÓN recibida.")
        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta: return None # Error ya logueado en helper

        sugerenciaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)
        # Validación básica del tipo de análisis
        if sugerenciaJson and sugerenciaJson.get("tipo_analisis") != "refactor_decision":
            log.error(f"{logPrefix} Respuesta JSON no es del tipo esperado 'refactor_decision'. JSON: {sugerenciaJson}")
            return None
        return sugerenciaJson

    except Exception as e:
        _manejarExcepcionGemini(e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None

# --- NUEVO: Función para el Paso 2: Ejecutar Acción ---
def ejecutarAccionConGemini(decisionParseada, contextoCodigoReducido):
    """
    PASO 2: Recibe la DECISIÓN y el CONTEXTO REDUCIDO. Pide a Gemini
    generar el CONTENIDO FINAL de los archivos afectados.
    Retorna un JSON con {ruta: nuevoContenidoCompleto}.
    """
    logPrefix = "ejecutarAccionConGemini (Paso 2):"
    if not configurarGemini(): return None
    # contextoCodigoReducido PUEDE estar vacío si la acción es crear_directorio, etc.
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
    archivos_afectados_esperados = decisionParseada.get("archivos_relevantes", []) # Para validación

    # --- Prompt para Paso 2 (Enfoque en EJECUCIÓN) ---
    promptPartes = []
    promptPartes.append("Eres un asistente de refactorización. Se ha decidido realizar la siguiente acción:")
    promptPartes.append(f"**Acción:** {accion}")
    promptPartes.append(f"**Descripción:** {descripcion}")
    promptPartes.append(f"**Parámetros:** {json.dumps(params)}")
    promptPartes.append("\nSe te proporciona el contenido ACTUAL de los archivos relevantes.")
    promptPartes.append("Tu tarea es generar el CONTENIDO COMPLETO Y FINAL para CADA archivo que resulte modificado o creado por esta acción.")
    promptPartes.append("Asegúrate de preservar el resto del código en los archivos modificados.")
    promptPartes.append("Si mueves código, elimínalo del origen y añádelo al destino apropiadamente (ej. con saltos de línea).")
    promptPartes.append("Si modificas código interno, aplica el cambio descrito en 'descripcion_del_cambio_interno'.")
    promptPartes.append("Si creas un archivo, genera su contenido inicial basado en 'proposito_del_archivo'.")
    promptPartes.append("Recuerda usar `<?` y `<? echo` si aplica según las convenciones del proyecto.")
    promptPartes.append("Añade un comentario como `// Modificado/Movido automáticamente por IA` donde realices cambios significativos.")

    promptPartes.append("\n--- REGLAS PARA TU RESPUESTA (EJECUCIÓN) ---")
    promptPartes.append("1.  **CONTENIDO COMPLETO**: Para cada archivo afectado, proporciona su contenido ÍNTEGRO final.")
    promptPartes.append("2.  **FORMATO JSON ESTRICTO**: Responde ÚNICAMENTE con un JSON que mapea la ruta RELATIVA del archivo a su nuevo contenido COMPLETO.")
    promptPartes.append("""
```json
{
  "tipo_resultado": "ejecucion_cambio",
  "archivos_modificados": {
    "ruta/relativa/archivo_modificado1.php": "<?php /* NUEVO CONTENIDO COMPLETO DEL ARCHIVO 1 */ ?>",
    "ruta/relativa/archivo_modificado_o_creado2.php": "<?php /* NUEVO CONTENIDO COMPLETO DEL ARCHIVO 2 */ ?>"
    // ... incluir una entrada por CADA archivo que cambie o se cree
  }
}
```""")
    # Caso especial: acciones sin modificación de contenido
    if accion in ["eliminar_archivo", "crear_directorio"]:
         promptPartes.append(f"\n**NOTA:** Para la acción '{accion}', la estructura `archivos_modificados` puede estar vacía, ya que no se modifica contenido de archivos existentes. El script principal manejará la eliminación o creación del directorio/archivo vacío.")
         promptPartes.append("Responde con el JSON vacío si no hay archivos que modificar:")
         promptPartes.append("""
```json
{
  "tipo_resultado": "ejecucion_cambio",
  "archivos_modificados": {}
}
```""")

    if contextoCodigoReducido:
        promptPartes.append("\n--- CONTENIDO ACTUAL DE ARCHIVOS RELEVANTES ---")
        promptPartes.append(contextoCodigoReducido)
        promptPartes.append("--- FIN CONTENIDO ---")
    else:
        promptPartes.append("\n(No se requiere contenido de archivo para esta acción específica)")


    promptCompleto = "\n".join(promptPartes)
    log.info(f"{logPrefix} Enviando solicitud de EJECUCIÓN a Gemini...")
    log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:300]}...")
    log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-300:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(temperature=0.3), # Quizás más determinista aquí
            # safety_settings=...
        )
        log.info(f"{logPrefix} Respuesta de EJECUCIÓN recibida.")
        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta: return None

        resultadoJson = _limpiarYParsearJson(textoRespuesta, logPrefix)
        # Validación básica del tipo de resultado
        if resultadoJson and resultadoJson.get("tipo_resultado") != "ejecucion_cambio":
             log.error(f"{logPrefix} Respuesta JSON no es del tipo esperado 'ejecucion_cambio'. JSON: {resultadoJson}")
             return None
        # Validación extra: ¿Las claves del JSON coinciden (más o menos) con los archivos relevantes esperados?
        if resultadoJson and isinstance(resultadoJson.get("archivos_modificados"), dict):
             claves_recibidas = set(resultadoJson["archivos_modificados"].keys())
             claves_esperadas = set(archivos_afectados_esperados)
             if not claves_recibidas.issubset(claves_esperadas) and accion not in ["crear_archivo", "crear_directorio", "eliminar_archivo"]:
                 # Permitir crear archivo nuevo, o no tener claves si se elimina/crea dir
                 archivos_inesperados = claves_recibidas - claves_esperadas
                 if archivos_inesperados:
                    log.warning(f"{logPrefix} Gemini intentó modificar archivos no listados como relevantes en Paso 1: {archivos_inesperados}. Esperados: {claves_esperadas}. Se procederá igualmente.")

        return resultadoJson

    except Exception as e:
        _manejarExcepcionGemini(e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None


# --- Helpers Internos para llamadas a Gemini ---

def _extraerTextoRespuesta(respuesta, logPrefix):
    """Extrae el texto de la respuesta de Gemini de forma robusta."""
    textoRespuesta = ""
    try:
        # Intentar varias formas comunes de acceder al texto
        if hasattr(respuesta, 'text') and respuesta.text:
            textoRespuesta = respuesta.text
        elif respuesta.parts:
            textoRespuesta = "".join(part.text for part in respuesta.parts)
        elif respuesta.candidates and respuesta.candidates[0].content and respuesta.candidates[0].content.parts:
            textoRespuesta = "".join(part.text for part in respuesta.candidates[0].content.parts)

        if not textoRespuesta:
            # Loguear información de bloqueo si está disponible
            feedback = getattr(respuesta, 'prompt_feedback', None)
            block_reason = getattr(feedback, 'block_reason', 'Desconocido') if feedback else 'Desconocido'
            safety_ratings = getattr(feedback, 'safety_ratings', 'No disponibles') if feedback else 'No disponibles'
            finish_reason_cand = 'Desconocido'
            if respuesta.candidates:
                 finish_reason_cand = getattr(respuesta.candidates[0], 'finish_reason', 'Desconocido')

            log.error(f"{logPrefix} Respuesta de Gemini vacía. BlockReason: {block_reason}, FinishReason: {finish_reason_cand}, SafetyRatings: {safety_ratings}")
            log.debug(f"{logPrefix} Respuesta completa (objeto): {respuesta}")
            return None
        return textoRespuesta.strip() # Devolver texto limpio

    except (AttributeError, IndexError, ValueError) as e:
        log.error(f"{logPrefix} Error extrayendo texto de la respuesta: {e}. Respuesta obj: {respuesta}")
        return None
    except Exception as e: # Captura genérica
        log.error(f"{logPrefix} Error inesperado extrayendo texto: {e}", exc_info=True)
        return None

def _limpiarYParsearJson(textoRespuesta, logPrefix):
    """Limpia ```json ... ``` y parsea el JSON."""
    textoLimpio = textoRespuesta
    if textoLimpio.startswith("```json"):
        textoLimpio = textoLimpio[7:]
        if textoLimpio.endswith("```"):
            textoLimpio = textoLimpio[:-3]
    elif textoLimpio.startswith("```"): # A veces olvida 'json'
         textoLimpio = textoLimpio[3:]
         if textoLimpio.endswith("```"):
             textoLimpio = textoLimpio[:-3]
    textoLimpio = textoLimpio.strip()

    if not textoLimpio.startswith("{") or not textoLimpio.endswith("}"):
        log.error(f"{logPrefix} Respuesta de Gemini no parece JSON válido (falta {{}}). Respuesta (limpia): {textoLimpio}")
        log.debug(f"{logPrefix} Respuesta Original:\n{textoRespuesta}")
        return None

    try:
        log.debug(f"{logPrefix} Intentando parsear JSON:\n{textoLimpio}")
        resultadoJson = json.loads(textoLimpio)
        log.info(f"{logPrefix} JSON parseado correctamente.")
        return resultadoJson
    except json.JSONDecodeError as e:
        log.error(f"{logPrefix} Error crítico parseando JSON de Gemini: {e}")
        log.error(f"{logPrefix} Respuesta (limpia) que falló:\n{textoLimpio}")
        log.debug(f"{logPrefix} Respuesta Original:\n{textoRespuesta}")
        return None
    except Exception as e:
        log.error(f"{logPrefix} Error inesperado parseando JSON: {e}", exc_info=True)
        return None

def _manejarExcepcionGemini(e, logPrefix, respuesta=None):
    """Maneja y loguea excepciones comunes de la API de Gemini."""
    if isinstance(e, google.api_core.exceptions.ResourceExhausted):
        log.error(f"{logPrefix} Error de cuota API Gemini (ResourceExhausted): {e}")
    elif isinstance(e, google.api_core.exceptions.InvalidArgument):
        log.error(f"{logPrefix} Error argumento inválido (InvalidArgument): {e}. ¿Contexto muy grande?")
    elif isinstance(e, (getattr(genai.types, 'BlockedPromptException', None), # Manejar si existe
                         getattr(genai.types, 'StopCandidateException', None))): # Manejar si existe
        log.error(f"{logPrefix} Prompt bloqueado o generación detenida por Gemini: {e}")
        feedback = getattr(respuesta, 'prompt_feedback', None)
        safety_ratings = getattr(feedback, 'safety_ratings', 'No disponibles') if feedback else 'No disponibles'
        finish_reason = 'Desconocida'
        if respuesta and respuesta.candidates:
             finish_reason = getattr(respuesta.candidates[0], 'finish_reason', 'Desconocida')
             safety_ratings_cand = getattr(respuesta.candidates[0], 'safety_ratings', None)
             if safety_ratings_cand: safety_ratings = safety_ratings_cand
        log.error(f"{logPrefix} Razón: {finish_reason}, Safety: {safety_ratings}")
    else:
        log.error(f"{logPrefix} Error inesperado en llamada API Gemini: {type(e).__name__} - {e}", exc_info=True)
        if respuesta:
            feedback = getattr(respuesta, 'prompt_feedback', None)
            if feedback: log.error(f"{logPrefix} Prompt Feedback: {feedback}")