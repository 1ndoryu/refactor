# nucleo/manejadorGit.py
import subprocess
import os
import logging
import shutil
# Importar settings para acceder a configuraciones si es necesario directamente,
# aunque es mejor pasarlas como argumentos a las funciones.
# from config import settings

log = logging.getLogger(__name__)

def ejecutarComando(comando, cwd=None):
    # Ejecuta un comando de shell y devuelve True si tiene éxito, False si falla.
    # Mantiene logs limpios y captura errores comunes.
    logPrefix = "ejecutarComando:"
    rutaEjecucion = cwd or os.getcwd()
    comandoStr = ' '.join(comando)
    log.debug(f"{logPrefix} Ejecutando '{comandoStr}' en {rutaEjecucion}")
    try:
        # Usamos encoding='utf-8' para manejar mejor caracteres especiales
        # text=True (o universal_newlines=True) es importante para obtener strings
        resultado = subprocess.run(
            comando, cwd=cwd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        stdoutLimpio = resultado.stdout.strip()
        if stdoutLimpio: # Loguear salida solo si no está vacía
             log.debug(f"{logPrefix} Salida: {stdoutLimpio}")
        # No loguear éxito por defecto para reducir ruido, solo si debug está activo
        log.debug(f"{logPrefix} Comando '{comandoStr}' ejecutado con éxito.")
        return True
    except FileNotFoundError:
        log.error(f"{logPrefix} Error - Comando '{comando[0]}' no encontrado. ¿Está Git instalado y en el PATH?")
        return False
    except subprocess.CalledProcessError as e:
        # Errores de Git a menudo van a stderr
        stderrLimpio = e.stderr.strip() if e.stderr else ""
        stdoutLimpio = e.stdout.strip() if e.stdout else ""
        log.error(f"{logPrefix} Error al ejecutar '{comandoStr}'. Codigo: {e.returncode}")
        if stderrLimpio: # Loguear error estándar si existe
            log.error(f"{logPrefix} Stderr: {stderrLimpio}")
        if stdoutLimpio: # Loguear salida estándar si existe (a veces contiene info útil)
             log.debug(f"{logPrefix} Stdout: {stdoutLimpio}")
        return False
    except Exception as e:
        # Captura otras posibles excepciones (ej. permisos, encoding no manejado)
        log.error(f"{logPrefix} Error inesperado ejecutando '{comandoStr}': {e}")
        return False

def clonarOActualizarRepo(repoUrl, rutaLocal, ramaTrabajo):
    # Gestiona el clonado o la actualización del repositorio local.
    # Asegura que el repositorio esté limpio y en la rama de trabajo especificada.
    logPrefix = "clonarOActualizarRepo:"
    log.info(f"{logPrefix} Gestionando repositorio {repoUrl} en {rutaLocal} (rama objetivo: {ramaTrabajo})")
    ramaPrincipal = "main" # Valor inicial por defecto

    gitDir = os.path.join(rutaLocal, '.git')

    if os.path.isdir(gitDir):
        log.info(f"{logPrefix} Repositorio existente encontrado en {rutaLocal}. Actualizando...")

        # 0. Detectar rama principal remota (best-effort)
        try:
            comandoRamaRemota = ['git', 'remote', 'show', 'origin']
            resultadoRama = subprocess.run(comandoRamaRemota, cwd=rutaLocal, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            output = resultadoRama.stdout
            headBranchLine = [line for line in output.splitlines() if 'HEAD branch:' in line]
            if headBranchLine:
                ramaPrincipalDetectada = headBranchLine[0].split(':')[1].strip()
                if ramaPrincipalDetectada != '(unknown)':
                    ramaPrincipal = ramaPrincipalDetectada
                    log.info(f"{logPrefix} Rama principal remota detectada: '{ramaPrincipal}'")
                else:
                    log.warning(f"{logPrefix} Rama principal remota desconocida. Usando default '{ramaPrincipal}'.")
            else:
                 log.warning(f"{logPrefix} No se pudo determinar la rama principal remota. Usando default '{ramaPrincipal}'.")
        except Exception as e:
             log.warning(f"{logPrefix} Excepción al detectar rama principal remota ({e}). Usando default '{ramaPrincipal}'.")

        # 1. Limpiar estado local (reset y clean) antes de cambiar de rama o hacer pull
        log.info(f"{logPrefix} Limpiando estado del repositorio local...")
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal):
            if ramaPrincipal == "main": # Fallback común
                log.warning(f"{logPrefix} Checkout a '{ramaPrincipal}' falló. Intentando 'master'...")
                if ejecutarComando(['git', 'checkout', 'master'], cwd=rutaLocal):
                    ramaPrincipal = "master"
                else:
                    log.error(f"{logPrefix} Falló el checkout a '{ramaPrincipal}' y 'master'. Abortando actualización.")
                    return False
            else:
                 log.error(f"{logPrefix} Falló el checkout a la rama principal detectada '{ramaPrincipal}'. Abortando actualización.")
                 return False
        # Ahora en la rama principal, limpiamos
        if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaPrincipal}'], cwd=rutaLocal):
             log.error(f"{logPrefix} Falló 'git reset --hard origin/{ramaPrincipal}'. El repo puede no estar limpio.")
             # Considerar si continuar o fallar aquí
             # return False
        if not ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaLocal):
             log.warning(f"{logPrefix} Falló 'git clean -fdx'. Archivos no rastreados podrían permanecer.")
             # No necesariamente un fallo crítico, pero advertir.

        # 2. Actualizar la rama principal desde origin
        log.info(f"{logPrefix} Actualizando rama principal '{ramaPrincipal}' desde origin...")
        if not ejecutarComando(['git', 'pull', 'origin', ramaPrincipal], cwd=rutaLocal):
            log.error(f"{logPrefix} Falló 'git pull origin {ramaPrincipal}'. Puede haber conflictos o problemas de red.")
            return False # Fallo crítico si no podemos actualizar la base

        # 3. Asegurar la existencia y checkout de la rama de trabajo
        log.info(f"{logPrefix} Asegurando rama de trabajo: '{ramaTrabajo}'")
        comandoCheckRamaLocal = ['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{ramaTrabajo}']
        comandoCheckRamaRemota = ['git', 'show-ref', '--verify', '--quiet', f'refs/remotes/origin/{ramaTrabajo}']

        existeLocal = ejecutarComando(comandoCheckRamaLocal, cwd=rutaLocal)
        existeRemota = ejecutarComando(comandoCheckRamaRemota, cwd=rutaLocal)

        if existeLocal:
            log.info(f"{logPrefix} Cambiando a la rama local existente '{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', ramaTrabajo], cwd=rutaLocal):
                log.error(f"{logPrefix} Fallo al cambiar a la rama '{ramaTrabajo}'.")
                return False
            # Opcional: ¿Sincronizarla con la remota si existe? ¿O con main?
            # Por simplicidad, asumimos que la local es la referencia por ahora o que el push la actualizará.
            # Podríamos hacer un pull si existe remota:
            if existeRemota:
                log.info(f"{logPrefix} Actualizando rama '{ramaTrabajo}' desde origin...")
                if not ejecutarComando(['git', 'pull', 'origin', ramaTrabajo], cwd=rutaLocal):
                    log.warning(f"{logPrefix} Falló 'git pull' en la rama '{ramaTrabajo}'. Puede estar desactualizada o tener conflictos.")
                    # Decidir si continuar o no. Por ahora continuamos.
        elif existeRemota:
            log.info(f"{logPrefix} Creando rama local '{ramaTrabajo}' rastreando 'origin/{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', '--track', f'origin/{ramaTrabajo}'], cwd=rutaLocal):
                log.error(f"{logPrefix} Falló el checkout para rastrear la rama remota '{ramaTrabajo}'.")
                return False
        else:
            log.info(f"{logPrefix} Creando nueva rama local '{ramaTrabajo}' desde '{ramaPrincipal}'.")
            if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, ramaPrincipal], cwd=rutaLocal):
                log.error(f"{logPrefix} Falló al crear la nueva rama '{ramaTrabajo}'.")
                return False
            log.info(f"{logPrefix} Nueva rama '{ramaTrabajo}' creada localmente.")

        log.info(f"{logPrefix} Repositorio actualizado y en la rama '{ramaTrabajo}'.")
        return True

    else: # --- Caso: No existe el directorio .git, hay que clonar ---
        log.info(f"{logPrefix} Repositorio no encontrado en {rutaLocal}. Clonando...")
        # Limpiar directorio si existe pero no es un repo git
        if os.path.exists(rutaLocal):
            log.warning(f"{logPrefix} Ruta {rutaLocal} existe pero no es un repo Git válido. Se eliminará.")
            try:
                shutil.rmtree(rutaLocal)
                log.info(f"{logPrefix} Directorio existente {rutaLocal} eliminado.")
            except OSError as e:
                log.error(f"{logPrefix} No se pudo eliminar directorio existente {rutaLocal}: {e}")
                return False

        # Asegurar que el directorio padre existe
        directorioPadre = os.path.dirname(rutaLocal)
        if directorioPadre and not os.path.exists(directorioPadre):
            try:
                os.makedirs(directorioPadre)
                log.info(f"{logPrefix} Creado directorio padre {directorioPadre}")
            except OSError as e:
                 log.error(f"{logPrefix} No se pudo crear directorio padre {directorioPadre}: {e}")
                 return False

        # Clonar
        if not ejecutarComando(['git', 'clone', repoUrl, rutaLocal]):
            log.error(f"{logPrefix} Falló la clonación de {repoUrl}.")
            # Limpiar si la clonación falló y dejó directorio parcial
            if os.path.exists(rutaLocal):
                log.info(f"{logPrefix} Limpiando directorio {rutaLocal} tras clonación fallida.")
                try: shutil.rmtree(rutaLocal)
                except OSError as e: log.error(f"{logPrefix} No se pudo limpiar {rutaLocal}: {e}")
            return False

        log.info(f"{logPrefix} Repositorio clonado con éxito en {rutaLocal}")

        # Después de clonar, estamos en la rama principal por defecto.
        # Necesitamos crear o cambiar a la rama de trabajo.
        log.info(f"{logPrefix} Asegurando rama de trabajo '{ramaTrabajo}' post-clonación...")
        # Reutilizamos la lógica de arriba para checkear remota y crear/trackear
        comandoCheckRamaRemota = ['git', 'show-ref', '--verify', '--quiet', f'refs/remotes/origin/{ramaTrabajo}']
        existeRemota = ejecutarComando(comandoCheckRamaRemota, cwd=rutaLocal)

        if existeRemota:
            log.info(f"{logPrefix} Cambiando a rama '{ramaTrabajo}' rastreando 'origin/{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', '--track', f'origin/{ramaTrabajo}'], cwd=rutaLocal):
                log.error(f"{logPrefix} Falló el checkout para rastrear la rama remota '{ramaTrabajo}' post-clonación.")
                return False
        else:
            # Detectar la rama principal en la que estamos post-clonación (debería ser la correcta)
            try:
                comandoRamaActual = ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
                resultadoRamaActual = subprocess.run(comandoRamaActual, cwd=rutaLocal, check=True, capture_output=True, text=True, encoding='utf-8')
                ramaPrincipalActual = resultadoRamaActual.stdout.strip()
                log.info(f"{logPrefix} Creando nueva rama local '{ramaTrabajo}' desde '{ramaPrincipalActual}'.")
                if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, ramaPrincipalActual], cwd=rutaLocal):
                    log.error(f"{logPrefix} Falló al crear la nueva rama '{ramaTrabajo}' post-clonación.")
                    return False
            except Exception as e:
                log.error(f"{logPrefix} No se pudo determinar la rama actual post-clonación para crear '{ramaTrabajo}': {e}")
                return False

        log.info(f"{logPrefix} Repositorio clonado y en la rama '{ramaTrabajo}'.")
        return True


def hacerCommit(rutaRepo, mensaje):
    # Añade todos los cambios y hace commit. Devuelve True si el commit tuvo éxito (o no había nada que commitear), False si falla.
    logPrefix = "hacerCommit:"
    log.info(f"{logPrefix} Intentando commit en {rutaRepo}") # Mensaje ya no aquí para no duplicar

    # Paso 1: Añadir todos los cambios (nuevos, modificados, eliminados)
    # Usar -A para stagear también eliminaciones de forma segura
    if not ejecutarComando(['git', 'add', '-A'], cwd=rutaRepo):
        log.error(f"{logPrefix} Falló 'git add -A' en {rutaRepo}.")
        return False
    log.debug(f"{logPrefix} Cambios añadidos al staging area.")

    # Paso 2: Comprobar si hay cambios staged antes de intentar commitear
    # 'git diff --staged --quiet' devuelve 0 si no hay cambios staged, 1 si hay cambios
    comandoCheckStaged = ['git', 'diff', '--staged', '--quiet']
    try:
        # check=False porque esperamos que falle (código 1) si hay cambios
        resultadoCheck = subprocess.run(comandoCheckStaged, cwd=rutaRepo, capture_output=True)
        if resultadoCheck.returncode == 0:
            # Código 0 significa que NO hay cambios staged
            log.warning(f"{logPrefix} No hay cambios en el staging area para hacer commit.")
            return True # Consideramos éxito porque no había nada que hacer
    except Exception as e:
        log.error(f"{logPrefix} Error inesperado verificando cambios staged: {e}. Procediendo a intentar commit...")
        # Continuar igual por si acaso

    # Paso 3: Hacer commit
    log.info(f"{logPrefix} Realizando commit con mensaje: '{mensaje}'")
    if not ejecutarComando(['git', 'commit', '-m', mensaje], cwd=rutaRepo):
        # El comando falló. Ya logueamos el error dentro de ejecutarComando.
        # Podría ser por config (nombre/email), hooks, etc.
        log.error(f"{logPrefix} Falló 'git commit'. Verifique logs anteriores y configuración de git.")
        return False

    log.info(f"{logPrefix} Commit realizado con éxito.")
    return True

def hacerPush(rutaRepo, rama):
    # Hace push de la rama especificada a origin.
    logPrefix = "hacerPush:"
    log.info(f"{logPrefix} Intentando push de la rama '{rama}' a 'origin' desde {rutaRepo}")
    # Usar -u la primera vez es útil, pero si la rama ya existe remotamente
    # y no la estamos rastreando, puede fallar. Es más seguro simplemente:
    # git push origin <rama>
    # Si queremos asegurar que la rama remota se cree o actualice:
    if not ejecutarComando(['git', 'push', 'origin', rama], cwd=rutaRepo):
        log.error(f"{logPrefix} Falló 'git push origin {rama}'. Verifique credenciales, permisos y si la rama remota requiere force-push (¡con cuidado!).")
        return False
    log.info(f"{logPrefix} Push de la rama '{rama}' a origin realizado con éxito.")
    return True

def descartarCambiosLocales(rutaRepo):
    # Intenta resetear el repositorio a HEAD y limpiar archivos no rastreados.
    logPrefix = "descartarCambiosLocales:"
    log.warning(f"{logPrefix} Intentando descartar todos los cambios locales en {rutaRepo}...")
    resetOk = ejecutarComando(['git', 'reset', '--hard', 'HEAD'], cwd=rutaRepo)
    cleanOk = ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaRepo)

    if resetOk and cleanOk:
        log.info(f"{logPrefix} Cambios locales descartados exitosamente.")
        return True
    else:
        log.error(f"{logPrefix} Falló al descartar cambios locales (reset: {resetOk}, clean: {cleanOk}). El repositorio puede estar inconsistente.")
        return False