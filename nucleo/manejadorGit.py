# nucleo/manejadorGit.py
import subprocess
import os
import logging
import shutil
from typing import Set, Optional, List # Para type hints
from config import settings # Para RAMATRABAJO en eliminarRama

log = logging.getLogger(__name__)


# MODIFICADO ### Añadir check y return_output
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
    ramaPrincipalDefault = "main" # Default, se intentará detectar la real
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
        if directorioPadre: # Asegurar que el directorio padre exista para clonar
            os.makedirs(directorioPadre, exist_ok=True)

        if not ejecutarComando(['git', 'clone', repoUrl, rutaLocal], check=True): # check=True, fallo es crítico
            log.error(f"{logPrefix} Falló la clonación.")
            return False
        log.info(f"{logPrefix} Repositorio clonado.")
        repoExiste = True # Actualizar estado

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
            else: log.warning(f"{logPrefix} No se pudo determinar rama HEAD remota. Usando default '{ramaPrincipalDefault}'.")
        else: log.warning(f"{logPrefix} Falló 'git remote show origin'. Usando default '{ramaPrincipalDefault}'.")

        log.info(f"{logPrefix} Limpiando estado local...")
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal, check=False):
            log.warning(f"Checkout a '{ramaPrincipal}' falló. Intentando 'master'...")
            if not ejecutarComando(['git', 'checkout', 'master'], cwd=rutaLocal, check=False):
                log.error("Falló checkout a rama principal/master. Abortando limpieza crítica."); return False
            else: ramaPrincipal = "master"

        if not ejecutarComando(['git', 'fetch', 'origin'], cwd=rutaLocal, check=False):
             log.warning(f"{logPrefix} 'git fetch origin' falló. Puede que el repo remoto no exista o no haya conexión.")
        if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaPrincipal}'], cwd=rutaLocal, check=False):
            log.error(f"Falló 'git reset --hard origin/{ramaPrincipal}'. Repo podría estar inconsistente."); return False
        if not ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaLocal, check=False):
            log.warning("Falló 'git clean -fdx', no es crítico pero podría haber archivos extra.")

        log.info(f"{logPrefix} Asegurando rama de trabajo '{ramaTrabajo}'...")
        if obtener_rama_actual(rutaLocal) == ramaTrabajo:
            log.info(f"{logPrefix} Ya en la rama de trabajo '{ramaTrabajo}'.")
        elif existe_rama(rutaLocal, ramaTrabajo, local_only=True):
            log.info(f"Cambiando a rama local existente '{ramaTrabajo}'.")
            if not cambiar_a_rama_existente(rutaLocal, ramaTrabajo): return False
        elif existe_rama(rutaLocal, ramaTrabajo, remote_only=True):
            log.info(f"Creando rama local '{ramaTrabajo}' desde 'origin/{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, f'origin/{ramaTrabajo}'], cwd=rutaLocal, check=True): return False
        else:
            log.info(f"Creando nueva rama local '{ramaTrabajo}' desde '{ramaPrincipal}'.")
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
        bool: True si se realizó un NUEVO commit con éxito.
              False si falló 'git add', 'git commit', o si no había nada que commitear.
    """
    logPrefix = "hacerCommit:"
    log.info(f"{logPrefix} Intentando commit en {rutaRepo}")

    if not ejecutarComando(['git', 'add', '-A'], cwd=rutaRepo, check=False):
        log.error(f"{logPrefix} Falló 'git add -A'. No se intentará commit.")
        return False

    try:
        resultado_diff = subprocess.run(
            ['git', 'diff', '--staged', '--quiet'], cwd=rutaRepo, capture_output=True, check=False)
        if resultado_diff.returncode == 1: # Hay cambios staged
            log.info(f"{logPrefix} Detectados cambios en staging area.")
            log.info(f"{logPrefix} Realizando commit con mensaje: '{mensaje[:80]}...'")
            if ejecutarComando(['git', 'commit', '-m', mensaje], cwd=rutaRepo, check=False):
                log.info(f"{logPrefix} Comando 'git commit' ejecutado con éxito.")
                return True
            else:
                log.error(f"{logPrefix} Falló 'git commit'.")
                return False
        elif resultado_diff.returncode == 0: # Nada staged
            log.warning(f"{logPrefix} No hay cambios en el staging area para hacer commit.")
            return False
        else: # Error en diff
            stderr_diff = resultado_diff.stderr.decode('utf-8', errors='ignore').strip()
            log.error(f"{logPrefix} Comando 'git diff --staged --quiet' devolvió código inesperado {resultado_diff.returncode}. Stderr: {stderr_diff}. Asumiendo que no hay cambios.")
            return False
    except Exception as e_diff:
        log.error(f"{logPrefix} Error verificando cambios staged: {e_diff}. No se intentará commit.")
        return False


def hacerPush(rutaRepo: str, rama: str) -> bool:
    """Hace push de la rama a origin."""
    logPrefix = "hacerPush:"
    log.info(f"{logPrefix} Intentando push de rama '{rama}' a 'origin'...")
    if not ejecutarComando(['git', 'push', 'origin', rama], cwd=rutaRepo, check=False): # check=False, el log ya informa del error
        log.error(
            f"{logPrefix} Falló 'git push origin {rama}'. Ver logs, credenciales, permisos.")
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
    comando = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
    try:
        resultado = subprocess.run(comando, cwd=rutaRepo, capture_output=True, check=False) # No usar check=True aquí
        if resultado.returncode == 1:
            log.info(f"{logPrefix} Sí, el último commit introdujo cambios.")
            return True
        elif resultado.returncode == 0:
            log.warning(
                f"{logPrefix} No, el último commit parece no tener cambios efectivos respecto a su padre.")
            return False
        else:
            stderr = resultado.stderr.decode('utf-8', errors='ignore').strip()
            log.error(
                f"{logPrefix} Error inesperado verificando diff del commit (código {resultado.returncode}). Stderr: {stderr}")
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
            f"{logPrefix} Falló 'git reset --soft HEAD~1'. No se pudo revertir el commit.")
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

        log.debug(f"{logPrefix} Procesando línea cruda: '{line_strip}'")
        parts = line_strip.split(maxsplit=1)
        if len(parts) < 2:
            log.warning(f"{logPrefix} Línea de status inesperada (formato no reconocido): '{line_strip}'. Saltando.")
            continue

        status_codes = parts[0]
        path_part_raw = parts[1]
        log.debug(f"{logPrefix}   - Status codes: '{status_codes}', Initial path part: '{path_part_raw}'")
        ruta_procesada = path_part_raw

        if status_codes.startswith('R') or status_codes.startswith('C'):
            arrow_index = path_part_raw.find(' -> ')
            if arrow_index != -1:
                ruta_destino = path_part_raw[arrow_index + 4:]
                log.debug(f"{logPrefix}   - Rename/Copy detected. Using destination: '{ruta_destino}'")
                ruta_procesada = ruta_destino
            else: log.warning(f"{logPrefix}   - Formato rename/copy inesperado (sin ' -> '): '{path_part_raw}'. Usando como está.")

        ruta_final_unescaped = ruta_procesada
        if ruta_procesada.startswith('"') and ruta_procesada.endswith('"'):
            path_in_quotes = ruta_procesada[1:-1]
            log.debug(f"{logPrefix}   - Path estaba entre comillas: '{path_in_quotes}'")
            try:
                # Importar codecs solo si es necesario aquí
                import codecs
                path_to_unescape = path_in_quotes.replace('\\\\', '\\')
                ruta_unescaped_val = codecs.decode(path_to_unescape, 'unicode_escape')
                log.debug(f"{logPrefix}   - Path después de quitar comillas y procesar escapes: '{ruta_unescaped_val}'")
                ruta_final_unescaped = ruta_unescaped_val
            except Exception as e_esc:
                log.warning(f"{logPrefix}   - Falló procesamiento de escapes/comillas para '{ruta_procesada}': {e_esc}. Usando la ruta como estaba.")

        if ruta_final_unescaped.endswith('/'):
            log.debug(f"{logPrefix}   - Ignorando entrada de directorio: '{ruta_final_unescaped}'")
            continue

        if ruta_final_unescaped:
            ruta_normalizada = ruta_final_unescaped.replace(os.sep, '/')
            log.debug(f"{logPrefix}   - Ruta final normalizada a añadir: '{ruta_normalizada}'")
            archivos_modificados.add(ruta_normalizada)
        else: log.warning(f"{logPrefix}   - No se pudo extraer ruta válida de la línea al final: '{line_strip}'")

    log.info(f"{logPrefix} Archivos con cambios válidos según git status: {len(archivos_modificados)}")
    log.debug(f"{logPrefix} Lista final de archivos modificados (set): {archivos_modificados}")
    return archivos_modificados

# --- NUEVAS FUNCIONES ---

def obtener_rama_actual(ruta_repo: str) -> Optional[str]:
    """Obtiene el nombre de la rama actual."""
    logPrefix = "obtener_rama_actual:"
    # git branch --show-current es más moderno y directo
    # git rev-parse --abbrev-ref HEAD también funciona, pero puede dar "HEAD" si está detached.
    success, output = ejecutarComando(['git', 'branch', '--show-current'], cwd=ruta_repo, check=False, return_output=True)
    if success and output:
        rama = output.strip()
        log.info(f"{logPrefix} Rama actual: '{rama}'")
        return rama
    else:
        # Fallback por si --show-current no está disponible o hay error
        success_fallback, output_fallback = ejecutarComando(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=ruta_repo, check=False, return_output=True)
        if success_fallback and output_fallback:
            rama_fallback = output_fallback.strip()
            if rama_fallback == "HEAD":
                log.warning(f"{logPrefix} Repositorio en estado 'detached HEAD'. No hay una rama actual específica.")
                return None
            log.info(f"{logPrefix} Rama actual (fallback): '{rama_fallback}'")
            return rama_fallback
        log.error(f"{logPrefix} No se pudo obtener la rama actual. Error: {output_fallback if not success_fallback else output}")
        return None


def existe_rama(ruta_repo: str, nombre_rama: str, local_only: bool = False, remote_only: bool = False) -> bool:
    """Verifica si una rama existe localmente y/o remotamente."""
    logPrefix = "existe_rama:"
    existe_local = False
    existe_remota = False

    if not remote_only: # Chequear local si no es remote_only o si es chequeo general
        # git branch --list <nombre_rama> devuelve el nombre si existe, vacío si no.
        success_local, output_local = ejecutarComando(['git', 'branch', '--list', nombre_rama], cwd=ruta_repo, check=False, return_output=True)
        if success_local and output_local.strip():
            existe_local = True
            log.debug(f"{logPrefix} Rama '{nombre_rama}' encontrada localmente.")
    
    if not local_only: # Chequear remota si no es local_only o si es chequeo general
        # git ls-remote --exit-code --heads origin <nombre_rama> devuelve 0 si existe, 2 si no.
        # Usamos ejecutarComando con check=False, así que miramos el booleano de éxito
        comando_remoto = ['git', 'ls-remote', '--exit-code', '--heads', 'origin', nombre_rama]
        remoto_check_success = ejecutarComando(comando_remoto, cwd=ruta_repo, check=False) # No necesitamos output, solo si comando tuvo éxito (exit code 0)
        if remoto_check_success: # Esto implica que el comando tuvo exit code 0
            existe_remota = True
            log.debug(f"{logPrefix} Rama '{nombre_rama}' encontrada remotamente en 'origin'.")

    if local_only: return existe_local
    if remote_only: return existe_remota
    return existe_local or existe_remota


def crear_y_cambiar_a_rama(ruta_repo: str, nombre_rama_nueva: str, rama_base: str) -> bool:
    """Crea una nueva rama a partir de rama_base y cambia a ella. Si ya existe, solo cambia."""
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
        # Asegurarse de estar en la rama base correcta primero si no lo estamos.
        if rama_actual != rama_base:
            if not cambiar_a_rama_existente(ruta_repo, rama_base):
                log.error(f"{logPrefix} No se pudo cambiar a la rama base '{rama_base}' para crear '{nombre_rama_nueva}'.")
                return False
        
        # Crear la nueva rama desde la rama_base (que ahora es la actual)
        if ejecutarComando(['git', 'checkout', '-b', nombre_rama_nueva], cwd=ruta_repo, check=False): # -b crea y cambia
            log.info(f"{logPrefix} Creada y cambiada a nueva rama '{nombre_rama_nueva}' desde '{rama_base}'.")
            return True
        else:
            # Si el checkout -b falla, podría ser por un nombre inválido u otro problema
            # Intentar un `git branch nombre_rama_nueva` y luego `git checkout nombre_rama_nueva` como fallback
            log.warning(f"{logPrefix} 'git checkout -b {nombre_rama_nueva}' falló. Intentando 'git branch' y luego 'git checkout'.")
            if ejecutarComando(['git', 'branch', nombre_rama_nueva, rama_base], cwd=ruta_repo, check=False):
                if cambiar_a_rama_existente(ruta_repo, nombre_rama_nueva):
                    log.info(f"{logPrefix} Creada (con git branch) y cambiada a nueva rama '{nombre_rama_nueva}'.")
                    return True
            log.error(f"{logPrefix} No se pudo crear la rama '{nombre_rama_nueva}' desde '{rama_base}'.")
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
        log.error(f"{logPrefix} No se pudo cambiar a la rama '{nombre_rama}'. Asegúrese que existe localmente y no hay conflictos.")
        return False


def hacerCommitEspecifico(ruta_repo: str, mensaje: str, lista_archivos_a_commitear: List[str]) -> bool:
    """Añade archivos específicos y hace commit."""
    logPrefix = "hacerCommitEspecifico:"
    if not lista_archivos_a_commitear:
        log.warning(f"{logPrefix} Lista de archivos para commitear está vacía. No se hará commit.")
        return False

    log.info(f"{logPrefix} Intentando commit específico en {ruta_repo} para archivos: {lista_archivos_a_commitear}")

    # Validar que todos los archivos existen antes de intentar 'git add'
    archivos_validados_relativos = []
    for ruta_rel_archivo in lista_archivos_a_commitear:
        ruta_abs_archivo = os.path.join(ruta_repo, ruta_rel_archivo)
        if not os.path.exists(ruta_abs_archivo):
            log.error(f"{logPrefix} Archivo '{ruta_rel_archivo}' (Abs: '{ruta_abs_archivo}') no existe. No se puede añadir al commit.")
            # Se podría decidir fallar aquí o continuar con los que sí existen. Por ahora, continuamos.
        else:
            archivos_validados_relativos.append(ruta_rel_archivo)
    
    if not archivos_validados_relativos:
        log.error(f"{logPrefix} Ninguno de los archivos especificados para commit existe. No se hará commit.")
        return False
    
    # Añadir solo los archivos especificados y validados
    comando_add = ['git', 'add'] + archivos_validados_relativos
    if not ejecutarComando(comando_add, cwd=ruta_repo, check=False):
        log.error(f"{logPrefix} Falló 'git add' para archivos específicos: {archivos_validados_relativos}. No se intentará commit.")
        return False

    # Verificar si hay cambios staged (similar a hacerCommit general)
    try:
        resultado_diff = subprocess.run(
            ['git', 'diff', '--staged', '--quiet'], cwd=ruta_repo, capture_output=True, check=False)
        if resultado_diff.returncode == 1: # Hay cambios staged
            log.info(f"{logPrefix} Detectados cambios en staging area para los archivos especificados.")
            log.info(f"{logPrefix} Realizando commit con mensaje: '{mensaje[:80]}...'")
            if ejecutarComando(['git', 'commit', '-m', mensaje], cwd=ruta_repo, check=False):
                log.info(f"{logPrefix} Comando 'git commit' para archivos específicos ejecutado con éxito.")
                return True
            else:
                log.error(f"{logPrefix} Falló 'git commit' para archivos específicos.")
                return False
        elif resultado_diff.returncode == 0: # Nada staged
            log.warning(f"{logPrefix} No hay cambios en el staging area para los archivos especificados. No se hará commit.")
            return False
        else: # Error en diff
            stderr_diff = resultado_diff.stderr.decode('utf-8', errors='ignore').strip()
            log.error(f"{logPrefix} Comando 'git diff --staged --quiet' devolvió código inesperado {resultado_diff.returncode}. Stderr: {stderr_diff}. Asumiendo que no hay cambios.")
            return False
    except Exception as e_diff:
        log.error(f"{logPrefix} Error verificando cambios staged: {e_diff}. No se intentará commit.")
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
    
    # Ejecutar merge. Usar --no-ff para crear siempre un commit de merge.
    # Podríamos añadir --no-edit si no queremos que se abra el editor para el mensaje de merge.
    comando_merge = ['git', 'merge', '--no-ff', '--no-edit', rama_origen]
    success, output_err = ejecutarComando(comando_merge, cwd=ruta_repo, check=False, return_output=True)

    if success:
        log.info(f"{logPrefix} Merge de '{rama_origen}' en '{rama_destino_actual}' completado con éxito.")
        return True
    else:
        log.error(f"{logPrefix} Falló el merge de '{rama_origen}' en '{rama_destino_actual}'. Error: {output_err}")
        # Comprobar si fue por conflicto
        if "conflict" in output_err.lower() or "conflicto" in output_err.lower():
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
        rama_actual = obtener_rama_actual(ruta_repo)
        if rama_actual == nombre_rama:
            rama_fallback = getattr(settings, 'RAMATRABAJO', 'main') # Usar RAMATRABAJO de settings o 'main'
            log.info(f"{logPrefix} La rama a eliminar es la actual. Cambiando a '{rama_fallback}' primero.")
            if not cambiar_a_rama_existente(ruta_repo, rama_fallback):
                log.error(f"{logPrefix} No se pudo cambiar de '{nombre_rama}' a '{rama_fallback}'. No se puede eliminar la rama local.")
                exito_general = False # Marcar fallo pero continuar si hay que borrar remota
            else: # Cambiado con éxito, proceder a borrar
                if not ejecutarComando(['git', 'branch', '-D', nombre_rama], cwd=ruta_repo, check=False):
                    log.error(f"{logPrefix} Falló la eliminación de la rama local '{nombre_rama}'.")
                    exito_general = False
                else: log.info(f"{logPrefix} Rama local '{nombre_rama}' eliminada con éxito.")
        else: # No es la rama actual, se puede borrar directamente
            if not ejecutarComando(['git', 'branch', '-D', nombre_rama], cwd=ruta_repo, check=False):
                log.error(f"{logPrefix} Falló la eliminación de la rama local '{nombre_rama}'.")
                exito_general = False
            else: log.info(f"{logPrefix} Rama local '{nombre_rama}' eliminada con éxito.")
    
    if remota:
        log.info(f"{logPrefix} Intentando eliminar rama remota 'origin/{nombre_rama}'.")
        if not ejecutarComando(['git', 'push', 'origin', '--delete', nombre_rama], cwd=ruta_repo, check=False):
            log.error(f"{logPrefix} Falló la eliminación de la rama remota 'origin/{nombre_rama}'.")
            exito_general = False
        else:
            log.info(f"{logPrefix} Rama remota 'origin/{nombre_rama}' eliminada con éxito (o ya no existía).")
            
    return exito_general