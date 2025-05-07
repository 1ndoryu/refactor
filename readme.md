
# 1ndoryu-Refactor: Agente Autónomo de Refactorización de Código con IA

Este proyecto es un agente autónomo diseñado para refactorizar código de forma iterativa utilizando modelos de lenguaje de IA (Google Gemini o OpenRouter). El agente sigue un proceso de tres pasos principales para analizar el código, proponer cambios, ejecutar dichos cambios y, opcionalmente, verificarlos antes de realizar un commit en un repositorio Git.

## Características Principales

*   **Refactorización Automatizada:** Sugiere y aplica cambios de refactorización pequeños y atómicos.
*   **Soporte Multi-API:** Compatible con Google Gemini y OpenRouter.
*   **Integración con Git:** Clona/actualiza repositorios, trabaja en ramas específicas, realiza commits y (en modo test) hace push.
*   **Proceso en 3 Pasos:**
    1.  **Análisis y Decisión:** La IA analiza el código, la estructura del proyecto y el historial para proponer una acción de refactorización.
    2.  **Ejecución:** Otra instancia de IA (o la misma) recibe la decisión y el contexto de los archivos relevantes para generar el código modificado.
    3.  **Verificación (Opcional, actualmente desactivada):** Compara la intención original con los cambios aplicados y el estado de Git.
*   **Configuración Flexible:** A través de variables de entorno (`.env`) y el archivo `config/settings.py`.
*   **Manejo de Historial:** Guarda un registro de todas las operaciones y sus resultados en `historial_refactor.log`.
*   **Logging Detallado:** Registra el proceso en `refactor.log` y en la consola.
*   **Manejo de Errores:** Intenta recuperarse de errores, descarta cambios si fallan los pasos críticos y registra los problemas.
*   **Rotación de API Keys:** El archivo `settings.py` incluye lógica para rotar entre múltiples API keys (si se configuran) para evitar límites de cuota.
*   **Timeout de Ejecución:** El script principal tiene un timeout para evitar ejecuciones indefinidas.

## Flujo de Trabajo Detallado

1.  **Inicialización:**
    *   Configura el sistema de logging.
    *   Carga el historial de refactorizaciones previas (`historial_refactor.log`).
    *   Prepara el repositorio Git local:
        *   Clona el repositorio si no existe o actualiza el existente.
        *   Realiza un `git reset --hard` a la rama principal remota y `git clean -fdx` para asegurar un estado limpio.
        *   Se cambia a la rama de trabajo especificada (ej. `refactor-2`), creándola si es necesario a partir de la rama principal.

2.  **Paso 1: Análisis y Decisión (Módulo `analizadorCodigo`)**
    *   Genera una representación textual de la estructura del proyecto.
    *   Lee el contenido de todos los archivos relevantes del proyecto (filtrados por extensión e directorios ignorados).
    *   Envía el código completo, la estructura del proyecto y el historial reciente a la IA (Gemini/OpenRouter).
    *   La IA devuelve una **decisión** en formato JSON, especificando:
        *   `accion_propuesta`: (ej. `mover_funcion`, `modificar_codigo_en_archivo`, `crear_archivo`, `no_accion`).
        *   `descripcion`: Para el mensaje de commit.
        *   `parametros_accion`: Detalles específicos para la acción.
        *   `archivos_relevantes`: Archivos que el Paso 2 necesitará leer.
        *   `razonamiento`: Justificación de la IA.
    *   Si la acción es `no_accion`, el ciclo termina.

3.  **Paso 2: Ejecución (Módulo `analizadorCodigo` y `aplicadorCambios`)**
    *   Se lee el contenido de los `archivos_relevantes` identificados en el Paso 1 para crear un contexto reducido.
    *   La decisión del Paso 1 y el contexto reducido se envían a la IA.
    *   La IA devuelve un **resultado** en formato JSON, que incluye:
        *   `archivos_modificados`: Un diccionario donde las claves son rutas relativas de archivos y los valores son el contenido completo y final de dichos archivos.
    *   El módulo `aplicadorCambios` toma este resultado y:
        *   Valida las rutas de los archivos.
        *   Crea directorios padres si es necesario.
        *   Decodifica secuencias de escape (ej. `\\n` -> `\n`) y corrige problemas comunes de codificación (Mojibake).
        *   Sobrescribe/crea los archivos en el repositorio local con el nuevo contenido.
        *   Maneja acciones especiales como `eliminar_archivo` o `crear_directorio` (añadiendo un `.gitkeep` a directorios nuevos).

4.  **Paso 3: Verificación (Módulo `principal` - Actualmente DESACTIVADA)**
    *   (Si estuviera activada) Compara la intención del Paso 1, el resultado del Paso 2 y los archivos realmente modificados según `git status`.
    *   Busca inconsistencias (archivos modificados inesperadamente, archivos que debían cambiar y no lo hicieron, etc.).
    *   Si la verificación falla, se descartan los cambios y se registra el error.

5.  **Commit y Finalización (Módulo `manejadorGit`)**
    *   Si los pasos anteriores fueron exitosos:
        *   Se realiza un `git add -A`.
        *   Se realiza un `git commit -m "descripcion_del_paso_1"`.
        *   Se guarda la entrada del ciclo actual en `historial_refactor.log`.
        *   Si el script se ejecuta con `--modo-test` y el commit fue efectivo, se intenta un `git push` a la rama de trabajo.
    *   En caso de cualquier error crítico durante el proceso, se intenta descartar los cambios locales (`git reset --hard HEAD && git clean -fdx`) para mantener el repositorio limpio.

## Estructura del Directorio

```
└── 1ndoryu-refactor/
    ├── principal.py           # Script principal que orquesta el proceso.
    ├── requirements.txt       # Dependencias del proyecto.
    ├── status.md              # Estado y problemas detectados (manual).
    ├── .env.example           # Ejemplo para el archivo de configuración .env
    ├── config/
    │   ├── __init__.py
    │   └── settings.py        # Carga configuración y gestiona API keys.
    └── nucleo/
        ├── __init__.py
        ├── analizadorCodigo.py    # Interactúa con la IA para análisis y generación de código.
        ├── aplicadorCambios.py  # Aplica los cambios de código a los archivos.
        ├── manejadorGit.py      # Gestiona las operaciones de Git.
        └── test_aplicarCambios.py # Pruebas unitarias para aplicadorCambios.py.
```
*(Nota: `refactor.log` y `historial_refactor.log` se crearán en el directorio raíz del proyecto al ejecutar el script).*

## Requisitos Previos

*   Python 3.7+
*   Git instalado y accesible en el PATH del sistema.
*   Una o más API Keys de Google Gemini y/o OpenRouter.

## Instalación

1.  **Clonar el repositorio:**
    ```bash
    git clone https://github.com/tu-usuario/1ndoryu-refactor.git
    cd 1ndoryu-refactor
    ```

2.  **Crear un entorno virtual (recomendado):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # En Windows: venv\Scripts\activate
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuración

El proyecto se configura principalmente a través de variables de entorno y el archivo `config/settings.py`.

1.  **Crear archivo `.env`:**
    Copia `.env.example` a `.env` en la raíz del proyecto y edítalo con tus valores:
    ```dotenv
    # --- Google Gemini API Keys (rotación) ---
    # Clave base (obligatoria si GEMINI_NUM_API_KEYS > 0 o es la única)
    GEMINI_API_KEY="TU_API_KEY_GEMINI_0"
    # Claves adicionales para rotación (opcional)
    # GEMINI_API_KEY1="TU_API_KEY_GEMINI_1"
    # GEMINI_API_KEY2="TU_API_KEY_GEMINI_2"
    # ... hasta GEMINI_API_KEY(N-1)

    # Modelo de Google Gemini a usar (ej. gemini-1.5-flash-latest, gemini-1.0-pro)
    GEMINI_MODEL="gemini-1.5-flash-latest"


    # --- OpenRouter API Keys (rotación) ---
    # Clave base (obligatoria si OPENROUTER_NUM_API_KEYS > 0 o es la única)
    OPENROUTER_API_KEY="sk-or-YOUR_OPENROUTER_KEY_0"
    # Claves adicionales para rotación (opcional)
    # OPENROUTER_API_KEY1="sk-or-YOUR_OPENROUTER_KEY_1"
    # OPENROUTER_API_KEY2="sk-or-YOUR_OPENROUTER_KEY_2"
    # ... hasta OPENROUTER_API_KEY(N-1)

    # URL base de la API de OpenRouter (normalmente no necesita cambiarse)
    OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
    # Referer y Title para OpenRouter (reemplaza con tu URL/nombre de sitio si lo usas en un contexto web)
    OPENROUTER_REFERER="<YOUR_SITE_URL>"
    OPENROUTER_TITLE="<YOUR_APP_NAME>"
    # Modelo de OpenRouter a usar (ej. google/gemini-flash-1.5, anthropic/claude-3-haiku)
    OPENROUTER_MODEL="google/gemini-flash-1.5"
    ```

2.  **Configuración en `config/settings.py`:**
    *   **`GEMINI_NUM_API_KEYS`**: Número total de claves Gemini API que has definido en `.env` (ej. `5` si tienes `GEMINI_API_KEY` y `GEMINI_API_KEY1` a `GEMINI_API_KEY4`).
    *   **`OPENROUTER_NUM_API_KEYS`**: Número total de claves OpenRouter API que has definido en `.env`.
    *   **`REPOSITORIOURL`**: URL del repositorio Git a refactorizar (ej. `git@github.com:usuario/proyecto.git`).
    *   **`RAMATRABAJO`**: Rama Git donde se aplicarán los cambios (ej. `refactor-dev`).
    *   `RUTACLON`, `RUTAHISTORIAL`: Rutas para el clon del proyecto y el archivo de historial. Normalmente no necesitan cambiarse.
    *   `N_HISTORIAL_CONTEXTO`: Número de entradas recientes del historial a pasar a la IA como contexto.
    *   `EXTENSIONESPERMITIDAS`: Lista de extensiones de archivo a considerar para el análisis.
    *   `DIRECTORIOS_IGNORADOS`: Lista de directorios a ignorar durante el análisis.

    **Importante sobre API Keys:**
    *   Si `GEMINI_NUM_API_KEYS` es `1`, solo se usará `GEMINI_API_KEY`.
    *   Si `GEMINI_NUM_API_KEYS` es `0`, la funcionalidad de Gemini estará desactivada.
    *   Lo mismo aplica para `OPENROUTER_API_KEY` y `OPENROUTER_NUM_API_KEYS`.
    *   El sistema rotará las claves para cada ejecución del script, usando el archivo `.api_key_last_index.txt` o `.openrouter_api_key_last_index.txt` (creados en `config/`) para recordar la última clave usada.

## Uso

Ejecuta el script principal desde la raíz del proyecto:

```bash
python principal.py [opciones]
```

**Opciones:**

*   `--modo-test`: Si se activa y el ciclo de refactorización resulta en un commit efectivo, el script intentará hacer `git push` a la rama de trabajo.
*   `--openrouter`: Utiliza OpenRouter como proveedor de IA en lugar de Google Gemini (que es el predeterminado).

**Ejemplos:**

*   Ejecutar un ciclo usando Google Gemini (predeterminado):
    ```bash
    python principal.py
    ```
*   Ejecutar un ciclo usando OpenRouter y activar el push en caso de éxito:
    ```bash
    python principal.py --openrouter --modo-test
    ```

El script tiene un **timeout global** (actualmente 5 minutos, configurable en `principal.py`) para prevenir ejecuciones excesivamente largas.

## Logging

*   **Consola:** Muestra logs informativos y de error durante la ejecución.
*   **Archivo `refactor.log`:** Se crea en la raíz del proyecto y contiene un registro detallado de todas las operaciones, incluyendo mensajes de debug.
*   **Archivo `historial_refactor.log`:** Se crea en la raíz del proyecto. Guarda un resumen de cada ciclo de refactorización, incluyendo la decisión de la IA, el resultado y cualquier error. Este historial se usa como contexto para futuras decisiones de la IA.

## Pruebas

El proyecto incluye pruebas unitarias para el módulo `aplicadorCambios.py`, que se enfoca en la correcta manipulación de strings (escapes, Mojibake) al escribir archivos. Para ejecutar las pruebas:

```bash
python -m unittest nucleo/test_aplicarCambios.py
```
o si estás en el directorio `nucleo`:
```bash
python test_aplicarCambios.py
```

## Problemas Conocidos y Limitaciones (basado en `status.md`)

*   **Modelo Gemini Pro (más antiguo, si se usara):**
    *   Puede tener problemas con acentos, punto y coma, etc.
    *   Los saltos de línea en logs o código pueden interpretarse/generarse de forma literal.
*   **Modelo Gemini Flash (o modelos más nuevos):**
    *   A veces puede borrar contenido válido por alucinaciones u olvidos. Se intenta mitigar con prompts más detallados.
*   **Calidad de la Refactorización:** La calidad de los cambios depende enteramente de la capacidad del modelo de IA y la claridad del prompt.
*   **Seguridad:** Aunque se intenta priorizar, la IA podría introducir vulnerabilidades. La revisión humana es crucial.
*   **Verificación Desactivada:** El Paso 3 de verificación está actualmente desactivado en `principal.py`. Si se activa, podría ayudar a detectar inconsistencias, pero también podría ser demasiado restrictivo.
*   **Manejo de Archivos Grandes:** El contexto enviado a la IA puede ser muy grande si el proyecto tiene muchos archivos o archivos muy extensos, lo que podría llevar a timeouts o respuestas truncadas de la API.

## Contribuciones

Las contribuciones son bienvenidas. Por favor, abre un issue para discutir cambios importantes o reportar bugs. Si deseas contribuir con código, considera hacer un fork y enviar un Pull Request.

## Licencia

Este proyecto se distribuye bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles (actualmente no incluido, pero es una sugerencia estándar).
