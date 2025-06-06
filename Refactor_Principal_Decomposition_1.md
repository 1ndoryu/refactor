# Misión: Refactor_Principal_Decomposition_1

**Metadatos de la Misión:**
- **Nombre Clave:** Refactor_Principal_Decomposition_1
- **Archivo Principal:** principal.py
- **Archivos de Contexto (Generación):** config/settings.py, nucleo/analizadorCodigo.py, nucleo/aplicadorCambios.py, nucleo/manejadorGit.py, nucleo/manejadorMision.py
- **Archivos de Contexto (Ejecución):** config/settings.py, nucleo/analizadorCodigo.py, nucleo/aplicadorCambios.py, nucleo/manejadorGit.py, nucleo/manejadorMision.py
- **Razón (Paso 1.1):** El archivo 'principal.py' es un monolito que excede significativamente el principio de Responsabilidad Única (SRP). Actúa como un 'God Object' o 'God Function', orquestando toda la lógica del agente, incluyendo la gestión de tokens, el registro de archivos, la carga/guardado de estado de misión, la interacción con Git, la selección y análisis de código, la generación de misiones, la ejecución de tareas y la aplicación de cambios. Su gran tamaño (más de 600 líneas) y la complejidad de sus funciones anidadas ('ejecutarFaseDelAgente', '_procesarMisionExistente', '_crearNuevaMision', y las funciones 'pasoX_') lo hacen difícil de leer, entender, probar y mantener. 

La refactorización se centraría en:
1.  **Descomposición en Clases/Módulos:** Extraer funcionalidades relacionadas en clases o módulos dedicados (ej. un 'Agente' principal que coordine, un 'GestorDeMisiones' para las funciones 'pasoX_', un 'LimitadorDeTokens', un 'GestorDeEstado' para persistencia, etc.).
2.  **Centralización de Estado:** Encapsular variables globales como 'token_usage_window' y el registro de archivos dentro de objetos de clase para un manejo más limpio del estado.
3.  **Reducir Duplicidad:** La lógica de validación granular de misiones y las operaciones repetitivas de Git podrían ser métodos o funciones auxiliares más genéricas.

Se necesita contexto adicional de los archivos sugeridos para comprender las interfaces y dependencias exactas de las funciones que se moverían o refactorizarían. Esto aseguraría que la descomposición modular sea coherente con la arquitectura existente y que las nuevas responsabilidades se deleguen correctamente sin romper la funcionalidad actual.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea RF-PRN-001: Extraer Gestión de Tokens a nucleo/gestionTokens.py
- **ID:** RF-PRN-001
- **Estado:** SALTADA
- **Descripción:** Mover la variable global `token_usage_window` y las funciones `gestionar_limite_tokens` y `registrar_tokens_usados` a un nuevo módulo `nucleo/gestionTokens.py`. Actualizar las importaciones y llamadas en `principal.py` para usar este nuevo módulo. El nuevo módulo debe importar `datetime`, `timedelta` y `settings`.
- **Archivos Implicados Específicos:** nucleo/gestionTokens.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `token_usage_window`
    - **Línea Inicio:** 32
    - **Línea Fin:** 32
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `gestionar_limite_tokens`
    - **Línea Inicio:** 51
    - **Línea Fin:** 76
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `registrar_tokens_usados`
    - **Línea Inicio:** 79
    - **Línea Fin:** 85
  - **Archivo:** `nucleo/gestionTokens.py`
    - **Nombre Bloque:** `ContenidoInicial`
    - **Línea Inicio:** 1
    - **Línea Fin:** 1
---
### Tarea RF-PRN-002: Extraer Registro de Archivos Analizados a nucleo/registroAnalisis.py
- **ID:** RF-PRN-002
- **Estado:** SALTADA
- **Descripción:** Mover la variable global `REGISTRO_ARCHIVOS_ANALIZADOS_PATH` y las funciones `cargar_registro_archivos`, `guardar_registro_archivos`, `seleccionar_archivo_mas_antiguo` a un nuevo módulo `nucleo/registroAnalisis.py`. Actualizar las importaciones y llamadas en `principal.py` para usar este nuevo módulo. El nuevo módulo debe importar `os`, `json`, `datetime`, `analizadorCodigo`, y `settings`.
- **Archivos Implicados Específicos:** nucleo/registroAnalisis.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `REGISTRO_ARCHIVOS_ANALIZADOS_PATH`
    - **Línea Inicio:** 28
    - **Línea Fin:** 30
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `cargar_registro_archivos`
    - **Línea Inicio:** 88
    - **Línea Fin:** 109
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `guardar_registro_archivos`
    - **Línea Inicio:** 112
    - **Línea Fin:** 121
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `seleccionar_archivo_mas_antiguo`
    - **Línea Inicio:** 124
    - **Línea Fin:** 162
  - **Archivo:** `nucleo/registroAnalisis.py`
    - **Nombre Bloque:** `ContenidoInicial`
    - **Línea Inicio:** 1
    - **Línea Fin:** 1
---
### Tarea RF-PRN-003: Extraer Gestión de Estado de Misión a nucleo/gestionMisionEstado.py
- **ID:** RF-PRN-003
- **Estado:** SALTADA
- **Descripción:** Mover la variable global `ACTIVE_MISSION_STATE_FILE` y las funciones `cargar_estado_mision_activa`, `guardar_estado_mision_activa`, `limpiar_estado_mision_activa` a un nuevo módulo `nucleo/gestionMisionEstado.py`. Actualizar las importaciones y llamadas en `principal.py` para usar este nuevo módulo. El nuevo módulo debe importar `os`, `logging`, `datetime`, `manejadorMision`, y `settings`.
- **Archivos Implicados Específicos:** nucleo/gestionMisionEstado.py
- **Intentos:** 0
- **Bloques de Código Objetivo:**
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `ACTIVE_MISSION_STATE_FILE`
    - **Línea Inicio:** 33
    - **Línea Fin:** 35
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `cargar_estado_mision_activa`
    - **Línea Inicio:** 165
    - **Línea Fin:** 188
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `guardar_estado_mision_activa`
    - **Línea Inicio:** 191
    - **Línea Fin:** 200
  - **Archivo:** `principal.py`
    - **Nombre Bloque:** `limpiar_estado_mision_activa`
    - **Línea Inicio:** 203
    - **Línea Fin:** 212
  - **Archivo:** `nucleo/gestionMisionEstado.py`
    - **Nombre Bloque:** `ContenidoInicial`
    - **Línea Inicio:** 1
    - **Línea Fin:** 1