# Misión de Refactorización Adaptativa, enfocarse aqui

hay que cambiar la forma en la que este proyecto funciona, podemos ir pasos por paso, llevaremos una lista de tareas aca, tu las agrega y las vas completado. Se que no puedes modificar los archivos pero tu me vas a indicado las tareas y yo las agrego. Como seran muchos pasos, y mucho trabajo, podemos saltarnos ir paso por paso, y hacer todos los pasos de una vez archivo por archivo, por favor, esto es importante para ahorrar tiempo.

Este proyecto es un refactorizador que necesita ser ajustado

tiene 2 pasos

En el primer paso toma una decisión analizando una carpeta entera, y luego en el segundo paso, realiza esa accion, esto funcionaba bien, pero ya no porque necesitamos limitar la cantidad de tokens que procesa. 

Hay que hacer muchos cambios adaptativos y significativos

lo importante, es no pasarse de 250k tokens por minutos ese es el limite asi que hay que de alguna forma inteligente, de pausarse a esperar que el limite pase antes de recibir una respuesta 429. 

Haremos varios pasos, cada paso tendra sus instruciones que yo agregare pero este es un boceto(mantener contexto dentro de los pasos pero al pasar al siguiente paso se limpia el contexto, no se como se hace esto con la api de gemini) 

Paso 1 revisar: revisar si hay una misión en la carpeta que esta analizando dentro del repositorio, se llamara misionOrion.md, si no existe el archivo o si todas las tareas estan completadas en el archivo, estonces pasa al paso 1.1 , si hay misiones pasa al paso 2 (recibira misionOrion.md y los archivos de contexto dentro .md tambien seran recibidos por paso 2)

Paso 1.1 eleccion: se envia un archivo aleatoreo (hay que llevar un registro de archivos escogidos con el proposito de elegir siempre el que haya pasado mas tiempo sin escogerse, esto tiene que ser intentarme en la logica de python, aun no se como), y va a revisar si necesita ser refactorizado dicho archivo, en caso de que si necesite ser refactorizado (esta decisión la va a tomar en base a un conjunto de reglas que establecere), va a decidir si necesita más contexto, y va a decidir cuales archivo va a leer, (recibira la estructura de la carpeta) (se le indicara que eliga archivos en base al nombre que parezcan estar relacionados), y va a pasar al paso 1.2.

Paso 1.2 misión: este paso generará una misión, importante, la mision necesita un nombre clave porque se usará para hacer una rama con ese nombre, esto va a recibir todos los archivos que decidio el paso 1.1, y los va a leer completo, y en base a sus instruciones, genera misionOrion.md (guardara dentro de misionOrion.md un conjunto de pasos y tareas y el nombre de los archivos para contexto)

Paso 2 misión: esto no lo voy a explicar tan detalladamente, este se encargara de leer todo lo que recibe, el md de mision y todos los archivos de contexto, y cumplirá una tarea, y guardara un historia como ya lo hace, cambiaremos la forma en la que se guarda este historial mas adelante.

## Fin de apartado de misión.


# Lista de Tareas del Proyecto de Refactorización Adaptativa
Nota: Dame la lista de tareas actualizadas despues de un cambio.

## Módulo: principal.py

- [X] **`ejecutarCicloAdaptativo`**: Implementar la función con la lógica de los nuevos Pasos 0, 1, 1.1, 1.2 y 2.
- [X] **Manejo de Límites de API**:
    - [X] Implementar `gestionar_limite_tokens`.
    - [X] Implementar `registrar_tokens_usados`.
- [X] **Paso 0 - Revisión de Misión Local**:
    - [X] Implementar estructura base de `paso0_revisar_mision_local`.
    - [ ] Implementar `parsear_mision_orion` de forma robusta.
    - [ ] Implementar `parsear_nombre_clave_de_mision` de forma robusta.
- [X] **Paso 1.1 - Selección y Decisión Inicial**:
    - [X] Implementar estructura base de `paso1_1_seleccion_y_decision_inicial`.
    - [X] Implementar `cargar_registro_archivos`.
    - [X] Implementar `guardar_registro_archivos`.
    - [X] Implementar `seleccionar_archivo_mas_antiguo`.
- [X] **Paso 1.2 - Generación de Misión**:
    - [X] Implementar estructura base de `paso1_2_generar_mision`.
- [X] **Paso 2 - Ejecución de Tarea de Misión**:
    - [X] Implementar estructura base de `paso2_ejecutar_tarea_mision`.
    - [ ] Implementar `obtener_proxima_tarea_pendiente` de forma robusta.
    - [ ] Implementar `marcar_tarea_como_completada` de forma robusta.

## Módulo: nucleo/analizadorCodigo.py

- [ ] **`solicitar_evaluacion_archivo` (Paso 1.1)**:
    - [ ] Crear la función para que la IA decida si refactorizar un archivo.
    - [ ] Definir el prompt y el formato JSON de respuesta (necesita_refactor, necesita_contexto_adicional, archivos_contexto_sugeridos, razonamiento, tokens_consumidos_estimados).
- [ ] **`generar_contenido_mision_orion` (Paso 1.2)**:
    - [ ] Crear la función para que la IA genere el contenido de `misionOrion.md`.
    - [ ] Definir el prompt y el formato JSON de respuesta (nombre_clave_mision, contenido_markdown_mision, tokens_consumidos_estimados).
- [ ] **`ejecutar_tarea_especifica_mision` (Paso 2)**:
    - [ ] Crear la función para que la IA ejecute una tarea específica de la misión.
    - [ ] Definir el prompt y el formato JSON de respuesta (archivos_modificados, tokens_consumidos_estimados).
- [ ] **`leerArchivos`**:
    - [ ] Verificar y refinar el conteo de tokens para que sea preciso según el proveedor API actual.
    - [ ] Asegurar que se use consistentemente con `gestionar_limite_tokens`.

## Módulo: nucleo/manejadorGit.py

- [ ] Implementar `crear_y_cambiar_a_rama(ruta_repo, nombre_rama_nueva, rama_base)`.
- [ ] Implementar `cambiar_a_rama_existente(ruta_repo, nombre_rama)`.
- [ ] Implementar `hacerCommitEspecifico(ruta_repo, mensaje, lista_archivos_a_commitear)`.
- [ ] Implementar `hacerMergeRama(ruta_repo, rama_origen, rama_destino_actual)`.
- [ ] Implementar `eliminarRama(ruta_repo, nombre_rama, local=True, remota=False)`.
- [ ] Implementar `existe_rama(ruta_repo, nombre_rama)`.

## Módulo: nucleo/manejadorHistorial.py

- [ ] Revisar `formatearEntradaHistorial` y `guardarHistorial` para el nuevo flujo de misiones (probablemente no requiera cambios mayores, pero verificar claridad del log).

## Tareas Comunes / Definiciones

- [ ] **Prompts de IA**:
    - [ ] Revisar y adaptar todos los prompts para las nuevas funciones en `analizadorCodigo.py`.
- [ ] **Formatos de Datos**:
    - [ ] Definir formatos robustos para `misionOrion.md` (metadatos, estructura de tareas, etc.).
    - [ ] Definir los formatos JSON de entrada/salida para las nuevas funciones de `analizadorCodigo.py`.

## Módulo: config/settings.py

- [ ] Añadir la variable `TOKEN_LIMIT_PER_MINUTE`.
- [ ] Añadir (opcionalmente, o dejar que se construyan en `principal.py`):
    - [ ] `MAX_CICLOS_PRINCIPALES_AGENTE`
    - [ ] `DELAY_ENTRE_CICLOS_AGENTE`