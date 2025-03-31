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
    # Use realpath on base to resolve any symlinks in the base path itself
    try:
        rutaBaseReal = os.path.realpath(rutaBase)
        if not os.path.isabs(rutaBaseReal):
             # This should ideally not happen if called correctly, but check anyway
             log.error(f"{logPrefix} Base path could not be resolved to absolute: '{rutaBase}' -> '{rutaBaseReal}'")
             return None
        if not os.path.isdir(rutaBaseReal):
             log.error(f"{logPrefix} Real base path is not a directory: '{rutaBaseReal}' (from '{rutaBase}')")
             return None
    except Exception as e_base:
         log.error(f"{logPrefix} Error resolving real path for base '{rutaBase}': {e_base}", exc_info=True)
         return None

    # Normalize relative path, disallowing '..' components or absolute paths
    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    if os.path.isabs(rutaRelativaNorm) or rutaRelativaNorm.split(os.sep)[0] == '..':
        # Check the first component specifically after normalization for '..'
        log.error(f"{logPrefix} Invalid or suspicious relative path (absolute or starts with '..'): '{rutaRelativa}' -> '{rutaRelativaNorm}'")
        return None

    # Join the REAL base path with the normalized relative path
    rutaAbsCandidata = os.path.join(rutaBaseReal, rutaRelativaNorm)
    # Normalize the combined path
    rutaAbsNorm = os.path.normpath(rutaAbsCandidata)

    # Security Check: Use realpath comparison for the final check
    try:
        rutaAbsReal = os.path.realpath(rutaAbsNorm)

        # The core check: common path must be the base path itself
        if os.path.commonpath([rutaBaseReal, rutaAbsReal]) == rutaBaseReal:
            # Path is safe
            if asegurar_existencia and not os.path.exists(rutaAbsReal):
                log.warning(f"{logPrefix} Path validated but does not exist (existence required): '{rutaAbsNorm}' (Real: '{rutaAbsReal}')")
                return None # Fail if existence was required

            log.debug(f"{logPrefix} Path validated and normalized to: '{rutaAbsNorm}'")
            # Return the normalized path (not realpath) to preserve intended structure
            return rutaAbsNorm
        else:
            log.error(f"{logPrefix} Path Traversal Attempt! Relative path '{rutaRelativa}' exits base '{rutaBaseReal}'. Result: '{rutaAbsNorm}', Real Result: '{rutaAbsReal}'")
            return None
    except Exception as e:
        log.error(f"{logPrefix} Error during path validation/realpath check for '{rutaRelativa}' in '{rutaBase}': {e}", exc_info=True)
        return None

# --- Mojibake common replacements (Robust Definition) ---
# Uses ignore errors for decode, as some UTF-8 bytes might not map cleanly to Latin-1 singular chars
MOJIBAKE_REPLACEMENTS = {
    b'\xc3\xa1'.decode('latin-1', errors='ignore'): "á", b'\xc3\xa9'.decode('latin-1', errors='ignore'): "é",
    b'\xc3\xad'.decode('latin-1', errors='ignore'): "í", b'\xc3\xb3'.decode('latin-1', errors='ignore'): "ó",
    b'\xc3\xba'.decode('latin-1', errors='ignore'): "ú", b'\xc3\xbc'.decode('latin-1', errors='ignore'): "ü",
    b'\xc3\x81'.decode('latin-1', errors='ignore'): "Á", b'\xc3\x89'.decode('latin-1', errors='ignore'): "É",
    b'\xc3\x8d'.decode('latin-1', errors='ignore'): "Í", b'\xc3\x93'.decode('latin-1', errors='ignore'): "Ó",
    b'\xc3\x9a'.decode('latin-1', errors='ignore'): "Ú", b'\xc3\x9c'.decode('latin-1', errors='ignore'): "Ü",
    b'\xc3\xb1'.decode('latin-1', errors='ignore'): "ñ", b'\xc3\x91'.decode('latin-1', errors='ignore'): "Ñ",
    b'\xc2\xa1'.decode('latin-1', errors='ignore'): "¡", b'\xc2\xbf'.decode('latin-1', errors='ignore'): "¿",
    b'\xc2\xaa'.decode('latin-1', errors='ignore'): "ª", b'\xc2\xba'.decode('latin-1', errors='ignore'): "º",
    b'\xc2\xab'.decode('latin-1', errors='ignore'): "«", b'\xc2\xbb'.decode('latin-1', errors='ignore'): "»",
    b'\xe2\x82\xac'.decode('latin-1', errors='ignore'): "€", b'\xe2\x84\xa2'.decode('latin-1', errors='ignore'): "™",
    b'\xe2\x80\x99'.decode('latin-1', errors='ignore'): "’", b'\xe2\x80\x98'.decode('latin-1', errors='ignore'): "‘",
    b'\xe2\x80\x9c'.decode('latin-1', errors='ignore'): "“", b'\xe2\x80\x9d'.decode('latin-1', errors='ignore'): "”",
    b'\xe2\x80\xa6'.decode('latin-1', errors='ignore'): "…", b'\xe2\x80\x93'.decode('latin-1', errors='ignore'): "–",
    b'\xe2\x80\x94'.decode('latin-1', errors='ignore'): "—",
}

# --- Function to decode \uXXXX escapes manually ---
def decode_unicode_escapes(s):
    def replace_match(match):
        try:
            hex_code = match.group(1)
            char_code = int(hex_code, 16)
            # Handle potential surrogate pairs if needed (basic chr() handles BMP)
            # For simplicity, assume BMP for now. Real-world might need surrogate handling.
            return chr(char_code)
        except ValueError:
            log.warning(f"Invalid unicode escape sequence found: {match.group(0)}")
            return match.group(0) # Return original if conversion fails

    # Regex to find \u followed by exactly 4 hex digits.
    # Use negative lookbehind to avoid matching an already escaped backslash (\\uXXXX)
    pattern = r'(?<!\\)\\u([0-9a-fA-F]{4})'
    processed_string, num_replacements = re.subn(pattern, replace_match, s)
    if num_replacements > 0:
         log.debug(f"decode_unicode_escapes: Replaced {num_replacements} sequences.")
    return processed_string


# --- FUNCIÓN PRINCIPAL (Estrategia: Targeted Replace Mojibake -> Manual Escapes -> Manual Unicode Decode) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    """
    Applies changes generated by Gemini.
    - FIRST replaces common Mojibake sequences using a predefined map.
    - SECOND replaces basic escapes (\\n, \\t, \\\\).
    - THIRD decodes \\uXXXX sequences manually (ignoring \\\\uXXXX).
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
                    os.makedirs(targetAbs, exist_ok=True)
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
             err = f"Expected content in 'archivos_con_contenido' for action '{accionOriginal}', but it's empty."
             log.error(f"{logPrefix} {err}")
             return False, err
        else:
            log.info(f"{logPrefix} No content provided, expected for action '{accionOriginal}'.")
            return True, None

    log.info(f"{logPrefix} Processing {len(archivos_con_contenido)} file(s) for writing/modification...")
    archivosProcesados = []
    errores = []

    # --- Main loop for writing files ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        # --- Path validation and parent directory creation ---
        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Invalid or unsafe path ('{rutaRel}'). File skipped."
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
                 raise ValueError(f"Parent path '{dirPadre}' exists but is NOT a directory.")
        except Exception as e_dir:
            msg = f"Error managing parent directory '{dirPadre}' for '{rutaRel}': {e_dir}. Skipping."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue

        # --- Start Correction Block ---
        contenido_procesado = contenido_str
        log.debug(f"{logPrefix} Content ORIGINAL for '{rutaRel}' (repr): {repr(contenido_procesado[:200])}...")

        try:
            # --- STEP 1: Replace common Mojibake sequences ---
            contenido_despues_mojibake = contenido_procesado
            replacements_made_moji = False
            temp_contenido_moji = contenido_procesado
            for mojibake, correct in MOJIBAKE_REPLACEMENTS.items():
                # Check if the key exists before replacing to avoid unnecessary work
                if mojibake in temp_contenido_moji:
                    new_temp_contenido = temp_contenido_moji.replace(mojibake, correct)
                    if new_temp_contenido != temp_contenido_moji: # Check if replace actually did something
                        if not replacements_made_moji:
                            log.info(f"{logPrefix} CORRECTION (Mojibake Replace): Common Mojibake sequence(s) being replaced for '{rutaRel}'.")
                        log.debug(f"{logPrefix}   Replaced Mojibake: {repr(mojibake)} -> {repr(correct)}")
                        replacements_made_moji = True
                        temp_contenido_moji = new_temp_contenido # Update for next iteration

            if replacements_made_moji:
                contenido_despues_mojibake = temp_contenido_moji
            else:
                 log.debug(f"{logPrefix} No common Mojibake sequences found/replaced for '{rutaRel}'.")

            log.debug(f"{logPrefix} Content AFTER Mojibake Replace for '{rutaRel}' (repr): {repr(contenido_despues_mojibake[:200])}...")

            # --- STEP 2: Replace basic escapes manually (handle \\ first) ---
            contenido_despues_basic_escapes = contenido_despues_mojibake
            # Use a placeholder unlikely to appear naturally or be created by unicode escapes
            placeholder = "\uFFFE" # Typically invalid unicode char, good placeholder
            # Check if any basic escapes are present before doing replacements
            if '\\\\' in contenido_despues_mojibake or '\\n' in contenido_despues_mojibake or \
               '\\t' in contenido_despues_mojibake or '\\r' in contenido_despues_mojibake:

                log.info(f"{logPrefix} CORRECTION (Basic Escapes): Basic escapes (\\n, \\t, \\\\ etc.) processing for '{rutaRel}'.")
                temp_contenido_basic = contenido_despues_mojibake.replace('\\\\', placeholder)
                temp_contenido_basic = temp_contenido_basic.replace('\\n', '\n')
                temp_contenido_basic = temp_contenido_basic.replace('\\t', '\t')
                temp_contenido_basic = temp_contenido_basic.replace('\\r', '\r')
                # Add others like \\" if they might appear and aren't handled by JSON loader
                # temp_contenido_basic = temp_contenido_basic.replace('\\"', '"')

                # Restore the literal backslash
                contenido_despues_basic_escapes = temp_contenido_basic.replace(placeholder, '\\')
            else:
                 log.debug(f"{logPrefix} No basic escapes ('\\\\', '\\n', etc.) found, skipping replacement.")


            log.debug(f"{logPrefix} Content AFTER Basic Escapes for '{rutaRel}' (repr): {repr(contenido_despues_basic_escapes[:200])}...")

            # --- STEP 3: Decode \uXXXX sequences manually ---
            contenido_despues_unicode = contenido_despues_basic_escapes
            # Check specifically for the pattern we want to decode: non-escaped \uXXXX
            if re.search(r'(?<!\\)\\u[0-9a-fA-F]{4}', contenido_despues_basic_escapes):
                log.info(f"{logPrefix} CORRECTION (Unicode Decode): \\uXXXX sequences found, applying manual decoding for '{rutaRel}'.")
                decoded_unicode_str = decode_unicode_escapes(contenido_despues_basic_escapes)
                if decoded_unicode_str != contenido_despues_basic_escapes:
                    # This check might be redundant if re.search found something, but safe
                    contenido_despues_unicode = decoded_unicode_str
                else:
                    # This case might happen if decode_unicode_escapes handles errors by returning original
                    log.debug(f"{logPrefix} Manual unicode decode ran but no effective changes detected (check decode_unicode_escapes function or specific sequences).")
            else:
                 log.debug(f"{logPrefix} No unescaped '\\uXXXX' sequences found, skipping manual unicode decode for '{rutaRel}'.")

            contenido_a_escribir = contenido_despues_unicode
            log.debug(f"{logPrefix} Content FINAL after all processing for '{rutaRel}' (repr): {repr(contenido_a_escribir[:200])}...")

            # --- Final Diagnostics and Writing ---
            remaining_mojibake_keys = [k for k in MOJIBAKE_REPLACEMENTS.keys() if k in contenido_a_escribir]
            if remaining_mojibake_keys:
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain known Mojibake patterns AFTER processing (e.g., {remaining_mojibake_keys[:3]}).")
            # Check for remaining literal \u escapes that were *not* preceded by a backslash
            if re.search(r'(?<!\\)\\u[0-9a-fA-F]{4}', contenido_a_escribir):
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain unescaped literal \\uXXXX sequences AFTER processing. This indicates a failure in the decode_unicode_escapes step.")


            log.debug(f"{logPrefix} Writing {len(contenido_a_escribir)} characters to {archivoAbs} using UTF-8")
            with open(archivoAbs, 'w', encoding='utf-8') as f:
                f.write(contenido_a_escribir)
            log.info(f"{logPrefix} File '{rutaRel}' written/overwritten successfully.")
            archivosProcesados.append(rutaRel)

        except Exception as e_process_write:
             msg = f"Error processing/writing file '{rutaRel}': {e_process_write}"
             log.error(f"{logPrefix} {msg}", exc_info=True)
             errores.append(msg)

    # --- End of loop ---
    # --- Final Evaluation ---
    if errores:
        error_summary = f"Process completed with {len(errores)} error(s): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary
    elif not archivosProcesados and archivos_con_contenido:
         msg = "Content provided but no files could be processed due to errors."
         log.error(f"{logPrefix} {msg}")
         return False, msg
    log.info(f"{logPrefix} Processing finished. {len(archivosProcesados)} files written/modified successfully.")
    return True, None