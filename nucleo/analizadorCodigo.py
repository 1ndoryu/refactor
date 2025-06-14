# nucleo/analizadorCodigo.py
import os
import logging
import json
import random
import re
import datetime
import google.generativeai as genai
import google.generativeai.types as types
import google.api_core.exceptions
# Mantenido por si se usa OpenRouter directamente
from openai import OpenAI, APIError
from config import settings
# from google.generativeai import types # types está en genai.types

log = logging.getLogger(__name__)
geminiConfigurado = False
API_TIMEOUT_SECONDS = 300  # 5 minutos, podría ser configurable


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
    # Nueva lógica para listar la carpeta 'app/' completa
    if rutaProyecto == settings.RUTACLON:  # Solo si estamos en la raíz del proyecto clonado
        rutaApp = os.path.join(settings.RUTACLON, 'app')
        log.info(
            f"{logPrefix} Proyecto raíz detectado. Intentando listar contenido de: {rutaApp}")
        if os.path.isdir(rutaApp):
            rutaBaseParaListar = rutaApp
            log.info(
                f"{logPrefix} Se listará el contenido completo de la carpeta: {rutaBaseParaListar}")
        else:
            log.warning(
                f"{logPrefix} La carpeta '{rutaApp}' no existe. Se usará la ruta original del proyecto: {rutaProyecto}")
            # rutaBaseParaListar permanece como rutaProyecto
    else:
        log.info(
            f"{logPrefix} No se está analizando el proyecto raíz, se listarán archivos de: {rutaProyecto}")

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

        log.info(
            f"{logPrefix} Archivos relevantes encontrados ({len(archivosProyecto)}) desde '{rutaBaseParaListar}'.")
        return archivosProyecto
    except Exception as e:
        log.error(
            f"{logPrefix} Error listando archivos en {rutaBaseParaListar}: {e}", exc_info=True)


def leerArchivos(listaArchivos, rutaBase, api_provider='google'):  # Añadido api_provider
    logPrefix = "leerArchivos:"

    if not listaArchivos:
        log.info(f"{logPrefix} La lista de archivos a leer estaba vacía.")
        return {'contenido': "", 'bytes': 0, 'tokens': 0, 'archivos_leidos': 0}

    contenidoConcatenado = ""
    archivosLeidos = 0
    bytesTotales = 0
    tokensTotales = 0  # Nuevo para contar tokens
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

    if archivosFallidos:
        log.warning(
            f"{logPrefix} No se pudieron leer {len(archivosFallidos)} archivos: {archivosFallidos[:5]}{'...' if len(archivosFallidos) > 5 else ''}")

    if archivosLeidos > 0:
        tamanoKB = bytesTotales / 1024
        log_msg_base = f"{logPrefix} Leídos {archivosLeidos} archivos. Tamaño total: {tamanoKB:.2f} KB."

        if contenidoConcatenado:
            tokensTotales = contarTokensTexto(
                contenidoConcatenado, api_provider)
            log.info(f"{log_msg_base} Tokens estimados: {tokensTotales}.")
        else:
            log.info(log_msg_base + " Contenido vacío, 0 tokens.")

        return {'contenido': contenidoConcatenado, 'bytes': bytesTotales, 'tokens': tokensTotales, 'archivos_leidos': archivosLeidos}
    else:
        log.warning(
            f"{logPrefix} No se leyó ningún archivo. Total de rutas intentadas: {len(listaArchivos)}.")
        return {'contenido': "", 'bytes': 0, 'tokens': 0, 'archivos_leidos': 0}


def contarTokensTexto(texto, api_provider='google'):
    logPrefix = "contarTokensTexto:"
    tokens = 0
    if not texto:
        return 0

    if api_provider == 'google':
        try:
            modelo_gemini_para_conteo = getattr(
                settings, 'MODELO_GOOGLE_GEMINI', None)
            if modelo_gemini_para_conteo:
                if not geminiConfigurado:
                    configurarGemini()
                model = genai.GenerativeModel(modelo_gemini_para_conteo)
                respuesta_conteo = model.count_tokens(texto)
                tokens = respuesta_conteo.total_tokens
            else:
                log.warning(
                    f"{logPrefix} MODELO_GOOGLE_GEMINI no definido. Tokens no contados para Google.")
                tokens = len(texto) // 4  # Aproximación muy general
        except Exception as e_count_tokens:
            log.error(
                f"{logPrefix} Error contando tokens con Gemini: {e_count_tokens}", exc_info=True)
            tokens = len(texto) // 4
    else:  # OpenRouter u otros
        tokens = len(texto) // 4  # Aproximación general
    return tokens


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


def generar_contenido_mision_desde_texto_guia(ruta_repo: str, contenido_texto_guia: str, nombre_archivo_guia: str, api_provider: str):
    """
    Paso Alternativo 1.2: IA genera el contenido para md de la mision a partir de un texto guía (ej. TODO.md).
    """
    logPrefix = f"generar_contenido_mision_desde_texto_guia ({nombre_archivo_guia}/{api_provider.upper()}):"
    logging.info(
        f"{logPrefix} Generando misión a partir del contenido de '{nombre_archivo_guia}'.")

    timestamp_actual = datetime.now().strftime("%Y%m%d%H%M%S")

    promptPartes = [
        f"Eres un asistente de IA que planifica misiones de refactorización de código. Tu tarea es analizar el siguiente texto guía (proveniente del archivo '{nombre_archivo_guia}') y generar una misión de refactorización completa.",
        "El texto guía NO tiene una estructura fija, debes interpretarlo para extraer tareas de desarrollo o refactorización.",
        "\n--- CONTENIDO DEL TEXTO GUÍA A ANALIZAR ---",
        contenido_texto_guia,
        "\n--- TU TAREA: GENERAR LA MISIÓN ---",
        "Debes generar ÚNICAMENTE un objeto JSON con la siguiente estructura:",
        """
```json
{
  "nombre_clave_mision": "UnNombreCortoYUnicoParaLaMision",
  "contenido_markdown_mision": "Contenido completo en formato Markdown para el archivo de misión"
}
```""",
        "REGLAS PARA EL JSON:",
        f"1. `nombre_clave_mision`: String. Debe ser corto (máx 30-40 chars), descriptivo, usar CamelCase o snake_case (preferiblemente con guiones bajos, ej. `Mision_Desde_TODO_{timestamp_actual}`), y ser adecuado para un nombre de rama Git. Intenta que sea único. Considera usar '{timestamp_actual}' como parte del nombre si es genérico.",
        "2. `contenido_markdown_mision`: String. Este es el contenido completo para el archivo de misión (cuyo nombre será `[nombre_clave_mision].md`, donde `[nombre_clave_mision]` es el valor que generes para la clave `nombre_clave_mision` en este mismo JSON). Debe seguir ESTRICTAMENTE el siguiente formato:",
        "   ```markdown",
        "   # Misión: [nombre_clave_mision] (Debe coincidir con el JSON y la clave 'Nombre Clave' abajo)",
        "",
        "   **Metadatos de la Misión:**",
        "   - **Nombre Clave:** [nombre_clave_mision] (Debe coincidir con el JSON y el título)",
        f"   - **Archivo Principal:** Basado en {nombre_archivo_guia}",
        f"   - **Archivos de Contexto (Generación):** Ninguno (ya que la misión se basa en '{nombre_archivo_guia}')",
        f"   - **Archivos de Contexto (Ejecución):** [lista_de_rutas_sin_corchetes_individuales] (Si el texto guía menciona archivos específicos que deberían ser contexto para ejecutar las tareas, lístalos aquí, separados por coma. Si no, escribe: `Ninguno`. IMPORTANTE: cada ruta NO DEBE contener corchetes `[` o `]` ni caracteres especiales. Deben ser rutas relativas limpias. Ejemplo: `app/utils.py, core/helper.php`.)",
        f"   - **Razón (Paso 1.1):** Misión generada a partir del análisis de '{nombre_archivo_guia}'.",
        "   - **Estado:** PENDIENTE",
        "",
        "   ## Tareas de Refactorización (Genera entre 1 y 5 tareas pequeñas y atómicas basadas en el texto guía. DEBES generar al menos UNA tarea si el texto guía tiene contenido accionable.):",
        "   ---",
        "   ### Tarea [ID_TAREA_EJEMPLO_1]: [Título Corto y Descriptivo de la Tarea 1]",
        "   - **ID:** [ID_TAREA_EJEMPLO_1] (Debe ser único en la misión, ej: TSK-TODO-001. DEBE COINCIDIR con el ID en el encabezado '### Tarea ...'.)",
        "   - **Estado:** PENDIENTE",
        "   - **Descripción:** [Descripción detallada, clara y accionable de la primera tarea derivada del texto guía. ¿Qué se debe hacer? ¿En qué archivo(s) específicamente si el texto lo sugiere? ¿Cuál es el objetivo? Sé explícito.]",
        "   - **Archivos Implicados Específicos (Opcional):** [ruta/al/archivo1.py, otra/ruta/archivo2.php] (Si la tarea se enfoca en archivos específicos mencionados en el texto guía. Lista separada por comas. IMPORTANTE: cada ruta aquí NO DEBE contener corchetes `[` o `]` ni otros caracteres inválidos para rutas. Si no, escribe textualmente: `Ninguno`.)",
        "   - **Intentos:** 0",
        "   ---",
        "   (Si se necesitan más tareas, usa el mismo formato exacto, separadas por ---. Recuerda: genera entre 1 y 5 tareas. Es OBLIGATORIO generar al menos UNA tarea si el texto guía contiene directrices.)",
        "   ```",
        "   Consideraciones ADICIONALES para `contenido_markdown_mision`:",
        "   - **OBLIGATORIO:** Debes generar al menos una tarea si el texto guía parece contener alguna directriz, por vaga que sea. Si el texto guía está completamente vacío o es incomprensible, puedes generar una sola tarea como 'Revisar y clarificar contenido de TODO.md'.",
        "   - Las tareas deben ser PEQUEÑAS, ESPECÍFICAS y REALIZABLES por otra IA en un solo paso.",
        "   - Los IDs de las tareas deben ser únicos dentro de la misión.",
        "   - **RUTAS DE ARCHIVO:** Para CUALQUIER ruta de archivo que generes (en 'Archivos de Contexto (Ejecución)' o en 'Archivos Implicados Específicos' de una tarea), ASEGÚRATE de que sean rutas relativas válidas. NO uses corchetes `[` o `]` DENTRO de las rutas individuales. Usa `/` como separador de directorios.",
        "No añadas explicaciones fuera del JSON. El `nombre_clave_mision` en el JSON y en el Markdown (título y metadato) DEBEN COINCIDIR."
    ]
    promptCompleto = "\n".join(promptPartes)

    textoRespuesta = None
    respuestaJson = None

    try:
        if api_provider == 'google':
            if not configurarGemini():
                return None
            modelo = genai.GenerativeModel(settings.MODELO_GOOGLE_GEMINI)
            respuesta = modelo.generate_content(
                promptCompleto,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.6, response_mime_type="application/json", max_output_tokens=settings.MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS),
                safety_settings={'HATE': 'BLOCK_MEDIUM_AND_ABOVE', 'HARASSMENT': 'BLOCK_MEDIUM_AND_ABOVE',
                                 'SEXUAL': 'BLOCK_MEDIUM_AND_ABOVE', 'DANGEROUS': 'BLOCK_MEDIUM_AND_ABOVE'}
            )
            textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        elif api_provider == 'openrouter':
            if not settings.OPENROUTER_API_KEY:
                logging.error(f"{logPrefix} Falta OPENROUTER_API_KEY.")
                return None
            client = OpenAI(base_url=settings.OPENROUTER_BASE_URL,
                            api_key=settings.OPENROUTER_API_KEY)
            mensajes = [{"role": "user", "content": promptCompleto}]
            completion = client.chat.completions.create(
                extra_headers={"HTTP-Referer": settings.OPENROUTER_REFERER,
                               "X-Title": settings.OPENROUTER_TITLE},
                model=settings.OPENROUTER_MODEL, messages=mensajes, temperature=0.6, max_tokens=settings.MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS, timeout=API_TIMEOUT_SECONDS
            )
            if completion.choices:
                textoRespuesta = completion.choices[0].message.content
        else:
            logging.error(
                f"{logPrefix} Proveedor API '{api_provider}' no soportado.")
            return None

        if not textoRespuesta:
            logging.error(f"{logPrefix} No se obtuvo texto de la IA.")
            return None

        respuestaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        if not respuestaJson:
            return None
        if not all(k in respuestaJson for k in ["nombre_clave_mision", "contenido_markdown_mision"]):
            logging.error(
                f"{logPrefix} Respuesta JSON no tiene la estructura esperada. Recibido: {respuestaJson}")
            return None

        nombre_clave_json = respuestaJson["nombre_clave_mision"]
        contenido_md = respuestaJson["contenido_markdown_mision"]
        
        if f"# Misión: {nombre_clave_json}" not in contenido_md:
            logging.warning(f"{logPrefix} El nombre_clave_mision '{nombre_clave_json}' del JSON no coincide exactamente con el título '# Misión: ...' en el contenido_markdown_mision.")
        if f"- **Nombre Clave:** {nombre_clave_json}" not in contenido_md:
            logging.warning(f"{logPrefix} El nombre_clave_mision '{nombre_clave_json}' del JSON no coincide con el metadato '- **Nombre Clave:** ...' en el contenido_markdown_mision.")
        if "### Tarea" not in contenido_md:
             logging.warning(f"{logPrefix} El contenido_markdown_mision generado parece NO TENER TAREAS DEFINIDAS (no se encontró '### Tarea'). Esto podría ser un problema. Fuente: '{nombre_archivo_guia}'.")

        logging.info(
            f"{logPrefix} Contenido de misión generado desde '{nombre_archivo_guia}'. Nombre clave: {nombre_clave_json}")
        return respuestaJson

    except Exception as e:
        logging.error(
            f"{logPrefix} Error en generación de contenido de misión desde '{nombre_archivo_guia}': {e}", exc_info=True)
        _manejar_excepcion_api(e, api_provider, logPrefix,
                               locals().get('respuesta'))
        return None

def obtenerDecisionRefactor(contextoCodigoCompleto, historialCambiosTexto=None, estructura_proyecto_texto=None, api_provider='google'):
    # Esta función es la del "Paso 1" original, se mantiene por si se usa, pero el nuevo flujo usa funciones más específicas.
    # Se podría refactorizar para que llame a `solicitar_evaluacion_archivo` si el contexto es de un solo archivo,
    # o mantenerla para un análisis global si es necesario en algún punto.
    # Por ahora, la dejamos como estaba en el archivo original.
    logPrefix = f"obtenerDecisionRefactor(Paso 1 ANTIGUO/{api_provider.upper()}):"
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
    # ... (resto del prompt original) ...
    promptPartes.append(
        "10. Si vas a eliminar algo porque un archivo esta vacío, asegurate de que realmente este vacío.")

    if estructura_proyecto_texto:
        promptPartes.append(
            "\n--- ESTRUCTURA ACTUAL DEL PROYECTO (Visión Global) ---")
        promptPartes.append(
            "# Nota: Esta estructura puede estar limitada en profundidad.")
        promptPartes.append(estructura_proyecto_texto)
        promptPartes.append("--- FIN ESTRUCTURA ---")
    else:
        promptPartes.append("\n(No se proporcionó la estructura del proyecto)")

    if historialCambiosTexto:
        promptPartes.append(
            "\n--- HISTORIAL DE CAMBIOS RECIENTES (para tu contexto, EVITA REPETIR o deshacer) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")

    promptPartes.append("\n--- CÓDIGO FUENTE COMPLETO A ANALIZAR ---")
    promptPartes.append(
        contextoCodigoCompleto if contextoCodigoCompleto else "(No se proporcionó código fuente completo, analiza basado en estructura e historial)")
    promptPartes.append("--- FIN CÓDIGO ---")
    promptPartes.append(
        "\n**IMPORTANTE**: Responde ÚNICAMENTE con el objeto JSON que cumple TODAS las reglas anteriores. No incluyas explicaciones adicionales fuera del JSON. Asegúrate de que el JSON sea válido.")

    promptCompleto = "\n".join(promptPartes)
    # (Lógica de llamada a API y parseo de JSON como en el original)
    # ...
    # Esto es un placeholder de la lógica de llamada que ya existe.
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
                    temperature=0.4, response_mime_type="application/json", max_output_tokens=60000),
                safety_settings={'HATE': 'BLOCK_MEDIUM_AND_ABOVE', 'HARASSMENT': 'BLOCK_MEDIUM_AND_ABOVE',
                                 'SEXUAL': 'BLOCK_MEDIUM_AND_ABOVE', 'DANGEROUS': 'BLOCK_MEDIUM_AND_ABOVE'}
            )
            textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        elif api_provider == 'openrouter':
            # ... (Lógica OpenRouter como en el original)
            log.info(
                f"{logPrefix} Usando OpenRouter API (Modelo: {settings.OPENROUTER_MODEL}).")
            if not settings.OPENROUTER_API_KEY:
                log.error(
                    f"{logPrefix} Falta OPENROUTER_API_KEY en la configuración.")
                return None
            client = OpenAI(base_url=settings.OPENROUTER_BASE_URL,
                            api_key=settings.OPENROUTER_API_KEY)
            mensajes = [{"role": "user", "content": promptCompleto}]
            completion = client.chat.completions.create(
                extra_headers={"HTTP-Referer": settings.OPENROUTER_REFERER,
                               "X-Title": settings.OPENROUTER_TITLE},
                # Ajustar max_tokens según necesidad
                model=settings.OPENROUTER_MODEL, messages=mensajes, temperature=0.4, max_tokens=60000, timeout=API_TIMEOUT_SECONDS
            )
            if completion.choices:
                textoRespuesta = completion.choices[0].message.content
        else:
            log.error(
                f"{logPrefix} Proveedor de API no soportado: {api_provider}")
            return None

        if not textoRespuesta:
            log.error(
                f"{logPrefix} No se pudo extraer texto de la respuesta de la IA.")
            return None

        respuestaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)
        # (Validaciones del JSON como en el original)
        if respuestaJson and respuestaJson.get("tipo_analisis") == "refactor_decision":
            return respuestaJson
        else:
            log.error(
                f"{logPrefix} JSON de respuesta inválido o tipo incorrecto.")
            return None

    except Exception as e:
        log.error(f"{logPrefix} Error durante llamada a API: {e}",
                  exc_info=True)
        # (Manejo de excepciones como en el original)
        return None


def ejecutarAccionConGemini(decisionParseada, contextoCodigoReducido, api_provider='google'):
    # Esta función es la del "Paso 2" original. Se podría refactorizar para que la llame `ejecutar_tarea_especifica_mision`
    # si la "decisión parseada" coincide con el formato de una tarea.
    # Por ahora, la dejamos como estaba en el archivo original.
    # Renombrado en log para claridad
    logPrefix = f"ejecutarAccionConIA(Paso 2 ANTIGUO/{api_provider.upper()}):"
    # ... (prompt y lógica como en el archivo original) ...
    # Esto es un placeholder de la lógica de llamada que ya existe.
    # ... (prompt original)
    accion = decisionParseada.get("accion_propuesta")
    descripcion = decisionParseada.get("descripcion")
    params = decisionParseada.get("parametros_accion", {})
    razonamiento_paso1 = decisionParseada.get("razonamiento")

    promptPartes = []
    promptPartes.append(
        "Eres un asistente de refactorización que EJECUTA una decisión ya tomada por otro agente IA.")
    promptPartes.append("**FORMATO DE COMENTARIOS O CODIGO CON SALTO DE LINEAS:** Si generas comentarios multilínea que usan `//` (PHP/JS), ASEGÚRATE de que **CADA LÍNEA** del comentario comience con `//` dentro del código generado.")
    promptPartes.append("1. No uses namespace, aqui todos los archivos estan al alcance global para que sea mas facil mover cosas, si se te pide usarlos o hacerlos, fue un error, decide no hacer nada si te causa confusión una decisión y regresa el codigo igual sin cambiar nada.")
    promptPartes.append("2. Si vas a mover algo, segurate de que realmente se esta moviendo algo, asegurate de tener el contexto necesario para mover lo que se te pide a los archivos indicados, si la decisión parece erronea, mejor no hagas nada y regresa el codigo igual sin cambiar nada.")
    promptPartes.append("3. Si vas a eliminar algo porque un archivo esta vacío, asegurate de que realmente este vacío, el anterior agente puede cometer el error de pedir eliminar un archivo supuestamente vacío pero a veces no lo esta, mejor no hagas nada si la decisión parece confusa y regresa el codigo igual sin cambiar nada.")
    promptPartes.append(
        "4. Siempre deja un comentario en el codigo indicando brevemente la acción que realizaste.")
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
    // Si la acción es eliminar_archivo o crear_directorio, este objeto debe ser exactamente: {}
  }
}
```""")
    promptPartes.append(
        "\n--- REGLAS DE EJECUCIÓN Y FORMATO JSON (¡MUY IMPORTANTE!) ---")
    promptPartes.append("1.  **SIGUE LA DECISIÓN AL PIE DE LA LETRA.**")
    promptPartes.append("2.  **CONTENIDO DE ARCHIVOS:** Para CADA archivo afectado (modificado o creado), incluye su ruta relativa como clave y su contenido ÍNTEGRO final como valor string en `archivos_modificados`.")
    promptPartes.append("3.  **¡ESCAPADO CRÍTICO!** Dentro de las cadenas de texto que representan el contenido de los archivos (los valores en `archivos_modificados`), **TODAS** las comillas dobles (`\"`) literales DEBEN ser escapadas como `\\\"`. Todos los backslashes (`\\`) literales DEBEN ser escapados como `\\\\`. Los saltos de línea DEBEN ser `\\n`.")
    promptPartes.append(
        "4.  **PRESERVA CÓDIGO:** Mantén intacto el resto del código no afectado en los archivos modificados, asegurate de que todo el codigo tenga sentido.")
    promptPartes.append(
        "5.  **MOVIMIENTOS:** Si mueves código y `eliminar_de_origen` es true, BORRA el código original del `archivo_origen`.")
    promptPartes.append(
        "6.  **MODIFICACIONES INTERNAS:** Aplica EXACTAMENTE la `descripcion_del_cambio_interno`.")
    promptPartes.append(
        "7.  **CREACIÓN:** Genera contenido inicial basado en `proposito_del_archivo`.")
    promptPartes.append("8.  **SIN CONTENIDO:** Si la acción es `eliminar_archivo` o `crear_directorio`, el objeto `archivos_modificados` debe ser exactamente `{}`, un objeto JSON vacío. EXCEPCIÓN: Si se pide eliminar un archivo NO VACÍO, devuelve el JSON con el contenido original del archivo (no lo borres) y añade una nota en un campo 'advertencia_ejecucion'.")
    promptPartes.append("9. **VALIDACIÓN CRÍTICA DE STRINGS JSON PARA CÓDIGO:** Asegúrate de que el contenido de los archivos (especialmente código PHP/JS) sea un string JSON VÁLIDO Y COMPLETO (escapa `\"` como `\\\"`, `\\` como `\\\\`, saltos de línea como `\\n`). Evita truncamiento. Presta MÁXIMA atención a esto.")

    if contextoCodigoReducido:
        promptPartes.append(
            "\n--- CONTENIDO ACTUAL DE ARCHIVOS RELEVANTES ---")
        promptPartes.append(contextoCodigoReducido)
        promptPartes.append("--- FIN CONTENIDO ---")
    else:
        promptPartes.append(
            "\n(No se proporcionó contenido de archivo para esta acción específica o no aplica)")

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
                generation_config=genai.types.GenerationConfig(temperature=0.5, response_mime_type="application/json", max_output_tokens=settings.MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS if hasattr(
                    # Usar 8192 si no está definido
                    settings, 'MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS') else 60000),
                safety_settings={'HATE': 'BLOCK_ONLY_HIGH', 'HARASSMENT': 'BLOCK_ONLY_HIGH',
                                 'SEXUAL': 'BLOCK_ONLY_HIGH', 'DANGEROUS': 'BLOCK_ONLY_HIGH'}
            )
            textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        elif api_provider == 'openrouter':
            # ... (Lógica OpenRouter como en el original)
            log.info(
                f"{logPrefix} Usando OpenRouter API (Modelo: {settings.OPENROUTER_MODEL}).")
            if not settings.OPENROUTER_API_KEY:
                log.error(
                    f"{logPrefix} Falta OPENROUTER_API_KEY en la configuración.")
                return None
            client = OpenAI(base_url=settings.OPENROUTER_BASE_URL,
                            api_key=settings.OPENROUTER_API_KEY)
            mensajes = [{"role": "user", "content": promptCompleto}]
            completion = client.chat.completions.create(
                extra_headers={"HTTP-Referer": settings.OPENROUTER_REFERER,
                               "X-Title": settings.OPENROUTER_TITLE},
                model=settings.OPENROUTER_MODEL, messages=mensajes, temperature=0.4, max_tokens=60000, timeout=API_TIMEOUT_SECONDS  # Ajustar max_tokens
            )  # Aumentar max_tokens para generación de código
            if completion.choices:
                textoRespuesta = completion.choices[0].message.content

        else:
            log.error(
                f"{logPrefix} Proveedor de API no soportado: {api_provider}")
            return None

        if not textoRespuesta:
            log.error(
                f"{logPrefix} No se pudo extraer texto de la respuesta de la IA.")
            return None

        respuestaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)
        # (Validaciones del JSON como en el original)
        if respuestaJson and respuestaJson.get("tipo_resultado") == "ejecucion_cambio" and "archivos_modificados" in respuestaJson:
            return respuestaJson
        else:
            log.error(
                f"{logPrefix} JSON de respuesta inválido, tipo incorrecto o falta 'archivos_modificados'.")
            return None

    except Exception as e:
        log.error(f"{logPrefix} Error durante llamada a API: {e}",
                  exc_info=True)
        # (Manejo de excepciones como en el original)
        return None


# --- Nuevas Funciones para el Flujo Adaptativo ---

def solicitar_evaluacion_archivo(ruta_archivo_seleccionado_rel: str, contenido_archivo: str, estructura_proyecto: str, api_provider: str, reglas_refactor: str = ""):
    """
    Paso 1.1: IA decide si un archivo necesita refactorización y qué contexto adicional podría necesitar.
    """
    logPrefix = f"solicitar_evaluacion_archivo (Paso 1.1/{api_provider.upper()}):"
    log.info(
        f"{logPrefix} Evaluando archivo '{ruta_archivo_seleccionado_rel}' para refactorización.")

    promptPartes = [
        f"Eres un asistente de IA experto en análisis de código. Tu tarea es evaluar el archivo '{ruta_archivo_seleccionado_rel}' y decidir si necesita refactorización.",
        "Considera las siguientes REGLAS GENERALES DE REFACTORIZACIÓN (si se proporcionan) y buenas prácticas de desarrollo (claridad, refactorizacion, simplificacion, mantenibilidad, DRY, SRP, seguridad básica, optimización leve).",
        "Reglas Específicas del Proyecto (si hay):",
        reglas_refactor if reglas_refactor else "No se proporcionaron reglas específicas adicionales para este proyecto. Usa tu juicio experto general.",
        "\n--- ESTRUCTURA DEL PROYECTO (para contexto de ubicación y posibles movimientos) ---",
        estructura_proyecto if estructura_proyecto else "(Estructura del proyecto no disponible)",
        "\n--- CONTENIDO DEL ARCHIVO SELECCIONADO A EVALUAR ---",
        f"Ruta Relativa: {ruta_archivo_seleccionado_rel}",
        contenido_archivo,
        "\n--- TU ANÁLISIS Y DECISIÓN ---",
        "Analiza el archivo y responde ÚNICAMENTE con un objeto JSON con la siguiente estructura:",
        """
```json
{
  "necesita_refactor": true_o_false,
  "necesita_contexto_adicional": true_o_false,
  "archivos_contexto_sugeridos": ["ruta/relativa/contexto1.py", "ruta/relativa/contexto2.md"],
  "razonamiento": "Tu justificación detallada sobre por qué necesita (o no) refactorización y por qué podrías necesitar (o no) contexto adicional, incluyendo qué buscarías en esos archivos de contexto."
}
```""",
        "DETALLES DEL JSON:",
        "- `necesita_refactor`: (boolean) True si crees que el archivo se beneficiaría de una refactorización (incluso pequeña).",
        "- `necesita_contexto_adicional`: (boolean) True si, PARA GENERAR UNA MISIÓN DE REFACTORIZACIÓN DETALLADA, necesitarías leer el contenido de OTROS archivos para entender mejor las interacciones, dependencias, o para realizar movimientos de código. Si `necesita_refactor` es false, esto también debería ser false.",
        "- `archivos_contexto_sugeridos`: (lista de strings) Si `necesita_contexto_adicional` es true, lista las rutas RELATIVAS de los archivos que sugieres leer. Elige archivos que parezcan relacionados por nombre o por la lógica del archivo evaluado, basándote en la estructura del proyecto. No más de 3-5 archivos.",
        "- `razonamiento`: (string) Explica tu decisión. Si no necesita refactor, explica por qué. Si necesita, explica qué tipo de refactorización visualizas y por qué el contexto adicional (si lo pides) sería útil.",
        "Sé conciso pero claro en tu razonamiento. No generes código, solo el JSON de evaluación."
    ]
    promptCompleto = "\n".join(promptPartes)

    tokens_estimados_prompt = len(promptCompleto) // 4  # Estimación muy burda
    # El conteo real de tokens del contenido ya se hizo al leer el archivo
    # Se asume que la gestión de límites se hace antes de llamar esta función en principal.py

    textoRespuesta = None
    respuestaJson = None

    try:
        if api_provider == 'google':
            if not configurarGemini():
                return None
            modelo = genai.GenerativeModel(settings.MODELO_GOOGLE_GEMINI)
            respuesta = modelo.generate_content(
                promptCompleto,
                generation_config=genai.types.GenerationConfig(
                    # Max tokens más bajo para decisión
                    temperature=0.5, response_mime_type="application/json", max_output_tokens=60000),
                safety_settings={'HATE': 'BLOCK_MEDIUM_AND_ABOVE', 'HARASSMENT': 'BLOCK_MEDIUM_AND_ABOVE',
                                 'SEXUAL': 'BLOCK_MEDIUM_AND_ABOVE', 'DANGEROUS': 'BLOCK_MEDIUM_AND_ABOVE'}
            )
            textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        elif api_provider == 'openrouter':
            if not settings.OPENROUTER_API_KEY:
                log.error(f"{logPrefix} Falta OPENROUTER_API_KEY.")
                return None
            client = OpenAI(base_url=settings.OPENROUTER_BASE_URL,
                            api_key=settings.OPENROUTER_API_KEY)
            mensajes = [{"role": "user", "content": promptCompleto}]
            completion = client.chat.completions.create(
                extra_headers={"HTTP-Referer": settings.OPENROUTER_REFERER,
                               "X-Title": settings.OPENROUTER_TITLE},
                model=settings.OPENROUTER_MODEL, messages=mensajes, temperature=0.5, max_tokens=60000, timeout=API_TIMEOUT_SECONDS
            )
            if completion.choices:
                textoRespuesta = completion.choices[0].message.content
        else:
            log.error(
                f"{logPrefix} Proveedor API '{api_provider}' no soportado.")
            return None

        if not textoRespuesta:
            log.error(f"{logPrefix} No se obtuvo texto de la IA.")
            return None

        respuestaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        if not respuestaJson:
            return None
        # Validar estructura básica
        if not all(k in respuestaJson for k in ["necesita_refactor", "necesita_contexto_adicional", "archivos_contexto_sugeridos", "razonamiento"]):
            log.error(
                f"{logPrefix} Respuesta JSON no tiene la estructura esperada. Recibido: {respuestaJson}")
            return None

        log.info(f"{logPrefix} Evaluación recibida para '{ruta_archivo_seleccionado_rel}'. Necesita refactor: {respuestaJson.get('necesita_refactor')}")
        return respuestaJson

    except Exception as e:
        log.error(
            f"{logPrefix} Error en solicitud de evaluación de archivo: {e}", exc_info=True)
        _manejar_excepcion_api(e, api_provider, logPrefix,
                               locals().get('respuesta'))
        return None

def generar_contenido_mision_orion(archivo_a_refactorizar_rel: str, contexto_archivos_leidos: str, razonamiento_paso1_1: str, api_provider: str, archivos_contexto_generacion_rel_list: list):
    """
    Paso 1.2: IA genera el contenido para md de la mision (nombre clave y tareas).
    El contexto_archivos_leidos SE ESPERA que ya venga con números de línea inyectados por _inyectar_numeros_linea.
    """
    logPrefix = f"generar_contenido_mision_orion (Paso 1.2/{api_provider.upper()}):"
    log.info(
        f"{logPrefix} Generando misión para archivo: {archivo_a_refactorizar_rel}")

    archivos_contexto_generacion_str_parts = []
    if archivos_contexto_generacion_rel_list:
        for ruta_ctx_gen in archivos_contexto_generacion_rel_list:
            ruta_limpia_prompt = str(ruta_ctx_gen).replace('[', '').replace(']', '').strip()
            if ruta_limpia_prompt:
                archivos_contexto_generacion_str_parts.append(ruta_limpia_prompt)
    
    archivos_contexto_generacion_str = ", ".join(archivos_contexto_generacion_str_parts) if archivos_contexto_generacion_str_parts else "Ninguno"

    promptPartes = [
        "Eres un asistente de IA que planifica misiones de refactorización de código. Basado en el archivo principal, su contexto (QUE AHORA INCLUYE NÚMEROS DE LÍNEA PREFIJADOS A CADA LÍNEA, ej: `1: codigo...`), y un razonamiento previo, debes generar una misión.",
        f"El archivo principal a refactorizar es: '{archivo_a_refactorizar_rel}'.",
        f"El razonamiento del paso anterior (Paso 1.1) para refactorizar fue: '{razonamiento_paso1_1 if razonamiento_paso1_1 else 'No se proporcionó razonamiento previo específico. Si este razonamiento indica que se necesita refactorizar, DEBES generar al menos una tarea.'}'",
        f"Los archivos que se leyeron para proporcionar contexto para esta generación de misión son: {archivos_contexto_generacion_str}.",
        "\n--- CONTENIDO DE LOS ARCHIVOS RELEVANTES (Incluye el archivo principal y los de contexto. CADA LÍNEA ESTÁ PREFIJADA CON SU NÚMERO DE LÍNEA seguido de ': ', ej: '1: <?php') ---",
        contexto_archivos_leidos,
        "\n--- TU TAREA: GENERAR LA MISIÓN ---",
        "Debes generar ÚNICAMENTE un objeto JSON con la siguiente estructura:",
        """
```json
{
  "nombre_clave_mision": "UnNombreCortoYUnicoParaLaMision",
  "contenido_markdown_mision": "Contenido completo en formato Markdown para el archivo de misión"
}
```""",
        "REGLAS PARA EL JSON:",
        "1. `nombre_clave_mision`: String. Debe ser corto (máx 30-40 chars), descriptivo, usar CamelCase o snake_case (preferiblemente con guiones bajos si es snake_case, ej. `Refactor_Login_Handler`), y ser adecuado para un nombre de rama Git (ej: `RefactorLoginHandler`, `OptimizarQueriesDB_123`). Intenta que sea único añadiendo un identificador numérico corto si es una tarea común.",
        "2. `contenido_markdown_mision`: String. Este es el contenido completo para el archivo de misión (cuyo nombre será `[nombre_clave_mision].md`). Debe seguir ESTRICTAMENTE el siguiente formato:",
        "   ```markdown",
        "   # Misión: [nombre_clave_mision] (Debe coincidir con el JSON y la clave 'Nombre Clave' abajo)",
        "",
        "   **Metadatos de la Misión:**",
        "   - **Nombre Clave:** [nombre_clave_mision] (Debe coincidir con el JSON y el título)",
        f"   - **Archivo Principal:** {archivo_a_refactorizar_rel}",
        f"   - **Archivos de Contexto (Generación):** {archivos_contexto_generacion_str}",
        f"   - **Archivos de Contexto (Ejecución):** [lista_de_rutas_sin_corchetes_individuales] (Inicialmente, usa la misma lista que 'Generación'. IMPORTANTE: cada ruta en esta lista NO DEBE contener corchetes `[` o `]` ni caracteres especiales que no sean válidos en rutas de archivo. Deben ser rutas relativas limpias separadas por coma. Ejemplo: `app/utils.py, core/helper.php`. Si no hay, escribe: `Ninguno`.)",
        f"   - **Razón (Paso 1.1):** {razonamiento_paso1_1 if razonamiento_paso1_1 else 'N/A'}",
        "   - **Estado:** PENDIENTE",
        "",
        "   ## Tareas de Refactorización (Genera entre 1 y 5 tareas pequeñas y atómicas. Si el razonamiento del Paso 1.1 fue refactorizar, DEBES generar al menos UNA tarea.):",
        "   ---",
        "   ### Tarea [ID_TAREA_EJEMPLO_1]: [Título Corto y Descriptivo de la Tarea 1]",
        "   - **ID:** [ID_TAREA_EJEMPLO_1] (Debe ser único en la misión, ej: TSK-001, RF-FuncX. DEBE COINCIDIR con el ID en el encabezado '### Tarea ...'.)",
        "   - **Estado:** PENDIENTE",
        "   - **Descripción:** [Descripción detallada, clara y accionable de la primera tarea. ¿Qué se debe hacer? ¿En qué archivo(s) específicamente? ¿Cuál es el objetivo? Sé explícito. Por ejemplo: \"Refactorizar la función `getUserDetails` en `user_module.py` para usar el nuevo servicio `AuthService` en lugar de acceso directo a DB. Actualizar llamadas en `profile_view.py`.\"]",
        "   - **Archivos Implicados Específicos:** [ruta/al/archivo1.py, otra/ruta/archivo2.php] (Si la tarea se enfoca en archivos específicos ADICIONALES al principal o al contexto general, o si la tarea es CREAR un nuevo archivo, incluye su ruta aquí. Lista separada por comas. IMPORTANTE: cada ruta aquí NO DEBE contener corchetes `[` o `]` ni otros caracteres inválidos para rutas. Si no, escribe textualmente: `Ninguno`.)",
        "   - **Intentos:** 0",
        "   - **Bloques de Código Objetivo:** (OBLIGATORIO para cada tarea. Describe los fragmentos de código específicos que la tarea modificará, creará o eliminará.)",
        "     - **Archivo:** `ruta/relativa/al/archivo_afectado.ext` (Ruta relativa al archivo afectado. DEBE coincidir con una ruta en 'Archivo Principal', 'Archivos de Contexto (Ejecución)' o 'Archivos Implicados Específicos').",
        "       - **Nombre Bloque:** `nombreFuncionMetodoClase` (Nombre de la función, método o clase a modificar/crear/eliminar. Si crea un archivo nuevo, puede ser nombre de clase principal o 'ContenidoInicial').",
        "       - **Línea Inicio:** NNN (USA LOS NÚMEROS DE LÍNEA DEL CONTEXTO PROVISTO CON NÚMEROS DE LÍNEA. Para un bloque existente, su línea de inicio. Si el archivo es NUEVO y se va a crear, usa `1`. Si se añade un bloque nuevo a un archivo existente, esta es la línea donde el nuevo bloque comenzará a insertarse, o la línea de inicio del bloque contenedor, ej. la clase).",
        "       - **Línea Fin:** MMM (USA LOS NÚMEROS DE LÍNEA DEL CONTEXTO. Para un bloque existente, su línea final. Si el archivo es NUEVO, ESTIMA la línea final del contenido a generar. Si se añade un bloque nuevo, esta es la línea final del nuevo bloque a insertar).",
        "     - (Puedes añadir más bloques bajo el mismo '- Archivo:' si la tarea afecta múltiples funciones/métodos en él, o más entradas de '- Archivo:' si la tarea afecta múltiples archivos).",
        "   ---",
        "   (Si se necesitan más tareas, usa el mismo formato exacto, separadas por ---. Recuerda: genera entre 1 y 5 tareas. Si el razonamiento del Paso 1.1 indicó refactorizar, ES OBLIGATORIO generar al menos UNA tarea.)",
        "   ```",
        "   Consideraciones ADICIONALES para `contenido_markdown_mision`:",
        "   - **OBLIGATORIO:** Si el `razonamiento_paso1_1` sugiere una refactorización, DEBES generar al menos una tarea. Si no hay nada que hacer, el flujo no debería haber llegado aquí, pero si lo hace, genera una tarea del tipo 'Revisar archivo X en busca de mejoras menores.'",
        "   - Las tareas deben ser PEQUEÑAS, ESPECÍFICAS y REALIZABLES por otra IA en un solo paso (Paso 2 del refactorizador).",
        "   - Los IDs de las tareas deben ser únicos dentro de la misión.",
        "   - **RUTAS DE ARCHIVO:** Para CUALQUIER ruta de archivo que generes (en 'Archivos de Contexto (Ejecución)' o en 'Archivos Implicados Específicos' de una tarea, o en 'Bloques de Código Objetivo'), ASEGÚRATE de que sean rutas relativas válidas. NO uses corchetes `[` o `]` DENTRO de las rutas individuales. Usa `/` como separador de directorios. Ejemplos válidos: `src/components/Boton.js`, `app/models/Usuario.php`. Ejemplo inválido: `[app/models/Usuario.php]`.",
        "   - El archivo principal y los de contexto para la generación ya están definidos en los metadatos. Las tareas deben operar sobre estos archivos o los especificados en 'Archivos Implicados Específicos'.",
        "No añadas explicaciones fuera del JSON. El `nombre_clave_mision` en el JSON y en el Markdown (título y metadato) DEBEN COINCIDIR."
    ]
    promptCompleto = "\n".join(promptPartes)

    textoRespuesta = None
    respuestaJson = None

    try:
        if api_provider == 'google':
            if not configurarGemini():
                return None
            modelo = genai.GenerativeModel(settings.MODELO_GOOGLE_GEMINI)
            respuesta = modelo.generate_content(
                promptCompleto,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.6, response_mime_type="application/json", max_output_tokens=settings.MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS), 
                safety_settings={'HATE': 'BLOCK_MEDIUM_AND_ABOVE', 'HARASSMENT': 'BLOCK_MEDIUM_AND_ABOVE',
                                 'SEXUAL': 'BLOCK_MEDIUM_AND_ABOVE', 'DANGEROUS': 'BLOCK_MEDIUM_AND_ABOVE'}
            )
            textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        elif api_provider == 'openrouter':
            if not settings.OPENROUTER_API_KEY:
                log.error(f"{logPrefix} Falta OPENROUTER_API_KEY.")
                return None
            client = OpenAI(base_url=settings.OPENROUTER_BASE_URL,
                            api_key=settings.OPENROUTER_API_KEY)
            mensajes = [{"role": "user", "content": promptCompleto}]
            completion = client.chat.completions.create(
                extra_headers={"HTTP-Referer": settings.OPENROUTER_REFERER,
                               "X-Title": settings.OPENROUTER_TITLE},
                model=settings.OPENROUTER_MODEL, messages=mensajes, temperature=0.6, max_tokens=settings.MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS, timeout=API_TIMEOUT_SECONDS
            )
            if completion.choices:
                textoRespuesta = completion.choices[0].message.content
        else:
            log.error(
                f"{logPrefix} Proveedor API '{api_provider}' no soportado.")
            return None

        if not textoRespuesta:
            log.error(f"{logPrefix} No se obtuvo texto de la IA.")
            return None

        respuestaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        if not respuestaJson:
            return None
        if not all(k in respuestaJson for k in ["nombre_clave_mision", "contenido_markdown_mision"]):
            log.error(
                f"{logPrefix} Respuesta JSON no tiene la estructura esperada. Recibido: {respuestaJson}")
            return None

        nombre_clave_json = respuestaJson["nombre_clave_mision"]
        contenido_md = respuestaJson["contenido_markdown_mision"]
        
        if f"# Misión: {nombre_clave_json}" not in contenido_md:
            log.warning(f"{logPrefix} El nombre_clave_mision '{nombre_clave_json}' del JSON no coincide exactamente con el título '# Misión: ...' en el contenido_markdown_mision.")
        if f"- **Nombre Clave:** {nombre_clave_json}" not in contenido_md:
            log.warning(f"{logPrefix} El nombre_clave_mision '{nombre_clave_json}' del JSON no coincide con el metadato '- **Nombre Clave:** ...' en el contenido_markdown_mision.")
        if "### Tarea" not in contenido_md and "Revisar archivo" not in contenido_md :
             log.warning(f"{logPrefix} El contenido_markdown_mision generado parece NO TENER TAREAS DEFINIDAS (no se encontró '### Tarea'). Esto podría ser un problema para el parser. Razonamiento original: {razonamiento_paso1_1}")
        if "Bloques de Código Objetivo" not in contenido_md and "### Tarea" in contenido_md: # Si hay tareas, debería haber bloques
             log.warning(f"{logPrefix} El contenido_markdown_mision generado TIENE TAREAS pero parece NO TENER LA SECCIÓN 'Bloques de Código Objetivo'. Esto es un problema para el nuevo flujo.")


        log.info(
            f"{logPrefix} Contenido de misión generado. Nombre clave: {nombre_clave_json}")
        return respuestaJson

    except Exception as e:
        log.error(
            f"{logPrefix} Error en generación de contenido de misión: {e}", exc_info=True)
        _manejar_excepcion_api(e, api_provider, logPrefix,
                               locals().get('respuesta'))
        return None

def ejecutar_tarea_especifica_mision(tarea_info: dict, mision_markdown_completa: str, bloques_codigo_input: list, api_provider: str):
    """
    Paso 2 (Modo Granular): IA ejecuta una tarea específica de la misión, operando sobre bloques de código.
    Devuelve un JSON con una lista de operaciones de modificación.

    Args:
        tarea_info (dict): Diccionario con la información de la tarea actual (descripción, ID, etc.).
        mision_markdown_completa (str): Contenido completo del archivo Markdown de la misión, para contexto general.
        bloques_codigo_input (list): Lista de diccionarios, donde cada diccionario representa un bloque de código objetivo:
            [
                {
                    "ruta_archivo": "app/controlador.php",
                    "nombre_bloque": "procesarFormulario",
                    "linea_inicio_original": 45, 
                    "linea_fin_original": 82,   
                    "contenido_actual_bloque": "código actual del bloque..." 
                },
                # ... más bloques
            ]
        api_provider (str): Proveedor de API a utilizar ('google' o 'openrouter').

    Returns:
        dict: Un diccionario parseado desde el JSON de respuesta de la IA, con la estructura de operaciones de modificación,
              o None si hay un error.
    """
    logPrefix = f"ejecutar_tarea_especifica_mision (Paso 2 Granular/{api_provider.upper()}):"
    descripcion_tarea = tarea_info.get("descripcion", "Tarea no especificada")
    tarea_id = tarea_info.get("id", "ID_TAREA_DESCONOCIDO")
    log.info(f"{logPrefix} Ejecutando Tarea ID '{tarea_id}': '{descripcion_tarea}'")

    # Serializar los bloques de código para el prompt
    bloques_input_str_parts = ["\n--- BLOQUES DE CÓDIGO OBJETIVO (CON SU CONTENIDO ACTUAL Y LÍNEAS ORIGINALES) ---"]
    if bloques_codigo_input:
        for i, bloque in enumerate(bloques_codigo_input):
            bloques_input_str_parts.append(f"\n-- Bloque de Código #{i+1} --")
            bloques_input_str_parts.append(f"  Ruta Archivo: {bloque.get('ruta_archivo', 'N/A')}")
            bloques_input_str_parts.append(f"  Nombre Bloque: {bloque.get('nombre_bloque', 'N/A')}")
            bloques_input_str_parts.append(f"  Línea Inicio Original (en archivo completo): {bloque.get('linea_inicio_original', 'N/A')}")
            bloques_input_str_parts.append(f"  Línea Fin Original (en archivo completo): {bloque.get('linea_fin_original', 'N/A')}")
            bloques_input_str_parts.append(f"  Contenido Actual del Bloque:\n```\n{bloque.get('contenido_actual_bloque', '')}\n```")
    else:
        bloques_input_str_parts.append("(No se proporcionaron bloques de código específicos. La tarea podría ser crear un archivo nuevo o la información del bloque está implícita en la descripción de la tarea.)")
    bloques_input_serializados_str = "\n".join(bloques_input_str_parts)

    promptPartes = [
        "Eres un asistente de IA avanzado especializado en refactorización de código y ejecución de tareas de desarrollo precisas. Tu objetivo es aplicar los cambios solicitados en la tarea actual, operando sobre los bloques de código proporcionados o creando nuevo código según se especifique.",
        "Debes analizar la tarea, el contexto general de la misión y los bloques de código objetivo (con su contenido actual y metadatos como ruta y líneas originales en el archivo completo).",
        "Tu respuesta DEBE SER EXCLUSIVAMENTE un objeto JSON que describa una lista de operaciones de modificación.",

        "\n--- MISIÓN GENERAL (Contexto Global) ---",
        mision_markdown_completa,

        f"\n--- TAREA ESPECÍFICA A EJECUTAR (ID: {tarea_id}) ---",
        f"Descripción de la Tarea: {descripcion_tarea}",

        bloques_input_serializados_str, 

        "\n--- FORMATO DE RESPUESTA JSON REQUERIDO ---",
        "Responde ÚNICAMENTE con un objeto JSON VÁLIDO que tenga la siguiente estructura:",
        """
```json
{
  "modificaciones": [
    {
      "tipo_operacion": "REEMPLAZAR_BLOQUE",
      "ruta_archivo": "ruta/relativa/al/archivo.ext",
      "linea_inicio": 45,
      "linea_fin": 82,
      "nuevo_contenido": "/* ... nuevo código completo para el bloque procesarFormulario ... */"
    },
    {
      "tipo_operacion": "AGREGAR_BLOQUE",
      "ruta_archivo": "app/modelo.php",
      "insertar_despues_de_linea": 150,
      "nuevo_contenido": "  public function validarEmail($email) {\\n    // ... nueva lógica de validación ...\\n  }"
    },
    {
      "tipo_operacion": "ELIMINAR_BLOQUE",
      "ruta_archivo": "app/viejo_controlador.php",
      "linea_inicio": 10,
      "linea_fin": 25
    }
  ],
  "advertencia_ejecucion": null
}
```""",
        "REGLAS DETALLADAS PARA EL JSON DE RESPUESTA:",
        "1.  **`modificaciones`**: (Array de objetos) Una lista de operaciones. Puede estar vacía si no se realizan cambios y solo hay una `advertencia_ejecucion`.",
        "2.  **Objeto de Operación (dentro de `modificaciones`)**: Cada objeto debe tener:",
        "    a.  **`tipo_operacion`**: (String) Uno de: `REEMPLAZAR_BLOQUE`, `AGREGAR_BLOQUE`, `ELIMINAR_BLOQUE`.",
        "    b.  **`ruta_archivo`**: (String) Ruta relativa al archivo afectado (ej: `src/utils/helpers.js`).",
        "    c.  **Campos específicos por `tipo_operacion`**:",
        "        i.  **Si `tipo_operacion` es `REEMPLAZAR_BLOQUE`**: ",
        "            -   **`linea_inicio`**: (Integer) Número de línea (1-indexed) en el archivo original donde comienza el bloque a reemplazar. DEBE CORRESPONDER a `linea_inicio_original` del bloque que te pasaron, si estás reemplazando un bloque existente. **ESTE CAMPO ES OBLIGATORIO.**",
        "            -   **`linea_fin`**: (Integer) Número de línea (1-indexed) en el archivo original donde termina el bloque a reemplazar. DEBE CORRESPONDER a `linea_fin_original` del bloque que te pasaron. **ESTE CAMPO ES ABSOLUTAMENTE OBLIGATORIO. NO LO OMITAS BAJO NINGUNA CIRCUNSTANCIA PARA REEMPLAZAR_BLOQUE.**",
        "            -   **`nuevo_contenido`**: (String) El código completo que reemplazará el bloque original. Si el bloque es una función, debe ser la función completa. **ESTE CAMPO ES OBLIGATORIO.**",
        "               - Si la tarea es crear un archivo NUEVO, usa `REEMPLAZAR_BLOQUE` con `linea_inicio: 1`, `linea_fin: 1` (o 0, pero usa 1) y `nuevo_contenido` siendo el contenido completo del nuevo archivo. **TODOS LOS CAMPOS (`linea_inicio`, `linea_fin`, `nuevo_contenido`) SON OBLIGATORIOS IGUALMENTE.**",
        "        ii. **Si `tipo_operacion` es `AGREGAR_BLOQUE`**: ",
        "            -   **`insertar_despues_de_linea`**: (Integer) Número de línea (1-indexed) en el archivo original DESPUÉS de la cual se insertará el `nuevo_contenido`. Usa `0` para insertar al principio del archivo. **ESTE CAMPO ES OBLIGATORIO.**",
        "            -   **`nuevo_contenido`**: (String) El código completo del nuevo bloque a agregar. **ESTE CAMPO ES OBLIGATORIO.**",
        "        iii.**Si `tipo_operacion` es `ELIMINAR_BLOQUE`**: ",
        "            -   **`linea_inicio`**: (Integer) Número de línea (1-indexed) en el archivo original donde comienza el bloque a eliminar. DEBE CORRESPONDER a `linea_inicio_original` del bloque que te pasaron. **ESTE CAMPO ES OBLIGATORIO.**",
        "            -   **`linea_fin`**: (Integer) Número de línea (1-indexed) en el archivo original donde termina el bloque a eliminar. **ESTE CAMPO ES ABSOLUTAMENTE OBLIGATORIO. NO LO OMITAS BAJO NINGUNA CIRCUNSTANCIA PARA ELIMINAR_BLOQUE.**",
        "            -   El campo `nuevo_contenido` se ignora o puede ser `null` o `\"\"`.",
        "3.  **`advertencia_ejecucion`**: (String o Null) Si no puedes realizar la tarea de forma segura o si hay ambigüedades importantes, explica el problema aquí. Si todo está bien, usa `null`.",
        "4.  **IMPORTANTE SOBRE LÍNEAS**: Todas las referencias a `linea_inicio`, `linea_fin`, e `insertar_despues_de_linea` en TU RESPUESTA JSON deben ser números de línea relativos al ARCHIVO COMPLETO ORIGINAL, no a los fragmentos de `contenido_actual_bloque` que se te proporcionan. Usa los `linea_inicio_original` y `linea_fin_original` de los bloques de entrada como referencia para esto.",
        "5.  **CONTENIDO DEL CÓDIGO (`nuevo_contenido`)**: Debe ser un string JSON válido. Esto significa que los caracteres especiales DENTRO del código (como comillas dobles, barras invertidas, saltos de línea) DEBEN estar correctamente escapados (ej: `\\\"` para comilla doble, `\\\\` para barra invertida, `\\n` para salto de línea).",
        "6.  ** atomicidad**: Las operaciones deben ser lo más atómicas posible. Si una tarea implica múltiples cambios pequeños, genera múltiples objetos de operación en la lista `modificaciones`.",
        "7.  **Archivos Nuevos**: Si la tarea es crear un archivo nuevo, usa `REEMPLAZAR_BLOQUE` con `ruta_archivo` siendo la nueva ruta, `linea_inicio: 1`, `linea_fin: 1`, y `nuevo_contenido` con el contenido completo del archivo.",
        "No añadas explicaciones fuera del JSON. La única explicación permitida está en el campo `advertencia_ejecucion`."
    ]
    promptCompleto = "\n".join(promptPartes)

    textoRespuesta = None
    respuestaJson = None

    response_schema_granular = {
        'type': 'OBJECT',
        'properties': {
            'modificaciones': {
                'type': 'ARRAY',
                'items': {
                    'type': 'OBJECT',
                    'properties': {
                        'tipo_operacion': {'type': 'STRING', 'enum': ['REEMPLAZAR_BLOQUE', 'AGREGAR_BLOQUE', 'ELIMINAR_BLOQUE']},
                        'ruta_archivo': {'type': 'STRING'},
                        'linea_inicio': {'type': 'INTEGER', 'nullable': True},
                        'linea_fin': {'type': 'INTEGER', 'nullable': True},
                        'insertar_despues_de_linea': {'type': 'INTEGER', 'nullable': True},
                        'nuevo_contenido': {'type': 'STRING', 'nullable': True}
                    },
                    'required': ['tipo_operacion', 'ruta_archivo']
                }
            },
            'advertencia_ejecucion': {'type': 'STRING', 'nullable': True}
        },
        'required': ['modificaciones']
    }

    try:
        if api_provider == 'google':
            if not configurarGemini():
                return None
            modelo = genai.GenerativeModel(settings.MODELO_GOOGLE_GEMINI)
            
            generation_config_dict = {
                "temperature": 0.3, 
                "response_mime_type": "application/json",
                "max_output_tokens": settings.MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS if hasattr(settings, 'MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS') else 60000
            }
            generation_config_dict["response_schema"] = response_schema_granular
            log.debug(f"{logPrefix} Incluyendo response_schema granular en GenerationConfig para Gemini.")

            respuesta = modelo.generate_content(
                promptCompleto,
                generation_config=types.GenerationConfig(**generation_config_dict),
                safety_settings={'HATE': 'BLOCK_ONLY_HIGH', 'HARASSMENT': 'BLOCK_ONLY_HIGH',
                                 'SEXUAL': 'BLOCK_ONLY_HIGH', 'DANGEROUS': 'BLOCK_ONLY_HIGH'}
            )
            textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        elif api_provider == 'openrouter':
            if not settings.OPENROUTER_API_KEY:
                log.error(f"{logPrefix} Falta OPENROUTER_API_KEY.")
                return None
            client = OpenAI(base_url=settings.OPENROUTER_BASE_URL,
                            api_key=settings.OPENROUTER_API_KEY)
            mensajes = [{"role": "user", "content": promptCompleto}]
            completion = client.chat.completions.create(
                extra_headers={"HTTP-Referer": settings.OPENROUTER_REFERER,
                               "X-Title": settings.OPENROUTER_TITLE},
                model=settings.OPENROUTER_MODEL, messages=mensajes, temperature=0.3, 
                max_tokens=settings.MODELO_GOOGLE_GEMINI_MAX_OUTPUT_TOKENS, 
                timeout=API_TIMEOUT_SECONDS,
                response_format={"type": "json_object"} 
            )
            if completion.choices:
                textoRespuesta = completion.choices[0].message.content
        else:
            log.error(f"{logPrefix} Proveedor API '{api_provider}' no soportado.")
            return None

        if not textoRespuesta:
            log.error(f"{logPrefix} No se obtuvo texto de la IA.")
            return None

        respuestaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        if not respuestaJson:
            tokens_prompt_estimados_error = contarTokensTexto(promptCompleto, api_provider)
            return {"modificaciones": [], "advertencia_ejecucion": "Fallo al parsear JSON de la IA.", "tokens_consumidos_api": tokens_prompt_estimados_error }

        if "modificaciones" not in respuestaJson or not isinstance(respuestaJson["modificaciones"], list):
            log.error(f"{logPrefix} Respuesta JSON no tiene 'modificaciones' como lista o falta. Recibido: {respuestaJson}")
            adv = respuestaJson.get("advertencia_ejecucion", "Respuesta JSON no tiene 'modificaciones' como lista o falta.")
            if not isinstance(adv, str): adv = str(adv) 
            tokens_prompt_estimados_error = contarTokensTexto(promptCompleto, api_provider)
            return {"modificaciones": [], "advertencia_ejecucion": adv, "tokens_consumidos_api": tokens_prompt_estimados_error}

        for i, op in enumerate(respuestaJson["modificaciones"]):
            if not isinstance(op, dict) or "tipo_operacion" not in op or "ruta_archivo" not in op:
                log.error(f"{logPrefix} Operación de modificación inválida #{i+1}: {op}. Faltan campos clave (tipo_operacion o ruta_archivo).")
                tokens_prompt_estimados_error = contarTokensTexto(promptCompleto, api_provider)
                return {"modificaciones": [], "advertencia_ejecucion": f"Operación de modificación inválida #{i+1}: {op}. Faltan campos clave.", "tokens_consumidos_api": tokens_prompt_estimados_error}
            
            tipo_op = op.get("tipo_operacion")

            if tipo_op == "REEMPLAZAR_BLOQUE":
                if "linea_fin" not in op and "linea_inicio" in op:
                    op_linea_inicio = op.get("linea_inicio")
                    autocorregido_con_exito_desde_input = False

                    if isinstance(op_linea_inicio, int):
                        for bloque_in in bloques_codigo_input:
                            if bloque_in.get("ruta_archivo") == op.get("ruta_archivo") and \
                               bloque_in.get("linea_inicio_original") == op_linea_inicio and \
                               "linea_fin_original" in bloque_in:
                                op["linea_fin"] = bloque_in.get("linea_fin_original")
                                log.warning(f"{logPrefix} Operación REEMPLAZAR_BLOQUE #{i+1} en '{op.get('ruta_archivo')}' L{op_linea_inicio} no tenía 'linea_fin'. "
                                            f"Autocorregido a '{op['linea_fin']}' basado en el bloque de entrada original (L{bloque_in.get('linea_inicio_original')}-L{bloque_in.get('linea_fin_original')}).")
                                autocorregido_con_exito_desde_input = True
                                break
                        
                        if not autocorregido_con_exito_desde_input and op_linea_inicio == 1:
                            op["linea_fin"] = 1 
                            log.warning(f"{logPrefix} Operación REEMPLAZAR_BLOQUE #{i+1} en '{op.get('ruta_archivo')}' (potencial creación/L1) no tenía 'linea_fin'. "
                                        f"No se pudo inferir de un bloque de entrada exacto (o el bloque de entrada no tenía 'linea_fin_original'). Autocorregido 'linea_fin' a '1' como fallback.")
                            autocorregido_con_exito_desde_input = True
                        elif not autocorregido_con_exito_desde_input:
                            log.warning(f"{logPrefix} Operación REEMPLAZAR_BLOQUE #{i+1} en '{op.get('ruta_archivo')}' L{op_linea_inicio} no tenía 'linea_fin' y no se pudo inferir del bloque de entrada. "
                                        "Esto probablemente causará un error en la validación de campos faltantes.")
                    else:
                         log.warning(f"{logPrefix} Operación REEMPLAZAR_BLOQUE #{i+1} en '{op.get('ruta_archivo')}' no tenía 'linea_fin' y 'linea_inicio' ('{op_linea_inicio}') no es un entero válido. No se puede autocorregir.")
                
                campos_necesarios_reemplazar = ["linea_inicio", "linea_fin", "nuevo_contenido"]
                campos_faltantes = [k for k in campos_necesarios_reemplazar if k not in op]
                if campos_faltantes:
                    log.error(f"{logPrefix} Operación REEMPLAZAR_BLOQUE inválida #{i+1} en '{op.get('ruta_archivo')}': {op}. Faltan campos: {campos_faltantes} (post-autocorrección).")
                    tokens_prompt_estimados_error = contarTokensTexto(promptCompleto, api_provider)
                    return {"modificaciones": [], "advertencia_ejecucion": f"Operación REEMPLAZAR_BLOQUE inválida #{i+1} en '{op.get('ruta_archivo')}', faltan campos: {campos_faltantes}.", "tokens_consumidos_api": tokens_prompt_estimados_error}
            
            elif tipo_op == "AGREGAR_BLOQUE":
                campos_necesarios_agregar = ["insertar_despues_de_linea", "nuevo_contenido"]
                campos_faltantes = [k for k in campos_necesarios_agregar if k not in op]
                if campos_faltantes:
                    log.error(f"{logPrefix} Operación AGREGAR_BLOQUE inválida #{i+1}: {op}. Faltan campos: {campos_faltantes}.")
                    tokens_prompt_estimados_error = contarTokensTexto(promptCompleto, api_provider)
                    return {"modificaciones": [], "advertencia_ejecucion": f"Operación AGREGAR_BLOQUE inválida #{i+1}, faltan campos: {campos_faltantes}.", "tokens_consumidos_api": tokens_prompt_estimados_error}
            
            elif tipo_op == "ELIMINAR_BLOQUE":
                if "linea_fin" not in op and "linea_inicio" in op: 
                    autocorregido_linea_fin_eliminar = False
                    op_linea_inicio = op.get("linea_inicio")
                    if isinstance(op_linea_inicio, int): 
                        for bloque_in in bloques_codigo_input:
                            if bloque_in.get("ruta_archivo") == op.get("ruta_archivo") and \
                               bloque_in.get("linea_inicio_original") == op_linea_inicio and \
                               "linea_fin_original" in bloque_in:
                                op["linea_fin"] = bloque_in.get("linea_fin_original")
                                log.warning(f"{logPrefix} Operación ELIMINAR_BLOQUE #{i+1} en '{op.get('ruta_archivo')}' L{op_linea_inicio} no tenía 'linea_fin'. "
                                            f"Autocorregido a '{op['linea_fin']}' basado en el bloque de entrada original (L{bloque_in.get('linea_inicio_original')}-L{bloque_in.get('linea_fin_original')}).")
                                autocorregido_linea_fin_eliminar = True
                                break
                        if not autocorregido_linea_fin_eliminar:
                             log.warning(f"{logPrefix} Operación ELIMINAR_BLOQUE #{i+1} en '{op.get('ruta_archivo')}' L{op_linea_inicio} no tenía 'linea_fin' y no se pudo inferir del bloque de entrada. Esto probablemente causará un error.")
                
                campos_necesarios_eliminar = ["linea_inicio", "linea_fin"]
                campos_faltantes = [k for k in campos_necesarios_eliminar if k not in op]
                if campos_faltantes:
                    log.error(f"{logPrefix} Operación ELIMINAR_BLOQUE inválida #{i+1} en '{op.get('ruta_archivo')}': {op}. Faltan campos: {campos_faltantes} (post-autocorrección).")
                    tokens_prompt_estimados_error = contarTokensTexto(promptCompleto, api_provider)
                    return {"modificaciones": [], "advertencia_ejecucion": f"Operación ELIMINAR_BLOQUE inválida #{i+1} en '{op.get('ruta_archivo')}', faltan campos: {campos_faltantes}.", "tokens_consumidos_api": tokens_prompt_estimados_error}
            
            elif tipo_op is None:
                 log.error(f"{logPrefix} Operación inválida #{i+1}: 'tipo_operacion' es None o no está. Operación: {op}")
                 tokens_prompt_estimados_error = contarTokensTexto(promptCompleto, api_provider)
                 return {"modificaciones": [], "advertencia_ejecucion": f"Operación inválida #{i+1}, 'tipo_operacion' es None o falta.", "tokens_consumidos_api": tokens_prompt_estimados_error}

        num_modificaciones = len(respuestaJson["modificaciones"])
        adv = respuestaJson.get("advertencia_ejecucion")
        log.info(f"{logPrefix} Ejecución de tarea completada por IA. Modificaciones: {num_modificaciones}. Advertencia: {adv if adv else 'Ninguna'}")
        
        tokens_prompt = contarTokensTexto(promptCompleto, api_provider)
        tokens_respuesta_estimados = contarTokensTexto(json.dumps(respuestaJson), api_provider)
        respuestaJson["tokens_consumidos_api"] = tokens_prompt + tokens_respuesta_estimados 
        
        return respuestaJson

    except Exception as e:
        log.error(f"{logPrefix} Error en ejecución de tarea específica (granular): {e}", exc_info=True)
        _manejar_excepcion_api(e, api_provider, logPrefix, locals().get('respuesta'))
        tokens_prompt = contarTokensTexto(promptCompleto, api_provider)
        return {"modificaciones": [], 
                "advertencia_ejecucion": f"Error interno procesando la tarea: {str(e)}",
                "tokens_consumidos_api": tokens_prompt }

# --- Funciones de Ayuda Internas (ya existen en el original, asegurarse de que estén completas) ---
def _extraerTextoRespuesta(respuesta, logPrefix):
    textoRespuesta = ""
    try:
        # Priorizar el atributo 'text' si existe directamente en la respuesta (Gemini V1 Pro)
        if hasattr(respuesta, 'text') and respuesta.text:
            textoRespuesta = respuesta.text
        # Estructura de Gemini V1.5 (candidates -> content -> parts)
        elif hasattr(respuesta, 'candidates') and respuesta.candidates:
            candidate = respuesta.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts') and candidate.content.parts:
                textoRespuesta = "".join(
                    part.text for part in candidate.content.parts if hasattr(part, 'text'))
            # Fallback por si 'content' no tiene 'parts' pero sí 'text' (menos común)
            elif hasattr(candidate, 'content') and hasattr(candidate.content, 'text') and candidate.content.text:
                textoRespuesta = candidate.content.text
        # Estructura más antigua de Gemini (parts directamente en la respuesta)
        elif hasattr(respuesta, 'parts') and respuesta.parts:
            textoRespuesta = "".join(
                part.text for part in respuesta.parts if hasattr(part, 'text'))

        if not textoRespuesta:
            finish_reason_str = "N/A"
            safety_ratings_str = "N/A"
            block_reason_str = "N/A"

            if hasattr(respuesta, 'prompt_feedback'):
                feedback = respuesta.prompt_feedback
                if hasattr(feedback, 'block_reason'):
                    block_reason_str = str(feedback.block_reason)
                if hasattr(feedback, 'safety_ratings'):  # Lista de SafetyRating
                    safety_ratings_str = ", ".join(
                        [f"{r.category}: {r.probability}" for r in feedback.safety_ratings])

            if hasattr(respuesta, 'candidates') and isinstance(respuesta.candidates, (list, tuple)) and respuesta.candidates:
                candidate = respuesta.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    finish_reason_str = str(candidate.finish_reason)
                # Lista de SafetyRating
                if hasattr(candidate, 'safety_ratings') and safety_ratings_str == "N/A":
                    safety_ratings_str = ", ".join(
                        [f"{r.category}: {r.probability}" for r in candidate.safety_ratings])

            log.error(f"{logPrefix} Respuesta de IA vacía o no se pudo extraer texto. "
                      f"FinishReason: {finish_reason_str}, BlockReason: {block_reason_str}, SafetyRatings: {safety_ratings_str}")
            log.debug(f"{logPrefix} Respuesta completa (objeto): {respuesta}")
            return None

        return textoRespuesta.strip()

    except (AttributeError, IndexError, ValueError, TypeError) as e:
        log.error(
            f"{logPrefix} Error extrayendo texto de la respuesta: {e}. Respuesta obj: {respuesta}", exc_info=True)
        return None
    except Exception as e:  # Captura general para errores inesperados
        log.error(
            f"{logPrefix} Error inesperado extrayendo texto: {e}. Respuesta obj: {respuesta}", exc_info=True)
        return None


def _limpiarYParsearJson(textoRespuesta, logPrefix):
    # Para asegurar que 'log' exista si no está definido globalmente, 
    # podrías pasarlo como argumento o instanciar uno básico aquí.
    # Por simplicidad, se asume que 'log' ya está configurado y disponible.
    # Ejemplo de fallback si no estuviera disponible:
    # log_temp = logging.getLogger(f"{__name__}._limpiarYParsearJson")
    # if not hasattr(log_temp, 'debug'): # Una forma simple de chequear si ya está configurado
    #     logging.basicConfig(level=logging.INFO) # Configuración básica
    # log = log_temp # Usar log local si no hay uno global

    if not textoRespuesta: # Manejar caso de textoRespuesta vacío o None tempranamente
        log.error(f"{logPrefix} No se recibió texto de respuesta de la IA (None o vacío).")
        return None

    log.debug(f"{logPrefix} Respuesta cruda de IA (antes de cualquier limpieza/parseo):\n{textoRespuesta}")

    textoLimpio = textoRespuesta.strip()

    # Quitar ```json ... ``` o ``` ... ``` si existen
    if textoLimpio.startswith("```"):
        first_newline = textoLimpio.find('\n')
        if first_newline != -1:
            first_line_marker = textoLimpio[:first_newline].strip()
            if first_line_marker == "```json" or first_line_marker == "```":
                textoLimpio = textoLimpio[first_newline + 1:]
        if textoLimpio.endswith("```"):
            textoLimpio = textoLimpio[:-3].strip()

    start_brace = textoLimpio.find('{')
    end_brace = textoLimpio.rfind('}')

    if start_brace == -1 or end_brace == -1 or start_brace >= end_brace:
        log.error(
            f"{logPrefix} Respuesta de IA no parece contener un bloque JSON válido {{...}}. Respuesta (limpia inicial): {textoLimpio[:500]}...")
        # El log de la respuesta original ya se hizo arriba.
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
        contexto_inicio_error = max(0, e.pos - 150)
        contexto_fin_error = min(len(json_candidate), e.pos + 150)
        contexto_error_str = json_candidate[contexto_inicio_error:contexto_fin_error]
        contexto_error_repr = repr(contexto_error_str)

        log.error(
            f"{logPrefix} Error crítico parseando JSON de IA: {e.msg} (char {e.pos})")
        log.error(
            f"{logPrefix} Contexto alrededor del error ({contexto_inicio_error}-{contexto_fin_error}):\n{contexto_error_repr}")

        if len(json_candidate) > 2000:
            log.debug(
                f"{logPrefix} JSON Candidato que falló (Inicio - 1000 chars):\n{json_candidate[:1000]}...")
            log.debug(
                f"{logPrefix} JSON Candidato que falló (Fin - 1000 chars):...{json_candidate[-1000:]}")
        else:
            log.debug(
                f"{logPrefix} JSON Candidato Completo que falló:\n{json_candidate}")
        # El log de la respuesta original ya se hizo arriba.
        return None
    except Exception as e_general_parse:
        log.error(
            f"{logPrefix} Error inesperado durante json.loads: {e_general_parse}", exc_info=True)
        log.debug(f"{logPrefix} JSON Candidato que falló (por error general):\n{json_candidate}")
        # El log de la respuesta original ya se hizo arriba.
        return None
    
def _manejar_excepcion_api(e, api_provider, logPrefix, respuesta_api=None):
    """Función helper centralizada para manejar excepciones de API."""
    if api_provider == 'google':
        _manejarExcepcionGemini(e, logPrefix, respuesta_api)
    elif api_provider == 'openrouter':
        if isinstance(e, APIError):  # Específico de la librería OpenAI
            if "timeout" in str(e).lower() or (hasattr(e, 'code') and e.code == 'ETIMEDOUT'):
                log.error(
                    f"{logPrefix} Error de TIMEOUT ({API_TIMEOUT_SECONDS}s) en API OpenRouter: {e}", exc_info=True)
            else:
                log.error(
                    f"{logPrefix} Error API OpenRouter (OpenAI lib): {e}", exc_info=True)
        else:  # Excepciones genéricas
            log.error(
                f"{logPrefix} Error inesperado con OpenRouter: {type(e).__name__} - {e}", exc_info=True)
    else:
        log.error(
            f"{logPrefix} Error inesperado con proveedor API desconocido '{api_provider}': {type(e).__name__} - {e}", exc_info=True)


def _manejarExcepcionGemini(e, logPrefix, respuesta=None):
    # (Como en el original, pero asegurándose de que los tipos de excepción sean correctos para la v de la API)
    # Ejemplo: google.api_core.exceptions.InvalidArgument, etc.
    # La versión actual de google.generativeai usa excepciones más directas a veces.

    if isinstance(e, google.api_core.exceptions.ResourceExhausted):  # Límite de cuota
        log.error(
            f"{logPrefix} Error de CUOTA API Google Gemini (ResourceExhausted): {e}")
    # Prompt inválido, contenido bloqueado
    elif isinstance(e, google.api_core.exceptions.InvalidArgument):
        log.error(f"{logPrefix} Error de ARGUMENTO INVÁLIDO API Google Gemini (InvalidArgument): {e}. ¿Prompt mal formado, JSON no generable, o contenido bloqueado?", exc_info=True)
    elif isinstance(e, google.api_core.exceptions.PermissionDenied):  # API Key
        log.error(
            f"{logPrefix} Error de PERMISO API Google Gemini (PermissionDenied): {e}. ¿API Key incorrecta o sin permisos?")
    # Error temporal del servicio
    elif isinstance(e, google.api_core.exceptions.ServiceUnavailable):
        log.error(
            f"{logPrefix} Error SERVICIO NO DISPONIBLE API Google Gemini (ServiceUnavailable): {e}. Reintentar más tarde.")

    # Excepciones específicas de la librería google-generativeai (pueden no heredar de google.api_core)
    # type(e).__name__ es un fallback útil.
    elif type(e).__name__ in ['BlockedPromptException', 'StopCandidateException', 'ResponseBlockedError', 'GenerationStoppedException']:
        log.error(
            f"{logPrefix} Prompt bloqueado o generación detenida/bloqueada por Google Gemini: {type(e).__name__} - {e}")
        finish_reason = "Desconocida"
        safety_ratings_str = "No disponibles"
        block_reason_str = "No disponible"

        if respuesta:  # 'respuesta' es el objeto devuelto por `model.generate_content()`
            if hasattr(respuesta, 'prompt_feedback') and respuesta.prompt_feedback:
                feedback = respuesta.prompt_feedback
                if hasattr(feedback, 'block_reason'):  # Enum BlockReason
                    # Acceder al nombre del enum
                    block_reason_str = str(feedback.block_reason.name)
                if hasattr(feedback, 'safety_ratings'):  # Lista de SafetyRating
                    safety_ratings_str = ", ".join(
                        [f"{r.category.name}: {r.probability.name}" for r in feedback.safety_ratings])

            if hasattr(respuesta, 'candidates') and respuesta.candidates:
                try:
                    candidate = respuesta.candidates[0]
                    if hasattr(candidate, 'finish_reason'):  # Enum FinishReason
                        finish_reason = str(candidate.finish_reason.name)
                    # Lista de SafetyRating
                    if hasattr(candidate, 'safety_ratings') and not safety_ratings_str:
                        safety_ratings_str = ", ".join(
                            [f"{r.category.name}: {r.probability.name}" for r in candidate.safety_ratings])
                except (IndexError, AttributeError):
                    log.debug(
                        f"{logPrefix} No se pudo extraer finish_reason/safety_ratings del candidato (posiblemente bloqueado antes).")

        log.error(f"{logPrefix} Detalles (Gemini): FinishReason: {finish_reason}, BlockReason: {block_reason_str}, SafetyRatings: {safety_ratings_str}")

    else:  # Otras excepciones de google.api_core o genéricas
        log.error(
            f"{logPrefix} Error inesperado en llamada API Google Gemini: {type(e).__name__} - {e}", exc_info=True)
        if respuesta and hasattr(respuesta, 'prompt_feedback'):
            try:
                log.debug(
                    f"{logPrefix} Prompt Feedback (si disponible): {respuesta.prompt_feedback}")
            except Exception:
                pass

def _inyectar_numeros_linea(contenido_codigo: str) -> str:
    """
    Toma el contenido de un archivo de código y le antepone un número de línea a cada línea.
    Ejemplo: 'def func():\\n    pass' -> '1: def func():\\n2:     pass'
    """
    if not contenido_codigo:
        return ""
    
    lineas = contenido_codigo.splitlines()
    lineas_numeradas = [f"{i+1}: {linea}" for i, linea in enumerate(lineas)]
    return "\n".join(lineas_numeradas)
