# EL BUSCADOR DE CODIGO FUNCIONA MUY MAL 11:00 PM

> EJEMPLO DE LO QUE SIEMPRE SUELE SUCEDER. 


Con la accion de "Mueve funcion obtenerIdiomaDelNavegador a functions.php para reutilización"

El codigo_a_mover (Código Buscado): Gemini ha proporcionado el siguiente bloque exacto (según Código buscado (literal)):

<?

// Función para obtener el idioma preferido del navegador
function obtenerIdiomaDelNavegador() {
    // ... cuerpo de la función ...
}

PHP
Nota clave: Empieza con <?, seguido de dos saltos de línea, y luego el comentario // Función....

El contenidoOrigen (Archivo mover_codigo_origen_contenido_TemplateInicio_php.txt): El contenido real del archivo TemplateInicio.php empieza así:

<?
/*
Template Name: Inicio
*/

// Función para obtener el idioma preferido del navegador
function obtenerIdiomaDelNavegador() {
    // ... cuerpo de la función ...
}
// ... resto del archivo ...
?>

Funciona mal porque la cantidad de contexto no deja analizar bien exactamente que tiene que buscar, no porque el codigo este malo sino porque alucina por el contexto grande, por lo tanto alucina y comete errores, lo ideal es cambiar la logica, para que primero gemini analice y tome una decisión, por ejemplo, de que archivo tiene que analizar, que tiene cambiar, que tiene que mover, por que, etc. 

(se resetea el contexto)

Y despues otra solicitud a gemini que haga el cambio que incluya solo el contexto de los archivos que va a modificar, y que haga un cambio del codigo completo, no una parte pequeña porque eso lleva a errores, sino todo el archivo, 

otra solucion eficiente es agregar mas contexto en el historial, diferenciar entre pensamiento (la primera parte que analiza todo el codigo) y decisión (segunda parte en donde el contexto se reduce para que haga el cambio), el pensamiento tiene que ser muy claro y detallado para que la decisión sea lo mas acertada y precisa. 


# 29 de marzo 6:00 PM

1. [BIEN] Parece mover codigo correctamente de un documento a otro. 
2. [MAL] Suele tener un error como este "Texto a buscar no encontrado o la primera ocurrencia ya coincidía con el reemplazo en TemplateFeedSample.php."

# Objectivo iniciales

El objectivo es crear una programa (lo mas razonable parece ser llamarlo agente) que clone un repositorio para un determinado proyecto, y refactorice, organice, resuelva problemas, mejore la legibilidad. Sera para un proyecto en especificos, hay algunas cosas a tener en cuenta. 

1. El proyecto tiene una ventana de contexto muy grande, casi 700.000 token. 
2. El proyecto carece de arquitectura, es un tema de wordpress. 
3. El programa debe tomar una sola decisión, hacer el cambio necesario pequeño, y hacer un commit detallado de lo que hice. 
4. El programa por cada decisión que toma limpia la ventana de contexto y registra un historial de su cambio, vuelve a leer el historial en la proxima acción para que sepa lo que hace. 
5. Inicialmente se necesita que funcione en mode test, es decir cuando se ejecute en modo test, solo hara un cambio y envia los cambios a github. 
6. Obviamente la capacidad de crear archivos, borrar, mover, crear carpetas. 
7. Usar la gemini api. 
8. Usará una rama propia llamada refactor. 
9. Solo debe leer los archivos .php , por el momento es la prioridad. debe entender la estructura, la ubicacion de cada archivo, etc.
10. Dentro del prompt, obviamente tiene que ver todas las carpetas y nombres de archivo porque le será ulti. 
