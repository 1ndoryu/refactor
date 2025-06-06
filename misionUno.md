### 3. [ ] (CRÍTICO) Implementación y **Priorización Estricta** de Cambios Atómicos (Nivel Función/Método) con Mapeo de Líneas

*   **Problema:** El método actual de devolver el contenido completo de un archivo para aplicar un cambio es propenso a errores. Se busca **priorizar y forzar** el uso del mecanismo granular.
*   **Solución Estratégica:** Reestructurar y reforzar el flujo de trabajo en tres fases para asegurar una precisión quirúrgica, usando mapeo de líneas.

*   **Subtareas Detalladas:**

    #### Paso A: Planificación Precisa y **Obligatoriamente Granular** en la Creación de la Misión

    1.  **[COMPLETADA]** Pre-procesamiento del Contexto con Números de Línea (`_inyectar_numeros_linea`).
    2.  **[COMPLETADA]** Modificación del Prompt de `analizadorCodigo.generar_contenido_mision_orion` (para identificar bloques y usar código numerado).
    3.  **[COMPLETADA]** Evolución del Formato de Tarea en el Archivo de Misión (`.md`) (con sección `Bloques de Código Objetivo` obligatoria).
        *   Ejemplo de formato de bloque:
        ```markdown
        ---
        ### Tarea TSK-001: ...
        ...
        - **Bloques de Código Objetivo:**
          - **Archivo:** `app/controlador.php`
            - **Nombre Bloque:** `procesarFormulario`
            - **Línea Inicio:** 45
            - **Línea Fin:** 82
          - **Archivo:** `app/nuevo_servicio.php`
            - **Nombre Bloque:** `ContenidoInicialNuevoServicio`
            - **Línea Inicio:** 1
            - **Línea Fin:** 1
        ---
        ```

    4.  **[ ] (NUEVO - PARA FORZAR GRANULARIDAD) Validación Estricta Post-Generación de Misión:**
        *   **Descripción General:** Después de que la IA genere `contenido_markdown_mision` (en `paso1_2_generar_mision` o `generar_contenido_mision_desde_texto_guia`) y ANTES de guardar el archivo `.md` o commitear:
            *   Invocar `manejadorMision.parsear_mision_orion`.
            *   Verificar que cada tarea y cada bloque dentro de `bloques_codigo_objetivo` cumpla con la estructura requerida (claves `archivo`, `nombre_bloque`, `linea_inicio`, `linea_fin` con tipos y valores correctos).
            *   **Si falla la validación:** Loguear error crítico, no guardar misión/estado, revertir rama de misión si se creó, registrar fallo en historial (`PASO1.2_ERROR_VALIDACION_GRANULAR`), y proceder según el flujo (reintentar o retornar fallo).
        *   **Subtareas de Implementación:**
            *   **[COMPLETADA] A.4.1: Implementar validación granular en `principal.py` - función `_intentarCrearMisionDesdeSeleccionArchivo`.**
                *   Lógica implementada después de llamar a `paso1_2_generar_mision`.
            *   **[COMPLETADA] A.4.2: Implementar validación granular en `principal.py` - función `_intentarCrearMisionDesdeTodoMD`.**
                *   Lógica a implementar después de llamar a `analizadorCodigo.generar_contenido_mision_desde_texto_guia`.

    #### Paso B: Ejecución **Estrictamente Granular** de la Tarea

    1.  **[COMPLETADA]** Modificación del Input de `analizadorCodigo.ejecutar_tarea_especifica_mision` (recibe `bloques_codigo_input`).
    2.  **[COMPLETADA Y REFORZADA]** Modificación del Prompt de `analizadorCodigo.ejecutar_tarea_especifica_mision` (para devolver JSON con `modificaciones` y `response_schema` para Gemini).
    3.  **[COMPLETADA]** Definición del Nuevo Formato de Respuesta JSON de la IA (con `modificaciones` y `advertencia_ejecucion`).

    #### Paso C: Aplicación **Quirúrgica Obligatoria** de Cambios

    1.  **[COMPLETADA]** Creación de Nueva Función `aplicadorCambios.aplicarCambiosGranulares`.
    2.  **[COMPLETADA]** Preservación de `aplicadorCambios.aplicarCambiosSobrescrituraV2` (temporalmente no como fallback automático).
    3.  **[ ] (MODIFICAR - PARA FORZAR GRANULARIDAD) Actualizar `principal.py` para Enrutamiento Inteligente (con restricción temporal):**
        *   **Ubicación:** En `principal.py`, función `paso2_ejecutar_tarea_mision`, después de `analizadorCodigo.ejecutar_tarea_especifica_mision`.
        *   **Nueva Lógica:**
            *   Si respuesta IA tiene `"modificaciones"` (lista): Llamar a `aplicarCambiosGranulares`.
            *   Si respuesta IA tiene `"archivos_modificados"` (dict no vacío): Loguear ADVERTENCIA SEVERA (IA no siguió protocolo granular), NO llamar a `aplicarCambiosSobrescrituraV2`, marcar tarea como `FALLIDA_TEMPORALMENTE`, guardar y commitear misión, retornar `"tarea_fallida"`.
            *   Si respuesta no tiene formato válido: Tratar como error de formato IA (tarea `FALLIDA_TEMPORALMENTE`).
        *   **Siguiente Paso:** Implementar esta lógica en `paso2_ejecutar_tarea_mision`.

    4.  **[COMPLETADA - VERIFICAR]** Logueo del Aplicador Utilizado o Fallo de Formato.
        *   Confirmado: `paso2_ejecutar_tarea_mision` loguea `aplicador_usado`. Con C.3, se logueará advertencia/fallo si IA devuelve `archivos_modificados`.

---

**Próximos Pasos:**

1.  **Implementar A.4.2:** La validación estricta en `principal.py` - función `_intentarCrearMisionDesdeTodoMD`.
2.  **Implementar C.3:** La modificación del enrutamiento en `principal.py` - función `paso2_ejecutar_tarea_mision` para tratar el formato `archivos_modificados` como un fallo temporal de la tarea.


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