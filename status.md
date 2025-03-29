# Objectivo 

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
