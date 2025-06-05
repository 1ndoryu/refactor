# Misión: RefactorPrincipalSRP_1

**Metadatos de la Misión:**
- **Nombre Clave:** RefactorPrincipalSRP_1
- **Archivo Principal:** principal.py
- **Archivos de Contexto (Generación):** config/settings.py
- **Archivos de Contexto (Ejecución):** config/settings.py
- **Razón (Paso 1.1):** El archivo 'principal.py' es excesivamente grande y monolítico, violando el Principio de Responsabilidad Única (SRP). Contiene una mezcla de lógica de orquestación de alto nivel, gestión de estado (límites de tokens, registro de archivos analizados, estado de misión activa), manejo de argumentos, configuración de logging y la implementación detallada de cada 'fase' del agente. Esto dificulta enormemente la legibilidad, mantenibilidad y capacidad de prueba del código. Se beneficiaría de una refactorización para extraer responsabilidades claras en módulos o clases dedicadas (ej., un módulo para la gestión de estado del agente, una clase para la orquestación del flujo principal, etc.). El contexto adicional de 'config/settings.py' es esencial para entender las dependencias de configuración (rutas, claves API, límites) que son críticas para la lógica de 'principal.py' y para asegurar que cualquier refactorización de rutas o acceso a configuraciones sea correcta.
- **Estado:** PENDIENTE

## Tareas de Refactorización:
---
### Tarea SRP-001: Extraer Gestión de Tokens a Módulo Dedicado
- **ID:** SRP-001
- **Estado:** PENDIENTE
- **Descripción:** Mover las funciones 'gestionar_limite_tokens' y 'registrar_tokens_usados', junto con la variable global 'token_usage_window', a un nuevo módulo 'nucleo/token_manager.py'. Asegurar que todas las llamadas y referencias en 'principal.py' sean actualizadas para usar el nuevo módulo. El objetivo es centralizar la lógica de control de límite de tokens.
- **Archivos Implicados Específicos (Opcional):** principal.py, nucleo/token_manager.py
- **Intentos:** 0
---
### Tarea SRP-002: Extraer Gestión de Registro de Archivos Analizados
- **ID:** SRP-002
- **Estado:** PENDIENTE
- **Descripción:** Mover las funciones 'cargar_registro_archivos', 'guardar_registro_archivos' y 'seleccionar_archivo_mas_antiguo', junto con la constante 'REGISTRO_ARCHIVOS_ANALIZADOS_PATH', a un nuevo módulo 'nucleo/file_registry.py'. Actualizar todas las referencias en 'principal.py' para importar y usar estas funciones desde el nuevo módulo. Esto mejora la separación de responsabilidades para el seguimiento de archivos.
- **Archivos Implicados Específicos (Opcional):** principal.py, nucleo/file_registry.py
- **Intentos:** 0
---
### Tarea SRP-003: Extraer Gestión de Estado de Misión Activa
- **ID:** SRP-003
- **Estado:** PENDIENTE
- **Descripción:** Mover las funciones 'cargar_estado_mision_activa', 'guardar_estado_mision_activa' y 'limpiar_estado_mision_activa', junto con la constante 'ACTIVE_MISSION_STATE_FILE', a un nuevo módulo 'nucleo/mission_state_manager.py'. Actualizar las llamadas en 'principal.py' para importar desde el nuevo módulo. Esto centraliza la gestión del estado de la misión.
- **Archivos Implicados Específicos (Opcional):** principal.py, nucleo/mission_state_manager.py
- **Intentos:** 0