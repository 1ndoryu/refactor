# Misión: RefactorHistorialJSON

**Metadatos de la Misión:**
- **Nombre Clave:** RefactorHistorialJSON
- **Archivo Principal:** nucleo/manejadorHistorial.py
- **Archivos de Contexto (Generación):** nucleo/manejadorMision.py, nucleo/analizadorCodigo.py, nucleo/aplicadorCambios.py
- **Archivos de Contexto (Ejecución):** nucleo/manejadorHistorial.py, nucleo/manejadorMision.py, nucleo/analizadorCodigo.py, nucleo/aplicadorCambios.py
- **Razón (Paso 1.1):** El archivo necesita refactorización principalmente por la forma en que se manejan las entradas del historial. Actualmente, las entradas se almacenan como cadenas de texto multilínea con un delimitador (`--- END ENTRY ---`) y se filtran utilizando una 'cadena mágica' (`[[ERROR_PASO1]]`). Este enfoque es frágil y propenso a errores, ya que un cambio en el formato de la cadena o la aparición de la cadena mágica dentro de una entrada real podría romper la lógica de carga y guardado.

**Puntos clave para la refactorización:**
1.  **Estandarización del formato de datos:** La función `formatearEntradaHistorial` ya construye una estructura de datos compleja que se serializa en una cadena. Sería mucho más robusto almacenar las entradas del historial como objetos JSON (uno por línea o un array JSON completo) en lugar de cadenas de texto delimitadas. Esto permitiría una serialización/deserialización más fiable y un acceso programático más sencillo a los campos de cada entrada.
2.  **Manejo de errores/filtrado:** La cadena `[[ERROR_PASO1]]` para el filtrado es una 'magic string'. Si las entradas fueran JSON, se podría añadir un campo específico (ej. `"status": "ERROR_PASO1"`) que sería mucho más claro y robusto para el filtrado.
3.  **Consistencia de logging:** Se utiliza `logging.getLogger(__name__)` pero luego se llama directamente a `logging.info` y `logging.error`. Es mejor usar la instancia `log` creada (`log.info`, `log.error`).

**Necesidad de contexto adicional:**
Se necesita contexto adicional para entender cómo se generan y consumen estas entradas de historial. Esto es crucial para asegurar que el cambio a un formato JSON no rompa otras partes del sistema y para diseñar la estructura JSON óptima. Los archivos sugeridos son:
*   `nucleo/manejadorMision.py`: Probablemente el orquestador principal que llama a `formatearEntradaHistorial` y consume/genera las entradas del historial.
*   `nucleo/analizadorCodigo.py`: Podría estar relacionado con la generación de `decision` (Paso 1) y el origen del `[[ERROR_PASO1]]`.
*   `nucleo/aplicadorCambios.py`: Podría estar relacionado con `result_details` (Paso 2) y cómo se aplican los cambios.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea RH-LOG-001: Consistencia de Logging en manejadorHistorial.py
- **ID:** RH-LOG-001
- **Estado:** COMPLETADA
- **Descripción:** Reemplazar todas las llamadas directas a `logging.info` y `logging.error` en `nucleo/manejadorHistorial.py` por la instancia `log` ya definida (ej. `log.info`, `log.error`) para asegurar la consistencia en el uso del logger.
- **Archivos Implicados Específicos (Opcional):** nucleo/manejadorHistorial.py
- **Intentos:** 0
---
### Tarea RH-JSON-001: Convertir formatearEntradaHistorial a JSON
- **ID:** RH-JSON-001
- **Estado:** COMPLETADA
- **Descripción:** Modificar la función `formatearEntradaHistorial` en `nucleo/manejadorHistorial.py` para que devuelva un objeto JSON serializado como string. La estructura JSON debe incluir campos como `timestamp`, `outcome`, `decision` (objeto), `result_details` (objeto), `verification_details` (objeto), y `error_message`. Si `result_details` es un diccionario, debe ser incluido completo.
- **Archivos Implicados Específicos (Opcional):** nucleo/manejadorHistorial.py
- **Intentos:** 0
---
### Tarea RH-LOAD-001: Adaptar cargarHistorial para formato JSON
- **ID:** RH-LOAD-001
- **Estado:** COMPLETADA
- **Descripción:** Modificar la función `cargarHistorial` en `nucleo/manejadorHistorial.py` para que lea y parse las entradas del historial como objetos JSON, en lugar de cadenas de texto delimitadas por `--- END ENTRY ---`.
- **Archivos Implicados Específicos (Opcional):** nucleo/manejadorHistorial.py
- **Intentos:** 0
---
### Tarea RH-SAVE-001: Adaptar guardarHistorial para JSON y filtrado robusto
- **ID:** RH-SAVE-001
- **Estado:** COMPLETADA
- **Descripción:** Modificar la función `guardarHistorial` en `nucleo/manejadorHistorial.py` para que serialice y guarde las entradas del historial como objetos JSON (uno por línea). Reemplazar el filtrado de la 'cadena mágica' `[[ERROR_PASO1]]` por un campo JSON específico, por ejemplo, `"status": "ERROR_PASO1"`, y realizar el filtrado basándose en este campo.
- **Archivos Implicados Específicos (Opcional):** nucleo/manejadorHistorial.py
- **Intentos:** 0
---
### Tarea RH-INTEG-001: Actualizar usos del historial en archivos de contexto
- **ID:** RH-INTEG-001
- **Estado:** PENDIENTE
- **Descripción:** Revisar los archivos `nucleo/manejadorMision.py`, `nucleo/analizadorCodigo.py`, y `nucleo/aplicadorCambios.py` para identificar y actualizar las llamadas a `formatearEntradaHistorial` y cualquier otro uso de `cargarHistorial` o `guardarHistorial` para que sean compatibles con el nuevo formato de historial basado en JSON. Esto podría implicar ajustes en cómo se pasan los datos o cómo se interpretan los datos cargados.
- **Archivos Implicados Específicos (Opcional):** nucleo/manejadorMision.py, nucleo/analizadorCodigo.py, nucleo/aplicadorCambios.py, nucleo/manejadorHistorial.py
- **Intentos:** 0