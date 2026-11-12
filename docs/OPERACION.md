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

Cambiar un plazo (fecha, indicaciones, destinatarios o estado) incrementa su revisión y su versión de avisos. Guardar sin cambios no reenvía avisos. Las pestañas con una revisión anterior deben recargar antes de guardar. Para una entrega distinta, crea otro plazo.

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


## Agenda y seguimiento de entregas

Los paneles personales destacan los plazos vencidos sin entrega y las evidencias propias rechazadas. Coordinación y dinamización disponen de una cola de revisión ordenada por primera entrega. “Mis plazos” permite buscar y filtrar por proyecto y estado; “Ver evidencias” conserva el plazo y el propietario al aplicar otros filtros.

En **Plazos de reportes → Seguimiento**, administración consulta los destinatarios activos actuales, entregas a tiempo, tardías y pendientes. Se cuentan personas, aunque una persona tenga varias evidencias. La revisión mostrada corresponde a la evidencia más reciente. El CSV exporta todos los resultados filtrados, sin limitarse a la página; neutraliza fórmulas de hoja de cálculo y no se almacena en caché.

**Preparar recordatorios** exige contraseña actual, CSRF y la revisión vigente. Crea un aviso adicional por persona pendiente y versión del plazo, respetando sus preferencias de correo. Repetir la acción no duplica avisos y no adelanta ni sustituye los recordatorios automáticos. Los filtros de la tabla no limitan esta acción: siempre cubre a quienes faltan en todo el plazo. Las peticiones sensibles tienen límites por cuenta e IP.

**Archivar** conserva las evidencias, retira el plazo de las agendas y cancela su cola pendiente. También funciona para plazos vencidos. Una edición desde Django admin utiliza el mismo servicio de versiones, grupos y avisos.

El trabajador vuelve a comprobar cuenta, preferencias, destinatarios, disponibilidad y versión del plazo antes de cada envío. Si alguien ya entregó, cancela sus recordatorios pendientes. `cancelado` identifica estos descartes normales y no se reintenta como un fallo SMTP. Los correos ya aceptados por el transporte no se pueden retirar. Una modificación concurrente durante el intercambio SMTP puede llegar después de la comprobación; queda registrado el resultado real de la aceptación. El latido del trabajador se renueva durante lotes largos.

## Organización de la bandeja

La búsqueda por título o mensaje, los filtros de tipo y lectura y la paginación comparten la misma consulta autorizada. Cada usuario puede cambiar el estado individual, seleccionar avisos de la página (máximo 100 por petición) o marcar todos los resultados filtrados. Una selección con identificadores ajenos se rechaza completa. Al consultar un aviso se comprueba el acceso actual a su destino; si fue archivado, eliminado o dejó de estar asignado, la bandeja explica el motivo.

Al actualizar, aplica `Gesicom.0014` (índice de plazo/usuario/primera entrega) y `notificaciones.0002` (revisión, actualización y estados de seguimiento/cancelación), recoge estáticos y reinicia web y trabajador. No se cambian fechas ni límites de evidencias previas. La columna `version` de avisos y `revision` de edición tienen finalidades distintas; las escrituras deben pasar por `notificaciones.plazos` para mantenerlas coherentes.

## Reportes y exportaciones

La lista de evidencias, los reportes y sus CSV comparten `Gesicom.filtros`. Se puede buscar por nombre, tipo u observaciones y combinar proyecto, estado, meses, propietario y plazo. Los proyectos históricos y los registros sin proyecto permanecen consultables. Un filtro inválido muestra errores y no devuelve registros; las descargas con filtros inválidos responden HTTP 400, sin generar un CSV de toda la base.

La serie trimestral termina en el trimestre del mes final elegido. Sin fecha final, utiliza el trimestre actual. Pantalla y CSV trimestral utilizan la misma agregación SQL y de 1 a 12 trimestres. Las aprobadas reflejan el estado actual de las evidencias registradas en cada trimestre; no se cuentan como si fueran la fecha de aprobación. El total general corresponde a todos los registros filtrados y se indica cuando la ventana trimestral solo muestra una parte.

Los gráficos permiten filtrar por proyecto o estado. Los enlaces de las tablas ofrecen la misma acción con teclado o sin JavaScript. Los filtros conservan el historial del navegador. Cada gráfico incluye una tabla de datos; la impresión utiliza estas tablas. Si Chart.js no está disponible, los datos siguen siendo consultables.

El CSV de evidencias conserva primero las seis columnas históricas y añade estado, usuario, primera entrega, plazo, límite original y entrega tardía. Se ordena según la consulta y recorre los registros en lotes de 500, sin acumular las instancias ni el documento CSV completo en Django. El controlador de MySQL puede mantener sus propios búferes de filas. Se usa UTF-8 con marca BOM para las tildes en hojas de cálculo, neutralización de fórmulas y `Cache-Control: no-store`. El CSV trimestral usa el mismo período que el gráfico. El seguimiento de plazos reutiliza la misma respuesta CSV.

## Permisos de grupos

El panel conserva los seis permisos históricos, con etiquetas que describen su función real. “Sin asignar” retira la concesión del grupo; no deniega permisos que una persona obtenga de otros grupos o de asignaciones individuales. El acceso a Django admin también requiere una cuenta de personal autorizada. Los permisos nativos no sustituyen los roles que gobiernan los paneles de GESICOM.

Guardar requiere contraseña actual y una revisión calculada sobre el grupo y sus permisos completos. La actualización bloquea el grupo, vuelve a comprobar la autorización y valida todo el formulario antes de escribir. Una pestaña antigua se rechaza; guardar sin cambios no genera otro movimiento de auditoría. Los permisos ajenos al catálogo se conservan al usar el panel de GESICOM. Se aceptan los nombres de campo históricos y el valor anterior de retirada para mantener compatibilidad.

Solo un superadministrador puede modificar el grupo `administrador` o un grupo con cuentas de personal/superusuario. Django admin utiliza la misma política, contraseña y revisión para añadir o editar grupos. Los seis grupos del sistema no se pueden renombrar ni eliminar desde esa administración, incluso en lotes mixtos. Los intentos de confirmación se limitan por identidad e IP. La auditoría registra actor y ruta, sin contraseña ni contenido de la petición.

Este bloque no necesita migraciones ni nuevas tablas de permisos. Después de actualizar, recoge los estáticos y reinicia web y trabajador para cargar los módulos compartidos.
