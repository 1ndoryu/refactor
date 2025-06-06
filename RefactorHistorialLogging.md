# Misión: RefactorHistorialLogging

**Metadatos de la Misión:**
- **Nombre Clave:** RefactorHistorialLogging
- **Archivo Principal:** nucleo/manejadorHistorial.py
- **Archivos de Contexto (Generación):** nucleo/manejadorMision.py, nucleo/analizadorCodigo.py, principal.py
- **Archivos de Contexto (Ejecución):** nucleo/manejadorMision.py, nucleo/analizadorCodigo.py, principal.py
- **Razón (Paso 1.1):** El archivo `manejadorHistorial.py` necesita refactorización por varias razones clave:

1.  **Formato de Historial Personalizado y Frágil**: Las funciones `cargarHistorial` y `guardarHistorial` utilizan un formato de texto personalizado con un delimitador `--- END ENTRY ---`. Esto es propenso a errores si el delimitador aparece dentro de una entrada y hace que el parsing sea más complejo de lo necesario. Se recomienda encarecidamente cambiar el almacenamiento del historial a un formato estructurado como JSON (una entrada JSON por línea o un array JSON completo). Esto simplificaría drásticamente `cargarHistorial` y `guardarHistorial` usando `json.loads` y `json.dumps`, mejoraría la robustez, la mantenibilidad y la extensibilidad.

2.  **Violación del SRP en `guardarHistorial`**: La función `guardarHistorial` contiene lógica de filtrado específica (`if "[[ERROR_PASO1]]" in entrada: ... pass`). Esta es una regla de negocio temporal (como indica el comentario `**TEMPORALMENTE**`) que no debería residir en una función genérica de gestión de historial. La responsabilidad de `guardarHistorial` debería ser simplemente escribir el historial proporcionado. El filtrado de entradas debería realizarse *antes* de llamar a `guardarHistorial`, por la parte del código que conoce y maneja el significado de `[[ERROR_PASO1]]`.

3.  **Consistencia de Logging**: Se utiliza `logging.getLogger(__name__)` pero luego se mezclan llamadas a `logging.info` y `logging.error` directamente en lugar de usar `log.info` y `log.error`. Es una mejora menor pero contribuye a la consistencia.

**Necesidad de Contexto Adicional**:
Se necesita contexto adicional para entender cómo se generan las entradas de historial y cómo se consume el historial. Esto es crucial para:
*   **Transición a JSON**: Entender cómo se construyen los objetos `decision`, `result_details`, `verification_details` y `error_message` que se pasan a `formatearEntradaHistorial` permitirá diseñar la nueva estructura JSON para el historial de manera óptima.
*   **Manejo de `[[ERROR_PASO1]]`**: Determinar dónde se origina este marcador y quién es responsable de decidir si una entrada debe ser guardada o no. Esto ayudará a mover la lógica de filtrado al lugar apropiado.

Los archivos sugeridos (`manejadorMision.py`, `analizadorCodigo.py`, `principal.py`) probablemente orquestan el flujo de trabajo, generan los datos de decisión y resultado, y son los puntos donde se llama a `manejadorHistorial`.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea RFL-001: Estandarizar llamadas de Logging en manejadorHistorial.py
- **ID:** RFL-001
- **Estado:** SALTADA
- **Descripción:** Modificar todas las llamadas a `logging.info`, `logging.error` y `logging.warning` en `nucleo/manejadorHistorial.py` para usar la instancia `log` predefinida (`log.info`, `log.error`, `log.warning`) y asegurar la consistencia del logging.
- **Archivos Implicados Específicos:** nucleo/manejadorHistorial.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `logging.info call (L12)`
    - **Línea Inicio:** 12
    - **Línea Fin:** 12
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `logging.error call (L18)`
    - **Línea Inicio:** 18
    - **Línea Fin:** 18
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `logging.info call (L28)`
    - **Línea Inicio:** 28
    - **Línea Fin:** 28
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `logging.warning call (L35)`
    - **Línea Inicio:** 35
    - **Línea Fin:** 35
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `logging.info call (L40)`
    - **Línea Inicio:** 40
    - **Línea Fin:** 40
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `logging.error call (L43)`
    - **Línea Inicio:** 43
    - **Línea Fin:** 43
---
### Tarea RFL-002: Refactorizar formatearEntradaHistorial para retornar un diccionario
- **ID:** RFL-002
- **Estado:** PENDIENTE
- **Descripción:** Modificar la función `formatearEntradaHistorial` en `nucleo/manejadorHistorial.py` para que, en lugar de construir y retornar una cadena de texto formateada, construya y retorne un diccionario de Python. Este diccionario debe contener las claves `timestamp`, `outcome`, `decision`, `result_details`, `verification_details` y `error_message`, con sus respectivos valores. La serialización a JSON se realizará en la función `guardarHistorial`.
- **Archivos Implicados Específicos:** nucleo/manejadorHistorial.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `formatearEntradaHistorial`
    - **Línea Inicio:** 46
    - **Línea Fin:** 66
---
### Tarea RFL-003: Migrar guardarHistorial a formato JSON y eliminar violación de SRP
- **ID:** RFL-003
- **Estado:** PENDIENTE
- **Descripción:** Actualizar la función `guardarHistorial` en `nucleo/manejadorHistorial.py` para que espere una lista de diccionarios de Python (generados por `formatearEntradaHistorial`). Cada diccionario debe ser serializado a una cadena JSON y escrito en una nueva línea en el archivo de historial. El delimitador `--- END ENTRY ---` y la lógica de filtrado de `[[ERROR_PASO1]]` deben ser eliminados de esta función, ya que violan el Principio de Responsabilidad Única (SRP).
- **Archivos Implicados Específicos:** nucleo/manejadorHistorial.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `guardarHistorial`
    - **Línea Inicio:** 23
    - **Línea Fin:** 43
---
### Tarea RFL-004: Migrar cargarHistorial para leer entradas JSON
- **ID:** RFL-004
- **Estado:** PENDIENTE
- **Descripción:** Modificar la función `cargarHistorial` en `nucleo/manejadorHistorial.py` para que lea el archivo de historial, esperando que cada línea sea una cadena JSON que representa una entrada. Debe parsear cada línea JSON en un diccionario de Python y devolver una lista de estos diccionarios. La lógica de parsing basada en el delimitador `--- END ENTRY ---` debe ser eliminada.
- **Archivos Implicados Específicos:** nucleo/manejadorHistorial.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `nucleo/manejadorHistorial.py`
    - **Nombre Bloque:** `cargarHistorial`
    - **Línea Inicio:** 10
    - **Línea Fin:** 21
---
### Tarea RFL-005: Implementar filtrado de [[ERROR_PASO1]] en principal.py
- **ID:** RFL-005
- **Estado:** PENDIENTE
- **Descripción:** Localizar todas las llamadas a `manejadorHistorial.guardarHistorial` en `principal.py`. Antes de añadir una nueva entrada de historial a la lista que se pasa a `guardarHistorial`, se debe verificar si el diccionario de la nueva entrada (obtenido de `formatearEntradaHistorial`) contiene `[[ERROR_PASO1]]` en su campo `error_message`. Si lo contiene, la entrada no debe ser añadida a la lista, moviendo así la lógica de filtrado fuera de `manejadorHistorial.py`.
- **Archivos Implicados Específicos:** principal.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso1_1_seleccion_y_decision_inicial`
    - **Línea Inicio:** 317
    - **Línea Fin:** 335
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso1_2_generar_mision` (primera llamada)
    - **Línea Inicio:** 353
    - **Línea Fin:** 356
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso1_2_generar_mision` (segunda llamada)
    - **Línea Inicio:** 376
    - **Línea Fin:** 379
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso2_ejecutar_tarea_mision` (primera llamada)
    - **Línea Inicio:** 410
    - **Línea Fin:** 413
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso2_ejecutar_tarea_mision` (segunda llamada)
    - **Línea Inicio:** 431
    - **Línea Fin:** 434
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso2_ejecutar_tarea_mision` (tercera llamada)
    - **Línea Inicio:** 457
    - **Línea Fin:** 460
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso2_ejecutar_tarea_mision` (cuarta llamada)
    - **Línea Inicio:** 465
    - **Línea Fin:** 468
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso2_ejecutar_tarea_mision` (quinta llamada)
    - **Línea Inicio:** 486
    - **Línea Fin:** 489
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `paso2_ejecutar_tarea_mision` (sexta llamada)
    - **Línea Inicio:** 514
    - **Línea Fin:** 517
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `_intentarCrearMisionDesdeTodoMD` (primera llamada)
    - **Línea Inicio:** 698
    - **Línea Fin:** 701
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `_intentarCrearMisionDesdeTodoMD` (segunda llamada)
    - **Línea Inicio:** 743
    - **Línea Fin:** 748
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `_intentarCrearMisionDesdeTodoMD` (tercera llamada)
    - **Línea Inicio:** 780
    - **Línea Fin:** 785
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `_intentarCrearMisionDesdeTodoMD` (cuarta llamada)
    - **Línea Inicio:** 790
    - **Línea Fin:** 793
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `_intentarCrearMisionDesdeSeleccionArchivo` (primera llamada)
    - **Línea Inicio:** 846
    - **Línea Fin:** 851
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `_intentarCrearMisionDesdeSeleccionArchivo` (segunda llamada)
    - **Línea Inicio:** 870
    - **Línea Fin:** 875