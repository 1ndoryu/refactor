# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import json
# import codecs # No longer needed for 'unicode_escape'
import re
import ftfy # Import the library

# Get logger
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
        # Ensure rutaBase is treated as a string
        rutaBaseStr = str(rutaBase)
        rutaBaseAbs = os.path.abspath(rutaBaseStr)
        rutaBaseNorm = os.path.normpath(rutaBaseAbs)
    except Exception as e:
        log.error(f"{logPrefix} Error normalizing base path '{rutaBase}': {e}")
        return None

    # Normalize relative path, disallowing '..' components or absolute paths
    try:
        # Ensure rutaRelativa is treated as a string
        rutaRelativaStr = str(rutaRelativa)
        rutaRelativaNorm = os.path.normpath(rutaRelativaStr)
    except Exception as e:
         log.error(f"{logPrefix} Error normalizing relative path '{rutaRelativa}': {e}")
         return None

    # Check for absolute paths or path traversal attempts more carefully
    # os.path.isabs() checks for leading '/' or 'C:\' etc.
    # Also check for '..' components explicitly
    # Ensure comparison is done case-insensitively on Windows if necessary, though normpath helps
    rutaRelativaNorm_lower = rutaRelativaNorm.lower()
    if os.path.isabs(rutaRelativaNorm) or \
       rutaRelativaNorm_lower.startswith('..' + os.sep) or \
       (os.sep + '..' + os.sep) in rutaRelativaNorm_lower or \
       rutaRelativaNorm_lower.endswith(os.sep + '..'):
        log.error(f"{logPrefix} Invalid or suspicious relative path (absolute or contains '..'): '{rutaRelativa}' -> '{rutaRelativaNorm}'")
        return None

    # Join and normalize the final path
    rutaAbsCandidata = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbsNorm = os.path.normpath(rutaAbsCandidata)

    # Security Check: Compare the normalized absolute path with the normalized base path
    # Use os.path.commonpath as the primary check. It's generally reliable.
    try:
        # Ensure the common prefix is *exactly* the base path.
        # Using rstrip(os.sep) helps handle cases like base='/a/b' vs candidate='/a/b/'
        # On Windows, compare case-insensitively
        common = os.path.commonpath([rutaBaseNorm, rutaAbsNorm])
        base_to_compare = rutaBaseNorm
        common_to_compare = common

        if os.name == 'nt': # Case-insensitive comparison for Windows
             base_to_compare = base_to_compare.lower()
             common_to_compare = common_to_compare.lower()

        if common_to_compare.rstrip(os.sep) != base_to_compare.rstrip(os.sep):
            # If common path doesn't match, it's potentially unsafe.
            log.error(f"{logPrefix} Path Traversal Attempt Detected! Common path '{common}' does not match base path '{rutaBaseNorm}'. Candidate: '{rutaAbsNorm}'")
            return None # Return None based on commonpath failure

        # Path seems safe based on commonpath
        if asegurar_existencia:
            # Perform the existence check *after* validation
            if not os.path.exists(rutaAbsNorm):
                log.warning(f"{logPrefix} Path validated but does not exist (existence required): '{rutaAbsNorm}'")
                return None

        log.debug(f"{logPrefix} Path validated and normalized to: '{rutaAbsNorm}'")
        return rutaAbsNorm

    except ValueError as e_val:
        # commonpath raises ValueError if paths are on different drives (Windows)
        log.error(f"{logPrefix} Path validation failed (ValueError, possibly different drives?): {e_val}. Base='{rutaBaseNorm}', Candidate='{rutaAbsNorm}'")
        return None
    except Exception as e:
        log.error(f"{logPrefix} Unexpected error during path validation for '{rutaRelativa}' in '{rutaBase}': {e}", exc_info=True)
        return None


# --- MOJIBAKE_REPLACEMENTS is no longer needed ---

# --- Helper function for controlled escape replacement ---
def _reemplazar_escapes_controlado(text):
    """
    Replaces specific escape sequences (\n, \t, \r, \\, \\uXXXX) manually.
    Avoids the broad and potentially problematic 'unicode_escape' codec.
    """
    logPrefix = "_reemplazar_escapes_controlado:"
    # Ensure input is a string
    if not isinstance(text, str):
        log.warning(f"{logPrefix} Input is not a string (type: {type(text)}). Returning as is.")
        return text

    # Optimization: Skip if no backslash present
    if '\\' not in text:
        return text

    original_text = text
    text_changed = False # Track overall change
    processed_text = text

    # 1. Replace simple escapes (\n, \t, \r, \\)
    simple_replacements = {
        '\\\\': '\\', # MUST be first to handle escaped backslashes correctly
        '\\n': '\n',
        '\\t': '\t',
        '\\r': '\r',
        # Add other simple escapes like \f, \b if needed
    }
    current_text_stage1 = processed_text
    stage1_changed = False
    for escaped, unescaped in simple_replacements.items():
        text_after_replace = current_text_stage1.replace(escaped, unescaped)
        if text_after_replace != current_text_stage1:
             if not stage1_changed:
                  log.info(f"{logPrefix} Replacing common simple escape sequences...")
                  stage1_changed = True
             log.debug(f"{logPrefix}   Replaced simple: {repr(escaped)} -> {repr(unescaped)}")
             current_text_stage1 = text_after_replace # Update text for the next replacement in this stage
    if stage1_changed:
        text_changed = True
        processed_text = current_text_stage1 # Update main processed text after all simple replacements

    # 2. Replace \uXXXX escapes using regex substitution
    current_text_stage2 = processed_text # Start with text after simple escapes
    stage2_changed = False
    def replace_unicode_match(match):
        nonlocal stage2_changed # Allow modification of the outer scope flag
        escape_seq = match.group(0) # The matched escape sequence (e.g., \u00f3)
        hex_code = match.group(1) # The hexadecimal part (e.g., 00f3)
        try:
            char_code = int(hex_code, 16)
            # Check if the code point is within the valid Unicode range
            if 0 <= char_code <= 0x10FFFF:
                 # Check for surrogate pairs (though chr usually handles them in Python 3)
                 # High surrogates: U+D800 to U+DBFF
                 # Low surrogates: U+DC00 to U+DFFF
                 if 0xD800 <= char_code <= 0xDFFF:
                      log.warning(f"{logPrefix} Encountered Unicode surrogate escape {escape_seq}. Leaving as is, as these require pairs.")
                      return escape_seq # Return original escape, don't replace surrogates individually
                 else:
                      char = chr(char_code)
                      log.debug(f"{logPrefix}   Replaced Unicode: {escape_seq} -> {repr(char)}")
                      stage2_changed = True # Mark that a change occurred in this stage
                      return char
            else:
                # Code point is outside the valid Unicode range
                log.warning(f"{logPrefix} Unicode escape sequence {escape_seq} is out of valid range [0x0-0x10FFFF]. Leaving as is.")
                return escape_seq # Return original if out of range
        except ValueError:
            # Error converting hex to int (shouldn't happen with the regex)
            log.warning(f"{logPrefix} Invalid hexadecimal in Unicode escape sequence {escape_seq}. Leaving as is.")
            return escape_seq # Return original if conversion fails
        except Exception as e_chr:
             # Catch potential errors from chr() itself, though unlikely with range check
             log.warning(f"{logPrefix} Error converting Unicode escape {escape_seq} using chr(): {e_chr}. Leaving as is.")
             return escape_seq

    try:
        # Find all \uXXXX sequences and replace them using the helper function
        # Regex ensures we only match valid hex characters
        final_text = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode_match, current_text_stage2)

        if stage2_changed:
            if not stage1_changed: # Log header only if simple escapes didn't log it
                 log.info(f"{logPrefix} Replacing Unicode escape sequences...")
            text_changed = True # Mark overall change occurred
            processed_text = final_text # Update main processed text
        # If no changes in stage 2, processed_text remains as it was after stage 1

    except Exception as e_re:
        # Catch potential errors during the regex substitution process
        log.error(f"{logPrefix} Error during regex substitution for Unicode escapes: {e_re}. Returning text after simple escapes.", exc_info=True)
        # Fallback: processed_text already holds the result after stage 1 if stage 2 failed
        pass # Keep processed_text as is (result after simple escapes)

    # Final log message indicating whether any replacements were made
    if not text_changed:
         log.debug(f"{logPrefix} No targeted escape sequences found or replaced.")
    # If changes occurred, detailed logs were already generated during the stages

    return processed_text


# --- FUNCIÓN PRINCIPAL (Estrategia: ftfy FIRST, then Controlled Escapes) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    """
    Applies changes generated by Gemini.
    - FIRST uses `ftfy.fix_text` to correct Mojibake and other encoding issues.
    - THEN replaces specific escape sequences (\n, \t, \\, \\uXXXX) in a controlled manner.
    - Writes files in UTF-8. Handles delete/create actions.
    """
    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Applying changes for original action '{accionOriginal}'...")
    try:
        rutaBaseNorm = os.path.normpath(str(rutaBase)) # Use normalized base path
    except Exception as e_base:
        log.error(f"{logPrefix} Failed to normalize base path '{rutaBase}': {e_base}")
        return False, f"Invalid base path: {rutaBase}"


    # --- Handle delete_file, create_directory ---
    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        targetRel = paramsOriginal.get("archivo") or paramsOriginal.get("directorio")
        if not targetRel:
            return False, f"Missing target parameter ('archivo' or 'directorio') for {accionOriginal}."

        targetAbs = _validar_y_normalizar_ruta(targetRel, rutaBaseNorm, asegurar_existencia=False)
        if targetAbs is None:
            # Validation failed, _validar_y_normalizar_ruta already logged error
            return False, f"Invalid or unsafe path provided for {accionOriginal}: '{targetRel}'"

        # --- Action Execution (Delete/Create) ---
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
                        err = f"Target '{targetRel}' exists but is not a file, link, or directory."
                        log.error(f"{logPrefix} {err}")
                        return False, err
                    return True, None # Deletion successful
                except Exception as e:
                    err = f"Error deleting '{targetRel}': {e}"
                    log.error(f"{logPrefix} {err}", exc_info=True)
                    return False, err
            else:
                log.warning(f"{logPrefix} Target '{targetRel}' not found for deletion. Considering successful.")
                return True, None # Target didn't exist, deletion is idempotent

        elif accionOriginal == "crear_directorio":
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Creating directory {targetRel} (Abs: {targetAbs})")
            if os.path.exists(targetAbs):
                if os.path.isdir(targetAbs):
                    log.warning(f"{logPrefix} Directory '{targetRel}' already exists.")
                    return True, None # Directory already exists, creation is idempotent
                else:
                    err = f"Path '{targetRel}' exists but is not a directory. Cannot create directory."
                    log.error(f"{logPrefix} {err}")
                    return False, err
            else:
                try:
                    os.makedirs(targetAbs, exist_ok=True) # exist_ok=True is generally safe
                    log.info(f"{logPrefix} Directory '{targetRel}' created.")
                    return True, None # Directory creation successful
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
        # This case is only valid if the action was delete/create (handled above).
        # If reached for other actions, it's an error.
        err = f"Expected content in 'archivos_con_contenido' for action '{accionOriginal}', but it's empty. Likely error in Step 2."
        log.error(f"{logPrefix} {err}")
        return False, err # Fail if content expected but not provided

    log.info(f"{logPrefix} Processing {len(archivos_con_contenido)} file(s) for writing/modification...")
    archivosProcesados = []
    errores = []

    # --- Main loop for writing files ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        # --- Path validation ---
        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Invalid or unsafe path ('{rutaRel}') received. File skipped."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue # Skip this file

        # --- String type validation/conversion ---
        if not isinstance(contenido_original_json, str):
             log.warning(f"{logPrefix} Content for '{rutaRel}' is not string (type {type(contenido_original_json)}). Converting to JSON string.")
             try:
                 # Convert non-string content to JSON string with indentation and ensure_ascii=False
                 contenido_str = json.dumps(contenido_original_json, indent=2, ensure_ascii=False)
             except Exception as e_conv:
                  log.error(f"{logPrefix} Could not convert non-string content to string for '{rutaRel}': {e_conv}. Skipping file.")
                  errores.append(f"Invalid non-string content for {rutaRel}")
                  continue # Skip this file
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
            continue # Skip this file

        # --- Start Correction Block (STRATEGY: ftfy FIRST, then Controlled Escapes) ---
        contenido_procesado = contenido_str
        log.debug(f"{logPrefix} Content ORIGINAL for '{rutaRel}' (repr): {repr(contenido_procesado[:200])}...")

        contenido_a_escribir = contenido_procesado # Start with the input string

        try:
            # --- STEP 1: Fix text using ftfy (Mojibake, etc.) ---
            try:
                log.debug(f"{logPrefix} Applying ftfy.fix_text for '{rutaRel}'...")
                # Use normalization='NFC' which is standard for text content
                contenido_fixed_ftfy = ftfy.fix_text(contenido_procesado, normalization='NFC')

                if contenido_fixed_ftfy != contenido_procesado:
                     log.info(f"{logPrefix} CORRECTION (ftfy): Text fixed using ftfy for '{rutaRel}'.")
                     contenido_a_escribir = contenido_fixed_ftfy # Update content
                else:
                     log.debug(f"{logPrefix} ftfy.fix_text resulted in no change for '{rutaRel}'.")
                log.debug(f"{logPrefix} Content AFTER ftfy for '{rutaRel}' (repr): {repr(contenido_a_escribir[:200])}...")

            except Exception as e_ftfy:
                 log.error(f"{logPrefix} Error applying ftfy.fix_text for '{rutaRel}': {e_ftfy}. Proceeding with original content for escape handling.", exc_info=True)
                 # Keep contenido_a_escribir as contenido_procesado if ftfy fails

            # --- STEP 2: Handle specific Python escapes (\n, \t, \\, \uXXXX) MANUALLY ---
            # Apply this AFTER ftfy has cleaned up Mojibake
            try:
                contenido_despues_manual_escapes = _reemplazar_escapes_controlado(contenido_a_escribir)

                if contenido_despues_manual_escapes != contenido_a_escribir:
                    # Detailed logs are inside _reemplazar_escapes_controlado
                    log.info(f"{logPrefix} CORRECTION (Manual Escapes): Replaced specific Python escapes AFTER ftfy for '{rutaRel}'.")
                    contenido_a_escribir = contenido_despues_manual_escapes # Update content
                # else: No need to log if no escapes were replaced

                log.debug(f"{logPrefix} Content AFTER Manual Escapes (post-ftfy) for '{rutaRel}' (repr): {repr(contenido_a_escribir[:200])}...")

            except Exception as e_manual_escape:
                log.error(f"{logPrefix} Error applying _reemplazar_escapes_controlado for '{rutaRel}': {e_manual_escape}. Proceeding with content after ftfy step.", exc_info=True)
                # Keep contenido_a_escribir as it was after the ftfy step if manual escapes fail


            # --- STEP 3: Final Diagnostics and Writing ---
            log.debug(f"{logPrefix} FINAL content to write for '{rutaRel}' (start, repr): {repr(contenido_a_escribir[:200])}")

            # Final check for remaining literal \uXXXX or simple escapes
            # (Could indicate intentional double-escapes or issues in manual replacement)
            if re.search(r'(?<!\\)\\u[0-9a-fA-F]{4}', contenido_a_escribir): # Look for \uXXXX not preceded by \
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain literal \\uXXXX escapes AFTER processing. Could be intended (e.g., '\\\\uXXXX' input) or issue in escape handling.")
            # Look for \n, \r, \t, \\ that are NOT preceded by another \
            # This helps distinguish between intended literal backslashes (like \\n) and unprocessed escapes.
            if re.search(r'(?<!\\)\\[nrt\\]', contenido_a_escribir):
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain literal simple escapes (\\n, \\t, \\r, \\\\) AFTER processing. Check input or escape handling.")


            # Write the final result in UTF-8
            log.debug(f"{logPrefix} Writing {len(contenido_a_escribir)} characters to {archivoAbs} using UTF-8")
            with open(archivoAbs, 'w', encoding='utf-8') as f:
                f.write(contenido_a_escribir)
            log.info(f"{logPrefix} File '{rutaRel}' written/overwritten successfully.")
            archivosProcesados.append(rutaRel) # Add to list of successful files

        except Exception as e_process_write:
             # Catch any unexpected errors during the processing/writing of this specific file
             msg = f"Error processing/writing file '{rutaRel}': {e_process_write}"
             log.error(f"{logPrefix} {msg}", exc_info=True)
             errores.append(msg) # Add error message to list
             # Continue with the next file in the loop

    # --- End of loop ---

    # --- Final Evaluation ---
    if errores:
        # If there were errors during processing individual files
        error_summary = f"Process completed with {len(errores)} error(s): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        # Return False even if some files were processed successfully
        return False, error_summary
    elif not archivosProcesados and isinstance(archivos_con_contenido, dict) and archivos_con_contenido:
         # Check if content was provided (and it was a non-empty dict) but *no* files were successfully processed
         msg = "Content was provided but no files could be processed successfully (check logs for per-file errors)."
         log.error(f"{logPrefix} {msg}")
         return False, msg # This is definitely a failure state
    # If no errors were recorded in the `errores` list AND
    # (either archivosProcesados has items OR archivos_con_contenido was empty/not dict initially and action was delete/create)
    # then consider the overall operation successful.
    log.info(f"{logPrefix} Processing finished. {len(archivosProcesados)} files written/modified successfully.")
    return True, None # Success