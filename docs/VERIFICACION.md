# Verificación de la revisión

Fecha: 11 de noviembre de 2026. Las mediciones corresponden al entorno local de revisión.

## Pruebas y dependencias

- 64 pruebas automatizadas aprobadas contra MySQL, incluidas concurrencia, permisos, recuperación y salud en producción.
- `check`, `check --deploy`, revisión de migraciones y Ruff sin incidencias.
- Recopilación de archivos estáticos con manifiesto completada.
- Auditoría de los 12 paquetes de ejecución fijados: sin vulnerabilidades conocidas en la consulta realizada.
- Chart.js 4.4.8: sin avisos en la consulta al registro de npm.
- Imagen Docker construida y arrancada con usuario 10001: migraciones, estáticos, salud HTTP interna, redirección HTTPS, HSTS y acceso administrativo comprobados.

Estas comprobaciones no sustituyen una auditoría de penetración ni garantizan ausencia de vulnerabilidades futuras.

## Capacidad HTTP

- MySQL 8.4, Redis y Gunicorn con 4 procesos y 2 hilos.
- 1.200 cuentas y 12.000 evidencias temporales.
- 2.400 peticiones autenticadas, con 40 clientes concurrentes.
- Cero errores; duración 17,28 s; mediana 230,27 ms; percentil 95 de 649,69 ms.
- Rendimiento observado: 138,85 peticiones/s.

La prueba alterna el panel de usuario y la lista de evidencias. No representa 1.200 inicios de sesión simultáneos, envíos SMTP reales ni descargas masivas. Los datos temporales se eliminaron al terminar.

## Consultas y cola

Con 1.200 usuarios y 12.000 evidencias, las vistas administrativas, de evidencias y de reportes necesitaron 8, 7 y 9 consultas respectivamente. Publicar avisos para 1.200 usuarios utilizó 13 consultas, sin esperar envíos SMTP dentro de la petición web.

Se comprobaron dos publicaciones simultáneas de una misma novedad y dos trabajadores reclamando correo: no duplicaron avisos ni tomaron los mismos mensajes.

## Flujos verificados

- PIN de seis dígitos enviado a Mailpit, rechazo de PIN incorrecto, verificación y cambio de contraseña.
- La pantalla de nueva contraseña no está disponible antes de verificar el PIN.
- Inicio de sesión con la contraseña nueva.
- Publicación dirigida, creación de plazo, entrega asociada, revisión y aviso al propietario.
- Captura del aviso de vencimiento y preferencias de correo.
- Acceso denegado a archivos de otros usuarios y a descargas anónimas.
- Encabezados de seguridad, CSRF, límites, caducidad, reutilización y aislamiento de sesiones.
- Copia de MySQL y restauración en una base independiente con las seis cuentas de revisión.
- Renderizado de los roles y adaptación a escritorio/móvil.
- 129 vistas comprobadas en navegador, entre 320 y 1.440 píxeles, sin desbordamientos ni errores JavaScript.

Los mensajes de la revisión se capturaron localmente; no se enviaron a Internet. El acceso SMTP real queda sujeto a la credencial institucional.

## Repetición

```bash
python manage.py test --settings=SENNOVA.test_settings --noinput
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
ruff check .
python scripts/prueba_carga_http.py
```

Las pruebas de concurrencia requieren MySQL y utilizan una base de pruebas independiente. Los archivos de resultados y las credenciales locales se guardan en `.local/`, fuera del repositorio.
