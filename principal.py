# principal.py
import logging
import sys
import os
import json
import argparse
import subprocess # Necesario para el check de git diff
from config import settings
# Importar módulos del núcleo
from nucleo import manejadorGit
from nucleo import analizadorCodigo
from nucleo import aplicadorCambios

# Configuración del logging (mover a una función para claridad)
def configurarLogging():
    # Usar logging.getLogger() directamente aquí para configurar el logger raíz
    log_raiz = logging.getLogger()
    if log_raiz.handlers:
        # Evitar añadir handlers múltiples veces si se llama de nuevo
        # Podríamos verificar si ya tiene los handlers específicos que añadimos
        # o simplemente asumir que si tiene handlers, ya está configurado.
        # logging.info("configurarLogging: Logging ya parece configurado.")
        return

    # Determinar nivel de log (ej., desde variable de entorno o argumento)
    # Por ahora, hardcodeado a INFO, pero podría ser más flexible
    nivelLog = logging.INFO
    # nivelLog = logging.DEBUG # Descomentar para más detalle

    formatoLog = '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s: %(message)s'
    fechaFormato = '%Y-%m-%d %H:%M:%S'

    # Handler para la consola
    consolaHandler = logging.StreamHandler(sys.stdout)
    consolaHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
    log_raiz.addHandler(consolaHandler)

    # Handler para el archivo
    try:
        # Usar RUTA_BASE_PROYECTO para la ruta del log
        rutaLogArchivo = os.path.join(settings.RUTA_BASE_PROYECTO, "refactor.log")
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(rutaLogArchivo), exist_ok=True)
        archivoHandler = logging.FileHandler(rutaLogArchivo, encoding='utf-8')
        archivoHandler.setFormatter(logging.Formatter(formatoLog, fechaFormato))
        log_raiz.addHandler(archivoHandler)
    except Exception as e:
        # Usar el logger raíz aquí, aunque el handler de archivo falló, el de consola debería funcionar
        log_raiz.error(f"configurarLogging: No se pudo crear el archivo de log '{rutaLogArchivo}': {e}")

    log_raiz.setLevel(nivelLog)
    logging.info("="*50)
    logging.info("="*50)
    logging.info("="*50)
    logging.info("configurarLogging: Sistema de logging configurado.")
    logging.info(f"configurarLogging: Nivel de log establecido a {logging.getLevelName(log_raiz.level)}")


# Funciones para manejar el historial persistente
def cargarHistorial():
    logPrefix = "cargarHistorial:"
    historial = []
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    if not os.path.exists(rutaArchivoHistorial):
        logging.info(f"{logPrefix} Archivo de historial no encontrado en {rutaArchivoHistorial}. Iniciando historial vacío.")
        return historial

    try:
        with open(rutaArchivoHistorial, 'r', encoding='utf-8') as f:
            # Leer líneas y quitar espacios/saltos de línea vacíos
            historial = [line.strip() for line in f if line.strip()]
        logging.info(f"{logPrefix} Historial cargado desde {rutaArchivoHistorial} ({len(historial)} entradas).")
    except Exception as e:
        logging.error(f"{logPrefix} Error crítico cargando historial desde {rutaArchivoHistorial}: {e}. Se procederá con historial vacío.")
        historial = [] # Asegurar que devolvemos lista vacía en caso de error
    return historial

def guardarHistorial(historial):
    logPrefix = "guardarHistorial:"
    rutaArchivoHistorial = settings.RUTAHISTORIAL
    try:
        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(rutaArchivoHistorial), exist_ok=True)
        with open(rutaArchivoHistorial, 'w', encoding='utf-8') as f:
            for entrada in historial:
                # Asegurar que cada entrada termine con un salto de línea
                f.write(entrada.strip() + "\n")
        logging.info(f"{logPrefix} Historial guardado en {rutaArchivoHistorial} ({len(historial)} entradas).")
        return True
    except Exception as e:
        logging.error(f"{logPrefix} Error crítico guardando historial en {rutaArchivoHistorial}: {e}")
        return False

# Función para parsear y validar la sugerencia JSON de Gemini
def parsearSugerencia(sugerenciaJson):
    logPrefix = "parsearSugerencia:"
    accionesSoportadas = [
        "modificar_archivo", "mover_archivo", "crear_archivo",
        "eliminar_archivo", "crear_directorio", "mover_codigo", "no_accion"
    ]

    # Verificar que sea un diccionario
    if not isinstance(sugerenciaJson, dict):
        logging.error(f"{logPrefix} La sugerencia recibida no es un diccionario JSON válido. Tipo: {type(sugerenciaJson)}. Valor: {sugerenciaJson}")
        return None

    # Extraer campos principales
    accion = sugerenciaJson.get("accion")
    detalles = sugerenciaJson.get("detalles")
    descripcion = sugerenciaJson.get("descripcion")
    razonamiento = sugerenciaJson.get("razonamiento") # También útil para logs

    # Validar campos obligatorios y tipos
    if not accion or not isinstance(detalles, dict) or not descripcion:
        logging.error(f"{logPrefix} Formato JSON inválido. Faltan 'accion', 'detalles' o 'descripcion', o 'detalles' no es un dict. JSON: {sugerenciaJson}")
        return None

    # Validar que la acción sea soportada
    if accion not in accionesSoportadas:
        logging.error(f"{logPrefix} Acción '{accion}' NO RECONOCIDA o NO SOPORTADA. Válidas: {accionesSoportadas}. JSON: {sugerenciaJson}")
        return None

    # Log específico para no_accion
    if accion == "no_accion":
        logging.info(f"{logPrefix} Sugerencia 'no_accion' recibida y parseada. Razón: {razonamiento or 'No proporcionada'}")

    logging.info(f"{logPrefix} Sugerencia parseada exitosamente. Acción: {accion}")
    return sugerenciaJson # Devolver el diccionario completo validado


def ejecutarProcesoPrincipal():
    logPrefix = "ejecutarProcesoPrincipal:"
    logging.info(f"{logPrefix} ===== INICIO CICLO DE REFACTORIZACIÓN =====")
    cicloExitosoConCommit = False # Flag para estado final
    historialRefactor = [] # Inicializar aquí para asegurar disponibilidad en try/except
    accionParseada = None # Inicializar info de acción
    codigoAAnalizar = "" # Guardará el contexto completo leído

    try:
        # 1. Verificar configuración esencial
        if not settings.GEMINIAPIKEY or not settings.REPOSITORIOURL:
            logging.critical(f"{logPrefix} Configuración esencial faltante (GEMINI_API_KEY o REPOSITORIOURL). Abortando.")
            # No guardar historial aquí, es un fallo de configuración previo
            return False # No se puede proceder

        # 2. Cargar historial existente
        historialRefactor = cargarHistorial()

        # 3. Preparar repositorio local
        logging.info(f"{logPrefix} Preparando repositorio local en '{settings.RUTACLON}' en la rama '{settings.RAMATRABAJO}'...")
        if not manejadorGit.clonarOActualizarRepo(settings.REPOSITORIOURL, settings.RUTACLON, settings.RAMATRABAJO):
            logging.error(f"{logPrefix} No se pudo preparar el repositorio. Abortando ciclo.")
            # Podríamos guardar historial de fallo de git, pero es más un problema de entorno
            # guardarHistorial(historialRefactor + ["[ERROR] Fallo crítico preparando repositorio Git."])
            return False
        logging.info(f"{logPrefix} Repositorio listo y en la rama '{settings.RAMATRABAJO}'.")

        # 4. Analizar código del proyecto
        logging.info(f"{logPrefix} Analizando código del proyecto en {settings.RUTACLON}...")
        extensiones = getattr(settings, 'EXTENSIONESPERMITIDAS', None)
        ignorados = getattr(settings, 'DIRECTORIOS_IGNORADOS', None)
        archivos = analizadorCodigo.listarArchivosProyecto(settings.RUTACLON, extensiones, ignorados)

        if archivos is None: # Error listando archivos
             logging.error(f"{logPrefix} Error al listar archivos del proyecto. Abortando ciclo.")
             return False
        if not archivos: # No se encontraron archivos relevantes
            logging.warning(f"{logPrefix} No se encontraron archivos relevantes con las extensiones/ignorados configurados. Terminando ciclo.")
            # Guardar historial indicando no acción por falta de archivos? Opcional.
            # historialRefactor.append("[INFO] No se encontraron archivos relevantes para analizar.")
            # guardarHistorial(historialRefactor)
            return False # No hay nada que hacer

        # Leer contenido de archivos relevantes (¡Guardar en codigoAAnalizar!)
        codigoAAnalizar = analizadorCodigo.leerArchivos(archivos, settings.RUTACLON)
        if not codigoAAnalizar: # Error leyendo archivos
            logging.error(f"{logPrefix} Error al leer el contenido de los archivos. Abortando ciclo.")
            # guardarHistorial(historialRefactor + ["[ERROR] Fallo crítico leyendo contenido de archivos."])
            return False

        tamanoBytes = len(codigoAAnalizar.encode('utf-8'))
        tamanoKB = tamanoBytes / 1024
        logging.info(f"{logPrefix} Código fuente leído ({len(archivos)} archivos, {tamanoKB:.2f} KB).")

        # 5. Obtener sugerencia de Gemini
        logging.info(f"{logPrefix} Obteniendo sugerencia de Gemini (modelo: {settings.MODELOGEMINI})...")
        # Tomar N entradas recientes del historial para contexto
        historialRecienteTexto = "\n".join(historialRefactor[-settings.N_HISTORIAL_CONTEXTO:])
        sugerenciaJson = analizadorCodigo.analizarConGemini(codigoAAnalizar, historialRecienteTexto)

        if not sugerenciaJson:
            logging.error(f"{logPrefix} No se recibió sugerencia válida de Gemini. Abortando ciclo.")
            # Intentar limpiar por si acaso (aunque no debería haber cambios)
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            # Registrar fallo de Gemini en historial
            historialRefactor.append("[ERROR] No se pudo obtener una sugerencia válida de Gemini.")
            guardarHistorial(historialRefactor)
            return False

        # 6. Parsear y validar la sugerencia recibida
        logging.info(f"{logPrefix} Parseando sugerencia de Gemini...")
        accionParseada = parsearSugerencia(sugerenciaJson)

        if not accionParseada:
            logging.error(f"{logPrefix} Sugerencia inválida, mal formada o no soportada. Abortando ciclo.")
            manejadorGit.descartarCambiosLocales(settings.RUTACLON)
            # Registrar fallo de parseo en historial
            # Limitar tamaño del JSON logueado
            sugerencia_str = json.dumps(sugerenciaJson)
            sugerencia_log = sugerencia_str[:500] + ('...' if len(sugerencia_str) > 500 else '')
            historialRefactor.append(f"[ERROR] Sugerencia de Gemini inválida o no soportada: {sugerencia_log}")
            guardarHistorial(historialRefactor)
            return False

        # Manejar caso 'no_accion' explícito
        if accionParseada.get("accion") == "no_accion":
            razonamientoNoAccion = accionParseada.get('razonamiento', 'Sin razonamiento especificado.')
            logging.info(f"{logPrefix} Gemini sugirió 'no_accion'. Razón: {razonamientoNoAccion}. Terminando ciclo.")
            # Registrar 'no_accion' en historial para trazabilidad
            historialRefactor.append(f"[INFO] Acción 'no_accion' sugerida. Razón: {razonamientoNoAccion}")
            guardarHistorial(historialRefactor)
            return False # No hubo error, pero no se hizo commit

        # --- INICIO VALIDACIÓN PREVIA (SI ES modificar_archivo con buscar/reemplazar) ---
        if accionParseada.get("accion") == "modificar_archivo":
            detalles = accionParseada.get("detalles", {})
            buscar = detalles.get("buscar")
            reemplazar = detalles.get("reemplazar")
            archivoRel = detalles.get("archivo")

            # Solo validar si tenemos buscar, reemplazar y archivo válidos
            if isinstance(buscar, str) and reemplazar is not None and isinstance(archivoRel, str):
                logging.info(f"{logPrefix} Realizando validación previa para 'modificar_archivo' en '{archivoRel}'...")
                # Reconstruir el nombre de archivo y marcadores como en analizadorCodigo.leerArchivos
                # Asegurarse de que la ruta relativa use '/' como separador, como lo hace leerArchivos
                archivoRelNorm = archivoRel.replace(os.sep, '/')
                inicio_marcador = f"########## START FILE: {archivoRelNorm} ##########"
                fin_marcador = f"########## END FILE: {archivoRelNorm} ##########"

                inicio_idx = codigoAAnalizar.find(inicio_marcador)
                fin_idx = codigoAAnalizar.find(fin_marcador)

                if inicio_idx != -1 and fin_idx != -1 and fin_idx > inicio_idx:
                    # Extraer el contenido específico de ese archivo del contexto completo
                    contenido_archivo_en_contexto = codigoAAnalizar[inicio_idx + len(inicio_marcador):fin_idx].strip()

                    # ¡La validación crucial!
                    if buscar not in contenido_archivo_en_contexto:
                        logging.error(f"{logPrefix} ¡VALIDACIÓN PREVIA FALLIDA! La cadena 'buscar' EXACTA NO se encontró en el CONTEXTO ORIGINAL enviado a Gemini para el archivo '{archivoRel}'. Es probable que Gemini se equivocara o el archivo haya cambiado inesperadamente.")
                        logging.error(f"{logPrefix} Buscar (inicio, repr): {repr(buscar[:150])}{'...' if len(buscar)>150 else ''}")
                        # Abortar el ciclo para evitar el error en aplicadorCambios
                        razonamientoIntento = accionParseada.get('razonamiento', 'Sin razonamiento.')
                        descripcionIntento = accionParseada.get('descripcion', 'Acción sin descripción')
                        entradaHistorialError = f"[ERROR] Validación Previa Fallida: 'buscar' no encontrado en contexto original. Archivo: {archivoRel}. Desc: {descripcionIntento}. Razón Gemini: {razonamientoIntento}"
                        historialRefactor.append(entradaHistorialError)
                        guardarHistorial(historialRefactor)
                        # No debería haber cambios que descartar, pero por si acaso
                        manejadorGit.descartarCambiosLocales(settings.RUTACLON)
                        logging.warning(f"{logPrefix} Ciclo abortado debido a fallo en validación previa.")
                        return False # Indicar fallo del ciclo
                    else:
                         # La cadena sí se encontró en el contexto original
                         logging.info(f"{logPrefix} Validación previa OK: 'buscar' encontrado en el contexto original de '{archivoRel}'. Procediendo a aplicar el cambio.")
                else:
                    # No se pudieron encontrar los marcadores, algo raro pasó
                    logging.warning(f"{logPrefix} Validación previa: No se pudo extraer el contenido del archivo '{archivoRel}' del contexto 'codigoAAnalizar' usando los marcadores ('{inicio_marcador}', '{fin_marcador}'). Se continuará, pero el riesgo de fallo en 'aplicarCambio' aumenta.")
                    # Decidimos continuar, pero podrías optar por abortar aquí también si es crítico.

        # --- FIN VALIDACIÓN PREVIA ---

        # --- Si llegamos aquí, la acción es válida y, si era 'modificar_archivo', pasó la validación previa ---

        # Extraer descripción y razonamiento para logs y commit
        descripcionIntento = accionParseada.get('descripcion', 'Acción sin descripción')
        razonamientoIntento = accionParseada.get('razonamiento', 'Sin razonamiento proporcionado.')

        # 7. Intentar aplicar los cambios sugeridos
        logging.info(f"{logPrefix} Aplicando cambios sugeridos: {descripcionIntento}")
        # aplicadorCambios ahora devuelve (bool_exito, mensaje_error_o_none)
        exitoAplicar, mensajeErrorAplicar = aplicadorCambios.aplicarCambio(accionParseada, settings.RUTACLON)

        if not exitoAplicar:
            # --- Caso: Aplicación Fallida ---
            logging.error(f"{logPrefix} Falló la aplicación de cambios: {mensajeErrorAplicar}")
            # Construir entrada de historial de error detallada
            entradaHistorialError = f"[ERROR] Aplicación fallida: {descripcionIntento}. Razón: {mensajeErrorAplicar}. Razonamiento original: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)

            # Intentar descartar cambios locales fallidos
            logging.info(f"{logPrefix} Intentando descartar cambios locales tras fallo...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                # ¡Esto es grave! No se aplicó Y no se pudo limpiar. Requiere intervención.
                logging.critical(f"{logPrefix} ¡FALLO CRÍTICO! No se aplicaron cambios Y TAMPOCO se pudieron descartar. ¡Revisión manual URGENTE requerida en {settings.RUTACLON}!")
                # Añadir nota al historial también
                historialRefactor.append("[ERROR CRÍTICO] FALLO AL DESCARTAR CAMBIOS TRAS ERROR DE APLICACIÓN.")
            else:
                logging.info(f"{logPrefix} Cambios locales (si los hubo) descartados tras fallo en aplicación.")

            # Guardar historial CON el error y salir indicando fallo
            guardarHistorial(historialRefactor)
            return False # Indicar fallo del ciclo

        # --- Si llegamos aquí, exitoAplicar fue True ---
        logging.info(f"{logPrefix} Cambios aplicados localmente con éxito.")

        # 8. Hacer commit de los cambios aplicados
        logging.info(f"{logPrefix} Realizando commit en rama '{settings.RAMATRABAJO}'...")
        mensajeCommit = descripcionIntento # Usar la descripción de Gemini como mensaje

        # Validar/Truncar longitud del mensaje de commit si es necesario
        if len(mensajeCommit.encode('utf-8')) > 4000: # Límite práctico seguro
             mensajeCommit = mensajeCommit[:1000] + "... (truncado)"
             logging.warning(f"{logPrefix} Mensaje de commit truncado por longitud excesiva.")
        # Advertir si la primera línea es muy larga (convención Git)
        elif len(mensajeCommit.splitlines()[0]) > 72:
             logging.warning(f"{logPrefix} La primera línea del mensaje de commit supera los 72 caracteres recomendados.")

        # Intentar hacer el commit
        exitoCommitIntento = manejadorGit.hacerCommit(settings.RUTACLON, mensajeCommit)

        if not exitoCommitIntento:
            # --- Caso: Comando 'git commit' falló ---
            # manejadorGit.hacerCommit ya logueó el error específico de git
            logging.error(f"{logPrefix} Falló el comando 'git commit' (ver logs anteriores).")
             # Construir entrada de historial de error
            entradaHistorialError = f"[ERROR] Cambios aplicados, PERO 'git commit' FALLÓ. Intento: {descripcionIntento}. Razonamiento: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)

            # Intentar descartar cambios locales tras fallo de commit
            logging.info(f"{logPrefix} Intentando descartar cambios locales tras fallo de commit...")
            if not manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                 logging.critical(f"{logPrefix} ¡FALLO CRÍTICO! Cambios aplicados, commit falló Y NO SE PUDO DESCARTAR. ¡Revisión manual URGENTE requerida en {settings.RUTACLON}!")
                 historialRefactor.append("[ERROR CRÍTICO] FALLO AL DESCARTAR CAMBIOS TRAS ERROR DE COMMIT.")
            else:
                 logging.info(f"{logPrefix} Cambios locales descartados tras fallo de commit.")


            # Guardar historial CON el error de commit y salir
            guardarHistorial(historialRefactor)
            return False # Indicar fallo del ciclo

        # --- Si llegamos aquí, el comando 'git commit' no dio error ---
        # Ahora, verificar si el commit realmente introdujo cambios
        logging.info(f"{logPrefix} Verificando si el commit introdujo cambios efectivos...")
        comandoCheckDiff = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
        commitTuvoCambios = False
        errorVerificandoCommit = False
        try:
            # Ejecutar 'git diff --quiet'. Devuelve 1 si hay diferencias, 0 si no hay.
            resultadoCheck = subprocess.run(comandoCheckDiff, cwd=settings.RUTACLON, capture_output=True)

            if resultadoCheck.returncode == 1:
                # Código 1 significa que HEAD es diferente de HEAD~1 -> Hubo cambios
                logging.info(f"{logPrefix} Commit realizado con éxito y contiene cambios efectivos.")
                commitTuvoCambios = True
            elif resultadoCheck.returncode == 0:
                 # Código 0 significa que HEAD es igual a HEAD~1 -> Commit vacío o sin efecto real
                 logging.warning(f"{logPrefix} Aunque 'git commit' se ejecutó, no se detectaron cambios efectivos respecto al commit anterior. La acción pudo no tener efecto real o ser redundante.")
                 # Intentar deshacer el commit vacío/sin efecto para mantener limpio el historial
                 logging.info(f"{logPrefix} Intentando revertir commit vacío/sin efecto (reset --soft HEAD~1)...")
                 try:
                     # Usar reset --soft para quitar el commit pero mantener los cambios en staging (luego descartar)
                     if manejadorGit.ejecutarComando(['git', 'reset', '--soft', 'HEAD~1'], cwd=settings.RUTACLON):
                         # Ahora descartar los cambios que quedaron en staging/working dir
                         if manejadorGit.descartarCambiosLocales(settings.RUTACLON):
                              logging.info(f"{logPrefix} Commit vacío/sin efecto revertido y cambios descartados.")
                         else:
                              logging.error(f"{logPrefix} Se hizo reset soft del commit vacío, pero falló el descarte posterior. ¡Repo puede tener cambios sin commitear!")
                     else:
                          logging.error(f"{logPrefix} No se pudo revertir el commit potencialmente vacío/sin efecto mediante 'reset --soft'.")
                 except Exception as e_revert:
                      logging.error(f"{logPrefix} Excepción inesperada al intentar revertir commit vacío: {e_revert}")
                 # A pesar del intento de revertir, consideramos que el ciclo no tuvo un commit efectivo.
                 commitTuvoCambios = False
            else:
                 # Código de retorno inesperado de 'git diff'
                 stderr_log = resultadoCheck.stderr.decode('utf-8', errors='ignore').strip()
                 logging.error(f"{logPrefix} Error inesperado al verificar diferencias del commit con 'git diff' (código {resultadoCheck.returncode}). Stderr: {stderr_log}")
                 errorVerificandoCommit = True
                 commitTuvoCambios = False # No podemos asegurar que hubo cambios

        except FileNotFoundError:
             logging.error(f"{logPrefix} Error crítico: Comando 'git' no encontrado al verificar commit. ¿Está instalado?")
             errorVerificandoCommit = True
             commitTuvoCambios = False
        except Exception as e:
             logging.error(f"{logPrefix} Error inesperado verificando diferencias del último commit: {e}", exc_info=True)
             errorVerificandoCommit = True
             commitTuvoCambios = False

        # --- Decidir estado final y guardar historial basado en si hubo commit efectivo ---
        if commitTuvoCambios:
            # --- Caso: Éxito Real (Commit con cambios) ---
            cicloExitosoConCommit = True
            logging.info(f"{logPrefix} Ciclo completado con éxito. Registrando en historial.")
            # Formatear entrada de historial de éxito
            entradaHistorialExito = f"[ÉXITO] {descripcionIntento}"
            # Añadir razonamiento si existe y es útil
            if razonamientoIntento and razonamientoIntento.lower() not in ['sin razonamiento proporcionado.', 'sin razonamiento.', 'no aplica']:
                entradaHistorialExito += f" Razonamiento: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialExito)
            guardarHistorial(historialRefactor)
            logging.info(f"{logPrefix} ===== FIN CICLO DE REFACTORIZACIÓN (Commit realizado) =====")
            return True # Éxito final del ciclo

        else:
            # --- Caso: Commit Ejecutado pero Sin Cambios, o Error Verificando ---
            razonFalloCommitEfectivo = "No se detectaron cambios efectivos tras el commit (posible acción redundante o sin efecto)."
            if errorVerificandoCommit:
                razonFalloCommitEfectivo = "Error al verificar los cambios del commit."
            # Nota: el caso de 'git commit' fallando ya se manejó antes y retorna False

            logging.warning(f"{logPrefix} El ciclo finaliza porque no se realizó un commit con cambios efectivos. Razón: {razonFalloCommitEfectivo}")
            # Registrar este estado en el historial como un error o advertencia
            entradaHistorialError = f"[ERROR] Cambios aplicados, pero SIN commit efectivo. Intento: {descripcionIntento}. Razón: {razonFalloCommitEfectivo}. Razonamiento Gemini: {razonamientoIntento}"
            historialRefactor.append(entradaHistorialError)

            # Guardar historial CON el error/advertencia y salir
            guardarHistorial(historialRefactor)
            # Aunque no hubo error catastrófico, no se logró el objetivo de un commit útil.
            return False # Indicar fallo (o no éxito) del ciclo

    except Exception as e:
        # --- Caso: Error Inesperado General durante el proceso ---
        logging.critical(f"{logPrefix} Error inesperado y no capturado durante la ejecución principal: {e}", exc_info=True)
        # Intentar grabar un error genérico en el historial si es posible
        if historialRefactor is not None: # Comprobar si historial fue inicializado
             descripcionIntento = "Acción desconocida (error temprano)"
             if accionParseada and isinstance(accionParseada.get("descripcion"), str) :
                 descripcionIntento = accionParseada.get("descripcion")

             entradaHistorialError = f"[ERROR CRÍTICO] Error inesperado durante el proceso. Intento: {descripcionIntento}. Detalle: {e}"
             historialRefactor.append(entradaHistorialError)
             guardarHistorial(historialRefactor) # Intentar guardar

        # Intentar limpiar el repositorio como último recurso
        try:
            if 'settings' in locals() and hasattr(settings, 'RUTACLON'):
                 logging.info(f"{logPrefix} Intentando descartar cambios locales debido a error inesperado...")
                 manejadorGit.descartarCambiosLocales(settings.RUTACLON)
        except Exception as e_clean:
            logging.error(f"{logPrefix} Falló el intento de limpieza tras error inesperado: {e_clean}")

        return False # Indicar fallo del ciclo


# Punto de entrada principal del script
if __name__ == "__main__":
    # Configurar logging al inicio
    configurarLogging()

    # Parsear argumentos de línea de comandos
    parser = argparse.ArgumentParser(
        description="Agente de Refactorización de Código con IA (Gemini).",
        epilog="Ejecuta un ciclo de refactorización: analiza, obtiene sugerencia, aplica y commitea. Usa --modo-test para hacer push si hay commit."
    )
    parser.add_argument(
        "--modo-test", action="store_true",
        help="Activa modo prueba: Si el ciclo realiza un commit efectivo, intenta hacer push a origin."
    )
    args = parser.parse_args()

    logging.info(f"Iniciando script principal. Modo Test: {'Activado' if args.modo_test else 'Desactivado'}")

    try:
        # Ejecutar el proceso principal. Devuelve True solo si hubo un commit CON cambios efectivos.
        # Devuelve False en cualquier otro caso (error, no acción, commit vacío, etc.).
        # El historial se guarda DENTRO de ejecutarProcesoPrincipal en todos los casos.
        commitRealizadoConExito = ejecutarProcesoPrincipal()

        if commitRealizadoConExito:
            # El ciclo fue exitoso, se hizo commit con cambios.
            logging.info("Proceso principal completado: Se realizó un commit con cambios efectivos.")

            if args.modo_test:
                # Si estamos en modo test, intentar hacer push
                logging.info("Modo Test activado: Intentando hacer push a origin...")
                # Obtener rama de trabajo desde settings
                ramaPush = getattr(settings, 'RAMATRABAJO', 'main') # Fallback a 'main' si no está definida
                if manejadorGit.hacerPush(settings.RUTACLON, ramaPush):
                    logging.info(f"Modo Test: Push a la rama '{ramaPush}' realizado con éxito.")
                    sys.exit(0) # Éxito total (código 0)
                else:
                    # El push falló (manejadorGit ya logueó el error)
                    logging.error(f"Modo Test: Falló el push a la rama '{ramaPush}'. El commit se realizó localmente.")
                    # Registrar fallo de PUSH en historial? Opcional.
                    # historial = cargarHistorial()
                    # historial.append(f"[ERROR] MODO TEST: Commit local OK, pero PUSH falló a rama {ramaPush}")
                    # guardarHistorial(historial)
                    sys.exit(1) # Salir con error (commit hecho, push falló)
            else:
                # Modo test desactivado, éxito local.
                logging.info("Modo Test desactivado. Commit realizado localmente, no se hizo push.")
                sys.exit(0) # Éxito (commit local, código 0)
        else:
            # El ciclo no terminó con un commit exitoso (ya se loguearon detalles y guardó historial)
            logging.warning("Proceso principal finalizó sin realizar un commit efectivo o con errores (ver historial y logs).")
            sys.exit(1) # Salir con código de error/advertencia genérico

    except Exception as e:
        # Captura de cualquier error fatal no manejado en ejecutarProcesoPrincipal o en el flujo __main__
        logging.critical(f"Error fatal no manejado en el bloque principal __main__: {e}", exc_info=True)
        # Intentar grabar un último mensaje en el historial
        try:
            historial = cargarHistorial() # Recargar por si acaso
            historial.append(f"[ERROR FATAL] Error no manejado en __main__: {e}")
            guardarHistorial(historial)
        except Exception as e_hist_fatal:
            logging.error(f"No se pudo ni siquiera guardar el historial del error fatal: {e_hist_fatal}")
        sys.exit(2) # Código de error grave