import os
import logging
import json
import random # Añadido para selección aleatoria
import google.generativeai as genai
import google.api_core.exceptions
from openai import OpenAI, APIError
from config import settings
# from google.generativeai import types

log = logging.getLogger(__name__)
geminiConfigurado = False
API_TIMEOUT_SECONDS = 300 # 2 minutos

def configurarGemini():
    global geminiConfigurado
    if geminiConfigurado:
        return True
    logPrefix = "configurarGemini:"
    apiKey = settings.GEMINIAPIKEY
    if not apiKey:
        log.critical(f"{logPrefix} API Key de Google Gemini no configurada.")
        return False
    try:
        genai.configure(api_key=apiKey)
        log.info(f"{logPrefix} Cliente de Google Gemini configurado.")
        geminiConfigurado = True
        return True
    except Exception as e:
        log.critical(
            f"{logPrefix} Error configurando cliente Google Gemini: {e}")
        return False

def listarArchivosProyecto(rutaProyecto, extensionesPermitidas=None, directoriosIgnorados=None):
    logPrefix = "listarArchivosProyecto:"
    archivosProyecto = []
    if extensionesPermitidas is None:
        extensionesPermitidas = getattr(settings, 'EXTENSIONESPERMITIDAS', [
                                        '.php', '.js', '.py', '.md', '.txt'])
        extensionesPermitidas = [ext.lower() for ext in extensionesPermitidas]
    if directoriosIgnorados is None:
        directoriosIgnorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', [
                                       '.git', 'vendor', 'node_modules'])

    rutaBaseParaListar = rutaProyecto
    # Nueva lógica para seleccionar subcarpeta de 'app/' aleatoriamente
    if rutaProyecto == settings.RUTACLON: # Solo si estamos en la raíz del proyecto clonado
        rutaApp = os.path.join(settings.RUTACLON, 'app')
        log.info(f"{logPrefix} Proyecto raíz detectado. Intentando seleccionar subcarpeta aleatoria de: {rutaApp}")
        if os.path.isdir(rutaApp):
            subcarpetasApp = [d for d in os.listdir(rutaApp) if os.path.isdir(os.path.join(rutaApp, d)) and d not in directoriosIgnorados and not d.startswith('.')]
            if subcarpetasApp:
                subcarpetaElegida = random.choice(subcarpetasApp)
                rutaBaseParaListar = os.path.join(rutaApp, subcarpetaElegida)
                log.info(f"{logPrefix} Subcarpeta aleatoria seleccionada para análisis: {rutaBaseParaListar}")
            else:
                log.warning(f"{logPrefix} No se encontraron subcarpetas válidas en '{rutaApp}'. Se listarán todos los archivos de '{rutaApp}' si existe, o se procederá con la ruta original del proyecto si '{rutaApp}' no existe o está vacía.")
                if os.path.exists(rutaApp) and os.listdir(rutaApp): # Si app existe y tiene algo (aunque no sean subcarpetas validas para elegir una)
                    rutaBaseParaListar = rutaApp
                else:
                    log.warning(f"{logPrefix} La carpeta '{rutaApp}' está vacía o no existe. Se usará la ruta original del proyecto: {rutaProyecto}")
                    # rutaBaseParaListar permanece como rutaProyecto
        else:
            log.warning(f"{logPrefix} La carpeta '{rutaApp}' no existe. Se usará la ruta original del proyecto: {rutaProyecto}")
            # rutaBaseParaListar permanece como rutaProyecto
    else:
        log.info(f"{logPrefix} No se está analizando el proyecto raíz, se listarán archivos de: {rutaProyecto}")

    try:
        log.info(
            f"{logPrefix} Listando archivos en: {rutaBaseParaListar} (Ignorando: {directoriosIgnorados})")
        for raiz, dirs, archivos in os.walk(rutaBaseParaListar, topdown=True):
            # Aplicar directoriosIgnorados también a las subcarpetas encontradas durante el walk
            dirs[:] = [
                d for d in dirs if d not in directoriosIgnorados and not d.startswith('.')]

            for nombreArchivo in archivos:
                if nombreArchivo.startswith('.'):
                    continue

                _, ext = os.path.splitext(nombreArchivo)
                if not extensionesPermitidas or ext.lower() in extensionesPermitidas:
                    rutaCompleta = os.path.join(raiz, nombreArchivo)
                    archivosProyecto.append(os.path.normpath(rutaCompleta))

        if not archivosProyecto and rutaBaseParaListar != rutaProyecto:
            log.warning(f"{logPrefix} No se encontraron archivos en la subcarpeta seleccionada '{rutaBaseParaListar}'. Intentando con la ruta original del proyecto '{rutaProyecto}' como fallback.")
            # Fallback a la ruta original del proyecto si no se encontraron archivos en la subcarpeta
            # Esto es para evitar no enviar nada si la subcarpeta elegida estaba vacía de archivos permitidos
            for raiz, dirs, archivos in os.walk(rutaProyecto, topdown=True):
                dirs[:] = [d for d in dirs if d not in directoriosIgnorados and not d.startswith('.')]
                for nombreArchivo in archivos:
                    if nombreArchivo.startswith('.'): continue
                    _, ext = os.path.splitext(nombreArchivo)
                    if not extensionesPermitidas or ext.lower() in extensionesPermitidas:
                        rutaCompleta = os.path.join(raiz, nombreArchivo)
                        archivosProyecto.append(os.path.normpath(rutaCompleta))

        log.info(
            f"{logPrefix} Archivos relevantes encontrados ({len(archivosProyecto)}) desde '{rutaBaseParaListar}'.")
        return archivosProyecto
    except Exception as e:
        log.error(
            f"{logPrefix} Error listando archivos en {rutaBaseParaListar}: {e}", exc_info=True)
        return None

def leerArchivos(listaArchivos, rutaBase):
    logPrefix = "leerArchivos:"
    contenidoConcatenado = ""
    archivosLeidos = 0
    bytesTotales = 0
    archivosFallidos = []

    for rutaAbsoluta in listaArchivos:
        rutaBaseNorm = os.path.normpath(os.path.abspath(rutaBase))
        rutaAbsNorm = os.path.normpath(os.path.abspath(rutaAbsoluta))

        if not rutaAbsNorm.startswith(rutaBaseNorm + os.sep) and rutaAbsNorm != rutaBaseNorm:
            log.error(
                f"{logPrefix} Archivo '{rutaAbsoluta}' parece estar fuera de la ruta base '{rutaBase}'. Se omitirá.")
            archivosFallidos.append(rutaAbsoluta)
            continue
        if not os.path.exists(rutaAbsNorm) or not os.path.isfile(rutaAbsNorm):
            log.warning(
                f"{logPrefix} Archivo no encontrado o no es un archivo válido en '{rutaAbsNorm}'. Se omitirá.")
            archivosFallidos.append(rutaAbsoluta)
            continue

        try:
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
            log.error(
                f"{logPrefix} Error leyendo '{rutaAbsNorm}' (Relativa: '{rutaRelativa if 'rutaRelativa' in locals() else 'N/A'}'): {e}")
            archivosFallidos.append(rutaAbsoluta)

    tamanoKB = bytesTotales / 1024
    if archivosFallidos:
        log.warning(
            f"{logPrefix} No se pudieron leer {len(archivosFallidos)} archivos: {archivosFallidos[:5]}{'...' if len(archivosFallidos) > 5 else ''}")

    if archivosLeidos > 0:
        log.info(
            f"{logPrefix} Leídos {archivosLeidos} archivos. Tamaño total: {tamanoKB:.2f} KB.")
        return contenidoConcatenado
    elif not listaArchivos:
        log.info(f"{logPrefix} La lista de archivos a leer estaba vacía.")
        return ""
    else:
        log.error(
            f"{logPrefix} No se pudo leer ningún archivo de la lista proporcionada (contenía {len(listaArchivos)} rutas).")
        return None

def generarEstructuraDirectorio(ruta_base, directorios_ignorados=None, max_depth=8, incluir_archivos=True, indent_char="    "):
    logPrefix = "generarEstructuraDirectorio:"
    if not os.path.isdir(ruta_base):
        log.error(
            f"{logPrefix} La ruta base '{ruta_base}' no es un directorio válido.")
        return None

    if directorios_ignorados is None:
        directorios_ignorados = set()
    else:
        directorios_ignorados = set(directorios_ignorados)

    directorios_ignorados.add('.git')

    estructura_lines = [os.path.basename(ruta_base) + "/"]
    processed_paths = set()

    def _walk_recursive(current_path, depth, prefix=""):
        if depth > max_depth:
            if depth == max_depth + 1:
                estructura_lines.append(
                    prefix + "└── ... (Profundidad máxima alcanzada)")
            return

        real_path = os.path.realpath(current_path)
        if real_path in processed_paths:
            estructura_lines.append(
                prefix + f"└── -> ... (Enlace circular o repetido a {os.path.basename(real_path)})")
            return
        processed_paths.add(real_path)

        try:
            entries = sorted(os.listdir(current_path))
        except OSError as e:
            estructura_lines.append(
                prefix + f"└── [Error al listar: {e.strerror}]")
            return

        items = []
        for entry in entries:
            if entry.startswith('.') or entry in directorios_ignorados:
                continue

            entry_path = os.path.join(current_path, entry)
            is_dir = False
            try:
                is_dir = os.path.isdir(entry_path)
            except OSError:
                continue

            if is_dir:
                if os.path.basename(entry_path) not in directorios_ignorados:
                    items.append(
                        {'name': entry, 'is_dir': True, 'path': entry_path})
            elif incluir_archivos and os.path.isfile(entry_path):
                items.append(
                    {'name': entry, 'is_dir': False, 'path': entry_path})

        count = len(items)
        for i, item in enumerate(items):
            is_last = (i == count - 1)
            connector = "└── " if is_last else "├── "
            line_prefix = prefix + connector

            if item['is_dir']:
                estructura_lines.append(line_prefix + item['name'] + "/")
                new_prefix = prefix + \
                    (indent_char if is_last else "│" + indent_char[1:])
                _walk_recursive(item['path'], depth + 1, new_prefix)
            else:
                estructura_lines.append(line_prefix + item['name'])

    try:
        _walk_recursive(ruta_base, 0)
        log.info(
            f"{logPrefix} Estructura de directorios generada para '{ruta_base}' (hasta {max_depth} niveles).")
        return "\n".join(estructura_lines)
    except Exception as e:
        log.error(
            f"{logPrefix} Error inesperado generando estructura: {e}", exc_info=True)
        return None

def obtenerDecisionRefactor(contextoCodigoCompleto, historialCambiosTexto=None, estructura_proyecto_texto=None, api_provider='google'):
    logPrefix = f"obtenerDecisionRefactor(Paso 1/{api_provider.upper()}):"
    log.info(f"{logPrefix} Iniciando análisis para obtener decisión...")

    if not contextoCodigoCompleto and not estructura_proyecto_texto:
        log.error(
            f"{logPrefix} No se proporcionó ni contexto de código ni estructura del proyecto.")
        return None
    if not contextoCodigoCompleto:
        log.warning(
            f"{logPrefix} No se proporcionó contexto de código, se usará solo estructura e historial.")

    promptPartes = []
    promptPartes.append("Eres un asistente experto en refactorización de código PHP/JS (WordPress). Tu tarea es analizar TODO el código fuente, **la estructura del proyecto** y el historial, y proponer UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA. Es importante que seas detallado con la informacion que generas para que el segundo agente que realiza la accion sepa exactamente que hacer. La organización primero y dejeramos para el final la seguridad, el proyecto carece de arquitectura y todo esta muy desordenado, hay que ordenar primero. Y POR FAVOR MUY IMPORTANTE, NO HAGAS ARCHIVO TAN LARGOS Y GRANDE; SI NOTAS QUE HAY UNA ARCHIVO MUY EXTENSO, DIVIDELO EN PARTES PEQUEÑAS!")
    promptPartes.append("Prioriza: eliminar código muerto, simplificar lógica compleja, añadir validaciones FALTANTES y básicas de seguridad, **mejorar la organización del código (mover funciones/clases a archivos/directorios más apropiados basándote en la estructura proporcionada)**, reducir duplicación, mejorar legibilidad (nombres en español `camelCase`). EVITA cambios masivos o reestructuraciones grandes. **La estructura del proyecto es desordenada; usa la información estructural para proponer movimientos lógicos y crear directorios si es necesario para agrupar funcionalidades relacionadas (ej: `app/Helpers/`, `app/Utils/`, `app/Services/`).** No es importante ni necesario que agregues nuevos comentarios a funciones viejas para explicar lo que hacen. Puedes hacer mejoras de optimización, seguridad, simplificación sin arriesgarte a que el codigo falle.")
    promptPartes.append("Considera el historial para NO repetir errores, NO deshacer trabajo anterior y mantener la consistencia. Y EL HECHO DE QUE SE HAYA MOVIDO UNA FUNCION DE UN ARCHIVO NO SIGNIFICA QUE QUEDO VACÍO! SUELES COMETER EL ERROR DE PENSAR QUE POR QUE MUEVE FUNCIONES DE UN ARCHIVO SIGNIFICA QUE ESTA VACÍO, POR FAVOR DEJA DE COMETER ESE ERROR")
    promptPartes.append("A veces cometes el error de eliminar archivos que no estan vacíos, no se por qué pero no pidas eliminar algo si realmente no esta vacío.")
    promptPartes.append("Archivos pequeños con funciones especificas es mucho mejor que archivos grandes con muchas funciones.")
    promptPartes.append("Ultimamente me di cuenta que mueves muchas funciones a un mismo archivo, por ejemplo a postService las cosas relacionada a los post, parece algo logico pero, necesito que los archivos no sean tan grande y que las funciones esten en archivos mas especificos, para que los archivos no se vuelvan tan largo y extensos. Es importante que los archivos sean pequenos y que las funciones esten en archivos mas especificos.")
    promptPartes.append("\n--- REGLAS ESTRICTAS PARA LA ESTRUCTURA JSON DE TU RESPUESTA (DECISIÓN) ---")
    promptPartes.append("1.  **`accion_propuesta`**: Elige UNA de: `mover_funcion`, `mover_clase`, `modificar_codigo_en_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`. Si NINGUNA acción es segura/útil/necesaria, USA `no_accion`.")
    promptPartes.append("2.  **`descripcion`**: Sé MUY específico para un mensaje de commit útil (ej: 'Refactor(Seguridad): Añade isset() a $_GET['param'] en archivo.php', 'Refactor(Clean): Elimina función duplicada viejaFuncion() de utils_old.php', 'Refactor(Org): Mueve función auxiliar miHelper() de main.php a app/Helpers/uiHelper.php', 'Refactor(Org): Crea directorio app/Http/Controllers').")
    promptPartes.append("3.  **`parametros_accion`**: Objeto JSON con TODA la información necesaria para ejecutar el cambio SIN DUDAS. Usa rutas RELATIVAS desde la raíz del proyecto.")
    promptPartes.append("    -   `mover_funcion`/`mover_clase`: `archivo_origen`, `archivo_destino`, `nombre_funcion`/`nombre_clase`, `eliminar_de_origen` (boolean). ¡Asegúrate que `archivo_destino` sea una ruta válida según la estructura!")
    promptPartes.append("    -   `modificar_codigo_en_archivo`: `archivo`, `descripcion_del_cambio_interno` (MUY detallado: 'Eliminar bloque if comentado entre lineas 80-95', 'Reemplazar bucle for en linea 120 por array_map', 'Añadir `global $wpdb;` al inicio de la función `miQuery()` en linea 30', 'Borrar la declaración completa de la función `funcionObsoleta(arg1)`'). NO incluyas el código aquí.")
    promptPartes.append("    -   `crear_archivo`: `archivo` (ruta completa relativa, ej: 'app/Helpers/stringUtils.php'), `proposito_del_archivo` (breve, ej: 'Funciones auxiliares para manejo de cadenas').")
    promptPartes.append("    -   `eliminar_archivo`: `archivo` (ruta relativa). Asegúrate de que sea seguro eliminarlo (ej: no usado en otros sitios).")
    promptPartes.append("    -   `crear_directorio`: `directorio` (ruta relativa, ej: 'app/Interfaces').")
    promptPartes.append("4.  **`archivos_relevantes`**: Lista de strings [ruta1, ruta2, ...] con **TODAS** las rutas relativas de archivos que el Paso 2 NECESITARÁ LEER para *generar el código modificado*. ¡CRUCIAL y preciso! (Ej: si mueves función de A a B, incluye [A, B]). Si creas directorio, puede ser []. Si creas archivo nuevo y no necesita contexto, puede ser []. Si modificas archivo A, debe ser [A].")
    promptPartes.append("5.  **`razonamiento`**: String justificando CLARAMENTE el *por qué* de esta acción (ej: 'Mejora la organización agrupando helpers', 'Elimina código no utilizado', 'Necesario para nueva estructura MVC') o la razón específica para `no_accion`.")
    promptPartes.append("6.  **`tipo_analisis`**: Incluye siempre el campo `tipo_analisis` con el valor fijo `\"refactor_decision\"`.")
    promptPartes.append("7. Evita las tareas de legibilidad, no son importantes, no es importante agregar comentarios Añade comentario phpDoc descriptivo o cosas asi.")
    promptPartes.append("8. No uses namespace, por favor no importa que parezca una decisión optima, no usaremos namespace en este proyecto, aqui todos los archivos estan al alcance global para que sea mas facil mover cosas.")
    promptPartes.append("9. Si vas a mover algo, asegurate de indicar correctamente a donde se tiene que mover o si se tiene que crear un nuevo archivo para ello.")
    promptPartes.append("10. Si vas a eliminar algo porque un archivo esta vacío, asegurate de que realmente este vacío.")

    if estructura_proyecto_texto:
        promptPartes.append("\n--- ESTRUCTURA ACTUAL DEL PROYECTO (Visión Global) ---")
        promptPartes.append("# Nota: Esta estructura puede estar limitada en profundidad.")
        promptPartes.append(estructura_proyecto_texto)
        promptPartes.append("--- FIN ESTRUCTURA ---")
    else:
        promptPartes.append("\n(No se proporcionó la estructura del proyecto)")

    if historialCambiosTexto:
        promptPartes.append("\n--- HISTORIAL DE CAMBIOS RECIENTES (para tu contexto, EVITA REPETIR o deshacer) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")

    promptPartes.append("\n--- CÓDIGO FUENTE COMPLETO A ANALIZAR ---")
    promptPartes.append(contextoCodigoCompleto if contextoCodigoCompleto else "(No se proporcionó código fuente completo, analiza basado en estructura e historial)")
    promptPartes.append("--- FIN CÓDIGO ---")
    promptPartes.append("\n**IMPORTANTE**: Responde ÚNICAMENTE con el objeto JSON que cumple TODAS las reglas anteriores. No incluyas explicaciones adicionales fuera del JSON. Asegúrate de que el JSON sea válido.")

    promptCompleto = "\n".join(promptPartes)
    textoRespuesta = None
    respuestaJson = None

    try:
        if api_provider == 'google':
            log.info(
                f"{logPrefix} Usando Google Gemini API (Modelo: {settings.MODELO_GOOGLE_GEMINI}).")
            if not configurarGemini():
                return None
            modelo = genai.GenerativeModel(settings.MODELO_GOOGLE_GEMINI)
            respuesta = modelo.generate_content(
                promptCompleto,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.4,
                    response_mime_type="application/json",
                    max_output_tokens=8192
                ),
                safety_settings={
                    'HATE': 'BLOCK_MEDIUM_AND_ABOVE',
                    'HARASSMENT': 'BLOCK_MEDIUM_AND_ABOVE',
                    'SEXUAL': 'BLOCK_MEDIUM_AND_ABOVE',
                    'DANGEROUS': 'BLOCK_MEDIUM_AND_ABOVE'
                }
            )
            textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)

        elif api_provider == 'openrouter':
            log.info(
                f"{logPrefix} Usando OpenRouter API (Modelo: {settings.OPENROUTER_MODEL}).")
            if not settings.OPENROUTER_API_KEY:
                log.error(
                    f"{logPrefix} Falta OPENROUTER_API_KEY en la configuración.")
                return None
            client = OpenAI(
                base_url=settings.OPENROUTER_BASE_URL,
                api_key=settings.OPENROUTER_API_KEY,
            )
            mensajes = [{"role": "user", "content": promptCompleto}]
            log.debug(f"{logPrefix} Enviando solicitud a OpenRouter (timeout={API_TIMEOUT_SECONDS}s)...")
            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": settings.OPENROUTER_REFERER,
                    "X-Title": settings.OPENROUTER_TITLE,
                },
                model=settings.OPENROUTER_MODEL,
                messages=mensajes,
                temperature=0.4,
                max_tokens=65536,
                timeout=API_TIMEOUT_SECONDS
            )
            if completion.choices:
                textoRespuesta = completion.choices[0].message.content
                log.debug(f"{logPrefix} Respuesta recibida de OpenRouter (Choice 0).")
            else:
                log.error(f"{logPrefix} No se recibieron 'choices' en la respuesta de OpenRouter.")
                log.warning(f"{logPrefix} [DIAGNÓSTICO] Objeto 'completion' (como string): {str(completion)}")
                try:
                    completion_json = completion.model_dump_json(indent=2)
                    log.warning(f"{logPrefix} [DIAGNÓSTICO] Respuesta completa OpenRouter (JSON):\n{completion_json}")
                except Exception as dump_err:
                    log.error(f"{logPrefix} [DIAGNÓSTICO] ¡FALLÓ completion.model_dump_json()!: {dump_err}", exc_info=True)
                return None

        else:
            log.error(
                f"{logPrefix} Proveedor de API no soportado: {api_provider}")
            return None

        if not textoRespuesta:
            log.error(
                f"{logPrefix} No se pudo extraer texto de la respuesta de la IA.")
            return None

        log.debug(
            f"{logPrefix} Texto crudo recibido de IA:\n{textoRespuesta[:1000]}...")
        respuestaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        if respuestaJson is None:
            log.error(f"{logPrefix} El parseo/extracción final de JSON falló.")
            return None

        if respuestaJson.get("tipo_analisis") != "refactor_decision":
            log.error(
                f"{logPrefix} Respuesta JSON no es del tipo esperado 'refactor_decision'.")
            try:
                log.error(
                    f"{logPrefix} JSON Recibido:\n{json.dumps(respuestaJson, indent=2, ensure_ascii=False)}")
            except Exception:
                log.error(
                    f"{logPrefix} JSON Recibido (no se pudo formatear): {respuestaJson}")
            return None

        log.info(
            f"{logPrefix} JSON de Decisión Generado y parseado correctamente.")
        log.debug(
            f"{logPrefix} JSON:\n{json.dumps(respuestaJson, indent=2, ensure_ascii=False)}")
        return respuestaJson

    except google.api_core.exceptions.GoogleAPIError as e_gemini:
        log.error(
            f"{logPrefix} Error API Google Gemini: {e_gemini}", exc_info=True)
        _manejarExcepcionGemini(e_gemini, logPrefix,
                                respuesta if 'respuesta' in locals() else None)
        return None
    except APIError as e_openai:
        if "timeout" in str(e_openai).lower():
             log.error(f"{logPrefix} Error de TIMEOUT ({API_TIMEOUT_SECONDS}s) en API OpenRouter: {e_openai}", exc_info=True)
        else:
             log.error(f"{logPrefix} Error API OpenRouter (via OpenAI lib): {e_openai}", exc_info=True)
        return None
    except Exception as e:
        log.error(
            f"{logPrefix} Error inesperado durante llamada a API: {e}", exc_info=True)
        if api_provider == 'google' and isinstance(e, Exception):
            _manejarExcepcionGemini(
                e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None

def ejecutarAccionConGemini(decisionParseada, contextoCodigoReducido, api_provider='google'):
    logPrefix = f"ejecutarAccionConIA(Paso 2/{api_provider.upper()}):"
    log.info(f"{logPrefix} Iniciando ejecución de acción...")

    if not decisionParseada:
        log.error(f"{logPrefix} No se proporcionó la decisión del Paso 1.")
        return None

    accion = decisionParseada.get("accion_propuesta")
    descripcion = decisionParseada.get("descripcion")
    params = decisionParseada.get("parametros_accion", {})
    razonamiento_paso1 = decisionParseada.get("razonamiento")

    promptPartes = []
    promptPartes.append("Eres un asistente de refactorización que EJECUTA una decisión ya tomada por otro agente IA.")
    promptPartes.append("**FORMATO DE COMENTARIOS O CODIGO CON SALTO DE LINEAS:** Si generas comentarios multilínea que usan `//` (PHP/JS), ASEGÚRATE de que **CADA LÍNEA** del comentario comience con `//` dentro del código generado.")
    promptPartes.append("1. No uses namespace, aqui todos los archivos estan al alcance global para que sea mas facil mover cosas, si se te pide usarlos o hacerlos, fue un error, decide no hacer nada si te causa confusión una decisión y regresa el codigo igual sin cambiar nada.")
    promptPartes.append("2. Si vas a mover algo, segurate de que realmente se esta moviendo algo, asegurate de tener el contexto necesario para mover lo que se te pide a los archivos indicados, si la decisión parece erronea, mejor no hagas nada y regresa el codigo igual sin cambiar nada.")
    promptPartes.append("3. Si vas a eliminar algo porque un archivo esta vacío, asegurate de que realmente este vacío, el anterior agente puede cometer el error de pedir eliminar un archivo supuestamente vacío pero a veces no lo esta, mejor no hagas nada si la decisión parece confusa y regresa el codigo igual sin cambiar nada.")
    promptPartes.append("4. Siempre deja un comentario en el codigo indicando brevemente la acción que realizaste.")
    promptPartes.append("Se ha decidido realizar la siguiente acción basada en el análisis previo:")
    promptPartes.append("\n--- DECISIÓN DEL PASO 1 (Debes seguirla EXACTAMENTE) ---")
    promptPartes.append(f"Acción: {accion}")
    promptPartes.append(f"Descripción: {descripcion}")
    promptPartes.append(f"Parámetros Detallados: {json.dumps(params)}")
    promptPartes.append(f"Razonamiento (Contexto): {razonamiento_paso1}")
    promptPartes.append("--- FIN DECISIÓN ---")
    promptPartes.append("\nSe te proporciona el contenido ACTUAL de los archivos relevantes (si aplica).")
    promptPartes.append("**TU ÚNICA TAREA:** Realizar la acción descrita en los 'Parámetros Detallados'.")
    promptPartes.append("\n**RESPUESTA ESPERADA:** Responde ÚNICAMENTE con un objeto JSON VÁLIDO que tenga la siguiente estructura:")
    promptPartes.append("""
```json
{
  "tipo_resultado": "ejecucion_cambio",
  "archivos_modificados": {
    "ruta/relativa/al/archivo1.php": "CONTENIDO COMPLETO Y FINAL DEL ARCHIVO 1...",
    "ruta/relativa/al/archivo2.js": "CONTENIDO COMPLETO Y FINAL DEL ARCHIVO 2...",
    // ... más archivos si son modificados o creados ...
    // Si la acción es eliminar_archivo o crear_directorio, este objeto debe ser exactamente: {}
  }
}
```""")
    promptPartes.append("\n--- REGLAS DE EJECUCIÓN Y FORMATO JSON (¡MUY IMPORTANTE!) ---")
    promptPartes.append("1.  **SIGUE LA DECISIÓN AL PIE DE LA LETRA.**")
    promptPartes.append("2.  **CONTENIDO DE ARCHIVOS:** Para CADA archivo afectado (modificado o creado), incluye su ruta relativa como clave y su contenido ÍNTEGRO final como valor string en `archivos_modificados`.")
    promptPartes.append("3.  **¡ESCAPADO CRÍTICO!** Dentro de las cadenas de texto que representan el contenido de los archivos (los valores en `archivos_modificados`), **TODAS** las comillas dobles (`\"`) literales DEBEN ser escapadas como `\\\"`. Todos los backslashes (`\\`) literales DEBEN ser escapados como `\\\\`. Los saltos de línea DEBEN ser `\\n`.")
    promptPartes.append("4.  **PRESERVA CÓDIGO:** Mantén intacto el resto del código no afectado en los archivos modificados, asegurate de que todo el codigo tenga sentido.")
    promptPartes.append("5.  **MOVIMIENTOS:** Si mueves código y `eliminar_de_origen` es true, BORRA el código original del `archivo_origen`.")
    promptPartes.append("6.  **MODIFICACIONES INTERNAS:** Aplica EXACTAMENTE la `descripcion_del_cambio_interno`.")
    promptPartes.append("7.  **CREACIÓN:** Genera contenido inicial basado en `proposito_del_archivo`.")
    promptPartes.append("8.  **SIN CONTENIDO:** Si la acción es `eliminar_archivo` o `crear_directorio`, el objeto `archivos_modificados` debe ser exactamente `{}`, un objeto JSON vacío. EXCEPCIÓN: Si se pide eliminar un archivo NO VACÍO, devuelve el JSON con el contenido original del archivo (no lo borres) y añade una nota en un campo 'advertencia_ejecucion'.")
    promptPartes.append("9. **VALIDACIÓN CRÍTICA DE STRINGS JSON PARA CÓDIGO:** Asegúrate de que el contenido de los archivos (especialmente código PHP/JS) sea un string JSON VÁLIDO Y COMPLETO (escapa `\"` como `\\\"`, `\\` como `\\\\`, saltos de línea como `\\n`). Evita truncamiento. Presta MÁXIMA atención a esto.")

    if contextoCodigoReducido:
        promptPartes.append("\n--- CONTENIDO ACTUAL DE ARCHIVOS RELEVANTES ---")
        promptPartes.append(contextoCodigoReducido)
        promptPartes.append("--- FIN CONTENIDO ---")
    else:
        promptPartes.append("\n(No se proporcionó contenido de archivo para esta acción específica o no aplica)")

    promptCompleto = "\n".join(promptPartes)
    textoRespuesta = None
    respuestaJson = None

    try:
        if api_provider == 'google':
            log.info(
                f"{logPrefix} Usando Google Gemini API (Modelo: {settings.MODELO_GOOGLE_GEMINI}).")
            if not configurarGemini():
                return None
            modelo = genai.GenerativeModel(settings.MODELO_GOOGLE_GEMINI)
            respuesta = modelo.generate_content(
                promptCompleto,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.5,
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
            textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)

        elif api_provider == 'openrouter':
            log.info(
                f"{logPrefix} Usando OpenRouter API (Modelo: {settings.OPENROUTER_MODEL}).")
            if not settings.OPENROUTER_API_KEY:
                log.error(
                    f"{logPrefix} Falta OPENROUTER_API_KEY en la configuración.")
                return None
            client = OpenAI(
                base_url=settings.OPENROUTER_BASE_URL,
                api_key=settings.OPENROUTER_API_KEY,
            )
            mensajes = [{"role": "user", "content": promptCompleto}]
            log.debug(f"{logPrefix} Enviando solicitud a OpenRouter (timeout={API_TIMEOUT_SECONDS}s)...")
            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": settings.OPENROUTER_REFERER,
                    "X-Title": settings.OPENROUTER_TITLE,
                },
                model=settings.OPENROUTER_MODEL,
                messages=mensajes,
                temperature=0.4,
                max_tokens=65536,
                timeout=API_TIMEOUT_SECONDS
            )
            if completion.choices:
                textoRespuesta = completion.choices[0].message.content
                log.debug(
                    f"{logPrefix} Respuesta recibida de OpenRouter (Choice 0).")
            else:
                log.error(
                    f"{logPrefix} No se recibieron 'choices' en la respuesta de OpenRouter.")
                try:
                    completion_json_dump = completion.model_dump_json(indent=2)
                    log.warning(f"{logPrefix} [DEBUG] Respuesta COMPLETA de OpenRouter (JSON Dump) cuando choices faltaba:\n{completion_json_dump}")
                except Exception as dump_err:
                    log.error(f"{logPrefix} [DEBUG] No se pudo hacer model_dump_json. Error: {dump_err}")
                    log.warning(f"{logPrefix} [DEBUG] Respuesta COMPLETA de OpenRouter (repr) cuando choices faltaba: {repr(completion)}")
                return None

        else:
            log.error(
                f"{logPrefix} Proveedor de API no soportado: {api_provider}")
            return None

        if not textoRespuesta:
            log.error(
                f"{logPrefix} No se pudo extraer texto de la respuesta de la IA.")
            return None

        log.debug(
            f"{logPrefix} Texto crudo recibido de IA:\n{textoRespuesta[:1000]}...")
        respuestaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        if respuestaJson is None:
            log.error(f"{logPrefix} El parseo/extracción final de JSON falló.")
            return None

        if respuestaJson.get("tipo_resultado") != "ejecucion_cambio":
            log.warning(
                f"{logPrefix} Respuesta JSON no tiene 'tipo_resultado'=\"ejecucion_cambio\" esperado. Intentando continuar si 'archivos_modificados' existe.")
            if "archivos_modificados" not in respuestaJson:
                log.error(
                    f"{logPrefix} Falta clave 'archivos_modificados'. JSON inválido.")
                try:
                    log.error(
                        f"{logPrefix} JSON Recibido:\n{json.dumps(respuestaJson, indent=2, ensure_ascii=False)}")
                except Exception:
                    log.error(
                        f"{logPrefix} JSON Recibido (no se pudo formatear): {respuestaJson}")
                return None

        archivos_mod = respuestaJson.get("archivos_modificados")
        if archivos_mod is None:
            log.error(
                f"{logPrefix} La clave 'archivos_modificados' falta en la respuesta JSON.")
            try:
                log.error(
                    f"{logPrefix} JSON Recibido:\n{json.dumps(respuestaJson, indent=2, ensure_ascii=False)}")
            except Exception:
                log.error(
                    f"{logPrefix} JSON Recibido (no se pudo formatear): {respuestaJson}")
            return None
        if not isinstance(archivos_mod, dict):
            log.error(
                f"{logPrefix} 'archivos_modificados' no es un diccionario (tipo: {type(archivos_mod)}). JSON inválido.")
            try:
                log.error(
                    f"{logPrefix} JSON Recibido:\n{json.dumps(respuestaJson, indent=2, ensure_ascii=False)}")
            except Exception:
                log.error(
                    f"{logPrefix} JSON Recibido (no se pudo formatear): {respuestaJson}")
            return None

        accion_sin_contenido = accion in [
            "eliminar_archivo", "crear_directorio"]
        if accion_sin_contenido and archivos_mod != {}:
            if not respuestaJson.get("advertencia_ejecucion"):
                log.warning(
                    f"{logPrefix} Se esperaba 'archivos_modificados' vacío {{}} para la acción '{accion}', pero se recibió: {list(archivos_mod.keys())}. Se procederá con dict vacío.")
                respuestaJson["archivos_modificados"] = {}
            else:
                log.warning(
                    f"{logPrefix} Acción '{accion}' resultó en advertencia: {respuestaJson.get('advertencia_ejecucion')}. 'archivos_modificados' no está vacío, se mantendrá.")

        for k, v in archivos_mod.items():
            if not isinstance(k, str) or not isinstance(v, str):
                log.error(
                    f"{logPrefix} Entrada inválida en 'archivos_modificados'. Clave '{k}' (tipo {type(k)}) o valor (tipo {type(v)}) no son strings. JSON inválido.")
                try:
                    log.error(
                        f"{logPrefix} JSON Recibido:\n{json.dumps(respuestaJson, indent=2, ensure_ascii=False)}")
                except Exception:
                    log.error(
                        f"{logPrefix} JSON Recibido (no se pudo formatear): {respuestaJson}")
                return None

        log.info(
            f"{logPrefix} Respuesta JSON de Ejecución parseada y validada correctamente.")
        log.debug(
            f"{logPrefix} JSON Ejecución Completo:\n{json.dumps(respuestaJson, indent=2, ensure_ascii=False)}")

        return respuestaJson

    except google.api_core.exceptions.GoogleAPIError as e_gemini:
        log.error(
            f"{logPrefix} Error API Google Gemini: {e_gemini}", exc_info=True)
        _manejarExcepcionGemini(e_gemini, logPrefix,
                                respuesta if 'respuesta' in locals() else None)
        return None
    except APIError as e_openai:
        if "timeout" in str(e_openai).lower():
             log.error(f"{logPrefix} Error de TIMEOUT ({API_TIMEOUT_SECONDS}s) en API OpenRouter: {e_openai}", exc_info=True)
        else:
             log.error(f"{logPrefix} Error API OpenRouter (via OpenAI lib): {e_openai}", exc_info=True)
        return None
    except Exception as e:
        log.error(
            f"{logPrefix} Error inesperado durante llamada a API: {e}", exc_info=True)
        if api_provider == 'google' and isinstance(e, Exception):
            _manejarExcepcionGemini(
                e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None

def _extraerTextoRespuesta(respuesta, logPrefix):
    textoRespuesta = ""
    try:
        if hasattr(respuesta, 'text') and respuesta.text:
            textoRespuesta = respuesta.text
        elif hasattr(respuesta, 'parts') and respuesta.parts:
            if isinstance(respuesta.parts, (list, tuple)) and respuesta.parts:
                if hasattr(respuesta, 'text') and respuesta.text:
                    textoRespuesta = respuesta.text
                else:
                    textoRespuesta = "".join(
                        part.text for part in respuesta.parts if hasattr(part, 'text'))
        elif hasattr(respuesta, 'candidates') and respuesta.candidates:
            if isinstance(respuesta.candidates, (list, tuple)) and respuesta.candidates:
                if hasattr(respuesta, 'text') and respuesta.text:
                    textoRespuesta = respuesta.text
                else:
                    candidate = respuesta.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts') and candidate.content.parts:
                        if isinstance(candidate.content.parts, (list, tuple)) and candidate.content.parts:
                            textoRespuesta = "".join(
                                part.text for part in candidate.content.parts if hasattr(part, 'text'))

        if not textoRespuesta:
            finish_reason_str = "N/A"
            safety_ratings_str = "N/A"
            block_reason_str = "N/A"

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
                if hasattr(candidate, 'safety_ratings') and safety_ratings_str == "N/A":
                    safety_ratings_str = str(candidate.safety_ratings)

            log.error(f"{logPrefix} Respuesta de IA vacía o no se pudo extraer texto. "
                      f"FinishReason: {finish_reason_str}, BlockReason: {block_reason_str}, SafetyRatings: {safety_ratings_str} (Info puede ser específica de Gemini)")
            log.debug(f"{logPrefix} Respuesta completa (objeto): {respuesta}")
            return None

        return textoRespuesta.strip()

    except (AttributeError, IndexError, ValueError, TypeError) as e:
        log.error(
            f"{logPrefix} Error extrayendo texto de la respuesta: {e}. Respuesta obj: {respuesta}", exc_info=True)
        return None
    except Exception as e:
        log.error(
            f"{logPrefix} Error inesperado extrayendo texto: {e}", exc_info=True)
        return None

def _limpiarYParsearJson(textoRespuesta, logPrefix):
    textoLimpio = textoRespuesta.strip()

    if textoLimpio.startswith("```"):
        first_newline = textoLimpio.find('\n')
        if first_newline != -1:
            first_line = textoLimpio[:first_newline].strip()
            if first_line == "```json" or first_line == "```":
                textoLimpio = textoLimpio[first_newline + 1:]
        if textoLimpio.endswith("```"):
            textoLimpio = textoLimpio[:-3].strip()

    start_brace = textoLimpio.find('{')
    end_brace = textoLimpio.rfind('}')

    if start_brace == -1 or end_brace == -1 or start_brace >= end_brace:
        log.error(
            f"{logPrefix} Respuesta de IA no parece contener un bloque JSON válido {{...}}. Respuesta (limpia inicial): {textoLimpio[:500]}...")
        log.debug(f"{logPrefix} Respuesta Original Completa:\n{textoRespuesta}")
        return None

    json_candidate = textoLimpio[start_brace: end_brace + 1]

    try:
        log.debug(
            f"{logPrefix} Intentando parsear JSON candidato (tamaño: {len(json_candidate)})...")
        resultadoJson = json.loads(json_candidate)
        log.info(
            f"{logPrefix} JSON parseado correctamente (previo a validación de contenido).")
        return resultadoJson
    except json.JSONDecodeError as e:
        contexto_inicio = max(0, e.pos - 150)
        contexto_fin = min(len(json_candidate), e.pos + 150)
        contexto_error = json_candidate[contexto_inicio:contexto_fin]
        contexto_error_repr = repr(contexto_error)

        log.error(f"{logPrefix} Error crítico parseando JSON de IA: {e}")
        log.error(f"{logPrefix} Posición del error: {e.pos}")
        log.error(
            f"{logPrefix} Contexto alrededor del error ({contexto_inicio}-{contexto_fin}):\n{contexto_error_repr}")
        log.error(
            f"{logPrefix} JSON Candidato (inicio):\n{json_candidate[:1000]}...")
        log.error(
            f"{logPrefix} JSON Candidato (fin):...{json_candidate[-1000:]}")
        log.debug(f"{logPrefix} Respuesta Original Completa:\n{textoRespuesta}")
        return None
    except Exception as e:
        log.error(
            f"{logPrefix} Error inesperado parseando JSON: {e}", exc_info=True)
        return None

def _manejarExcepcionGemini(e, logPrefix, respuesta=None):
    if isinstance(e, google.api_core.exceptions.ResourceExhausted):
        log.error(
            f"{logPrefix} Error de cuota API Google Gemini (ResourceExhausted): {e}")
    elif isinstance(e, google.api_core.exceptions.InvalidArgument):
        log.error(f"{logPrefix} Error argumento inválido API Google Gemini (InvalidArgument): {e}. ¿Prompt mal formado, contenido bloqueado o fallo en generación JSON?", exc_info=True)
    elif isinstance(e, google.api_core.exceptions.PermissionDenied):
        log.error(
            f"{logPrefix} Error de permiso API Google Gemini (PermissionDenied): {e}. ¿API Key incorrecta o sin permisos?")
    elif isinstance(e, google.api_core.exceptions.ServiceUnavailable):
        log.error(
            f"{logPrefix} Error servicio no disponible API Google Gemini (ServiceUnavailable): {e}. Reintentar más tarde.")
    elif type(e).__name__ in ['BlockedPromptException', 'StopCandidateException', 'ResponseBlockedError']:
        log.error(
            f"{logPrefix} Prompt bloqueado o generación detenida/bloqueada por Google Gemini: {e}")
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
                try:
                    candidate = respuesta.candidates[0]
                    if hasattr(candidate, 'finish_reason'):
                        finish_reason = f"FinishReason: {candidate.finish_reason}"
                    if hasattr(candidate, 'safety_ratings'):
                        safety_ratings = str(candidate.safety_ratings)
                except IndexError:
                    log.debug(
                        f"{logPrefix} No se encontraron candidates en la respuesta (probablemente bloqueada).")
        log.error(
            f"{logPrefix} Razón (Gemini): {finish_reason}, Safety (Gemini): {safety_ratings}")
    else:
        log.error(
            f"{logPrefix} Error inesperado en llamada API Google Gemini: {type(e).__name__} - {e}", exc_info=True)
        if respuesta:
            try:
                feedback = getattr(respuesta, 'prompt_feedback', None)
                if feedback:
                    log.error(
                        f"{logPrefix} Prompt Feedback (Gemini, si disponible): {feedback}")
            except Exception as e_fb:
                log.debug(
                    f"Error al intentar obtener feedback de la respuesta Gemini: {e_fb}")