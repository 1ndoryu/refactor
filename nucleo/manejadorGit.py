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
            # El comando falló, pero no se lanzó una excepción porque check=False.
            stderrLimpio = resultado.stderr.strip() if resultado.stderr else ""
            stdoutLimpio = resultado.stdout.strip() if resultado.stdout else "" # Puede haber stdout incluso en error
            log.error(
                f"{logPrefix} Comando '{comandoStr}' falló con código {resultado.returncode} (check=False).")
            if stderrLimpio:
                log.error(f"{logPrefix} Stderr: {stderrLimpio}")
            if stdoutLimpio:
                log.debug(f"{logPrefix} Stdout (en error): {stdoutLimpio}")
            
            error_message = stderrLimpio or f"Comando '{comandoStr}' falló con código {resultado.returncode}"
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

        if not ejecutarComando(['git', 'clone', repoUrl, rutaLocal], check=False): # check=False, el log ya informa del error
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

        # Intentar determinar la rama principal remota
        success_remote_show, output_remote_show = ejecutarComando(
            ['git', 'remote', 'show', 'origin'], cwd=rutaLocal, check=False, return_output=True)
        if success_remote_show:
            for line in output_remote_show.splitlines():
                if 'HEAD branch:' in line:
                    ramaDetectada = line.split(':')[1].strip()
                    if ramaDetectada and ramaDetectada != '(unknown)' and ramaDetectada != '(ninguna)': # Añadido '(ninguna)' por si acaso
                        ramaPrincipal = ramaDetectada
                        log.info(
                            f"{logPrefix} Rama principal remota detectada: '{ramaPrincipal}'")
                        break
            else: log.warning(f"{logPrefix} No se pudo determinar rama HEAD remota de 'origin' vía 'remote show'. Usando default '{ramaPrincipalDefault}'.")
        else: log.warning(f"{logPrefix} Falló 'git remote show origin'. Error: {output_remote_show}. Usando default '{ramaPrincipalDefault}'.")


        log.info(f"{logPrefix} Limpiando estado local (fetch, checkout a principal, reset, clean)...")
        if not ejecutarComando(['git', 'fetch', 'origin'], cwd=rutaLocal, check=False):
             log.warning(f"{logPrefix} 'git fetch origin' falló. Puede que el repo remoto no exista, no haya conexión, o no haya ramas para fetchear. Procediendo con cautela...")
        
        # Checkout a la rama principal detectada (o default)
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal, check=False):
            log.warning(f"{logPrefix} Checkout a rama principal '{ramaPrincipal}' falló. Intentando 'master' como fallback...")
            if not ejecutarComando(['git', 'checkout', 'master'], cwd=rutaLocal, check=False):
                log.error(f"{logPrefix} Falló checkout a '{ramaPrincipal}' y a 'master'. Abortando limpieza crítica."); return False
            else: ramaPrincipal = "master" # Actualizar ramaPrincipal si master funcionó
        
        # Reset --hard a la versión remota de la rama principal
        if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaPrincipal}'], cwd=rutaLocal, check=False):
            log.error(f"{logPrefix} Falló 'git reset --hard origin/{ramaPrincipal}'. Repo podría estar inconsistente. ¿Existe 'origin/{ramaPrincipal}' remotamente?"); return False
        
        if not ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaLocal, check=False):
            log.warning(f"{logPrefix} Falló 'git clean -fdx', no es crítico pero podría haber archivos extra.")

        log.info(f"{logPrefix} Asegurando rama de trabajo '{ramaTrabajo}'...")
        if obtener_rama_actual(rutaLocal) == ramaTrabajo:
            log.info(f"{logPrefix} Ya en la rama de trabajo '{ramaTrabajo}'.")
            # Opcional: intentar actualizarla desde origin/ramaTrabajo si existe
            if existe_rama(rutaLocal, ramaTrabajo, remote_only=True):
                log.info(f"{logPrefix} Intentando actualizar '{ramaTrabajo}' desde 'origin/{ramaTrabajo}'...")
                if not ejecutarComando(['git', 'pull', 'origin', ramaTrabajo], cwd=rutaLocal, check=False):
                    log.warning(f"{logPrefix} Falló 'git pull origin {ramaTrabajo}'. La rama local puede no estar actualizada con la remota.")

        elif existe_rama(rutaLocal, ramaTrabajo, local_only=True):
            log.info(f"{logPrefix} Cambiando a rama local existente '{ramaTrabajo}'.")
            if not cambiar_a_rama_existente(rutaLocal, ramaTrabajo): return False
            # Opcional: intentar actualizarla desde origin/ramaTrabajo si existe
            if existe_rama(rutaLocal, ramaTrabajo, remote_only=True):
                log.info(f"{logPrefix} Intentando actualizar '{ramaTrabajo}' desde 'origin/{ramaTrabajo}'...")
                if not ejecutarComando(['git', 'pull', 'origin', ramaTrabajo], cwd=rutaLocal, check=False):
                    log.warning(f"{logPrefix} Falló 'git pull origin {ramaTrabajo}'. La rama local puede no estar actualizada con la remota.")

        elif existe_rama(rutaLocal, ramaTrabajo, remote_only=True):
            log.info(f"{logPrefix} Creando rama local '{ramaTrabajo}' desde 'origin/{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, f'origin/{ramaTrabajo}'], cwd=rutaLocal, check=False):
                log.warning(f"{logPrefix} Falló la creación de '{ramaTrabajo}' desde 'origin/{ramaTrabajo}'. Intentando desde '{ramaPrincipal}'.")
                if not crear_y_cambiar_a_rama(rutaLocal, ramaTrabajo, ramaPrincipal):
                    log.error(f"{logPrefix} No se pudo crear '{ramaTrabajo}' ni desde 'origin/{ramaTrabajo}' ni desde '{ramaPrincipal}'.")
                    return False
        else: # No existe ni local ni remotamente (o no se pudo detectar remotamente)
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
        bool: True si se realizó un NUEVO commit con éxito.
              False si falló 'git add', 'git commit', o si no había nada que commitear.
    """
    logPrefix = "hacerCommit:"
    log.info(f"{logPrefix} Intentando commit en {rutaRepo}")

    if not ejecutarComando(['git', 'add', '-A'], cwd=rutaRepo, check=False):
        log.error(f"{logPrefix} Falló 'git add -A'. No se intentará commit.")
        return False

    # Verificar si hay cambios staged
    # 'git diff --staged --quiet' devuelve:
    # 0 si no hay diferencias (nada staged para commit)
    # 1 si hay diferencias (algo staged para commit)
    # >1 en otros errores
    diff_success, diff_output_or_error = ejecutarComando(
        ['git', 'diff', '--staged', '--quiet'], cwd=rutaRepo, check=False, return_output=True
    )
    # Aquí, diff_success es True si el comando diff en sí se ejecutó sin errores (exit code 0 o 1)
    # y False si el comando diff falló (p.ej. no es un repo git, código de salida > 1)

    # Para saber si hay algo que commitear, necesitamos verificar el *comportamiento* de `git diff --quiet`:
    # Necesitamos el código de salida del comando `diff` en sí.
    # Re-ejecutamos, pero esta vez para obtener el código de salida del subprocess.
    # Esta es una limitación de la abstracción actual de ejecutarComando si necesitamos el código de salida exacto
    # para la lógica de control y no solo éxito/fallo del comando.
    # Por ahora, una forma más simple es verificar `git status --porcelain`
    
    status_success, status_output = ejecutarComando(['git', 'status', '--porcelain'], cwd=rutaRepo, check=False, return_output=True)
    if not status_success:
        log.error(f"{logPrefix} Falló 'git status --porcelain' para verificar cambios. No se intentará commit. Error: {status_output}")
        return False

    if not status_output.strip(): # No hay salida, significa no hay cambios
        log.warning(f"{logPrefix} No hay cambios detectados por 'git status --porcelain' para hacer commit.")
        return False
    
    log.info(f"{logPrefix} Detectados cambios en staging area o working tree. Realizando commit con mensaje: '{mensaje[:80]}...'")
    if ejecutarComando(['git', 'commit', '-m', mensaje], cwd=rutaRepo, check=False):
        log.info(f"{logPrefix} Comando 'git commit' ejecutado con éxito (o no había nada que commitear después del add).")
        # Para ser más precisos, verificar si realmente se hizo un nuevo commit
        if commitTuvoCambiosReales(rutaRepo):
             return True
        else:
             log.warning(f"{logPrefix} 'git commit' no resultó en cambios efectivos (posiblemente commit vacío o enmienda sin cambios).")
             return False # O True si un commit "vacío" es aceptable
    else:
        log.error(f"{logPrefix} Falló 'git commit'.")
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
    # Verificar si hay un commit padre (HEAD~1 existe)
    success_check_parent, _ = ejecutarComando(['git', 'rev-parse', 'HEAD~1'], cwd=rutaRepo, check=False, return_output=True)
    if not success_check_parent:
        # Puede ser el primer commit del repositorio, que por definición tiene cambios.
        log.info(f"{logPrefix} No se encontró HEAD~1 (probablemente primer commit). Asumiendo que tuvo cambios.")
        return True

    comando = ['git', 'diff', 'HEAD~1', 'HEAD', '--quiet']
    # `git diff --quiet` devuelve 1 si hay diferencias, 0 si no.
    # Necesitamos el código de retorno real, no solo si el comando `ejecutarComando` tuvo éxito.
    # Esto requiere una modificación en cómo se manejan los códigos de retorno o una llamada directa a subprocess.
    # Por simplicidad aquí, usaremos la lógica actual y asumiremos que si `ejecutarComando` devuelve False
    # para `git diff --quiet` (con check=False), significa que hubo un código de salida != 0 (es decir, hay diferencias).
    
    try:
        proc = subprocess.run(comando, cwd=rutaRepo, capture_output=True, text=True, check=False)
        if proc.returncode == 1: # Hay diferencias
            log.info(f"{logPrefix} Sí, el último commit introdujo cambios (diff HEAD~1 HEAD).")
            return True
        elif proc.returncode == 0: # No hay diferencias
            log.warning(
                f"{logPrefix} No, el último commit parece no tener cambios efectivos respecto a su padre.")
            return False
        else: # Otro error
            stderr = proc.stderr.strip() if proc.stderr else ""
            log.error(
                f"{logPrefix} Error inesperado verificando diff del commit (código {proc.returncode}). Stderr: {stderr}")
            return None # Indeterminado
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
    if not output: # output puede ser "" si no hay cambios
        log.info(
            f"{logPrefix} No hay cambios detectados por 'git status --porcelain'.")
        return archivos_modificados

    log.debug(f"{logPrefix} Salida cruda de 'git status --porcelain':\n{output}")

    for line in output.strip().splitlines():
        line_strip = line.strip()
        if not line_strip: continue

        # log.debug(f"{logPrefix} Procesando línea cruda: '{line_strip}'")
        # El formato de --porcelain es "XY PATH" o "XY ORIG_PATH -> PATH" para renombrados/copiados
        status_codes = line_strip[:2]
        path_part_raw = line_strip[3:] # El resto es el path
        
        # log.debug(f"{logPrefix}   - Status codes: '{status_codes}', Initial path part: '{path_part_raw}'")
        ruta_procesada = path_part_raw

        if status_codes.startswith('R') or status_codes.startswith('C'): # Renombrado o Copiado
            # El formato es "XY ORIG_PATH -> PATH"
            # Necesitamos el PATH final
            arrow_index = path_part_raw.find(' -> ')
            if arrow_index != -1:
                ruta_destino = path_part_raw[arrow_index + 4:]
                # log.debug(f"{logPrefix}   - Rename/Copy detected. Using destination: '{ruta_destino}'")
                ruta_procesada = ruta_destino
            else: 
                log.warning(f"{logPrefix}   - Formato rename/copy inesperado (sin ' -> '): '{path_part_raw}'. Usando como está.")
                # Esto podría ser un problema si el nombre original contiene " -> "
        
        # Manejar archivos con espacios o caracteres especiales que Git pone entre comillas
        ruta_final_unescaped = ruta_procesada
        if ruta_procesada.startswith('"') and ruta_procesada.endswith('"'):
            path_in_quotes = ruta_procesada[1:-1]
            # log.debug(f"{logPrefix}   - Path estaba entre comillas: '{path_in_quotes}'")
            try:
                # Git usa escapes C-style para caracteres no estándar en nombres de archivo entre comillas.
                # Ej: un tabulador es \t, un newline es \n, una comilla doble es \", un backslash es \\.
                # Y caracteres > 127 son representados como secuencias octales, ej: \303\261 para ñ.
                # La librería `codecs.decode('unicode_escape')` puede manejar algunos, pero los octales no directamente así.
                # `bytes(path_in_quotes, 'ascii').decode('unicode_escape')` es una forma.
                # Sin embargo, para el caso de --porcelain, si está entre comillas, es porque el nombre *contiene* esos caracteres.
                # Si no hay secuencias de escape problemáticas, simplemente quitar comillas es suficiente.
                # Python str.encode().decode() puede ser más robusto para esto si se sabe la codificación.
                # Por ahora, un simple reemplazo de las secuencias de escape más comunes que Git usa.
                
                # Esta es una simplificación. Para un unescaping C completo, se necesitaría una librería o una función más compleja.
                temp_unescaped = path_in_quotes.replace('\\\\', '\\').replace('\\"', '"').replace('\\t', '\t').replace('\\n', '\n')
                # Para los octales, es más complejo. `ast.literal_eval` podría ayudar si fuera un string literal Python.
                # Dado que es salida de Git, el manejo más simple es usualmente asumir que los nombres de archivo no son *tan* exóticos.
                ruta_final_unescaped = temp_unescaped
                # log.debug(f"{logPrefix}   - Path después de quitar comillas y procesar escapes simples: '{ruta_final_unescaped}'")
            except Exception as e_esc:
                log.warning(f"{logPrefix}   - Falló procesamiento de escapes/comillas para '{ruta_procesada}': {e_esc}. Usando la ruta como estaba sin comillas: '{path_in_quotes}'")
                ruta_final_unescaped = path_in_quotes # Usar sin comillas como fallback

        if ruta_final_unescaped.endswith('/'): # Ignorar directorios
            # log.debug(f"{logPrefix}   - Ignorando entrada de directorio: '{ruta_final_unescaped}'")
            continue

        if ruta_final_unescaped:
            ruta_normalizada = ruta_final_unescaped.replace(os.sep, '/') # Asegurar formato con /
            # log.debug(f"{logPrefix}   - Ruta final normalizada a añadir: '{ruta_normalizada}'")
            archivos_modificados.add(ruta_normalizada)
        else: log.warning(f"{logPrefix}   - No se pudo extraer ruta válida de la línea al final: '{line_strip}'")

    log.info(f"{logPrefix} Archivos con cambios válidos según git status: {len(archivos_modificados)}")
    # log.debug(f"{logPrefix} Lista final de archivos modificados (set): {archivos_modificados}")
    return archivos_modificados

# --- NUEVAS FUNCIONES ---

def obtener_rama_actual(ruta_repo: str) -> Optional[str]:
    """Obtiene el nombre de la rama actual."""
    logPrefix = "obtener_rama_actual:"
    success, output = ejecutarComando(['git', 'branch', '--show-current'], cwd=ruta_repo, check=False, return_output=True)
    if success and output.strip(): # output podría ser solo whitespace si está detached y --show-current no da error
        rama = output.strip()
        log.info(f"{logPrefix} Rama actual: '{rama}'")
        return rama
    else:
        # Fallback por si --show-current no está disponible, falla, o da vacío (detached)
        success_fallback, output_fallback = ejecutarComando(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=ruta_repo, check=False, return_output=True)
        if success_fallback and output_fallback:
            rama_fallback = output_fallback.strip()
            if rama_fallback == "HEAD": # Detached HEAD
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

    if not remote_only: # Chequear local si no es remote_only o si es chequeo general
        success_local, output_local = ejecutarComando(['git', 'branch', '--list', nombre_rama], cwd=ruta_repo, check=False, return_output=True)
        if success_local and output_local.strip(): # Si output_local no está vacío, la rama existe
            existe_local = True
            log.debug(f"{logPrefix} Rama '{nombre_rama}' encontrada localmente.")
    
    if not local_only: # Chequear remota si no es local_only o si es chequeo general
        # `git ls-remote --exit-code --heads origin <nombre_rama>` devuelve 0 si existe, 2 si no, 128 si origin no existe.
        # `ejecutarComando` con `check=False` devolverá True si el código de salida es 0.
        comando_remoto = ['git', 'ls-remote', '--exit-code', '--heads', 'origin', nombre_rama]
        remoto_check_success = ejecutarComando(comando_remoto, cwd=ruta_repo, check=False, return_output=False) # Solo necesitamos saber si el comando tuvo éxito (exit code 0)
        
        if remoto_check_success:
            existe_remota = True
            log.debug(f"{logPrefix} Rama '{nombre_rama}' encontrada remotamente en 'origin'.")
        else:
            # Para depurar, podemos ver la salida si falló
            # _, err_msg = ejecutarComando(comando_remoto, cwd=ruta_repo, check=False, return_output=True)
            log.debug(f"{logPrefix} Rama '{nombre_rama}' no encontrada remotamente en 'origin' (o error en ls-remote).")


    if local_only: return existe_local
    if remote_only: return existe_remota
    return existe_local or existe_remota # Si es chequeo general, existe si está en cualquier lado


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
    else: # La rama no existe localmente, hay que crearla
        log.info(f"{logPrefix} Creando nueva rama '{nombre_rama_nueva}' a partir de '{rama_base}'.")
        
        # Asegurarse de estar en la rama base correcta o que la rama base exista
        if not existe_rama(ruta_repo, rama_base, local_only=True):
            # Intentar crear la rama base desde su contraparte remota si existe
            if existe_rama(ruta_repo, rama_base, remote_only=True):
                log.info(f"{logPrefix} Rama base '{rama_base}' no existe localmente, pero sí remota. Creando localmente desde 'origin/{rama_base}'.")
                if not ejecutarComando(['git', 'checkout', '-b', rama_base, f'origin/{rama_base}'], cwd=ruta_repo, check=False):
                    log.error(f"{logPrefix} No se pudo crear la rama base local '{rama_base}' desde 'origin/{rama_base}'. Abortando creación de '{nombre_rama_nueva}'.")
                    return False
            else:
                log.error(f"{logPrefix} La rama base '{rama_base}' no existe ni local ni remotamente. No se puede crear '{nombre_rama_nueva}'.")
                return False
        
        # Cambiar a la rama base si no estamos en ella
        if rama_actual != rama_base:
            if not cambiar_a_rama_existente(ruta_repo, rama_base):
                log.error(f"{logPrefix} No se pudo cambiar a la rama base '{rama_base}' para crear '{nombre_rama_nueva}'.")
                return False
        
        # Crear la nueva rama desde la rama_base (que ahora es la actual o existe)
        # `git checkout -b <nueva_rama> <punto_partida>` o `git branch <nueva_rama> <punto_partida>` y luego checkout
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
        # Podría haber cambios sin commitear que impiden el checkout.
        # Intentar un stash si ese es el caso. (Esto es una mejora, opcional)
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
        # Limpiar la ruta relativa por si acaso
        ruta_rel_limpia = os.path.normpath(ruta_rel_archivo).replace(os.sep, '/')
        ruta_abs_archivo = os.path.join(ruta_repo, ruta_rel_limpia)
        if not os.path.exists(ruta_abs_archivo):
            log.warning(f"{logPrefix} Archivo '{ruta_rel_limpia}' (Abs: '{ruta_abs_archivo}') no existe en el sistema de archivos. No se puede añadir al commit si no está ya trackeado y fue eliminado.")
            # Git 'add' puede manejar archivos eliminados si estaban trackeados.
            # Si el archivo es nuevo y no existe, 'git add' fallará silenciosamente para ese archivo.
            # Por ahora, lo añadimos a la lista y dejamos que 'git add' decida.
            archivos_validados_relativos.append(ruta_rel_limpia)
        else:
            archivos_validados_relativos.append(ruta_rel_limpia)
    
    if not archivos_validados_relativos: # Si la lista original estaba vacía.
        log.error(f"{logPrefix} Lista de archivos para commit (después de validación mínima) está vacía.")
        return False
    
    comando_add = ['git', 'add'] + archivos_validados_relativos
    if not ejecutarComando(comando_add, cwd=ruta_repo, check=False):
        log.error(f"{logPrefix} Falló 'git add' para archivos específicos: {archivos_validados_relativos}. No se intentará commit.")
        return False

    # Verificar si hay cambios staged para los archivos especificados
    # `git diff --staged --quiet -- <lista_de_archivos>`
    comando_diff = ['git', 'diff', '--staged', '--quiet', '--'] + archivos_validados_relativos
    try:
        proc_diff = subprocess.run(comando_diff, cwd=ruta_repo, capture_output=True, check=False)
        if proc_diff.returncode == 1: # Hay cambios staged en los archivos especificados
            log.info(f"{logPrefix} Detectados cambios en staging area para los archivos especificados.")
        elif proc_diff.returncode == 0: # Nada staged en esos archivos
            log.warning(f"{logPrefix} No hay cambios en el staging area para los archivos especificados ({archivos_validados_relativos}). No se hará commit.")
            return False
        else: # Error en diff
            stderr_diff = proc_diff.stderr.decode('utf-8', errors='ignore').strip()
            log.error(f"{logPrefix} Comando 'git diff --staged --quiet -- <archivos>' devolvió código inesperado {proc_diff.returncode}. Stderr: {stderr_diff}. Asumiendo que no hay cambios.")
            return False
    except Exception as e_diff_staged:
        log.error(f"{logPrefix} Error verificando cambios staged para archivos específicos: {e_diff_staged}. No se intentará commit.")
        return False

    log.info(f"{logPrefix} Realizando commit con mensaje: '{mensaje[:80]}...'")
    if ejecutarComando(['git', 'commit', '-m', mensaje], cwd=ruta_repo, check=False):
        log.info(f"{logPrefix} Comando 'git commit' para archivos específicos ejecutado (potencialmente).")
        # Verificar si realmente se hizo un nuevo commit y tuvo cambios.
        # Esto es importante porque `git commit` puede no hacer nada si los archivos no cambiaron realmente
        # o si el commit es idéntico al anterior.
        if commitTuvoCambiosReales(ruta_repo):
            log.info(f"{logPrefix} Commit específico resultó en cambios efectivos.")
            return True
        else:
            log.warning(f"{logPrefix} Commit específico no resultó en cambios efectivos (posiblemente commit vacío).")
            # Considerar esto un fallo o no depende de la semántica deseada. Por ahora, sí.
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
                rama_fallback = getattr(settings, 'RAMATRABAJO', None) or getattr(settings, 'RAMAPRINCIPAL', 'main') # Usar RAMATRABAJO o RAMAPRINCIPAL o 'main'
                log.info(f"{logPrefix} La rama a eliminar es la actual. Cambiando a '{rama_fallback}' primero.")
                if not cambiar_a_rama_existente(ruta_repo, rama_fallback):
                    log.error(f"{logPrefix} No se pudo cambiar de '{nombre_rama}' a '{rama_fallback}'. No se puede eliminar la rama local.")
                    exito_general = False
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
        if not existe_rama(ruta_repo, nombre_rama, remote_only=True):
            log.info(f"{logPrefix} Rama remota 'origin/{nombre_rama}' no existe. No se necesita eliminar.")
        else:
            if not ejecutarComando(['git', 'push', 'origin', '--delete', nombre_rama], cwd=ruta_repo, check=False):
                log.error(f"{logPrefix} Falló la eliminación de la rama remota 'origin/{nombre_rama}'.")
                exito_general = False
            else:
                log.info(f"{logPrefix} Rama remota 'origin/{nombre_rama}' eliminada con éxito (o ya no existía).")
            
    return exito_general