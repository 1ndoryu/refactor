# nucleo/analizadorCodigo.py
import os
import logging
import google.generativeai as genai
from config import settings  

log = logging.getLogger(__name__)


def configurarGemini():
    # Configura la API de Gemini usando la key de settings
    logPrefix = "configurarGemini:"
    apiKey = settings.GEMINIAPIKEY
    if not apiKey:
        log.error(f"{logPrefix} API Key de Gemini no configurada.")
        return False
    try:
        genai.configure(api_key=apiKey)
        log.info(f"{logPrefix} Cliente de Gemini configurado exitosamente.")
        return True
    except Exception as e:
        log.error(f"{logPrefix} Error configurando cliente de Gemini: {e}")
        return False


def listarArchivosProyecto(rutaProyecto, extensionesPermitidas=None):
    # Devuelve una lista de rutas completas a archivos relevantes en el proyecto.
    # Por ahora, lista todos los archivos ignorando .git y opcionalmente filtra por extensión.
    logPrefix = "listarArchivosProyecto:"
    archivosProyecto = []
    if extensionesPermitidas is None:
        # Ejemplo: Permitir php, js, css, html por defecto si no se especifica
        extensionesPermitidas = ['.php', '.js',
                                 '.css', '.html', '.py', '.json', '.md']
        log.debug(
            f"{logPrefix} Usando extensiones por defecto: {extensionesPermitidas}")

    try:
        for raiz, dirs, archivos in os.walk(rutaProyecto):
            # Ignorar el directorio .git
            if '.git' in dirs:
                dirs.remove('.git')
            # Ignorar directorios específicos si es necesario (ej. vendor, node_modules)
            # if 'vendor' in dirs:
            #     dirs.remove('vendor')

            for nombreArchivo in archivos:
                rutaCompleta = os.path.join(raiz, nombreArchivo)
                # Filtrar por extensión si se especificaron
                if extensionesPermitidas:
                    _, ext = os.path.splitext(nombreArchivo)
                    if ext.lower() in extensionesPermitidas:
                        archivosProyecto.append(rutaCompleta)
                else:  # Si no hay filtro, añadir todos
                    archivosProyecto.append(rutaCompleta)

        log.info(
            f"{logPrefix} Encontrados {len(archivosProyecto)} archivos relevantes en {rutaProyecto}")
        return archivosProyecto
    except Exception as e:
        log.error(f"{logPrefix} Error listando archivos en {rutaProyecto}: {e}")
        return None


def leerArchivos(listaArchivos, rutaBase):
    # Lee el contenido de una lista de archivos y los devuelve en un diccionario
    # o como una cadena concatenada, manejando errores de lectura/decodificación.
    logPrefix = "leerArchivos:"
    contenidoArchivos = {}  # {ruta_relativa: contenido}
    contenidoConcatenado = ""  # Opcion B: todo junto

    log.info(f"{logPrefix} Leyendo {len(listaArchivos)} archivos...")
    archivosLeidos = 0
    archivosFallidos = 0

    for rutaAbsoluta in listaArchivos:
        try:
            # Obtener ruta relativa para usarla como clave o en el prompt
            rutaRelativa = os.path.relpath(rutaAbsoluta, rutaBase)
            with open(rutaAbsoluta, 'r', encoding='utf-8', errors='ignore') as f:
                contenido = f.read()
                contenidoArchivos[rutaRelativa] = contenido
                # Para la opción concatenada:
                contenidoConcatenado += f"\n--- INICIO ARCHIVO: {rutaRelativa} ---\n"
                contenidoConcatenado += contenido
                contenidoConcatenado += f"\n--- FIN ARCHIVO: {rutaRelativa} ---\n"
                archivosLeidos += 1
        except FileNotFoundError:
            log.warning(
                f"{logPrefix} Archivo no encontrado (quizás eliminado recientemente?): {rutaAbsoluta}")
            archivosFallidos += 1
        except Exception as e:
            log.error(f"{logPrefix} Error leyendo archivo {rutaAbsoluta}: {e}")
            archivosFallidos += 1

    log.info(
        f"{logPrefix} Lectura completada. Leidos: {archivosLeidos}, Fallidos: {archivosFallidos}")

    # Decidir qué devolver: un diccionario o una cadena.
    # Para Gemini, una cadena larga puede ser más simple de manejar en el prompt.
    # return contenidoArchivos
    return contenidoConcatenado


def analizarConGemini(contextoCodigo, historialCambios=None):
    # Envía el contexto a Gemini y pide una sugerencia de refactorización.
    # Devuelve la respuesta de Gemini (idealmente parseada como JSON).
    logPrefix = "analizarConGemini:"

    if not configurarGemini():  # Asegurarse que el cliente esté listo
        return None

    # TODO: Definir el modelo a usar (ej. 'gemini-pro', 'gemini-1.5-pro-latest')
    # Considerar modelos con ventana de contexto más grande si es necesario y disponible.
    modelo = genai.GenerativeModel('gemini-pro')

    # --- Construcción del Prompt ---
    # Este es el paso más CRÍTICO y requiere iteración.
    promptPartes = []

    promptPartes.append(
        "Eres un asistente experto en refactorización de software.")
    promptPartes.append(
        "Tu objetivo es analizar el código proporcionado y proponer UN ÚNICO cambio PEQUEÑO y CONCRETO para mejorar la organización, legibilidad o mantenibilidad del proyecto.")
    # TODO: Hacer esto configurable o detectarlo
    promptPartes.append(
        "El proyecto es [DESCRIBIR BREVEMENTE EL PROYECTO SI ES POSIBLE, EJ: una aplicación web PHP con algo de JS].")

    if historialCambios:
        promptPartes.append("\n--- HISTORIAL DE CAMBIOS RECIENTES ---")
        promptPartes.append(historialCambios)
        promptPartes.append("--- FIN HISTORIAL ---")
        promptPartes.append(
            "Considera estos cambios previos al proponer el siguiente.")

    promptPartes.append("\n--- CÓDIGO A ANALIZAR ---")
    # IMPORTANTE: Aquí va el contexto. Si es muy grande, habrá que enviarlo en partes
    # o usar una estrategia para reducirlo (ej. pedir primero identificar área).
    # Por ahora, asumimos que contextoCodigo cabe en la ventana del modelo.
    promptPartes.append(contextoCodigo)
    promptPartes.append("--- FIN CÓDIGO ---")

    promptPartes.append("\n--- INSTRUCCIONES PARA TU RESPUESTA ---")
    promptPartes.append(
        "1. Identifica UNA sola acción de refactorización (ej: renombrar variable, extraer método, mover archivo, crear directorio, eliminar código muerto).")
    promptPartes.append("2. Describe la acción claramente.")
    promptPartes.append(
        "3. Proporciona TODOS los detalles necesarios para aplicar el cambio (archivo(s) afectado(s), número de línea si aplica, código nuevo/modificado, ruta de destino, etc.).")
    promptPartes.append(
        "4. RESPONDE ÚNICAMENTE EN FORMATO JSON VÁLIDO con la siguiente estructura:")
    promptPartes.append("""
```json
{
  "accion": "TIPO_ACCION", // Ej: "modificar_archivo", "mover_archivo", "crear_archivo", "eliminar_archivo", "crear_directorio"
  "descripcion": "Descripción breve y clara del cambio propuesto para el mensaje de commit.",
  "detalles": {
    // Los campos aquí dependen de 'accion'
    // Para "modificar_archivo":
    //   "archivo": "ruta/relativa/al/archivo.php",
    //   "linea_inicio": numero_linea_opcional, // Opcional
    //   "linea_fin": numero_linea_opcional, // Opcional
    //   "codigo_nuevo": "el contenido completo o la sección modificada...",
    //   "buscar": "texto_a_reemplazar_opcional", // Alternativa a linea_inicio/fin
    //   "reemplazar": "texto_nuevo_opcional"
    // Para "mover_archivo":
    //   "archivo_origen": "ruta/relativa/origen.php",
    //   "archivo_destino": "nueva/ruta/relativa/destino.php"
    // Para "crear_archivo":
    //   "archivo": "nueva/ruta/relativa/archivo.js",
    //   "contenido": "el contenido inicial del archivo..."
    // Para "eliminar_archivo":
    //   "archivo": "ruta/relativa/a/eliminar.txt"
    // Para "crear_directorio":
    //   "directorio": "nueva/ruta/relativa/directorio"
    // ... otros tipos de acción si son necesarios ...
  },
  "razonamiento": "Explicación breve de por qué este cambio es beneficioso." // Opcional pero útil
}
```""")
    promptPartes.append(
        "5. Si no encuentras ninguna refactorización obvia o segura en este momento, responde con un JSON como: `{\"accion\": \"no_accion\", \"descripcion\": \"No se identificaron acciones de refactorización inmediatas.\", \"detalles\": {}}`")
    promptPartes.append("6. Asegúrate que el JSON sea válido y completo.")

    promptCompleto = "\n".join(promptPartes)

    # --- Llamada a Gemini ---
    log.info(
        f"{logPrefix} Enviando solicitud a Gemini (modelo: {modelo.model_name})...")
    log.debug(f"{logPrefix} Prompt completo:\n{promptCompleto[:500]}...") # Loguear inicio del prompt para depuración

    try:
        # Configurar safety_settings para ser menos restrictivo si es necesario (con precaución)
        # safety_settings = [
        #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        # ]
        respuesta = modelo.generate_content(
            promptCompleto,
            # safety_settings=safety_settings,
            # generation_config=genai.types.GenerationConfig( # Opciones de generación
            #     temperature=0.7 # Ajustar creatividad vs determinismo
            # )
        )

        # Limpiar posible markdown ```json ... ``` de la respuesta
        textoRespuesta = respuesta.text.strip()
        if textoRespuesta.startswith("```json"):
            textoRespuesta = textoRespuesta[7:]
        if textoRespuesta.endswith("```"):
            textoRespuesta = textoRespuesta[:-3]
        textoRespuesta = textoRespuesta.strip()

        log.info(f"{logPrefix} Respuesta recibida de Gemini.")
        # log.debug(f"{logPrefix} Respuesta texto: {textoRespuesta}") # Loguear respuesta completa para depurar

        # Intentar parsear la respuesta JSON
        import json
        try:
            sugerenciaJson = json.loads(textoRespuesta)
            log.info(f"{logPrefix} Sugerencia JSON parseada correctamente.")
            return sugerenciaJson
        except json.JSONDecodeError as e:
            log.error(f"{logPrefix} Error al parsear JSON de Gemini: {e}")
            log.error(
                f"{logPrefix} Respuesta recibida (puede estar incompleta o mal formada): {respuesta.text}")
            return None

    except Exception as e:
        log.error(
            f"{logPrefix} Error durante la llamada a la API de Gemini: {e}")
        # Podríamos querer inspeccionar respuesta.prompt_feedback si existe
        # if hasattr(respuesta, 'prompt_feedback'):
        #      log.error(f"{logPrefix} Prompt Feedback: {respuesta.prompt_feedback}")
        return None
