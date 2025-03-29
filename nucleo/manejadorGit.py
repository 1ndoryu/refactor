# nucleo/manejadorGit.py
import subprocess
import os
import logging
import shutil

log = logging.getLogger(__name__) 

def ejecutarComando(comando, cwd=None):
    # Ejecuta un comando de shell y devuelve True si tiene éxito, False si falla.
    logPrefix = "ejecutarComando:"
    rutaEjecucion = cwd or os.getcwd()
    comandoStr = ' '.join(comando)
    log.debug(f"{logPrefix} Ejecutando '{comandoStr}' en {rutaEjecucion}")
    try:
        # Usamos encoding='utf-8' para manejar mejor caracteres especiales
        resultado = subprocess.run(
            comando, cwd=cwd, check=True, capture_output=True, text=True, encoding='utf-8')
        stdoutLimpio = resultado.stdout.strip()
        if stdoutLimpio: # Loguear salida solo si no está vacía
             log.debug(f"{logPrefix} Salida: {stdoutLimpio}")
        log.info(f"{logPrefix} Comando '{comandoStr}' ejecutado con éxito.")
        return True
    except FileNotFoundError:
        log.error(f"{logPrefix} Error - Comando '{comando[0]}' no encontrado. ¿Está Git instalado y en el PATH?")
        return False
    except subprocess.CalledProcessError as e:
        stderrLimpio = e.stderr.strip()
        stdoutLimpio = e.stdout.strip()
        log.error(f"{logPrefix} Error al ejecutar '{comandoStr}'. Codigo: {e.returncode}")
        if stderrLimpio: # Loguear error solo si no está vacío
            log.error(f"{logPrefix} Stderr: {stderrLimpio}")
        if stdoutLimpio: # Loguear salida aunque haya error, a veces contiene info útil
             log.debug(f"{logPrefix} Stdout: {stdoutLimpio}")
        return False
    except Exception as e:
        # Captura otras posibles excepciones como errores de encoding
        log.error(f"{logPrefix} Error inesperado ejecutando '{comandoStr}': {e}")
        return False

def clonarOActualizarRepo(repoUrl, rutaLocal):
    logPrefix = "clonarOActualizarRepo:"
    log.info(f"{logPrefix} Gestionando repositorio {repoUrl} en {rutaLocal}")
    ramaPrincipal = "main"

    gitDir = os.path.join(rutaLocal, '.git')

    if os.path.isdir(gitDir):
        log.info(f"{logPrefix} Repositorio existente encontrado. Actualizando...")
        # Primero, intentamos obtener la rama actual por defecto del remoto
        try:
            comandoRamaRemota = ['git', 'rev-parse', '--abbrev-ref', 'origin/HEAD']
            resultadoRama = subprocess.run(comandoRamaRemota, cwd=rutaLocal, check=True, capture_output=True, text=True, encoding='utf-8')
            ramaRemotaCompleta = resultadoRama.stdout.strip() # ej: origin/main
            if ramaRemotaCompleta and '/' in ramaRemotaCompleta:
                ramaPrincipal = ramaRemotaCompleta.split('/', 1)[1]
                log.info(f"{logPrefix} Rama principal detectada del remoto: '{ramaPrincipal}'")
            else:
                 log.warning(f"{logPrefix} No se pudo determinar la rama principal remota ('{ramaRemotaCompleta}'). Usando '{ramaPrincipal}'.")
        except Exception as e:
             log.warning(f"{logPrefix} Excepcion al intentar detectar rama principal remota: {e}. Usando '{ramaPrincipal}'.")

        # Comprobamos si hay cambios locales sin commitear antes de hacer pull/reset
        comandoStatus = ['git', 'status', '--porcelain']
        try:
            resultadoStatus = subprocess.run(comandoStatus, cwd=rutaLocal, check=True, capture_output=True, text=True, encoding='utf-8')
            if resultadoStatus.stdout.strip():
                log.warning(f"{logPrefix} Detectados cambios locales sin commit en {rutaLocal}. Intentando descartarlos...")
                # Descartar cambios locales (modified y untracked)
                if not ejecutarComando(['git', 'reset', '--hard'], cwd=rutaLocal):
                     log.error(f"{logPrefix} Fallo al descartar cambios con 'git reset --hard'.")
                     # No continuamos si no podemos limpiar
                     # return False # Opcional: ser estricto
                if not ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaLocal):
                     log.error(f"{logPrefix} Fallo al limpiar archivos no rastreados con 'git clean -fdx'.")
                     # No continuamos si no podemos limpiar
                     # return False # Opcional: ser estricto
                log.info(f"{logPrefix} Cambios locales descartados.")
            else:
                log.info(f"{logPrefix} No hay cambios locales pendientes.")
        except Exception as e:
             log.error(f"{logPrefix} Error al comprobar estado del repositorio: {e}. Procediendo con cautela.")

        # Actualizar
        if not ejecutarComando(['git', 'fetch', 'origin'], cwd=rutaLocal):
            log.error(f"{logPrefix} Fallo 'git fetch'.")
            return False
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal):
             # Si falla main, intentamos master como fallback común
             if ramaPrincipal == "main":
                 log.warning(f"{logPrefix} Checkout a '{ramaPrincipal}' fallo. Intentando 'master'...")
                 ramaPrincipal = "master"
                 if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal):
                     log.error(f"{logPrefix} Checkout a 'master' tambien fallo. Abortando actualizacion.")
                     return False
             else:
                 log.error(f"{logPrefix} Checkout a '{ramaPrincipal}' fallo. Abortando actualizacion.")
                 return False

        # Hacemos pull con rebase para intentar mantener historial limpio
        if not ejecutarComando(['git', 'pull', 'origin', ramaPrincipal, '--rebase'], cwd=rutaLocal):
            log.warning(f"{logPrefix} 'git pull --rebase' fallo. Intentando 'git merge'...")
            # Fallback a merge si rebase falla (puede ser por conflictos complejos)
            # Primero reseteamos cualquier estado intermedio del rebase fallido
            ejecutarComando(['git', 'rebase', '--abort'], cwd=rutaLocal) # Ignoramos si falla (puede que no hubiera rebase en curso)
            # Ahora intentamos el merge
            if not ejecutarComando(['git', 'merge', f'origin/{ramaPrincipal}'], cwd=rutaLocal):
                 log.error(f"{logPrefix} 'git merge' tambien fallo. Probablemente hay conflictos. Requiere intervencion manual en {rutaLocal}")
                 return False
            log.info(f"{logPrefix} Repositorio actualizado via merge tras fallo de rebase.")
        else:
             log.info(f"{logPrefix} Repositorio actualizado via rebase.")
        return True
    else:
        log.info(f"{logPrefix} Repositorio no encontrado. Clonando...")
        if os.path.exists(rutaLocal):
            log.warning(f"{logPrefix} Ruta {rutaLocal} existe pero no es repo Git. Se eliminara.")
            try:
                # Usar shutil.rmtree para borrar directorios recursivamente
                shutil.rmtree(rutaLocal)
                log.info(f"{logPrefix} Directorio existente {rutaLocal} eliminado.")
            except OSError as e:
                log.error(f"{logPrefix} No se pudo eliminar directorio {rutaLocal}: {e}")
                return False

        # Asegurarse que el directorio padre existe antes de clonar
        directorioPadre = os.path.dirname(rutaLocal)
        if directorioPadre and not os.path.exists(directorioPadre):
            try:
                os.makedirs(directorioPadre)
                log.info(f"{logPrefix} Creado directorio padre {directorioPadre}")
            except OSError as e:
                 log.error(f"{logPrefix} No se pudo crear directorio padre {directorioPadre}: {e}")
                 return False

        if ejecutarComando(['git', 'clone', repoUrl, rutaLocal]):
            log.info(f"{logPrefix} Repositorio clonado con exito en {rutaLocal}")
            # Opcional: checkout a la rama deseada si no es la por defecto (ya debería estar en la rama por defecto)
            return True
        else:
            log.error(f"{logPrefix} Fallo la clonacion de {repoUrl}.")
            # Limpiar si la clonación falló
            if os.path.exists(rutaLocal):
                log.info(f"{logPrefix} Limpiando directorio {rutaLocal} tras clonacion fallida.")
                try:
                    shutil.rmtree(rutaLocal)
                except OSError as e:
                    log.error(f"{logPrefix} No se pudo limpiar {rutaLocal}: {e}")
            return False

def hacerCommit(rutaRepo, mensaje):
    # Añade todos los cambios y hace commit.
    logPrefix = "hacerCommit:"
    log.info(f"{logPrefix} Intentando commit en {rutaRepo} con mensaje: '{mensaje}'")

    # Paso 1: Añadir todos los cambios (nuevos, modificados, eliminados)
    if not ejecutarComando(['git', 'add', '.'], cwd=rutaRepo):
        log.error(f"{logPrefix} Fallo 'git add .' en {rutaRepo}.")
        return False
    log.info(f"{logPrefix} Cambios añadidos al staging area.")

    # Paso 2: Hacer commit
    # Usar -m para el mensaje directamente
    if not ejecutarComando(['git', 'commit', '-m', mensaje], cwd=rutaRepo):
        # Podría fallar si no hay nada que commitear después del add (raro pero posible)
        # o por configuración de git (nombre/email no seteado).
        # Comprobamos si es porque no hay cambios
        comandoStatus = ['git', 'status', '--porcelain']
        try:
            resultadoStatus = subprocess.run(comandoStatus, cwd=rutaRepo, check=True, capture_output=True, text=True, encoding='utf-8')
            if not resultadoStatus.stdout.strip():
                log.warning(f"{logPrefix} 'git commit' fallo, pero parece que no habia cambios para commitear.")
                # Consideramos esto un éxito "vacío", no un error real de commit.
                return True # O False si prefieres ser estricto
            else:
                 log.error(f"{logPrefix} Fallo 'git commit -m \"{mensaje}\"' en {rutaRepo}. Verifique la configuracion de git o posibles hooks.")
                 return False
        except Exception as e:
             log.error(f"{logPrefix} Fallo 'git commit -m \"{mensaje}\"' en {rutaRepo} y error al verificar status: {e}")
             return False

    log.info(f"{logPrefix} Commit realizado con exito.")
    return True

# --- Añadir función push (opcional por ahora) ---
# def hacerPush(rutaRepo, rama):
#     logPrefix = "hacerPush:"
#     log.info(f"{logPrefix} Intentando push a origin/{rama} desde {rutaRepo}")
#     if not ejecutarComando(['git', 'push', 'origin', rama], cwd=rutaRepo):
#         log.error(f"{logPrefix} Falló 'git push origin {rama}'.")
#         return False
#     log.info(f"{logPrefix} Push realizado con éxito.")
#     return True