# nucleo/analizadorCodigo.py
import os
import logging
import json
import google.generativeai as genai
from config import settings  # Importar settings para acceder a configuraciones

log = logging.getLogger(__name__)

# Variable global para el cliente de Gemini para no reconfigurar cada vez
gemini_configurado = False


def configurarGemini():
    global gemini_configurado
    if gemini_configurado:
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
        gemini_configurado = True
        return True
    except Exception as e:
        log.critical(
            f"{logPrefix} Error fatal configurando cliente de Gemini: {e}")
        return False


def listarArchivosProyecto(rutaProyecto, extensionesPermitidas=None, directoriosIgnorados=None):
    # Devuelve una lista de rutas completas a archivos relevantes en el proyecto.
    # Lee todo el proyecto por defecto, respetando ignorados y extensiones.
    logPrefix = "listarArchivosProyecto:"
    archivosProyecto = []

    # Usar valores por defecto si no se proporcionan
    if extensionesPermitidas is None:
        # Leer desde settings si existe, o usar un default razonable
        extensionesPermitidas = getattr(settings, 'EXTENSIONESPERMITIDAS',
                                        ['.php', '.js', '.py','.md', '.txt'])
        # Convertir a minúsculas para comparación insensible
        extensionesPermitidas = [ext.lower() for ext in extensionesPermitidas]
        log.debug(
            f"{logPrefix} Usando extensiones permitidas: {extensionesPermitidas}")

    if directoriosIgnorados is None:
        # Leer desde settings si existe, o usar un default razonable
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
            # Modificar 'dirs' in-place para evitar recorrer directorios ignorados
            dirs[:] = [d for d in dirs if d not in directoriosIgnorados]

            for nombreArchivo in archivos:
                numArchivos += 1
                # Comprobar extensión
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
    # Lee el contenido de una lista de archivos y los devuelve como una
    # única cadena concatenada, lista para el prompt de Gemini.
    logPrefix = "leerArchivos:"
    contenidoConcatenado = ""
    archivosLeidos = 0
    archivosFallidos = 0
    bytesTotales = 0

    log.info(f"{logPrefix} Leyendo contenido de {len(listaArchivos)} archivos...")

    for rutaAbsoluta in listaArchivos:
        try:
            # Obtener ruta relativa para usarla como marcador en el prompt
            rutaRelativa = os.path.relpath(rutaAbsoluta, rutaBase)
            with open(rutaAbsoluta, 'r', encoding='utf-8', errors='ignore') as f:
                contenido = f.read()
                # Calcular tamaño en bytes
                bytesArchivo = len(contenido.encode('utf-8'))
                # Usar un formato claro para separar archivos en el prompt
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
            # Loguear error específico pero continuar con otros archivos
            log.error(f"{logPrefix} Error leyendo archivo {rutaAbsoluta}: {e}")
            archivosFallidos += 1

    # Loguear resumen
    log.info(f"{logPrefix} Lectura completada. Leídos: {archivosLeidos}, Fallidos: {archivosFallidos}. Tamaño total del contexto: {bytesTotales / 1024:.2f} KB")
    if bytesTotales == 0 and archivosLeidos > 0:
        log.warning(
            f"{logPrefix} Se leyeron {archivosLeidos} archivos pero el tamaño total es 0 bytes. ¿Archivos vacíos?")
    elif archivosLeidos == 0 and len(listaArchivos) > 0:
        log.error(
            f"{logPrefix} No se pudo leer ningún archivo de la lista proporcionada.")
        return None  # Devolver None si no se pudo leer nada

    # ¡ADVERTENCIA! Esta cadena puede ser GIGANTESCA.
    return contenidoConcatenado


def analizarConGemini(contextoCodigo, historialCambiosTexto=None):
    # Envía el contexto a Gemini y pide una sugerencia de refactorización.
    # Devuelve la respuesta de Gemini parseada como diccionario JSON.
    logPrefix = "analizarConGemini:"

    if not configurarGemini():  # Asegurarse que el cliente esté listo
        log.error(
            f"{logPrefix} Cliente Gemini no configurado. Abortando análisis.")
        return None

    if not contextoCodigo:
        log.error(
            f"{logPrefix} No se proporcionó contexto de código para analizar.")
        return None

    # Obtener el modelo desde settings
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
        promptPartes.append(
            "\n--- HISTORIAL DE CAMBIOS RECIENTES (Últimos aplicados por ti) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")
        promptPartes.append(
            "Evita proponer cambios idénticos o revertir acciones recientes del historial.")

    # ADVERTENCIA DE TAMAÑO: Esto puede fallar si contextoCodigo es muy grande
    promptPartes.append("\n--- CÓDIGO FUENTE A ANALIZAR ---")
    # Comprobar tamaño antes de añadirlo? Podría ser útil
    tamanoContextoKB = len(contextoCodigo.encode('utf-8')) / 1024
    log.info(
        f"{logPrefix} Tamaño del contexto a enviar a Gemini: {tamanoContextoKB:.2f} KB")
    if tamanoContextoKB > 900:  # Umbral de advertencia (ajustar según modelo)
        log.warning(
            f"{logPrefix} El tamaño del contexto ({tamanoContextoKB:.2f} KB) es muy grande y puede exceder los límites de la API o causar timeouts/errores.")
    promptPartes.append(contextoCodigo)
    promptPartes.append("--- FIN CÓDIGO ---")

    promptPartes.append("\n--- INSTRUCCIONES PARA TU RESPUESTA ---")
    promptPartes.append(
        "1. Identifica UNA sola acción de refactorización concreta y bien definida.")
    promptPartes.append(
        "2. Describe la acción CLARAMENTE en el campo 'descripcion' para usarla como mensaje de commit (ej: 'Refactor: Renombra variable $usr_data a $userData en functions.php').")
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
    // "archivo": "ruta/relativa/al/archivo.php", // Obligatorio
    // "buscar": "CODIGO_O_TEXTO_EXACTO_A_BUSCAR", // Obligatorio si no se usa codigo_nuevo
    // "reemplazar": "CODIGO_O_TEXTO_DE_REEMPLAZO", // Obligatorio si se usa buscar
    // "codigo_nuevo": "CONTENIDO_COMPLETO_DEL_ARCHIVO", // Usar con precaución, prefiere buscar/reemplazar para cambios pequeños
    // --- Campos para accion "mover_archivo" ---
    // "archivo_origen": "ruta/relativa/origen.php", // Obligatorio
    // "archivo_destino": "nueva/ruta/relativa/destino.php" // Obligatorio
    // --- Campos para accion "crear_archivo" ---
    // "archivo": "nueva/ruta/relativa/archivo.js", // Obligatorio
    // "contenido": "CONTENIDO_INICIAL_DEL_ARCHIVO" // Obligatorio
    // --- Campos para accion "eliminar_archivo" ---
    // "archivo": "ruta/relativa/a/eliminar.txt" // Obligatorio
    // --- Campos para accion "crear_directorio" ---
    // "directorio": "nueva/ruta/relativa/directorio" // Obligatorio
  },
  "razonamiento": "Explicación breve del beneficio del cambio (opcional)."
}
```""")
    promptPartes.append(
        "TIPOS DE ACCION VÁLIDOS: `modificar_archivo`, `mover_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`.")
    promptPartes.append(
        "Para `modificar_archivo`, prefiere usar `buscar` y `reemplazar` para cambios pequeños y específicos en lugar de `codigo_nuevo` que reemplaza todo el archivo.")
    promptPartes.append(
        "Asegúrate que las rutas de archivo sean RELATIVAS a la raíz del proyecto.")
    promptPartes.append(
        "5. Si después de un análisis cuidadoso, no encuentras ninguna refactorización pequeña, segura e inmediata que proponer, responde OBLIGATORIAMENTE con este JSON:")
    promptPartes.append("`{\"accion\": \"no_accion\", \"descripcion\": \"No se identificaron acciones de refactorización inmediatas.\", \"detalles\": {}, \"razonamiento\": \"El código actual parece razonable o los cambios necesarios son demasiado grandes.\"}`")
    promptPartes.append(
        "6. Valida internamente que tu respuesta sea un JSON perfecto antes de enviarla.")

    promptCompleto = "\n".join(promptPartes)

    # --- Llamada a Gemini ---
    log.info(f"{logPrefix} Enviando solicitud a Gemini...")
    # Loguear solo inicio y fin del prompt para no llenar logs
    log.debug(f"{logPrefix} Inicio del Prompt:\n{promptCompleto[:500]}...")
    log.debug(f"{logPrefix} ...Fin del Prompt:\n...{promptCompleto[-500:]}")

    try:
        # Configurar safety_settings para ser menos restrictivo si es necesario
        # (¡PRECAUCIÓN! Usar solo si Gemini bloquea respuestas legítimas de código)
        safety_settings = {
            # Ejemplo: Permitir contenido potencialmente dañino si es código
            # 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
        }

        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(
                # Forzar respuesta JSON si el modelo lo soporta (ej. 1.5 Pro)
                # response_mime_type="application/json", # Descomentar si usas modelo compatible
                temperature=0.5  # Un poco menos creativo, más determinista para formato JSON
            ),
            safety_settings=safety_settings if safety_settings else None
        )

        # --- Procesamiento de Respuesta ---
        log.info(f"{logPrefix} Respuesta recibida de Gemini.")

        # Acceder al texto de la respuesta
        # A veces la respuesta viene en partes, intentamos obtener el texto completo
        textoRespuesta = ""
        try:
            textoRespuesta = respuesta.text
        except ValueError:  # Puede ocurrir si la respuesta fue bloqueada por seguridad
            log.error(
                f"{logPrefix} La respuesta de Gemini fue bloqueada o no contiene texto.")
            if hasattr(respuesta, 'prompt_feedback'):
                log.error(
                    f"{logPrefix} Prompt Feedback: {respuesta.prompt_feedback}")
            # Intentar obtener información del bloqueo si está disponible
            if respuesta.candidates and respuesta.candidates[0].finish_reason != "STOP":
                log.error(
                    f"{logPrefix} Razón de finalización: {respuesta.candidates[0].finish_reason}")
                if respuesta.candidates[0].safety_ratings:
                    log.error(
                        f"{logPrefix} Safety Ratings: {respuesta.candidates[0].safety_ratings}")
            return None
        except Exception as e:
            log.error(
                f"{logPrefix} Error inesperado al acceder al texto de la respuesta: {e}")
            return None

        textoLimpio = textoRespuesta.strip()

        # Limpiar posible markdown ```json ... ```
        if textoLimpio.startswith("```json"):
            textoLimpio = textoLimpio[7:]
        elif textoLimpio.startswith("```"):  # Por si solo pone ``` al inicio
            textoLimpio = textoLimpio[3:]
        if textoLimpio.endswith("```"):
            textoLimpio = textoLimpio[:-3]
        textoLimpio = textoLimpio.strip()

        log.debug(f"{logPrefix} Respuesta JSON (limpia):\n{textoLimpio}")

        # Intentar parsear la respuesta JSON
        try:
            sugerenciaJson = json.loads(textoLimpio)
            log.info(
                f"{logPrefix} Sugerencia JSON parseada correctamente. Acción: {sugerenciaJson.get('accion')}")
            # Validación básica de estructura esperada
            if "accion" not in sugerenciaJson or "detalles" not in sugerenciaJson or "descripcion" not in sugerenciaJson:
                log.error(
                    f"{logPrefix} JSON parseado pero le faltan campos obligatorios (accion, detalles, descripcion). JSON: {sugerenciaJson}")
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
        # Suele ocurrir si el prompt es inválido o excede límites de tokens de forma inesperada
        log.error(f"{logPrefix} Error de argumento inválido en API Gemini (InvalidArgument): {e}. Probablemente el contexto es demasiado grande o el prompt tiene problemas.")
        return None
    except Exception as e:
        # Captura otros errores de la API o de red
        log.error(
            f"{logPrefix} Error durante la llamada a la API de Gemini: {type(e).__name__} - {e}")
        # Considerar inspeccionar respuesta.prompt_feedback si la respuesta se generó parcialmente
        try:
            if respuesta and hasattr(respuesta, 'prompt_feedback'):
                log.error(
                    f"{logPrefix} Prompt Feedback: {respuesta.prompt_feedback}")
        except NameError:
            pass  # 'respuesta' puede no estar definida si el error fue antes de la llamada
        return None
