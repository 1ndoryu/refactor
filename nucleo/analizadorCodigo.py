# nucleo/analizadorCodigo.py
import os
import logging
import json
import google.generativeai as genai
# Importar google.api_core.exceptions para manejo específico de errores API
import google.api_core.exceptions
from config import settings

log = logging.getLogger(__name__)

geminiConfigurado = False


def configurarGemini():
    global geminiConfigurado
    if geminiConfigurado:
        return True

    logPrefix = "configurarGemini:"
    apiKey = settings.GEMINIAPIKEY
    if not apiKey:
        log.critical(
            f"{logPrefix} API Key de Gemini (GEMINI_API_KEY) no configurada en .env")
        return False
    try:
        genai.configure(api_key=apiKey)
        log.info(f"{logPrefix} Cliente de Gemini configurado exitosamente.")
        geminiConfigurado = True
        return True
    except Exception as e:
        log.critical(
            f"{logPrefix} Error fatal configurando cliente de Gemini: {e}")
        return False


def listarArchivosProyecto(rutaProyecto, extensionesPermitidas=None, directoriosIgnorados=None):
    logPrefix = "listarArchivosProyecto:"
    archivosProyecto = []

    if extensionesPermitidas is None:
        extensionesPermitidas = getattr(settings, 'EXTENSIONESPERMITIDAS',
                                        ['.php', '.js', '.py','.md', '.txt'])
        extensionesPermitidas = [ext.lower() for ext in extensionesPermitidas]
        log.debug(
            f"{logPrefix} Usando extensiones permitidas: {extensionesPermitidas}")

    if directoriosIgnorados is None:
        directoriosIgnorados = getattr(settings, 'DIRECTORIOS_IGNORADOS',
                                       ['.git', '.hg', '.svn', 'node_modules', 'vendor', 'dist', 'build', '__pycache__'])
        log.debug(
            f"{logPrefix} Usando directorios ignorados: {directoriosIgnorados}")

    try:
        log.info(f"{logPrefix} Listando archivos en: {rutaProyecto}")
        numArchivos = 0
        numDirectorios = 0
        for raiz, dirs, archivos in os.walk(rutaProyecto, topdown=True):
            numDirectorios += len(dirs)
            dirs[:] = [d for d in dirs if d not in directoriosIgnorados]

            for nombreArchivo in archivos:
                numArchivos += 1
                _, ext = os.path.splitext(nombreArchivo)
                if ext.lower() in extensionesPermitidas:
                    rutaCompleta = os.path.join(raiz, nombreArchivo)
                    archivosProyecto.append(rutaCompleta)

        log.info(f"{logPrefix} Escaneo completo. Total directorios: {numDirectorios}, Total archivos: {numArchivos}. Archivos relevantes encontrados: {len(archivosProyecto)}")
        if not archivosProyecto:
            log.warning(
                f"{logPrefix} No se encontraron archivos relevantes con las extensiones permitidas en {rutaProyecto}.")
        return archivosProyecto
    except Exception as e:
        log.error(
            f"{logPrefix} Error crítico listando archivos en {rutaProyecto}: {e}")
        return None


def leerArchivos(listaArchivos, rutaBase):
    logPrefix = "leerArchivos:"
    contenidoConcatenado = ""
    archivosLeidos = 0
    archivosFallidos = 0
    bytesTotales = 0

    log.info(f"{logPrefix} Leyendo contenido de {len(listaArchivos)} archivos...")

    for rutaAbsoluta in listaArchivos:
        try:
            rutaRelativa = os.path.relpath(rutaAbsoluta, rutaBase)
            with open(rutaAbsoluta, 'r', encoding='utf-8', errors='ignore') as f:
                contenido = f.read()
                bytesArchivo = len(contenido.encode('utf-8'))
                contenidoConcatenado += f"--- INICIO ARCHIVO: {rutaRelativa} ---\n"
                contenidoConcatenado += contenido
                contenidoConcatenado += f"\n--- FIN ARCHIVO: {rutaRelativa} ---\n\n"
                archivosLeidos += 1
                bytesTotales += bytesArchivo
        except FileNotFoundError:
            log.warning(
                f"{logPrefix} Archivo no encontrado (quizás eliminado recientemente?): {rutaAbsoluta}")
            archivosFallidos += 1
        except Exception as e:
            log.error(f"{logPrefix} Error leyendo archivo {rutaAbsoluta}: {e}")
            archivosFallidos += 1

    log.info(f"{logPrefix} Lectura completada. Leídos: {archivosLeidos}, Fallidos: {archivosFallidos}. Tamaño total del contexto: {bytesTotales / 1024:.2f} KB")
    if bytesTotales == 0 and archivosLeidos > 0:
        log.warning(
            f"{logPrefix} Se leyeron {archivosLeidos} archivos pero el tamaño total es 0 bytes. ¿Archivos vacíos?")
    elif archivosLeidos == 0 and len(listaArchivos) > 0:
        log.error(
            f"{logPrefix} No se pudo leer ningún archivo de la lista proporcionada.")
        return None

    return contenidoConcatenado


def analizarConGemini(contextoCodigo, historialCambiosTexto=None):
    logPrefix = "analizarConGemini:"

    if not configurarGemini():
        log.error(
            f"{logPrefix} Cliente Gemini no configurado. Abortando análisis.")
        return None

    if not contextoCodigo:
        log.error(
            f"{logPrefix} No se proporcionó contexto de código para analizar.")
        return None

    nombreModelo = settings.MODELOGEMINI
    try:
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{logPrefix} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(
            f"{logPrefix} Error al inicializar el modelo Gemini '{nombreModelo}': {e}")
        return None

    # --- Construcción del Prompt ---
    promptPartes = []
    promptPartes.append("Eres un asistente experto en refactorización de código PHP y JavaScript, enfocado en mejorar la calidad, legibilidad, mantenibilidad y seguridad de proyectos web, especialmente temas y plugins de WordPress.")
    promptPartes.append(
        "Tu tarea es analizar el código fuente proporcionado y proponer UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA.")
    promptPartes.append("Prioriza acciones como: eliminar código muerto o comentado, renombrar variables/funciones para mayor claridad (estilo camelCase para JS, snake_case para PHP si es consistente), extraer pequeñas funciones/métodos, simplificar condicionales complejos, añadir validaciones básicas faltantes (ej. sanitizar inputs, escapar outputs en PHP/WordPress), o mover funciones a archivos más apropiados si la estructura es evidente.")
    promptPartes.append(
        "NO propongas cambios masivos de arquitectura, reescrituras completas de archivos, o adición de librerías externas.")
    promptPartes.append(
        "El objetivo es hacer mejoras incrementales y seguras.")

    if historialCambiosTexto:
        promptPartes.append("\n--- HISTORIAL DETALLADO DE CAMBIOS RECIENTES (Formato: [Num] [Timestamp] Accion: Tipo | Desc: Descripcion | Detalles: {json}) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")
        promptPartes.append("Analiza CUIDADOSAMENTE cada entrada del historial, prestando atención a 'Accion' y 'Detalles' para entender la operación exacta realizada.")
        promptPartes.append("Por ejemplo, si la última acción fue 'mover_archivo' de A a B, el siguiente paso lógico podría ser eliminar referencias a la función/elemento en A, o eliminar A si quedó vacío. NO vuelvas a proponer mover el mismo elemento.")
        promptPartes.append("Evita proponer cambios redundantes o revertir acciones recientes basándote en esta información detallada.")
    
    promptPartes.append("\n--- CÓDIGO FUENTE A ANALIZAR ---")
    tamanoContextoKB = len(contextoCodigo.encode('utf-8')) / 1024
    log.info(
        f"{logPrefix} Tamaño del contexto a enviar a Gemini: {tamanoContextoKB:.2f} KB")
    # Aumentar umbral de advertencia ligeramente, los límites pueden variar
    if tamanoContextoKB > 1500:
        log.warning(
            f"{logPrefix} El tamaño del contexto ({tamanoContextoKB:.2f} KB) es muy grande y puede exceder los límites de la API o causar timeouts/errores.")
    promptPartes.append(contextoCodigo)
    promptPartes.append("--- FIN CÓDIGO ---")

    # <<< INICIO: Nuevas instrucciones de validación >>>
    promptPartes.append("\n--- VALIDACIÓN ANTES DE RESPONDER ---")
    promptPartes.append("Antes de generar el JSON, verifica rigurosamente:")
    promptPartes.append("- Que TODAS las rutas de archivo en 'detalles' sean RELATIVAS a la raíz del proyecto y EXISTENTES dentro de la estructura de archivos proporcionada (excepto para 'crear_archivo', 'crear_directorio', o el 'archivo_destino' en 'mover_archivo').")
    promptPartes.append("- Para 'mover_archivo', asegúrate ABSOLUTAMENTE que el 'archivo_origen' especificado existe y contiene el elemento mencionado en 'descripcion'. Verifica también que la ruta 'archivo_destino' sea válida (no necesariamente existente aún).")
    promptPartes.append("- Para 'modificar_archivo' con 'buscar', asegúrate que el texto a buscar REALMENTE existe en el archivo especificado.")
    promptPartes.append("Si alguna de estas validaciones falla, o si el archivo o elemento a modificar/mover ya no parece existir o está en otro lugar, responde OBLIGATORIAMENTE con 'no_accion' y explica el motivo de la validación fallida en 'razonamiento'.")
    # <<< FIN: Nuevas instrucciones de validación >>>

    promptPartes.append("\n--- INSTRUCCIONES PARA TU RESPUESTA ---")
    promptPartes.append(
        "1. Identifica UNA sola acción de refactorización concreta y bien definida basada en el código Y las validaciones anteriores.")
    promptPartes.append(
        "2. Describe la acción CLARAMENTE en el campo 'descripcion' para usarla como mensaje de commit (ej: 'Refactor: Mueve funcion miFuncion de utils.php a helpers/general.php').")
    promptPartes.append(
        "3. Proporciona TODOS los detalles necesarios en el campo 'detalles' para aplicar el cambio AUTOMÁTICAMENTE.")
    promptPartes.append(
        "4. RESPONDE ÚNICAMENTE EN FORMATO JSON VÁLIDO y COMPLETO, sin texto introductorio ni explicaciones fuera del JSON. La estructura debe ser:")
    promptPartes.append("""
```json
{
  "accion": "TIPO_ACCION",
  "descripcion": "Descripción clara y concisa para mensaje de commit.",
  "detalles": {
    // --- Campos para accion "modificar_archivo" ---
    // "archivo": "ruta/relativa/al/archivo.php", // Obligatorio, DEBE EXISTIR
    // "buscar": "CODIGO_O_TEXTO_EXACTO_A_BUSCAR", // Obligatorio si no se usa codigo_nuevo, DEBE EXISTIR EN EL ARCHIVO
    // "reemplazar": "CODIGO_O_TEXTO_DE_REEMPLAZO", // Obligatorio si se usa buscar
    // "codigo_nuevo": "CONTENIDO_COMPLETO_DEL_ARCHIVO", // Usar con PRECAUCIÓN
    // --- Campos para accion "mover_archivo" ---
    // "archivo_origen": "ruta/relativa/origen.php", // Obligatorio, DEBE EXISTIR
    // "archivo_destino": "nueva/ruta/relativa/destino.php" // Obligatorio, la ruta debe ser válida
    // --- Campos para accion "crear_archivo" ---
    // "archivo": "nueva/ruta/relativa/archivo.js", // Obligatorio, NO DEBE EXISTIR
    // "contenido": "CONTENIDO_INICIAL_DEL_ARCHIVO" // Obligatorio
    // --- Campos para accion "eliminar_archivo" ---
    // "archivo": "ruta/relativa/a/eliminar.txt" // Obligatorio, DEBE EXISTIR
    // --- Campos para accion "crear_directorio" ---
    // "directorio": "nueva/ruta/relativa/directorio" // Obligatorio, NO DEBE EXISTIR como archivo
  },
  "razonamiento": "Explicación breve del beneficio del cambio (opcional, o motivo de 'no_accion')."
}
```""")
    promptPartes.append(
        "TIPOS DE ACCION VÁLIDOS: `modificar_archivo`, `mover_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`.")
    promptPartes.append(
        "Para `modificar_archivo`, prefiere usar `buscar` y `reemplazar` para cambios pequeños y específicos.")
    # <<< INICIO: Instrucción reforzada sobre rutas >>>
    promptPartes.append(
        "ASEGÚRATE que las rutas de archivo en 'detalles' sean RELATIVAS a la raíz del proyecto, sean EXACTAS y VÁLIDAS según la estructura de archivos proporcionada en el contexto.")
    # <<< FIN: Instrucción reforzada sobre rutas >>>
    promptPartes.append(
        "5. Si después de un análisis cuidadoso y pasar las validaciones, no encuentras ninguna refactorización pequeña, segura e inmediata que proponer, responde OBLIGATORIAMENTE con este JSON:")
    promptPartes.append("`{\"accion\": \"no_accion\", \"descripcion\": \"No se identificaron acciones de refactorización inmediatas.\", \"detalles\": {}, \"razonamiento\": \"El código actual parece razonable o las validaciones pre-respuesta fallaron.\"}`")
    promptPartes.append(
        "6. Valida internamente que tu respuesta sea un JSON perfecto antes de enviarla.")

    promptCompleto = "\n".join(promptPartes)

    log.info(f"{logPrefix} Enviando solicitud a Gemini...")
    log.debug(f"{logPrefix} Inicio del Prompt:\n{promptCompleto[:500]}...")
    log.debug(f"{logPrefix} ...Fin del Prompt:\n...{promptCompleto[-500:]}")

    try:
        safety_settings = {
            # Podrías necesitar ajustar esto si Gemini es muy restrictivo con el código
            # 'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
            # 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
            # 'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
            # 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE',
        }

        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(
                # response_mime_type="application/json", # Descomentar si el modelo lo soporta y funciona bien
                temperature=0.4 # Bajar un poco más para fomentar precisión sobre creatividad
            ),
            safety_settings=safety_settings if safety_settings else None
        )

        log.info(f"{logPrefix} Respuesta recibida de Gemini.")

        textoRespuesta = ""
        try:
            # Manejo robusto de candidatos y partes
            if respuesta.parts:
                 textoRespuesta = "".join(part.text for part in respuesta.parts)
            elif hasattr(respuesta, 'text'):
                 textoRespuesta = respuesta.text
            else:
                # Si no hay 'parts' ni 'text', intentar obtener de candidatos si existen
                if respuesta.candidates and respuesta.candidates[0].content and respuesta.candidates[0].content.parts:
                     textoRespuesta = "".join(part.text for part in respuesta.candidates[0].content.parts)

            if not textoRespuesta:
                 # Comprobar feedback si no se obtuvo texto
                 if hasattr(respuesta, 'prompt_feedback') and respuesta.prompt_feedback.block_reason:
                     log.error(f"{logPrefix} La respuesta de Gemini fue bloqueada. Razón: {respuesta.prompt_feedback.block_reason}")
                     if respuesta.prompt_feedback.safety_ratings:
                         log.error(f"{logPrefix} Safety Ratings: {respuesta.prompt_feedback.safety_ratings}")
                 # Comprobar finish_reason de candidatos
                 elif respuesta.candidates and respuesta.candidates[0].finish_reason != "STOP":
                      log.error(f"{logPrefix} Finalización inesperada de Gemini. Razón: {respuesta.candidates[0].finish_reason}")
                      if respuesta.candidates[0].safety_ratings:
                          log.error(f"{logPrefix} Safety Ratings: {respuesta.candidates[0].safety_ratings}")
                 else:
                      log.error(f"{logPrefix} La respuesta de Gemini está vacía o no se pudo extraer texto.")
                 return None

        except ValueError as e: # Captura si .text falla por algún motivo interno
            log.error(f"{logPrefix} Error interno al acceder a '.text' de la respuesta: {e}")
            if hasattr(respuesta, 'prompt_feedback'):
                log.error(f"{logPrefix} Prompt Feedback: {respuesta.prompt_feedback}")
            return None
        except Exception as e:
            log.error(f"{logPrefix} Error inesperado al acceder al contenido de la respuesta: {e}")
            return None

        textoLimpio = textoRespuesta.strip()

        if textoLimpio.startswith("```json"):
            textoLimpio = textoLimpio[7:]
        elif textoLimpio.startswith("```"):
            textoLimpio = textoLimpio[3:]
        if textoLimpio.endswith("```"):
            textoLimpio = textoLimpio[:-3]
        textoLimpio = textoLimpio.strip()

        log.debug(f"{logPrefix} Respuesta JSON (limpia):\n{textoLimpio}")

        try:
            sugerenciaJson = json.loads(textoLimpio)
            log.info(
                f"{logPrefix} Sugerencia JSON parseada correctamente. Acción: {sugerenciaJson.get('accion')}")
            if "accion" not in sugerenciaJson or "detalles" not in sugerenciaJson or "descripcion" not in sugerenciaJson:
                log.error(
                    f"{logPrefix} JSON parseado pero le faltan campos obligatorios (accion, detalles, descripcion). JSON: {sugerenciaJson}")
                # Podrías intentar extraer el razonamiento si existe para entender por qué faltan campos
                if "razonamiento" in sugerenciaJson:
                    log.error(f"{logPrefix} Razonamiento proporcionado: {sugerenciaJson.get('razonamiento')}")
                return None
            return sugerenciaJson
        except json.JSONDecodeError as e:
            log.error(
                f"{logPrefix} Error crítico al parsear JSON de Gemini: {e}")
            log.error(
                f"{logPrefix} Respuesta recibida (puede estar mal formada):\n{textoRespuesta}")
            return None
        except Exception as e:
            log.error(
                f"{logPrefix} Error inesperado procesando/parseando respuesta JSON: {e}")
            return None

    except google.api_core.exceptions.ResourceExhausted as e:
        log.error(f"{logPrefix} Error de cuota de API Gemini (ResourceExhausted): {e}. Revisa tus límites o reduce la frecuencia/tamaño de las solicitudes.")
        return None
    except google.api_core.exceptions.InvalidArgument as e:
        log.error(f"{logPrefix} Error de argumento inválido en API Gemini (InvalidArgument): {e}. Probablemente el contexto es demasiado grande o el prompt tiene problemas.")
        return None
    # Captura errores específicos de la librería google-generativeai si ocurren
    except google.generativeai.types.BlockedPromptException as e:
         log.error(f"{logPrefix} El prompt fue bloqueado por Gemini antes de generar respuesta: {e}")
         # Intenta obtener más info si está disponible en la excepción o en la 'respuesta' (aunque podría no existir)
         try:
             if respuesta and hasattr(respuesta, 'prompt_feedback'):
                 log.error(f"{logPrefix} Prompt Feedback: {respuesta.prompt_feedback}")
         except NameError: pass
         return None
    except google.generativeai.types.StopCandidateException as e:
         log.error(f"{logPrefix} La generación de Gemini fue detenida inesperadamente: {e}")
         try:
             if respuesta and respuesta.candidates:
                  log.error(f"{logPrefix} Razón de finalización: {respuesta.candidates[0].finish_reason}")
                  if respuesta.candidates[0].safety_ratings:
                     log.error(f"{logPrefix} Safety Ratings: {respuesta.candidates[0].safety_ratings}")
         except NameError: pass
         return None
    except Exception as e:
        log.error(
            f"{logPrefix} Error durante la llamada a la API de Gemini: {type(e).__name__} - {e}", exc_info=True) # Añadir exc_info para trazabilidad completa
        try:
            if respuesta and hasattr(respuesta, 'prompt_feedback'):
                log.error(
                    f"{logPrefix} Prompt Feedback: {respuesta.prompt_feedback}")
        except NameError:
            pass
        return None