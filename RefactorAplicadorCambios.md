# Misión: RefactorAplicadorCambios

**Metadatos de la Misión:**
- **Nombre Clave:** RefactorAplicadorCambios
- **Archivo Principal:** nucleo/aplicadorCambios.py
- **Archivos de Contexto (Generación):** principal.py, nucleo/manejadorMision.py, nucleo/analizadorCodigo.py, nucleo/test_aplicarCambios.py
- **Archivos de Contexto (Ejecución):** nucleo/aplicadorCambios.py, principal.py, nucleo/manejadorMision.py, nucleo/analizadorCodigo.py, nucleo/test_aplicarCambios.py
- **Razón (Paso 1.1):** El archivo 'aplicadorCambios.py' necesita refactorización por varias razones clave. Primero, existe una duplicación significativa de código entre `aplicarCambiosSobrescrituraV1noUse` y `aplicarCambiosSobrescrituraV2`. Dado que V1 está marcada como 'noUse', debería eliminarse o consolidarse con V2, extrayendo la lógica común de manejo de archivos/directorios (creación, eliminación) en funciones auxiliares. Segundo, la función `aplicarCambiosGranulares` es bastante extensa y maneja múltiples tipos de operaciones (reemplazar, agregar, eliminar bloques) dentro de una única estructura condicional anidada. Esto viola el Principio de Responsabilidad Única (SRP) a nivel de función y dificulta la lectura y el mantenimiento. Se beneficiaría enormemente de la extracción de cada tipo de operación en funciones más pequeñas y dedicadas (ej., `_aplicar_reemplazo_bloque`, `_aplicar_adicion_bloque`, `_aplicar_eliminacion_bloque`). La lógica de manejo de saltos de línea para `lineas_nuevo_contenido` en `aplicarCambiosGranulares` también podría simplificarse. Finalmente, la constante `MOJIBAKE_REPLACEMENTS` y su comentario asociado podrían tener una ubicación o una explicación más clara si su uso es más amplio. Se necesita contexto adicional para confirmar si `aplicarCambiosSobrescrituraV1noUse` realmente no se utiliza en ninguna parte del proyecto, así como para entender cómo `aplicarCambiosSobrescrituraV2` y `aplicarCambiosGranulares` son invocadas y qué formatos de datos se esperan de `analizadorCodigo.py` (que probablemente genera las modificaciones). Los archivos de test (`test_aplicarCambios.py`) serían cruciales para asegurar que las refactorizaciones no introduzcan regresiones.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea TSK-APL-001: Extract File System Helpers and Consolidate Overwrite Functions
- **ID:** TSK-APL-001
- **Estado:** PENDIENTE
- **Descripción:** Refactorizar `nucleo/aplicadorCambios.py` extrayendo las operaciones comunes de manejo de archivos/directorios (`eliminar_archivo`, `crear_directorio`) de `aplicarCambiosSobrescrituraV1noUse` y `aplicarCambiosSobrescrituraV2` en funciones auxiliares privadas como `_manejar_creacion_directorio` y `_manejar_eliminacion_archivo_o_directorio`. Luego, eliminar `aplicarCambiosSobrescrituraV1noUse` completamente, ya que está marcada como 'noUse' y `aplicarCambiosSobrescrituraV2` se convertirá en la función canónica de sobrescritura. Asegurar que `aplicarCambiosSobrescrituraV2` procese correctamente el contenido generado por la IA (por ejemplo, maneje `\n` para saltos de línea y mojibake) sin reintroducir la decodificación `unicode_escape`, ya que `json.loads` ya maneja los escapes básicos. Actualizar `nucleo/test_aplicarCambios.py` para eliminar las pruebas de V1 y adaptar las pruebas existentes de V2 si es necesario.
- **Archivos Implicados Específicos:** nucleo/aplicadorCambios.py, nucleo/test_aplicarCambios.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `aplicarCambiosSobrescrituraV1noUse`
    - **Línea Inicio:** 49
    - **Línea Fin:** 142
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `aplicarCambiosSobrescrituraV2`
    - **Línea Inicio:** 145
    - **Línea Fin:** 240
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `_manejar_creacion_directorio`
    - **Línea Inicio:** 38
    - **Línea Fin:** 60
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `_manejar_eliminacion_archivo_o_directorio`
    - **Línea Inicio:** 62
    - **Línea Fin:** 80
---
### Tarea TSK-APL-002: Modularize AplicarCambiosGranulares
- **ID:** TSK-APL-002
- **Estado:** PENDIENTE
- **Descripción:** Refactorizar la función `aplicarCambiosGranulares` en `nucleo/aplicadorCambios.py` para cumplir con el Principio de Responsabilidad Única (SRP). Extraer la lógica de cada tipo de operación (`REEMPLAZAR_BLOQUE`, `AGREGAR_BLOQUE`, `ELIMINAR_BLOQUE`) en funciones auxiliares privadas separadas y dedicadas (por ejemplo, `_aplicar_reemplazo_bloque`, `_aplicar_adicion_bloque`, `_aplicar_eliminacion_bloque`). Cada función auxiliar debe recibir la lista actual de líneas y los datos específicos de la operación, devolviendo la lista de líneas modificada. Además, simplificar el manejo de saltos de línea para `lineas_nuevo_contenido` utilizando `splitlines(keepends=True)` en lugar de `split('\n')` y volver a añadir `\n'`, asumiendo que la cadena de entrada ya contiene caracteres de salto de línea reales después del parseo JSON. Actualizar los casos de prueba relevantes en `nucleo/test_aplicarCambios.py` para reflejar estos cambios estructurales.
- **Archivos Implicados Específicos:** nucleo/aplicadorCambios.py, nucleo/test_aplicarCambios.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `aplicarCambiosGranulares`
    - **Línea Inicio:** 242
    - **Línea Fin:** 458
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `_aplicar_reemplazo_bloque`
    - **Línea Inicio:** 250
    - **Línea Fin:** 300
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `_aplicar_adicion_bloque`
    - **Línea Inicio:** 302
    - **Línea Fin:** 330
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `_aplicar_eliminacion_bloque`
    - **Línea Inicio:** 332
    - **Línea Fin:** 360
---
### Tarea TSK-APL-003: Clarify and Apply Mojibake Replacements Consistently
- **ID:** TSK-APL-003
- **Estado:** PENDIENTE
- **Descripción:** Mejorar la constante `MOJIBAKE_REPLACEMENTS` en `nucleo/aplicadorCambios.py` añadiendo un comentario más detallado que explique su propósito: corregir problemas comunes de codificación de caracteres (mojibake) que puedan surgir en el texto generado por la IA *después* del parseo JSON estándar. Asegurar que esta lógica de corrección de mojibake se aplique consistentemente a todo el contenido generado por la IA que se escribe en los archivos, integrándola específicamente en la función `aplicarCambiosGranulares` (o sus nuevas funciones auxiliares) además de `aplicarCambiosSobrescrituraV2`.
- **Archivos Implicados Específicos:** nucleo/aplicadorCambios.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `MOJIBAKE_REPLACEMENTS`
    - **Línea Inicio:** 40
    - **Línea Fin:** 42
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `aplicarCambiosGranulares`
    - **Línea Inicio:** 242
    - **Línea Fin:** 458
