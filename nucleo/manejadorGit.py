# nucleo/manejadorGit.py
import subprocess
import os
import logging
import shutil

log = logging.getLogger(__name__)


# MODIFICADO ### Añadir check y return_output
def ejecutarComando(comando, cwd=None, check=True, return_output=False):
    """
    Ejecuta un comando de shell.
    Args:
        comando (list): El comando y sus argumentos.
        cwd (str, optional): Directorio de trabajo. Default es el actual.
        check (bool, optional): Si es True, lanza CalledProcessError si el comando falla. Default True.
        return_output (bool, optional): Si es True, devuelve (True, stdout) en éxito o (False, stderr) en fallo. Si es False, devuelve solo True/False. Default False.

    Returns:
        bool or tuple: Depende de return_output y check.
                      Si return_output=False: True en éxito, False en fallo (si check=False).
                      Si return_output=True: (True, stdout) en éxito, (False, stderr) en fallo (si check=False).
                      Lanza CalledProcessError si check=True y el comando falla.
    """
    logPrefix = "ejecutarComando:"
    rutaEjecucion = cwd or os.getcwd()
    comandoStr = ' '.join(comando)
    log.debug(
        f"{logPrefix} Ejecutando '{comandoStr}' en {rutaEjecucion} (check={check}, return_output={return_output})")
    try:
        resultado = subprocess.run(
            comando, cwd=cwd, check=check, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        stdoutLimpio = resultado.stdout.strip() if resultado.stdout else ""
        # Capturar aunque no haya error
        stderrLimpio = resultado.stderr.strip() if resultado.stderr else ""

        if stderrLimpio and resultado.returncode == 0:  # A veces Git escribe a stderr info no crítica
            log.debug(f"{logPrefix} Stderr (no error): {stderrLimpio}")
        if stdoutLimpio:
            log.debug(f"{logPrefix} Stdout: {stdoutLimpio}")

        log.debug(
            f"{logPrefix} Comando '{comandoStr}' ejecutado con éxito (código {resultado.returncode}).")
        return (True, stdoutLimpio) if return_output else True

    except FileNotFoundError:
        log.error(
            f"{logPrefix} Error - Comando '{comando[0]}' no encontrado. ¿Está Git instalado y en el PATH?")
        if check:
            raise  # Re-lanzar si check=True
        return (False, f"Comando '{comando[0]}' no encontrado.") if return_output else False
    except subprocess.CalledProcessError as e:
        stderrLimpio = e.stderr.strip() if e.stderr else ""
        # A veces hay salida útil incluso en error
        stdoutLimpio = e.stdout.strip() if e.stdout else ""
        log.error(
            f"{logPrefix} Error al ejecutar '{comandoStr}'. Código: {e.returncode}")
        if stderrLimpio:
            log.error(f"{logPrefix} Stderr: {stderrLimpio}")
        if stdoutLimpio:
            log.debug(f"{logPrefix} Stdout (en error): {stdoutLimpio}")
        if check:
            raise  # Re-lanzar si check=True
        # Devolver False y el stderr como mensaje de error si return_output=True
        return (False, stderrLimpio or f"Comando falló con código {e.returncode}") if return_output else False
    except Exception as e:
        log.error(
            f"{logPrefix} Error inesperado ejecutando '{comandoStr}': {e}", exc_info=True)
        if check:
            raise  # Re-lanzar si check=True
        return (False, f"Error inesperado: {e}") if return_output else False


# --- Funciones existentes (clonarOActualizarRepo, obtenerUrlRemota, establecerUrlRemota) sin cambios funcionales grandes ---
# ... (mantenerlas como estaban, asegurando que usan el nuevo ejecutarComando si es necesario) ...
def obtenerUrlRemota(nombreRemoto, rutaRepo):
    """Obtiene la URL configurada para un remote específico."""
    comando = ['git', 'remote', 'get-url', nombreRemoto]
    # Usamos check=False porque esperamos que falle si no existe
    success, output = ejecutarComando(
        comando, cwd=rutaRepo, check=False, return_output=True)
    if success:
        url = output.strip()
        log.debug(f"obtenerUrlRemota: URL actual para '{nombreRemoto}': {url}")
        return url
    else:
        log.warning(
            f"obtenerUrlRemota: No se pudo obtener URL para '{nombreRemoto}'. Error: {output}")
        return None


def establecerUrlRemota(nombreRemoto, nuevaUrl, rutaRepo):
    """Establece la URL para un remote específico."""
    logPrefix = "establecerUrlRemota:"
    comando_set = ['git', 'remote', 'set-url', nombreRemoto, nuevaUrl]
    comando_add = ['git', 'remote', 'add', nombreRemoto, nuevaUrl]

    log.info(
        f"{logPrefix} Intentando establecer URL para '{nombreRemoto}' a: {nuevaUrl}")
    # Intentar set-url primero
    success_set, err_set = ejecutarComando(
        comando_set, cwd=rutaRepo, check=False, return_output=True)
    if success_set:
        log.info(
            f"{logPrefix} URL para '{nombreRemoto}' actualizada (set-url) correctamente.")
        return True
    else:
        log.warning(
            f"{logPrefix} Falló 'set-url' para '{nombreRemoto}' (Error: {err_set}). Intentando 'add'...")
        success_add, err_add = ejecutarComando(
            comando_add, cwd=rutaRepo, check=False, return_output=True)
        if success_add:
            log.info(
                f"{logPrefix} Remote '{nombreRemoto}' añadido con URL correcta.")
            return True
        else:
            log.error(
                f"{logPrefix} Falló también 'add' para '{nombreRemoto}' (Error: {err_add}). No se pudo configurar la URL remota.")
            return False


def clonarOActualizarRepo(repoUrl, rutaLocal, ramaTrabajo):
    """Gestiona clonado/actualización, asegura limpieza y rama correcta."""
    logPrefix = "clonarOActualizarRepo:"
    log.info(
        f"{logPrefix} Gestionando repo {repoUrl} en {rutaLocal} (rama: {ramaTrabajo})")
    ramaPrincipalDefault = "main"
    ramaPrincipal = ramaPrincipalDefault

    gitDir = os.path.join(rutaLocal, '.git')
    repoExiste = os.path.isdir(gitDir)

    # --- Clonar si no existe ---
    if not repoExiste:
        log.info(
            f"{logPrefix} Repositorio no encontrado. Clonando desde {repoUrl}...")
        if os.path.exists(rutaLocal):
            log.warning(
                f"{logPrefix} Ruta {rutaLocal} existe pero no es repo Git. Eliminando.")
            try:
                shutil.rmtree(rutaLocal)
            except OSError as e:
                log.error(f"No se pudo eliminar {rutaLocal}: {e}")
                return False
        directorioPadre = os.path.dirname(rutaLocal)
        if directorioPadre:
            os.makedirs(directorioPadre, exist_ok=True)

        # Check=True aquí
        if not ejecutarComando(['git', 'clone', repoUrl, rutaLocal], check=True):
            log.error(f"{logPrefix} Falló la clonación.")
            return False
        log.info(f"{logPrefix} Repositorio clonado.")
        repoExiste = True

    # --- Asegurar URL de 'origin' ---
    if repoExiste:
        log.info(f"{logPrefix} Verificando URL del remote 'origin'...")
        urlActual = obtenerUrlRemota("origin", rutaLocal)
        if not urlActual:
            log.warning(
                f"{logPrefix} Remote 'origin' no encontrado o sin URL. Estableciendo a {repoUrl}")
            if not establecerUrlRemota("origin", repoUrl, rutaLocal):
                return False  # Fallo crítico si no se puede poner URL
        elif urlActual != repoUrl:
            log.warning(
                f"{logPrefix} URL de 'origin' difiere ({urlActual}). Corrigiendo a {repoUrl}")
            if not establecerUrlRemota("origin", repoUrl, rutaLocal):
                return False  # Fallo crítico

    # --- Limpieza, Actualización y Cambio de Rama ---
    if repoExiste:
        # Detectar rama principal remota (best-effort)
        success_remote, output_remote = ejecutarComando(
            ['git', 'remote', 'show', 'origin'], cwd=rutaLocal, check=False, return_output=True)
        if success_remote:
            for line in output_remote.splitlines():
                if 'HEAD branch:' in line:
                    ramaDetectada = line.split(':')[1].strip()
                    if ramaDetectada and ramaDetectada != '(unknown)':
                        ramaPrincipal = ramaDetectada
                        log.info(
                            f"{logPrefix} Rama principal remota detectada: '{ramaPrincipal}'")
                        break
            else:
                log.warning(
                    f"{logPrefix} No se pudo determinar rama HEAD remota. Usando default '{ramaPrincipal}'.")
        else:
            log.warning(
                f"{logPrefix} Falló 'git remote show origin'. Usando default '{ramaPrincipal}'.")

        # Limpiar estado: checkout a principal, fetch, reset hard, clean
        log.info(f"{logPrefix} Limpiando estado local...")
        # Intentar checkout a principal, luego master como fallback
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal, check=False):
            log.warning(
                f"Checkout a '{ramaPrincipal}' falló. Intentando 'master'...")
            if not ejecutarComando(['git', 'checkout', 'master'], cwd=rutaLocal, check=False):
                log.error("Falló checkout a rama principal/master. Abortando.")
                return False
            else:
                ramaPrincipal = "master"  # Actualizar si se usó master

        if not ejecutarComando(['git', 'fetch', 'origin'], cwd=rutaLocal):
            # Continuar con precaución
            log.warning("Falló 'git fetch origin'.")
        if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaPrincipal}'], cwd=rutaLocal):
            log.error("Falló 'git reset --hard'.")
            return False
        if not ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaLocal):
            log.warning("Falló 'git clean -fdx'.")  # No crítico

        # Asegurar rama de trabajo
        log.info(f"{logPrefix} Asegurando rama de trabajo '{ramaTrabajo}'...")
        # Verificar existencia local y remota
        _, ramas_locales_raw = ejecutarComando(
            ['git', 'branch', '--list', ramaTrabajo], cwd=rutaLocal, check=False, return_output=True)
        existeLocal = bool(ramas_locales_raw.strip())
        _, ramas_remotas_raw = ejecutarComando(
            ['git', 'ls-remote', '--heads', 'origin', ramaTrabajo], cwd=rutaLocal, check=False, return_output=True)
        existeRemota = bool(ramas_remotas_raw.strip())

        if existeLocal:
            log.info(f"Cambiando a rama local '{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', ramaTrabajo], cwd=rutaLocal):
                return False
            if existeRemota:
                log.info(
                    f"Reseteando '{ramaTrabajo}' a 'origin/{ramaTrabajo}'.")
                # Permitir fallo en reset, podría no ser crítico pero advertir
                if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaTrabajo}'], cwd=rutaLocal, check=False):
                    log.warning(
                        f"Fallo al resetear '{ramaTrabajo}' a su versión remota.")
            else:
                log.info(
                    f"Rama '{ramaTrabajo}' existe localmente pero no en origin.")
        elif existeRemota:
            log.info(
                f"Creando rama local '{ramaTrabajo}' desde 'origin/{ramaTrabajo}'.")
            # Checkout directo para rastrear automáticamente
            if not ejecutarComando(['git', 'checkout', ramaTrabajo], cwd=rutaLocal, check=False):
                # Fallback explícito si el anterior falla
                if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, f'origin/{ramaTrabajo}'], cwd=rutaLocal):
                    return False
        else:
            log.info(
                f"Creando nueva rama local '{ramaTrabajo}' desde '{ramaPrincipal}'.")
            if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, ramaPrincipal], cwd=rutaLocal):
                return False

        log.info(f"{logPrefix} Repositorio listo en la rama '{ramaTrabajo}'.")
        return True
    else:
        log.error(f"{logPrefix} Error inesperado: El repositorio no existe.")
        return False


def hacerCommit(rutaRepo, mensaje):
    """Añade todos los cambios y hace commit. Devuelve True si OK, False si falla 'git add' o 'git commit'."""
    logPrefix = "hacerCommit:"
    log.info(f"{logPrefix} Intentando commit en {rutaRepo}")

    if not ejecutarComando(['git', 'add', '-A'], cwd=rutaRepo):
        log.error(f"{logPrefix} Falló 'git add -A'.")
        return False  # Fallo crítico antes de commit

    # Verificar si hay algo staged ANTES de intentar el commit
    # 'git diff --staged --quiet' devuelve 0 si NADA staged, 1 si HAY algo staged
    hay_cambios_staged = False
    try:
        # Usamos check=False y miramos el returncode
        resultado_diff = subprocess.run(
            ['git', 'diff', '--staged', '--quiet'], cwd=rutaRepo, capture_output=True)
        if resultado_diff.returncode == 1:
            hay_cambios_staged = True
            log.info(f"{logPrefix} Detectados cambios en staging area.")
        elif resultado_diff.returncode == 0:
            log.warning(
                f"{logPrefix} No hay cambios en el staging area para hacer commit.")
            # Se considera éxito si no había nada que hacer, no falló el comando
            return True
        else:
            # Código de retorno inesperado de git diff
            log.error(
                f"{logPrefix} Comando 'git diff --staged --quiet' devolvió código inesperado {resultado_diff.returncode}. Asumiendo que no hay cambios.")
            return True  # Considerar éxito para no bloquear innecesariamente
    except Exception as e_diff:
        log.error(
            f"{logPrefix} Error verificando cambios staged: {e_diff}. Intentando commit igualmente...")
        # Forzar intento de commit si la verificación falla
        hay_cambios_staged = True

    # Si detectamos cambios staged (o falló la detección), intentar commit
    if hay_cambios_staged:
        log.info(
            f"{logPrefix} Realizando commit con mensaje: '{mensaje[:80]}...'")
        if not ejecutarComando(['git', 'commit', '-m', mensaje], cwd=rutaRepo):
            # El error ya se logueó en ejecutarComando
            log.error(f"{logPrefix} Falló 'git commit'.")
            return False  # Falló el commit
        else:
            log.info(f"{logPrefix} Comando 'git commit' ejecutado.")
            # Ahora, la verificación de si tuvo efecto se hace DESPUÉS de llamar a esta función
            return True
    else:
        # Llegamos aquí si 'git diff' indicó que no había cambios
        return True  # Éxito (no había nada que hacer)


def hacerPush(rutaRepo, rama):
    """Hace push de la rama a origin."""
    logPrefix = "hacerPush:"
    log.info(f"{logPrefix} Intentando push de rama '{rama}' a 'origin'...")
    if not ejecutarComando(['git', 'push', 'origin', rama], cwd=rutaRepo):
        log.error(
            f"{logPrefix} Falló 'git push origin {rama}'. Ver logs, credenciales, permisos.")
        return False
    log.info(f"{logPrefix} Push de rama '{rama}' a origin realizado con éxito.")
    return True


def descartarCambiosLocales(rutaRepo):
    """Resetea HEAD y limpia archivos no rastreados."""
    logPrefix = "descartarCambiosLocales:"
    log.warning(
        f"{logPrefix} ¡ATENCIÓN! Descartando cambios locales en {rutaRepo}...")
    # Usamos check=False para loguear fallos específicos sin detener todo
    resetOk = ejecutarComando(
        ['git', 'reset', '--hard', 'HEAD'], cwd=rutaRepo, check=False)
    cleanOk = ejecutarComando(
        ['git', 'clean', '-fdx'], cwd=rutaRepo, check=False)

    if resetOk and cleanOk:
        log.info(
            f"{logPrefix} Cambios locales descartados (reset --hard + clean -fdx).")
        return True
    else:
        msg = f"{logPrefix} Falló al descartar cambios. "
        if not resetOk:
            msg += "'git reset --hard' falló. "
        if not cleanOk:
            msg += "'git clean -fdx' falló. "
        log.error(msg + "Repo puede estar inconsistente.")
        return False

# ### NUEVO ### Helper para verificar si el último commit tuvo cambios


def commitTuvoCambiosReales(rutaRepo):
    """Verifica si el commit más reciente (HEAD) introdujo cambios respecto a su padre (HEAD~1)."""
    logPrefix = "commitTuvoCambiosReales:"
    comando = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
    try:
        # check=False, miramos el return code
        resultado = subprocess.run(comando, cwd=rutaRepo, capture_output=True)
        if resultado.returncode == 1:
            log.info(f"{logPrefix} Sí, el último commit introdujo cambios.")
            return True  # Código 1 = Hubo diferencias
        elif resultado.returncode == 0:
            log.warning(
                f"{logPrefix} No, el último commit parece no tener cambios efectivos respecto a su padre.")
            return False  # Código 0 = No hubo diferencias
        else:
            # Código inesperado
            stderr = resultado.stderr.decode('utf-8', errors='ignore').strip()
            log.error(
                f"{logPrefix} Error inesperado verificando diff del commit (código {resultado.returncode}). Stderr: {stderr}")
            return None  # Indicar fallo en la verificación
    except Exception as e:
        log.error(
            f"{logPrefix} Excepción verificando diff del commit: {e}", exc_info=True)
        return None  # Indicar fallo en la verificación

# ### NUEVO ### Helper para revertir commit vacío


def revertirCommitVacio(rutaRepo):
    """Intenta hacer reset soft al commit anterior y luego descartar cambios."""
    logPrefix = "revertirCommitVacio:"
    log.info(f"{logPrefix} Intentando revertir commit sin cambios efectivos...")
    # Reset suave para quitar el commit pero mantener los archivos (si los hubiera)
    if ejecutarComando(['git', 'reset', '--soft', 'HEAD~1'], cwd=rutaRepo, check=False):
        log.info(
            f"{logPrefix} Reset soft a HEAD~1 OK. Descartando cambios restantes...")
        # Ahora descartar cualquier cambio que hubiera quedado en staging/working dir
        if descartarCambiosLocales(rutaRepo):
            log.info(
                f"{logPrefix} Commit vacío revertido y área de trabajo limpia.")
            return True
        else:
            log.error(
                f"{logPrefix} Reset soft OK, pero falló la limpieza posterior.")
            return False
    else:
        log.error(
            f"{logPrefix} Falló 'git reset --soft HEAD~1'. No se pudo revertir el commit.")
        return False

# ### NUEVO ### Helper para obtener lista de archivos modificados según 'git status'
def obtenerArchivosModificadosStatus(rutaRepo):
    """
    Obtiene una lista de archivos modificados, nuevos, eliminados, etc.,
    según 'git status --porcelain'. Devuelve un set de rutas relativas.
    Ignora entradas que terminen en '/' (directorios).
    Retorna None en caso de error del comando git.
    """
    logPrefix = "obtenerArchivosModificadosStatus:"
    comando = ['git', 'status', '--porcelain']
    # Usamos check=False y return_output=True para manejar errores y obtener salida
    success, output = ejecutarComando(
        comando, cwd=rutaRepo, check=False, return_output=True)

    if not success:
        log.error(
            f"{logPrefix} Falló 'git status --porcelain'. Error: {output}")
        return None

    archivos_modificados = set()
    if not output:
        log.info(
            f"{logPrefix} No hay cambios detectados por 'git status --porcelain'.")
        return archivos_modificados  # Vacío pero correcto

    # <-- DEBUGGING RAW OUTPUT -->
    log.debug(f"{logPrefix} Salida cruda de 'git status --porcelain':\n{output}")

    for line in output.strip().splitlines():
        line_strip = line.strip()
        # Ignorar líneas vacías
        if not line_strip:
            continue

        # <-- DEBUGGING LINE -->
        log.debug(f"{logPrefix} Procesando línea cruda: '{line_strip}'")

        # Extraer código de estado y parte de la ruta
        if len(line_strip) < 3:
             log.warning(f"{logPrefix} Línea inesperada (muy corta): '{line_strip}'. Saltando.")
             continue

        status_code = line_strip[:2]  # XY
        # Asumir que la ruta empieza después de 'XY ' (índice 3)
        # Necesitamos ser cuidadosos aquí si el formato varía
        path_part_raw = line_strip[3:]

        # <-- DEBUGGING INITIAL EXTRACTION -->
        log.debug(f"{logPrefix}   - Status: '{status_code}', Initial path part: '{path_part_raw}'")

        ruta_procesada = path_part_raw # Iniciar con la parte extraída

        # Manejar renombrados/copiados (R او C) : "origen" -> "destino"
        if status_code.startswith('R') or status_code.startswith('C'):
            try:
                arrow_index = path_part_raw.find(' -> ')
                if arrow_index != -1:
                    # El path relevante es el *destino*
                    ruta_destino = path_part_raw[arrow_index + 4:]
                    log.debug(f"{logPrefix}   - Rename/Copy detected. Using destination: '{ruta_destino}'")
                    ruta_procesada = ruta_destino # Actualizar con la ruta destino
                else:
                    log.warning(f"{logPrefix}   - Formato rename/copy inesperado: '{path_part_raw}'. Usando como está.")
                    # Continuar con ruta_procesada tal como estaba (path_part_raw)
            except Exception as e_rn:
                log.warning(f"{logPrefix}   - Error procesando rename/copy: {e_rn}. Usando path part original.")
                # Continuar con ruta_procesada tal como estaba

        # Quitar comillas y procesar escapes si existen
        ruta_final_unescaped = ruta_procesada # Variable para el resultado de este paso
        if ruta_procesada.startswith('"') and ruta_procesada.endswith('"'):
            path_in_quotes = ruta_procesada[1:-1]
            log.debug(f"{logPrefix}   - Path estaba entre comillas: '{path_in_quotes}'")
            try:
                # Intentar decodificar escapes (ej. \t, \n, \ooo)
                ruta_unescaped = codecs.decode(path_in_quotes, 'unicode_escape')
                # A veces unicode_escape puede fallar o no ser suficiente si hay escapes complejos
                # Podríamos necesitar 'string_escape' o manejo manual si esto falla.
                log.debug(f"{logPrefix}   - Path después de quitar comillas y procesar escapes: '{ruta_unescaped}'")
                ruta_final_unescaped = ruta_unescaped
            except Exception as e_esc:
                log.warning(f"{logPrefix}   - Falló procesamiento de escapes para '{path_in_quotes}': {e_esc}. Usando solo contenido sin comillas.")
                ruta_final_unescaped = path_in_quotes # Usar sin escapes si falló
        else:
             log.debug(f"{logPrefix}   - Path no estaba entre comillas.")
             # ruta_final_unescaped ya es ruta_procesada


        # --- Comprobación de Directorio y Normalización Final ---
        if ruta_final_unescaped.endswith('/'):
            log.debug(f"{logPrefix}   - Ignorando entrada de directorio: '{ruta_final_unescaped}'")
            continue # Saltar al siguiente 'line'

        if ruta_final_unescaped:
            # Normalizar separadores a '/' para consistencia interna
            ruta_normalizada = ruta_final_unescaped.replace(os.sep, '/')
            log.debug(f"{logPrefix}   - Ruta final normalizada a añadir: '{ruta_normalizada}'")

            # <<< ALERTA ESPECIAL SI DETECTAMOS EL TYPO >>>
            if ruta_normalizada == "emplateInicio.php":
                 log.critical(f"{logPrefix} ¡¡¡ALERTA!!! Se detectó 'emplateInicio.php' al procesar la línea: '{line_strip}'. Verificar pasos anteriores del parsing.")
            elif "emplateInicio.php" in ruta_normalizada:
                 log.warning(f"{logPrefix} Posible typo detectado: '{ruta_normalizada}' contiene 'emplate'. Línea original: '{line_strip}'")

            archivos_modificados.add(ruta_normalizada)
        else:
            log.warning(f"{logPrefix}   - No se pudo extraer ruta válida de la línea al final: '{line_strip}'")


    log.info(f"{logPrefix} Archivos con cambios válidos (ignorando directorios) según git status: {len(archivos_modificados)}")
    log.debug(f"{logPrefix} Lista final de archivos modificados (set): {archivos_modificados}") # Log del set final
    return archivos_modificados