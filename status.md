# Objectivo 

El objectivo es crear una programa que clone un repositorio para un determinado proyecto, y refactorice, organice, resuelva problemas, mejore la legibilidad. Sera para un proyecto en especificos, hay algunas cosas a tener en cuenta. 

1. El proyecto tiene una ventana de contexto muy grande, aproximadamente unos 600.000 token y va en aumento. 
2. El objectivo principal es organizar el codigo de la mejor manera porque el proyecto carece de arquitectura. 
3. El programa debe tomar una sola decisión, por cada git, debe tener unas instrucciones previas obviamente, pero la principal, es hacer un cambio pequeño, y registrarlo en commit detallado, asi se lleva un control mas preciso.
4. Por cada decisión que toma, la ventana de contexto se limpia, posteriormente, guarda un historial de lo que va haciendo para volverlo a leer con cada modificacación. 
5. Debe funcionar automaticamente cada cierto tiempo que se determine, tener un modo test solo sole se ejecutara una sola vez. 
6. Obviamente la capacidad de crear archivos, borrar, mover, crear carpetas. 
7. Usar la gemini api. 

