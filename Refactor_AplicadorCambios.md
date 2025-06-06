# Misión: Refactor_AplicadorCambios

**Metadatos de la Misión:**
- **Nombre Clave:** Refactor_AplicadorCambios
- **Archivo Principal:** nucleo/aplicadorCambios.py
- **Archivos de Contexto (Generación):** principal.py, nucleo/analizadorCodigo.py, nucleo/manejadorMision.py
- **Archivos de Contexto (Ejecución):** principal.py, nucleo/analizadorCodigo.py, nucleo/manejadorMision.py
- **Razón (Paso 1.1):** El archivo 'aplicadorCambios.py' necesita refactorización principalmente por la alta duplicación de código entre las funciones `aplicarCambiosSobrescrituraV1noUse` y `aplicarCambiosSobrescrituraV2`. La lógica para 'eliminar_archivo' y 'crear_directorio', así como el procesamiento general de archivos (lectura, escritura, diffing, manejo de directorios padre), es casi idéntica en ambas. Esto viola el principio DRY (Don't Repeat Yourself) y dificulta el mantenimiento.

Además, la función `aplicarCambiosGranulares` es bastante extensa y maneja múltiples tipos de operaciones con una lógica condicional anidada. Se beneficiaría de la extracción de la lógica específica de cada tipo de operación (REEMPLAZAR, AGREGAR, ELIMINAR) en funciones auxiliares más pequeñas para mejorar la claridad y la mantenibilidad (SRP - Single Responsibility Principle).

La función `_validar_y_normalizar_ruta` está bien implementada y es crucial para la seguridad, previniendo ataques de path traversal.

Se necesita contexto adicional para:
- **`principal.py`**: Para verificar si `aplicarCambiosSobrescrituraV1noUse` es realmente 'no usada' y si puede ser eliminada de forma segura o si su lógica debe ser fusionada con `V2` de manera más inteligente.
- **`nucleo/analizadorCodigo.py`**: Este módulo probablemente genera la estructura de datos que `aplicarCambiosGranulares` consume. Entender cómo se generan las 'modificaciones' y los 'archivos_con_contenido' es vital para asegurar que cualquier refactorización no rompa el contrato de la API interna.
- **`nucleo/manejadorMision.py`**: Podría ser el orquestador que decide cuándo y cómo se llaman estas funciones de aplicación de cambios, lo que daría una perspectiva sobre el flujo de trabajo general y la interacción entre los diferentes tipos de aplicación de cambios.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea RF-AC-001: Eliminar función obsoleta aplicarCambiosSobrescrituraV1noUse
- **ID:** RF-AC-001
- **Estado:** PENDIENTE
- **Descripción:** La función `aplicarCambiosSobrescrituraV1noUse` es obsoleta y no es utilizada por el flujo principal del agente (confirmado en `principal.py`). Eliminar completamente esta función para reducir la base de código y mejorar la claridad.
- **Archivos Implicados Específicos:** Ninguno
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `aplicarCambiosSobrescrituraV1noUse`
    - **Línea Inicio:** 52
    - **Línea Fin:** 205
---
### Tarea RF-AC-002: Extraer lógica de gestión de archivos/directorios en aplicarCambiosSobrescrituraV2
- **ID:** RF-AC-002
- **Estado:** PENDIENTE
- **Descripción:** La función `aplicarCambiosSobrescrituraV2` contiene lógica para `eliminar_archivo` y `crear_directorio` directamente. Extraer esta lógica en funciones auxiliares privadas (ej. `_manejar_operacion_archivo_directorio`) para mejorar la modularidad y reducir la complejidad de la función principal.
- **Archivos Implicados Específicos:** Ninguno
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `eliminar_archivo` block within `aplicarCambiosSobrescrituraV2`
    - **Línea Inicio:** 216
    - **Línea Fin:** 258
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `crear_directorio` block within `aplicarCambiosSobrescrituraV2`
    - **Línea Inicio:** 260
    - **Línea Fin:** 284
---
### Tarea RF-AC-003: Modularizar aplicarCambiosGranulares por tipo de operación
- **ID:** RF-AC-003
- **Estado:** PENDIENTE
- **Descripción:** La función `aplicarCambiosGranulares` es extensa y maneja la lógica de `REEMPLAZAR_BLOQUE`, `AGREGAR_BLOQUE` y `ELIMINAR_BLOQUE` directamente. Refactorizar extrayendo la lógica específica de cada tipo de operación en funciones auxiliares privadas (ej. `_aplicar_reemplazo_bloque`, `_aplicar_adicion_bloque`, `_aplicar_eliminacion_bloque`) para adherirse al Principio de Responsabilidad Única (SRP) y mejorar la legibilidad.
- **Archivos Implicados Específicos:** Ninguno
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `REEMPLAZAR_BLOQUE` logic within `aplicarCambiosGranulares`
    - **Línea Inicio:** 434
    - **Línea Fin:** 469
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `AGREGAR_BLOQUE` logic within `aplicarCambiosGranulares`
    - **Línea Inicio:** 471
    - **Línea Fin:** 496
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `ELIMINAR_BLOQUE` logic within `aplicarCambiosGranulares`
    - **Línea Inicio:** 498
    - **Línea Fin:** 523
