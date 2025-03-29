# nucleo/manejadorGit.py
import subprocess
import os
import logging
import shutil

log = logging.getLogger(__name__)

def ejecutarComando(comando, cwd=None):
    """
    Ejecuta un comando de shell y devuelve True si tiene éxito, False si falla.
    Captura stdout/stderr y loguea errores.
    """
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

def obtenerUrlRemota(nombreRemoto, rutaRepo):
    """Obtiene la URL configurada para un remote específico."""
    logPrefix = "obtenerUrlRemota:"
    comando = ['git', 'remote', 'get-url', nombreRemoto]
    try:
        resultado = subprocess.run(
            comando, cwd=rutaRepo, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        url = resultado.stdout.strip()
        log.debug(f"{logPrefix} URL actual para remote '{nombreRemoto}' en '{rutaRepo}': {url}")
        return url
    except subprocess.CalledProcessError as e:
        stderrLimpio = e.stderr.strip() if e.stderr else ""
        # Es común que falle si el remote no existe, loguear como warning
        log.warning(f"{logPrefix} No se pudo obtener URL para '{nombreRemoto}' (¿no existe?). Stderr: {stderrLimpio}")
        return None
    except Exception as e:
        log.error(f"{logPrefix} Error inesperado obteniendo URL para '{nombreRemoto}': {e}")
        return None

def establecerUrlRemota(nombreRemoto, nuevaUrl, rutaRepo):
    """Establece la URL para un remote específico."""
    logPrefix = "establecerUrlRemota:"
    # Primero intentar cambiarla, si falla, intentar añadirla (por si no existía)
    comando_set = ['git', 'remote', 'set-url', nombreRemoto, nuevaUrl]
    comando_add = ['git', 'remote', 'add', nombreRemoto, nuevaUrl]

    log.info(f"{logPrefix} Intentando establecer URL para remote '{nombreRemoto}' a: {nuevaUrl}")
    if ejecutarComando(comando_set, cwd=rutaRepo):
        log.info(f"{logPrefix} URL para '{nombreRemoto}' actualizada (set-url) correctamente.")
        return True
    else:
        log.warning(f"{logPrefix} Falló 'set-url' para '{nombreRemoto}'. Intentando 'add'...")
        if ejecutarComando(comando_add, cwd=rutaRepo):
             log.info(f"{logPrefix} Remote '{nombreRemoto}' añadido con URL correcta.")
             return True
        else:
            log.error(f"{logPrefix} Falló también 'add' para '{nombreRemoto}'. No se pudo configurar la URL remota.")
            return False


def clonarOActualizarRepo(repoUrl, rutaLocal, ramaTrabajo):
    """
    Gestiona el clonado o la actualización del repositorio local.
    Asegura que el repositorio esté limpio, en la rama de trabajo especificada
    y que el remote 'origin' use la URL correcta (repoUrl).
    """
    logPrefix = "clonarOActualizarRepo:"
    log.info(f"{logPrefix} Gestionando repositorio {repoUrl} en {rutaLocal} (rama objetivo: {ramaTrabajo})")
    ramaPrincipal = "main" # Valor inicial por defecto

    gitDir = os.path.join(rutaLocal, '.git')
    repoExiste = os.path.isdir(gitDir)

    if not repoExiste:
        # --- Caso: No existe el directorio .git, hay que clonar ---
        log.info(f"{logPrefix} Repositorio no encontrado en {rutaLocal}. Clonando desde {repoUrl}...")
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

        # Clonar usando la repoUrl (debe ser la URL SSH de settings.py)
        if not ejecutarComando(['git', 'clone', repoUrl, rutaLocal]):
            log.error(f"{logPrefix} Falló la clonación de {repoUrl}.")
            # Limpiar si la clonación falló y dejó directorio parcial
            if os.path.exists(rutaLocal):
                log.info(f"{logPrefix} Limpiando directorio {rutaLocal} tras clonación fallida.")
                try: shutil.rmtree(rutaLocal)
                except OSError as e: log.error(f"{logPrefix} No se pudo limpiar {rutaLocal}: {e}")
            return False

        log.info(f"{logPrefix} Repositorio clonado con éxito en {rutaLocal}")
        repoExiste = True # Marcar que ahora sí existe para la lógica siguiente

    # --- Asegurar que la URL del remote 'origin' sea la correcta ---
    # Se ejecuta SIEMPRE, tanto si ya existía como si se acaba de clonar
    if repoExiste:
        log.info(f"{logPrefix} Verificando y/o corrigiendo URL del remote 'origin'...")
        urlActualOrigin = obtenerUrlRemota("origin", rutaLocal)

        if not urlActualOrigin:
            log.warning(f"{logPrefix} No se encontró remote 'origin' o no se pudo obtener su URL. Intentando establecerla a: {repoUrl}")
            if not establecerUrlRemota("origin", repoUrl, rutaLocal):
                log.error(f"{logPrefix} ¡CRÍTICO! No se pudo establecer la URL para el remote 'origin'. Las operaciones push/pull podrían fallar.")
                # Considerar fallar aquí si la URL es esencial
                # return False
        elif urlActualOrigin != repoUrl:
            log.warning(f"{logPrefix} La URL del remote 'origin' ({urlActualOrigin}) difiere de la configurada ({repoUrl}). Corrigiendo...")
            if not establecerUrlRemota("origin", repoUrl, rutaLocal):
                log.error(f"{logPrefix} ¡CRÍTICO! No se pudo corregir la URL del remote 'origin'. Las operaciones push/pull podrían usar la URL incorrecta.")
                # return False # Opción más segura
            else:
                 log.info(f"{logPrefix} URL del remote 'origin' actualizada a {repoUrl}.")
        else:
            log.info(f"{logPrefix} URL del remote 'origin' ya está configurada correctamente a {repoUrl}.")

    # --- Lógica de Actualización y Cambio de Rama (si el repo ya existía o se acaba de clonar) ---
    if repoExiste:
        # 0. Detectar rama principal remota (best-effort) - Mantenemos tu lógica
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
        # Intentar checkout a la rama principal detectada o fallback
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal):
            log.warning(f"{logPrefix} Checkout a '{ramaPrincipal}' falló. Intentando 'master'...")
            if ejecutarComando(['git', 'checkout', 'master'], cwd=rutaLocal):
                ramaPrincipal = "master"
            else:
                log.error(f"{logPrefix} Falló el checkout a '{ramaPrincipal}' y 'master'. Abortando preparación.")
                return False

        # Ahora en la rama principal (o master), limpiamos
        # IMPORTANTE: Hacer fetch ANTES de reset para tener las refs remotas actualizadas
        log.info(f"{logPrefix} Actualizando referencias remotas (fetch)...")
        if not ejecutarComando(['git', 'fetch', 'origin'], cwd=rutaLocal):
             log.warning(f"{logPrefix} Falló 'git fetch origin'. El reset podría usar refs desactualizadas.")
             # No es necesariamente fatal, pero puede causar problemas. Continuamos con precaución.

        log.info(f"{logPrefix} Reseteando rama '{ramaPrincipal}' a 'origin/{ramaPrincipal}'...")
        if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaPrincipal}'], cwd=rutaLocal):
             log.error(f"{logPrefix} Falló 'git reset --hard origin/{ramaPrincipal}'. El repo puede no estar limpio.")
             # Podría ser fatal si el reset falla
             return False
        log.info(f"{logPrefix} Limpiando archivos no rastreados (clean)...")
        if not ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaLocal):
             log.warning(f"{logPrefix} Falló 'git clean -fdx'. Archivos no rastreados podrían permanecer.")
             # No necesariamente un fallo crítico, pero advertir.

        # 2. Actualizar (Pull) la rama principal ya no es estrictamente necesario después de fetch y reset --hard
        # log.info(f"{logPrefix} Actualizando rama principal '{ramaPrincipal}' desde origin (pull)...")
        # if not ejecutarComando(['git', 'pull', 'origin', ramaPrincipal], cwd=rutaLocal):
        #     log.error(f"{logPrefix} Falló 'git pull origin {ramaPrincipal}'. Puede haber conflictos o problemas de red.")
        #     return False

        # 3. Asegurar la existencia y checkout de la rama de trabajo
        log.info(f"{logPrefix} Asegurando rama de trabajo: '{ramaTrabajo}'")
        # Usar 'branch --list' es más directo para verificar existencia local
        comandoCheckRamaLocal = ['git', 'branch', '--list', ramaTrabajo]
        resultadoCheckLocal = subprocess.run(comandoCheckRamaLocal, cwd=rutaLocal, capture_output=True, text=True, encoding='utf-8')
        existeLocal = bool(resultadoCheckLocal.stdout.strip())

        # Usar 'ls-remote' es más fiable para verificar existencia remota sin fetch completo
        comandoCheckRamaRemota = ['git', 'ls-remote', '--heads', 'origin', ramaTrabajo]
        resultadoCheckRemoto = subprocess.run(comandoCheckRamaRemota, cwd=rutaLocal, capture_output=True, text=True, encoding='utf-8')
        existeRemota = bool(resultadoCheckRemoto.stdout.strip())


        if existeLocal:
            log.info(f"{logPrefix} Cambiando a la rama local existente '{ramaTrabajo}'.")
            if not ejecutarComando(['git', 'checkout', ramaTrabajo], cwd=rutaLocal):
                log.error(f"{logPrefix} Fallo al cambiar a la rama '{ramaTrabajo}'.")
                return False
            # Opcional: Sincronizarla con la remota si existe, o resetearla a origin/rama si existe remota
            if existeRemota:
                log.info(f"{logPrefix} Reseteando rama local '{ramaTrabajo}' a 'origin/{ramaTrabajo}'...")
                if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaTrabajo}'], cwd=rutaLocal):
                     log.warning(f"{logPrefix} Falló el reset de '{ramaTrabajo}' a su versión remota. Puede estar desactualizada o tener conflictos locales no limpiados.")
                     # Decidir si continuar o no. Por ahora continuamos.
            else:
                 log.info(f"{logPrefix} Rama '{ramaTrabajo}' existe localmente pero no en origin. Se usará la versión local.")

        elif existeRemota:
            log.info(f"{logPrefix} Creando rama local '{ramaTrabajo}' rastreando 'origin/{ramaTrabajo}'.")
            # Usamos checkout directo, Git >= 1.8.0 maneja el rastreo automáticamente si la rama local no existe pero sí la remota
            if not ejecutarComando(['git', 'checkout', ramaTrabajo], cwd=rutaLocal):
            # Alternativa explícita si lo anterior falla (versiones antiguas de git?):
            # if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, f'origin/{ramaTrabajo}'], cwd=rutaLocal):
                log.error(f"{logPrefix} Falló el checkout para crear/rastrear la rama remota '{ramaTrabajo}'.")
                return False
        else:
            log.info(f"{logPrefix} Creando nueva rama local '{ramaTrabajo}' desde '{ramaPrincipal}'.")
            if not ejecutarComando(['git', 'checkout', '-b', ramaTrabajo, ramaPrincipal], cwd=rutaLocal):
                log.error(f"{logPrefix} Falló al crear la nueva rama '{ramaTrabajo}'.")
                return False
            log.info(f"{logPrefix} Nueva rama '{ramaTrabajo}' creada localmente.")

        log.info(f"{logPrefix} Repositorio actualizado y en la rama '{ramaTrabajo}'.")
        return True

    else:
         # Esto no debería ocurrir si la clonación falló, pero por si acaso
         log.error(f"{logPrefix} Error inesperado: El repositorio no existe después del intento de clonación/verificación.")
         return False


def hacerCommit(rutaRepo, mensaje):
    """
    Añade todos los cambios y hace commit.
    Devuelve True si el commit tuvo éxito (o no había nada que commitear), False si falla.
    """
    logPrefix = "hacerCommit:"
    log.info(f"{logPrefix} Intentando commit en {rutaRepo}")

    # Paso 1: Añadir todos los cambios (nuevos, modificados, eliminados)
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
    # Añadir --allow-empty si se quisiera permitir commits sin cambios (generalmente no deseado)
    if not ejecutarComando(['git', 'commit', '-m', mensaje], cwd=rutaRepo):
        # El comando falló. Ya logueamos el error dentro de ejecutarComando.
        log.error(f"{logPrefix} Falló 'git commit'. Verifique logs anteriores, configuración de git (user.name/email) o si hay hooks fallando.")
        return False

    log.info(f"{logPrefix} Commit realizado con éxito.")
    return True

def hacerPush(rutaRepo, rama):
    """Hace push de la rama especificada a origin."""
    logPrefix = "hacerPush:"
    log.info(f"{logPrefix} Intentando push de la rama '{rama}' a 'origin' desde {rutaRepo}")
    # 'git push origin <rama>' es suficiente si la rama remota ya existe o si
    # la configuración por defecto de push está bien.
    # Usar '-u' (o --set-upstream) la primera vez que se crea la rama es buena práctica,
    # pero puede ser redundante si ya se hizo checkout --track o -b origin/rama.
    # El push simple debería funcionar bien ahora que la URL remota es correcta.
    if not ejecutarComando(['git', 'push', 'origin', rama], cwd=rutaRepo):
        log.error(f"{logPrefix} Falló 'git push origin {rama}'. Verifique logs de error (stderr), credenciales (SSH keys para root), permisos en GitHub y si la rama remota requiere force-push (¡usar con MUCHO cuidado!).")
        return False
    log.info(f"{logPrefix} Push de la rama '{rama}' a origin realizado con éxito.")
    return True

def descartarCambiosLocales(rutaRepo):
    """
    Intenta resetear el repositorio a HEAD y limpiar archivos no rastreados.
    ¡Operación destructiva!
    """
    logPrefix = "descartarCambiosLocales:"
    log.warning(f"{logPrefix} ¡ATENCIÓN! Intentando descartar todos los cambios locales en {rutaRepo}...")
    # Resetear cambios trackeados al último commit
    resetOk = ejecutarComando(['git', 'reset', '--hard', 'HEAD'], cwd=rutaRepo)
    # Limpiar archivos y directorios no trackeados
    # -d para directorios, -f para forzar, -x para ignorados también (¡cuidado!)
    cleanOk = ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaRepo)

    if resetOk and cleanOk:
        log.info(f"{logPrefix} Cambios locales descartados exitosamente (reset --hard + clean -fdx).")
        return True
    else:
        # Log detallado del fallo
        msg = f"{logPrefix} Falló al descartar cambios locales. "
        if not resetOk: msg += "'git reset --hard' falló. "
        if not cleanOk: msg += "'git clean -fdx' falló. "
        msg += "El repositorio puede estar inconsistente."
        log.error(msg)
        return False