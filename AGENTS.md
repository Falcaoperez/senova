# Trabajo en GESICOM

El repositorio de trabajo autorizado es `santiagoCoy2025/senova`. `Falcaoperez/senova` permanece como origen de referencia.

## Entrega de cambios

1. Crea una rama de trabajo para cada bloque de cambios a partir de `develop` actualizado.
2. Ejecuta las comprobaciones correspondientes y sube la rama al fork.
3. Abre un pull request dirigido a `develop` en el fork. Describe el comportamiento final y las pruebas.
4. Fusiona cuando las pruebas y las reglas del repositorio lo permitan. No omitas revisiones o comprobaciones obligatorias.
5. Verifica la integración antes de eliminar la rama de trabajo remota y local. Mientras un PR siga abierto, conserva su rama.
6. Conserva siempre `develop` y `main`. No fuerces actualizaciones ni borres esas ramas.

La primera integración incorpora el rediseño ya preparado y estas mejoras de seguridad; la rama `develop` inicial procede de `main` del fork.

## Configuración y comprobaciones

- El remitente elegido es `santiagoocoy2025@gmail.com`, por Gmail con STARTTLS. Las contraseñas de aplicación y tokens se configuran de forma privada.
- Nunca añadas `.env`, `.local/`, bases de datos, archivos de usuarios, logs ni credenciales al historial.
- Usa Python 3.12 y MySQL para verificar migraciones y concurrencia.
- Para cambios de autenticación, permisos o persistencia: `python manage.py test --settings=SENNOVA.test_settings --noinput`, `python manage.py makemigrations --check --dry-run` y `ruff check .`.
- Comprueba `DJANGO_DEBUG=False python manage.py check --deploy` y los recursos estáticos cuando corresponda.
- El entorno local captura correo con Mailpit. No confundas esa captura con entrega real de Gmail.
