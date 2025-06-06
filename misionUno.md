### 3. [ ] (CRÍTICO) Implementación y **Priorización Estricta** de Cambios Atómicos (Nivel Función/Método) con Mapeo de Líneas

*   **Problema:** El método actual de devolver el contenido completo de un archivo para aplicar un cambio es propenso a errores, como la eliminación accidental de código no relacionado. Los intentos anteriores de cambios granulares fallaron porque la IA no lograba identificar con precisión el bloque de código a modificar. Se busca **priorizar y, temporalmente, forzar** el uso del mecanismo granular.

*   **Solución Estratégica:** Reestructurar y reforzar el flujo de trabajo en tres fases para asegurar una precisión quirúrgica. La creación de la misión ahora incluirá la **identificación y mapeo exacto de los bloques de código objetivo mediante números de línea**. La ejecución de la tarea operará únicamente sobre esos bloques, y un nuevo aplicador de cambios usará el mapa de líneas para realizar el reemplazo, preservando el resto del archivo. La aplicación de cambios se restringirá temporalmente para favorecer este flujo.

*   **Subtareas Detalladas:**

    #### Paso A: Planificación Precisa y **Obligatoriamente Granular** en la Creación de la Misión

    1.  **[COMPLETADA] Pre-procesamiento del Contexto con Números de Línea:**
        *   Función `_inyectar_numeros_linea(contenido_codigo)` creada y aplicada antes de `generar_contenido_mision_orion`.

    2.  **[COMPLETADA] Modificar el Prompt de `analizadorCodigo.generar_contenido_mision_orion`:**
        *   Instruido a la IA para identificar bloques y extraer información de `Bloques de Código Objetivo` usando el código numerado.

    3.  **[COMPLETADA] Evolucionar el Formato de Tarea en el Archivo de Misión (`.md`):**
        *   Se añadió la sección obligatoria `Bloques de Código Objetivo` a cada tarea.
        *   **Nota sobre archivos nuevos:** El prompt para `generar_contenido_mision_orion` ya instruye a la IA para usar `Línea Inicio: 1` y `Línea Fin: 1` (o una estimación baja) para bloques que representan la creación de un archivo nuevo. El `contenido_actual_bloque` para estos casos sería indicativo de un archivo nuevo (ej., vacío o una nota).

        ```markdown
        ---
        ### Tarea TSK-001: Refactorizar la lógica de usuario
        - **ID:** TSK-001
        - **Estado:** PENDIENTE
        - **Descripción:** Mover la validación de email de `controlador.php` a un nuevo método en `modelo.php`.
        - **Archivos Implicados Específicos:** `app/controlador.php`, `app/modelo.php`
        - **Intentos:** 0
        - **Bloques de Código Objetivo:**
          - **Archivo:** `app/controlador.php`
            - **Nombre Bloque:** `procesarFormulario`
            - **Línea Inicio:** 45
            - **Línea Fin:** 82
          - **Archivo:** `app/modelo.php`  # Asumimos que este archivo ya existe para agregar un método
            - **Nombre Bloque:** `Usuario` # Podría ser la clase donde se añade el método
            - **Línea Inicio:** 12 # Línea de inicio de la clase Usuario
            - **Línea Fin:** 150 # Línea de fin de la clase Usuario
                                 # (La IA en el Paso B decidiría la inserción con AGREGAR_BLOQUE)
          - **Archivo:** `app/nuevo_servicio.php` # Ejemplo de bloque para archivo nuevo
            - **Nombre Bloque:** `ContenidoInicialNuevoServicio`
            - **Línea Inicio:** 1
            - **Línea Fin:** 1 # O una estimación pequeña del contenido a generar
        ---
        ```

    4.  **[ ] (NUEVO - PARA FORZAR GRANULARIDAD) Validación Estricta Post-Generación de Misión:**
        *   **Ubicación:** En `principal.py`, específicamente en las funciones `_intentarCrearMisionDesdeSeleccionArchivo` (dentro del bucle, después de llamar a `paso1_2_generar_mision`) y `_intentarCrearMisionDesdeTodoMD` (después de llamar a `analizadorCodigo.generar_contenido_mision_desde_texto_guia`).
        *   **Lógica:** Después de que la IA genere `contenido_markdown_mision` y ANTES de guardar el archivo `.md` o commitear la nueva rama de misión:
            *   Invocar `manejadorMision.parsear_mision_orion` sobre el `contenido_markdown_mision` generado.
            *   Para cada tarea (`tarea_info`) en la `lista_tareas` devuelta:
                *   Verificar que `tarea_info` sea un diccionario y contenga la clave `bloques_codigo_objetivo`.
                *   Verificar que el valor de `bloques_codigo_objetivo` sea una lista no vacía.
                *   Verificar que cada elemento (representando un bloque) dentro de la lista `bloques_codigo_objetivo` sea un diccionario y contenga todas las claves requeridas: `archivo` (string no vacío), `nombre_bloque` (string no vacío), `linea_inicio` (integer >= 1), `linea_fin` (integer >= `linea_inicio`, o `linea_fin` >= 0 si `linea_inicio` es 1 para creación de archivo).
            *   **Si alguna de estas verificaciones falla para CUALQUIER tarea:**
                *   Loguear un ERROR crítico indicando la misión (`nombre_clave_mision`) y la tarea/bloque específico que no cumple con la estructura granular esperada.
                *   **Acción Correctiva (Temporal - Para Forzar Granularidad):** Considerar la generación de la misión como fallida.
                    *   No guardar el archivo `.md` de la misión.
                    *   No guardar/actualizar `.active_mission`.
                    *   Si se había creado una rama de misión, cambiar a la rama de trabajo principal (`settings.RAMATRABAJO`) y eliminar la rama de misión recién creada (usar `manejadorGit.eliminarRama(..., local=True)`).
                    *   En `_intentarCrearMisionDesdeSeleccionArchivo`, esto debería llevar a `continue` en el bucle de intentos para probar con otro archivo.
                    *   En `_intentarCrearMisionDesdeTodoMD`, esto significa que la función retorna `False` (fallo en crear misión desde TODO.md).
                *   Registrar este fallo de validación estructural en `manejadorHistorial` con un `outcome` distintivo (ej., `PASO1.2_ERROR_VALIDACION_GRANULAR`).
        *   **Siguientes Pasos:** Implementar esta lógica de validación en `principal.py` en las funciones `_intentarCrearMisionDesdeSeleccionArchivo` y `_intentarCrearMisionDesdeTodoMD`.

    #### Paso B: Ejecución **Estrictamente Granular** de la Tarea

    1.  **[COMPLETADA] Modificar el Input de la Función `analizadorCodigo.ejecutar_tarea_especifica_mision`:**
        *   La función ahora recibe los `bloques_codigo_input` extraídos por `principal.py` (usando el mapa de `Bloques de Código Objetivo` del `.md`).

    2.  **[COMPLETADA Y REFORZADA] Modificar el Prompt de `analizadorCodigo.ejecutar_tarea_especifica_mision`:**
        *   El prompt ya instruye a la IA para que devuelva un JSON que describa una lista de `modificaciones`.
        *   Se ha verificado que el prompt es explícito sobre cómo manejar la creación de archivos nuevos usando `REEMPLAZAR_BLOQUE` con `linea_inicio: 1`, `linea_fin: 1` y `nuevo_contenido` siendo el contenido completo. También se especifica el `response_schema` para Gemini.

    3.  **[COMPLETADA] Definir el Nuevo Formato de Respuesta JSON de la IA:**
        *   Estructura con `modificaciones` (lista de operaciones: `REEMPLAZAR_BLOQUE`, `AGREGAR_BLOQUE`, `ELIMINAR_BLOQUE`) y `advertencia_ejecucion`.

    #### Paso C: Aplicación **Quirúrgica Obligatoria** de Cambios

    1.  **[COMPLETADA] Crear Nueva Función `aplicadorCambios.aplicarCambiosGranulares`:**
        *   Interpreta el JSON con la lista de `modificaciones` y aplica los cambios al sistema de archivos.

    2.  **[COMPLETADA] Preservar `aplicadorCambios.aplicarCambiosSobrescrituraV2`:**
        *   Se mantiene para uso futuro explícito o si se revierte la política de "forzar granularidad", pero temporalmente no se usará como fallback automático.

    3.  **[ ] (MODIFICAR - PARA FORZAR GRANULARIDAD) Actualizar `principal.py` para Enrutamiento Inteligente (con restricción temporal):**
        *   **Ubicación:** En `principal.py`, dentro de la función `paso2_ejecutar_tarea_mision`, después de la llamada a `analizadorCodigo.ejecutar_tarea_especifica_mision`.
        *   **Lógica Actual (a modificar):** El script actualmente inspecciona la respuesta de la IA. Si contiene `"modificaciones"`, llama a `aplicarCambiosGranulares`. Si contiene `"archivos_modificados"`, llama a `aplicarCambiosSobrescrituraV2`.
        *   **Nueva Lógica (Temporal - Para Forzar Granularidad):**
            *   Si la respuesta de la IA (`resultado_ejecucion_tarea`) contiene la clave `"modificaciones"` y su valor es una lista (posiblemente vacía si solo hay una advertencia):
                *   Proceder a llamar a `aplicadorCambios.aplicarCambiosGranulares`.
                *   Loguear que se usó el aplicador granular.
            *   Si la respuesta de la IA contiene la clave `"archivos_modificados"` (y es un diccionario no vacío):
                *   Loguear una ADVERTENCIA SEVERA indicando que la IA devolvió el formato de sobrescritura (`archivos_modificados`) a pesar de las instrucciones de priorizar el formato granular (`modificaciones`). Incluir detalles de la tarea (ID, título).
                *   **Acción (Temporal):** NO llamar a `aplicadorCambios.aplicarCambiosSobrescrituraV2`.
                *   En su lugar, tratar esta respuesta como una falla de la IA para seguir el protocolo granular.
                *   Actualizar `contenido_mision_post_tarea` marcando la tarea actual como `FALLIDA_TEMPORALMENTE` (usar `manejadorMision.marcar_tarea_como_completada` con `incrementar_intentos_si_fallida_temp=True`).
                *   Guardar y commitear el archivo `.md` de la misión con este nuevo estado de tarea.
                *   El estado de retorno de `paso2_ejecutar_tarea_mision` debería ser `"tarea_fallida"` para que `_procesarMisionExistente` actúe en consecuencia (generalmente deteniendo el script para esta fase, permitiendo reintentos en la siguiente).
            *   Si la respuesta no contiene ni `"modificaciones"` (como lista) ni `"archivos_modificados"` (como dict), o es inválida (ej. no es un dict):
                *   Tratar como un error de formato de respuesta de la IA (esta parte de la lógica ya existe y debería marcar la tarea como `FALLIDA_TEMPORALMENTE`).
        *   **Siguientes Pasos:** Implementar esta lógica de enrutamiento modificado en `principal.py`, función `paso2_ejecutar_tarea_mision`.

    4.  **[COMPLETADA - VERIFICAR] Loguear el Aplicador Utilizado o el Fallo de Formato:** ()
        *   **Acción:** Se ha confirmado que `paso2_ejecutar_tarea_mision` en `principal.py` ya loguea el `aplicador_usado`. Con la modificación de C.3, si se recibe `archivos_modificados`, se logueará la advertencia y el motivo del fallo de la tarea (IA no siguió protocolo granular).
        *   Este logging es crucial para monitorizar la frecuencia con la que la IA intenta desviarse del flujo granular.
        *   [x] Implementada la validación en _intentarCrearMisionDesdeSeleccionArchiv

---

**Próximos Pasos:**

Implementar A.4 (continuación): Implementar la misma lógica de validación estricta en la función _intentarCrearMisionDesdeTodoMD en principal.py.
Implementar C.3: La modificación del enrutamiento en principal.py (paso2_ejecutar_tarea_mision) para tratar el formato archivos_modificados como un fallo temporal de la tarea.

*PROMPT HELPER DE WAN*

Revisa el archivo misionStatus.md que te he proporcionado.
Con base en la primera tarea pendiente crítica o problema activo que identifiques en misionStatus.md (prioriza las de la sección "Problemas Activos" o "Tareas Pendientes Críticas"):
Identifica el archivo (.py) que necesita ser modificado para abordar esa tarea.
Decide si vas a modificar:
Una función/método completo: Proporciona la función/método completo, desde su definición (def miFuncion(...): o class MiClase:\n def miMetodo(...):) hasta su final, sin omitir ninguna línea interna.
Un archivo completo: Solo si la tarea implica cambios estructurales extensos o afecta a la mayoría del archivo.
Reglas Estrictas para la Entrega del Código:
Entrega ÚNICA: Tu respuesta debe contener única y exclusivamente el código modificado (la función/método completo o el archivo completo).
Sin Código Adicional: NO incluyas otras funciones, clases (a menos que se modifique la clase entera), o bloques de código no solicitados.
Completo y Copiable: El código proporcionado debe ser directamente copiable y pegable.

**OBLIGATORIO** Al final siempre indicamente cual es la tarea que hay que actualizar, si hay que agregar una nueva, y cuales seran las siguientes.

A continuación parte del proyecto.