import os
import logging
import shutil
import json
import codecs # Import codecs

# NO BORRAR ESTE COMENTARIO
# GUIA
# ESTO CASI FUNCIONA BIEN; SE SOLUCIONO EL PROBLEMA DONDE LOS SALTOS DE LINEA DENTRO DEL CODIGO (EJEMPLO UN LOG QUE CONTENIA INDICACIONES DE SALTO DE LINEA; SE MANEA BIEN SEGUN EL TEST, Y LOS CARACTERES ASI COMO  usarÃ¡ TAMBIEN SE SOLUCIONA PERO NO SE ARREGLA Funci\\u00f3n, ¿por que? no lo se, pero rompe te toda la logica cuando se intenta, lo que se me ocurre es otra funcion que despues de que aplicarCambiosSobrescritura haga su trabajo, procesa a solucionar Funci\\u00f3n, no hay que modificar nada de lo que ya hace, sola otra etapa
# REVISIÓN: La guía sugiere una etapa extra, pero usar 'unicode_escape' en el orden correcto debería resolverlo de forma más integrada.

# Obtener logger
log = logging.getLogger(__name__)


# --- FUNCIÓN PRINCIPAL CON ESTRATEGIA REVISADA (Mojibake -> unicode_escape) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    """
    Aplica los cambios generados por Gemini.
    - Sobrescribe archivos existentes o crea nuevos con el contenido proporcionado.
    - Maneja acciones como eliminar_archivo y crear_directorio.
    - PRIMERO intenta corregir Mojibake común (UTF-8 mal leído como Latin-1).
    - LUEGO decodifica secuencias de escape estándar (\\n, \\t, \\uXXXX, \\\\) usando 'unicode_escape'.
    - Escribe archivos en UTF-8.

    Args:
        archivos_con_contenido (dict): Diccionario {ruta_relativa: contenido_string}.
        rutaBase (str): Ruta base absoluta del repositorio clonado.
        accionOriginal (str): La acción decidida por Gemini (ej: 'modificar_codigo_en_archivo').
        paramsOriginal (dict): Los parámetros asociados a la acción original.

    Returns:
        tuple[bool, str | None]: (True, None) en éxito, (False, mensaje_error) en fallo.
    """
    logPrefix = "aplicarCambiosSobrescritura:"
    log.info(f"{logPrefix} Aplicando cambios para acción original '{accionOriginal}'...")
    rutaBaseNorm = os.path.normpath(rutaBase)

    # --- Manejo de eliminar_archivo, crear_directorio (sin cambios) ---
    if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
        # ... (código sin cambios para eliminar/crear) ...
        if accionOriginal == "eliminar_archivo":
            archivoRel = paramsOriginal.get("archivo")
            if not archivoRel: return False, "Falta 'archivo' en parámetros para eliminar_archivo."
            # Normalizar ruta relativa antes de validar
            archivoRelNorm = os.path.normpath(archivoRel)
            archivoAbs = _validar_y_normalizar_ruta(archivoRelNorm, rutaBaseNorm, asegurar_existencia=False)
            if archivoAbs is None: return False, f"Ruta inválida o insegura para eliminar: '{archivoRelNorm}'"
            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Eliminando {archivoRelNorm}")
            if os.path.exists(archivoAbs):
                if os.path.isfile(archivoAbs):
                    try: os.remove(archivoAbs); log.info(f"{logPrefix} Archivo '{archivoRelNorm}' eliminado."); return True, None
                    except Exception as e: err = f"Error al eliminar archivo '{archivoRelNorm}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
                elif os.path.isdir(archivoAbs): # Permitir eliminar directorios vacíos si se especifica un dir? Por ahora no.
                    try: os.rmdir(archivoAbs); log.info(f"{logPrefix} Directorio vacío '{archivoRelNorm}' eliminado."); return True, None
                    except OSError as e: err = f"Error al eliminar directorio '{archivoRelNorm}' (¿no está vacío?): {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
                    except Exception as e: err = f"Error inesperado al eliminar directorio '{archivoRelNorm}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
                else: err = f"Ruta a eliminar '{archivoRelNorm}' existe pero NO es un archivo o directorio estándar."; log.error(f"{logPrefix} {err}"); return False, err
            else: log.warning(f"{logPrefix} Elemento a eliminar '{archivoRelNorm}' no encontrado. Se considera éxito."); return True, None
        elif accionOriginal == "crear_directorio":
            dirRel = paramsOriginal.get("directorio")
            if not dirRel: return False, "Falta 'directorio' en parámetros para crear_directorio."
            # Normalizar ruta relativa antes de validar
            dirRelNorm = os.path.normpath(dirRel)
            dirAbs = _validar_y_normalizar_ruta(dirRelNorm, rutaBaseNorm, asegurar_existencia=False)
            if dirAbs is None: return False, f"Ruta inválida o insegura para crear directorio: '{dirRelNorm}'"
            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Creando directorio {dirRelNorm}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs): log.warning(f"{logPrefix} Directorio '{dirRelNorm}' ya existe."); return True, None
                else: err = f"Ya existe un ARCHIVO en la ruta del directorio a crear: '{dirRelNorm}'"; log.error(f"{logPrefix} {err}"); return False, err
            else:
                try: os.makedirs(dirAbs, exist_ok=True); log.info(f"{logPrefix} Directorio '{dirRelNorm}' creado."); return True, None
                except Exception as e: err = f"Error al crear directorio '{dirRelNorm}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
        # El return en las ramas anteriores hace innecesario un return aquí.


    # --- Validaciones iniciales (sin cambios) ---
    if not isinstance(archivos_con_contenido, dict):
         err = "Argumento 'archivos_con_contenido' no es un diccionario."
         log.error(f"{logPrefix} {err}")
         return False, err
    if not archivos_con_contenido:
         # Permitir esto si la acción original no requería contenido (ej. eliminar)
         if accionOriginal not in ["eliminar_archivo", "crear_directorio"]:
             err = f"Se esperaba contenido en 'archivos_con_contenido' para la acción '{accionOriginal}', pero está vacío. Error probable en Paso 2."
             log.error(f"{logPrefix} {err}")
             return False, err
         else:
             log.info(f"{logPrefix} No hay contenido en 'archivos_con_contenido', lo cual es esperado para la acción '{accionOriginal}'.")
             # Si la acción ya se manejó arriba, esto no se ejecutará. Si no, puede ser un caso borde.
             # Si la acción era eliminar/crear y ya se hizo, deberíamos haber retornado.
             # Si llega aquí, es un estado inesperado o una acción futura no manejada.
             # Por seguridad, considerarlo un éxito si la acción no requería contenido.
             if accionOriginal in ["eliminar_archivo", "crear_directorio"]:
                 # Esto no debería pasar si la lógica anterior es correcta
                 log.warning(f"{logPrefix} Lógica inesperada: Acción '{accionOriginal}' llegó aquí sin contenido y sin haber retornado antes.")
                 return True, None # Asumir éxito si la acción se completó arriba implícitamente
             else:
                 # Acción desconocida o que requería contenido pero no lo tiene
                 err = f"Acción '{accionOriginal}' recibió 'archivos_con_contenido' vacío inesperadamente."
                 log.error(f"{logPrefix} {err}")
                 return False, err


    log.info(f"{logPrefix} Procesando {len(archivos_con_contenido)} archivo(s) para escritura/modificación...")
    archivosProcesados = []
    errores = []

    # --- Bucle principal para escribir archivos ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        # --- Validación de ruta y creación de directorio padre (ligeramente mejorada) ---
        rutaRelNorm = os.path.normpath(rutaRel) # Normalizar ruta relativa
        archivoAbs = _validar_y_normalizar_ruta(rutaRelNorm, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Ruta inválida o insegura ('{rutaRelNorm}') recibida de Gemini (Paso 2). Archivo omitido."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        # --- Validación de tipo string (sin cambios) ---
        if not isinstance(contenido_original_json, str):
             log.warning(f"{logPrefix} Contenido para '{rutaRelNorm}' no es string (tipo {type(contenido_original_json)}). Convirtiendo a string.")
             try:
                 if isinstance(contenido_original_json, (dict, list)):
                     contenido_str = json.dumps(contenido_original_json, indent=2, ensure_ascii=False)
                 else:
                     contenido_str = str(contenido_original_json)
             except Exception as e_conv:
                  log.error(f"{logPrefix} No se pudo convertir el contenido no-string a string para '{rutaRelNorm}': {e_conv}. Omitiendo archivo.")
                  errores.append(f"Contenido no string inválido para {rutaRelNorm}")
                  continue
        else:
             contenido_str = contenido_original_json

        log.debug(f"{logPrefix} Procesando archivo: {rutaRelNorm} (Abs: {archivoAbs})")
        dirPadre = os.path.dirname(archivoAbs)
        try:
            if not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif not os.path.isdir(dirPadre):
                 # Esta verificación es crucial si la ruta base ya existe
                 raise ValueError(f"La ruta padre '{dirPadre}' para el archivo '{rutaRelNorm}' existe pero NO es un directorio.")
        except Exception as e_dir:
            msg = f"Error creando/validando directorio padre '{dirPadre}' para '{rutaRelNorm}': {e_dir}. Archivo omitido."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue

        # --- Inicio Bloque de Corrección (ESTRATEGIA REVISADA) ---
        contenido_procesado = contenido_str # Empezar con el string validado
        log.debug(f"{logPrefix} Contenido ORIGINAL para '{rutaRelNorm}' (repr): {repr(contenido_procesado[:200])}...")

        try:
            # --- PASO 1: Intentar corregir Mojibake (UTF-8 mal leído como Latin-1) ---
            contenido_despues_mojibake = contenido_procesado # Default si no se corrige
            try:
                # Solo intentar si parece contener Mojibake potencial (heurística simple)
                # Esto evita el encode/decode innecesario en texto ASCII o UTF-8 ya correcto.
                # Podría ser más sofisticado, pero es un comienzo.
                # La heurística original de simplemente intentar es más robusta.
                # if 'Ã' in contenido_procesado or 'Â' in contenido_procesado:
                log.debug(f"{logPrefix} Mojibake Check: Intentando encode('latin-1') y decode('utf-8') para '{rutaRelNorm}'...")
                # encode puede fallar si ya es UTF-8 con chars > Latin1
                bytes_probables = contenido_procesado.encode('latin-1')
                cadena_reconstruida_utf8 = bytes_probables.decode('utf-8') # decode puede fallar si encode tuvo éxito pero no era Mojibake real

                # Aplicar solo si la cadena cambió
                if cadena_reconstruida_utf8 != contenido_procesado:
                    log.info(f"{logPrefix} CORRECCIÓN (Mojibake UTF-8->Latin1->UTF-8): Aplicada para '{rutaRelNorm}'.")
                    contenido_despues_mojibake = cadena_reconstruida_utf8
                else:
                    log.debug(f"{logPrefix} Mojibake Check: La cadena no cambió después del ciclo encode/decode. No se aplicó corrección.")
                # else:
                #     log.debug(f"{logPrefix} Mojibake Check: No se detectaron caracteres Mojibake comunes. Saltando ciclo encode/decode.")
                #     contenido_despues_mojibake = contenido_procesado

            except UnicodeEncodeError:
                # Esto es normal si la cadena original ya era UTF-8 correcto.
                log.debug(f"{logPrefix} Mojibake Check: encode('latin-1') falló (esperado si ya es UTF-8 correcto). No se aplicó corrección de Mojibake.")
                contenido_despues_mojibake = contenido_procesado # Mantener el original
            except UnicodeDecodeError as e_moji_codec:
                 # Esto puede pasar si encode() tuvo éxito (ej: con \n) pero el resultado no es UTF-8 válido.
                 log.warning(f"{logPrefix} Mojibake Check para '{rutaRelNorm}': Falló el decode('utf-8') ('{e_moji_codec}'). Se usará la cadena original.")
                 contenido_despues_mojibake = contenido_procesado # Mantener el original
            except Exception as e_moji_other:
                 # Captura genérica por si acaso
                 log.warning(f"{logPrefix} Error inesperado durante chequeo de Mojibake para '{rutaRelNorm}': {e_moji_other}. Se usará la cadena original.")
                 contenido_despues_mojibake = contenido_procesado # Mantener el original como fallback seguro

            # Contenido listo para el siguiente paso
            contenido_intermedio = contenido_despues_mojibake
            log.debug(f"{logPrefix} Contenido DESPUÉS de Mojibake Check para '{rutaRelNorm}' (repr): {repr(contenido_intermedio[:200])}...")

            # --- PASO 2: Decodificar escapes estándar (incluyendo \uXXXX, \n, \t, \\, etc.) ---
            contenido_final = contenido_intermedio # Default si decode falla
            try:
                # Usar 'unicode_escape' para manejar \n, \t, \uXXXX, \\ etc.
                # ¡Importante! Esto asume que el 'contenido_intermedio' tiene las secuencias
                # de escape como literales (ej. la cadena contiene '\\' y 'n', no un newline real aun).
                log.debug(f"{logPrefix} Aplicando codecs.decode(..., 'unicode_escape') para '{rutaRelNorm}'")
                contenido_decodificado = codecs.decode(contenido_intermedio, 'unicode_escape')

                # Loguear solo si hubo cambios efectivos
                if contenido_decodificado != contenido_intermedio:
                     log.info(f"{logPrefix} CORRECCIÓN (unicode_escape): Secuencias de escape decodificadas (\\n, \\uXXXX, etc.) para '{rutaRelNorm}'.")
                     contenido_final = contenido_decodificado
                else:
                     log.debug(f"{logPrefix} No se aplicó decodificación 'unicode_escape' (o no hubo cambios).")

            except Exception as e_escape:
                 # Si unicode_escape falla (raro, pero posible con secuencias mal formadas),
                 # nos quedamos con el resultado post-Mojibake.
                 log.error(f"{logPrefix} Error decodificando escapes con 'unicode_escape' para '{rutaRelNorm}': {e_escape}. Se usará el contenido post-Mojibake.", exc_info=True)
                 contenido_final = contenido_intermedio # Fallback

            contenido_a_escribir = contenido_final
            log.debug(f"{logPrefix} Contenido DESPUÉS de unicode_escape para '{rutaRelNorm}' (repr): {repr(contenido_a_escribir[:200])}...")

            # --- PASO 3: Diagnóstico y Escritura ---
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRelNorm}' (inicio, repr): {repr(contenido_a_escribir[:200])}")
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRelNorm}' (fin, repr): {repr(contenido_a_escribir[-200:])}")

            # Advertir si aún se ven patrones Mojibake comunes (puede indicar problema en Paso 1 o entrada muy corrupta)
            mojibake_patterns = ['Ã©', 'Ã³', 'Ã¡', 'Ã±', 'Ãº', 'Ã‘', 'Ãš', 'Ã', 'Â¡', 'Â¿',
                                 'â‚¬', 'â„¢', 'Å¡', 'Å¥', 'Å¾', 'Å¸', 'Å“'] # Añadir más si es necesario
            if any(pattern in contenido_a_escribir for pattern in mojibake_patterns):
                found_pattern = next((p for p in mojibake_patterns if p in contenido_a_escribir), "N/A")
                log.warning(f"{logPrefix} ¡ALERTA! Contenido para '{rutaRelNorm}' TODAVÍA parece contener Mojibake (ej: '{found_pattern}') DESPUÉS del procesamiento. Revisar pasos anteriores y entrada original.")

            # Advertir si todavía hay secuencias de escape literales \uXXXX (podría indicar error en Paso 2 o entrada)
            # Usamos una expresión regular simple para encontrar '\' seguido de 'u' y 4 hex.
            import re
            if re.search(r'\\u[0-9a-fA-F]{4}', contenido_a_escribir):
                 log.warning(f"{logPrefix} ¡ALERTA! Contenido para '{rutaRelNorm}' TODAVÍA parece contener escapes \\uXXXX literales DESPUÉS del procesamiento. Esto puede ser intencional (si eran \\\\uXXXX) o un error.")


            # Escribir el resultado final en UTF-8
            log.debug(f"{logPrefix} Escribiendo {len(contenido_a_escribir)} caracteres en {archivoAbs} con UTF-8")
            with open(archivoAbs, 'w', encoding='utf-8') as f:
                f.write(contenido_a_escribir)
            log.info(f"{logPrefix} Archivo '{rutaRelNorm}' escrito/sobrescrito correctamente.")
            archivosProcesados.append(rutaRelNorm)

        except Exception as e_process_write:
             # Error durante la corrección o escritura del archivo específico
             msg = f"Error procesando/escribiendo archivo '{rutaRelNorm}': {e_process_write}"
             log.error(f"{logPrefix} {msg}", exc_info=True)
             errores.append(msg)
             # Continuar con el siguiente archivo si es posible

    # --- Fin del bucle for ---

    # --- Evaluación final (sin cambios) ---
    if errores:
        error_summary = f"Se completó el proceso pero con {len(errores)} error(es): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        # Decidir si devolver False incluso si algunos archivos se procesaron.
        # Por consistencia, si hubo algún error, devolver False.
        return False, error_summary
    elif not archivosProcesados and archivos_con_contenido:
         # Esto significa que se intentó procesar archivos pero todos fallaron antes de escribir.
         msg = "Se proporcionó contenido pero ningún archivo pudo ser procesado debido a errores previos (ver logs)."
         log.error(f"{logPrefix} {msg}")
         return False, msg
    elif not archivosProcesados and not archivos_con_contenido:
         # Esto es normal si la acción era eliminar/crear y no había nada que escribir.
         log.info(f"{logPrefix} No se procesaron archivos para escritura (esperado para acción '{accionOriginal}').")
         return True, None # Éxito
    else:
        # Se procesaron algunos o todos los archivos sin errores reportados en la lista 'errores'.
        log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados para escritura/modificación con éxito.")
        return True, None # Éxito

    
# Helper de rutas (sin cambios necesarios aquí, asumiendo que funciona)
def _validar_y_normalizar_ruta(rutaRelativa, rutaBase, asegurar_existencia=False):
    logPrefix = "_validar_y_normalizar_ruta:"
    # Añadir un check inicial para None o no string
    if not rutaRelativa or not isinstance(rutaRelativa, str):
        log.error(f"{logPrefix} Se recibió una ruta relativa inválida (None o no string): {rutaRelativa!r}")
        return None
    # Resto de la función como estaba...
    log.debug(f"{logPrefix} Validando rutaRelativa='{rutaRelativa}', rutaBase='{rutaBase}', asegurar_existencia={asegurar_existencia}")
    if '..' in rutaRelativa.split(os.sep):
        log.error(f"{logPrefix} Ruta relativa inválida o sospechosa (contiene '..'): '{rutaRelativa}'")
        return None
    rutaBaseNorm = os.path.normpath(os.path.abspath(rutaBase))
    rutaRelativaNorm = os.path.normpath(rutaRelativa)
    if os.path.isabs(rutaRelativaNorm):
         log.error(f"{logPrefix} Ruta relativa '{rutaRelativa}' parece ser absoluta tras normalizar: '{rutaRelativaNorm}'. Rechazada.")
         return None
    rutaAbs = os.path.join(rutaBaseNorm, rutaRelativaNorm)
    rutaAbs = os.path.normpath(rutaAbs)

    # Comprobación de seguridad estricta
    # Asegurarse que la base termine con separador para evitar falsos positivos (ej /base vs /base_otro)
    base_con_sep = rutaBaseNorm if rutaBaseNorm.endswith(os.sep) else rutaBaseNorm + os.sep
    if not os.path.abspath(rutaAbs).startswith(os.path.abspath(base_con_sep)) and \
       os.path.abspath(rutaAbs) != os.path.abspath(rutaBaseNorm):
        log.error(f"{logPrefix} Ruta calculada '{os.path.abspath(rutaAbs)}' intenta salir de la base '{os.path.abspath(rutaBaseNorm)}' (originada de '{rutaRelativa}')")
        return None

    if asegurar_existencia and not os.path.exists(rutaAbs):
        log.warning(f"{logPrefix} La ruta requerida no existe: '{rutaAbs}' (de '{rutaRelativa}')")
        # Cambiado a False, si se pide asegurar existencia y no existe, es un fallo en ese contexto
        return None # O podría ser True dependiendo de la lógica que llama

    log.debug(f"{logPrefix} Ruta validada y normalizada a: '{rutaAbs}'")
    return rutaAbs
