# Operación

## Notificaciones

El alta de una novedad o plazo crea avisos en lotes y prepara la cola de correo. La petición web no espera el envío de mensajes a todos los destinatarios.

```bash
python manage.py procesar_notificaciones --continuo --intervalo 30 --lote 50
```

El trabajador genera recordatorios y vencimientos, omite usuarios que ya entregaron el reporte y reclama mensajes con bloqueos de MySQL. Dos trabajadores no toman el mismo lote activo. Los errores de envío se reintentan con espera creciente hasta cinco veces. Después pueden reactivarse desde la página administrativa de Novedades.

El estado visible del procesador se guarda en Redis. La bandeja funciona aunque SMTP esté temporalmente indisponible. Las preferencias se vuelven a comprobar justo antes de enviar. El mismo trabajador procesa primero la cola de seguridad: PIN y avisos de cambios de credenciales. Mientras hay lotes listos, continúa sin esperar el intervalo de reposo.

Los PIN no se envían dentro de la petición web. La respuesta de recuperación es genérica incluso si SMTP falla. La cola de seguridad reintenta tres veces con espera creciente, respeta la caducidad de 10 minutos y borra el contenido cifrado al enviar, cancelar o agotar los intentos. Un PIN caducado necesita una solicitud nueva; los errores ordinarios de novedades siguen el procedimiento de reactivación anterior.

La cola ofrece entrega al menos una vez: un corte justo después de la aceptación del proveedor y antes de registrar el resultado puede producir una repetición. Los avisos internos por novedad/fase de plazo sí se deduplican con restricciones de la base de datos.

## Plazos y entregas

Las fechas se muestran en `America/Bogota`. El usuario puede asociar una evidencia a un plazo de su grupo y proyecto. Se conserva la fecha límite aplicable al registro y se identifica una entrega tardía. Entregar el reporte detiene los avisos pendientes de ese plazo; la aprobación se gestiona por separado.

Cambiar la fecha de un plazo incrementa su versión y permite emitir los avisos de la nueva programación. Para una entrega distinta, crea otro plazo.

## Correo de producción

El remitente es `santiagoocoy2025@gmail.com` por `smtp.gmail.com:587`, con STARTTLS y una contraseña de aplicación de Google. Se requiere verificación en dos pasos. El perfil local de Mailpit captura correos; no valida la autenticación de Gmail ni envía mensajes reales. Para producción, usa `compose.yml` sin el perfil de desarrollo y añade la credencial privada.

Si se utiliza OAuth2, la renovación del token corresponde al servicio de identidad del despliegue. Comprueba la conexión con `python manage.py comprobar_correo`; no imprime secretos ni envía mensajes.

Las cuentas personales de Gmail tienen cuotas de envío. Dimensiona el volumen de avisos antes de usarlo con todos los usuarios; la cola no aumenta los límites del proveedor. Las direcciones `example.invalid` de las cuentas de revisión solo sirven con la captura local.

## Sesiones y cambios de cuenta

`/mi-cuenta/seguridad/` muestra las sesiones del usuario y permite cerrarlas mediante POST, CSRF y contraseña actual. La eliminación alcanza la caché y MySQL. El inicio de sesión registra la sesión antes de la primera navegación. `SESSION_IDLE_TIMEOUT` controla la caducidad por inactividad, con 1.800 segundos por defecto; la actividad visible se actualiza como máximo una vez por minuto para limitar escrituras.

Al cambiar la contraseña desde el perfil se conserva la sesión actual y se cierran las demás. Una recuperación cierra todas las sesiones autenticadas y solicita ingresar de nuevo. Los cambios sensibles invalidan las solicitudes de recuperación y generan avisos al correo anterior y al actual.

Ejecuta `python manage.py clearsessions` periódicamente para retirar sesiones caducadas de MySQL; sus registros asociados se eliminan en cascada.

La primera instalación de esta política exige iniciar sesión de nuevo: las sesiones anteriores que todavía no estaban registradas no se aceptan, aunque quedaran en caché. Esto permite que el cierre de otras sesiones abarque todos los accesos admitidos por la nueva versión.

Las consultas automáticas de la campana no prolongan la sesión. Cuando el servidor responde que el acceso terminó, la interfaz vuelve a la pantalla de ingreso.

## Actualizar esta versión

Instala las dependencias, ejecuta `python manage.py migrate --noinput` y `python manage.py collectstatic --noinput`, y reinicia aplicación y trabajador. Las migraciones añaden la cola, el registro de sesiones y la vinculación de las solicitudes a las credenciales. Los PIN anteriores a esa vinculación dejan de ser válidos: debe solicitarse uno nuevo. No se eliminan cuentas ni evidencias.

## Capacidad

`WEB_WORKERS` y `WEB_THREADS` acotan la concurrencia y las conexiones. Los listados se paginan y las estadísticas se agrupan en SQL. El número de cuentas almacenadas no se convierte en el número de procesos o conexiones abiertos.

La capacidad real depende del hardware, consultas, conexiones SMTP y tamaño de archivos. Consulta las mediciones en `VERIFICACION.md` antes de ajustar el número de trabajadores o el límite de conexiones de MySQL.

## Salud y copias

`/health/` devuelve un estado mínimo tras comprobar base de datos y caché. No muestra credenciales ni detalles internos. Docker utiliza esta ruta para supervisar la aplicación.

Realiza copias de MySQL y del volumen de medios. Verifica una restauración independiente antes de reemplazar datos de una instalación existente.

## Validación de GitHub Actions

El workflow vigente es `.github/workflows/validacion.yml`. El trabajo corre dentro de `python:3.12-bookworm`; los servicios MySQL y Redis se resuelven como `mysql` y `redis`. No necesita publicar sus puertos en el servidor de GitHub ni buscar contenedores con `docker ps`.

Esta configuración evita que la instalación de las bibliotecas de MySQL interactúe con un servidor MySQL preinstalado del runner. La preparación de `test_senova` usa el cliente dentro del contenedor de trabajo. No se ocultan fallos de paquetes con `dpkg --configure -a || true`: si una dependencia no se instala, la validación debe detenerse.

Las claves que empiezan por `ci-` solo pertenecen a servicios efímeros de pruebas. Los secretos de la instalación y la contraseña de revisión no se incluyen en el workflow. Cada PR a `develop` verifica Ruff, migraciones, pruebas MySQL, configuración de producción, estáticos y dependencias antes de integrarse.

## Interacciones del espacio de trabajo

- `Ctrl K`, `Cmd K` o `/` abre la búsqueda; flechas y Enter eligen un resultado y Escape cierra.
- Los filtros de usuarios y evidencias conservan su estado en la URL y permiten volver con el navegador. Los formularios GET continúan funcionando sin JavaScript.
- El centro de operaciones permite períodos de 7, 30 o 90 días. El gráfico cuenta la fecha de envío de las evidencias y ofrece una tabla de datos accesible, también sin JavaScript.
- La selección de cuentas se limita a la página visible. El cambio de roles solo afecta los desplegables modificados; puede conservar varios roles existentes. Las cuentas protegidas no se pueden modificar por un administrador sin privilegios de superusuario.

## Corrección y revisión de evidencias

1. El propietario abre el detalle de una evidencia pendiente o rechazada y selecciona **Corregir evidencia**.
2. Actualiza nombre, tipo, archivo o enlace y explica qué corrigió. El plazo y la primera entrega se conservan.
3. Al guardar vuelve a revisión. El último revisor autorizado recibe un aviso en su bandeja y, si lo permite, en la cola de correo.
4. El equipo consulta el contenido y el historial antes de aprobar o rechazar. Una pestaña desactualizada debe recargar la versión vigente.

La primera entrega sigue determinando el cumplimiento del plazo; las correcciones posteriores muestran su fecha propia en el historial. Una corrección no crea una entrega nueva ni cambia retroactivamente el límite aplicado.

El registro inicial redirige al detalle para que actualizar el navegador no reenvíe el formulario. Las correcciones funcionan sin JavaScript y reutilizan el mismo formulario. El administrador nativo participa en el control de versiones y en el historial.

La migración `Gesicom.0013` añade los campos de versión y el historial. Crea un movimiento de estado histórico para las evidencias existentes en lotes de 500; conserva sus datos y adjuntos. Realiza una copia de seguridad antes de actualizar una instalación con datos y aplica `python manage.py migrate --noinput` con el procedimiento habitual de despliegue.

## Diagnóstico de SMTP

`python manage.py comprobar_correo` comprueba conexión y autenticación sin enviar mensajes. `--solo-configuracion` valida los parámetros sin conectarse. El comando distingue rechazo de credenciales, error de resolución, espera agotada, certificado TLS no confiable y falta de acceso de red. Ninguno de esos mensajes muestra la contraseña ni la respuesta privada del proveedor.

Una validación de configuración no demuestra que el servidor acepte la cuenta. Si el entorno no tiene acceso a `smtp.gmail.com:587`, habilita esa salida en el despliegue antes de comprobar la autenticación. Gmail requiere una contraseña de aplicación de Google o un token OAuth2 vigente; la contraseña normal de acceso no sustituye esa autorización.
