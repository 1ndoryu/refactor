# nucleo/aplicadorCambios.py
import os
import logging
import shutil
import json
import codecs 

# NO BORRAR ESTE COMENTARIO 
# GUIA 
# ESTO FUNCIONA MAL, HAY QUE TESTEAR Y NO DEPENDER DE LA FORMA EN LA QUE RESPONDA GEMINI, AYUDAME A TESTEAR ESTO Y PROBAR QUE FUNCIONA BIEN PARA TODOS LOS COSAS  

#TE DEJO UN EJEMPLO DE COMO SE VE LA RESPUESTA DE GEMINI, PRUEBA COLOCAR UN LOG CON /N , Y ACENTOS 

# HAY 3 COSAS QUE PASAN A VECES, 
# LA PRIMERA, IMAGINA UN LOG QUE CONTIENE /N EN EL CODIGO PARA QUE CUANDO SE ACTIVE, GENERE ESPACIOS, AL GENERARSE ACA, LITERALMENTE SE GENERAN ESPACIOS, NO SE SI ESO SE PUEDE SOLUCIONAR (YA EN EL PROMPT SE INDICA QUE TIENE PONER //N DENTRO DEL CODIGO CUANDO EL CODIGO ES SALTO DE LINEA)
# LA SEGUNDA ES QUE A VECES GENERA CARACTERES ASI Funci\\u00f3n
# Y A VECES GENERA CODIGO ASI usarÃ¡:
# NECESITO TESTEAR QUE FUNCIONE CORRECTAMENTE SI CORRER EL CODIGO COMPLETO (NO SE COMO TESTEAR)

# 2025-03-31 09:24:34 - INFO - nucleo.analizadorCodigo.ejecutarAccionConGemini: ejecutarAccionConGemini (Paso 2): JSON de Ejecución Generado:
# {
#  "tipo_resultado": "ejecucion_cambio",
#  "archivos_modificados": {
#    "js/taskmove.js": "window.initMoverTarea = () => {\n    const tit = document.getElementById('tituloTarea');\n    if (tit) moverTarea();\n};\n\nfunction manejarSeleccionTarea(ev) {\n    const tarea = ev.target.closest('.draggable-element');\n    if (!tarea) return;\n    const id = tarea.getAttribute('id-post');\n\n    if (ev.ctrlKey) {\n        if (tareasSeleccionadas.includes(id)) {\n            tareasSeleccionadas = tareasSeleccionadas.filter(selId => selId !== id);\n            tarea.classList.remove('seleccionado');\n        } else {\n            tareasSeleccionadas.push(id);\n            tarea.classList.add('seleccionado');\n        }\n    }\n}\n\nfunction deseleccionarTareas() {\n    tareasSeleccionadas.forEach(id => {\n        const tarea = document.querySelector(`.draggable-element[id-post=\"${id}\"]`);\n        if (tarea) tarea.classList.remove('seleccionado');\n    });\n    tareasSeleccionadas = [];\n}\n\nfunction moverTarea() {\n    listaMov = document.querySelector('.clase-tarea');\n    if (!listaMov || listaMov.listenersAdded) return;\n    listaMov.listenersAdded = true;\n\n    const iniciarArrastre = ev => {\n        if (inicializarVars(ev)) {\n            listaMov.addEventListener('mousemove', manejarMov);\n            listaMov.addEventListener('mouseup', finalizarArrastre);\n        }\n    };\n\n    listaMov.addEventListener('mousedown', ev => {\n        const elem = ev.target.closest('.draggable-element');\n        if (elem) {\n            // Solo se deselecciona si no hay ninguna tarea previamente seleccionada\n            if (!ev.ctrlKey && tareasSeleccionadas.length === 0) {\n                deseleccionarTareas();\n            }\n            iniciarArrastre(ev);\n        } else {\n            deseleccionarTareas();\n        }\n    });\n\n    listaMov.addEventListener('click', manejarSeleccionTarea);\n    listaMov.addEventListener('dragstart', ev => ev.preventDefault());\n    document.addEventListener('click', ev => {\n        if (!listaMov.contains(ev.target)) deseleccionarTareas();\n    });\n}\n\n/* VARIABLES GLOBALES */\nlet listaMov,\n    // Para el modo individual se usan estas variables:\n    arrastrandoElem = null,\n    idTarea = null,\n    subtareasArrastradas = [],\n    esSubtarea = false,\n    // Para ambos modos (individual o grupal) se usará:\n    arrastrandoElems = [],\n    ordenViejo = [],\n    posInicialY = null,\n    movRealizado = false,\n    tareasSeleccionadas = [];\n\nconst tolerancia = 10;\n\n/* INICIALIZACIÓN DE VARIABLES AL INICIAR EL ARRASTRE */\nfunction inicializarVars(ev) {\n    // Se obtiene el elemento clickeado\n    const target = ev.target.closest('.draggable-element');\n    if (!target) return false;\n\n    let grupo;\n    // Si el elemento está en la lista de seleccionadas, se arrastrará el grupo completo\n    if (tareasSeleccionadas.includes(target.getAttribute('id-post'))) {\n        grupo = Array.from(listaMov.querySelectorAll('.draggable-element')).filter(el => tareasSeleccionadas.includes(el.getAttribute('id-post')));\n    } else {\n        grupo = [target];\n    }\n    arrastrandoElems = grupo;\n\n    // Si se arrastra una única tarea, se usan las variables originales para conservar la lógica de “subtareas”\n    if (grupo.length === 1) {\n        arrastrandoElem = grupo[0];\n        esSubtarea = arrastrandoElem.getAttribute('subtarea') === 'true';\n        idTarea = arrastrandoElem.getAttribute('id-post');\n        ordenViejo = Array.from(listaMov.querySelectorAll('.draggable-element')).map(t => t.getAttribute('id-post'));\n        // Para arrastrar subtareas: si la tarea arrastrada no es subtarea, se obtienen las tareas que cuelgan de ella\n        if (!esSubtarea) {\n            subtareasArrastradas = Array.from(listaMov.querySelectorAll(`.draggable-element[padre=\"${idTarea}\"]`));\n        } else {\n            subtareasArrastradas = [];\n        }\n    } else {\n        // En modo grupo se ignoran las variables individuales; se conserva solo el grupo.\n        arrastrandoElem = null;\n        subtareasArrastradas = [];\n        esSubtarea = false;\n        idTarea = null;\n        ordenViejo = [];\n    }\n\n    posInicialY = ev.clientY;\n    movRealizado = false;\n\n    // Se agrega la clase de arrastre a todos los elementos del grupo\n    arrastrandoElems.forEach(el => el.classList.add('dragging'));\n    document.body.classList.add('dragging-active');\n    return true;\n}\n\n/* MANEJO DEL MOVIMIENTO */\nfunction manejarMov(ev) {\n    if (arrastrandoElems.length === 0) return;\n    ev.preventDefault();\n    const mouseY = ev.clientY;\n    const rectLista = listaMov.getBoundingClientRect();\n\n    if (!movRealizado && Math.abs(mouseY - posInicialY) > tolerancia) {\n        movRealizado = true;\n    }\n    if (mouseY < rectLista.top || mouseY > rectLista.bottom) return;\n\n    // Se obtienen los elementos visibles que NO forman parte del grupo arrastrado\n    const elemsVisibles = Array.from(listaMov.children).filter(child => child.style.display !== 'none' && !arrastrandoElems.includes(child));\n    let insertado = false;\n\n    // Se recorre la lista para determinar dónde insertar el grupo\n    for (let i = 0; i < elemsVisibles.length; i++) {\n        const elem = elemsVisibles[i];\n        const rectElem = elem.getBoundingClientRect();\n        const elemMedio = rectElem.top + rectElem.height / 2;\n        if (mouseY < elemMedio) {\n            // Se inserta cada elemento del grupo antes del elemento actual\n            arrastrandoElems.forEach(el => {\n                listaMov.insertBefore(el, elem);\n            });\n            insertado = true;\n            break;\n        }\n    }\n    // Si no se insertó en medio, se agregan al final\n    if (!insertado && elemsVisibles.length > 0) {\n        arrastrandoElems.forEach(el => {\n            listaMov.appendChild(el);\n        });\n    }\n\n    // En modo individual y si la tarea no es subtarea, se reposicionan también sus subtareas justo detrás\n    if (arrastrandoElems.length === 1 && !esSubtarea) {\n        let current = arrastrandoElem;\n        subtareasArrastradas.forEach(subtarea => {\n            listaMov.insertBefore(subtarea, current.nextSibling);\n            current = subtarea;\n        });\n    }\n}\n\n/* FINALIZAR ARRASTRE */\nfunction finalizarArrastre() {\n    if (arrastrandoElems.length === 0) return;\n    const ordenNuevo = Array.from(listaMov.querySelectorAll('.draggable-element')).map(t => t.getAttribute('id-post'));\n\n    if (movRealizado) {\n        // MODO INDIVIDUAL: se conserva la lógica original (con manejo de “subtarea”)\n        if (arrastrandoElems.length === 1) {\n            const nuevaPos = ordenNuevo.indexOf(idTarea);\n            const {sesionArriba, dataArriba} = obtenerSesionYData();\n            const {nuevaEsSubtarea} = cambioASubtarea();\n            let padre = '';\n            if (nuevaEsSubtarea) {\n                const tareaPadre = arrastrandoElem.nextElementSibling;\n                padre = tareaPadre ? tareaPadre.getAttribute('id-post') : '';\n                if (padre) {\n                    arrastrandoElem.setAttribute('padre', padre);\n                    arrastrandoElem.setAttribute('subtarea', 'true');\n                } else {\n                    padre = '';\n                }\n                arrastrandoElem.setAttribute('data-seccion', dataArriba);\n                arrastrandoElem.setAttribute('sesion', sesionArriba);\n            } else {\n                padre = '';\n                arrastrandoElem.removeAttribute('padre');\n                arrastrandoElem.setAttribute('subtarea', 'false');\n                arrastrandoElem.setAttribute('data-seccion', dataArriba);\n                subtareasArrastradas.forEach(subtarea => subtarea.setAttribute('data-seccion', dataArriba));\n                arrastrandoElem.setAttribute('sesion', sesionArriba);\n                subtareasArrastradas.forEach(subtarea => subtarea.setAttribute('sesion', sesionArriba));\n            }\n            guardarOrdenTareas({\n                idTarea,\n                nuevaPos,\n                ordenNuevo,\n                sesionArriba,\n                dataArriba,\n                subtarea: nuevaEsSubtarea,\n                padre\n            });\n        } else {\n            // MODO GRUPAL: se toma el array de ids de las tareas arrastradas y se determina la posición\n            const draggedIds = arrastrandoElems.map(el => el.getAttribute('id-post'));\n            // Se toma la menor posición (la del primer elemento en el nuevo orden)\n            const primeraPos = Math.min(...draggedIds.map(id => ordenNuevo.indexOf(id)));\n            guardarOrdenTareasGrupo({\n                tareasMovidas: draggedIds,\n                nuevaPos: primeraPos,\n                ordenNuevo\n            });\n        }\n    }\n\n    // Se quitan las clases de “arrastre” y se limpian las variables\n    arrastrandoElems.forEach(el => el.classList.remove('dragging'));\n    document.body.classList.remove('dragging-active');\n    listaMov.removeEventListener('mousemove', manejarMov);\n    listaMov.removeEventListener('mouseup', finalizarArrastre);\n\n    arrastrandoElem = null;\n    arrastrandoElems = [];\n    idTarea = null;\n    ordenViejo = [];\n    posInicialY = null;\n    movRealizado = false;\n    subtareasArrastradas = [];\n    esSubtarea = false;\n}\n\n/* Función para obtener datos de la tarea de referencia (sin cambios respecto a la versión original) */\nfunction obtenerSesionYData() {\n    let sesionArriba = null;\n    let dataArriba = null;\n    let anterior = (arrastrandoElem || arrastrandoElems[0]).previousElementSibling;\n    while (anterior) {\n        if (anterior.classList.contains('POST-tarea')) {\n            sesionArriba = anterior.getAttribute('sesion');\n            dataArriba = anterior.getAttribute('data-seccion');\n        } else if (anterior.classList.contains('divisorTarea')) {\n            sesionArriba = sesionArriba || anterior.getAttribute('data-valor');\n            dataArriba = dataArriba || anterior.getAttribute('data-valor');\n        }\n        if (sesionArriba !== null && dataArriba !== null) break;\n        anterior = anterior.previousElementSibling;\n    }\n    return {sesionArriba, dataArriba};\n}\n\n/* Función que determina si la tarea cambia a subtarea (se usa en modo individual) */\n\n\nfunction cambioASubtarea() {\n    const nuevaEsSubtarea = esSubtareaNueva();\n    const cambioSubtarea = nuevaEsSubtarea !== esSubtarea;\n    if (cambioSubtarea) {\n        window.reiniciarPost(idTarea, 'tarea');\n    }\n    return {nuevaEsSubtarea};\n}\n\n/* Función para guardar el nuevo orden cuando se mueve una sola tarea (modo individual) */\nfunction guardarOrdenTareas({idTarea, nuevaPos, ordenNuevo, sesionArriba, dataArriba, subtarea, padre}) {\n    let data = {\n        tareaMovida: idTarea,\n        nuevaPos,\n        ordenNuevo,\n        sesionArriba,\n        dataArriba,\n        subtarea,\n        padre: subtarea ? padre : null\n    };\n    enviarAjax('actualizarOrdenTareas', data)\n        .then(res => {\n            if (res && res.success) {\n                window.reiniciarPost(idTarea, 'tarea');\n            } else {\n                console.error('Hubo un error en la respuesta del servidor:', res);\n            }\n        })\n        .catch(err => {\n            console.error('Error en la petición AJAX:', err);\n        });\n}\n\n/* Función para guardar el nuevo orden cuando se mueven varias tareas (modo grupal) */\nfunction guardarOrdenTareasGrupo({tareasMovidas, nuevaPos, ordenNuevo}) {\n    let data = {\n        tareasMovidas, // array de ids de las tareas arrastradas\n        nuevaPos, // posición de inserción (la del primer elemento del grupo)\n        ordenNuevo\n    };\n    enviarAjax('actualizarOrdenTareasGrupo', data)\n        .then(res => {\n            if (res && res.success) {\n                // Opcional: reiniciar cada tarea del grupo\n                tareasMovidas.forEach(id => window.reiniciarPost(id, 'tarea'));\n            } else {\n                console.error('Hubo un error en la respuesta del servidor:', res);\n            }\n        })\n        .catch(err => {\n            console.error('Error en la petición AJAX:', err);\n        });\n}\n"
#  }
# }

# Obtener logger
log = logging.getLogger(__name__)

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


# --- FUNCIÓN PRINCIPAL CON ESTRATEGIA FINAL (Mojibake primero, luego escapes manuales básicos) ---
def aplicarCambiosSobrescritura(archivos_con_contenido, rutaBase, accionOriginal, paramsOriginal):
    # LUEGO reemplaza manualmente escapes básicos (\n, \t, \r, \\). NO procesa \uXXXX.
    """
    Aplica los cambios generados por Gemini.
    - Sobrescribe archivos existentes o crea nuevos con el contenido proporcionado.
    - Maneja acciones como eliminar_archivo y crear_directorio.
    - PRIMERO intenta corregir Mojibake común (UTF-8 mal leído como Latin-1).
    -
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
        if accionOriginal == "eliminar_archivo":
            archivoRel = paramsOriginal.get("archivo")
            if not archivoRel: return False, "Falta 'archivo' en parámetros para eliminar_archivo."
            archivoAbs = _validar_y_normalizar_ruta(archivoRel, rutaBaseNorm, asegurar_existencia=False)
            if archivoAbs is None: return False, f"Ruta inválida o no encontrada para eliminar: '{archivoRel}'"
            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Eliminando {archivoRel}")
            if os.path.exists(archivoAbs):
                if os.path.isfile(archivoAbs):
                    try: os.remove(archivoAbs); log.info(f"{logPrefix} Archivo '{archivoRel}' eliminado."); return True, None
                    except Exception as e: err = f"Error al eliminar archivo '{archivoRel}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
                else: err = f"Ruta a eliminar '{archivoRel}' existe pero NO es un archivo."; log.error(f"{logPrefix} {err}"); return False, err
            else: log.warning(f"{logPrefix} Archivo a eliminar '{archivoRel}' no encontrado. Se considera éxito."); return True, None
        elif accionOriginal == "crear_directorio":
            dirRel = paramsOriginal.get("directorio")
            if not dirRel: return False, "Falta 'directorio' en parámetros para crear_directorio."
            dirAbs = _validar_y_normalizar_ruta(dirRel, rutaBaseNorm, asegurar_existencia=False)
            if dirAbs is None: return False, f"Ruta inválida para crear directorio: '{dirRel}'"
            log.info(f"{logPrefix} Ejecutando acción '{accionOriginal}': Creando directorio {dirRel}")
            if os.path.exists(dirAbs):
                if os.path.isdir(dirAbs): log.warning(f"{logPrefix} Directorio '{dirRel}' ya existe."); return True, None
                else: err = f"Ya existe un ARCHIVO en la ruta del directorio a crear: '{dirRel}'"; log.error(f"{logPrefix} {err}"); return False, err
            else:
                try: os.makedirs(dirAbs, exist_ok=True); log.info(f"{logPrefix} Directorio '{dirRel}' creado."); return True, None
                except Exception as e: err = f"Error al crear directorio '{dirRel}': {e}"; log.error(f"{logPrefix} {err}", exc_info=True); return False, err
        # El return en las ramas anteriores hace innecesario un return aquí.

    # --- Validaciones iniciales (sin cambios) ---
    if not isinstance(archivos_con_contenido, dict):
         err = "Argumento 'archivos_con_contenido' no es un diccionario."
         log.error(f"{logPrefix} {err}")
         return False, err
    if not archivos_con_contenido:
         err = f"Se esperaba contenido en 'archivos_con_contenido' para la acción '{accionOriginal}', pero está vacío. Error probable en Paso 2."
         log.error(f"{logPrefix} {err}")
         return False, err

    log.info(f"{logPrefix} Sobrescribiendo/Creando {len(archivos_con_contenido)} archivo(s)...")
    archivosProcesados = []
    errores = []

    # --- Bucle principal para escribir archivos ---
    for rutaRel, contenido_original_json in archivos_con_contenido.items():
        # --- Validación de ruta y creación de directorio padre (sin cambios) ---
        archivoAbs = _validar_y_normalizar_ruta(rutaRel, rutaBaseNorm, asegurar_existencia=False)
        if archivoAbs is None:
            msg = f"Ruta inválida o insegura ('{rutaRel}') recibida de Gemini (Paso 2). Archivo omitido."
            log.error(f"{logPrefix} {msg}")
            errores.append(msg)
            continue

        # --- Validación de tipo string (sin cambios) ---
        if not isinstance(contenido_original_json, str):
             log.warning(f"{logPrefix} Contenido para '{rutaRel}' no es string (tipo {type(contenido_original_json)}). Convirtiendo a string.")
             try:
                 if isinstance(contenido_original_json, (dict, list)):
                     contenido_str = json.dumps(contenido_original_json, indent=2, ensure_ascii=False)
                 else:
                     contenido_str = str(contenido_original_json)
             except Exception as e_conv:
                  log.error(f"{logPrefix} No se pudo convertir el contenido no-string a string para '{rutaRel}': {e_conv}. Omitiendo archivo.")
                  errores.append(f"Contenido no string inválido para {rutaRel}")
                  continue
        else:
             contenido_str = contenido_original_json

        log.debug(f"{logPrefix} Procesando archivo: {rutaRel} (Abs: {archivoAbs})")
        dirPadre = os.path.dirname(archivoAbs)
        try:
            if not os.path.exists(dirPadre):
                log.info(f"{logPrefix} Creando directorio padre necesario: {dirPadre}")
                os.makedirs(dirPadre, exist_ok=True)
            elif not os.path.isdir(dirPadre):
                 raise ValueError(f"La ruta padre '{dirPadre}' para el archivo '{rutaRel}' existe pero NO es un directorio.")
        except Exception as e_dir:
            msg = f"Error creando/validando directorio padre '{dirPadre}' para '{rutaRel}': {e_dir}. Archivo omitido."
            log.error(f"{logPrefix} {msg}", exc_info=True)
            errores.append(msg)
            continue

        # --- Inicio Bloque de Corrección (ESTRATEGIA FINAL) ---
        contenido_procesado = contenido_str # Empezar con el string validado
        log.debug(f"{logPrefix} Contenido ORIGINAL (repr): {repr(contenido_procesado[:200])}...")

        try:
            # --- PASO 1: Intentar corregir Mojibake (UTF-8 mal leído como Latin-1) ---
            contenido_despues_mojibake = contenido_procesado # Default si no se corrige
            try:
                log.debug(f"{logPrefix} Mojibake Check: Intentando encode('latin-1') y decode('utf-8') para '{rutaRel}'...")
                # encode puede fallar si ya es UTF-8 con chars > Latin1
                bytes_probables = contenido_procesado.encode('latin-1')
                cadena_reconstruida_utf8 = bytes_probables.decode('utf-8') # decode puede fallar si encode tuvo éxito pero no era Mojibake real

                # Aplicar solo si la cadena cambió
                if cadena_reconstruida_utf8 != contenido_procesado:
                    log.info(f"{logPrefix} CORRECCIÓN (Mojibake UTF-8->Latin1->UTF-8): Aplicada para '{rutaRel}'.")
                    contenido_despues_mojibake = cadena_reconstruida_utf8
                else:
                    log.debug(f"{logPrefix} Mojibake Check: La cadena no cambió después del ciclo encode/decode. No se aplicó corrección.")

            except UnicodeEncodeError:
                # Esto es normal si la cadena original ya era UTF-8 correcto.
                log.debug(f"{logPrefix} Mojibake Check: encode('latin-1') falló (esperado si ya es UTF-8 correcto). No se aplicó corrección de Mojibake.")
                contenido_despues_mojibake = contenido_procesado # Mantener el original
            except UnicodeDecodeError as e_moji_codec:
                 # Esto puede pasar si encode() tuvo éxito (ej: con \n) pero el resultado no es UTF-8 válido.
                 log.warning(f"{logPrefix} Mojibake Check para '{rutaRel}': Falló el decode('utf-8') ('{e_moji_codec}'). Se usará la cadena original.")
                 contenido_despues_mojibake = contenido_procesado # Mantener el original
            except Exception as e_moji_other:
                 # Captura genérica por si acaso
                 log.warning(f"{logPrefix} Error inesperado durante chequeo de Mojibake para '{rutaRel}': {e_moji_other}. Se usará la cadena original.")
                 contenido_despues_mojibake = contenido_procesado # Mantener el original como fallback seguro

            # Actualizar para el siguiente paso
            contenido_intermedio = contenido_despues_mojibake
            log.debug(f"{logPrefix} Contenido DESPUÉS de Mojibake Check (repr): {repr(contenido_intermedio[:200])}...")

            # --- PASO 2: Reemplazar manualmente escapes comunes ---
            # ¡Importante! El orden de reemplazo es crucial, especialmente para '\\'
            contenido_final = contenido_intermedio.replace('\\\\', '\u0001') # Placeholder temporal para barra invertida
            contenido_final = contenido_final.replace('\\n', '\n')   # Newline
            contenido_final = contenido_final.replace('\\t', '\t')   # Tab
            contenido_final = contenido_final.replace('\\r', '\r')   # Carriage return
            contenido_final = contenido_final.replace('\\"', '"')    # Doble comilla escapada (si viene así de JSON)
            # contenido_final = contenido_final.replace("\\'", "'")  # Comilla simple escapada (menos probable)
            contenido_final = contenido_final.replace('\u0001', '\\') # Restaurar barra invertida

            # Loguear si hubo cambios en este paso
            if contenido_final != contenido_intermedio:
                 log.info(f"{logPrefix} CORRECCIÓN (Escapes Manuales): Se reemplazaron secuencias de escape comunes (\\n, \\t, \\\\, etc.) para '{rutaRel}'.")
            else:
                 log.debug(f"{logPrefix} No se encontraron secuencias de escape comunes para reemplazar manualmente.")

            # Nota: No procesamos \uXXXX explícitamente para evitar la corrupción vista antes.
            # Si Gemini envía \uXXXX literal, se escribirá \uXXXX literal.

            contenido_a_escribir = contenido_final
            log.debug(f"{logPrefix} Contenido DESPUÉS de Escapes Manuales (repr): {repr(contenido_a_escribir[:200])}...")

            # --- PASO 3: Diagnóstico y Escritura ---
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRel}' (inicio, repr): {repr(contenido_a_escribir[:200])}")
            log.debug(f"{logPrefix} Contenido FINAL A ESCRIBIR para '{rutaRel}' (fin, repr): {repr(contenido_a_escribir[-200:])}")

            # Advertir si aún se ven patrones Mojibake comunes
            mojibake_patterns = ['Ã©', 'Ã³', 'Ã¡', 'Ã±', 'Ãº', 'Ã‘', 'Ãš', 'Ã', 'Â¡', 'Â¿',
                                 'â‚¬', 'â„¢', 'Å¡', 'Å¥', 'Å¾', 'Å¸', 'Å“']
            if any(pattern in contenido_a_escribir for pattern in mojibake_patterns):
                found_pattern = next((p for p in mojibake_patterns if p in contenido_a_escribir), "N/A")
                log.warning(f"{logPrefix} ¡ALERTA! Contenido para '{rutaRel}' TODAVÍA parece contener Mojibake (ej: '{found_pattern}') ANTES de escribir. Revisar pasos anteriores.")

            # Escribir el resultado final en UTF-8
            log.debug(f"{logPrefix} Escribiendo {len(contenido_a_escribir)} caracteres en {archivoAbs} con UTF-8")
            with open(archivoAbs, 'w', encoding='utf-8') as f:
                f.write(contenido_a_escribir)
            log.info(f"{logPrefix} Archivo '{rutaRel}' escrito/sobrescrito correctamente.")
            archivosProcesados.append(rutaRel)

        except Exception as e_process_write:
             # Error durante la corrección o escritura del archivo específico
             msg = f"Error procesando/escribiendo archivo '{rutaRel}': {e_process_write}"
             log.error(f"{logPrefix} {msg}", exc_info=True)
             errores.append(msg)
             # Continuar con el siguiente archivo si es posible

    # --- Fin del bucle for ---

    # --- Evaluación final (sin cambios) ---
    if errores:
        error_summary = f"Se completó el proceso pero con {len(errores)} error(es): {'; '.join(errores[:3])}{'...' if len(errores) > 3 else ''}"
        log.error(f"{logPrefix} {error_summary}")
        return False, error_summary
    elif not archivosProcesados and archivos_con_contenido:
         msg = "Se proporcionó contenido pero ningún archivo pudo ser procesado debido a errores previos (ver logs)."
         log.error(f"{logPrefix} {msg}")
         return False, msg
    else:
        log.info(f"{logPrefix} Todos los archivos ({len(archivosProcesados)}) fueron procesados con éxito.")
        return True, None # Éxito