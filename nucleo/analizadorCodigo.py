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
    logPrefix = "leerArchivos:"
    contenidoConcatenado = ""
    archivosLeidos = 0
    bytesTotales = 0
    for rutaAbsoluta in listaArchivos:
        try:
            # Siempre usar '/' como separador en el encabezado
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


# --- REVISADO: Función para el Paso 1: Obtener Decisión ---
def obtenerDecisionRefactor(contextoCodigoCompleto, historialCambiosTexto=None):
    """
    PASO 1: Analiza el código COMPLETO y el historial para DECIDIR una acción.
    Retorna un JSON describiendo la ACCIÓN PROPUESTA, el RAZONAMIENTO DETALLADO,
    los PARÁMETROS ESPECÍFICOS y los ARCHIVOS RELEVANTES.
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

    # --- Prompt REVISADO para Paso 1 (Enfoque en DECISIÓN DETALLADA) ---
    promptPartes = []
    promptPartes.append("Eres un ingeniero de software senior experto en refactorización de código PHP/JS (WordPress). Tu tarea es realizar un análisis DETALLADO del código fuente completo proporcionado y proponer UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA.")
    promptPartes.append("Prioriza acciones claras y de bajo riesgo: eliminar código muerto o comentado, simplificar lógica compleja, añadir validaciones de entrada básicas, mover funciones/clases a archivos más apropiados para mejorar la cohesión y reducir la duplicación, mejorar la legibilidad (nombres descriptivos en español `camelCase`, comentarios útiles donde sea necesario).")
    promptPartes.append("Analiza el historial reciente para evitar repetir errores, acciones ineficaces o entrar en bucles de refactorización.")

    promptPartes.append("\n--- PROCESO DE RAZONAMIENTO (¡OBLIGATORIO Y DETALLADO!) ---")
    promptPartes.append("1.  **Observación:** Describe brevemente qué patrón, problema o mejora identificaste en el código (ej: 'Función `X` en archivo `A` parece ser utilitaria y no específica de `A`', 'Bloque de código comentado desde hace mucho tiempo en `B`', 'Lógica `if/else` anidada compleja en función `Y` de archivo `C`').")
    promptPartes.append("2.  **Justificación:** Explica POR QUÉ la acción propuesta es beneficiosa (ej: 'Mover `X` a `helpers.php` aumentará la reutilización y cohesión', 'Eliminar código comentado mejora la legibilidad', 'Simplificar `Y` reducirá la complejidad ciclomática y facilitará el mantenimiento').")
    promptPartes.append("3.  **Acción Específica:** Define CLARAMENTE la acción a tomar. Si es mover, indica el nombre EXACTO de la función/clase y los archivos origen/destino. Si es modificar, sé preciso sobre qué cambiar (ej: 'Eliminar las líneas XX a YY en `archivo.php` que contienen el `if` comentado', 'Reemplazar el bucle `for` en la función `Z` con `array_map`'). Si es crear, especifica el propósito.")
    promptPartes.append("4.  **Impacto Esperado:** Menciona brevemente cómo esta acción mejora el código (legibilidad, mantenibilidad, rendimiento, etc.).")
    promptPartes.append("5.  **Riesgos/Consideraciones:** (Opcional, pero útil) Si hay algún riesgo mínimo o algo a tener en cuenta (ej: 'Asegurarse de actualizar llamadas a la función movida si existen fuera de los archivos analizados', 'Validar que la simplificación no altere la lógica borde').")
    promptPartes.append("6.  **(Si aplica) Código a Eliminar:** Si la acción implica mover o reemplazar código, especifica CLARAMENTE qué código debe ser ELIMINADO del archivo original. Puedes citar el bloque o describirlo sin ambigüedad.")

    promptPartes.append("\n--- REGLAS PARA TU RESPUESTA (DECISIÓN) ---")
    promptPartes.append("1.  **RAZONAMIENTO COMPLETO:** Incluye el proceso de razonamiento detallado en el campo `razonamiento`.")
    promptPartes.append("2.  **ACCIÓN CLARA**: Elige una acción: `mover_funcion`, `mover_clase`, `modificar_codigo_en_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`. Si NINGUNA acción segura/útil es posible, usa `no_accion` y explica por qué en el razonamiento.")
    promptPartes.append("3.  **DESCRIPCIÓN CONCISA**: En `descripcion`, un mensaje claro y breve para un commit (ej: 'Refactor: Mueve función `miUtilidad` de `a.php` a `lib/utils.php`').")
    promptPartes.append("4.  **PARÁMETROS PRECISOS**: En `parametros_accion`, incluye SOLO los identificadores necesarios para que OTRO proceso (Paso 2) realice el cambio. Usa rutas RELATIVAS (separador `/`).")
    promptPartes.append("    -   `mover_funcion`/`mover_clase`: `archivo_origen`, `archivo_destino`, `nombre_funcion`/`nombre_clase`. ¡Indica si el archivo destino debe crearse!")
    promptPartes.append("    -   `modificar_codigo_en_archivo`: `archivo`, `descripcion_detallada_cambio` (ej: 'Eliminar bloque `if (false)` en líneas 80-85', 'Simplificar bucle `for` en funcion `procesarItems` usando `array_walk`', 'Añadir comentario `@param` a función `calcularTotal`'). NO incluyas el código nuevo aquí, solo la descripción de QUÉ hacer.")
    promptPartes.append("    -   `crear_archivo`: `archivo` (ruta completa relativa), `proposito_del_archivo` (ej: 'Clase para gestionar conexiones a API externa X').")
    promptPartes.append("    -   `eliminar_archivo`: `archivo`.")
    promptPartes.append("    -   `crear_directorio`: `directorio`.")
    promptPartes.append("5.  **ARCHIVOS RELEVANTES CRUCIALES**: En `archivos_relevantes`, lista TODAS las rutas relativas (separador `/`) de los archivos que el Paso 2 necesitará LEER para ejecutar la acción (origen, destino potencial si existe, archivos que podrían necesitar `require/include` actualizados si mueves código, etc.). Es VITAL para el contexto reducido del Paso 2.")
    promptPartes.append("6.  **FORMATO JSON ESTRICTO**: Responde ÚNICAMENTE con el JSON, sin explicaciones fuera del JSON.")

    promptPartes.append("""
```json
{
  "tipo_analisis": "refactor_decision",
  "razonamiento": "1. Observación: ...\\n2. Justificación: ...\\n3. Acción Específica: ...\\n4. Impacto Esperado: ...\\n5. Riesgos: ...\\n6. Código a Eliminar (si aplica): ...",
  "accion_propuesta": "TIPO_ACCION", // mover_funcion, modificar_codigo_en_archivo, etc.
  "descripcion": "Mensaje de commit conciso y claro.",
  "parametros_accion": {
    // --- Ejemplo para mover_funcion ---
    // "archivo_origen": "modulo_a/componente.php",
    // "archivo_destino": "lib/utilidades/funciones_globales.php", // Especificar si debe crearse
    // "nombre_funcion": "calcularImpuestoDetallado",
    // --- Ejemplo para modificar_codigo_en_archivo ---
    // "archivo": "procesos/batch_nocturno.php",
    // "descripcion_detallada_cambio": "Refactorizar la función `generarReporte` para usar try-catch alrededor de la conexión DB y eliminar el comentario TODO obsoleto en línea 45.",
    // --- Ejemplo para crear_archivo ---
    // "archivo": "api/v1/endpoints/usuarios.php",
    // "proposito_del_archivo": "Contendrá los endpoints REST para el CRUD de usuarios."
    // ... otros ejemplos según acción
  },
  "archivos_relevantes": [
    "modulo_a/componente.php", // Ejemplo: Origen de la función
    "lib/utilidades/funciones_globales.php", // Ejemplo: Destino (incluso si no existe aún)
    "index.php" // Ejemplo: Archivo que podría incluir/requerir el archivo modificado
    // Lista COMPLETA de archivos cuyo contenido necesita el Paso 2
  ]
}
```""")

    if historialCambiosTexto:
        promptPartes.append("\n--- HISTORIAL DE CAMBIOS RECIENTES (PARA TU CONTEXTO) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")
        promptPartes.append("¡IMPORTANTE: Analiza el historial para no repetir errores o acciones inútiles!")

    promptPartes.append("\n--- CÓDIGO FUENTE COMPLETO A ANALIZAR ---")
    promptPartes.append(contextoCodigoCompleto)
    promptPartes.append("--- FIN CÓDIGO ---")
    promptPartes.append("\nAhora, proporciona tu DECISIÓN en el formato JSON estricto especificado.")


    promptCompleto = "\n".join(promptPartes)
    log.info(f"{logPrefix} Enviando solicitud de DECISIÓN detallada a Gemini...")
    # Log corto para no saturar
    log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:200]}...")
    log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-200:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(temperature=0.3), # Un poco más determinista
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
        # Validar campos clave extra (razonamiento ahora es crucial)
        if sugerenciaJson and not all(k in sugerenciaJson for k in ["razonamiento", "accion_propuesta", "descripcion", "parametros_accion", "archivos_relevantes"]):
             log.error(f"{logPrefix} Respuesta JSON incompleta, faltan campos clave obligatorios. JSON: {sugerenciaJson}")
             return None

        return sugerenciaJson

    except Exception as e:
        _manejarExcepcionGemini(e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None

# --- REVISADO: Función para el Paso 2: Ejecutar Acción ---
def ejecutarAccionConGemini(decisionParseada, contextoCodigoReducido):
    """
    PASO 2: Recibe la DECISIÓN DETALLADA del Paso 1 y el CONTEXTO REDUCIDO.
    SIGUE ESTRICTAMENTE las instrucciones de la decisión para generar el
    CONTENIDO FINAL de los archivos afectados.
    Retorna un JSON con {rutaRelativa: nuevoContenidoCompleto}.
    """
    logPrefix = "ejecutarAccionConGemini (Paso 2):"
    if not configurarGemini(): return None
    # contextoCodigoReducido PUEDE estar vacío si la acción es crear_directorio, eliminar_archivo, o crear archivo nuevo.
    if not decisionParseada:
        log.error(f"{logPrefix} No se proporcionó la decisión detallada del Paso 1.")
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
    descripcion = decisionParseada.get("descripcion") # Para contexto, aunque no se use directamente
    params = decisionParseada.get("parametros_accion", {})
    razonamiento_paso1 = decisionParseada.get("razonamiento", "No proporcionado.") # Para contexto interno
    archivos_relevantes_paso1 = decisionParseada.get("archivos_relevantes", []) # Para referencia

    # --- Prompt REVISADO para Paso 2 (Enfoque en EJECUCIÓN PRECISA) ---
    promptPartes = []
    promptPartes.append("Eres un asistente de ejecución de refactorización. Se ha tomado una decisión en un paso anterior basada en el análisis completo del código. TU ÚNICA TAREA AHORA es ejecutar PRECISAMENTE la acción descrita a continuación, utilizando el contenido de los archivos relevantes proporcionados.")
    promptPartes.append("\n--- DECISIÓN TOMADA (Paso 1) - DEBES SEGUIRLA ESTRICTAMENTE ---")
    promptPartes.append(f"**Acción:** `{accion}`")
    promptPartes.append(f"**Descripción General:** {descripcion}")
    promptPartes.append(f"**Parámetros Específicos:** {json.dumps(params)}")
    promptPartes.append(f"**Razonamiento (Contexto):** {razonamiento_paso1}") # Incluir razonamiento ayuda a Gemini a entender el 'por qué'

    promptPartes.append("\n--- TUS INSTRUCCIONES DETALLADAS DE EJECUCIÓN ---")
    promptPartes.append("1.  **RECIBE**: Se te da el contenido ACTUAL de los archivos listados como `archivos_relevantes` en el Paso 1.")
    promptPartes.append("2.  **EJECUTA**: Realiza la acción `{accion}` usando los `parametros_accion` proporcionados.")
    promptPartes.append("    -   **Si es `mover_funcion` o `mover_clase`**: Localiza la función/clase `nombre_funcion`/`nombre_clase` en `archivo_origen`. CÓPIALA EXACTAMENTE a `archivo_destino`. ASEGÚRATE DE ELIMINARLA COMPLETAMENTE de `archivo_origen`. Si `archivo_destino` no existe en el contexto, créalo con el contenido necesario (incluyendo `<?` si es PHP). Mantén la indentación y formato. Añade `// Movido automáticamente por IA desde {archivo_origen}` en el destino.")
    promptPartes.append("    -   **Si es `modificar_codigo_en_archivo`**: Aplica el cambio descrito en `descripcion_detallada_cambio` al archivo `archivo`. Sé preciso. Si dice 'eliminar líneas X-Y', elimínalas. Si dice 'simplificar bucle', hazlo. NO introduzcas otros cambios. Añade `// Modificado automáticamente por IA` cerca del cambio.")
    promptPartes.append("    -   **Si es `crear_archivo`**: Genera el contenido inicial para `archivo` basado en `proposito_del_archivo`. Asegúrate de que sea un archivo válido (ej. `<?` para PHP).")
    promptPartes.append("    -   **Si es `eliminar_archivo` o `crear_directorio`**: No necesitas generar contenido. El sistema principal se encargará. Responde con el JSON de resultado vacío como se indica abajo.")
    promptPartes.append("3.  **DEVUELVE**: Genera el CONTENIDO COMPLETO Y FINAL para CADA archivo que haya sido modificado o creado como resultado DIRECTO de la acción. ¡NO incluyas archivos que no cambiaste!")
    promptPartes.append("4.  **PRESERVA**: Mantén el resto del código en los archivos modificados INTACTO.")
    promptPartes.append("5.  **FORMATO PHP**: RECUERDA usar `<?` y `<? echo` (NO `<?php`) según las convenciones vistas en el código proporcionado. Evita errores comunes como `<?` duplicados o mal cerrados. Revisa tu salida cuidadosamente.")

    promptPartes.append("\n--- REGLAS ESTRICTAS PARA TU RESPUESTA (EJECUCIÓN) ---")
    promptPartes.append("1.  **CONTENIDO COMPLETO FINAL**: Para cada archivo afectado, proporciona su contenido ÍNTEGRO y final.")
    promptPartes.append("2.  **SOLO ARCHIVOS AFECTADOS**: Incluye únicamente los archivos cuyo contenido ha cambiado o que has creado.")
    promptPartes.append("3.  **FORMATO JSON ESTRICTO**: Responde ÚNICAMENTE con un JSON que mapea la ruta RELATIVA (separador `/`) del archivo a su nuevo contenido COMPLETO.")
    promptPartes.append("""
```json
{
  "tipo_resultado": "ejecucion_cambio",
  "archivos_modificados": {
    "ruta/relativa/archivo_modificado1.php": "<?php\\n/* NUEVO CONTENIDO COMPLETO DEL ARCHIVO 1 */\\n// Modificado automáticamente por IA\\n?>",
    "ruta/relativa/archivo_creado.php": "<?php\\n/* CONTENIDO INICIAL DEL NUEVO ARCHIVO */\\n?>"
    // ... incluir una entrada por CADA archivo que cambie o se cree
  }
}
```""")
    # Caso especial: acciones sin modificación de contenido
    if accion in ["eliminar_archivo", "crear_directorio"]:
         promptPartes.append(f"\n**NOTA IMPORTANTE:** Dado que la acción es `{accion}`, NO debes generar contenido de archivo. Responde con el JSON vacío para `archivos_modificados`:")
         promptPartes.append("""
```json
{
  "tipo_resultado": "ejecucion_cambio",
  "archivos_modificados": {}
}
```""")

    if contextoCodigoReducido:
        promptPartes.append("\n--- CONTENIDO ACTUAL DE ARCHIVOS RELEVANTES (PARA TU EJECUCIÓN) ---")
        promptPartes.append(contextoCodigoReducido)
        promptPartes.append("--- FIN CONTENIDO ---")
    elif accion not in ["eliminar_archivo", "crear_directorio", "crear_archivo"]:
        # Advertencia si falta contexto y la acción debería tenerlo
         log.warning(f"{logPrefix} La acción '{accion}' normalmente requiere contexto, pero no se proporcionó contexto reducido. Esto podría indicar un error en el Paso 1 o en la lógica de lectura.")
         promptPartes.append("\n**ADVERTENCIA:** No se proporcionó contenido de archivo, pero la acción lo requeriría. Intenta proceder basado en los parámetros, pero el resultado es incierto.")
    else:
         promptPartes.append("\n(No se requiere contenido de archivo existente para esta acción específica)")


    promptCompleto = "\n".join(promptPartes)
    log.info(f"{logPrefix} Enviando solicitud de EJECUCIÓN precisa a Gemini...")
    log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:200]}...")
    log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-200:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            # Temperatura baja para ejecución precisa
            generation_config=genai.types.GenerationConfig(temperature=0.1),
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
        # Validación de coherencia (más laxa, Gemini puede decidir no modificar un archivo relevante si no es necesario)
        if resultadoJson and isinstance(resultadoJson.get("archivos_modificados"), dict):
             claves_recibidas = set(resultadoJson["archivos_modificados"].keys())
             claves_relevantes_esperadas = set(archivos_relevantes_paso1) # Archivos que le dimos
             # Es normal que las claves recibidas sean un subconjunto de las relevantes
             archivos_inesperados = claves_recibidas - claves_relevantes_esperadas
             if archivos_inesperados:
                  # Permitir crear archivos nuevos definidos en params
                  archivo_a_crear = params.get("archivo") if accion == "crear_archivo" else None
                  archivo_destino_nuevo = params.get("archivo_destino") if accion in ["mover_funcion", "mover_clase"] and params.get("archivo_destino") not in contextoCodigoReducido else None # Aproximación

                  es_inesperado_real = False
                  for inesperado in archivos_inesperados:
                      if inesperado == archivo_a_crear or inesperado == archivo_destino_nuevo:
                          continue # Es esperado que cree este archivo
                      es_inesperado_real = True
                      break

                  if es_inesperado_real:
                      log.warning(f"{logPrefix} Gemini intentó modificar/crear archivos NO ESPERADOS ({archivos_inesperados}) según los relevantes ({claves_relevantes_esperadas}) y la acción '{accion}'. Se procederá, pero podría ser un error.")

        return resultadoJson

    except Exception as e:
        _manejarExcepcionGemini(e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None


# --- Helpers Internos para llamadas a Gemini (SIN CAMBIOS) ---

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
    # Ser más robusto con la limpieza de ```
    if textoLimpio.startswith("```"):
        textoLimpio = textoLimpio.split('\n', 1)[1] if '\n' in textoLimpio else ''
        if textoLimpio.endswith("```"):
            textoLimpio = textoLimpio.rsplit('\n', 1)[0] if '\n' in textoLimpio else ''
    textoLimpio = textoLimpio.strip()


    if not textoLimpio.startswith("{") or not textoLimpio.endswith("}"):
        # Intentar encontrar JSON dentro del texto si no empieza/termina bien
        json_start = textoLimpio.find('{')
        json_end = textoLimpio.rfind('}')
        if json_start != -1 and json_end != -1 and json_start < json_end:
            textoLimpio = textoLimpio[json_start:json_end+1]
            log.warning(f"{logPrefix} Se extrajo JSON potencialmente incrustado en texto adicional.")
        else:
            log.error(f"{logPrefix} Respuesta de Gemini no parece contener JSON válido. Respuesta (limpia): {textoLimpio[:500]}...")
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
        log.error(f"{logPrefix} Error argumento inválido (InvalidArgument): {e}. ¿Contexto muy grande o prompt mal formado?")
        # Podríamos intentar loguear el prompt si el tamaño no es excesivo
    elif isinstance(e, (getattr(genai.types, 'BlockedPromptException', Exception), # Usar Exception como fallback
                         getattr(genai.types, 'StopCandidateException', Exception))):
        log.error(f"{logPrefix} Prompt bloqueado o generación detenida por Gemini: {e}")
        feedback = getattr(respuesta, 'prompt_feedback', None)
        block_reason = getattr(feedback, 'block_reason', 'Desconocido') if feedback else 'Desconocido'
        safety_ratings = getattr(feedback, 'safety_ratings', 'No disponibles') if feedback else 'No disponibles'
        finish_reason = 'Desconocida'
        if respuesta and respuesta.candidates:
             # Acceder de forma segura a candidates[0]
             candidate = respuesta.candidates[0] if respuesta.candidates else None
             finish_reason = getattr(candidate, 'finish_reason', 'Desconocida') if candidate else 'Desconocida'
             safety_ratings_cand = getattr(candidate, 'safety_ratings', None) if candidate else None
             if safety_ratings_cand: safety_ratings = safety_ratings_cand
        log.error(f"{logPrefix} Razón Bloqueo: {block_reason}, Razón Fin: {finish_reason}, Safety: {safety_ratings}")
    else:
        log.error(f"{logPrefix} Error inesperado en llamada API Gemini: {type(e).__name__} - {e}", exc_info=True)
        if respuesta:
            feedback = getattr(respuesta, 'prompt_feedback', None)
            if feedback: log.error(f"{logPrefix} Prompt Feedback: {feedback}")