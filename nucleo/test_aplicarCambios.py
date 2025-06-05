import unittest
import os
import tempfile
import shutil
import json
import logging
from nucleo.aplicadorCambios import aplicarCambiosSobrescrituraV1, aplicarCambiosSobrescrituraV2

# Configura un logger básico para ver los logs de la función durante las pruebas
logging.basicConfig(level=logging.INFO, # Cambiado a INFO para reducir verbosidad, DEBUG si es necesario
                    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s: %(message)s')
log_test = logging.getLogger(__name__)


class TestAplicadorCambios(unittest.TestCase):

    def setUp(self):
        """Crea un directorio temporal para cada prueba."""
        self.test_dir = tempfile.mkdtemp()
        log_test.debug(f"Directorio temporal creado: {self.test_dir}")

    def tearDown(self):
        """Elimina el directorio temporal después de cada prueba."""
        shutil.rmtree(self.test_dir)
        log_test.debug(f"Directorio temporal eliminado: {self.test_dir}")

    def _run_test(self, test_name, funcion_a_probar, input_content, expected_content, ruta_relativa="test.txt", accion_original="modificar_codigo_en_archivo", params_original=None):
        """Función helper para ejecutar una prueba individual."""
        log_test.info(f"--- Ejecutando Test: {test_name} para {funcion_a_probar.__name__} ---")
        
        # Asegurar que el directorio de prueba esté limpio para esta ejecución específica si es necesario,
        # aunque setUp/tearDown por método de test debería manejarlo.
        # Por seguridad, creamos la ruta completa al archivo esperado para limpiarlo si existe.
        ruta_absoluta_a_escribir = os.path.join(self.test_dir, ruta_relativa)
        if os.path.exists(ruta_absoluta_a_escribir):
            os.remove(ruta_absoluta_a_escribir)
        
        # El formato correcto para archivos_con_contenido es una lista de dicts
        archivos_para_aplicar = [{"nombre": ruta_relativa, "contenido": input_content}]
        
        if params_original is None:
            params_original = {"archivo": ruta_relativa}

        # Llama a la función bajo prueba
        success, error_msg = funcion_a_probar(
            archivos_para_aplicar,
            self.test_dir,
            accion_original,
            params_original
        )

        self.assertTrue(success, f"{funcion_a_probar.__name__} falló para '{test_name}': {error_msg}")
        self.assertIsNone(error_msg, f"Se esperaba error_msg None para '{test_name}', pero fue: {error_msg}")

        self.assertTrue(os.path.exists(ruta_absoluta_a_escribir),
                        f"El archivo {ruta_relativa} no fue creado por {funcion_a_probar.__name__} para '{test_name}'.")

        with open(ruta_absoluta_a_escribir, 'r', encoding='utf-8') as f:
            contenido_real = f.read()

        log_test.debug(f"Test: {test_name} ({funcion_a_probar.__name__}) - Contenido REAL escrito en {ruta_relativa}:\n{repr(contenido_real)}")
        log_test.debug(f"Test: {test_name} ({funcion_a_probar.__name__}) - Contenido ESPERADO para {ruta_relativa}:\n{repr(expected_content)}")
        
        self.assertEqual(contenido_real, expected_content,
                         f"El contenido del archivo no coincide para '{test_name}' ({funcion_a_probar.__name__})")
        log_test.info(f"--- Test '{test_name}' ({funcion_a_probar.__name__}) superado ---")

    # --- Casos de Prueba Específicos ---

    def test_01_saltos_de_linea_escapados(self):
        test_name = "Salto de línea (\\n y \\\\n)"
        entrada_gemini = "Primera línea\\nSegunda línea con \\\\n literal."
        
        # V1: codecs.decode(..., 'unicode_escape') convierte '\\n' a '\n' y '\\\\n' a '\\n' (literal).
        salida_esperada_v1 = "Primera línea\nSegunda línea con \\n literal."
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada_v1)

        # V2: No hay unicode_escape, se mantiene la entrada.
        salida_esperada_v2 = "Primera línea\\nSegunda línea con \\\\n literal."
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada_v2)

    def test_02_unicode_escapes(self):
        test_name = "Escapes Unicode (\\uXXXX y \\\\uXXXX)"
        entrada_gemini = "Funci\\u00f3n con car\\u00e1cter especial \\\\u00e1 (debería ser literal)."
        
        # V1: '\\u00f3' -> 'ó', '\\\\u00e1' -> '\\u00e1' (literal)
        salida_esperada_v1 = "Función con carácter especial \\u00e1 (debería ser literal)."
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada_v1)

        # V2: Se mantiene la entrada.
        salida_esperada_v2 = "Funci\\u00f3n con car\\u00e1cter especial \\\\u00e1 (debería ser literal)."
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada_v2)

    def test_03_mojibake_simple(self):
        test_name = "Mojibake Simple (Ã¡, Ã±)"
        entrada_gemini = "Este texto usarÃ¡ acentos y eÃ±es."
        salida_esperada = "Este texto usará acentos y eñes." # Ambas versiones deben corregir Mojibake
        
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada)
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada)

    def test_04_mojibake_complejo(self):
        test_name = "Mojibake Complejo (¡, ¿, ú)"
        entrada_gemini = "Â¡Hola, MÃºndo! Â¿QuÃ© tal?"
        salida_esperada = "¡Hola, Múndo! ¿Qué tal?" # Ambas versiones
        
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada)
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada)

    def test_05_mixto_mojibake_y_escapes(self):
        test_name = "Mixto Mojibake y Escapes"
        entrada_gemini = "Descripci\\u00f3n: El c\\u00f3digo fallarÃ¡ si no se corrige.\\nL\\u00ednea nueva."
        
        # V1: unicode_escape primero, luego mojibake.
        # "Descripci\\u00f3n: El c\\u00f3digo fallarÃ¡ si no se corrige.\\nL\\u00ednea nueva."
        # -> "Descripción: El código fallarÃ¡ si no se corrige.\nLínea nueva." (unicode_escape)
        # -> "Descripción: El código fallará si no se corrige.\nLínea nueva." (mojibake)
        salida_esperada_v1 = "Descripción: El código fallará si no se corrige.\nLínea nueva."
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada_v1)

        # V2: solo mojibake.
        # "Descripci\\u00f3n: El c\\u00f3digo fallarÃ¡ si no se corrige.\\nL\\u00ednea nueva."
        # -> "Descripci\\u00f3n: El c\\u00f3digo fallará si no se corrige.\\nL\\u00ednea nueva." (mojibake)
        salida_esperada_v2 = "Descripci\\u00f3n: El c\\u00f3digo fallará si no se corrige.\\nL\\u00ednea nueva."
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada_v2)

    def test_06_texto_utf8_correcto(self):
        test_name = "Texto UTF-8 Correcto"
        entrada_gemini = "Texto ya correcto: áéíóúñ ¿?"
        salida_esperada = "Texto ya correcto: áéíóúñ ¿?" # Ambas versiones
        
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada)
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada)

    def test_07_caso_barra_n_literal_gemini(self):
        test_name = "Barra N literal (//n)"
        entrada_gemini = "log.info('Procesando...//nNueva línea en log');"
        # '//n' no es una secuencia de escape estándar, unicode_escape no la toca.
        salida_esperada = "log.info('Procesando...//nNueva línea en log');" # Ambas versiones
        
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada)
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada)

    def test_08_comillas_y_barras_escapadas_json(self):
        test_name = "Comillas y Barras Escapadas (JSON style \\\\ y \\\")"
        # Cadena Python que simula lo que llega después de json.loads de: "print(\"Hola \\\\ \\\"mundo\\\"\")"
        entrada_post_json_loads = 'print("Hola \\\\ \\"mundo\\"")'
        
        # V1: codecs.decode(..., 'unicode_escape')
        # '\\\\' se convierte en '\\' (una barra literal)
        # '\\"' se convierte en '\"' (barra y comilla literales)
        salida_esperada_v1 = 'print("Hola \\ \\"mundo\\"")' # Corregido: una barra, espacio, barra-comilla
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_post_json_loads, salida_esperada_v1)

        # V2: No hay unicode_escape, se mantiene la entrada.
        salida_esperada_v2 = 'print("Hola \\\\ \\"mundo\\"")'
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_post_json_loads, salida_esperada_v2)

    def test_09_ruta_con_subdirectorio(self):
        test_name = "Ruta con Subdirectorio"
        entrada_gemini = "Contenido en subdirectorio."
        salida_esperada = "Contenido en subdirectorio." # Ambas versiones
        ruta_rel = "subdir/archivo.js"
        
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada, ruta_relativa=ruta_rel)
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada, ruta_relativa=ruta_rel)

    def test_10_contenido_no_string(self):
        test_name = "Contenido No String (Dict)"
        entrada_gemini = {"clave": "valor", "lista": [1, 2, "texto"]}
        # Ambas versiones deben convertir a JSON string si no es string
        salida_esperada = json.dumps(entrada_gemini, indent=2, ensure_ascii=False)
        
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada)
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada)

    def test_11_php_string_literal_con_barra_n(self):
        test_name = "PHP String Literal con \\n (queremos \\n literal en archivo)"
        # Lo que la IA envía: $log = "Error:\\nDetalles";
        # Como cadena Python de entrada a la función:
        entrada_gemini = '$log_message = "Detalles de scriptsOrdenados:\\n" . implode("\\n", $error_log) . "\\n";'

        # V1: aplica unicode_escape, por lo que '\\n' se convierte en '\n' (newline real).
        salida_esperada_v1 = '$log_message = "Detalles de scriptsOrdenados:\n" . implode("\n", $error_log) . "\n";'
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada_v1, ruta_relativa="test_script_v1.php")

        # V2: no aplica unicode_escape, por lo que '\\n' permanece como '\\n' (literal).
        # ESTE ES EL COMPORTAMIENTO DESEADO SEGÚN EL NOMBRE DEL TEST ORIGINAL.
        salida_esperada_v2 = '$log_message = "Detalles de scriptsOrdenados:\\n" . implode("\\n", $error_log) . "\\n";'
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada_v2, ruta_relativa="test_script_v2.php")

    def test_12_php_multilinea_echo_con_escapes(self):
        test_name = "PHP Multilinea Echo con \\n (queremos newline real en archivo)"
        entrada_gemini = (
            'function loadingBar()\\n'
            '{\\n'
            '    echo \'<style>\\\\n' # IA quiere \n aquí, envía \\\\n
            '        #loadingBar {\\\\n' # Ídem
            '            /* ...css... */\\\\n'
            '        }\\\\n'
            '    </style>\';\\n'
            '}'
        )
        
        # V1: aplica unicode_escape.
        # '\\n' (formato de código) -> '\n'
        # '\\\\n' (dentro de string PHP) -> '\\n' (literal \n)
        salida_esperada_v1 = (
            'function loadingBar()\n'
            '{\n'
            '    echo \'<style>\\n' # Esto es lo que la V1 produce y es el objetivo del test
            '        #loadingBar {\\n'
            '            /* ...css... */\\n'
            '        }\\n'
            '    </style>\';\n'
            '}'
        )
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, entrada_gemini, salida_esperada_v1, ruta_relativa="loading_bar_v1.php")

        # V2: no aplica unicode_escape.
        # '\\n' (formato de código) -> '\\n'
        # '\\\\n' (dentro de string PHP) -> '\\\\n'
        salida_esperada_v2 = (
            'function loadingBar()\\n'
            '{\\n'
            '    echo \'<style>\\\\n'
            '        #loadingBar {\\\\n'
            '            /* ...css... */\\\\n'
            '        }\\\\n'
            '    </style>\';\\n'
            '}'
        )
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, entrada_gemini, salida_esperada_v2, ruta_relativa="loading_bar_v2.php")

    # --- Nuevos Casos de Prueba ---

    def test_13_entrada_ia_con_doble_barra_n(self):
        test_name = "Entrada IA con \\\\n (esperando conversión o no)"
        # IA envía una cadena que contiene la secuencia literal '\\' y 'n'
        input_content = "codigo_con_doble_barra_n = \"print(\\\"Linea1\\\\nLinea2\\\")\""
        
        # V1: codecs.decode convierte '\\n' a '\n' (newline real)
        expected_v1 = "codigo_con_doble_barra_n = \"print(\\\"Linea1\\nLinea2\\\")\""
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, input_content, expected_v1, "test13_v1.py")

        # V2: Sin unicode_escape, '\\n' se mantiene como '\\n'
        expected_v2 = "codigo_con_doble_barra_n = \"print(\\\"Linea1\\\\nLinea2\\\")\""
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, input_content, expected_v2, "test13_v2.py")

    def test_14_entrada_ia_con_newline_real(self):
        test_name = "Entrada IA con \\n real (esperando preservación)"
        # IA envía una cadena que YA contiene un carácter newline real (ASCII 10)
        input_content = "codigo_con_newline_real = \"print(\\\"Linea1\nLinea2\\\")\"" # \n es un newline real
        
        # V1: unicode_escape no debería afectar un newline ya real
        expected_v1 = "codigo_con_newline_real = \"print(\\\"Linea1\nLinea2\\\")\""
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, input_content, expected_v1, "test14_v1.py")

        # V2: Sin unicode_escape, obviamente preserva el newline real
        expected_v2 = "codigo_con_newline_real = \"print(\\\"Linea1\nLinea2\\\")\""
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, input_content, expected_v2, "test14_v2.py")
        
    def test_15_control_chars_como_literales_escapados(self):
        test_name = "Secuencias como \\a, \\f (queremos literales o caracteres de control)"
        # La IA quiere escribir \a y \f literalmente, por lo que envía '\\a' y '\\f'
        # Esto, en una cadena Python que representa la entrada, es '\\\\a' y '\\\\f'
        # O, si la IA envía directamente \a (no escapado por la IA), la cadena Python es '\\a'
        # Probemos el caso donde la IA envía una cadena que contiene las secuencias de dos caracteres '\' y 'a'
        input_content = "# Ruta problemática: C:\\app\\file.py" # Python: '# Ruta problemática: C:\\app\\file.py'
                                                          # \a es BEL, \f es FF

        # V1: unicode_escape convierte '\a' a BEL (0x07), '\f' a FF (0x0C)
        expected_v1 = "# Ruta problemática: C:\x07pp\x0cile.py"
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, input_content, expected_v1, "test15_v1.txt")

        # V2: Sin unicode_escape, '\a' y '\f' se escriben como están (secuencias de dos caracteres)
        expected_v2 = "# Ruta problemática: C:\\app\\file.py"
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, input_content, expected_v2, "test15_v2.txt")

    def test_16_php_backslash_en_array_literal(self):
        test_name = "PHP: \\\\ literal en string dentro de array ['\\\\', '/']"
        # Objetivo en archivo PHP: $arr = ['\\', '/'];
        # Para eso, la cadena Python a escribir en el archivo debe ser: "$arr = ['\\\\', '/'];"
        # Esta es la cadena que la IA debería generar como contenido.
        input_content = "$arr = ['\\\\', '/'];"

        # V1: unicode_escape convierte '\\\\' en '\\'.
        # El archivo contendrá: $arr = ['\', '/']; (Esto es un error de sintaxis en PHP)
        expected_v1 = "$arr = ['\\', '/'];"
        self._run_test(test_name, aplicarCambiosSobrescrituraV1, input_content, expected_v1, "test16_v1.php")

        # V2: Sin unicode_escape, se escribe tal cual.
        # El archivo contendrá: $arr = ['\\\\', '/']; (Esto es correcto en PHP)
        expected_v2 = "$arr = ['\\\\', '/'];"
        self._run_test(test_name, aplicarCambiosSobrescrituraV2, input_content, expected_v2, "test16_v2.php")


# Para poder ejecutar desde la línea de comandos
if __name__ == '__main__':
    unittest.main()