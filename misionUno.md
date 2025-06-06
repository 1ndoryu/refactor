### 3. [ ] (CRÍTICO) Implementación de Cambios Atómicos (Nivel Función/Método) con Mapeo de Líneas, esta tarea de total relevancia.

*   **Problema:** El método actual de devolver el contenido completo de un archivo para aplicar un cambio es propenso a errores, como la eliminación accidental de código no relacionado. Los intentos anteriores de cambios granulares fallaron porque la IA no lograba identificar con precisión el bloque de código a modificar (ej. por diferencias mínimas en el nombre de la función).

*   **Solución Estratégica:** Reestructurar el flujo de trabajo en tres fases para asegurar una precisión quirúrgica. La creación de la misión ahora incluirá la **identificación y mapeo exacto de los bloques de código objetivo mediante números de línea**. La ejecución de la tarea operará únicamente sobre esos bloques, y un nuevo aplicador de cambios usará el mapa de líneas para realizar el reemplazo, preservando el resto del archivo.

*   **Subtareas Detalladas:**

    #### Paso A: Planificación Precisa en la Creación de la Misión

    El objetivo es modificar `analizadorCodigo.generar_contenido_mision_orion` para que la misión generada contenga un mapa exacto de los bloques de código que se pretenden modificar.

    1.  **[COMPLETADA] Pre-procesamiento del Contexto con Números de Línea:**
        *   Crear una nueva función de ayuda, por ejemplo `_inyectar_numeros_linea(contenido_codigo)`, que tome el texto de un archivo y le anteponga un número de línea a cada línea (ej. `1: <?php\n2: function miFuncion()...`).
        *   Antes de pasar el contexto de los archivos a `generar_contenido_mision_orion`, aplicarles esta función.

    2.  **[COMPLETADA] Modificar el Prompt de `generar_contenido_mision_orion`:**
        *   Instruir a la IA para que, al definir una tarea, identifique los bloques de código específicos (funciones, métodos) que deben ser modificados.
        *   Exigir a la IA que, utilizando el código con números de línea que se le proporciona, extraiga la siguiente información para cada bloque objetivo y la formatee en una nueva sección dentro de la tarea en el Markdown.

    3.  **[ ] Evolucionar el Formato de Tarea en el Archivo de Misión (`.md`):**
        *   Añadir una nueva sección obligatoria a la estructura de cada tarea llamada `Bloques de Código Objetivo`.

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
          - **Archivo:** `app/modelo.php`
            - **Nombre Bloque:** `Usuario` (para indicar una clase)
            - **Línea Inicio:** 12 #creo que esto no debería de ir porque si el archivo todavía no existe, no debería pues saber cuales son las lineas por logica, no se, tengo dudas. O debe manejarse de varias formas dependiendo de que si el archivo existe o no, o evaluarse despues.
            - **Línea Fin:** 150
        ---
        ```

    #### Paso B: Ejecución Enfocada de la Tarea

    El objetivo es modificar `analizadorCodigo.ejecutar_tarea_especifica_mision` para que trabaje de forma atómica.

    1.  **[ ] Modificar el Input de la Función:**
        *   La función ya no recibirá el contenido completo de todos los archivos de contexto. En su lugar, `principal.py` deberá usar el mapa de `Bloques de Código Objetivo` para extraer y pasar a la IA únicamente los fragmentos de código relevantes para la tarea. Esto reduce drásticamente el uso de tokens.

    2.  **[ ] Modificar el Prompt de `ejecutar_tarea_especifica_mision`:**
        *   El prompt instruirá a la IA para que devuelva un JSON que describa una lista de *operaciones de modificación*, en lugar del contenido de archivos completos.

    3.  **[ ] Definir el Nuevo Formato de Respuesta JSON de la IA:**
        *   La IA deberá generar una estructura como la siguiente:

        ```json
        {
          "modificaciones": [
            {
              "tipo_operacion": "REEMPLAZAR_BLOQUE",
              "ruta_archivo": "app/controlador.php",
              "linea_inicio": 45,
              "linea_fin": 82,
              "nuevo_contenido": "/* ... nuevo código completo para la función procesarFormulario ... */"
            },
            {
              "tipo_operacion": "AGREGAR_BLOQUE",
              "ruta_archivo": "app/modelo.php",
              "insertar_despues_de_linea": 150,
              "nuevo_contenido": "  public function validarEmail($email) {\n    // ... nueva lógica de validación ...\n  }\n"
            }
          ],
          "advertencia_ejecucion": null
        }
        ```
        *   `tipo_operacion` puede ser `REEMPLAZAR_BLOQUE`, `AGREGAR_BLOQUE`, `ELIMINAR_BLOQUE`.

    #### Paso C: Aplicación Quirúrgica de Cambios

    El objetivo es crear un nuevo aplicador en `aplicadorCambios.py` que sepa interpretar la nueva estructura de datos de la IA.

    1.  **[ ] Crear Nueva Función `aplicadorCambios.aplicarCambiosGranulares`:**
        *   Esta nueva función recibirá el objeto JSON con la lista de `modificaciones`.
        *   Para cada operación en la lista:
            *   Leerá el archivo objetivo en una lista de líneas de Python.
            *   **Para `REEMPLAZAR_BLOQUE`:** Creará una nueva lista de líneas reemplazando el rango `[linea_inicio-1:linea_fin]` con el `nuevo_contenido`.
            *   **Para `AGREGAR_BLOQUE`:** Insertará el `nuevo_contenido` en la lista en la posición `insertar_despues_de_linea`.
            *   **Para `ELIMINAR_BLOQUE`:** Idéntico a `REEMPLAZAR_BLOQUE` pero con `nuevo_contenido` vacío.
            *   Finalmente, unirá la lista de líneas modificada y sobrescribirá el archivo.

    2.  **[ ] Preservar `aplicadorCambios.aplicarCambiosSobrescrituraV2`:**
        *   Esta función se mantendrá intacta. Será útil para tareas que legítimamente necesiten crear o reescribir archivos pequeños desde cero.

    3.  **[ ] Actualizar `principal.py` para Enrutamiento Inteligente:**
        *   Después de la llamada a `ejecutar_tarea_especifica_mision`, el script inspeccionará la respuesta de la IA.
        *   Si la respuesta contiene la clave `"modificaciones"`, llamará a `aplicarCambiosGranulares`.
        *   Si contiene la clave `"archivos_modificados"`, llamará a `aplicarCambiosSobrescrituraV2` (manteniendo la compatibilidad con el flujo antiguo o tareas que lo requieran).


4.  [ ] **(ALTO)** **Mecanismo de Validación Post-Cambio y Auto-Corrección/Reversión:**
    *   Implementar un paso de validación después de que `aplicadorCambios` aplique los cambios de una tarea.
    *   **Subtareas:**
        *   [ ] Diseñar un prompt para que la IA revise el `git diff` de los cambios o el contenido del bloque modificado, comparándolo con la intención original de la tarea.
        *   [ ] Si la validación de la IA indica un problema, intentar una corrección (otro prompt pidiendo que corrija su salida anterior).
        *   [ ] Si la corrección falla, revertir automáticamente los cambios de ESA tarea (ej. `git reset HEAD^` si la tarea ya se commiteó).
5.  [ ] **(ALTO)** **Verificación de Archivos Vacíos Antes de Lectura por IA:**
    *   En `analizadorCodigo.leerArchivos` (o antes de llamarlo), verificar si un archivo está vacío. Si lo está, no incluir su contenido en el prompt y registrar este hecho para ahorrar tokens.
6.  [ ] **(ALTO)** **Robustez en `manejadorGit.clonarOActualizarRepo`:**
    *   Mejorar la detección de la rama principal remota. Antes de cualquier `checkout` o `reset`, verificar explícitamente que la rama exista en `origin` (`manejadorGit.existe_rama(..., remote_only=True)`). Manejar el error si no existe.
7.  [ ] **(MEDIO)** **Timeout por Tarea de IA:**
    *   Implementar un timeout específico (ej. 4-5 minutos) para las llamadas a la IA que son propensas a tardar mucho, como `ejecutar_tarea_especifica_mision`. Si se excede el timeout, la tarea debe marcarse como `FALLIDA_TEMPORALMENTE` para que se pueda reintentar o investigar.


### Lluvias de ideas

*Todas las ideas previas en esta sección han sido integradas en la hoja de ruta principal. Esta sección está lista para nuevas ideas pendientes de análisis y priorización.*

---
Este documento debe ser la guía principal para el desarrollo y refactorización de Misión Orion.
---

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