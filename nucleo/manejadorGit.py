# nucleo/manejadorGit.py
import subprocess
import os
import logging
import shutil

log = logging.getLogger(__name__)


def ejecutarComando(comando, cwd=None):
    prefijoLog = "ejecutarComando:"
    rutaEjecucion = cwd or os.getcwd()
    comandoStr = ' '.join(comando)
    log.debug(f"{prefijoLog} Ejecutando '{comandoStr}' en {rutaEjecucion}")
    try:
        resultado = subprocess.run(
            comando, cwd=cwd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        stdoutLimpio = resultado.stdout.strip()
        if stdoutLimpio:
            log.debug(f"{prefijoLog} Salida: {stdoutLimpio}")
        log.debug(f"{prefijoLog} Comando '{comandoStr}' ejecutado con éxito.")
        return True
    except FileNotFoundError:
        log.error(
            f"{prefijoLog} Error - Comando '{comando[0]}' no encontrado. ¿Está Git instalado y en el PATH?")
        return False
    except subprocess.CalledProcessError as e:
        stderrLimpio = e.stderr.strip() if e.stderr else ""
        stdoutLimpio = e.stdout.strip() if e.stdout else ""
        log.error(
            f"{prefijoLog} Error al ejecutar '{comandoStr}'. Codigo: {e.returncode}")
        if stderrLimpio:
            log.error(f"{prefijoLog} Stderr: {stderrLimpio}")
        if stdoutLimpio:
            log.debug(f"{prefijoLog} Stdout: {stdoutLimpio}")
        return False
    except Exception as e:
        log.error(
            f"{prefijoLog} Error inesperado ejecutando '{comandoStr}': {e}")
        return False


def clonarOActualizarRepo(urlRepositorio, rutaLocal, ramaTrabajo):
    prefijoLog = "clonarOActualizarRepo:"
    log.info(
        f"{prefijoLog} Gestionando repositorio {urlRepositorio} en {rutaLocal} (rama objetivo: {ramaTrabajo})")
    ramaPrincipalDefault = "main"  # Intentar main primero
    ramaPrincipal = ramaPrincipalDefault

    rutaGit = os.path.join(rutaLocal, '.git')

    if os.path.isdir(rutaGit):
        log.info(
            f"{prefijoLog} Repositorio existente encontrado en {rutaLocal}. Actualizando...")

        try:
            comandoRamaRemota = ['git', 'remote', 'show', 'origin']
            resultadoRama = subprocess.run(comandoRamaRemota, cwd=rutaLocal, check=True,
                                           capture_output=True, text=True, encoding='utf-8', errors='ignore')
            output = resultadoRama.stdout
            lineaRamaHead = [
                linea for linea in output.splitlines() if 'HEAD branch:' in linea]
            if lineaRamaHead:
                ramaPrincipalDetectada = lineaRamaHead[0].split(':')[1].strip()
                if ramaPrincipalDetectada and ramaPrincipalDetectada != '(unknown)':
                    ramaPrincipal = ramaPrincipalDetectada
                    log.info(
                        f"{prefijoLog} Rama principal remota detectada: '{ramaPrincipal}'")
                else:
                    log.warning(
                        f"{prefijoLog} Rama principal remota desconocida. Usando default '{ramaPrincipal}'.")
            else:
                log.warning(
                    f"{prefijoLog} No se pudo determinar la rama principal remota. Usando default '{ramaPrincipal}'.")
        except Exception as e:
            log.warning(
                f"{prefijoLog} Excepción al detectar rama principal remota ({e}). Usando default '{ramaPrincipal}'.")

        log.info(f"{prefijoLog} Limpiando estado del repositorio local...")
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal):
            if ramaPrincipal == ramaPrincipalDefault:  # Si falló con 'main', intentar 'master'
                log.warning(
                    f"{prefijoLog} Checkout a '{ramaPrincipal}' falló. Intentando 'master'...")
                if ejecutarComando(['git', 'checkout', 'master'], cwd=rutaLocal):
                    ramaPrincipal = "master"
                    log.info(f"{prefijoLog} Usando rama principal 'master'.")
                else:
                    log.error(
                        f"{prefijoLog} Falló el checkout a '{ramaPrincipalDefault}' y 'master'. Abortando actualización.")
                    return False
            else:  # Falló con una rama detectada diferente a main/master
                log.error(
                    f"{prefijoLog} Falló el checkout a la rama principal detectada '{ramaPrincipal}'. Abortando actualización.")
                return False

        if not ejecutarComando(['git', 'fetch', 'origin', ramaPrincipal], cwd=rutaLocal):
            log.warning(
                f"{prefijoLog} Falló 'git fetch origin {ramaPrincipal}'. Puede que el reset falle.")
        if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaPrincipal}'], cwd=rutaLocal):
            log.error(
                f"{prefijoLog} Falló 'git reset --hard origin/{ramaPrincipal}'. El repo puede no estar limpio.")
            # return False # Considerar fallar aquí si la limpieza es crítica
        if not ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaLocal):
            log.warning(
                f"{prefijoLog} Falló 'git clean -fdx'. Archivos no rastreados podrían permanecer.")

        log.info(
            f"{prefijoLog} Actualizando rama principal '{ramaPrincipal}' desde origin...")
        if not ejecutarComando(['git', 'pull', 'origin', ramaPrincipal], cwd=rutaLocal):
            log.error(
                f"{prefijoLog} Falló 'git pull origin {ramaPrincipal}'. Puede haber conflictos o problemas de red.")
            return False

        log.info(f"{prefijoLog} Asegurando rama de trabajo: '{ramaTrabajo}'")
        comandoCheckRamaLocal = [
            'git', 'show-ref', '--verify', '--quiet', f'refs/heads/{ramaTrabajo}']
        comandoCheckRamaRemota = [
            'git', 'show-ref', '--verify', '--quiet', f'refs/remotes/origin/{ramaTrabajo}']

        # Usamos subprocess.run directamente para chequear existencia sin el log de ejecutarComando
        existeLocal = subprocess.run(
            comandoCheckRamaLocal, cwd=rutaLocal, capture_output=True).returncode == 0
        existeRemota = subprocess.run(
            comandoCheckRamaRemota, cwd=rutaLocal, capture_output=True).returncode == 0

        if existeLocal:
            log.info(
                f"{prefijoLog} Cambiando a la rama local existente '{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', ramaTrabajo], cwd=rutaLocal):
                log.error(
                    f"{prefijoLog} Fallo al cambiar a la rama '{ramaTrabajo}'.")
                return False
            if existeRemota:
                log.info(
                    f"{prefijoLog} Actualizando rama '{ramaTrabajo}' desde origin...")
                if not ejecutarComando(['git', 'pull', 'origin', ramaTrabajo], cwd=rutaLocal):
                    log.warning(
                        f"{prefijoLog} Falló 'git pull' en la rama '{ramaTrabajo}'. Puede estar desactualizada o tener conflictos locales.")
                    # Decidimos continuar, el commit/push posterior podría fallar
        elif existeRemota:
            log.info(
                f"{prefijoLog} Creando rama local '{ramaTrabajo}' rastreando 'origin/{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', '--track', f'origin/{ramaTrabajo}'], cwd=rutaLocal):
                log.error(
                    f"{prefijoLog} Falló el checkout para rastrear la rama remota '{ramaTrabajo}'.")
                return False
        else:
            log.info(
                f"{prefijoLog} Creando nueva rama local '{ramaTrabajo}' desde '{ramaPrincipal}'.")
            if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, ramaPrincipal], cwd=rutaLocal):
                log.error(
                    f"{prefijoLog} Falló al crear la nueva rama '{ramaTrabajo}'.")
                return False
            log.info(
                f"{prefijoLog} Nueva rama '{ramaTrabajo}' creada localmente.")

        log.info(
            f"{prefijoLog} Repositorio actualizado y en la rama '{ramaTrabajo}'.")
        return True

    else:  # No existe .git, clonar
        log.info(
            f"{prefijoLog} Repositorio no encontrado en {rutaLocal}. Clonando...")
        if os.path.exists(rutaLocal):
            log.warning(
                f"{prefijoLog} Ruta {rutaLocal} existe pero no es un repo Git válido. Se eliminará.")
            try:
                shutil.rmtree(rutaLocal)
                log.info(
                    f"{prefijoLog} Directorio existente {rutaLocal} eliminado.")
            except OSError as e:
                log.error(
                    f"{prefijoLog} No se pudo eliminar directorio existente {rutaLocal}: {e}")
                return False

        directorioPadre = os.path.dirname(rutaLocal)
        if directorioPadre and not os.path.exists(directorioPadre):
            try:
                os.makedirs(directorioPadre)
                log.info(
                    f"{prefijoLog} Creado directorio padre {directorioPadre}")
            except OSError as e:
                log.error(
                    f"{prefijoLog} No se pudo crear directorio padre {directorioPadre}: {e}")
                return False

        if not ejecutarComando(['git', 'clone', urlRepositorio, rutaLocal]):
            log.error(f"{prefijoLog} Falló la clonación de {urlRepositorio}.")
            if os.path.exists(rutaLocal):
                log.info(
                    f"{prefijoLog} Limpiando directorio {rutaLocal} tras clonación fallida.")
                try:
                    shutil.rmtree(rutaLocal)
                except OSError as e:
                    log.error(
                        f"{prefijoLog} No se pudo limpiar {rutaLocal}: {e}")
            return False

        log.info(f"{prefijoLog} Repositorio clonado con éxito en {rutaLocal}")

        log.info(
            f"{prefijoLog} Asegurando rama de trabajo '{ramaTrabajo}' post-clonación...")
        comandoCheckRamaRemota = [
            'git', 'show-ref', '--verify', '--quiet', f'refs/remotes/origin/{ramaTrabajo}']
        existeRemota = subprocess.run(
            comandoCheckRamaRemota, cwd=rutaLocal, capture_output=True).returncode == 0

        if existeRemota:
            log.info(
                f"{prefijoLog} Cambiando a rama '{ramaTrabajo}' rastreando 'origin/{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', '--track', f'origin/{ramaTrabajo}'], cwd=rutaLocal):
                log.error(
                    f"{prefijoLog} Falló el checkout para rastrear la rama remota '{ramaTrabajo}' post-clonación.")
                return False
        else:
            try:
                comandoRamaActual = [
                    'git', 'rev-parse', '--abbrev-ref', 'HEAD']
                resultadoRamaActual = subprocess.run(
                    comandoRamaActual, cwd=rutaLocal, check=True, capture_output=True, text=True, encoding='utf-8')
                ramaPrincipalActual = resultadoRamaActual.stdout.strip()
                log.info(
                    f"{prefijoLog} Creando nueva rama local '{ramaTrabajo}' desde '{ramaPrincipalActual}'.")
                if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, ramaPrincipalActual], cwd=rutaLocal):
                    log.error(
                        f"{prefijoLog} Falló al crear la nueva rama '{ramaTrabajo}' post-clonación.")
                    return False
            except Exception as e:
                log.error(
                    f"{prefijoLog} No se pudo determinar la rama actual post-clonación para crear '{ramaTrabajo}': {e}")
                return False

        log.info(
            f"{prefijoLog} Repositorio clonado y en la rama '{ramaTrabajo}'.")
        return True


def hacerCommit(rutaRepo, mensaje):
    prefijoLog = "hacerCommit:"
    log.info(f"{prefijoLog} Intentando commit en {rutaRepo}")

    if not ejecutarComando(['git', 'add', '-A'], cwd=rutaRepo):
        log.error(f"{prefijoLog} Falló 'git add -A' en {rutaRepo}.")
        return False
    log.debug(f"{prefijoLog} Cambios añadidos al staging area.")

    comandoCheckStaged = ['git', 'diff', '--staged', '--quiet']
    try:
        resultadoCheck = subprocess.run(
            comandoCheckStaged, cwd=rutaRepo, capture_output=True)
        if resultadoCheck.returncode == 0:
            log.warning(
                f"{prefijoLog} No hay cambios en el staging area para hacer commit.")
            return True
    except Exception as e:
        log.error(
            f"{prefijoLog} Error inesperado verificando cambios staged: {e}. Procediendo a intentar commit...")

    log.info(f"{prefijoLog} Realizando commit con mensaje: '{mensaje}'")
    if not ejecutarComando(['git', 'commit', '-m', mensaje], cwd=rutaRepo):
        log.error(
            f"{prefijoLog} Falló 'git commit'. Verifique logs anteriores y configuración de git.")
        return False

    log.info(f"{prefijoLog} Commit realizado con éxito.")
    return True


def hacerPush(rutaRepo, rama):
    prefijoLog = "hacerPush:"
    log.info(
        f"{prefijoLog} Intentando push de la rama '{rama}' a 'origin' desde {rutaRepo}")
    if not ejecutarComando(['git', 'push', 'origin', rama], cwd=rutaRepo):
        log.error(f"{prefijoLog} Falló 'git push origin {rama}'. Verifique credenciales, permisos y si la rama remota requiere force-push (¡con cuidado!).")
        return False
    log.info(
        f"{prefijoLog} Push de la rama '{rama}' a origin realizado con éxito.")
    return True


def descartarCambiosLocales(rutaRepo):
    prefijoLog = "descartarCambiosLocales:"
    log.warning(
        f"{prefijoLog} Intentando descartar todos los cambios locales en {rutaRepo}...")
    # Intentar fetch antes de reset por si la rama local está adelantada y HEAD no es origin/rama
    ejecutarComando(['git', 'fetch', 'origin'],
                    cwd=rutaRepo)  # Ignorar fallo aquí
    # Usar checkout . para descartar cambios no staged antes del reset
    ejecutarComando(['git', 'checkout', '--', '.'], cwd=rutaRepo)
    resetOk = ejecutarComando(['git', 'reset', '--hard', 'HEAD'], cwd=rutaRepo)
    cleanOk = ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaRepo)

    if resetOk and cleanOk:
        log.info(f"{prefijoLog} Cambios locales descartados exitosamente.")
        return True
    else:
        log.error(f"{prefijoLog} Falló al descartar cambios locales (reset: {resetOk}, clean: {cleanOk}). El repositorio puede estar inconsistente.")
        return False
