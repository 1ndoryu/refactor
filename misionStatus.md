Claro, Wan. He analizado tus nuevas ideas y las he integrado en una versión actualizada y reorganizada de la hoja de ruta del proyecto. Se han añadido nuevas tareas críticas, se han mejorado las existentes con nuevos conceptos como la evaluación de riesgos y se han reordenado las prioridades para reflejar los puntos más importantes que has señalado.

Aquí tienes el documento `Misión Orion` actualizado.

---

# Misión Orion: Proyecto de Refactorización Adaptativa por IA

**Versión Documento:** 1.3
**Fecha de Última Revisión:** 25/06/2024

**Estado:** En Desarrollo

**Autores:** Wan

**ESTE FLUJO DEBE ACTIVARSE PARA NOMBRE CLAVE WAN** ENFOCARTE EN ESTO Y USAR EL PROMPT HELPER CUANDO EL NOMBRE CLAVE SE TE INDIQUE ES WAN.

## Resumen del Proyecto

**Misión Orion** es un sistema de IA diseñado para refactorizar código de manera autónoma y adaptativa. Opera en ciclos discretos, donde cada ejecución del script `principal.py` completa una única "fase" de trabajo (ya sea la creación de un plan de misión o la ejecución de una tarea de una misión existente). Este enfoque por fases permite gestionar los límites de tokens de las API de IA, facilita el progreso incremental y mejora la trazabilidad y recuperación ante errores.

El agente interactúa con repositorios Git, creando ramas específicas para cada misión de refactorización y realizando commits incrementales a medida que progresa en las tareas.

## Flujo de Trabajo Central

El agente se ejecuta en fases. Cada invocación de `principal.py` intenta completar una fase y luego termina, guardando su estado para la siguiente ejecución.

1.  **Preparación del Entorno e Inicialización:**
    *   Al iniciar, el agente clona el repositorio especificado (si no existe localmente) o actualiza la copia local.
    *   Se asegura de estar en la rama de trabajo principal configurada (ej. `Orion` o `main`, según `settings.RAMATRABAJO`), limpiando el estado del repositorio (`reset --hard`, `clean -fdx`).
    *   Verifica si existe una misión activa registrada en el archivo de estado (ej. `.orion_meta/.active_mission` dentro del repositorio clonado).

2.  **Procesamiento de Fase (Creación o Ejecución de Misión):**

    *   **A. Si hay una Misión Activa Cargada:**
        *   El agente intenta cambiar a la rama Git asociada con la misión activa.
        *   Lee el archivo de misión (ej. `.orion_meta/<nombre_clave_mision>.md`) de dicha rama.
        *   **Ejecución de Tarea Pendiente:**
            *   Identifica la próxima tarea pendiente en el archivo de misión (priorizando tareas marcadas como `FALLIDA_TEMPORALMENTE` que aún tengan reintentos disponibles).
            *   La IA recibe la descripción de la tarea, el contexto de la misión y el contenido de los archivos relevantes para ejecutarla.
            *   La IA devuelve los cambios de código necesarios.
            *   Los cambios se aplican a los archivos en el repositorio local.
            *   El archivo de misión se actualiza para marcar la tarea como `COMPLETADA`, `FALLIDA_TEMPORALMENTE` (incrementando intentos), o `SALTADA`.
            *   Todos los cambios (código modificado y archivo de misión actualizado) se commitean a la rama de la misión.
            *   Si el `modo-automatico` está activo, se realiza `git push` de la rama de la misión al repositorio remoto.
            *   **Transición de Fase:**
                *   Si la tarea ejecutada era la última de la misión:
                    *   Se marca el estado general de la misión como `COMPLETADA` en el archivo de misión (y se commitea/pushea).
                    *   Se limpia el archivo de estado `.active_mission`.
                    *   El agente cambia a la rama de trabajo principal (`RAMATRABAJO`).
                    *   El script se detiene. La misión ha finalizado. (Nota: No se realiza merge automático a `RAMATRABAJO` ni se elimina la rama de misión).
                *   Si quedan más tareas pendientes en la misión (o la tarea actual falló y tiene reintentos):
                    *   El script se detiene. La siguiente ejecución de `principal.py` continuará con la misma misión.

    *   **B. Si NO hay una Misión Activa (o la anterior no pudo ser procesada):**
        *   El agente se asegura de estar en la rama de trabajo principal (`RAMATRABAJO`).
        *   **Opción 1: Generación de Misión desde `TODO.md` (si `modo-automatico` está activo):**
            *   Si el archivo `TODO.md` existe en la raíz del repositorio y tiene contenido:
                *   La IA analiza `TODO.md` para generar un plan de refactorización (nombre clave de misión y lista de tareas).
                *   Se crea una nueva rama Git (usando el nombre clave generado).
                *   El plan de refactorización se guarda en un nuevo archivo de misión (ej. `.orion_meta/<nombre_clave_mision_todo>.md`) en esta rama y se commitea.
                *   El nombre de la nueva misión se guarda en `.active_mission`.
                *   Si `modo-automatico` está activo, se hace `git push` de la nueva rama de misión.
                *   El script se detiene. La siguiente ejecución procesará esta nueva misión.
        *   **Opción 2: Selección de Archivo y Generación de Misión Estándar (si Opción 1 no aplica o falla):**
            *   Se selecciona un archivo del proyecto para análisis (usando una estrategia como "el menos recientemente analizado" de `registro_archivos_analizados.json`, o una estrategia mejorada).
            *   La IA evalúa si el archivo seleccionado necesita refactorización y si requiere contexto de otros archivos para planificar (`analizadorCodigo.solicitar_evaluacion_archivo`).
            *   Si se decide refactorizar:
                *   La IA genera un plan de refactorización detallado (nombre clave, metadatos, y una o más tareas atómicas) basado en el archivo principal y su contexto (`analizadorCodigo.generar_contenido_mision_orion`).
                *   Se crea una nueva rama Git.
                *   El plan se guarda en un nuevo archivo de misión (ej. `.orion_meta/<nombre_clave_mision_refactor>.md`) y se commitea.
                *   El nombre de la nueva misión se guarda en `.active_mission`.
                *   Si `modo-automatico` está activo, se hace `git push`.
                *   El script se detiene.
            *   Si la IA decide que no se necesita refactorización, o si no se pudo seleccionar un archivo:
                *   Se actualiza `registro_archivos_analizados.json`.
                *   El script se detiene.

3.  **Gestión de Límites de Tokens y Timeout de Ejecución:**
    *   El sistema monitorea el uso estimado de tokens antes de las llamadas a la IA y puede pausar la ejecución para respetar los límites por minuto de la API.
    *   Un timeout global del script previene ejecuciones indefinidas.


##  Siguientes pasos segun la ultima ejecución #EXCLUSIVO PARA WAN (puede aqui se agregen cosas que no estan en las tareas pero al completarse agregarlas e indicar como agregarse)


## Hoja de Ruta de Refactorización y Desarrollo

A continuación, se presenta la lista de tareas priorizadas para la evolución de Misión Orion.

### Fase 1: Estabilidad y Corrección de Errores Base

Objetivo: Asegurar la robustez del núcleo del sistema, corregir problemas fundamentales y mejorar la seguridad de las operaciones de modificación de código.

1.  [x] **(COMPLETADO)** **Nombre de Archivo de Misión Dinámico:**
    *   Modificar el sistema para que el archivo de misión se nombre dinámicamente usando el `nombre_clave_mision` (ej. `<nombre_clave_mision>.md`).
2.  [x] **(COMPLETADO)** **Centralización de Archivos de Estado y Logs en el Repositorio Clonado:**
    *   Mover los archivos de estado del agente (`.active_mission`, `registro_archivos_analizados.json`) y los logs (`historial_refactor_adaptativo.log`, etc.) al directorio `.orion_meta/` dentro del repositorio clonado.

### Fase 2: Mejora del Flujo de Misiones y Gestión de Contexto

Objetivo: Hacer que la creación y ejecución de misiones sea más inteligente, consciente de los riesgos y adaptable en términos de la información que maneja.


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
8.  [ ] **(ALTO)** **Mejorar Estrategia de Selección de Archivo Inicial:**
    *   En lugar de tomar solo el archivo más antiguo, seleccionar N (ej. 3) candidatos. Usar la IA (con un prompt ligero) para elegir cuál de los N es el más prometedor para refactorización.
9.  [ ] **(ALTO)** **Gestión de Contexto y Riesgo Dinámica y Adaptativa:**
    *   **Concepto:** Otorgar a la IA la capacidad de evaluar el riesgo de sus propias sugerencias y de ajustar dinámicamente el plan de la misión para mitigarlo.
    *   **Subtareas:**
        *   [ ] **Análisis de Riesgo en Creación de Misión:** Al generar una misión (`generar_contenido_mision_orion`), instruir a la IA para que evalúe el riesgo de los cambios propuestos. Si el riesgo es alto (ej. modificar una función central con muchas dependencias), la IA debe añadir automáticamente tareas de verificación previas o posteriores.
        *   [ ] **Inserción de Tareas de Verificación:** La IA debe poder generar y añadir a la misión tareas como:
            *   "**Tarea de Verificación Previa:** Confirmar todos los puntos de llamada de la función `X` en el proyecto antes de modificarla."
            *   "**Tarea de Verificación Posterior:** Después de aplicar los cambios de la tarea Y, ejecutar una revisión para asegurar que el código sigue siendo sintácticamente correcto y que las dependencias no se han roto."
        *   [ ] **Capacidad de Solicitar Más Contexto durante la Ejecución:** En `ejecutar_tarea_especifica_mision`, permitir que la IA responda indicando que el contexto es insuficiente para completar la tarea de forma segura. Si esto ocurre, la tarea se marca como `NECESITA_MAS_CONTEXTO` y el sistema inserta una nueva tarea antes de la actual para obtener los archivos adicionales que la IA haya solicitado.
10. [ ] **(MEDIO)** **Optimización de Selección de Contexto Inicial con `mapaArchivos`:**
    *   Crear y mantener un `mapaArchivos.md` (o `.json`) en `.orion_meta/` que sirva como caché de resúmenes y propósitos de los archivos del proyecto. Esto ayudará a la IA a tomar decisiones más informadas sobre qué archivos necesita como contexto, sin tener que leerlos todos cada vez.
11. [ ] **(MEDIO)** **Historial de Misiones para Evitar Duplicados:**
    *   Implementar `historial_misiones.json` en `.orion_meta/`. Antes de crear una nueva misión, consultar este historial para evitar generar misiones que ya se han intentado o que son muy similares.

### Fase 3: Nuevas Funcionalidades y Mejoras de Usabilidad

Objetivo: Añadir herramientas y opciones que mejoren la interacción y control del usuario sobre el agente.

12. [ ] **(ALTO)** **Procesamiento de Instrucción Directa por Argumento:**
    *   Implementar `python3 principal.py --instruccion "Tu instrucción aquí..."`.
    *   Este comando debe tener la máxima prioridad. Si se usa, el agente debe saltarse la selección de archivos y generar una misión directamente basada en la instrucción del usuario. Esto permite un control preciso y dirigido.
13. [ ] **(MEDIO)** **Comando `--back` para Revertir Última Ejecución:**
    *   Añadir un argumento `--back` a `principal.py` que identifique y revierta el/los commit(s) de la última fase de ejecución del agente, restaurando el estado de la tarea a `PENDIENTE`.
14. [ ] **(BAJO)** **Procesamiento de Archivo Específico por Argumento:**
    *   Permitir `python3 principal.py --archivo ruta/al/archivo.ext`.
    *   Si no hay misión activa, procede a crear una misión para este archivo. Es una versión menos potente que `--instruccion`.

### Fase 4: Optimización y Mantenimiento Continuo

Objetivo: Mejorar la eficiencia, la gestión de recursos y la mantenibilidad a largo plazo.

15. [ ] **(MEDIO)** **Gestión de Tamaño de Archivos de Log y Metadatos:**
    *   Implementar un mecanismo de rotación o truncamiento para `historial_refactor_adaptativo.log`, `mapaArchivos` y `historial_misiones.json` para evitar que crezcan indefinidamente.
16. [ ] **(MEDIO)** **Implementar Lectura Parcial/Incremental de Archivos:**
    *   Para archivos muy grandes, permitir que la IA primero lea solo las firmas de funciones/clases. Basado en eso, decidir si necesita leer el contenido completo de una función específica, ahorrando tokens.
17. [ ] **(BAJA PRIORIDAD)** **Auto-corrección de Rutas de Archivo Fallidas:**
    *   Si una ruta de archivo sugerida por la IA no existe, darle la capacidad de intentar "corregirla" basándose en la estructura del proyecto.
18. [ ] **(BAJA PRIORIDAD)** **Modo Manual con Intervención Humana:**
    *   Implementar un `modo-manual` donde el agente pausa en puntos clave (después de generar una misión, después de proponer cambios) y solicita la aprobación del usuario antes de proceder.

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