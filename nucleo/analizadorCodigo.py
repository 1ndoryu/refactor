# nucleo/analizadorCodigo.py
import os
import logging
import json
import google.generativeai as genai
import google.api_core.exceptions
from config import settings
# Quita la importación específica de types si ya no la usas para Schema
# from google.generativeai import types

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

def generarEstructuraDirectorio(ruta_base, directorios_ignorados=None, max_depth=8, incluir_archivos=True, indent_char="    "):
    """
    Genera una representación de cadena formateada de la estructura de directorios.

    Args:
        ruta_base (str): Ruta al directorio raíz del proyecto.
        directorios_ignorados (set, optional): Conjunto de nombres de directorios a ignorar.
        max_depth (int, optional): Profundidad máxima a explorar.
        incluir_archivos (bool, optional): Si incluir archivos en la estructura.
        indent_char (str, optional): Caracteres a usar para la indentación.

    Returns:
        str: Cadena formateada con la estructura, o None en caso de error.
    """
    logPrefix = "generarEstructuraDirectorio:"
    if not os.path.isdir(ruta_base):
        log.error(f"{logPrefix} La ruta base '{ruta_base}' no es un directorio válido.")
        return None

    if directorios_ignorados is None:
        directorios_ignorados = set()
    else:
        directorios_ignorados = set(directorios_ignorados) # Asegurar que sea set

    estructura_lines = [os.path.basename(ruta_base) + "/"]
    processed_paths = set() # Para detectar posibles bucles de enlaces simbólicos

    def _walk_recursive(current_path, depth, prefix=""):
        if depth > max_depth:
            if depth == max_depth + 1: # Mostrar solo una vez por rama
                 estructura_lines.append(prefix + "└── ... (Profundidad máxima alcanzada)")
            return

        # Normalizar y comprobar si ya se procesó para evitar bucles
        real_path = os.path.realpath(current_path)
        if real_path in processed_paths:
            estructura_lines.append(prefix + f"└── -> ... (Enlace circular o repetido a {os.path.basename(real_path)})")
            return
        processed_paths.add(real_path)

        try:
            # Obtener entradas, manejar errores de permisos
            entries = sorted(os.listdir(current_path))
        except OSError as e:
            estructura_lines.append(prefix + f"└── [Error al listar: {e.strerror}]")
            return

        # Filtrar directorios y archivos
        items = []
        for entry in entries:
            # Ignorar ocultos y los especificados
            if entry.startswith('.') or entry in directorios_ignorados:
                continue

            entry_path = os.path.join(current_path, entry)
            is_dir = False
            try: # Comprobar si es directorio (manejar enlaces rotos)
                 is_dir = os.path.isdir(entry_path)
            except OSError:
                 continue # Ignorar enlaces rotos u otros errores

            if is_dir:
                items.append({'name': entry, 'is_dir': True, 'path': entry_path})
            elif incluir_archivos and os.path.isfile(entry_path):
                 items.append({'name': entry, 'is_dir': False, 'path': entry_path})

        count = len(items)
        for i, item in enumerate(items):
            is_last = (i == count - 1)
            connector = "└── " if is_last else "├── "
            line_prefix = prefix + connector

            if item['is_dir']:
                estructura_lines.append(line_prefix + item['name'] + "/")
                # Preparar prefijo para el siguiente nivel
                new_prefix = prefix + (indent_char if is_last else "│" + indent_char[1:]) # Usar "│" si no es el último
                _walk_recursive(item['path'], depth + 1, new_prefix)
            else: # Es archivo
                estructura_lines.append(line_prefix + item['name'])

    try:
        # Iniciar la recursión
        _walk_recursive(ruta_base, 0)
        log.info(f"{logPrefix} Estructura de directorios generada para '{ruta_base}' (hasta {max_depth} niveles).")
        return "\n".join(estructura_lines)
    except Exception as e:
         log.error(f"{logPrefix} Error inesperado generando estructura: {e}", exc_info=True)
         return None


# --- Modificar la firma y el prompt de obtenerDecisionRefactor ---

# <<< MODIFICADO: Añadir parámetro 'estructura_proyecto_texto' >>>
def obtenerDecisionRefactor(contextoCodigoCompleto, historialCambiosTexto=None, estructura_proyecto_texto=None):
    """
    PASO 1: Analiza código COMPLETO, **estructura del proyecto** e historial para DECIDIR una acción DETALLADA.
    Retorna JSON con ACCIÓN, PARÁMETROS ESPECÍFICOS, RAZONAMIENTO y ARCHIVOS RELEVANTES.
    Utiliza el modo JSON de Gemini.
    """
    logPrefix = "obtenerDecisionRefactor (Paso 1):"
    if not configurarGemini():
        return None
    if not contextoCodigoCompleto:
        # Permitir continuar si solo se tiene la estructura (aunque es raro)
        log.warning(f"{logPrefix} No se proporcionó contexto de código, se usará solo la estructura y el historial si existen.")
        # return None # Opcional: hacer que falle si no hay código
    if not contextoCodigoCompleto and not estructura_proyecto_texto:
         log.error(f"{logPrefix} No se proporcionó ni contexto de código ni estructura del proyecto.")
         return None


    nombreModelo = settings.MODELOGEMINI
    try:
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{logPrefix} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(
            f"{logPrefix} Error inicializando modelo '{nombreModelo}': {e}")
        return None

    # ### MODIFICADO ### Prompt ajustado para incluir la estructura
    promptPartes = []
    # Instrucciones generales (enfatizar uso de estructura)
    promptPartes.append("Eres un asistente experto en refactorización de código PHP/JS (WordPress). Tu tarea es analizar TODO el código fuente, **la estructura del proyecto** y el historial, y proponer UNA ÚNICA acción de refactorización PEQUEÑA, SEGURA y ATÓMICA. Es importante que seas detallado con la informacion que generas para que el segundo agente que realiza la accion sepa exactamente que hacer. La organización primero y dejeramos para el final la seguridad, el proyecto carece de arquitectura y todo esta muy desordenado, hay que ordenar primero.")
    promptPartes.append("Prioriza: eliminar código muerto, simplificar lógica compleja, añadir validaciones FALTANTES y básicas de seguridad, **mejorar la organización del código (mover funciones/clases a archivos/directorios más apropiados basándote en la estructura proporcionada)**, reducir duplicación, mejorar legibilidad (nombres en español `camelCase`). EVITA cambios masivos o reestructuraciones grandes. **La estructura del proyecto es desordenada; usa la información estructural para proponer movimientos lógicos y crear directorios si es necesario para agrupar funcionalidades relacionadas (ej: `app/Helpers/`, `app/Utils/`, `app/Services/`).** No es importante ni necesario que agregues nuevos comentarios a funciones viejas para explicar lo que hacen. Puedes hacer mejoras de optimización, seguridad, simplificación sin arriesgarte a que el codigo falle.")
    promptPartes.append(
        "Considera el historial para NO repetir errores, NO deshacer trabajo anterior y mantener la consistencia.")
    promptPartes.append(
        "A veces cometes el error de eliminar archivos que no estan vacíos, no se por qué pero no pidas eliminar algo si realmente no esta vacío.")
    promptPartes.append(
        "Archivos pequeños con funciones especificas es mucho mejor que archivos grandes con muchas funciones.")

    

    # Reglas JSON (sin cambios necesarios aquí, pero deben ser respetadas)
    promptPartes.append(
        "\n--- REGLAS ESTRICTAS PARA LA ESTRUCTURA JSON DE TU RESPUESTA (DECISIÓN) ---")
    promptPartes.append("1.  **`accion_propuesta`**: Elige UNA de: `mover_funcion`, `mover_clase`, `modificar_codigo_en_archivo`, `crear_archivo`, `eliminar_archivo`, `crear_directorio`. Si NINGUNA acción es segura/útil/necesaria, USA `no_accion`.")
    promptPartes.append(
        "2.  **`descripcion`**: Sé MUY específico para un mensaje de commit útil (ej: 'Refactor(Seguridad): Añade isset() a $_GET['param'] en archivo.php', 'Refactor(Clean): Elimina función duplicada viejaFuncion() de utils_old.php', 'Refactor(Org): Mueve función auxiliar miHelper() de main.php a app/Helpers/uiHelper.php', 'Refactor(Org): Crea directorio app/Http/Controllers').") # Ejemplo de crear dir
    promptPartes.append(
        "3.  **`parametros_accion`**: Objeto JSON con TODA la información necesaria para ejecutar el cambio SIN DUDAS. Usa rutas RELATIVAS desde la raíz del proyecto.")
    promptPartes.append(
        "    -   `mover_funcion`/`mover_clase`: `archivo_origen`, `archivo_destino`, `nombre_funcion`/`nombre_clase`, `eliminar_de_origen` (boolean). ¡Asegúrate que `archivo_destino` sea una ruta válida según la estructura!")
    promptPartes.append("    -   `modificar_codigo_en_archivo`: `archivo`, `descripcion_del_cambio_interno` (MUY detallado: 'Eliminar bloque if comentado entre lineas 80-95', 'Reemplazar bucle for en linea 120 por array_map', 'Añadir `global $wpdb;` al inicio de la función `miQuery()` en linea 30', 'Borrar la declaración completa de la función `funcionObsoleta(arg1)`'). NO incluyas el código aquí.")
    promptPartes.append(
        "    -   `crear_archivo`: `archivo` (ruta completa relativa, ej: 'app/Helpers/stringUtils.php'), `proposito_del_archivo` (breve, ej: 'Funciones auxiliares para manejo de cadenas').")
    promptPartes.append(
        "    -   `eliminar_archivo`: `archivo` (ruta relativa). Asegúrate de que sea seguro eliminarlo (ej: no usado en otros sitios).")
    promptPartes.append(
        "    -   `crear_directorio`: `directorio` (ruta relativa, ej: 'app/Interfaces').")
    promptPartes.append(
        "4.  **`archivos_relevantes`**: Lista de strings [ruta1, ruta2, ...] con **TODAS** las rutas relativas de archivos que el Paso 2 NECESITARÁ LEER para *generar el código modificado*. ¡CRUCIAL y preciso! (Ej: si mueves función de A a B, incluye [A, B]). Si creas directorio, puede ser []. Si creas archivo nuevo, puede ser [].")
    promptPartes.append(
        "5.  **`razonamiento`**: String justificando CLARAMENTE el *por qué* de esta acción (ej: 'Mejora la organización agrupando helpers', 'Elimina código no utilizado', 'Necesario para nueva estructura MVC') o la razón específica para `no_accion`.")
    promptPartes.append(
        "6.  **`tipo_analisis`**: Incluye siempre el campo `tipo_analisis` con el valor fijo `\"refactor_decision\"`.")
    promptPartes.append(
        "7. Evita las tareas de legibilidad, no son importantes, no es importante agregar comentarios Añade comentario phpDoc descriptivo o cosas asi.")
    promptPartes.append(
        "8. No uses namespace, por favor no importa que parezca una decisión optima, no usaremos namespace en este proyecto, aqui todos los archivos estan al alcance global para que sea mas facil mover cosas."
    )
    promptPartes.append(
        "9. Si vas a mover algo, asegurate de indicar correctamente a donde se tiene que mover o si se tiene que crear un nuevo archivo para ello."
    )
    promptPartes.append(
        "10. Si vas a eliminar algo porque un archivo esta vacío, asegurate de que realmente este vacío."
    )
    

    # <<< NUEVO: Añadir la estructura del proyecto al prompt >>>
    if estructura_proyecto_texto:
        promptPartes.append("\n--- ESTRUCTURA ACTUAL DEL PROYECTO (Visión Global) ---")
        promptPartes.append("# Nota: Esta estructura puede estar limitada en profundidad.")
        promptPartes.append(estructura_proyecto_texto)
        promptPartes.append("--- FIN ESTRUCTURA ---")
    else:
        # Incluir placeholder si no se pudo generar
        promptPartes.append("\n(No se proporcionó la estructura del proyecto)")


    if historialCambiosTexto:
        promptPartes.append(
            "\n--- HISTORIAL DE CAMBIOS RECIENTES (para tu contexto, EVITA REPETIR o deshacer) ---")
        promptPartes.append(historialCambiosTexto)
        promptPartes.append("--- FIN HISTORIAL ---")

    promptPartes.append("\n--- CÓDIGO FUENTE COMPLETO A ANALIZAR ---")
    # Añadir placeholder si no hay código pero sí estructura
    promptPartes.append(contextoCodigoCompleto if contextoCodigoCompleto else "(No se proporcionó código fuente completo, analiza basado en estructura e historial)")
    promptPartes.append("--- FIN CÓDIGO ---")

    promptPartes.append(
        "\nRecuerda: Responde ÚNICAMENTE con el objeto JSON que cumple TODAS las reglas anteriores, **considerando la estructura del proyecto proporcionada para decisiones de organización.**")

    promptCompleto = "\n".join(promptPartes)
    log.info(f"{logPrefix} Enviando solicitud de DECISIÓN a Gemini (MODO JSON)...")
    # Considera loguear solo partes del prompt si es muy grande
    # log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:500]}...")
    # log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-500:]}")
    if estructura_proyecto_texto:
         log.debug(f"{logPrefix} Estructura enviada en prompt (primeras líneas):\n{estructura_proyecto_texto[:500]}...")


    # ... (resto de la lógica para llamar a Gemini y procesar la respuesta sin cambios) ...
    try:
        # ... (llamada a modelo.generate_content) ...
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(
                temperature=0.4,
                response_mime_type="application/json",
                max_output_tokens=8192 # Ajusta si necesitas respuestas más largas (cuidado con límites)
            ),
             # Ajusta safety si es necesario, pero cuidado con bloqueos
            safety_settings={
                'HATE': 'BLOCK_MEDIUM_AND_ABOVE', # O BLOCK_ONLY_HIGH si tienes problemas
                'HARASSMENT': 'BLOCK_MEDIUM_AND_ABOVE',
                'SEXUAL': 'BLOCK_MEDIUM_AND_ABOVE',
                'DANGEROUS': 'BLOCK_MEDIUM_AND_ABOVE'
            }
        )
        # ... (procesar respuesta, _extraerTextoRespuesta, _limpiarYParsearJson) ...
        log.info(f"{logPrefix} Respuesta de DECISIÓN (MODO JSON) recibida.")
        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta:
            return None
        log.debug(f"{logPrefix} Texto crudo recibido de Gemini (antes de parsear JSON):\n{textoRespuesta}")
        sugerenciaJson = _limpiarYParsearJson(textoRespuesta, logPrefix)
        # ... (validación básica y logueo del JSON) ...
        if sugerenciaJson is None:
             log.error(f"{logPrefix} El parseo/extracción final de JSON falló.")
             return None
        if sugerenciaJson.get("tipo_analisis") != "refactor_decision":
             log.error(f"{logPrefix} Respuesta JSON no es del tipo esperado 'refactor_decision'.")
             try:
                 log.error(f"{logPrefix} JSON Recibido:\n{json.dumps(sugerenciaJson, indent=2, ensure_ascii=False)}")
             except Exception:
                 log.error(f"{logPrefix} JSON Recibido (no se pudo formatear): {sugerenciaJson}")
             return None
        log.info(f"{logPrefix} JSON de Decisión Generado:\n{json.dumps(sugerenciaJson, indent=2, ensure_ascii=False)}")
        return sugerenciaJson

    # ... (manejo de excepciones igual) ...
    except google.api_core.exceptions.InvalidArgument as e_inv:
         # Loguear más detalles si es posible
        log.error(f"{logPrefix} Error InvalidArgument durante la generación JSON: {e_inv}. ¿Prompt inválido, contenido bloqueado o problema generando JSON? Verifica las safety settings y el tamaño del prompt/respuesta.", exc_info=True)
        _manejarExcepcionGemini(e_inv, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None
    except Exception as e:
        _manejarExcepcionGemini(e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None


# --- PASO 2: Ejecutar Acción (Modificado para Logging) ---
def ejecutarAccionConGemini(decisionParseada, contextoCodigoReducido):
    logPrefix = "ejecutarAccionConGemini (Paso 2):"
    if not configurarGemini():
        return None
    if not decisionParseada:
        log.error(f"{logPrefix} No se proporcionó la decisión del Paso 1.")
        return None

    nombreModelo = settings.MODELOGEMINI
    try:
        modelo = genai.GenerativeModel(nombreModelo)
        log.info(f"{logPrefix} Usando modelo Gemini: {nombreModelo}")
    except Exception as e:
        log.error(
            f"{logPrefix} Error inicializando modelo '{nombreModelo}': {e}")
        return None

    # --- Construye el Prompt (AJUSTADO PARA ÉNFASIS EN ESCAPADO) ---
    accion = decisionParseada.get("accion_propuesta")
    descripcion = decisionParseada.get("descripcion")
    params = decisionParseada.get("parametros_accion", {})
    razonamiento_paso1 = decisionParseada.get("razonamiento")

    promptPartes = []
    promptPartes.append(
        "Eres un asistente de refactorización que EJECUTA una decisión ya tomada (la decisiones se toman de forma automatica por otro agente gemini IA).")
    promptPartes.append("**FORMATO DE COMENTARIOS O CODIGO CON SALTO DE LINEAS:** Si generas comentarios multilínea que usan `//` (PHP/JS), ASEGÚRATE de que **CADA LÍNEA** del comentario comience con `//` dentro del código generado.")
    promptPartes.append(
        "1. No uses namespace, aqui todos los archivos estan al alcance global para que sea mas facil mover cosas, si se te pide usarlos o hacerlos, fue un error, decide no hacer nada si te causa confusión una decisión y regresa el codigo igual sin cambiar nada."
    )
    promptPartes.append(
        "2. Si vas a mover algo, segurate de que realmente se esta moviendo algo, asegurate de tener el contexto necesario para mover lo que se te pide a los archivos indicados, si la decisión parece erronea, mejor no hagas nada y regresa el codigo igual sin cambiar nada."
    )
    promptPartes.append(
        "3. Si vas a eliminar algo porque un archivo esta vacío, asegurate de que realmente este vacío, el anterior agente puede cometer el error de pedir eliminar un archivo supuestamente vacío pero a veces no lo esta, mejor no hagas nada si la decisión parece confusa y regresa el codigo igual sin cambiar nada.."
    )
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

    # --- INICIO: ÉNFASIS EN JSON Y ESCAPADO ---
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
    // Si la acción es eliminar_archivo o crear_directorio, este objeto debe estar vacío: {}
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
    promptPartes.append(
        "8.  **SIN CONTENIDO:** Si la acción es `eliminar_archivo` o `crear_directorio`, el objeto `archivos_modificados` debe ser exactamente `{}`, es decir, un objeto JSON vacío, hay una excepción, si la solicitud dice elimiar un archivo vacío y no esta vacío, entonces no hagas nada, mejor no hagas nada si la decisión parece confusa, regresa el json completo sin cambiar nada del archivo, esto porque el agente anterior a veces comete el error de creer que el archivo esta vacío pero no lo esta, esto es importante por favor, evita ese error de borrar archivos vacíos que no estan vacíos (al menos que tengan comentarios o cosas nulas es justificable borrarlo).")
    promptPartes.append(
        "10. **VALIDACIÓN CRÍTICA DE STRINGS JSON PARA CÓDIGO:** Al incluir contenido de archivos (especialmente código fuente PHP, JS, etc.) dentro de un string JSON (ej: en la clave 'archivos_modificados'), es **absolutamente esencial** que ese string sea JSON válido y completo. \n"
        "    - **ESCAPA CORRECTAMENTE:** Todas las comillas dobles (`\"`) dentro del código deben escaparse como `\\\"`. Todas las barras invertidas (`\\`) deben escaparse como `\\\\`. Los saltos de línea literales deben representarse como `\\n`. \n"
        "    - **EVITA TRUNCAMIENTO:** Asegúrate de que el string contenga el *contenido completo* del archivo modificado y termine correctamente con una comilla doble (`\"`).\n"
        "    - **EJEMPLO DEL ERROR COMETIDO PREVIAMENTE (Incorrecto - Causa 'Unterminated string'):**\n"
        "      ```json\n"
        "      {\n"
        "        \"tipo_resultado\": \"ejecucion_cambio\",\n"
        "        \"archivos_modificados\": {\n"
        "          \"functions.php\": \"<?php ... \n"
        "             // ... mucho código ... \n"
        "             echo \"Este texto tiene comillas\"; \n"
        "             // ... más código ... \n"
        "             // (Respuesta incompleta o comillas sin escapar)\n"
        "        }\n"
        "      }\n"
        "      ```\n"
        "    - **EJEMPLO DE CÓMO DEBIÓ SER (Correcto - String JSON válido):**\n"
        "      ```json\n"
        "      {\n"
        "        \"tipo_resultado\": \"ejecucion_cambio\",\n"
        "        \"archivos_modificados\": {\n"
        "          \"functions.php\": \"<?php ... \\n // ... mucho código ... \\n echo \\\"Este texto tiene comillas\\\"; \\n // ... más código ... \\n?>\"\n"
        "        },\n"
        "        \"resumen_cambios\": \"...\"\n"
        "      }\n"
        "      ```\n"
        "    Presta **máxima atención** a esto para evitar fallos críticos en el parseo del JSON."
    )
    # --- FIN: ÉNFASIS EN JSON Y ESCAPADO ---

    if contextoCodigoReducido:
        promptPartes.append(
            "\n--- CONTENIDO ACTUAL DE ARCHIVOS RELEVANTES ---")
        promptPartes.append(contextoCodigoReducido)
        promptPartes.append("--- FIN CONTENIDO ---")
    else:
        promptPartes.append(
            "\n(No se proporcionó contenido de archivo para esta acción específica)")

    promptCompleto = "\n".join(promptPartes)

    log.info(
        f"{logPrefix} Enviando solicitud de EJECUCIÓN a Gemini (MODO JSON)...")
    # --- COMENTADO Log del prompt ---
    # log.debug(f"{logPrefix} Prompt (inicio): {promptCompleto[:200]}...")
    # log.debug(f"{logPrefix} Prompt (fin): ...{promptCompleto[-200:]}")

    try:
        respuesta = modelo.generate_content(
            promptCompleto,
            generation_config=genai.types.GenerationConfig(  # O usa dict
                temperature=0.4,  # Mantenemos una temperatura baja para seguir instrucciones
                response_mime_type="application/json",
                max_output_tokens=65536  # Asegurar suficiente espacio para código
            ),
            safety_settings={  # Configuración de seguridad estándar
                'HATE': 'BLOCK_ONLY_HIGH',
                'HARASSMENT': 'BLOCK_ONLY_HIGH',
                'SEXUAL': 'BLOCK_ONLY_HIGH',
                'DANGEROUS': 'BLOCK_ONLY_HIGH'
            }
        )
        log.info(f"{logPrefix} Respuesta de EJECUCIÓN (MODO JSON) recibida.")

        textoRespuesta = _extraerTextoRespuesta(respuesta, logPrefix)
        if not textoRespuesta:
            return None

        # _limpiarYParsearJson ya es robusto encontrando el bloque {},
        # pero fallará si el *contenido* del string no está bien escapado.
        # El logging detallado que ya tiene nos dirá si el problema persiste.
        resultadoJson = _limpiarYParsearJson(textoRespuesta, logPrefix)

        if resultadoJson is None:
            log.error(
                f"{logPrefix} El parseo/extracción final de JSON falló. (Ver logs anteriores para detalles del error y JSON candidato)")
            # El error ya fue logueado extensamente por _limpiarYParsearJson
            return None

        # --- Validación del contenido del JSON (sin cambios aquí, ya era adecuada) ---
        if resultadoJson.get("tipo_resultado") != "ejecucion_cambio":
            log.warning(
                f"{logPrefix} Respuesta JSON no tiene 'tipo_resultado'=\"ejecucion_cambio\" esperado. Verificando estructura.")
            # ... (resto de validaciones igual)
            if "archivos_modificados" not in resultadoJson or not isinstance(resultadoJson.get("archivos_modificados"), dict):
                log.error(
                    f"{logPrefix} Falta 'archivos_modificados' o no es un diccionario.")
                try:
                    log.error(
                        f"{logPrefix} JSON Recibido:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
                except Exception:
                    log.error(
                        f"{logPrefix} JSON Recibido (no se pudo formatear): {resultadoJson}")
                return None
            # Intentar corregir si falta solo eso
            resultadoJson["tipo_resultado"] = "ejecucion_cambio"

        accion_sin_contenido = accion in [
            "eliminar_archivo", "crear_directorio"]
        archivos_mod = resultadoJson.get("archivos_modificados")

        if archivos_mod is None:
            log.error(
                f"{logPrefix} La clave 'archivos_modificados' falta en la respuesta JSON.")
            try:
                log.error(
                    f"{logPrefix} JSON Recibido:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
            except Exception:
                log.error(
                    f"{logPrefix} JSON Recibido (no se pudo formatear): {resultadoJson}")
            return None

        if accion_sin_contenido and archivos_mod != {}:
            log.warning(
                f"{logPrefix} Se esperaba 'archivos_modificados' vacío para la acción '{accion}', pero se recibió: {list(archivos_mod.keys())}. Se procederá con dict vacío.")
            resultadoJson["archivos_modificados"] = {}
        elif not accion_sin_contenido and not isinstance(archivos_mod, dict):
            log.error(
                f"{logPrefix} Se esperaba un diccionario para 'archivos_modificados' en acción '{accion}', pero se recibió tipo {type(archivos_mod)}.")
            try:
                log.error(
                    f"{logPrefix} JSON Recibido:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
            except Exception:
                log.error(
                    f"{logPrefix} JSON Recibido (no se pudo formatear): {resultadoJson}")
            return None
        # Validación adicional: que los valores sean strings
        elif isinstance(archivos_mod, dict):
            for k, v in archivos_mod.items():
                if not isinstance(v, str):
                    log.error(
                        f"{logPrefix} El valor para la clave '{k}' en 'archivos_modificados' NO es un string (tipo: {type(v)}). JSON inválido.")
                    try:
                        log.error(
                            f"{logPrefix} JSON Recibido:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
                    except Exception:
                        log.error(
                            f"{logPrefix} JSON Recibido (no se pudo formatear): {resultadoJson}")
                    return None

        log.info(
            f"{logPrefix} Respuesta JSON (MODO JSON) parseada y validada correctamente.")
        # Loguear el resultado es útil, pero puede ser muy largo. Se mantiene.
        log.info(
            f"{logPrefix} JSON de Ejecución Generado:\n{json.dumps(resultadoJson, indent=2, ensure_ascii=False)}")
        return resultadoJson

    except google.api_core.exceptions.InvalidArgument as e_inv:
        # Este error puede ocurrir si el *prompt* es inválido O si el modelo falla en generar JSON válido.
        log.error(f"{logPrefix} Error InvalidArgument durante la generación JSON: {e_inv}. ¿El modelo tuvo problemas para generar el JSON solicitado O hubo contenido bloqueado?", exc_info=True)
        _manejarExcepcionGemini(
            e_inv, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None
    except Exception as e:
        _manejarExcepcionGemini(
            e, logPrefix, respuesta if 'respuesta' in locals() else None)
        return None

# --- Helpers Internos ---
# _extraerTextoRespuesta, _limpiarYParsearJson, _manejarExcepcionGemini
# (Sin cambios necesarios en los helpers, _limpiarYParsearJson ya es robusto
# y el logging del JSON se hace después de llamarlo con éxito)

# ... (resto de _extraerTextoRespuesta, _limpiarYParsearJson, _manejarExcepcionGemini igual) ...


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
                # MODIFICACIÓN: Si se usa response_mime_type="application/json"
                # el texto puede no estar en part.text directamente, pero sí en respuesta.text
                # Así que priorizamos respuesta.text si existe.
                if hasattr(respuesta, 'text') and respuesta.text:
                    textoRespuesta = respuesta.text
                else:
                    # Fallback a concatenar partes si respuesta.text no está
                    textoRespuesta = "".join(
                        part.text for part in respuesta.parts if hasattr(part, 'text'))
        elif hasattr(respuesta, 'candidates') and respuesta.candidates:
            # Comprobar si candidates es iterable y no vacío
            if isinstance(respuesta.candidates, (list, tuple)) and respuesta.candidates:
                # Similar al caso de 'parts', priorizar respuesta.text si existe
                if hasattr(respuesta, 'text') and respuesta.text:
                    textoRespuesta = respuesta.text
                else:
                    # Fallback a la lógica anterior del candidate
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
    # Aunque JSON mode *debería* evitar esto, lo mantenemos por robustez
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

    # A veces Gemini añade texto antes o después del JSON real incluso en JSON mode
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
        log.debug(
            f"{logPrefix} Intentando parsear JSON candidato (tamaño: {len(json_candidate)})...")
        resultadoJson = json.loads(json_candidate)
        # Ajuste leve msg
        log.info(
            f"{logPrefix} JSON parseado correctamente (previo a validación de contenido).")
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
        # O problemas del modelo generando el formato JSON solicitado
        # Añadido exc_info
        log.error(f"{logPrefix} Error argumento inválido API Gemini (InvalidArgument): {e}. ¿Prompt mal formado, contenido bloqueado o fallo en generación JSON?", exc_info=True)
    elif isinstance(e, google.api_core.exceptions.PermissionDenied):
        log.error(
            f"{logPrefix} Error de permiso API Gemini (PermissionDenied): {e}. ¿API Key incorrecta o sin permisos?")
    elif isinstance(e, google.api_core.exceptions.ServiceUnavailable):
        log.error(
            f"{logPrefix} Error servicio no disponible API Gemini (ServiceUnavailable): {e}. Reintentar más tarde.")
    # Intentar manejo específico de excepciones de bloqueo si están disponibles
    # Añadido ResponseBlockedError
    elif type(e).__name__ in ['BlockedPromptException', 'StopCandidateException', 'ResponseBlockedError']:
        log.error(
            f"{logPrefix} Prompt bloqueado o generación detenida/bloqueada por Gemini: {e}")
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
                # Puede que candidates esté vacío si la respuesta fue bloqueada
                try:
                    candidate = respuesta.candidates[0]
                    if hasattr(candidate, 'finish_reason'):
                        # Sobreescribir si hay finish_reason más específico
                        finish_reason = f"FinishReason: {candidate.finish_reason}"
                    if hasattr(candidate, 'safety_ratings'):
                        safety_ratings = str(candidate.safety_ratings)
                except IndexError:
                    log.debug(
                        f"{logPrefix} No se encontraron candidates en la respuesta (probablemente bloqueada).")

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
