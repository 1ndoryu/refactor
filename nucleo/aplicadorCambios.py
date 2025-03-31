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
# ... (código existente sin cambios) ...
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
        # Resolve potential symlinks in base path ONCE for validation
        # Check if base exists and is a directory before realpath if needed
        if not os.path.isdir(rutaBaseNorm):
             # This check might be too strict if base is created later, but good for validation
             log.warning(f"{logPrefix} Base path does not exist or is not a directory during validation: '{rutaBaseNorm}'")
             # Depending on strictness, you might allow this or return None.
             # For now, let's assume base should generally exist for validation.
             # If creation is expected, defer this check or handle os.makedirs errors later.
             # Let's proceed but be aware.
             rutaBaseReal = rutaBaseNorm # Use normalized if realpath fails or dir doesnt exist
        else:
             rutaBaseReal = os.path.realpath(rutaBaseNorm)
             if not os.path.isdir(rutaBaseReal): # Double check after realpath
                log.error(f"{logPrefix} Real base path resolved to something not a directory: '{rutaBaseReal}' (from '{rutaBase}')")
                return None

        # Use realpath on the candidate path *without* checking existence yet,
        # as the file might not exist but the path could still be validly constructed.
        # os.path.realpath will resolve symlinks in existing parts of the path.
        rutaAbsRealCandidata = os.path.realpath(rutaAbsNorm)

        # The core check: common path must be the base path itself
        # This handles cases where base is '/a/b' and candidate is '/a/b/c' or '/a/b'
        # Check against the resolved real base path
        if os.path.commonpath([rutaBaseReal, rutaAbsRealCandidata]).rstrip(os.sep) == rutaBaseReal.rstrip(os.sep):
            # Path is safe
            if asegurar_existencia:
                # If existence is required, perform the final check AFTER validation
                # Using the *non-realpath* version for the check might be intended
                # unless you specifically need to follow symlinks for the final file.
                if not os.path.exists(rutaAbsNorm):
                    log.warning(f"{logPrefix} Path validated but does not exist (existence required): '{rutaAbsNorm}'")
                    return None # Fail if existence was required

            log.debug(f"{logPrefix} Path validated and normalized to: '{rutaAbsNorm}'")
            # Return the normalized path (not realpath) to preserve intended structure
            return rutaAbsNorm
        else:
            log.error(f"{logPrefix} Path Traversal Attempt! Relative path '{rutaRelativa}' exits base '{rutaBaseNorm}'. Result: '{rutaAbsNorm}', Real Candidate: '{rutaAbsRealCandidata}', Real Base: '{rutaBaseReal}'")
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
    # --- Added based on test_05 failure analysis ---
    # Sequence observed AFTER unicode_escape incorrectly modified Ã¡: Ã<0x83>Â¡
    # We should NOT need this if we fix the Mojibake FIRST.
    # Let's keep the dictionary focused on the common UTF8->Latin1->UTF8 Mojibake.
    # If new Mojibake patterns appear, add them based on their *original* misinterpretation.
    # Example: If Windows-1252 interpreted as UTF-8 caused issues, add those mappings.
}

# --- FUNCIÓN PRINCIPAL (NUEVA ESTRATEGIA: Mojibake FIRST, then unicode_escape) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    """
    Applies changes generated by Gemini.
    - FIRST replaces common Mojibake sequences using a predefined map.
    - THEN decodes standard escape sequences (\\n, \\t, \\uXXXX, \\\\) using 'unicode_escape'.
    - Writes files in UTF-8. Handles delete/create actions.
    """
    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Applying changes for original action '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase) # Use normalized base path

    # --- Handle delete_file, create_directory ---
    # ... (código existente sin cambios) ...
    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        targetRel = paramsOriginal.get("archivo") or paramsOriginal.get("directorio")
        if not targetRel:
            return False, f"Missing target parameter ('archivo' or 'directorio') for {accionOriginal}."
        # Ensure we use the *base* directory for validation, not the target itself yet
        targetAbs = _validar_y_normalizar_ruta(targetRel, rutaBaseNorm, asegurar_existencia=False)
        if targetAbs is None:
            return False, f"Invalid or unsafe path provided for {accionOriginal}: '{targetRel}'"

        if accionOriginal == "eliminar_archivo":
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Targeting {targetRel} (Abs: {targetAbs})")
            # Use targetAbs which is now validated and absolute
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
                    # Use targetAbs here for creation
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
        if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             err = f"Expected content in 'archivos_con_contenido' for action '{accionOriginal}', but it's empty. Likely error in Step 2."
             log.error(f"{logPrefix} {err}")
             return False, err
        else:
            log.info(f"{logPrefix} No content in 'archivos_con_contenido', which is expected for action '{accionOriginal}'.")
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
            if dirPadre and not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creating necessary parent directory: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif dirPadre and not os.path.isdir(dirPadre):
                 raise ValueError(f"Parent path '{dirPadre}' for file '{rutaRel}' exists but is NOT a directory.")
        except Exception as e_dir:
            msg = f"Error creating/validating parent directory '{dirPadre}' for '{rutaRel}': {e_dir}. File skipped."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue

        # --- Start Correction Block (NEW STRATEGY: Mojibake FIRST, then unicode_escape) ---
        contenido_procesado = contenido_str
        log.debug(f"{logPrefix} Content ORIGINAL for '{rutaRel}' (repr): {repr(contenido_procesado[:200])}...")

        try:
            # --- STEP 1: Replace common Mojibake sequences FIRST ---
            contenido_despues_mojibake = contenido_procesado # Start with original string
            replacements_made = False # Flag to track if any change happened
            temp_contenido = contenido_procesado

            for mojibake, correct in MOJIBAKE_REPLACEMENTS.items():
                new_temp_contenido = temp_contenido.replace(mojibake, correct)
                if new_temp_contenido != temp_contenido:
                    if not replacements_made:
                        log.info(f"{logPrefix} CORRECTION (Mojibake Replace): Common Mojibake sequence(s) being replaced FIRST for '{rutaRel}'.")
                    log.debug(f"{logPrefix}   Replaced: {repr(mojibake)} -> {repr(correct)}")
                    replacements_made = True
                    temp_contenido = new_temp_contenido # Update string for next replacement

            if replacements_made:
                 contenido_despues_mojibake = temp_contenido
            else:
                 log.debug(f"{logPrefix} No common Mojibake sequences found/replaced in the original content for '{rutaRel}'.")

            log.debug(f"{logPrefix} Content AFTER Mojibake Replace for '{rutaRel}' (repr): {repr(contenido_despues_mojibake[:200])}...")

            # --- STEP 2: Decode standard escapes (including \uXXXX, \n, \t, \\) ---
            contenido_final = contenido_despues_mojibake # Default if decode fails or no escapes
            try:
                # Apply unicode_escape AFTER Mojibake fix, only if backslash present
                if '\\' in contenido_despues_mojibake:
                    log.debug(f"{logPrefix} Applying codecs.decode(..., 'unicode_escape') AFTER Mojibake fix for '{rutaRel}'")
                    # Use errors='strict' to catch malformed escapes like trailing backslash or \u123
                    contenido_decodificado = codecs.decode(contenido_despues_mojibake, 'unicode_escape', errors='strict')

                    if contenido_decodificado != contenido_despues_mojibake:
                        log.info(f"{logPrefix} CORRECTION (unicode_escape): Standard escape sequences decoded AFTER Mojibake fix for '{rutaRel}'.")
                        contenido_final = contenido_decodificado
                    else:
                        log.debug(f"{logPrefix} 'unicode_escape' applied after Mojibake fix but resulted in no further change.")
                else:
                    log.debug(f"{logPrefix} No backslashes found after Mojibake fix, skipping 'unicode_escape' decoding for '{rutaRel}'.")

            except UnicodeDecodeError as e_escape_decode:
                 # Malformed escape sequence (e.g., "\z", "\u12", trailing "\")
                 log.warning(f"{logPrefix} FAILED 'unicode_escape' AFTER Mojibake fix for '{rutaRel}': {e_escape_decode}. Malformed escape sequence likely present. Using string *before* escape attempt.")
                 contenido_final = contenido_despues_mojibake # Use the content *after Mojibake* but *before* the failed escape attempt
            except Exception as e_escape:
                 log.error(f"{logPrefix} Unexpected error during 'unicode_escape' AFTER Mojibake fix for '{rutaRel}': {e_escape}. Using string *before* escape attempt.", exc_info=True)
                 contenido_final = contenido_despues_mojibake # Use the content *after Mojibake* but *before* the failed escape attempt

            # Content ready for writing
            contenido_a_escribir = contenido_final
            log.debug(f"{logPrefix} Content AFTER unicode_escape (post-Mojibake) for '{rutaRel}' (repr): {repr(contenido_a_escribir[:200])}...")


            # --- STEP 3: Final Diagnostics and Writing ---
            log.debug(f"{logPrefix} FINAL content to write for '{rutaRel}' (start, repr): {repr(contenido_a_escribir[:200])}")

            # Final check for remaining Mojibake (indicates uncommon Mojibake not in map OR failure in Step 1)
            remaining_mojibake_keys = [k for k in MOJIBAKE_REPLACEMENTS.keys() if k in contenido_a_escribir]
            if remaining_mojibake_keys:
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain known Mojibake patterns AFTER processing (e.g., {remaining_mojibake_keys[:3]}). Check MOJIBAKE_REPLACEMENTS map or input data.")

            # Final check for remaining literal \uXXXX escapes (indicates issue or intentional double-escape \\uXXXX)
            # This check is now more meaningful as unicode_escape ran last (if needed)
            if re.search(r'\\u[0-9a-fA-F]{4}', contenido_a_escribir):
                 # Example: If input was "\\u1234", Mojibake wouldn't touch it, unicode_escape would turn it into "\u1234".
                 # This warning helps identify such cases.
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain literal \\uXXXX escapes AFTER processing. This could be intended if input was e.g., '\\\\uXXXX', or indicate an issue if not intended.")

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
         # Check if action was delete/create, which might not need content processing
         if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             return False, msg
         else: # If delete/create succeeded earlier, this state might be okay
             log.warning(f"{logPrefix} No content processed, but original action was '{accionOriginal}' which might have succeeded earlier.")
             # Consider returning True if the original action logic passed, but this indicates potential confusion
             # Let's stick to returning False if content was expected but failed, regardless of action type.
             # Adjust if delete/create success should override content processing failure.
             # For now, if content dict was non-empty but nothing processed -> likely indicates failure even if delete/create was the *intended* action name
             return False, msg # Treat as error if content was given but not processed


    # No errors, or only errors were handled (like file not found on delete)
    log.info(f"{logPrefix} Processing finished. {len(archivosProcesados)} files written/modified successfully.")
    return True, None # Success