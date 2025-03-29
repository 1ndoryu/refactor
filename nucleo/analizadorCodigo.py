# nucleo/analizadorCodigo.py
import os
import logging
import json
import google.generativeai as genai
import google.api_core.exceptions
from config import settings

log = logging.getLogger(__name__)

geminiConfigurado = False

def configurarGemini():
    global geminiConfigurado
    if geminiConfigurado:
        return True

    prefijoLog = "configurarGemini:"
    claveApi = settings.claveApiGemini
    if not claveApi:
        log.critical(f"{prefijoLog} Clave API de Gemini (GEMINI_API_KEY) no configurada en .env")
        return False
    try:
        genai.configure(api_key=claveApi)
        log.info(f"{prefijoLog} Cliente de Gemini configurado exitosamente.")
        geminiConfigurado = True
        return True
    except Exception as e:
        log.critical(f"{prefijoLog} Error fatal configurando cliente de Gemini: {e}")
        return False

def listarArchivosProyecto(rutaProyecto, extensionesPermitidas=None, directoriosIgnorados=None):
    prefijoLog = "listarArchivosProyecto:"
    archivosProyecto = []

    # Usar valores de settings si no se proporcionan argumentos
    if extensionesPermitidas is None:
        extensionesPermitidas = getattr(settings, 'extensionesPermitidas', ['.php']) # Default a .php si no está en settings
    # Asegurar que sean minúsculas para comparación
    extensionesPermitidas = [ext.lower() for ext in extensionesPermitidas]
    log.debug(f"{prefijoLog} Usando extensiones permitidas: {extensionesPermitidas}")

    if directoriosIgnorados is None:
        directoriosIgnorados = getattr(settings, 'directoriosIgnorados', ['.git', 'vendor', 'node_modules']) # Defaults básicos
    log.debug(f"{prefijoLog} Usando directorios ignorados: {directoriosIgnorados}")

    try:
        log.info(f"{prefijoLog} Listando archivos en: {rutaProyecto}")
        numArchivosTotal = 0
        numDirectoriosTotal = 0
        for raiz, dirs, archivos in os.walk(rutaProyecto, topdown=True):
            numDirectoriosTotal += len(dirs)
            # Filtrar directorios ignorados EN EL LUGAR para evitar recorrerlos
            dirs[:] = [d for d in dirs if d not in directoriosIgnorados]

            for nombreArchivo in archivos:
                numArchivosTotal += 1
                _, ext = os.path.splitext(nombreArchivo)
                if ext.lower() in extensionesPermitidas:
                    rutaCompleta = os.path.join(raiz, nombreArchivo)
                    # Convertir a ruta relativa para consistencia
                    rutaRelativa = os.path.relpath(rutaCompleta, rutaProyecto)
                    archivosProyecto.append(rutaRelativa) # Guardar rutas relativas

        log.info(f"{prefijoLog} Escaneo completo. Directorios: {numDirectoriosTotal}, Archivos: {numArchivosTotal}. Archivos relevantes encontrados: {len(archivosProyecto)}")
        if not archivosProyecto:
            log.warning(f"{prefijoLog} No se encontraron archivos con extensiones {extensionesPermitidas} en {rutaProyecto} (ignorando {directoriosIgnorados}).")
        return archivosProyecto # Devuelve lista de rutas relativas
    except Exception as e:
        log.error(f"{prefijoLog} Error crítico listando archivos en {rutaProyecto}: {e}")
        return None

def leerArchivos(listaArchivosRelativos, rutaBase):
    prefijoLog = "leerArchivos:"
    contenidoConcatenado = ""
    archivosLeidos = 0
    archivosFallidos = 0
    bytesTotales = 0

    log.info(f"{prefijoLog} Leyendo contenido de {len(listaArchivosRelativos)} archivos...")

    for rutaRelativa in listaArchivosRelativos:
        rutaAbsoluta = os.path.join(rutaBase, rutaRelativa)
        try:
            # Usar ruta relativa en los marcadores
            with open(rutaAbsoluta, 'r', encoding='utf-8', errors='ignore') as f:
                contenido = f.read()
                bytesArchivo = len(contenido.encode('utf-8'))
                # Usar solo nombres de archivo en marcadores para reducir tokens? O rutas relativas completas? Usemos relativas por claridad.
                contenidoConcatenado += f"--- INICIO ARCHIVO: {rutaRelativa} ---\n"
                contenidoConcatenado += contenido
                contenidoConcatenado += f"\n--- FIN ARCHIVO: {rutaRelativa} ---\n\n"
                archivosLeidos += 1
                bytesTotales += bytesArchivo
        except FileNotFoundError:
            log.warning(f"{prefijoLog} Archivo no encontrado (quizás eliminado recientemente?): {rutaAbsoluta}")
            archivosFallidos += 1
        except Exception as e:
            log.error(f"{prefijoLog} Error leyendo archivo {rutaAbsoluta}: {e}")
            archivosFallidos += 1

    tasaExito = (archivosLeidos / len(listaArchivosRelativos)) * 100 if listaArchivosRelativos else 0
    log.info(f"{prefijoLog} Lectura completada. Leídos: {archivosLeidos}/{len(listaArchivosRelativos)} ({tasaExito:.1f}%), Fallidos: {archivosFallidos}. Tamaño total contexto: {bytesTotales / 1024:.2f} KB")

    if bytesTotales == 0 and archivosLeidos > 0:
        log.warning(f"{prefijoLog} Se leyeron {archivosLeidos} archivos pero el tamaño total es 0 bytes. ¿Archivos vacíos?")
    elif archivosLeidos == 0 and len(listaArchivosRelativos) > 0:
        log.error(f"{prefijoLog} No se pudo leer ningún archivo de la lista proporcionada.")
        return None # Devolver None si no se pudo leer nada

    return contenidoConcatenado

def analizarConGemini(contextoCodigo, historialCambiosTexto=None):
    prefijoLog = "analizarConGemini:"

    if not configurarGemini():
        log.error(f"{prefijoLog} Cliente Gemini no configurado. Abortando análisis.")
        return None

    if not contextoCodigo:
        log.error(f"{prefijoLog} No se proporcionó contexto de código para analizar.")
        return None

    nombreModelo = settings.modeloGemini
    try:
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{prefijoLog} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(f"{prefijoLog} Error al inicializar el modelo Gemini '{nombreModelo}': {e}")
        return None

    # --- Construcción del Prompt ---
    promptPartes = []
    promptPartes.append("Eres un asistente experto en refactorización de código PHP y JavaScript, enfocado en mejorar calidad, legibilidad, mantenibilidad y seguridad en proyectos WordPress.")
    promptPartes.append("Analiza el código fuente y propone UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA.")
    promptPartes.append("Prioriza: eliminar código muerto/comentado, simplificar lógica, añadir validaciones básicas (sanitizar/escapar en WordPress), extraer funciones/métodos PEQUEÑOS y CLAROS, o mover código a archivos más apropiados si la estructura lo justifica claramente.")
    promptPartes.append("Sé MUY CAUTELOSO al renombrar variables/funciones existentes; solo hazlo si estás seguro de que no romperá dependencias (preferiblemente evita renombres complejos).")
    promptPartes.append("NO propongas cambios masivos, reescrituras completas, ni añadir librerías externas.")
    promptPartes.append("Objetivo: mejoras incrementales y seguras.")

    if historialCambiosTexto:
        promptPartes.append("\n--- HISTORIAL DE CAMBIOS RECIENTES (aplicados por ti) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")
        promptPartes.append("Considera el historial para evitar repeticiones o revertir cambios recientes.")

    promptPartes.append("\n--- CÓDIGO FUENTE A ANALIZAR (con rutas relativas) ---")
    tamanoContextoKB = len(contextoCodigo.encode('utf-8')) / 1024
    log.info(f"{prefijoLog} Tamaño del contexto a enviar a Gemini: {tamanoContextoKB:.2f} KB")
    if tamanoContextoKB > 3000: # Umbral de advertencia
        log.warning(f"{prefijoLog} Tamaño del contexto ({tamanoContextoKB:.2f} KB) es muy grande, puede causar errores/timeouts.")
    promptPartes.append(contextoCodigo)
    promptPartes.append("--- FIN CÓDIGO ---")

    promptPartes.append("\n--- VALIDACIÓN ANTES DE RESPONDER ---")
    promptPartes.append("Verifica rigurosamente ANTES de generar el JSON:")
    promptPartes.append("1. RUTAS: ¿Son todas las rutas en 'detalles' RELATIVAS a la raíz y VÁLIDAS según la estructura de archivos proporcionada?")
    promptPartes.append("2. EXISTENCIA (Modificar/Eliminar/Mover Origen): ¿EXISTE el archivo/directorio especificado en el contexto?")
    promptPartes.append("3. EXISTENCIA (Mover Código): ¿EXISTE 'codigo_a_mover' EXACTAMENTE en 'archivo_origen'?")
    promptPartes.append("4. NO EXISTENCIA (Crear/Mover Destino): ¿NO EXISTE ya el archivo/directorio destino? (Para mover_codigo, ¿NO EXISTE 'codigo_a_mover' en 'archivo_destino'?)")
    promptPartes.append("5. MODIFICAR (buscar): ¿EXISTE el texto 'buscar' EXACTAMENTE en el archivo?")
    promptPartes.append("Si alguna validación falla o el elemento ya no está donde esperas, RESPONDE OBLIGATORIAMENTE con 'no_accion' y explica por qué en 'razonamiento'.")

    promptPartes.append("\n--- INSTRUCCIONES PARA TU RESPUESTA ---")
    promptPartes.append("1. Identifica UNA acción basada en el código y las validaciones.")
    promptPartes.append("2. Describe la acción CLARAMENTE en 'descripcion' (para commit).")
    promptPartes.append("3. Proporciona TODOS los detalles necesarios en 'detalles' para la ejecución automática.")
    promptPartes.append("4. RESPONDE ÚNICAMENTE EN FORMATO JSON VÁLIDO y COMPLETO. Estructura:")
    promptPartes.append("""
```json
{
  "accion": "TIPO_ACCION",
  "descripcion": "Descripción clara y concisa (ej: Refactor: Mueve miFuncion de utils.php a helpers/general.php).",
  "detalles": {
    // acción "modificar_archivo":
    //   "archivo": "ruta/relativa/existente.php", // REQUERIDO
    //   "buscar": "CODIGO_EXACTO_A_BUSCAR", // REQUERIDO si no usa codigo_nuevo, DEBE EXISTIR
    //   "reemplazar": "NUEVO_CODIGO", // REQUERIDO con buscar
    //   "codigo_nuevo": "CONTENIDO_COMPLETO_ARCHIVO" // USAR CON CUIDADO EXTREMO
    // acción "mover_archivo":
    //   "archivo_origen": "ruta/relativa/origen.php", // REQUERIDO, DEBE EXISTIR
    //   "archivo_destino": "nueva/ruta/relativa/destino.php" // REQUERIDO, RUTA VALIDA, NO DEBE EXISTIR
    // acción "crear_archivo":
    //   "archivo": "nueva/ruta/relativa/archivo.js", // REQUERIDO, NO DEBE EXISTIR
    //   "contenido": "CONTENIDO_INICIAL" // REQUERIDO
    // acción "eliminar_archivo":
    //   "archivo": "ruta/relativa/a/eliminar.php" // REQUERIDO, DEBE EXISTIR
    // acción "crear_directorio":
    //   "directorio": "nueva/ruta/relativa/directorio" // REQUERIDO, NO DEBE EXISTIR
    // acción "mover_codigo":
    //   "archivo_origen": "ruta/relativa/origen.php", // REQUERIDO, DEBE EXISTIR
    //   "archivo_destino": "ruta/relativa/destino.php", // REQUERIDO, DEBE EXISTIR
    //   "codigo_a_mover": "BLOQUE_DE_CODIGO_EXACTO_A_MOVER", // REQUERIDO, DEBE EXISTIR EN ORIGEN, NO EN DESTINO
    //   "codigo_a_eliminar": "BLOQUE_DE_CODIGO_EXACTO_A_ELIMINAR_DE_ORIGEN" // REQUERIDO (puede ser igual a mover)
  },
  "razonamiento": "Breve explicación del beneficio o motivo de 'no_accion' si validación falló."
}
```""")
    promptPartes.append("TIPOS DE ACCION VÁLIDOS: `modificar_archivo`, `mover_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`, `mover_codigo`, `no_accion`.")
    promptPartes.append("Para `modificar_archivo`, prefiere `buscar`/`reemplazar` para cambios pequeños.")
    promptPartes.append("Para `mover_codigo`, asegúrate que `codigo_a_mover` y `codigo_a_eliminar` sean EXACTOS, incluyendo indentación y saltos de línea, para que el reemplazo funcione. Verifica que el código no exista ya en el destino.")
    promptPartes.append("ASEGÚRATE que todas las rutas de archivo sean RELATIVAS y VÁLIDAS según el contexto.")
    promptPartes.append("5. Si no encuentras refactorización segura/inmediata O falla una validación, responde OBLIGATORIAMENTE con `no_accion` y explica en 'razonamiento'.")
    promptPartes.append("`{\"accion\": \"no_accion\", \"descripcion\": \"No se identificaron acciones inmediatas / Validación fallida.\", \"detalles\": {}, \"razonamiento\": \"[Tu explicación aquí]\"}`")
    promptPartes.append("6. Valida internamente que tu respuesta sea JSON perfecto.")

    promptCompleto = "\n".join(promptPartes)

    log.info(f"{prefijoLog} Enviando solicitud a Gemini...")
    log.debug(f"{prefijoLog} Inicio del Prompt:\n{promptCompleto[:500]}...")
    log.debug(f"{prefijoLog} ...Fin del Prompt:\n...{promptCompleto[-500:]}")

    try:
        # Configuraciones de seguridad (ajustar si es necesario)
        safety_settings = {} # Usar defaults por ahora

        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(
                # response_mime_type="application/json", # Puede ayudar si el modelo lo soporta bien
                temperature=0.3 # Más determinista para tareas de código
            ),
            safety_settings=safety_settings if safety_settings else None
        )

        log.info(f"{prefijoLog} Respuesta recibida de Gemini.")

        textoRespuesta = ""
        # Acceso robusto al texto de la respuesta
        try:
            if hasattr(respuesta, 'text'):
                textoRespuesta = respuesta.text
            elif respuesta.parts:
                 textoRespuesta = "".join(part.text for part in respuesta.parts)
            elif respuesta.candidates and respuesta.candidates[0].content and respuesta.candidates[0].content.parts:
                 textoRespuesta = "".join(part.text for part in respuesta.candidates[0].content.parts)

            if not textoRespuesta:
                 razonBloqueo = "Razón desconocida"
                 if hasattr(respuesta, 'prompt_feedback') and respuesta.prompt_feedback.block_reason:
                     razonBloqueo = respuesta.prompt_feedback.block_reason
                 elif respuesta.candidates and respuesta.candidates[0].finish_reason != "STOP":
                     razonBloqueo = f"Finalización: {respuesta.candidates[0].finish_reason}"
                 log.error(f"{prefijoLog} Respuesta de Gemini vacía o bloqueada. Razón: {razonBloqueo}")
                 # Loguear ratings de seguridad si existen
                 if hasattr(respuesta, 'prompt_feedback') and respuesta.prompt_feedback.safety_ratings:
                     log.error(f"{prefijoLog} Safety Ratings (Prompt): {respuesta.prompt_feedback.safety_ratings}")
                 if respuesta.candidates and respuesta.candidates[0].safety_ratings:
                      log.error(f"{prefijoLog} Safety Ratings (Candidate): {respuesta.candidates[0].safety_ratings}")
                 return None

        except (ValueError, AttributeError, IndexError) as e:
            log.error(f"{prefijoLog} Error accediendo al contenido de la respuesta de Gemini: {e}")
            if hasattr(respuesta, 'prompt_feedback'): log.error(f"{prefijoLog} Prompt Feedback: {respuesta.prompt_feedback}")
            return None
        except Exception as e: # Captura genérica por si acaso
            log.error(f"{prefijoLog} Error inesperado extrayendo texto de respuesta: {e}")
            return None

        # Limpiar posible formato markdown de bloque de código JSON
        textoLimpio = textoRespuesta.strip()
        if textoLimpio.startswith("```json"):
            textoLimpio = textoLimpio[7:]
        elif textoLimpio.startswith("```"):
             textoLimpio = textoLimpio[3:]
        if textoLimpio.endswith("```"):
            textoLimpio = textoLimpio[:-3]
        textoLimpio = textoLimpio.strip()

        log.debug(f"{prefijoLog} Respuesta JSON (limpia):\n{textoLimpio}")

        try:
            sugerenciaJson = json.loads(textoLimpio)
            log.info(f"{prefijoLog} Sugerencia JSON parseada. Acción: {sugerenciaJson.get('accion')}")
            # Validación básica de estructura
            if not all(k in sugerenciaJson for k in ["accion", "descripcion", "detalles"]):
                log.error(f"{prefijoLog} JSON parseado pero faltan campos obligatorios (accion, descripcion, detalles). JSON: {sugerenciaJson}")
                return None
            return sugerenciaJson
        except json.JSONDecodeError as e:
            log.error(f"{prefijoLog} Error crítico al parsear JSON de Gemini: {e}")
            log.error(f"{prefijoLog} Respuesta recibida (puede estar mal formada):\n{textoRespuesta}")
            return None
        except Exception as e:
            log.error(f"{prefijoLog} Error inesperado procesando/parseando JSON: {e}")
            return None

    # Manejo de errores específicos de la API
    except google.api_core.exceptions.ResourceExhausted as e:
        log.error(f"{prefijoLog} Error de cuota API Gemini (ResourceExhausted): {e}.")
        return None
    except google.api_core.exceptions.InvalidArgument as e:
        log.error(f"{prefijoLog} Error argumento inválido API Gemini (InvalidArgument): {e}. ¿Contexto muy grande?")
        return None
    except google.generativeai.types.BlockedPromptException as e:
         log.error(f"{prefijoLog} Prompt bloqueado por Gemini: {e}")
         if hasattr(respuesta, 'prompt_feedback'): log.error(f"{prefijoLog} Prompt Feedback: {respuesta.prompt_feedback}")
         return None
    except google.generativeai.types.StopCandidateException as e:
         log.error(f"{prefijoLog} Generación detenida inesperadamente por Gemini: {e}")
         if respuesta.candidates: log.error(f"{prefijoLog} Razón finalización: {respuesta.candidates[0].finish_reason}, Ratings: {respuesta.candidates[0].safety_ratings}")
         return None
    except Exception as e: # Captura genérica final
        log.error(f"{prefijoLog} Error durante llamada API Gemini: {type(e).__name__} - {e}", exc_info=False) # exc_info=False para no ser tan verboso aquí
        if 'respuesta' in locals() and hasattr(respuesta, 'prompt_feedback'): log.error(f"{prefijoLog} Prompt Feedback: {respuesta.prompt_feedback}")
        return None