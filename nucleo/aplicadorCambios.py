# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import json
import codecs
import re

# Obtener logger
log = logging.getLogger(__name__)


# --- Helper function _validar_y_normalizar_ruta (Essential for Security) ---
def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    """
    Validates that a relative path stays within the base path and normalizes it.
    Prevents path traversal. Returns the absolute, normalized path if safe, else None.
    """
    logPrefix = "_validar_y_normalizar_ruta:"
    if not rutaRelativa or not isinstance(rutaRelativa, str):
        log.error(f"{logPrefix} Invalid relative path received (None or not string): {rutaRelativa!r}")
        return None

    # Normalize base path and ensure it's absolute
    rutaBaseAbs = os.path.abspath(rutaBase)
    rutaBaseNorm = os.path.normpath(rutaBaseAbs)

    # Normalize relative path, disallowing '..' components or absolute paths
    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    if os.path.isabs(rutaRelativaNorm) or '..' in rutaRelativaNorm.split(os.sep):
        log.error(f"{logPrefix} Invalid or suspicious relative path (absolute or contains '..'): '{rutaRelativa}' -> '{rutaRelativaNorm}'")
        return None

    # Join and normalize the final path
    rutaAbsCandidata = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbsNorm = os.path.normpath(rutaAbsCandidata)

    # Security Check: Use realpath for comparison to resolve symlinks
    # Check if the common path of the real base and real candidate is the real base
    try:
        rutaBaseReal = os.path.realpath(rutaBaseNorm)
        rutaAbsReal = os.path.realpath(rutaAbsNorm)
        if not os.path.isdir(rutaBaseReal): # Ensure base is a directory after resolving symlinks
             log.error(f"{logPrefix} Real base path is not a directory: '{rutaBaseReal}' (from '{rutaBase}')")
             return None

        # The core check: common path must be the base path itself
        # This handles cases where base is '/a/b' and candidate is '/a/b/c' or '/a/b'
        if os.path.commonpath([rutaBaseReal, rutaAbsReal]) == rutaBaseReal:
            # Path is safe
            if asegurar_existencia and not os.path.exists(rutaAbsReal):
                log.warning(f"{logPrefix} Path validated but does not exist (existence required): '{rutaAbsNorm}'")
                return None # Fail if existence was required

            log.debug(f"{logPrefix} Path validated and normalized to: '{rutaAbsNorm}'")
            # Return the normalized path (not realpath) to preserve intended structure unless symlinks must be followed
            return rutaAbsNorm
        else:
            log.error(f"{logPrefix} Path Traversal Attempt! Relative path '{rutaRelativa}' exits base '{rutaBaseNorm}'. Result: '{rutaAbsNorm}', Real Result: '{rutaAbsReal}', Real Base: '{rutaBaseReal}'")
            return None
    except Exception as e:
        log.error(f"{logPrefix} Error during path validation/realpath check for '{rutaRelativa}' in '{rutaBase}': {e}", exc_info=True)
        return None

# --- Mojibake common replacements (Robust Definition) ---
# Ensure keys represent the literal byte sequence misinterpreted as Latin-1/CP1252
# Use errors='ignore' for decode as some multi-byte UTF-8 chars might not have valid single-byte Latin-1 representations
MOJIBAKE_REPLACEMENTS = {
    b'\xc3\xa1'.decode('latin-1', errors='ignore'): "á",  # Ã¡ -> á
    b'\xc3\xa9'.decode('latin-1', errors='ignore'): "é",  # Ã© -> é
    b'\xc3\xad'.decode('latin-1', errors='ignore'): "í",  # Ã­ -> í
    b'\xc3\xb3'.decode('latin-1', errors='ignore'): "ó",  # Ã³ -> ó
    b'\xc3\xba'.decode('latin-1', errors='ignore'): "ú",  # Ãº -> ú
    b'\xc3\xbc'.decode('latin-1', errors='ignore'): "ü",  # Ã¼ -> ü
    b'\xc3\x81'.decode('latin-1', errors='ignore'): "Á",  # Ã -> Á
    b'\xc3\x89'.decode('latin-1', errors='ignore'): "É",  # Ã‰ -> É
    b'\xc3\x8d'.decode('latin-1', errors='ignore'): "Í",  # Ã -> Í
    b'\xc3\x93'.decode('latin-1', errors='ignore'): "Ó",  # Ã“ -> Ó
    b'\xc3\x9a'.decode('latin-1', errors='ignore'): "Ú",  # Ãš -> Ú
    b'\xc3\x9c'.decode('latin-1', errors='ignore'): "Ü",  # Ãœ -> Ü
    b'\xc3\xb1'.decode('latin-1', errors='ignore'): "ñ",  # Ã± -> ñ
    b'\xc3\x91'.decode('latin-1', errors='ignore'): "Ñ",  # Ã‘ -> Ñ
    b'\xc2\xa1'.decode('latin-1', errors='ignore'): "¡",  # Â¡ -> ¡
    b'\xc2\xbf'.decode('latin-1', errors='ignore'): "¿",  # Â¿ -> ¿
    b'\xc2\xaa'.decode('latin-1', errors='ignore'): "ª",  # Âª -> ª
    b'\xc2\xba'.decode('latin-1', errors='ignore'): "º",  # Âº -> º
    b'\xc2\xab'.decode('latin-1', errors='ignore'): "«",  # Â« -> «
    b'\xc2\xbb'.decode('latin-1', errors='ignore'): "»",  # Â» -> »
    # Common CP1252 / Windows-1252 issues mapped from their UTF-8 bytes misinterpreted as Latin-1
    b'\xe2\x82\xac'.decode('latin-1', errors='ignore'): "€", # â‚¬ -> €
    b'\xe2\x84\xa2'.decode('latin-1', errors='ignore'): "™", # â„¢ -> ™
    b'\xe2\x80\x99'.decode('latin-1', errors='ignore'): "’", # â€™ -> ’ (Right single quote)
    b'\xe2\x80\x98'.decode('latin-1', errors='ignore'): "‘", # â€˜ -> ‘ (Left single quote)
    b'\xe2\x80\x9c'.decode('latin-1', errors='ignore'): "“", # â€œ -> “ (Left double quote)
    b'\xe2\x80\x9d'.decode('latin-1', errors='ignore'): "”", # â€ -> ” (Right double quote)
    b'\xe2\x80\xa6'.decode('latin-1', errors='ignore'): "…", # â€¦ -> … (Ellipsis)
    b'\xe2\x80\x93'.decode('latin-1', errors='ignore'): "–", # â€“ -> – (En dash)
    b'\xe2\x80\x94'.decode('latin-1', errors='ignore'): "—", # â€” -> — (Em dash)
}

# --- FUNCIÓN PRINCIPAL (Estrategia: unicode_escape FIRST, then Targeted Replace Mojibake) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    """
    Applies changes generated by Gemini.
    - FIRST decodes standard escape sequences (\\n, \\t, \\uXXXX, \\\\) using 'unicode_escape'.
    - THEN replaces common Mojibake sequences using a predefined map.
    - Writes files in UTF-8. Handles delete/create actions.
    """
    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Applying changes for original action '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase) # Use normalized base path

    # --- Handle delete_file, create_directory ---
    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        targetRel = paramsOriginal.get("archivo") or paramsOriginal.get("directorio")
        if not targetRel:
            return False, f"Missing target parameter ('archivo' or 'directorio') for {accionOriginal}."
        targetAbs = _validar_y_normalizar_ruta(targetRel, rutaBaseNorm, asegurar_existencia=False)
        if targetAbs is None:
            return False, f"Invalid or unsafe path provided for {accionOriginal}: '{targetRel}'"

        if accionOriginal == "eliminar_archivo":
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Targeting {targetRel} (Abs: {targetAbs})")
            if os.path.exists(targetAbs):
                try:
                    if os.path.isfile(targetAbs) or os.path.islink(targetAbs):
                        os.remove(targetAbs)
                        log.info(f"{logPrefix} File/Link '{targetRel}' deleted.")
                    elif os.path.isdir(targetAbs):
                        # Decide on deleting non-empty: shutil.rmtree(targetAbs) vs os.rmdir(targetAbs)
                        try:
                            os.rmdir(targetAbs) # Try removing empty dir first
                            log.info(f"{logPrefix} Empty directory '{targetRel}' deleted.")
                        except OSError: # Directory not empty
                            # Option 1: Fail
                            # err = f"Directory '{targetRel}' is not empty. Deletion aborted for safety."
                            # log.error(f"{logPrefix} {err}")
                            # return False, err
                            # Option 2: Delete recursively (USE WITH CAUTION)
                            log.warning(f"{logPrefix} Directory '{targetRel}' not empty. Attempting recursive delete with shutil.rmtree.")
                            shutil.rmtree(targetAbs)
                            log.info(f"{logPrefix} Non-empty directory '{targetRel}' recursively deleted.")
                    else:
                        err = f"Target '{targetRel}' exists but is not a file, link, or directory."
                        log.error(f"{logPrefix} {err}")
                        return False, err
                    return True, None
                except Exception as e:
                    err = f"Error deleting '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    return False, err
            else:
                log.warning(f"{logPrefix} Target '{targetRel}' not found for deletion. Considering successful.")
                return True, None

        elif accionOriginal == "crear_directorio":
            # dirRel is targetRel here
            # dirAbs is targetAbs
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Creating directory {targetRel} (Abs: {targetAbs})")
            if os.path.exists(targetAbs):
                if os.path.isdir(targetAbs):
                    log.warning(f"{logPrefix} Directory '{targetRel}' already exists.")
                    return True, None
                else:
                    err = f"Path '{targetRel}' exists but is not a directory. Cannot create directory."
                    log.error(f"{logPrefix} {err}")
                    return False, err
            else:
                try:
                    os.makedirs(targetAbs, exist_ok=True) # exist_ok=True is generally safe here
                    log.info(f"{logPrefix} Directory '{targetRel}' created.")
                    return True, None
                except Exception as e:
                    err = f"Error creating directory '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    return False, err

    # --- Initial Validations for content operations ---
    if not isinstance(archivos_con_contenido, dict):
         err = "Argument 'archivos_con_contenido' is not a dictionary."
         log.error(f"{logPrefix} {err}")
         return False, err
    if not archivos_con_contenido:
        # Allow if action didn't require content (already handled above)
        if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             err = f"Expected content in 'archivos_con_contenido' for action '{accionOriginal}', but it's empty. Likely error in Step 2."
             log.error(f"{logPrefix} {err}")
             return False, err
        else:
            # This state might be reachable if action was handled but flow didn't exit? Log and proceed.
            log.info(f"{logPrefix} No content in 'archivos_con_contenido', which is expected for action '{accionOriginal}'.")
            return True, None # Assume success if action was handled

    log.info(f"{logPrefix} Processing {len(archivos_con_contenido)} file(s) for writing/modification...")
    archivosProcesados = []
    errores = []

    # --- Main loop for writing files ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        # --- Path validation and parent directory creation ---
        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Invalid or unsafe path ('{rutaRel}') received from Gemini (Step 2). File skipped."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        # --- String type validation/conversion ---
        if not isinstance(contenido_original_json, str):
             log.warning(f"{logPrefix} Content for '{rutaRel}' is not string (type {type(contenido_original_json)}). Converting to JSON string.")
             try:
                 contenido_str = json.dumps(contenido_original_json, indent=2, ensure_ascii=False)
             except Exception as e_conv:
                  log.error(f"{logPrefix} Could not convert non-string content to string for '{rutaRel}': {e_conv}. Skipping file.")
                  errores.append(f"Invalid non-string content for {rutaRel}")
                  continue
        else:
             contenido_str = contenido_original_json

        # --- Parent Directory Creation ---
        dirPadre = os.path.dirname(archivoAbs)
        try:
            if dirPadre and not os.path.exists(dirPadre): # Check if dirPadre is not empty (for root files)
                log.info(f"{logPrefix} Creating necessary parent directory: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif dirPadre and not os.path.isdir(dirPadre):
                 # If the parent path exists but is a file, raise error
                 raise ValueError(f"Parent path '{dirPadre}' for file '{rutaRel}' exists but is NOT a directory.")
        except Exception as e_dir:
            msg = f"Error creating/validating parent directory '{dirPadre}' for '{rutaRel}': {e_dir}. File skipped."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue

       # --- Start Correction Block (STRATEGY: unicode_escape FIRST, then Targeted Replace) ---
        contenido_procesado = contenido_str
        log.debug(f"{logPrefix} Content ORIGINAL for '{rutaRel}' (repr): {repr(contenido_procesado[:200])}...")

        # Determinar extensión del archivo para condicionar el procesamiento de escapes
        ext = os.path.splitext(rutaRel)[1].lower()

        try:
            # --- STEP 1: Decode standard escapes (incluyendo \uXXXX, \n, \t, \\) ---
            if ext == '.php':
                log.debug(f"{logPrefix} Archivo PHP detectado ('{rutaRel}'): se omite la decodificación de escapes.")
                contenido_despues_escape = contenido_procesado
            else:
                contenido_despues_escape = contenido_procesado  # valor por defecto
                # Solo aplicar si se detecta al menos una barra invertida
                if '\\' in contenido_procesado:
                    log.debug(f"{logPrefix} Aplicando codecs.decode(..., 'unicode_escape') para '{rutaRel}'")
                    contenido_decodificado = codecs.decode(contenido_procesado, 'unicode_escape', errors='strict')
                    if contenido_decodificado != contenido_procesado:
                        log.info(f"{logPrefix} CORRECCIÓN (unicode_escape): Secuencias de escape decodificadas para '{rutaRel}'.")
                        contenido_despues_escape = contenido_decodificado
                    else:
                        log.debug(f"{logPrefix} 'unicode_escape' aplicado sin cambios en '{rutaRel}'.")
                else:
                    log.debug(f"{logPrefix} No se encontraron barras invertidas; se omite 'unicode_escape' para '{rutaRel}'.")

            # El contenido listo para reemplazo de Mojibake
            contenido_intermedio = contenido_despues_escape
            log.debug(f"{logPrefix} Content AFTER unicode_escape para '{rutaRel}' (repr): {repr(contenido_intermedio[:200])}...")

            # --- STEP 2: Reemplazo de secuencias de Mojibake comunes ---
            contenido_final = contenido_intermedio  # Empezamos con el resultado tras escapes
            replacements_made = False  # Para indicar si se realizó algún cambio
            temp_contenido = contenido_intermedio

            for mojibake, correct in MOJIBAKE_REPLACEMENTS.items():
                new_temp_contenido = temp_contenido.replace(mojibake, correct)
                if new_temp_contenido != temp_contenido:
                    if not replacements_made:
                        log.info(f"{logPrefix} CORRECCIÓN (Mojibake Replace): Se reemplazarán secuencias Mojibake para '{rutaRel}'.")
                    log.debug(f"{logPrefix}   Reemplazado: {repr(mojibake)} -> {repr(correct)}")
                    replacements_made = True
                    temp_contenido = new_temp_contenido

            if replacements_made:
                contenido_final = temp_contenido
            else:
                log.debug(f"{logPrefix} No se encontraron secuencias Mojibake en '{rutaRel}' tras escapes.")

            log.debug(f"{logPrefix} Content AFTER Mojibake Replace para '{rutaRel}' (repr): {repr(contenido_final[:200])}...")

            for mojibake, correct in MOJIBAKE_REPLACEMENTS.items():
                # Repeatedly replace until no more occurrences are found
                # This handles cases where replacements might create new instances (unlikely here but safer)
                # However, simple replace loop is usually sufficient and faster
                # Use the simpler loop first:
                new_temp_contenido = temp_contenido.replace(mojibake, correct)
                if new_temp_contenido != temp_contenido:
                    if not replacements_made: # Log first time only for this file
                        log.info(f"{logPrefix} CORRECTION (Mojibake Replace): Common Mojibake sequence(s) being replaced AFTER escapes for '{rutaRel}'.")
                    # Log details of the specific replacement
                    log.debug(f"{logPrefix}   Replaced: {repr(mojibake)} -> {repr(correct)}")
                    replacements_made = True
                    temp_contenido = new_temp_contenido # Update string for next replacement in loop


            if replacements_made:
                 # log.info(...) # Logged first instance above
                 contenido_final = temp_contenido # Assign the fully modified string
            else:
                 log.debug(f"{logPrefix} No common Mojibake sequences found/replaced after escapes for '{rutaRel}'.")
                 # contenido_final remains contenido_intermedio (result after escapes)

            log.debug(f"{logPrefix} Content AFTER Mojibake Replace (post-escapes) for '{rutaRel}' (repr): {repr(contenido_final[:200])}...") # Log final result before write

            contenido_a_escribir = contenido_final

            # --- STEP 3: Final Diagnostics and Writing ---
            log.debug(f"{logPrefix} FINAL content to write for '{rutaRel}' (start, repr): {repr(contenido_a_escribir[:200])}")

            # Final check for remaining Mojibake (indicates uncommon Mojibake not in map)
            # Check if any key from the dictionary is STILL present
            remaining_mojibake_keys = [k for k in MOJIBAKE_REPLACEMENTS.keys() if k in contenido_a_escribir]
            if remaining_mojibake_keys:
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain known Mojibake patterns AFTER processing (e.g., {remaining_mojibake_keys[:3]}). Check MOJIBAKE_REPLACEMENTS map or input data.")

            # Final check for remaining literal \uXXXX escapes (indicates issue or intentional double-escape \\uXXXX)
            if re.search(r'\\u[0-9a-fA-F]{4}', contenido_a_escribir):
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain literal \\uXXXX escapes AFTER processing. This could be intended if input was e.g., '\\\\uXXXX'.")

            # Write the final result in UTF-8
            log.debug(f"{logPrefix} Writing {len(contenido_a_escribir)} characters to {archivoAbs} using UTF-8")
            with open(archivoAbs, 'w', encoding='utf-8') as f:
                f.write(contenido_a_escribir)
            log.info(f"{logPrefix} File '{rutaRel}' written/overwritten successfully.")
            archivosProcesados.append(rutaRel)

        except Exception as e_process_write:
             # Catch errors during the processing/writing of a specific file
             msg = f"Error processing/writing file '{rutaRel}': {e_process_write}"
             log.error(f"{logPrefix} {msg}", exc_info=True)
             errores.append(msg)
             # Continue with the next file

    # --- End of loop ---

    # --- Final Evaluation ---
    if errores:
        error_summary = f"Process completed with {len(errores)} error(s): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary
    elif not archivosProcesados and archivos_con_contenido:
         # All files provided failed processing
         msg = "Content was provided but no files could be processed due to errors (see logs)."
         log.error(f"{logPrefix} {msg}")
         return False, msg
    # No errors, or only errors were handled (like file not found on delete)
    log.info(f"{logPrefix} Processing finished. {len(archivosProcesados)} files written/modified successfully.")
    return True, None # Success