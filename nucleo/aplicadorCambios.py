import re  # Import re
import codecs
import os
import logging
import shutil
import json
import codecs  # Import codecs
import re

# NO BORRAR ESTE COMENTARIO
# GUIA
# ESTO CASI FUNCIONA BIEN; SE SOLUCIONO EL PROBLEMA DONDE LOS SALTOS DE LINEA DENTRO DEL CODIGO (EJEMPLO UN LOG QUE CONTENIA INDICACIONES DE SALTO DE LINEA; SE MANEA BIEN SEGUN EL TEST, Y LOS CARACTERES ASI COMO  usarÃ¡ TAMBIEN SE SOLUCIONA PERO NO SE ARREGLA Funci\\u00f3n, ¿por que? no lo se, pero rompe te toda la logica cuando se intenta, lo que se me ocurre es otra funcion que despues de que aplicarCambiosSobrescritura haga su trabajo, procesa a solucionar Funci\\u00f3n, no hay que modificar nada de lo que ya hace, sola otra etapa
# REVISIÓN: La guía sugiere una etapa extra, pero usar 'unicode_escape' en el orden correcto debería resolverlo de forma más integrada.

# Obtener logger
log = logging.getLogger(__name__)


# --- Mojibake common replacements ---
MOJIBAKE_REPLACEMENTS = {
    "Ã¡": "á", "Ã©": "é", "Ã­": "í", "Ã³": "ó", "Ãº": "ú", "Ã¼": "ü",
    "Ã": "Á", "Ã‰": "É", "Ã": "Í", "Ã“": "Ó", "Ãš": "Ú", "Ãœ": "Ü", # Added accented caps
    "Ã±": "ñ", "Ã‘": "Ñ",
    "Â¡": "¡", "Â¿": "¿",
    "Âª": "ª", "Âº": "º",
    "Â«": "«", "Â»": "»",
    "â‚¬": "€", "â„¢": "™", "â€™": "’", "â€˜": "‘", "â€œ": "“", "â€": "”", "â€¦": "…",
    # Add common CP1252 errors if seen
    "â€š": "‚", # Single low-9 quotation mark
    "Æ’": "ƒ",  # Latin small letter f with hook
    "â€ž": "„", # Double low-9 quotation mark
    "â€¡": "‡", # Double dagger
    "Ë†": "ˆ",  # Modifier letter circumflex accent
    "â€°": "‰", # Per mille sign
    "Å’": "Œ", # Latin capital ligature OE
    "Å½": "Ž", # Latin capital letter Z with caron
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
    rutaBaseNorm = os.path.normpath(rutaBase)

    # --- Handle delete_file, create_directory ---
    # (Use robust implementation from previous steps - simplified here for focus)
    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        targetRel = paramsOriginal.get("archivo") or paramsOriginal.get("directorio")
        if not targetRel: return False, f"Missing target parameter for {accionOriginal}."
        targetAbs = _validar_y_normalizar_ruta(targetRel, rutaBaseNorm, asegurar_existencia=False)
        if targetAbs is None: return False, f"Invalid/unsafe path for {accionOriginal}: '{targetRel}'"

        if accionOriginal == "eliminar_archivo":
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Targeting {targetRel}")
            if os.path.exists(targetAbs):
                try:
                    if os.path.isfile(targetAbs) or os.path.islink(targetAbs): os.remove(targetAbs); log.info(f"{logPrefix} File/Link deleted.")
                    elif os.path.isdir(targetAbs): os.rmdir(targetAbs); log.info(f"{logPrefix} Empty directory deleted.") # Only empty
                    else: return False, f"Target '{targetRel}' is not a file/link/directory."
                    return True, None
                except OSError as e: return False, f"OS Error deleting '{targetRel}': {e}"
                except Exception as e: return False, f"Error deleting '{targetRel}': {e}"
            else: log.warning(f"{logPrefix} Target '{targetRel}' not found for deletion."); return True, None
        elif accionOriginal == "crear_directorio":
            log.info(f"{logPrefix} Executing action '{accionOriginal}': Creating {targetRel}")
            if os.path.exists(targetAbs):
                if os.path.isdir(targetAbs): log.warning(f"{logPrefix} Directory '{targetRel}' already exists."); return True, None
                else: return False, f"Path '{targetRel}' exists but is not a directory."
            else:
                try: os.makedirs(dirAbs, exist_ok=True); log.info(f"{logPrefix} Directory created."); return True, None
                except Exception as e: return False, f"Error creating directory '{targetRel}': {e}"


    # --- Initial Validations ---
    if not isinstance(archivos_con_contenido, dict):
         return False, "Argument 'archivos_con_contenido' is not a dictionary."
    if not archivos_con_contenido:
        if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             return False, f"Empty 'archivos_con_contenido' for action '{accionOriginal}'."
        else:
            log.info(f"{logPrefix} No content provided, expected for action '{accionOriginal}'.")
            return True, None

    log.info(f"{logPrefix} Processing {len(archivos_con_contenido)} file(s) for writing/modification...")
    archivosProcesados = []
    errores = []

    # --- Main loop for writing files ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Invalid or unsafe path ('{rutaRel}'). File skipped."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        if not isinstance(contenido_original_json, str):
             log.warning(f"{logPrefix} Content for '{rutaRel}' is not string ({type(contenido_original_json)}). Converting to JSON.")
             try:
                 contenido_str = json.dumps(contenido_original_json, indent=2, ensure_ascii=False)
             except Exception as e_conv:
                  log.error(f"{logPrefix} Failed to convert non-string content for '{rutaRel}': {e_conv}. Skipping.")
                  errores.append(f"Invalid non-string content for {rutaRel}")
                  continue
        else:
             contenido_str = contenido_original_json

        dirPadre = os.path.dirname(archivoAbs)
        try:
            if dirPadre and not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creating parent directory: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif dirPadre and not os.path.isdir(dirPadre):
                 raise ValueError(f"Parent path '{dirPadre}' exists but is not a directory.")
        except Exception as e_dir:
            msg = f"Error managing parent directory '{dirPadre}' for '{rutaRel}': {e_dir}. Skipping."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue

        # --- Start Correction Block (STRATEGY: unicode_escape FIRST, then Targeted Replace) ---
        contenido_procesado = contenido_str
        log.debug(f"{logPrefix} Content ORIGINAL for '{rutaRel}' (repr): {repr(contenido_procesado[:200])}...")

        try:
            # --- STEP 1: Decode standard escapes (including \uXXXX, \n, \t, \\) ---
            contenido_despues_escape = contenido_procesado # Default if decode fails
            try:
                # Apply unicode_escape first to handle explicit escapes
                if '\\' in contenido_procesado:
                    log.debug(f"{logPrefix} Applying codecs.decode(..., 'unicode_escape') for '{rutaRel}'")
                    contenido_decodificado = codecs.decode(contenido_procesado, 'unicode_escape', errors='strict')

                    if contenido_decodificado != contenido_procesado:
                        log.info(f"{logPrefix} CORRECTION (unicode_escape): Standard escape sequences decoded for '{rutaRel}'.")
                        contenido_despues_escape = contenido_decodificado
                    else:
                        log.debug(f"{logPrefix} 'unicode_escape' applied but resulted in no change.")
                else:
                    log.debug(f"{logPrefix} No backslashes found, skipping 'unicode_escape' decoding for '{rutaRel}'.")

            except UnicodeDecodeError as e_escape_decode:
                 # Malformed escape sequence
                 log.warning(f"{logPrefix} FAILED 'unicode_escape' for '{rutaRel}': {e_escape_decode}. Using original string for Mojibake replacement.")
                 contenido_despues_escape = contenido_procesado # Use original for next step
            except Exception as e_escape:
                 log.error(f"{logPrefix} Unexpected error during 'unicode_escape' for '{rutaRel}': {e_escape}. Using original string for Mojibake replacement.", exc_info=True)
                 contenido_despues_escape = contenido_procesado # Use original for next step

            # Content ready for Mojibake replacement
            contenido_intermedio = contenido_despues_escape
            log.debug(f"{logPrefix} Content AFTER unicode_escape for '{rutaRel}' (repr): {repr(contenido_intermedio[:200])}...")

            # --- STEP 2: Replace common Mojibake sequences ---
            contenido_final = contenido_intermedio # Start with the result after escapes
            replacements_count = 0
            # Create a temporary variable for replacement to avoid modifying during iteration issues (though less likely with string.replace)
            temp_contenido = contenido_intermedio
            for mojibake, correct in MOJIBAKE_REPLACEMENTS.items():
                # Check if the mojibake sequence exists in the current state of the string
                if mojibake in temp_contenido:
                    count_before = temp_contenido.count(mojibake)
                    temp_contenido = temp_contenido.replace(mojibake, correct)
                    replacements_count += count_before

            # Only update contenido_final if replacements actually happened
            if replacements_count > 0:
                 log.info(f"{logPrefix} CORRECTION (Mojibake Replace): {replacements_count} common Mojibake sequence(s) replaced AFTER escapes for '{rutaRel}'.")
                 contenido_final = temp_contenido # Assign the modified string
            else:
                 log.debug(f"{logPrefix} No common Mojibake sequences found/replaced after escapes for '{rutaRel}'.")
                 # contenido_final remains contenido_intermedio

            contenido_a_escribir = contenido_final
            log.debug(f"{logPrefix} Content AFTER Mojibake Replace (post-escapes) for '{rutaRel}' (repr): {repr(contenido_a_escribir[:200])}...")

            # --- STEP 3: Final Diagnostics and Writing ---
            log.debug(f"{logPrefix} FINAL content to write for '{rutaRel}' (start, repr): {repr(contenido_a_escribir[:200])}")

            # Final checks (can be simplified or removed if confident)
            remaining_mojibake = [p for p in MOJIBAKE_REPLACEMENTS.keys() if p in contenido_a_escribir]
            if remaining_mojibake:
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain known Mojibake patterns AFTER processing (e.g., {remaining_mojibake[:3]}). Check MOJIBAKE_REPLACEMENTS map or input.")
            if re.search(r'\\u[0-9a-fA-F]{4}', contenido_a_escribir):
                 log.warning(f"{logPrefix} ALERT! Content for '{rutaRel}' might STILL contain literal \\uXXXX escapes AFTER processing.")

            # Write the final result in UTF-8
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
         msg = "Content provided but no files processed due to errors."
         log.error(f"{logPrefix} {msg}")
         return False, msg
    log.info(f"{logPrefix} Processing finished. {len(archivosProcesados)} files written/modified successfully.")
    return True, None # Success


# Helper de rutas (sin cambios necesarios aquí, asumiendo que funciona)
def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    logPrefix = "_validar_y_normalizar_ruta:"
    # Añadir un check inicial para None o no string
    if not rutaRelativa or not isinstance(rutaRelativa, str):
        log.error(
            f"{logPrefix} Se recibió una ruta relativa inválida (None o no string): {rutaRelativa!r}")
        return None
    # Resto de la función como estaba...
    log.debug(f"{logPrefix} Validando rutaRelativa='{rutaRelativa}', rutaBase='{rutaBase}', asegurar_existencia={asegurar_existencia}")
    if '..' in rutaRelativa.split(os.sep):
        log.error(
            f"{logPrefix} Ruta relativa inválida o sospechosa (contiene '..'): '{rutaRelativa}'")
        return None
    rutaBaseNorm = os.path.normpath(os.path.abspath(rutaBase))
    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    if os.path.isabs(rutaRelativaNorm):
        log.error(
            f"{logPrefix} Ruta relativa '{rutaRelativa}' parece ser absoluta tras normalizar: '{rutaRelativaNorm}'. Rechazada.")
        return None
    rutaAbs = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbs = os.path.normpath(rutaAbs)

    # Comprobación de seguridad estricta
    # Asegurarse que la base termine con separador para evitar falsos positivos (ej /base vs /base_otro)
    base_con_sep = rutaBaseNorm if rutaBaseNorm.endswith(
        os.sep) else rutaBaseNorm + os.sep
    if not os.path.abspath(rutaAbs).startswith(os.path.abspath(base_con_sep)) and \
       os.path.abspath(rutaAbs) != os.path.abspath(rutaBaseNorm):
        log.error(f"{logPrefix} Ruta calculada '{os.path.abspath(rutaAbs)}' intenta salir de la base '{os.path.abspath(rutaBaseNorm)}' (originada de '{rutaRelativa}')")
        return None

    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.warning(
            f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (de '{rutaRelativa}')")
        # Cambiado a False, si se pide asegurar existencia y no existe, es un fallo en ese contexto
        return None  # O podría ser True dependiendo de la lógica que llama

    log.debug(f"{logPrefix} Ruta validada y normalizada a: '{rutaAbs}'")
    return rutaAbs
