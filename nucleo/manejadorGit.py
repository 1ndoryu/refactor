# nucleo/manejadorGit.py
import subprocess
import os
import logging
import shutil 


def ejecutarComando(comando, cwd=None):
    # Ejecuta un comando de shell y devuelve True si tiene éxito, False si falla.
    
    logging.debug(
        f"ejecutarComando: Ejecutando '{' '.join(comando)}' en {cwd or os.getcwd()}")
    try:
        resultado = subprocess.run(
            comando, cwd=cwd, check=True, capture_output=True, text=True, encoding='utf-8')
        logging.debug(f"ejecutarComando: Salida: {resultado.stdout.strip()}")
        logging.info(
            f"ejecutarComando: Comando '{' '.join(comando)}' ejecutado con éxito.")
        return True
    except FileNotFoundError:
        logging.error(
            f"ejecutarComando: Error - El comando '{comando[0]}' no se encontró. ¿Está Git instalado y en el PATH?")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(
            f"ejecutarComando: Error al ejecutar '{' '.join(comando)}'. Código de salida: {e.returncode}")
        logging.error(f"ejecutarComando: Stderr: {e.stderr.strip()}")
        logging.error(f"ejecutarComando: Stdout: {e.stdout.strip()}")
        return False
    except Exception as e:
        logging.error(
            f"ejecutarComando: Error inesperado al ejecutar '{' '.join(comando)}': {e}")
        return False


def clonarOActualizarRepo(repoUrl, rutaLocal):

    # Clona un repositorio si no existe localmente, o lo actualiza (git pull) si ya existe.
    # Devuelve True si el repositorio está listo, False en caso de error.

    logPrefix = "clonarOActualizarRepo:"
    logging.info(
        f"{logPrefix} Iniciando gestion de repositorio {repoUrl} en {rutaLocal}")

    ramaPrincipal = "main" 

    if os.path.isdir(os.path.join(rutaLocal, '.git')):
        logging.info(
            f"{logPrefix} Repositorio existente encontrado en {rutaLocal}. Actualizando...")
        # Comandos para actualizar:
        # 1. Cambiar a la rama principal (por si estaba en otra)
        # 2. Descartar cambios locales (para evitar conflictos de pull simples, ¡cuidado!)
        # 3. Traer cambios del remoto
        # 4. Hacer pull (merge)

        # Opcional: Limpiar estado local antes de actualizar (¡Peligroso si hay cambios no deseados!)
        # if not ejecutarComando(['git', 'reset', '--hard', f'origin/{ramaPrincipal}'], cwd=rutaLocal):
        #     logging.error(f"{logPrefix} No se pudo resetear el repositorio local.")
        #     return False
        # if not ejecutarComando(['git', 'clean', '-fdx'], cwd=rutaLocal):
        #      logging.error(f"{logPrefix} No se pudo limpiar el repositorio local.")
        #      return False

        if not ejecutarComando(['git', 'fetch', 'origin'], cwd=rutaLocal):
            logging.error(f"{logPrefix} Falló 'git fetch'.")
            return False
        # Intentamos hacer checkout a la rama principal
        if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal):
            logging.warning(
                f"{logPrefix} No se pudo hacer checkout a la rama '{ramaPrincipal}'. Puede que no exista o haya conflictos. Intentando con 'master'...")
            ramaPrincipal = "master"
            if not ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal):
                logging.error(
                    f"{logPrefix} Tampoco se pudo hacer checkout a 'master'. Abortando actualización.")
                return False

        # Hacemos pull rebase para mantener historial limpio si es posible
        # Si falla el rebase, podría requerir intervención manual. Por ahora, fallamos.
        if not ejecutarComando(['git', 'pull', 'origin', ramaPrincipal, '--rebase'], cwd=rutaLocal):
            logging.error(
                f"{logPrefix} Falló 'git pull --rebase'. Puede haber conflictos. Verifica el repositorio en {rutaLocal}")
            # Podrías intentar un merge normal como fallback:
            # if not ejecutarComando(['git', 'merge', f'origin/{ramaPrincipal}'], cwd=rutaLocal):
            #    logging.error(f"{logPrefix} También falló 'git merge'. Se necesita intervención manual.")
            #    return False
            return False

        logging.info(f"{logPrefix} Repositorio actualizado con éxito.")
        return True
    else:
        logging.info(
            f"{logPrefix} Repositorio no encontrado en {rutaLocal}. Clonando...")
        # Si la ruta existe pero no es un repo git válido, la borramos para empezar limpio
        if os.path.exists(rutaLocal):
            logging.warning(
                f"{logPrefix} La ruta {rutaLocal} existe pero no es un repo Git válido. Se eliminará.")
            try:
                shutil.rmtree(rutaLocal)
            except OSError as e:
                logging.error(
                    f"{logPrefix} No se pudo eliminar el directorio existente {rutaLocal}: {e}")
                return False

        if ejecutarComando(['git', 'clone', repoUrl, rutaLocal]):
            logging.info(
                f"{logPrefix} Repositorio clonado con éxito en {rutaLocal}")
            # Opcional: checkout a la rama deseada si no es la por defecto
            # ejecutarComando(['git', 'checkout', ramaPrincipal], cwd=rutaLocal)
            return True
        else:
            logging.error(
                f"{logPrefix} Falló la clonación del repositorio {repoUrl}.")
            # Limpiamos si la clonación falló para evitar estados inconsistentes
            if os.path.exists(rutaLocal):
                try:
                    shutil.rmtree(rutaLocal)
                except OSError:
                    logging.error(
                        f"{logPrefix} No se pudo limpiar el directorio {rutaLocal} después de clonación fallida.")
            return False
