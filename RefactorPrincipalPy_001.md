# Misión: RefactorPrincipalPy_001

**Metadatos de la Misión:**
- **Nombre Clave:** RefactorPrincipalPy_001
- **Archivo Principal:** principal.py
- **Archivos de Contexto (Generación):** Ninguno
- **Archivos de Contexto (Ejecución):** Ninguno
- **Razón (Paso 1.1):** El archivo 'principal.py' necesita refactorización principalmente por dos razones: 

1.  **Violación del Principio de Responsabilidad Única (SRP) y Complejidad de Función:** La función `paso2_ejecutar_tarea_mision` es excesivamente larga y compleja. Realiza múltiples responsabilidades, incluyendo la preparación del contexto, la interacción con la IA, la aplicación de cambios de código, la gestión de operaciones Git y la actualización del estado de la misión y el historial. Esto dificulta su lectura, mantenimiento y prueba. Debería dividirse en funciones más pequeñas y con responsabilidades más claras (ej. `preparar_contexto_tarea`, `ejecutar_ia_tarea`, `aplicar_cambios_propuestos`, `actualizar_estado_tarea_git`).

2.  **Duplicación de Código (DRY):** Existe una sección de lógica de 'VALIDACIÓN GRANULAR' idéntica y extensa duplicada en las funciones `_intentarCrearMisionDesdeTodoMD` y `_intentarCrearMisionDesdeSeleccionArchivo`. Esta lógica de validación de la estructura de la misión debería extraerse a una función auxiliar compartida, posiblemente en el módulo `manejadorMision` o un nuevo módulo de utilidades de validación.

Adicionalmente, la función `seleccionar_archivo_mas_antiguo` podría beneficiarse de una división para separar la lógica de listado/filtrado de archivos de la lógica de selección y actualización del registro. No se necesita contexto adicional de otros archivos, ya que las mejoras propuestas son de organización interna y eliminación de duplicidades dentro del propio archivo 'principal.py'.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea SRP-P2-CtxPrep: Extraer Preparacion Contexto en paso2_ejecutar_tarea_mision
- **ID:** SRP-P2-CtxPrep
- **Estado:** PENDIENTE
- **Descripción:** Extraer la lógica de limpieza y validación de rutas de archivo, así como la lectura y preparación de los `bloques_codigo_input_para_ia` de la función `paso2_ejecutar_tarea_mision` a una nueva función auxiliar, por ejemplo, `_preparar_contexto_para_ia_tarea`. Esta nueva función debería encapsular la lógica de `limpiar_lista_rutas` (ya sea moviéndola como función top-level o anidándola dentro de la nueva función extraída) y retornar el `bloques_codigo_input_para_ia` y el `contexto_general_archivos_str` junto con sus tokens.
- **Archivos Implicados Específicos:** Ninguno
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso2_ejecutar_tarea_mision`
    - **Línea Inicio:** 362
    - **Línea Fin:** 466
---
### Tarea DRY-Validation: Centralizar Validacion Granular de Mision
- **ID:** DRY-Validation
- **Estado:** PENDIENTE
- **Descripción:** Extraer la lógica de 'VALIDACIÓN GRANULAR' presente de forma idéntica en las funciones `_intentarCrearMisionDesdeTodoMD` y `_intentarCrearMisionDesdeSeleccionArchivo` a una nueva función auxiliar compartida, por ejemplo, `manejadorMision.validar_estructura_mision_granular(contenido_markdown_mision)`. Esta función debería devolver un booleano indicando el éxito de la validación y, opcionalmente, detalles del error. Luego, reemplazar el código duplicado en ambas funciones con llamadas a esta nueva función. La nueva función debe ser implementada en el módulo `nucleo/manejadorMision.py`.
- **Archivos Implicados Específicos:** nucleo/manejadorMision.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `_intentarCrearMisionDesdeTodoMD`
    - **Línea Inicio:** 707
    - **Línea Fin:** 789
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `_intentarCrearMisionDesdeSeleccionArchivo`
    - **Línea Inicio:** 841
    - **Línea Fin:** 923
---
### Tarea SRP-SelFile: Dividir Logica Seleccion Archivo Mas Antiguo
- **ID:** SRP-SelFile
- **Estado:** PENDIENTE
- **Descripción:** Dividir la función `seleccionar_archivo_mas_antiguo` en dos funciones: una para listar y filtrar archivos del proyecto (ej. `_listar_archivos_proyecto_relativos`) y otra para seleccionar el archivo más antiguo basado en el registro y actualizar dicho registro (ej. `_seleccionar_y_registrar_archivo`). La función original `seleccionar_archivo_mas_antiguo` debería orquestar estas dos nuevas funciones.
- **Archivos Implicados Específicos:** Ninguno
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `seleccionar_archivo_mas_antiguo`
    - **Línea Inicio:** 93
    - **Línea Fin:** 143
