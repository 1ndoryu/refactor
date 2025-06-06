# Misión: RefactorAplicadorCambios

**Metadatos de la Misión:**
- **Nombre Clave:** RefactorAplicadorCambios
- **Archivo Principal:** nucleo/aplicadorCambios.py
- **Archivos de Contexto (Generación):** nucleo/test_aplicarCambios.py, nucleo/analizadorCodigo.py, nucleo/manejadorMision.py
- **Archivos de Contexto (Ejecución):** nucleo/test_aplicarCambios.py, nucleo/analizadorCodigo.py, nucleo/manejadorMision.py
- **Razón (Paso 1.1):** El archivo 'aplicadorCambios.py' necesita refactorización principalmente por la duplicación de código y la violación del Principio de Responsabilidad Única (SRP).

**Razones para la refactorización:**
1.  **Duplicación de Código (DRY):** Las funciones `aplicarCambiosSobrescrituraV1noUse` y `aplicarCambiosSobrescrituraV2` son casi idénticas. Dado que V1 está marcada como 'noUse', debería eliminarse o fusionarse de forma condicional si hay alguna razón para mantenerla. La lógica para `eliminar_archivo` y `crear_directorio` también se duplica entre ellas y podría extraerse.
2.  **Violación del SRP:** Las funciones `aplicarCambiosSobrescrituraV2` y `aplicarCambiosGranulares` son demasiado extensas y manejan múltiples responsabilidades: validación de rutas, creación/eliminación de directorios, procesamiento de contenido (conversión JSON, corrección Mojibake), lectura/escritura de archivos y la lógica específica de cada tipo de cambio. Esto las hace difíciles de leer, probar y mantener.
3.  **Complejidad:** La longitud y el número de responsabilidades por función aumentan la complejidad cognitiva.

**Propuesta de refactorización:**
*   Eliminar `aplicarCambiosSobrescrituraV1noUse`.
*   Extraer funciones auxiliares para operaciones comunes como: `_manejar_eliminacion_archivo`, `_manejar_creacion_directorio`, `_procesar_contenido_ia` (para JSON, Mojibake, etc.).
*   Descomponer `aplicarCambiosSobrescrituraV2` y `aplicarCambiosGranulares` en funciones más pequeñas y enfocadas, cada una con una única responsabilidad (ej., una función para aplicar un reemplazo de bloque, otra para agregar, otra para eliminar).

**Necesidad de contexto adicional:**
Se necesita contexto adicional para asegurar que la refactorización no rompa la funcionalidad existente y para entender mejor las interacciones:
*   `nucleo/test_aplicarCambios.py`: Es crucial para garantizar que las refactorizaciones no introduzcan regresiones. Las pruebas existentes servirán como una red de seguridad.
*   `nucleo/analizadorCodigo.py`: Probablemente genera las estructuras de datos de entrada (`archivos_con_contenido`, `respuesta_ia_modificaciones`). Entender cómo se construyen estas entradas es vital para asegurar la compatibilidad de las interfaces después de la refactorización.
*   `nucleo/manejadorMision.py`: Este módulo podría ser el orquestador principal que invoca las funciones de `aplicadorCambios.py`. Comprender cómo se utilizan estas funciones en el flujo general de la aplicación puede ayudar a definir las interfaces de las funciones refactorizadas.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea TSK-AC-001: Eliminar `aplicarCambiosSobrescrituraV1noUse` y sus referencias
- **ID:** TSK-AC-001
- **Estado:** SALTADA
- **Descripción:** Eliminar la función `aplicarCambiosSobrescrituraV1noUse` de `nucleo/aplicadorCambios.py` ya que está marcada como 'noUse' y es una duplicación de `aplicarCambiosSobrescrituraV2`. Además, eliminar o adaptar las llamadas y pruebas a esta función en `nucleo/test_aplicarCambios.py` para asegurar que no se introduzcan regresiones.
- **Archivos Implicados Específicos:** nucleo/aplicadorCambios.py, nucleo/test_aplicarCambios.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `aplicarCambiosSobrescrituraV1noUse`
    - **Línea Inicio:** 62
    - **Línea Fin:** 181
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_01_saltos_de_linea_escapados` (referencia V1)
    - **Línea Inicio:** 45
    - **Línea Fin:** 50
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_02_unicode_escapes` (referencia V1)
    - **Línea Inicio:** 52
    - **Línea Fin:** 57
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_05_mixto_mojibake_y_escapes` (referencia V1)
    - **Línea Inicio:** 70
    - **Línea Fin:** 75
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_08_comillas_y_barras_escapadas_json` (referencia V1)
    - **Línea Inicio:** 88
    - **Línea Fin:** 93
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_11_php_string_literal_con_barra_n` (referencia V1)
    - **Línea Inicio:** 105
    - **Línea Fin:** 109
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_12_php_multilinea_echo_con_escapes` (referencia V1)
    - **Línea Inicio:** 128
    - **Línea Fin:** 137
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_13_entrada_ia_con_doble_barra_n` (referencia V1)
    - **Línea Inicio:** 146
    - **Línea Fin:** 150
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_15_control_chars_como_literales_escapados` (referencia V1)
    - **Línea Inicio:** 168
    - **Línea Fin:** 172
  - **Archivo:** `nucleo/test_aplicarCambios.py`
    - **Nombre Bloque:** `test_16_php_backslash_en_array_literal` (referencia V1)
    - **Línea Inicio:** 180
    - **Línea Fin:** 184
---
### Tarea TSK-AC-002: Extraer funciones de manejo de archivos en `aplicadorCambios.py`
- **ID:** TSK-AC-002
- **Estado:** SALTADA
- **Descripción:** Extraer la lógica duplicada de eliminación de archivos y creación de directorios de `aplicarCambiosSobrescrituraV2` en dos nuevas funciones auxiliares privadas en `nucleo/aplicadorCambios.py`: `_manejar_eliminacion_archivo(target_abs: str, target_rel: str)` y `_manejar_creacion_directorio(target_abs: str, target_rel: str)`. Ambas funciones deben incluir la validación de ruta, comprobación de existencia y manejo de errores, así como la creación del archivo `.gitkeep` en el caso de directorios. Reemplazar el código original en `aplicarCambiosSobrescrituraV2` con llamadas a estas nuevas funciones.
- **Archivos Implicados Específicos:** Ninguno
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `eliminar_archivo_logic_in_V2`
    - **Línea Inicio:** 195
    - **Línea Fin:** 219
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `crear_directorio_logic_in_V2`
    - **Línea Inicio:** 227
    - **Línea Fin:** 263
---
### Tarea TSK-AC-003: Extraer función de procesamiento de contenido en `aplicadorCambios.py`
- **ID:** TSK-AC-003
- **Estado:** SALTADA
- **Descripción:** Crear una nueva función auxiliar privada `_procesar_contenido_ia(contenido_raw: Any) -> str` en `nucleo/aplicadorCambios.py`. Esta función debe encapsular la lógica de conversión de contenido no-string (ej. dicts) a JSON string y la corrección de secuencias Mojibake. `aplicarCambiosSobrescrituraV2` debe llamar a esta nueva función para obtener el contenido final procesado antes de escribirlo en el disco.
- **Archivos Implicados Específicos:** Ninguno
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `contenido_ia_str_conversion`
    - **Línea Inicio:** 279
    - **Línea Fin:** 287
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `mojibake_correction`
    - **Línea Inicio:** 298
    - **Línea Fin:** 310
---
### Tarea TSK-AC-004: Descomponer `aplicarCambiosGranulares` en funciones específicas
- **ID:** TSK-AC-004
- **Estado:** FALLIDA_TEMPORALMENTE
- **Descripción:** Descomponer la función `aplicarCambiosGranulares` en `nucleo/aplicadorCambios.py` extrayendo la lógica para cada tipo de operación (`REEMPLAZAR_BLOQUE`, `AGREGAR_BLOQUE`, `ELIMINAR_BLOQUE`) en funciones privadas dedicadas, por ejemplo: `_aplicar_reemplazo_bloque(lineas_modificadas, operacion)`, `_aplicar_agregar_bloque(lineas_modificadas, operacion)`, `_aplicar_eliminar_bloque(lineas_modificadas, operacion)`. La función principal `aplicarCambiosGranulares` debe simplificarse para orquestar las llamadas a estas nuevas funciones basadas en el `tipo_operacion`.
- **Archivos Implicados Específicos:** Ninguno
- **Intentos:** 1
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `REEMPLAZAR_BLOQUE_logic`
    - **Línea Inicio:** 431
    - **Línea Fin:** 460
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `AGREGAR_BLOQUE_logic`
    - **Línea Inicio:** 462
    - **Línea Fin:** 482
  - **Archivo:** `nucleo/aplicadorCambios.py`
    - **Nombre Bloque:** `ELIMINAR_BLOQUE_logic`
    - **Línea Inicio:** 484
    - **Línea Fin:** 507