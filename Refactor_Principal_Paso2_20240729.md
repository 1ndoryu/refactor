# Misión: Refactor_Principal_Paso2_20240729

**Metadatos de la Misión:**
- **Nombre Clave:** Refactor_Principal_Paso2_20240729
- **Archivo Principal:** principal.py
- **Archivos de Contexto (Generación):** config/settings.py, nucleo/analizadorCodigo.py, nucleo/manejadorMision.py, nucleo/manejadorGit.py
- **Archivos de Contexto (Ejecución):** config/settings.py, nucleo/analizadorCodigo.py, nucleo/manejadorMision.py, nucleo/manejadorGit.py, nucleo/utilidades.py
- **Razón (Paso 1.1):** El archivo 'principal.py' actúa como el orquestador central del agente adaptativo, coordinando múltiples módulos y flujos de trabajo. Si bien se han realizado mejoras para modularizar la lógica de creación y procesamiento de misiones (con funciones como `_procesarMisionExistente`, `_crearNuevaMision`, etc.), la función `paso2_ejecutar_tarea_mision` sigue siendo excesivamente larga y compleja. Contiene lógica para la validación de rutas, la interacción con la IA, la aplicación de cambios y la actualización del estado de la misión, lo que viola el Principio de Responsabilidad Única (SRP).

Además, se observa una función auxiliar (`limpiar_lista_rutas`) definida localmente dentro de `paso2_ejecutar_tarea_mision`, lo cual es una clara oportunidad para extraerla a un módulo de utilidades o a un lugar más apropiado para evitar la duplicación de código (DRY).

La refactorización se centraría en:
1.  **Descomponer `paso2_ejecutar_tarea_mision`**: Separar la preparación del contexto, la ejecución de la tarea por la IA, la aplicación de cambios y la gestión del estado de la misión en funciones más pequeñas y con responsabilidades claras.
2.  **Extraer `limpiar_lista_rutas`**: Mover esta función a un módulo de utilidades compartidas (ej. `nucleo/utilidades.py`) para que pueda ser reutilizada y mantenida centralmente.
3.  **Abstracción de operaciones Git repetitivas**: Algunas secuencias de operaciones Git (cambio de rama, commit, push) se repiten en diferentes 'pasos'. Podrían ser encapsuladas en funciones de ayuda en `manejadorGit` o en un nuevo módulo de flujo de trabajo.

Se necesita contexto adicional de los archivos sugeridos para entender las dependencias y responsabilidades de los módulos subyacentes (`settings`, `analizadorCodigo`, `manejadorMision`, `manejadorGit`) y así realizar una refactorización que mejore la coherencia, la mantenibilidad y la claridad del código sin romper la funcionalidad existente.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea RF-P2-001: Extraer función limpiar_lista_rutas
- **ID:** RF-P2-001
- **Estado:** PENDIENTE
- **Descripción:** Mover la función `limpiar_lista_rutas` que se encuentra definida localmente dentro de `paso2_ejecutar_tarea_mision` en `principal.py` a un nuevo archivo `nucleo/utilidades.py`. Crear el archivo si no existe. Luego, actualizar `principal.py` para importar y utilizar `limpiar_lista_rutas` desde `nucleo.utilidades`.
- **Archivos Implicados Específicos (Opcional):** principal.py, nucleo/utilidades.py
- **Intentos:** 0
---
### Tarea RF-P2-002: Descomponer preparación de contexto en paso2_ejecutar_tarea_mision
- **ID:** RF-P2-002
- **Estado:** PENDIENTE
- **Descripción:** Crear una nueva función privada auxiliar en `principal.py` (ej. `_obtener_contexto_para_tarea`) que encapsule toda la lógica de preparación y lectura de archivos de contexto para la tarea actual dentro de `paso2_ejecutar_tarea_mision`. Esta nueva función debe retornar el contenido concatenado y el conteo de tokens, y utilizar la función `limpiar_lista_rutas` (de `nucleo/utilidades.py`).
- **Archivos Implicados Específicos (Opcional):** principal.py
- **Intentos:** 0
---
### Tarea RF-P2-003: Descomponer aplicación de cambios y commit en paso2_ejecutar_tarea_mision
- **ID:** RF-P2-003
- **Estado:** PENDIENTE
- **Descripción:** Crear una nueva función privada auxiliar en `principal.py` (ej. `_aplicar_y_registrar_cambios_tarea`) que maneje la llamada a `aplicadorCambios.aplicarCambiosSobrescrituraV2`, el manejo de errores de aplicación (incluyendo `manejadorGit.descartarCambiosLocales`), y la lógica de `manejadorGit.hacerCommit` para los archivos modificados. Integrar esta nueva función en `paso2_ejecutar_tarea_mision`.
- **Archivos Implicados Específicos (Opcional):** principal.py
- **Intentos:** 0
---
### Tarea RF-P2-004: Abstraer operaciones Git repetitivas
- **ID:** RF-P2-004
- **Estado:** PENDIENTE
- **Descripción:** Identificar secuencias repetitivas de operaciones Git (como cambiar de rama y luego hacer un push o un commit específico) en `principal.py`. Crear funciones de ayuda más abstractas en `nucleo/manejadorGit.py` (ej. `_realizar_commit_y_push_mision`, `_asegurar_rama_y_limpiar`). Reemplazar las llamadas directas a múltiples comandos Git en `principal.py` con estas nuevas funciones abstractas.
- **Archivos Implicados Específicos (Opcional):** principal.py, nucleo/manejadorGit.py
- **Intentos:** 0