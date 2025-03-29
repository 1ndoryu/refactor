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
            # Filtrar directorios ignorados ANTES de descender en ellos
            dirs[:] = [d for d in dirs if d not in directoriosIgnorados and not d.startswith('.')] # Ignorar ocultos también

            for nombreArchivo in archivos:
                if nombreArchivo.startswith('.'): # Ignorar archivos ocultos
                    continue
                numArchivos += 1
                _, ext = os.path.splitext(nombreArchivo)
                if ext.lower() in extensionesPermitidas:
                    rutaCompleta = os.path.join(raiz, nombreArchivo)
                    # Normalizar separadores por si acaso
                    archivosProyecto.append(os.path.normpath(rutaCompleta))

        log.info(f"{logPrefix} Escaneo completo. Total directorios procesados: {numDirectorios}, Total archivos encontrados: {numArchivos}. Archivos relevantes: {len(archivosProyecto)}")
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
            # Asegurarse de que la ruta relativa use '/' como separador para consistencia en el prompt
            rutaRelativa = os.path.relpath(rutaAbsoluta, rutaBase).replace(os.sep, '/')
            with open(rutaAbsoluta, 'r', encoding='utf-8', errors='ignore') as f:
                contenido = f.read()
                bytesArchivo = len(contenido.encode('utf-8'))
                # --- Separador claro para la IA ---
                contenidoConcatenado += f"########## START FILE: {rutaRelativa} ##########\n"
                contenidoConcatenado += contenido
                contenidoConcatenado += f"\n########## END FILE: {rutaRelativa} ##########\n\n"
                # --- ---
                archivosLeidos += 1
                bytesTotales += bytesArchivo
        except FileNotFoundError:
            log.warning(
                f"{logPrefix} Archivo no encontrado (quizás eliminado recientemente?): {rutaAbsoluta}")
            archivosFallidos += 1
        except Exception as e:
            log.error(f"{logPrefix} Error leyendo archivo {rutaAbsoluta}: {e}")
            archivosFallidos += 1

    tamanoKB = bytesTotales / 1024
    log.info(f"{logPrefix} Lectura completada. Leídos: {archivosLeidos}, Fallidos: {archivosFallidos}. Tamaño total del contexto: {tamanoKB:.2f} KB")
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
    promptPartes.append("Prioriza acciones como: eliminar código muerto o comentado, simplificar condicionales, añadir validaciones básicas (sanitizar inputs, escapar outputs), usar funciones existentes para reducir duplicación, o mover fragmentos de código (funciones, clases pequeñas) a archivos más apropiados si mejora la organización.") # Added detail on using existing functions

    # <<< INICIO: Reglas importantes >>>
    promptPartes.append("\n--- REGLAS IMPORTANTES ---")
    promptPartes.append("1.  **UNA ACCIÓN A LA VEZ**: Propón solo un cambio pequeño y autocontenido.")
    promptPartes.append("2.  **USA LAS ACCIONES CORRECTAS**: Tienes `mover_codigo` para fragmentos y `mover_archivo` para ficheros completos. No los confundas.")
    promptPartes.append("3.  **VALIDACIÓN PREVIA**: ANTES de proponer una acción, verifica mentalmente:")
    promptPartes.append("    -   ¿Existe realmente el archivo/código que quieres modificar/mover?")
    promptPartes.append("    -   ¿Las rutas de archivo son CORRECTAS y RELATIVAS a la raíz del proyecto?")
    promptPartes.append("    -   Para `modificar_archivo` con `buscar`/`reemplazar`: ¿El valor de `buscar` es un SUBSTRING LITERAL y EXACTO del contenido del archivo `archivo`? NO incluyas comentarios, etiquetas `<?php`, `?>`, espacios en blanco iniciales/finales u otro código circundante que NO sea parte ÍNTEGRA y CONTIGUA del bloque que quieres encontrar. ¡LA PRECISIÓN ES CRÍTICA!") # <<< MODIFIED/ADDED RULE
    promptPartes.append("    -   Para `mover_codigo`: ¿El `codigo_a_mover` es EXACTO y está presente en `archivo_origen`?")
    promptPartes.append("    -   Para `mover_codigo`: ¿El `archivo_destino` es apropiado? (Normalmente debe existir, a menos que sea parte de una refactorización mayor que implique crearlo).")
    promptPartes.append("    -   ¿El cambio propuesto podría romper referencias o dependencias? Si es así, NO lo propongas o advierte sobre ello.")
    promptPartes.append("4.  **NO RENOMBRES SIN ESTAR SEGURO**: Evita renombrar funciones o variables automáticamente. Si es necesario, propónlo como una acción `modificar_archivo` separada y justifica por qué es seguro.")
    promptPartes.append("5.  **CONSIDERA EL HISTORIAL**: Revisa el historial reciente. No repitas acciones, no reviertas cambios inmediatamente, y ten en cuenta la dirección general de la refactorización.")
    promptPartes.append("6.  **SI LA VALIDACIÓN FALLA**: Si alguna verificación previa falla (ej: el código a mover/buscar ya no existe donde esperabas), responde OBLIGATORIAMENTE con `no_accion` y explica el motivo en 'razonamiento'.")
    promptPartes.append("7.  **AGREGA COMENTARIOS INDICADO TUS CAMBIOS**: Si escribes código nuevo, agrega un comentario indicando que los cambios fueron automáticos con IA.")
    # <<< FIN: Reglas importantes >>>


    if historialCambiosTexto:
        promptPartes.append(
            "\n--- HISTORIAL DE CAMBIOS RECIENTES (Últimos aplicados por ti)  IMPORTANTE TENER EN CUENTA TUS ACCIONES ANTERIORES! ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")
        promptPartes.append(
            "CONSIDERA ESTE HISTORIAL para evitar duplicados o conflictos, se consistente con los cambios, ejemplo si moviste algo lo mas probable es que quieras verificar que las funciones movidas no este repetidas en el anterior sitio.")

    promptPartes.append("\n--- CÓDIGO FUENTE A ANALIZAR (Archivos separados por '########## START/END FILE: ...') ---")
    tamanoContextoKB = len(contextoCodigo.encode('utf-8')) / 1024
    log.info(
        f"{logPrefix} Tamaño del contexto a enviar a Gemini: {tamanoContextoKB:.2f} KB")
    if tamanoContextoKB > 1800: # Reducido ligeramente el umbral de advertencia por si acaso
        log.warning(
            f"{logPrefix} El tamaño del contexto ({tamanoContextoKB:.2f} KB) es grande y puede acercarse a límites o afectar rendimiento/calidad.")
    promptPartes.append(contextoCodigo)
    promptPartes.append("--- FIN CÓDIGO ---")


    promptPartes.append("\n--- INSTRUCCIONES PARA TU RESPUESTA ---")
    promptPartes.append(
        "1. Identifica UNA sola acción de refactorización basada en las reglas y el código.")
    promptPartes.append(
        "2. Describe la acción CLARAMENTE en 'descripcion' para el commit (ej: 'Refactor: Mueve funcion miFuncion de utils.php a helpers/general.php').")
    promptPartes.append(
        "3. Proporciona TODOS los detalles necesarios en 'detalles' para aplicar el cambio AUTOMÁTICAMENTE. Usa rutas RELATIVAS.")
    promptPartes.append(
        "4. RESPONDE ÚNICAMENTE EN FORMATO JSON VÁLIDO, sin texto fuera del JSON. Estructura:")
    # *** MANTENEMOS la estructura JSON como estaba ***
    promptPartes.append("""
```json
{
  "accion": "TIPO_ACCION",
  "descripcion": "Descripción clara y concisa para mensaje de commit.",
  "detalles": {
    // --- Campos para "modificar_archivo" ---
    // "archivo": "ruta/relativa/al/archivo.php", // Obligatorio
    // "buscar": "CODIGO_O_TEXTO_LITERAL_EXACTO_A_BUSCAR", // Obligatorio si se usa reemplazar. ¡DEBE SER LA CADENA LITERAL EXACTA DEL ARCHIVO, SIN CÓDIGO EXTERNO NI ESPACIOS EXTRAÑOS! ¡Verifica que existe EXACTAMENTE así!
    // "reemplazar": "CODIGO_O_TEXTO_DE_REEMPLAZO", // Obligatorio si se usa buscar. Usa "" para eliminar.
    // "codigo_nuevo": "CONTENIDO_COMPLETO_DEL_ARCHIVO", // ¡USAR CON EXTREMA PRECAUCIÓN! Solo si reemplazar no es viable.
    // --- Campos para "mover_archivo" (Mueve fichero ENTERO) ---
    // "archivo_origen": "ruta/relativa/origen.php", // Obligatorio, DEBE EXISTIR
    // "archivo_destino": "nueva/ruta/relativa/destino.php", // Obligatorio, la ruta padre debe ser válida
    // --- Campos para "mover_codigo" (Mueve FRAGMENTO y lo BORRA del origen) ---
    // "archivo_origen": "ruta/relativa/origen.php", // Obligatorio, DEBE EXISTIR
    // "archivo_destino": "ruta/relativa/destino.php", // Obligatorio, DEBE EXISTIR (o ser creado aparte)
    // "codigo_a_mover": "/* CODIGO EXACTO A MOVER (puede ser multilínea) */", // Obligatorio, DEBE EXISTIR en origen
    // --- Campos para "crear_archivo" ---
    // "archivo": "nueva/ruta/relativa/archivo.js", // Obligatorio, NO DEBE EXISTIR
    // "contenido": "CONTENIDO_INICIAL_DEL_ARCHIVO", // Obligatorio
    // --- Campos para "eliminar_archivo" ---
    // "archivo": "ruta/relativa/a/eliminar.txt", // Obligatorio, DEBE EXISTIR
    // --- Campos para "crear_directorio" ---
    // "directorio": "nueva/ruta/relativa/directorio" // Obligatorio, NO DEBE EXISTIR como archivo
  },
  "razonamiento": "Explicación breve del beneficio del cambio o motivo de 'no_accion'."
}
```""")
    promptPartes.append(
        "TIPOS DE ACCION VÁLIDOS: `modificar_archivo`, `mover_archivo`, `mover_codigo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`.")
    promptPartes.append(
        "Para `modificar_archivo`, prefiere `buscar`/`reemplazar` para cambios pequeños y específicos.")
    # *** NUEVA INSTRUCCIÓN REFORZADA ***
    promptPartes.append(
        "**MUY IMPORTANTE** para `modificar_archivo` con `buscar`/`reemplazar`: El valor de `buscar` DEBE ser el texto *exactamente* como aparece en el archivo. Encuentra el bloque de código más pequeño y único que necesitas modificar. NO incluyas NADA fuera de ese bloque (ni `<?php`, ni comentarios no relacionados, ni espacios en blanco iniciales/finales que no sean parte del bloque). Si dudas, es mejor ser más específico y pequeño con `buscar`. Verifica TU MISMO que la cadena `buscar` existe literalmente en el archivo antes de proponerla.")
    promptPartes.append(
        "Para `mover_codigo`, asegúrate que `codigo_a_mover` es el fragmento EXACTO y COMPLETO que debe moverse.")
    promptPartes.append(
        "ASEGÚRATE que las rutas de archivo en 'detalles' sean RELATIVAS a la raíz del proyecto, EXACTAS y VÁLIDAS según la estructura proporcionada.")
    promptPartes.append(
        "5. Si tras un análisis cuidadoso y aplicar las validaciones, no encuentras una refactorización segura y útil, o si la validación falla (especialmente si no puedes encontrar un `buscar` exacto), responde OBLIGATORIAMENTE con:") # Reforzado
    promptPartes.append("`{\"accion\": \"no_accion\", \"descripcion\": \"No se identificaron acciones de refactorización inmediatas o la validación previa falló.\", \"detalles\": {}, \"razonamiento\": \"[Explica brevemente por qué no hay acción o qué validación falló, ej: 'No se encontró el texto exacto a buscar en el archivo X']\"}`") # Ejemplo en razonamiento
    promptPartes.append(
        "6. Valida internamente que tu respuesta sea un JSON perfecto antes de enviarla.")

    promptCompleto = "\n".join(promptPartes)

    log.info(f"{logPrefix} Enviando solicitud a Gemini...")
    # Loguear solo el inicio y fin para no llenar logs con todo el código
    log.debug(f"{logPrefix} Inicio del Prompt (primeros 500 chars):\n{promptCompleto[:500]}...")
    log.debug(f"{logPrefix} ...Fin del Prompt (últimos 500 chars):\n...{promptCompleto[-500:]}")

    try:
        # Configuraciones de seguridad (ajustar si es necesario)
        safety_settings = {} # Dejar vacío para usar defaults o ajustar si hay bloqueos

        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(
                # temperature=0.3 # Más determinista si es necesario
                temperature=0.4 # Mantenemos T=0.4
            ),
            safety_settings=safety_settings if safety_settings else None
        )

        log.info(f"{logPrefix} Respuesta recibida de Gemini.")

        textoRespuesta = ""
        # Extracción robusta del texto de la respuesta (sin cambios aquí)
        try:
            if hasattr(respuesta, 'text') and respuesta.text:
                 textoRespuesta = respuesta.text
            elif respuesta.parts:
                 textoRespuesta = "".join(part.text for part in respuesta.parts)
            elif respuesta.candidates and respuesta.candidates[0].content and respuesta.candidates[0].content.parts:
                 textoRespuesta = "".join(part.text for part in respuesta.candidates[0].content.parts)

            if not textoRespuesta:
                block_reason = getattr(getattr(respuesta, 'prompt_feedback', None), 'block_reason', None)
                finish_reason = None
                safety_ratings = None
                if respuesta.candidates:
                    candidate = respuesta.candidates[0]
                    finish_reason = getattr(candidate, 'finish_reason', None)
                    safety_ratings = getattr(candidate, 'safety_ratings', None)

                log.error(f"{logPrefix} La respuesta de Gemini está vacía o no se pudo extraer texto. Block Reason: {block_reason}, Finish Reason: {finish_reason}, Safety Ratings: {safety_ratings}")
                return None

        except (ValueError, AttributeError, IndexError) as e:
            log.error(f"{logPrefix} Error extrayendo texto de la respuesta: {e}. Respuesta obj: {respuesta}")
            return None
        except Exception as e: # Captura genérica para errores inesperados aquí
            log.error(f"{logPrefix} Error inesperado extrayendo texto de la respuesta: {e}", exc_info=True)
            return None

        # Limpiar posible formato markdown (sin cambios aquí)
        textoLimpio = textoRespuesta.strip()
        if textoLimpio.startswith("```json"):
            textoLimpio = textoLimpio[7:]
            if textoLimpio.endswith("```"):
                textoLimpio = textoLimpio[:-3]
        elif textoLimpio.startswith("```"):
             textoLimpio = textoLimpio[3:]
             if textoLimpio.endswith("```"):
                textoLimpio = textoLimpio[:-3]
        textoLimpio = textoLimpio.strip()

        # Validación básica antes de parsear (sin cambios aquí)
        if not textoLimpio.startswith("{") or not textoLimpio.endswith("}"):
             log.error(f"{logPrefix} Respuesta de Gemini no parece ser un JSON válido (no empieza/termina con {{}}). Respuesta (limpia):\n{textoLimpio}\nRespuesta Original:\n{textoRespuesta}")
             return None

        log.debug(f"{logPrefix} Respuesta JSON (limpia):\n{textoLimpio}")

        try:
            sugerenciaJson = json.loads(textoLimpio)
            log.info(f"{logPrefix} Sugerencia JSON parseada correctamente. Acción: {sugerenciaJson.get('accion')}")
            if "accion" not in sugerenciaJson or "detalles" not in sugerenciaJson or "descripcion" not in sugerenciaJson:
                log.error(f"{logPrefix} JSON parseado pero le faltan campos obligatorios (accion, detalles, descripcion). JSON: {sugerenciaJson}")
                if "razonamiento" in sugerenciaJson:
                    log.error(f"{logPrefix} Razonamiento proporcionado: {sugerenciaJson.get('razonamiento')}")
                return None
            return sugerenciaJson
        except json.JSONDecodeError as e:
            log.error(f"{logPrefix} Error crítico al parsear JSON de Gemini: {e}")
            log.error(f"{logPrefix} Respuesta recibida (puede estar mal formada):\n{textoRespuesta}") # Loguear respuesta original
            log.error(f"{logPrefix} Respuesta después de limpieza (intentada):\n{textoLimpio}") # Loguear intento de limpieza
            return None
        except Exception as e: # Captura errores durante el parseo o validación post-parseo
            log.error(f"{logPrefix} Error inesperado procesando/parseando respuesta JSON: {e}", exc_info=True)
            return None

    # Manejo de errores específicos de la API (sin cambios aquí)
    except google.api_core.exceptions.ResourceExhausted as e:
        log.error(f"{logPrefix} Error de cuota de API Gemini (ResourceExhausted): {e}. Revisa límites.")
        return None
    except google.api_core.exceptions.InvalidArgument as e:
        log.error(f"{logPrefix} Error de argumento inválido (InvalidArgument): {e}. Contexto demasiado grande o prompt inválido?")
        return None
    except google.generativeai.types.BlockedPromptException as e:
         log.error(f"{logPrefix} El prompt fue bloqueado por Gemini: {e}")
         if hasattr(respuesta, 'prompt_feedback'):
              log.error(f"{logPrefix} Prompt Feedback: {respuesta.prompt_feedback}")
         else:
              log.error(f"{logPrefix} No se pudo obtener feedback detallado del bloqueo.")
         return None
    except google.generativeai.types.StopCandidateException as e:
         log.error(f"{logPrefix} Generación detenida inesperadamente por safety u otra razón: {e}")
         if respuesta and respuesta.candidates:
             candidate = respuesta.candidates[0]
             finish_reason = getattr(candidate, 'finish_reason', 'Desconocida')
             safety_ratings = getattr(candidate, 'safety_ratings', 'No disponibles')
             log.error(f"{logPrefix} Razón: {finish_reason}, Safety: {safety_ratings}")
         else:
              log.error(f"{logPrefix} No se pudo obtener información detallada del candidato detenido.")
         return None
    except Exception as e: # Captura genérica para cualquier otro error de API
        log.error(f"{logPrefix} Error durante la llamada a la API de Gemini: {type(e).__name__} - {e}", exc_info=True)
        if 'respuesta' in locals() and hasattr(respuesta, 'prompt_feedback'):
             log.error(f"{logPrefix} Prompt Feedback (si disponible): {respuesta.prompt_feedback}")
        return None