# Misión Orion: Proyecto de Refactorización Adaptativa por IA

**Versión Documento:** 1.2
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

Arreglar ultimo error 

2025-06-05 21:03:13 - INFO - [root] _crearNuevaMision: _crearNuevaMision: Procediendo con selección de archivo estándar para refactorización...
2025-06-05 21:03:13 - CRITICAL - [root] orchestrarEjecucionScript: Error fatal no manejado en orquestación: name 'paso1_1_seleccion_y_decision_inicial' is not defined
Traceback (most recent call last):
  File "/var/www/herramientaRefactor/principal.py", line 239, in orchestrarEjecucionScript
    fase_exitosa = ejecutarFaseDelAgente(
  File "/var/www/herramientaRefactor/principal.py", line 1010, in ejecutarFaseDelAgente
    exito_fase_creacion = _crearNuevaMision(
  File "/var/www/herramientaRefactor/principal.py", line 874, in _crearNuevaMision
    res_paso1_1, archivo_sel, ctx_sel, decision_ia_1_1 = paso1_1_seleccion_y_decision_inicial(
NameError: name 'paso1_1_seleccion_y_decision_inicial' is not defined
2025-06-05 21:03:13 - INFO - [root] orchestrarEjecucionScript: Registro de archivos analizados guardado al finalizar script.


## Hoja de Ruta de Refactorización y Desarrollo

A continuación, se presenta la lista de tareas priorizadas para la evolución de Misión Orion.

### Fase 1: Estabilidad y Corrección de Errores Base

Objetivo: Asegurar la robustez del núcleo del sistema y corregir problemas fundamentales.

1.  [x] **(CRÍTICO)** **Nombre de Archivo de Misión Dinámico:**
    *   Modificar el sistema para que el archivo de misión (actualmente `misionOrion.md`) se nombre dinámicamente usando el `nombre_clave_mision` (ej. `<nombre_clave_mision>.md`).
2.  [x] **(CRÍTICO)** **Centralización de Archivos de Estado y Logs en el Repositorio Clonado:**
    *   Mover los archivos de estado del agente (`.active_mission`, `registro_archivos_analizados.json`) y el log principal (`historial_refactor_adaptativo.log`, y otros como `mapaArchivos`, `historial_misiones`) al directorio del repositorio clonado (`settings.RUTACLON`), dentro de una subcarpeta dedicada (ej. `.orion_meta/`).
    *   **Subtareas:**
        *   [x] Crear la carpeta `.orion_meta/` si no existe.
        *   [x] Añadir `.orion_meta/` al `.gitignore` del repositorio `1ndoryu-refactor` (el proyecto del agente mismo) para no versionar los metadatos de los repositorios que analiza, pero **no** al `.gitignore` de los repositorios clonados (ya que esos metadatos sí deben persistir con el clon).
        *   [x] Actualizar las constantes y funciones de carga/guardado en `principal.py` (ej. `ACTIVE_MISSION_STATE_FILE`, `REGISTRO_ARCHIVOS_ANALIZADOS_PATH`, `cargar_estado_mision_activa`, etc.).
            *   [x] ruta y el nombre del archivo de log principal para que se almacene en settings.RUTACLON/.orion_meta/historial_refactor_adaptativo.log
            *   [x] Actualizar la constante REGISTRO_ARCHIVOS_ANALIZADOS_PATH en principal.py para que apunte a settings.RUTACLON/.orion_meta/registro_archivos_analizados.json.
            *   [x] Actualizar la constante ACTIVE_MISSION_STATE_FILE en principal.py para que apunte a settings.RUTACLON/.orion_meta/.active_mission.
            *   [x] Actualizar la constante RUTAHISTORIAL en config/settings.py para que apunte a settings.RUTACLON/.orion_meta/ (y decidir un nombre de archivo para el historial de manejadorHistorial.py si historial_refactor_adaptativo.log ya está tomado por el log principal, por ejemplo, historial_acciones_mision.log).
            *   [*PARCIALMENTECOMPLETADA*] Actualizar las funciones de carga/guardado en principal.py (guardar_registro_archivos, guardar_estado_mision_activa) para que incluyan os.makedirs(os.path.dirname(RUTA_AL_ARCHIVO), exist_ok=True).
            *   [x] Revisar y actualizar realizarReseteoAgente en principal.py para asegurar que limpie los archivos en sus nuevas ubicaciones.
        *   [x] Verificar y actualizar la función `realizarReseteoAgente` (comando `--reset`) para que limpie correctamente estos archivos en sus nuevas ubicaciones.
3.  [ ] **(ALTO)** **Mecanismo de Validación Post-Cambio y Auto-Corrección/Reversión:**
    *   Implementar un paso de validación después de que `aplicadorCambios.aplicarCambiosSobrescrituraV2` aplique los cambios de una tarea.
    *   **Subtareas:**
        *   [ ] Diseñar un prompt para la IA que le pida revisar el `git diff` de los cambios aplicados o el contenido de los archivos modificados, comparándolos con la intención original de la tarea.
        *   [ ] Implementar la lógica para que, si la validación de la IA indica un problema, se intente una corrección (posiblemente con otro prompt a la IA pidiéndole que corrija su salida anterior).
        *   [ ] Si la corrección falla, implementar una reversión automática de los cambios de ESA tarea específica (ej. `git checkout -- <archivos_afectados_por_la_tarea>` si aún no se ha hecho commit, o `git reset HEAD^` si la tarea ya resultó en un commit individual).
4.  [ ] **(ALTO)** **Verificación de Archivos Vacíos Antes de Lectura por IA:**
    *   En `analizadorCodigo.leerArchivos` (o antes de llamarlo), verificar si un archivo está vacío.
    *   Si un archivo está vacío, no incluir su contenido en el prompt para la IA y registrar este hecho. Esto ahorra tokens y evita que la IA procese contenido inexistente.
5.  [ ] **(ALTO)** **Robustez en `manejadorGit.clonarOActualizarRepo`:**
    *   Mejorar la detección de la rama principal remota (más allá de `main` o `master`).
    *   Antes de intentar `git checkout -b <rama> origin/<rama>` o `git reset --hard origin/<rama>`, verificar explícitamente que `<rama>` exista en `origin` usando `manejadorGit.existe_rama(..., remote_only=True)`.
    *   Si la rama esperada (ej. `settings.RAMATRABAJO` o una rama de misión) no existe remotamente, manejar el error de forma controlada (ej., si es `RAMATRABAJO`, intentar crearla desde la rama principal remota; si es una rama de misión, podría indicar un estado inconsistente).

### Fase 2: Mejora del Flujo de Misiones y Gestión de Contexto

Objetivo: Hacer que la creación y ejecución de misiones sea más inteligente y adaptable en términos de la información que maneja.

6.  [ ] **(ALTO)** **Mejorar Estrategia de Selección de Archivo Inicial:**
    *   Modificar `paso1_1_seleccion_y_decision_inicial` y `seleccionar_archivo_mas_antiguo`.
    *   En lugar de tomar solo el más antiguo, seleccionar N (ej. 3) archivos candidatos (basados en antigüedad o aleatoriedad controlada entre los no analizados recientemente).
    *   Usar la IA (con un prompt ligero, posiblemente usando `mapaArchivos` si existe) para elegir cuál de esos N candidatos es el más prometedor para refactorización o el que mejor se alinea con objetivos generales.
7.  [ ] **(ALTO)** **Gestión de Contexto Dinámica y Adaptativa:**
    *   Permitir que el sistema solicite o ajuste el contexto necesario durante la vida de una misión.
    *   **Subtareas:**
        *   [ ] **Análisis Inteligente de Dependencias (Búsqueda de Usos):** Al seleccionar un archivo para misión (Paso 1.1) o al preparar una tarea (Paso 2), la IA podría ser instruida para, basándose en el `mapaArchivos` o en un análisis superficial del código, identificar funciones/clases clave y sugerir una búsqueda en el proyecto para encontrar dónde se usan, añadiendo esos archivos al contexto.
        *   [ ] **Generación de Misiones (Paso 1.2):** Modificar `analizadorCodigo.generar_contenido_mision_orion` y `generar_contenido_mision_desde_texto_guia` para que la IA pueda, si detecta baja confianza en el contexto inicial, añadir una tarea específica al inicio de la misión para "Verificar y Expandir Contexto".
        *   [ ] **Ejecución de Tareas (Paso 2):**
            *   En `analizadorCodigo.ejecutar_tarea_especifica_mision`, modificar el prompt para que la IA pueda indicar si el contexto actual es insuficiente para completar la tarea de forma segura.
            *   Si la IA indica insuficiencia de contexto, la tarea actual podría marcarse como `NECESITA_MAS_CONTEXTO`. `principal.py` debería entonces:
                *   Usar la IA para generar una nueva tarea de "Obtener Contexto Adicional para Tarea X" (especificando qué archivos buscar).
                *   Insertar esta nueva tarea antes de la tarea original.
                *   La siguiente fase ejecutaría la tarea de obtención de contexto, actualizando `archivos_contexto_ejecucion` en el archivo `.md` de la misión.
8.  [ ] **(MEDIO)** **Optimización de Selección de Contexto Inicial con `mapaArchivos`:**
    *   Crear un `mapaArchivos.md` (o `.json`) en `.orion_meta/` que sirva como caché de resúmenes, propósitos y quizás dependencias clave de los archivos del proyecto.
    *   **Importante:** El `mapaArchivos` es una guía y no reemplaza la lectura de archivos para la IA, pero ayuda a seleccionar *qué* leer.
    *   **Actualización Constante:** Si un archivo es modificado por una tarea de Misión Orion, el `mapaArchivos` debe actualizarse para reflejar el nuevo estado/propósito del archivo.
    *   **Estructura:** Considerar un mapa por carpeta principal para manejar la extensibilidad si el proyecto es muy grande.
    *   **Implementación:** Este archivo debe considerarse metadato del repositorio analizado y NO debe estar en el `.gitignore` del repositorio analizado (pero sí en el `.gitignore` del proyecto Misión Orion mismo, si se almacena fuera del repo clonado, aunque la Tarea 2 lo mueve dentro).
    *   **Flujo:**
        *   Cuando `paso1_1_seleccion_y_decision_inicial` selecciona un archivo:
            *   Consultar `mapaArchivos` por si ya existe un resumen/info.
            *   Si existe, usar esa información como parte del input para `solicitar_evaluacion_archivo`.
            *   Si no existe (o la información es muy vieja):
                *   La IA lee el contenido completo del archivo.
                *   Pedir a la IA que genere un breve resumen del propósito del archivo y lo guarde en `mapaArchivos`.
        *   Al generar `archivos_contexto_sugeridos`, la IA también podría usar la información de `mapaArchivos` para tomar decisiones más informadas.
9.  [ ] **(MEDIO)** **Historial de Misiones para Evitar Duplicados:**
    *   Implementar un sistema para registrar misiones completadas, fallidas o incluso activas (ej. en un archivo `historial_misiones.json` dentro de `.orion_meta/`).
    *   Antes de crear una nueva misión (especialmente desde `paso1_1_seleccion_y_decision_inicial`), consultar este historial para evitar generar misiones que ya se han intentado o que son muy similares (ej. basadas en el mismo archivo principal y razón).

### Fase 3: Nuevas Funcionalidades y Mejoras de Usabilidad

Objetivo: Añadir herramientas y opciones que mejoren la interacción y control del usuario sobre el agente.

10. [ ] **(MEDIO)** **Comando `--back` para Revertir Última Ejecución:**
    *   Añadir un argumento `--back` a `principal.py`.
    *   Si se invoca, el agente deberá:
        *   Identificar la misión activa y su rama.
        *   Identificar el/los commit(s) realizados por el agente en la *última fase de ejecución* en esa rama. (Esto podría requerir guardar el SHA del último commit al final de cada fase en `.active_mission` o en el archivo de misión `.md`).
        *   Revertir esos commits (ej. `git reset --hard HEAD~N` donde N es el número de commits de la última fase, o una serie de `git revert SHA` si se prefiere no reescribir historia).
        *   Actualizar el estado de la tarea correspondiente en el archivo de misión a `PENDIENTE` (o al estado previo si se puede determinar).
11. [ ] **(BAJO)** **Procesamiento de Archivo Específico por Argumento:**
    *   Permitir `python3 principal.py --archivo ruta/al/archivo.ext`.
    *   **Comportamiento:**
        *   Si hay una misión activa:
            *   *Alternativa más simple (Inicial):* Abortar e informar al usuario que debe completar/resetear la misión actual antes de especificar un archivo.
            *   *(Futuro):* Preguntar al usuario (si es modo interactivo) o, por defecto en modo automático, crear una nueva misión para este archivo, pausando o marcando como "espera" la misión actual (requiere un sistema de gestión de múltiples misiones o un stack).
        *   Si NO hay misión activa: Proceder a crear una nueva misión directamente para este archivo, saltando `seleccionar_archivo_mas_antiguo`.

### Fase 4: Optimización y Mantenimiento Continuo

Objetivo: Mejorar la eficiencia, la gestión de recursos y la mantenibilidad a largo plazo.

12. [ ] **(MEDIO)** **Gestión de Tamaño de Archivos de Log y Metadatos:**
    *   Implementar un mecanismo para limitar el tamaño de:
        *   `historial_refactor_adaptativo.log` (en `.orion_meta/`)
        *   `mapaArchivos.md` (o `.json`, y sus posibles divisiones por carpeta) (en `.orion_meta/`)
        *   `historial_misiones.json` (en `.orion_meta/`)
    *   Esto podría ser mediante rotación de archivos, truncamiento de entradas antiguas, o archivado.
13. [ ] **(MEDIO)** **Implementar Lectura Parcial/Incremental de Archivos:**
    *   Modificar `analizadorCodigo.leerArchivos` o las funciones que lo llaman.
    *   Para archivos grandes, la IA podría primero leer solo una porción inicial (ej. primeros N tokens o líneas, o solo firmas de funciones/clases).
    *   Basado en esta lectura parcial (y `mapaArchivos`), la IA podría decidir si necesita leer más secciones específicas del archivo o el archivo completo para la tarea actual, ahorrando tokens cuando el contexto completo no es crucial.
14. [ ] **(BAJA PRIORIDAD)** **Auto-corrección de Rutas de Archivo Fallidas:**
    *   En `analizadorCodigo.leerArchivos`, si una ruta de archivo sugerida por la IA (ej. en `archivos_contexto_sugeridos` o `archivos_implicados_especificos`) no existe:
        *   Considerar la posibilidad de pedir a la IA que intente "corregir" la ruta basándose en la estructura del proyecto, si la ruta parece un error tipográfico o una ruta ligeramente incorrecta.
        *   Reintentar la lectura con la ruta corregida. (Esto tiene riesgo de bucles o errores adicionales, implementar con cautela).
15. [ ] **(BAJA PRIORIDAD)** **Modo Manual con Intervención Humana:**
    *   Implementar un `modo-manual` donde el agente pausa en puntos clave (ej. después de generar una misión, después de que la IA propone cambios para una tarea) y solicita la aprobación/modificación del usuario antes de proceder.
    *   Esto reutilizaría la mayor parte de la lógica existente, añadiendo puntos de interacción con el usuario.

### Lluvias de ideas.

*Todas las ideas previas en esta sección han sido integradas en la hoja de ruta principal. Esta sección se puede usar para nuevas ideas pendientes de análisis y priorización.*

1. Creo que ya sugire que se pueda elegir un archivo a refactorizar, algo algo que es mucho mas importante que eso, poder recibir una instruccion directa del usuario al ejecutar. 

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