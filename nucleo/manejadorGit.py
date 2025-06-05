# nucleo/manejadorGit.py
import subprocess
import os
import logging
import shutil
from typing import Set, Optional, List # Para type hints
from config import settings # Para RAMATRABAJO en eliminarRama

log = logging.getLogger(__name__)


def ejecutarComando(comando: List[str], cwd: Optional[str] = None, check: bool = True, return_output: bool = False):
    """
    Ejecuta un comando de shell.
    Args:
        comando (list): El comando y sus argumentos.
        cwd (str, optional): Directorio de trabajo. Default es el actual.
        check (bool, optional): Si es True, lanza CalledProcessError si el comando falla. Default True.
        return_output (bool, optional): Si es True, devuelve (True, stdout) en éxito o (False, stderr) en fallo. Si es False, devuelve solo True/False. Default False.

    Returns:
        bool or tuple: Depende de return_output y check.
                      Si return_output=False: True en éxito, False en fallo (si check=False y comando falla).
                      Si return_output=True: (True, stdout) en éxito, (False, error_output) en fallo (si check=False y comando falla).
                      Lanza CalledProcessError si check=True y el comando falla.
    """
    logPrefix = "ejecutarComando:"
    rutaEjecucion = cwd or os.getcwd()
    comandoStr = ' '.join(comando)
    log.debug(
        f"{logPrefix} Ejecutando '{comandoStr}' en {rutaEjecucion} (check={check}, return_output={return_output})")
    try:
        # Llamada a subprocess.run
        resultado = subprocess.run(
            comando, cwd=cwd, check=check, capture_output=True, text=True, encoding='utf-8', errors='ignore')

        # Si check=True, cualquier código de retorno != 0 ya habría lanzado CalledProcessError.
        # Si llegamos aquí y check=True, el comando tuvo éxito (returncode == 0).

        # Si check=False, debemos verificar el returncode manualmente.
        if not check and resultado.returncode != 0:
            # El comando falló (código de retorno != 0), pero no se lanzó una excepción porque check=False.
            stderrLimpio = resultado.stderr.strip() if resultado.stderr else ""
            stdoutLimpio = resultado.stdout.strip() if resultado.stdout else ""
            
            # Determinar si es un caso especial donde un código no-cero es esperado y no un error de ejecución.
            # Caso específico: 'git diff --staged --quiet' devuelve 1 si hay cambios staged.
            esCasoEspecialDiffStagedQuietConCambios = (
                comando == ['git', 'diff', '--staged', '--quiet'] and 
                resultado.returncode == 1
            )

            if esCasoEspecialDiffStagedQuietConCambios:
                # Para 'git diff --staged --quiet' código 1, este es un resultado esperado, no un error de ejecución.
                log.info(
                    f"{logPrefix} Comando '{comandoStr}' resultó en código {resultado.returncode} (esperado, indica cambios staged).")
                if stderrLimpio: # No se espera stderr en este caso, si existe es un error.
                    log.error(f"{logPrefix} Stderr (inesperado para diff --quiet con código 1): {stderrLimpio}")
            else:
                # Para otros comandos o 'git diff --staged --quiet' con código > 1 (error real de ejecución).
                log.error(
                    f"{logPrefix} Comando '{comandoStr}' falló con código {resultado.returncode} (check=False).")
                if stderrLimpio:
                    log.error(f"{logPrefix} Stderr: {stderrLimpio}")
            
            if stdoutLimpio: # Loguear stdout si existe, incluso con código no cero.
                log.debug(f"{logPrefix} Stdout (con código no cero {resultado.returncode}): {stdoutLimpio}")
            
            # La lógica de retorno se mantiene: si returncode !=0 y check=False, la función devuelve "fallo"
            # para que el llamador decida cómo interpretar ese "fallo" según el comando específico.
            # El mensaje de error prioriza stderr si existe.
            error_message = stderrLimpio or f"Comando '{comandoStr}' resultó en código {resultado.returncode}"
            return (False, error_message) if return_output else False

        # Si llegamos aquí, el comando fue exitoso:
        # (check=True y no hubo excepción) O (check=False y resultado.returncode == 0)
        stdoutLimpio = resultado.stdout.strip() if resultado.stdout else ""
        stderrLimpio = resultado.stderr.strip() if resultado.stderr else ""

        if stderrLimpio and resultado.returncode == 0:  # A veces Git escribe a stderr info no crítica
            log.debug(f"{logPrefix} Stderr (info no crítica, código 0): {stderrLimpio}")
        if stdoutLimpio:
            log.debug(f"{logPrefix} Stdout: {stdoutLimpio}")

        log.debug(
            f"{logPrefix} Comando '{comandoStr}' ejecutado con éxito (código {resultado.returncode}).")
        return (True, stdoutLimpio) if return_output else True

    except FileNotFoundError:
        log.error(
            f"{logPrefix} Error - Comando '{comando[0]}' no encontrado. ¿Está Git instalado y en el PATH?")
        if check:
            raise
        return (False, f"Comando '{comando[0]}' no encontrado.") if return_output else False
    except subprocess.CalledProcessError as e: # Solo se activa si check=True
        stderrLimpio = e.stderr.strip() if e.stderr else ""
        stdoutLimpio = e.stdout.strip() if e.stdout else "" # A veces hay salida útil incluso en error
        log.error(
            f"{logPrefix} Error al ejecutar '{comandoStr}'. Código: {e.returncode}")
        if stderrLimpio:
            log.error(f"{logPrefix} Stderr: {stderrLimpio}")
        if stdoutLimpio:
            log.debug(f"{logPrefix} Stdout (en error): {stdoutLimpio}")
        if check: # Si check es True, la excepción se propaga
            raise
        # Si check es False, este bloque no debería alcanzarse, pero por si acaso:
        error_message_ex = stderrLimpio or f"Comando '{comandoStr}' falló con código {e.returncode} (CalledProcessError)"
        return (False, error_message_ex) if return_output else False
    except Exception as e:
        log.error(
            f"{logPrefix} Error inesperado ejecutando '{comandoStr}': {type(e).__name__} - {e}", exc_info=True)
        if check:
            raise
        return (False, f"Error inesperado: {type(e).__name__} - {e}") if return_output else False


def obtenerUrlRemota(nombreRemoto: str, rutaRepo: str) -> Optional[str]:
    """Obtiene la URL configurada para un remote específico."""
    comando = ['git', 'remote', 'get-url', nombreRemoto]
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


def establecerUrlRemota(nombreRemoto: str, nuevaUrl: str, rutaRepo: str) -> bool:
    """Establece la URL para un remote específico."""
    logPrefix = "establecerUrlRemota:"
    comando_set = ['git', 'remote', 'set-url', nombreRemoto, nuevaUrl]
    comando_add = ['git', 'remote', 'add', nombreRemoto, nuevaUrl]

    log.info(
        f"{logPrefix} Intentando establecer URL para '{nombreRemoto}' a: {nuevaUrl}")
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


def clonarOActualizarRepo(repoUrl: str, rutaLocal: str, ramaTrabajo: str) -> bool:
    """Gestiona clonado/actualización, asegura limpieza y rama correcta."""
    logPrefix = "clonarOActualizarRepo:"
    log.info(
        f"{logPrefix} Gestionando repo {repoUrl} en {rutaLocal} (rama: {ramaTrabajo})")
    ramaPrincipalDefault = "main" 
    ramaPrincipal = ramaPrincipalDefault

    gitDir = os.path.join(rutaLocal, '.git')
    repoExiste = os.path.isdir(gitDir)

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

        if not ejecutarComando(['git', 'clone', repoUrl, rutaLocal], check=False): 
            log.error(f"{logPrefix} Falló la clonación.")
            return False
        log.info(f"{logPrefix} Repositorio clonado.")
        repoExiste = True

    if repoExiste:
        log.info(f"{logPrefix} Verificando URL del remote 'origin'...")
        urlActual = obtenerUrlRemota("origin", rutaLocal)
        if not urlActual:
            log.warning(
                f"{logPrefix} Remote 'origin' no encontrado o sin URL. Estableciendo a {repoUrl}")
            if not establecerUrlRemota("origin", repoUrl, rutaLocal): return False
        elif urlActual != repoUrl:
            log.warning(
                f"{logPrefix} URL de 'origin' difiere ({urlActual}). Corrigiendo a {repoUrl}")
            if not establecerUrlRemota("origin", repoUrl, rutaLocal): return False

        log.info(f"{logPrefix} Limpiando estado local (fetch, checkout a principal, reset, clean)...")

        # --- Manejo de git fetch con reintento y prune ---
        fetch_success, fetch_error_output = ejecutarComando(
            ['git', 'fetch', 'origin'], cwd=rutaLocal, check=False, return_output=True
        )
        if not fetch_success:
            log.warning(f"{logPrefix} 'git fetch origin' falló. Error: {fetch_error_output}")
            if "cannot lock ref" in fetch_error_output or "remote-tracking branch" in fetch_error_output: # Añadidas más palabras clave
                log.info(f"{logPrefix} Error de fetch sugiere referencias obsoletas. Ejecutando 'git remote prune origin' y reintentando fetch...")
                prune_success, prune_output = ejecutarComando(
                    ['git', 'remote', 'prune', 'origin'], cwd=rutaLocal, check=False, return_output=True
                )
                if prune_success:
                    log.info(f"{logPrefix} 'git remote prune origin' ejecutado. Salida: {prune_output}")
                else:
                    log.warning(f"{logPrefix} 'git remote prune origin' falló. Salida: {prune_output}")

                fetch_success, fetch_error_output = ejecutarComando(
                    ['git', 'fetch', 'origin'], cwd=rutaLocal, check=False, return_output=True
                )
                if not fetch_success:
                    log.error(f"{logPrefix} 'git fetch origin' falló incluso después de prune. Error: {fetch_error_output}. Abortando.")
                    return False
            else: # Otro tipo de error de fetch
                log.error(f"{logPrefix} 'git fetch origin' falló con un error no recuperable automáticamente. Error: {fetch_error_output}. Abortando.")
                return False
        log.info(f"{logPrefix} 'git fetch origin' exitoso.")
        # --- Fin Manejo de git fetch ---


        # Intentar determinar la rama principal remota
        success_remote_show, output_remote_show = ejecutarComando(
            ['git', 'remote', 'show', 'origin'], cwd=rutaLocal, check=False, return_output=True)
        if success_remote_show:
            for line in output_remote_show.splitlines():
                if 'HEAD branch:' in line:
                    ramaDetectada = line.split(':')[1].strip()
                    if ramaDetectada and ramaDetectada != '(unknown)' and ramaDetectada != '(ninguna)': 
                        ramaPrincipal = ramaDetectada
                        log.info(
                            f"{logPrefix} Rama principal remota detectada (vía 'remote show'): '{ramaPrincipal}'")
                        break
            else: log.warning(f"{logPrefix} No se pudo determinar rama HEAD remota de 'origin' vía 'remote show'.")
        else: log.warning(f"{logPrefix} Falló 'git remote show origin'. Error: {output_remote_show}.")
        
        if ramaPrincipal == ramaPrincipalDefault: # Si 'remote show' no funcionó o no encontró nada
            log.info(f"{logPrefix} Intentando detectar rama principal vía 'symbolic-ref'.")
            success_symbolic_ref, output_symbolic_ref = ejecutarComando(
                ['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], cwd=rutaLocal, check=False, return_output=True
            )
            if success_symbolic_ref and output_symbolic_ref:
                # output_symbolic_ref será algo como 'refs/remotes/origin/main'
                ref_parts = output_symbolic_ref.split('/')
                if len(ref_parts) > 0:
                    ramaDetectadaSym = ref_parts[-1]
                    ramaPrincipal = ramaDetectadaSym
                    log.info(f"{logPrefix} Rama principal remota detectada (vía 'symbolic-ref'): '{ramaPrincipal}'")
            else:
                log.warning(f"{logPrefix} No se pudo determinar rama HEAD remota vía 'symbolic-ref'. Usando default '{ramaPrincipalDefault}'.")
        
        # Checkout a la rama principal detectada (o default)
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal, check=False):
            log.warning(f"{logPrefix} Checkout a rama principal '{ramaPrincipal}' falló. Intentando 'master' como fallback...")
            if not ejecutarComando(['git', 'checkout', 'master'], cwd=rutaLocal, check=False):
                log.error(f"{logPrefix} Falló checkout a '{ramaPrincipal}' y a 'master'. Abortando limpieza crítica."); return False
            else: ramaPrincipal = "master" 
        
        # Reset --hard a la versión remota de la rama principal
        if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaPrincipal}'], cwd=rutaLocal, check=False):
            log.error(f"{logPrefix} Falló 'git reset --hard origin/{ramaPrincipal}'. Repo podría estar inconsistente. ¿Existe 'origin/{ramaPrincipal}' remotamente?"); return False
        
        if not ejecutarComando(['git', 'clean', '-fdx', '-e', '.orion_meta/'], cwd=rutaLocal, check=False):
            log.warning(f"{logPrefix} Falló 'git clean', no es crítico pero podría haber archivos extra.")

        log.info(f"{logPrefix} Asegurando rama de trabajo '{ramaTrabajo}'...")
        rama_actual_local = obtener_rama_actual(rutaLocal)

        if rama_actual_local == ramaTrabajo:
            log.info(f"{logPrefix} Ya en la rama de trabajo '{ramaTrabajo}'.")
            if existe_rama(rutaLocal, ramaTrabajo, remote_only=True):
                log.info(f"{logPrefix} Intentando actualizar '{ramaTrabajo}' desde 'origin/{ramaTrabajo}' (reset --hard).")
                if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaTrabajo}'], cwd=rutaLocal, check=False):
                    log.warning(f"{logPrefix} Falló 'git reset --hard origin/{ramaTrabajo}'. La rama local puede no estar sincronizada con la remota.")
        elif existe_rama(rutaLocal, ramaTrabajo, local_only=True):
            log.info(f"{logPrefix} Cambiando a rama local existente '{ramaTrabajo}'.")
            if not cambiar_a_rama_existente(rutaLocal, ramaTrabajo): return False
            if existe_rama(rutaLocal, ramaTrabajo, remote_only=True):
                log.info(f"{logPrefix} Intentando actualizar '{ramaTrabajo}' desde 'origin/{ramaTrabajo}' (reset --hard).")
                if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaTrabajo}'], cwd=rutaLocal, check=False):
                    log.warning(f"{logPrefix} Falló 'git reset --hard origin/{ramaTrabajo}'. La rama local puede no estar sincronizada con la remota.")
        elif existe_rama(rutaLocal, ramaTrabajo, remote_only=True):
            log.info(f"{logPrefix} Creando rama local '{ramaTrabajo}' desde 'origin/{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, f'origin/{ramaTrabajo}'], cwd=rutaLocal, check=False): # -b crea si no existe, -t trackea
                log.warning(f"{logPrefix} Falló la creación de '{ramaTrabajo}' desde 'origin/{ramaTrabajo}'. Intentando desde '{ramaPrincipal}'.")
                if not crear_y_cambiar_a_rama(rutaLocal, ramaTrabajo, ramaPrincipal):
                    log.error(f"{logPrefix} No se pudo crear '{ramaTrabajo}' ni desde 'origin/{ramaTrabajo}' ni desde '{ramaPrincipal}'.")
                    return False
        else: 
            log.info(f"{logPrefix} Creando nueva rama local '{ramaTrabajo}' desde '{ramaPrincipal}'.")
            if not crear_y_cambiar_a_rama(rutaLocal, ramaTrabajo, ramaPrincipal): return False
        
        log.info(f"{logPrefix} Repositorio listo en la rama '{ramaTrabajo}'.")
        return True
    else:
        log.error(f"{logPrefix} Error inesperado: El repositorio no existe después del intento de clonación.")
        return False

def hacerCommit(rutaRepo: str, mensaje: str) -> bool:
    """
    Añade todos los cambios y hace commit.
    Returns:
        bool: True si se realizó un NUEVO commit con éxito y este tuvo cambios reales.
              False si falló 'git add', 'git commit', no había nada que commitear,
              o si el commit no resultó en cambios efectivos.
    """
    logPrefix = "hacerCommit:"
    log.info(f"{logPrefix} Intentando commit en {rutaRepo}")

    if not ejecutarComando(['git', 'add', '-A'], cwd=rutaRepo, check=False):
        log.error(f"{logPrefix} Falló 'git add -A'. No se intentará commit.")
        return False

    # Verificar si hay cambios staged o untracked que serán commiteados
    # 'git status --porcelain' devuelve una lista de archivos con sus estados.
    # Si la salida está vacía, no hay cambios (staged, unstaged, untracked).
    # Si `git add -A` fue exitoso, los cambios unstaged y untracked ahora deberían estar staged.
    status_success, status_output = ejecutarComando(
        ['git', 'status', '--porcelain'], cwd=rutaRepo, check=False, return_output=True
    )

    if not status_success:
        log.error(f"{logPrefix} Falló 'git status --porcelain' para verificar cambios. No se intentará commit. Error: {status_output}")
        return False

    if not status_output.strip():
        log.warning(f"{logPrefix} No hay cambios detectados por 'git status --porcelain' después de 'git add -A'. Nada para commitear.")
        return False
    
    log.info(f"{logPrefix} Detectados cambios por 'git status --porcelain'. Salida:\n{status_output.strip()}")
    log.info(f"{logPrefix} Realizando commit con mensaje: '{mensaje[:80]}...'")

    commit_command_success, commit_error_output = ejecutarComando(
        ['git', 'commit', '-m', mensaje], cwd=rutaRepo, check=False, return_output=True
    )

    if not commit_command_success:
        # 'git commit' puede fallar si no hay nada que commitear (aunque 'git status --porcelain' haya mostrado algo,
        # como archivos untracked que no se añadieron por alguna razón, o si el add falló silenciosamente).
        # También puede fallar por otras razones (ej. hook pre-commit).
        log.error(f"{logPrefix} El comando 'git commit' falló. Error: {commit_error_output}")
        # Aquí podríamos intentar verificar si la falla fue por "nothing to commit"
        if "nothing to commit" in commit_error_output or "nada para hacer commit" in commit_error_output:
            log.warning(f"{logPrefix} 'git commit' indicó que no había nada que commitear, a pesar de la salida de 'git status --porcelain'.")
        return False
    
    log.info(f"{logPrefix} Comando 'git commit' ejecutado. Verificando si tuvo cambios reales...")
    if commitTuvoCambiosReales(rutaRepo):
        log.info(f"{logPrefix} Commit realizado con éxito y tuvo cambios reales.")
        return True
    else:
        log.warning(f"{logPrefix} 'git commit' se ejecutó, pero no resultó en cambios efectivos (posiblemente commit vacío o enmienda sin cambios).")
        # Aquí se podría considerar si revertir el commit vacío, pero la tarea solo es simplificar la detección.
        # Dejamos esa lógica para una tarea separada si es necesario.
        return False


def hacerPush(rutaRepo: str, rama: str, setUpstream: bool = False) -> bool:
    """Hace push de la rama a origin. Opcionalmente, establece upstream."""
    logPrefix = "hacerPush:"
    log.info(f"{logPrefix} Intentando push de rama '{rama}' a 'origin'...")
    comando = ['git', 'push']
    if setUpstream:
        comando.extend(['--set-upstream', 'origin', rama])
        log.info(f"{logPrefix} Con opción --set-upstream para 'origin/{rama}'.")
    else:
        comando.extend(['origin', rama])

    if not ejecutarComando(comando, cwd=rutaRepo, check=False):
        log.error(
            f"{logPrefix} Falló 'git push' para rama '{rama}'. Ver logs, credenciales, permisos, o si la rama remota necesita ser creada con --set-upstream.")
        return False
    log.info(f"{logPrefix} Push de rama '{rama}' a origin realizado con éxito.")
    return True


def descartarCambiosLocales(rutaRepo: str) -> bool:
    """Resetea HEAD y limpia archivos no rastreados."""
    logPrefix = "descartarCambiosLocales:"
    log.warning(
        f"{logPrefix} ¡ATENCIÓN! Descartando cambios locales en {rutaRepo}...")
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
        if not resetOk: msg += "'git reset --hard' falló. "
        if not cleanOk: msg += "'git clean -fdx' falló. "
        log.error(msg + "Repo puede estar inconsistente.")
        return False


def commitTuvoCambiosReales(rutaRepo: str) -> Optional[bool]:
    """Verifica si el commit más reciente (HEAD) introdujo cambios respecto a su padre (HEAD~1)."""
    logPrefix = "commitTuvoCambiosReales:"
    success_check_parent, _ = ejecutarComando(['git', 'rev-parse', 'HEAD~1'], cwd=rutaRepo, check=False, return_output=True)
    if not success_check_parent:
        log.info(f"{logPrefix} No se encontró HEAD~1 (probablemente primer commit). Asumiendo que tuvo cambios.")
        return True

    comando = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
    
    try:
        proc = subprocess.run(comando, cwd=rutaRepo, capture_output=True, text=True, check=False)
        if proc.returncode == 1: 
            log.info(f"{logPrefix} Sí, el último commit introdujo cambios (diff HEAD~1 HEAD).")
            return True
        elif proc.returncode == 0: 
            log.warning(
                f"{logPrefix} No, el último commit parece no tener cambios efectivos respecto a su padre.")
            return False
        else: 
            stderr = proc.stderr.strip() if proc.stderr else ""
            log.error(
                f"{logPrefix} Error inesperado verificando diff del commit (código {proc.returncode}). Stderr: {stderr}")
            return None 
    except Exception as e:
        log.error(
            f"{logPrefix} Excepción verificando diff del commit: {e}", exc_info=True)
        return None


def revertirCommitVacio(rutaRepo: str) -> bool:
    """Intenta hacer reset soft al commit anterior y luego descartar cambios."""
    logPrefix = "revertirCommitVacio:"
    log.info(f"{logPrefix} Intentando revertir commit sin cambios efectivos...")
    if ejecutarComando(['git', 'reset', '--soft', 'HEAD~1'], cwd=rutaRepo, check=False):
        log.info(
            f"{logPrefix} Reset soft a HEAD~1 OK. Descartando cambios restantes...")
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
            f"{logPrefix} Falló 'git reset --soft HEAD~1'. No se pudo revertir el commit (quizás es el primer commit).")
        return False


def obtenerArchivosModificadosStatus(rutaRepo: str) -> Optional[Set[str]]:
    """
    Obtiene una lista de archivos modificados, nuevos, eliminados, etc.,
    según 'git status --porcelain'. Devuelve un set de rutas relativas.
    Ignora entradas que terminen en '/' (directorios).
    Maneja correctamente nombres de archivo con espacios o caracteres especiales.
    Retorna un set vacío si no hay cambios.
    Retorna None en caso de error del comando git.
    """
    logPrefix = "obtenerArchivosModificadosStatus:"
    comando = ['git', 'status', '--porcelain']
    success, output = ejecutarComando(
        comando, cwd=rutaRepo, check=False, return_output=True)

    if not success:
        log.error(
            f"{logPrefix} Falló 'git status --porcelain'. Error: {output}")
        return None

    archivos_modificados: Set[str] = set()
    if not output: 
        log.info(
            f"{logPrefix} No hay cambios detectados por 'git status --porcelain'.")
        return archivos_modificados

    log.debug(f"{logPrefix} Salida cruda de 'git status --porcelain':\n{output}")

    for line in output.strip().splitlines():
        line_strip = line.strip()
        if not line_strip: continue

        status_codes = line_strip[:2]
        path_part_raw = line_strip[3:] 
        
        ruta_procesada = path_part_raw

        if status_codes.startswith('R') or status_codes.startswith('C'): 
            arrow_index = path_part_raw.find(' -> ')
            if arrow_index != -1:
                ruta_destino = path_part_raw[arrow_index + 4:]
                ruta_procesada = ruta_destino
            else: 
                log.warning(f"{logPrefix}   - Formato rename/copy inesperado (sin ' -> '): '{path_part_raw}'. Usando como está.")
        
        ruta_final_unescaped = ruta_procesada
        if ruta_procesada.startswith('"') and ruta_procesada.endswith('"'):
            path_in_quotes = ruta_procesada[1:-1]
            try:
                temp_unescaped = path_in_quotes.replace('\\\\', '\\').replace('\\"', '"').replace('\\t', '\t').replace('\\n', '\n')
                ruta_final_unescaped = temp_unescaped
            except Exception as e_esc:
                log.warning(f"{logPrefix}   - Falló procesamiento de escapes/comillas para '{ruta_procesada}': {e_esc}. Usando la ruta como estaba sin comillas: '{path_in_quotes}'")
                ruta_final_unescaped = path_in_quotes 

        if ruta_final_unescaped.endswith('/'): 
            continue

        if ruta_final_unescaped:
            ruta_normalizada = ruta_final_unescaped.replace(os.sep, '/') 
            archivos_modificados.add(ruta_normalizada)
        else: log.warning(f"{logPrefix}   - No se pudo extraer ruta válida de la línea al final: '{line_strip}'")

    log.info(f"{logPrefix} Archivos con cambios válidos según git status: {len(archivos_modificados)}")
    return archivos_modificados

# --- NUEVAS FUNCIONES ---

def obtener_rama_actual(ruta_repo: str) -> Optional[str]:
    """Obtiene el nombre de la rama actual."""
    logPrefix = "obtener_rama_actual:"
    success, output = ejecutarComando(['git', 'branch', '--show-current'], cwd=ruta_repo, check=False, return_output=True)
    if success and output.strip(): 
        rama = output.strip()
        log.info(f"{logPrefix} Rama actual: '{rama}'")
        return rama
    else:
        success_fallback, output_fallback = ejecutarComando(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=ruta_repo, check=False, return_output=True)
        if success_fallback and output_fallback:
            rama_fallback = output_fallback.strip()
            if rama_fallback == "HEAD": 
                log.warning(f"{logPrefix} Repositorio en estado 'detached HEAD'. No hay una rama actual específica.")
                return None
            log.info(f"{logPrefix} Rama actual (fallback rev-parse): '{rama_fallback}'")
            return rama_fallback
        log.error(f"{logPrefix} No se pudo obtener la rama actual. Error show-current: '{output}'. Error rev-parse: '{output_fallback}'.")
        return None


def existe_rama(ruta_repo: str, nombre_rama: str, local_only: bool = False, remote_only: bool = False) -> bool:
    """Verifica si una rama existe localmente y/o remotamente."""
    logPrefix = "existe_rama:"
    existe_local = False
    existe_remota = False

    if not remote_only: 
        success_local, output_local = ejecutarComando(['git', 'branch', '--list', nombre_rama], cwd=ruta_repo, check=False, return_output=True)
        if success_local and output_local.strip(): 
            existe_local = True
            log.debug(f"{logPrefix} Rama '{nombre_rama}' encontrada localmente.")
    
    if not local_only: 
        comando_remoto = ['git', 'ls-remote', '--exit-code', '--heads', 'origin', nombre_rama]
        remoto_check_success = ejecutarComando(comando_remoto, cwd=ruta_repo, check=False, return_output=False) 
        
        if remoto_check_success:
            existe_remota = True
            log.debug(f"{logPrefix} Rama '{nombre_rama}' encontrada remotamente en 'origin'.")
        else:
            log.debug(f"{logPrefix} Rama '{nombre_rama}' no encontrada remotamente en 'origin' (o error en ls-remote).")


    if local_only: return existe_local
    if remote_only: return existe_remota
    return existe_local or existe_remota 


def crear_y_cambiar_a_rama(ruta_repo: str, nombre_rama_nueva: str, rama_base: str) -> bool:
    """Crea una nueva rama a partir de rama_base y cambia a ella. Si ya existe localmente, solo cambia."""
    logPrefix = "crear_y_cambiar_a_rama:"
    
    rama_actual = obtener_rama_actual(ruta_repo)
    if rama_actual == nombre_rama_nueva:
        log.info(f"{logPrefix} Ya se encuentra en la rama '{nombre_rama_nueva}'. No se requiere acción.")
        return True

    if existe_rama(ruta_repo, nombre_rama_nueva, local_only=True):
        log.info(f"{logPrefix} La rama '{nombre_rama_nueva}' ya existe localmente. Cambiando a ella.")
        return cambiar_a_rama_existente(ruta_repo, nombre_rama_nueva)
    else: 
        log.info(f"{logPrefix} Creando nueva rama '{nombre_rama_nueva}' a partir de '{rama_base}'.")
        
        if not existe_rama(ruta_repo, rama_base, local_only=True):
            if existe_rama(ruta_repo, rama_base, remote_only=True):
                log.info(f"{logPrefix} Rama base '{rama_base}' no existe localmente, pero sí remota. Creando localmente desde 'origin/{rama_base}'.")
                if not ejecutarComando(['git', 'checkout', '-b', rama_base, f'origin/{rama_base}'], cwd=ruta_repo, check=False):
                    log.error(f"{logPrefix} No se pudo crear la rama base local '{rama_base}' desde 'origin/{rama_base}'. Abortando creación de '{nombre_rama_nueva}'.")
                    return False
            else:
                log.error(f"{logPrefix} La rama base '{rama_base}' no existe ni local ni remotamente. No se puede crear '{nombre_rama_nueva}'.")
                return False
        
        if rama_actual != rama_base:
            if not cambiar_a_rama_existente(ruta_repo, rama_base):
                log.error(f"{logPrefix} No se pudo cambiar a la rama base '{rama_base}' para crear '{nombre_rama_nueva}'.")
                return False
        
        if ejecutarComando(['git', 'checkout', '-b', nombre_rama_nueva, rama_base], cwd=ruta_repo, check=False):
            log.info(f"{logPrefix} Creada y cambiada a nueva rama '{nombre_rama_nueva}' desde '{rama_base}'.")
            return True
        else:
            log.error(f"{logPrefix} No se pudo crear la rama '{nombre_rama_nueva}' desde '{rama_base}' con 'checkout -b'.")
            return False


def cambiar_a_rama_existente(ruta_repo: str, nombre_rama: str) -> bool:
    """Cambia a una rama local existente."""
    logPrefix = "cambiar_a_rama_existente:"
    rama_actual = obtener_rama_actual(ruta_repo)
    if rama_actual == nombre_rama:
        log.info(f"{logPrefix} Ya se encuentra en la rama '{nombre_rama}'.")
        return True

    log.info(f"{logPrefix} Cambiando a rama existente '{nombre_rama}'.")
    if ejecutarComando(['git', 'checkout', nombre_rama], cwd=ruta_repo, check=False):
        log.info(f"{logPrefix} Cambiado a rama '{nombre_rama}' con éxito.")
        return True
    else:
        log.error(f"{logPrefix} No se pudo cambiar a la rama '{nombre_rama}'. Asegúrese que existe localmente y no hay conflictos/cambios sin guardar que lo impidan.")
        return False


def hacerCommitEspecifico(ruta_repo: str, mensaje: str, lista_archivos_a_commitear: List[str]) -> bool:
    """Añade archivos específicos y hace commit."""
    logPrefix = "hacerCommitEspecifico:"
    if not lista_archivos_a_commitear:
        log.warning(f"{logPrefix} Lista de archivos para commitear está vacía. No se hará commit.")
        return False

    log.info(f"{logPrefix} Intentando commit específico en {ruta_repo} para archivos: {lista_archivos_a_commitear}")

    archivos_validados_relativos = []
    for ruta_rel_archivo in lista_archivos_a_commitear:
        ruta_rel_limpia = os.path.normpath(ruta_rel_archivo).replace(os.sep, '/')
        ruta_abs_archivo = os.path.join(ruta_repo, ruta_rel_limpia)
        if not os.path.exists(ruta_abs_archivo):
            log.warning(f"{logPrefix} Archivo '{ruta_rel_limpia}' (Abs: '{ruta_abs_archivo}') no existe en el sistema de archivos. No se puede añadir al commit si no está ya trackeado y fue eliminado.")
            archivos_validados_relativos.append(ruta_rel_limpia)
        else:
            archivos_validados_relativos.append(ruta_rel_limpia)
    
    if not archivos_validados_relativos: 
        log.error(f"{logPrefix} Lista de archivos para commit (después de validación mínima) está vacía.")
        return False
    
    comando_add = ['git', 'add'] + archivos_validados_relativos
    if not ejecutarComando(comando_add, cwd=ruta_repo, check=False):
        log.error(f"{logPrefix} Falló 'git add' para archivos específicos: {archivos_validados_relativos}. No se intentará commit.")
        return False

    comando_diff = ['git', 'diff', '--staged', '--quiet', '--'] + archivos_validados_relativos
    try:
        proc_diff = subprocess.run(comando_diff, cwd=ruta_repo, capture_output=True, check=False)
        if proc_diff.returncode == 1: 
            log.info(f"{logPrefix} Detectados cambios en staging area para los archivos especificados.")
        elif proc_diff.returncode == 0: 
            log.warning(f"{logPrefix} No hay cambios en el staging area para los archivos especificados ({archivos_validados_relativos}). No se hará commit.")
            return False
        else: 
            stderr_diff = proc_diff.stderr.decode('utf-8', errors='ignore').strip()
            log.error(f"{logPrefix} Comando 'git diff --staged --quiet -- <archivos>' devolvió código inesperado {proc_diff.returncode}. Stderr: {stderr_diff}. Asumiendo que no hay cambios.")
            return False
    except Exception as e_diff_staged:
        log.error(f"{logPrefix} Error verificando cambios staged para archivos específicos: {e_diff_staged}. No se intentará commit.")
        return False

    log.info(f"{logPrefix} Realizando commit con mensaje: '{mensaje[:80]}...'")
    if ejecutarComando(['git', 'commit', '-m', mensaje], cwd=ruta_repo, check=False):
        log.info(f"{logPrefix} Comando 'git commit' para archivos específicos ejecutado (potencialmente).")
        if commitTuvoCambiosReales(ruta_repo):
            log.info(f"{logPrefix} Commit específico resultó en cambios efectivos.")
            return True
        else:
            log.warning(f"{logPrefix} Commit específico no resultó en cambios efectivos (posiblemente commit vacío).")
            return False
    else:
        log.error(f"{logPrefix} Falló 'git commit' para archivos específicos.")
        return False


def hacerMergeRama(ruta_repo: str, rama_origen: str, rama_destino_actual: str) -> bool:
    """Hace merge de rama_origen en rama_destino_actual."""
    logPrefix = "hacerMergeRama:"
    log.info(f"{logPrefix} Intentando merge de '{rama_origen}' en '{rama_destino_actual}'.")

    rama_actual = obtener_rama_actual(ruta_repo)
    if rama_actual != rama_destino_actual:
        log.info(f"{logPrefix} Rama actual es '{rama_actual}', cambiando a '{rama_destino_actual}' para el merge.")
        if not cambiar_a_rama_existente(ruta_repo, rama_destino_actual):
            log.error(f"{logPrefix} No se pudo cambiar a la rama destino '{rama_destino_actual}'. Merge abortado.")
            return False
    
    comando_merge = ['git', 'merge', '--no-ff', '--no-edit', rama_origen]
    success, output_err_or_info = ejecutarComando(comando_merge, cwd=ruta_repo, check=False, return_output=True)

    if success:
        if "Already up to date." in output_err_or_info:
            log.info(f"{logPrefix} Merge de '{rama_origen}' en '{rama_destino_actual}': Ya estaba actualizado.")
        else:
            log.info(f"{logPrefix} Merge de '{rama_origen}' en '{rama_destino_actual}' completado con éxito (nuevo commit de merge creado).")
        return True
    else:
        log.error(f"{logPrefix} Falló el merge de '{rama_origen}' en '{rama_destino_actual}'. Error/Info: {output_err_or_info}")
        if "conflict" in output_err_or_info.lower() or "conflicto" in output_err_or_info.lower():
            log.warning(f"{logPrefix} Conflicto de merge detectado. Abortando el merge...")
            if ejecutarComando(['git', 'merge', '--abort'], cwd=ruta_repo, check=False):
                log.info(f"{logPrefix} Merge abortado correctamente.")
            else:
                log.error(f"{logPrefix} No se pudo abortar el merge. El repositorio puede estar en estado de merge conflictivo.")
        return False


def eliminarRama(ruta_repo: str, nombre_rama: str, local: bool = True, remota: bool = False) -> bool:
    """Elimina una rama localmente y/o remotamente."""
    logPrefix = "eliminarRama:"
    exito_general = True

    if local:
        log.info(f"{logPrefix} Intentando eliminar rama local '{nombre_rama}'.")
        if not existe_rama(ruta_repo, nombre_rama, local_only=True):
            log.info(f"{logPrefix} Rama local '{nombre_rama}' no existe. No se necesita eliminar.")
        else:
            rama_actual = obtener_rama_actual(ruta_repo)
            if rama_actual == nombre_rama:
                rama_fallback = getattr(settings, 'RAMATRABAJO', None) or getattr(settings, 'RAMAPRINCIPAL', 'main') 
                log.info(f"{logPrefix} La rama a eliminar es la actual. Cambiando a '{rama_fallback}' primero.")
                if not cambiar_a_rama_existente(ruta_repo, rama_fallback):
                    log.error(f"{logPrefix} No se pudo cambiar de '{nombre_rama}' a '{rama_fallback}'. No se puede eliminar la rama local.")
                    exito_general = False
                else: 
                    if not ejecutarComando(['git', 'branch', '-D', nombre_rama], cwd=ruta_repo, check=False):
                        log.error(f"{logPrefix} Falló la eliminación de la rama local '{nombre_rama}'.")
                        exito_general = False
                    else: log.info(f"{logPrefix} Rama local '{nombre_rama}' eliminada con éxito.")
            else: 
                if not ejecutarComando(['git', 'branch', '-D', nombre_rama], cwd=ruta_repo, check=False):
                    log.error(f"{logPrefix} Falló la eliminación de la rama local '{nombre_rama}'.")
                    exito_general = False
                else: log.info(f"{logPrefix} Rama local '{nombre_rama}' eliminada con éxito.")
    
    if remota:
        log.info(f"{logPrefix} Intentando eliminar rama remota 'origin/{nombre_rama}'.")
        if not existe_rama(ruta_repo, nombre_rama, remote_only=True):
            log.info(f"{logPrefix} Rama remota 'origin/{nombre_rama}' no existe. No se necesita eliminar.")
        else:
            if not ejecutarComando(['git', 'push', 'origin', '--delete', nombre_rama], cwd=ruta_repo, check=False):
                log.error(f"{logPrefix} Falló la eliminación de la rama remota 'origin/{nombre_rama}'.")
                exito_general = False
            else:
                log.info(f"{logPrefix} Rama remota 'origin/{nombre_rama}' eliminada con éxito (o ya no existía).")
            
    return exito_general