# nucleo/test_aplicadorCambios.py
import unittest
import os
import tempfile
import shutil
import json
import logging
from nucleo.aplicadorCambios import aplicarCambiosSobrescritura

# Configura un logger básico para ver los logs de la función durante las pruebas
# Esto es importante para ver los logs DEBUG que añadimos
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s: %(message)s')
log_test = logging.getLogger(__name__)


class TestAplicadorCambios(unittest.TestCase):

    def setUp(self):
        """Crea un directorio temporal para cada prueba."""
        self.test_dir = tempfile.mkdtemp()
        log_test.info(f"Directorio temporal creado: {self.test_dir}")

    def tearDown(self):
        """Elimina el directorio temporal después de cada prueba."""
        shutil.rmtree(self.test_dir)
        log_test.info(f"Directorio temporal eliminado: {self.test_dir}")

    def _run_test(self, test_name, input_content, expected_content, ruta_relativa="test.txt"):
        """Función helper para ejecutar una prueba individual."""
        log_test.info(f"--- Ejecutando Test: {test_name} ---")
        archivos_con_contenido = {
            ruta_relativa: input_content
        }
        # Simula los otros parámetros necesarios
        accion_original = "modificar_codigo_en_archivo"  # O la acción relevante
        params_original = {"archivo": ruta_relativa}

        # Llama a la función bajo prueba
        success, error_msg = aplicarCambiosSobrescritura(
            archivos_con_contenido,
            self.test_dir,  # Ruta base es el directorio temporal
            accion_original,
            params_original
        )

        # Verifica que la función reportó éxito
        self.assertTrue(
            success, f"aplicarCambiosSobrescritura falló: {error_msg}")
        self.assertIsNone(
            error_msg, f"Se esperaba error_msg None, pero fue: {error_msg}")

        # Verifica el contenido del archivo escrito
        ruta_absoluta_esperada = os.path.join(self.test_dir, ruta_relativa)
        self.assertTrue(os.path.exists(ruta_absoluta_esperada),
                        f"El archivo {ruta_relativa} no fue creado.")

        with open(ruta_absoluta_esperada, 'r', encoding='utf-8') as f:
            contenido_real = f.read()

        log_test.debug(
            f"Contenido REAL escrito en {ruta_relativa}:\n{repr(contenido_real)}")
        log_test.debug(
            f"Contenido ESPERADO para {ruta_relativa}:\n{repr(expected_content)}")
        self.assertEqual(contenido_real, expected_content,
                         f"El contenido del archivo no coincide para {test_name}")
        log_test.info(f"--- Test '{test_name}' superado ---")

    # --- Casos de Prueba Específicos ---

    def test_01_saltos_de_linea_escapados(self):
        """Prueba que '\\n' literal se convierta en newline real."""
        # Gemini enviaría esto DENTRO de la cadena JSON
        entrada_gemini = "Primera línea\\nSegunda línea con \\\\n literal."
        # Lo que se espera en el archivo final
        salida_esperada = "Primera línea\nSegunda línea con \\n literal."
        self._run_test("Salto de línea (\\n)", entrada_gemini, salida_esperada)

    def test_02_unicode_escapes(self):
        """Prueba que '\\uXXXX' literal se convierta en el caracter."""
        # Fíjate en las dobles barras \\ para representar un \ literal en la cadena Python
        # que simula lo que vendría del JSON
        entrada_gemini = "Funci\\u00f3n con car\\u00e1cter especial \\\\u00e1 (debería ser literal)."
        salida_esperada = "Función con carácter especial \\u00e1 (debería ser literal)."
        self._run_test("Escapes Unicode (\\uXXXX)",
                       entrada_gemini, salida_esperada)

    def test_03_mojibake_simple(self):
        """Prueba la corrección de Mojibake común (UTF-8 -> Latin1 -> UTF-8)."""
        entrada_gemini = "Este texto usarÃ¡ acentos y eÃ±es."  # Típico de 'usará' y 'eñes'
        salida_esperada = "Este texto usará acentos y eñes."
        self._run_test("Mojibake Simple (Ã¡, Ã±)",
                       entrada_gemini, salida_esperada)

    def test_04_mojibake_complejo(self):
        """Prueba Mojibake con más caracteres."""
        entrada_gemini = "Â¡Hola, MÃºndo! Â¿QuÃ© tal?"  # Input Mojibake for ¡Hola, Múndo! ¿Qué tal?
        # CORRECTED Expected Output: The proper decoding of the input Mojibake
        salida_esperada = "¡Hola, Múndo! ¿Qué tal?"
        self._run_test("Mojibake Complejo (¡, ¿, ú)",
                       entrada_gemini, salida_esperada)

    def test_05_mixto_mojibake_y_escapes(self):
        """Prueba una cadena con Mojibake y escapes literales. (dificil de solucionar, ignorar pro el momento)"""
        entrada_gemini = "Descripci\\u00f3n: El c\\u00f3digo fallarÃ¡ si no se corrige.\\nL\\u00ednea nueva."
        # Esperado: Descripci[ó]n: El c[ó]digo fallar[á] si no se corrige.[Newline]L[í]nea nueva.
        salida_esperada = "Descripción: El código fallará si no se corrige.\nLínea nueva."
        self._run_test("Mixto Mojibake y Escapes",
                       entrada_gemini, salida_esperada)

    def test_06_texto_utf8_correcto(self):
        """Prueba que texto UTF-8 válido no se corrompa."""
        entrada_gemini = "Texto ya correcto: áéíóúñ ¿?"
        salida_esperada = "Texto ya correcto: áéíóúñ ¿?"
        self._run_test("Texto UTF-8 Correcto", entrada_gemini, salida_esperada)

    def test_07_caso_barra_n_literal_gemini(self):
        """
        Prueba qué pasa si Gemini envía '//n' como pidió el prompt.
        Se espera que se escriba literalmente '//n', ya que 'unicode_escape' no lo toca.
        """
        entrada_gemini = "log.info('Procesando...//nNueva línea en log');"
        salida_esperada = "log.info('Procesando...//nNueva línea en log');"
        self._run_test("Barra N literal (//n)",
                       entrada_gemini, salida_esperada)

    def test_08_comillas_y_barras_escapadas_json(self):
        """
        Prueba si el contenido tiene comillas y barras que necesitan escaparse en JSON.
        La entrada simula CÓMO LLEGARÍA la cadena DESPUÉS de `json.loads`.
        `aplicarCambiosSobrescritura` recibe la cadena ya parseada.
        El test verifica que `unicode_escape` maneje barras escapadas correctamente.
        """
        # Cadena original deseada: print("Hola \\ \"mundo\"")
        # En JSON se enviaría: "print(\"Hola \\\\ \\\"mundo\\\"\")"
        # Después de json.loads(), Python la tendría como: 'print("Hola \\\\ \\"mundo\\"")'
        #                                                     OJO: Doble barra + Barra+Comilla
        # 'unicode_escape' debería convertir '\\\\' a '\' y '\\"' a '"'.
        # Simula resultado de json.loads
        entrada_post_json_loads = 'print("Hola \\\\ \\"mundo\\"")'
        # El resultado final en el archivo
        salida_esperada = 'print("Hola \\ \"mundo\"")'
        self._run_test("Comillas y Barras Escapadas",
                       entrada_post_json_loads, salida_esperada)

    def test_09_ruta_con_subdirectorio(self):
        """Prueba la escritura en un subdirectorio."""
        entrada_gemini = "Contenido en subdirectorio."
        salida_esperada = "Contenido en subdirectorio."
        self._run_test("Ruta con Subdirectorio", entrada_gemini,
                       salida_esperada, ruta_relativa="subdir/archivo.js")

    def test_10_contenido_no_string(self):
        """Prueba qué pasa si el contenido no es un string (debería convertir a JSON)."""
        entrada_gemini = {"clave": "valor", "lista": [1, 2, "texto"]}
        # Se espera que se convierta a JSON string
        salida_esperada = json.dumps(
            entrada_gemini, indent=2, ensure_ascii=False)
        self._run_test("Contenido No String (Dict)",
                       entrada_gemini, salida_esperada)

    def test_11_php_string_literal_newline(self):
        """
        Prueba que '\\n' DENTRO de una cadena literal de código (PHP)
        permanezca como '\\n' literal en el archivo final, sin convertirse
        en un salto de línea real.
        Simula el caso problemático reportado.
        """
        # Lo que Gemini enviaría en el JSON (simplificado): "$log = \"Error:\\nDetalles\";"
        # Después de json.loads, la cadena Python sería: '$log = "Error:\\nDetalles";'
        # Esta es la cadena que recibe aplicarCambiosSobrescritura.
        entrada_gemini = '$log_message = "Detalles de scriptsOrdenados:\\n" . implode("\\n", $error_log) . "\\n";'

        # El contenido EXACTO que esperamos en el archivo .php final.
        # Debe mantener los \n L I T E R A L E S dentro de las comillas dobles de PHP.
        salida_esperada = '$log_message = "Detalles de scriptsOrdenados:\\n" . implode("\\n", $error_log) . "\\n";'

        self._run_test("PHP String Literal con \\n",
                       entrada_gemini,
                       salida_esperada,
                       ruta_relativa="test_script.php")  # Usar extensión .php es más representativo

    def test_12_real_newlines_from_json_remain_real(self):
        """
        Prueba que los saltos de línea REALES en la cadena de entrada
        (provenientes de '\\n' en el JSON original) se escriban como
        saltos de línea reales en el archivo, y no como '\\n' literales.
        Simula el segundo caso problemático reportado.
        """
        # Esta es la cadena Python que tendría tu función DESPUÉS de json.loads
        # si el JSON contenía '\\n' para los saltos de línea.
        # OJO: Usamos saltos de línea reales en esta cadena multilínea de Python.
        entrada_con_newlines_reales = """function loadingBar()
{
    echo '<style>
        #loadingBar {
            position: fixed;
            top: 0;
            left: 0;
            width: 0%;
            height: 4px;
            background-color: white; /* Color de la barra */
            transition: width 0.4s ease;
            z-index: 999999999999999;
        }
    </style>';
}"""  # Asegúrate que el indentado aquí sea el deseado en la salida

        # El contenido esperado en el archivo final debe ser idéntico,
        # preservando los saltos de línea reales.
        salida_esperada = """function loadingBar()
{
    echo '<style>
        #loadingBar {
            position: fixed;
            top: 0;
            left: 0;
            width: 0%;
            height: 4px;
            background-color: white; /* Color de la barra */
            transition: width 0.4s ease;
            z-index: 999999999999999;
        }
    </style>';
}"""

        self._run_test("Saltos de línea Reales (desde JSON \\n)",
                       entrada_con_newlines_reales,
                       salida_esperada,
                       ruta_relativa="test_script_newlines.php")


# Para poder ejecutar desde la línea de comandos
if __name__ == '__main__':
    unittest.main()
