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
    try:
        rutaBaseAbs = os.path.abspath(rutaBase)
        rutaBaseNorm = os.path.normpath(rutaBaseAbs)
    except Exception as e:
        log.error(f"{logPrefix} Error normalizing base path '{rutaBase}': {e}")
        return None

    # Normalize relative path, disallowing '..' components or absolute paths
    try:
        rutaRelativaNorm = os.path.normpath(rutaRelativa)
    except Exception as e:
         log.error(f"{logPrefix} Error normalizing relative path '{rutaRelativa}': {e}")
         return None

    if os.path.isabs(rutaRelativaNorm) or rutaRelativaNorm.startswith('..'+os.sep) or os.sep+'..' in rutaRelativaNorm:
        log.error(f"{logPrefix} Invalid or suspicious relative path (absolute or contains '..'): '{rutaRelativa}' -> '{rutaRelativaNorm}'")
        return None

    # Join and normalize the final path
    rutaAbsCandidata = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbsNorm = os.path.normpath(rutaAbsCandidata)

    # Security Check: Use realpath for comparison to resolve symlinks
    # Compare the normalized absolute path with the normalized base path
    try:
        # Ensure the base path exists and is a directory for comparison
        # This check should ideally happen *before* calling this validation function often,
        # but we include a basic check here for robustness.
        # Use realpath carefully, only on existing parts if possible.
        if not os.path.commonpath([rutaBaseNorm, rutaAbsNorm]) == rutaBaseNorm:
            # Use realpath for a potentially more robust check against symlinks,
            # but be aware realpath fails on non-existent paths.
            try:
                rutaBaseReal = os.path.realpath(rutaBaseNorm)
                rutaAbsReal = os.path.realpath(rutaAbsNorm)
                 # Check again after resolving symlinks
                if not os.path.commonpath([rutaBaseReal, rutaAbsReal]) == rutaBaseReal:
                    log.error(f"{logPrefix} Path Traversal Attempt Detected (Realpath check)! Relative path '{rutaRelativa}' exits base '{rutaBaseNorm}'. Real Result: '{rutaAbsReal}', Real Base: '{rutaBaseReal}'")
                    return None
            except FileNotFoundError:
                 # If realpath fails because part of the path doesn't exist yet (e.g., creating new file),
                 # the initial commonpath check is our best bet. We already checked it failed.
                 log.error(f"{logPrefix} Path Traversal Attempt Detected (Commonpath check)! Relative path '{rutaRelativa}' exits base '{rutaBaseNorm}'. Result: '{rutaAbsNorm}'")
                 return None
            except Exception as e_real:
                 log.error(f"{logPrefix} Error during realpath check for '{rutaRelativa}' in '{rutaBase}': {e_real}. Falling back to commonpath check result.")
                 # Since the initial commonpath check failed, return None.
                 return None


        # Path seems safe based on commonpath
        if asegurar_existencia:
            # Perform the existence check *after* validation using the normalized path
            if not os.path.exists(rutaAbsNorm):
                log.warning(f"{logPrefix} Path validated but does not exist (existence required): '{rutaAbsNorm}'")
                return None # Fail if existence was required

        log.debug(f"{logPrefix} Path validated and normalized to: '{rutaAbsNorm}'")
        # Return the normalized path (not realpath unless specifically needed downstream)
        return rutaAbsNorm

    except Exception as e:
        log.error(f"{logPrefix} Unexpected error during path validation for '{rutaRelativa}' in '{rutaBase}': {e}", exc_info=True)
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


# --- Helper function for controlled escape replacement ---
def _reemplazar_escapes_controlado(text):
    """
    Replaces specific escape sequences (\n, \t, \r, \\, \uXXXX) manually.
    Avoids the broad and potentially problematic 'unicode_escape' codec.
    """
    logPrefix = "_reemplazar_escapes_controlado:"
    if not isinstance(text, str) or '\\' not in text: # Optimization: Skip if no backslash
        return text # Return as is if not string or no escapes likely

    original_text = text
    text_changed = False # Track if any change occurs
    processed_text = text

    # 1. Replace simple escapes first (more common)
    # IMPORTANT: Order matters. Replace \\ first.
    simple_replacements = {
        '\\\\': '\\',
        '\\n': '\n',
        '\\t': '\t',
        '\\r': '\r',
        # Add others like \f, \b if needed, but often not from JSON sources
        # We are intentionally NOT handling \' or \" because they should have been
        # handled by the initial JSON parsing if the string came from JSON.
        # If the string *is* code, we want to preserve literal \' and \" within strings.
    }

    # Create a temporary variable to hold changes during this stage
    current_text_stage1 = processed_text
    stage1_changed = False
    for escaped, unescaped in simple_replacements.items():
        # Use a temporary var to check if replace did anything in *this* iteration
        text_after_replace = current_text_stage1.replace(escaped, unescaped)
        if text_after_replace != current_text_stage1:
             if not stage1_changed: # Log header only once for this stage
                  log.info(f"{logPrefix} Replacing common simple escape sequences...")
                  stage1_changed = True
             log.debug(f"{logPrefix}   Replaced simple: {repr(escaped)} -> {repr(unescaped)}")
             current_text_stage1 = text_after_replace # Update for next replacement

    if stage1_changed:
        text_changed = True # Mark that *some* change happened overall
        processed_text = current_text_stage1 # Update main processed text


    # 2. Replace \uXXXX escapes using regex and chr()
    # Use a temporary variable for this stage as well
    current_text_stage2 = processed_text
    stage2_changed = False

    # Define the replacement function separately for clarity and error handling
    def replace_unicode_match(match):
        nonlocal stage2_changed # Allow modification of the flag
        escape_seq = match.group(0) # The whole \uXXXX sequence
        hex_code = match.group(1) # The XXXX part
        try:
            char_code = int(hex_code, 16)
            # Check if the code point is valid for chr()
            # (Handles potential surrogate pairs if needed, although chr usually handles this range)
            # Basic check for validity range (Python handles surrogates internally mostly)
            if 0 <= char_code <= 0x10FFFF:
                 char = chr(char_code)
                 log.debug(f"{logPrefix}   Replaced Unicode: {escape_seq} -> {repr(char)}")
                 stage2_changed = True # Mark change for this stage
                 return char
            else:
                log.warning(f"{logPrefix} Unicode escape sequence {escape_seq} is out of valid range. Leaving as is.")
                return escape_seq
        except ValueError:
            # Invalid hex code format (shouldn't happen with regex '[0-9a-fA-F]{4}')
            # or potentially other issues with chr() (though less likely with range check)
            log.warning(f"{logPrefix} Invalid Unicode escape sequence {escape_seq} (format or value error). Leaving as is.")
            return escape_seq # Return the original sequence if invalid

    try:
        # Apply the substitution using the function
        final_text = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode_match, current_text_stage2)

        if stage2_changed:
            if not stage1_changed: # Log header only if simple escapes didn't log it
                 log.info(f"{logPrefix} Replacing Unicode escape sequences...")
            text_changed = True # Mark overall change
            processed_text = final_text # Update main processed text
        # If no changes in stage 2, processed_text remains as it was after stage 1

    except Exception as e_re:
        log.error(f"{logPrefix} Error during regex substitution for Unicode escapes: {e_re}. Returning text after simple escapes.", exc_info=True)
        # Fallback: return the text processed after stage 1 (simple escapes)
        # processed_text already holds this value if stage 2 failed
        pass # Keep processed_text as is

    # Final log message based on whether *any* change occurred
    if not text_changed:
         log.debug(f"{logPrefix} No targeted escape sequences found or replaced.")
    # No need for an "else" log here, details were logged during replacement stages.

    return processed_text


# --- FUNCIÓN PRINCIPAL (Estrategia: Escapes Controlados FIRST, then Mojibake Replace) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    """
    Applies changes generated by Gemini.
    - FIRST replaces specific escape sequences (\n, \t, \\, \uXXXX) in a controlled manner.
    - THEN replaces common Mojibake sequences using a predefined map.
    - Writes files in UTF-8. Handles delete/create actions.
    """
    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Applying changes for original action '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase)

    # --- Handle delete_file, create_directory ---
    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        targetRel = paramsOriginal.get("archivo") or paramsOriginal.get("directorio")
        if not targetRel:
            return False, f"Missing target parameter ('archivo' or 'directorio') for {accionOriginal}."

        targetAbs = _validar_y_normalizar_ruta(targetRel, rutaBaseNorm, asegurar_existencia=False)
        if targetAbs is None:
            # Validation failed, _validar_y_normalizar_ruta already logged error
            return False, f"Invalid or unsafe path provided for {accionOriginal}: '{targetRel}'"

        if accionOriginal == "eliminar_archivo":
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Targeting {targetRel} (Abs: {targetAbs})")
            if os.path.exists(targetAbs):
                try:
                    if os.path.isfile(targetAbs) or os.path.islink(targetAbs):
                        os.remove(targetAbs)
                        log.info(f"{logPrefix} File/Link '{targetRel}' deleted.")
                    elif os.path.isdir(targetAbs):
                        try:
                            os.rmdir(targetAbs) # Try removing empty dir first
                            log.info(f"{logPrefix} Empty directory '{targetRel}' deleted.")
                        except OSError: # Directory not empty
                            log.warning(f"{logPrefix} Directory '{targetRel}' not empty. Attempting recursive delete with shutil.rmtree.")
                            shutil.rmtree(targetAbs)
                            log.info(f"{logPrefix} Non-empty directory '{targetRel}' recursively deleted.")
                    else:
                        # Should not happen if os.path.exists is true, but good practice
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
                    # Create directory using the validated absolute path
                    os.makedirs(targetAbs, exist_ok=True) # exist_ok=True is generally safe
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
        # This case should ideally not be reached if the action was delete/create,
        # as those return earlier. If it's reached for other actions, it's an error.
        if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             err = f"Expected content in 'archivos_con_contenido' for action '{accionOriginal}', but it's empty. Likely error in Step 2."
             log.error(f"{logPrefix} {err}")
             return False, err
        else:
            # Should technically not happen, but log if it does. Assume prior action handled it.
            log.warning(f"{logPrefix} No content in 'archivos_con_contenido', but action was '{accionOriginal}'. Assuming prior success.")
            return True, None

    log.info(f"{logPrefix} Processing {len(archivos_con_contenido)} file(s) for writing/modification...")
    archivosProcesados = []
    errores = []

    # --- Main loop for writing files ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        # --- Path validation ---
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
                 # Convert non-string content to JSON string with indentation and ensure_ascii=False
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
            # Check if dirPadre is not empty (e.g., for files in the root of rutaBase)
            # and if it exists and is not a directory
            if dirPadre:
                 if os.path.exists(dirPadre) and not os.path.isdir(dirPadre):
                      # If the parent path exists but is a file, raise error
                      raise ValueError(f"Parent path '{dirPadre}' for file '{rutaRel}' exists but is NOT a directory.")
                 elif not os.path.exists(dirPadre):
                      log.info(f"{logPrefix} Creating necessary parent directory: {dirPadre}")
                      os.makedirs(dirPadre, exist_ok=True)
            # If dirPadre is empty (root file), no need to create/check directory.
        except Exception as e_dir:
            msg = f"Error creating/validating parent directory '{dirPadre}' for '{rutaRel}': {e_dir}. File skipped."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue

        # --- Start Correction Block (NEW STRATEGY: Controlled Escapes FIRST, then Mojibake Replace) ---
        contenido_procesado = contenido_str
        log.debug(f"{logPrefix} Content ORIGINAL for '{rutaRel}' (repr): {repr(contenido_procesado[:200])}...")

        try:
            # --- STEP 1: Replace specific escapes in a controlled manner ---
            # log.debug(f"{logPrefix} Applying controlled escape replacement for '{rutaRel}'...") # Logged inside helper now
            contenido_despues_escape = _reemplazar_escapes_controlado(contenido_procesado)
            log.debug(f"{logPrefix} Content AFTER controlled escapes for '{rutaRel}' (repr): {repr(contenido_despues_escape[:200])}...")


            # --- STEP 2: Replace common Mojibake sequences ---
            contenido_intermedio = contenido_despues_escape # Start with the result after escapes
            contenido_final = contenido_intermedio # Default if no mojibake found
            replacements_made = False # Flag to track if any Mojibake change happened
            temp_contenido = contenido_intermedio

            for mojibake, correct in MOJIBAKE_REPLACEMENTS.items():
                # Simple replace is usually sufficient and faster for non-overlapping patterns
                new_temp_contenido = temp_contenido.replace(mojibake, correct)
                if new_temp_contenido != temp_contenido:
                    if not replacements_made: # Log header first time only
                        log.info(f"{logPrefix} CORRECTION (Mojibake Replace): Common Mojibake sequence(s) being replaced AFTER controlled escapes for '{rutaRel}'.")
                    log.debug(f"{logPrefix}   Replaced Mojibake: {repr(mojibake)} -> {repr(correct)}")
                    replacements_made = True
                    temp_contenido = new_temp_contenido # Update string for next replacement


            if replacements_made:
                 contenido_final = temp_contenido # Assign the fully modified string
            else:
                 log.debug(f"{logPrefix} No common Mojibake sequences found/replaced after controlled escapes for '{rutaRel}'.")
                 # contenido_final remains contenido_intermedio (result after escapes)

            log.debug(f"{logPrefix} Content AFTER Mojibake Replace (post-escapes) for '{rutaRel}' (repr): {repr(contenido_final[:200])}...") # Log result before write checks

            contenido_a_escribir = contenido_final

            # --- STEP 3: Final Diagnostics and Writing ---
            log.debug(f"{logPrefix} FINAL content to write for '{rutaRel}' (start, repr): {repr(contenido_a_escribir[:200])}")

            # Final check for remaining Mojibake (indicates uncommon Mojibake not in map)
            remaining_mojibake_keys = [k for k in MOJIBAKE_REPLACEMENTS.keys() if k in contenido_a_escribir]
            if remaining_mojibake_keys:
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain known Mojibake patterns AFTER processing (e.g., {remaining_mojibake_keys[:3]}). Check MOJIBAKE_REPLACEMENTS map or input data.")

            # Final check for remaining literal \uXXXX or simple escapes (indicates issue in _reemplazar_escapes_controlado OR intentional double-escape)
            if re.search(r'\\u[0-9a-fA-F]{4}', contenido_a_escribir):
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain literal \\uXXXX escapes AFTER processing. Could be intended (e.g., '\\\\uXXXX' input) or issue in escape handling.")
            if re.search(r'\\[nrt\\]', contenido_a_escribir): # Check for \n, \r, \t, \\
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain literal simple escapes (\\n, \\t, \\r, \\\\) AFTER processing. Check input or escape handling.")


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
        # If there were errors during processing individual files
        error_summary = f"Process completed with {len(errores)} error(s): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        # Return False even if some files were processed successfully
        return False, error_summary
    elif not archivosProcesados and archivos_con_contenido:
         # Check if content was provided but *no* files were successfully processed
         # This check ensures we didn't just silently fail on every file
         msg = "Content was provided but no files could be processed successfully (check logs for per-file errors)."
         log.error(f"{logPrefix} {msg}")
         # This is definitely a failure state if content was expected
         return False, msg
    # If no errors were recorded in the `errores` list AND
    # (either archivosProcesados has items OR archivos_con_contenido was empty initially for delete/create actions)
    # then consider the overall operation successful.
    log.info(f"{logPrefix} Processing finished. {len(archivosProcesados)} files written/modified successfully.")
    return True, None # Success