# Verificación de la revisión

Fecha: 11 de noviembre de 2026. Las mediciones corresponden al entorno local de revisión.

## Pruebas y dependencias

- 96 pruebas automatizadas contra MySQL, incluidas concurrencia, permisos, recuperación y salud en producción.
- `check`, `check --deploy`, revisión de migraciones y Ruff sin incidencias.
- Recopilación de archivos estáticos con manifiesto completada.
- Auditoría de los 15 paquetes de ejecución fijados: sin vulnerabilidades conocidas en la consulta realizada.
- Chart.js 4.4.8: sin avisos en la consulta al registro de npm.
- Imagen Docker construida y arrancada con usuario 10001: migraciones, estáticos, salud HTTP interna, redirección HTTPS, HSTS y acceso administrativo comprobados.

Estas comprobaciones no sustituyen una auditoría de penetración ni garantizan ausencia de vulnerabilidades futuras.

## Capacidad HTTP

- MySQL 8.4, Redis y Gunicorn con 4 procesos y 2 hilos.
- 1.200 cuentas y 12.000 evidencias temporales.
- 2.400 peticiones autenticadas, con 40 clientes concurrentes.
- Cero errores; duración 15,97 s; mediana 187,42 ms; percentil 95 de 758,2 ms.
- Rendimiento observado: 150,31 peticiones/s.

La prueba alterna el panel de usuario y la lista de evidencias. No representa 1.200 inicios de sesión simultáneos, envíos SMTP reales ni descargas masivas. Los datos temporales se eliminaron al terminar.

## Consultas y cola

Con 1.200 usuarios y 12.000 evidencias, las vistas administrativas, de evidencias y de reportes necesitaron 9, 8 y 10 consultas respectivamente. Publicar avisos para 1.200 usuarios utilizó 13 consultas, sin esperar envíos SMTP dentro de la petición web.

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

Los mensajes de la revisión se capturaron localmente; no se enviaron a Internet. El acceso SMTP real queda sujeto a la credencial privada de Gmail.

## Actualización de Gmail y seguridad

Se comprobaron 30 pantallas adicionales en navegador, con los seis roles y escritorio/móvil: reautenticación, confirmación de contraseña, cierre de otras sesiones, recuperación en cola, remitente Gmail capturado en Mailpit, revocación después de recuperar y pantalla HTML de límite de intentos. No hubo errores JavaScript ni desbordamientos.

Las pruebas incluyen dos trabajadores enviando correos de seguridad sin repetir destinatarios, eliminación del contenido cifrado, reintentos, clave de cifrado anterior durante una rotación, vinculación del PIN a las credenciales y rechazo de sesiones previas a la nueva política. Gmail real requiere su contraseña de aplicación; la captura local no valida esa autenticación.

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

## Centro de operaciones e interacciones — 12 de noviembre de 2026

- 117 pruebas automatizadas con MySQL, incluidas las 96 de la revisión anterior. Se añadieron regresiones de aislamiento de búsqueda, autorización tras retirar roles, limitación por cuenta, caída del contador, transacciones masivas, cuentas protegidas, revocación al desactivar y datos históricos sin propietario o autor.
- 40 comprobaciones de navegador: seis roles en escritorio y móvil, y administración a 320, 768 y 1.440 píxeles. Sin errores JavaScript, CSP ni desbordamientos.
- Cierre de la búsqueda con Escape incluso con texto escrito y devolución de foco al botón.
- Gráfico real de 7/30/90 días, actualización sin recarga y navegación con Atrás; búsqueda con teclado, selección de resultados y cierre; filtros, paginación y observaciones tras sustituir filas; selección, cancelación, activación, desactivación y cambio de roles con confirmación.
- Filtros y formularios de administración comprobados con JavaScript desactivado. La tabla de datos del gráfico se genera en el servidor.
- Ruff, comprobación de migraciones, configuración de producción y recopilación de estáticos completados. No se requiere una migración nueva.
- Las nueve consultas de `database/consultas/diagnostico.sql` se ejecutaron contra MySQL; solo consultan metadatos y contadores.

La revisión utilizó dos cuentas, 33 evidencias y un plazo temporales. Se eliminaron al terminar; permanecen las seis cuentas y los datos de revisión previos. La contraseña solicitada para el administrador solo se aplicó a la base local y al archivo privado de credenciales. No forma parte del código, del workflow ni de la configuración SMTP.

El workflow conserva el contenedor Python y las conexiones internas a MySQL/Redis ya corregidas. La imagen de aplicación y la medición HTTP de capacidad descritas arriba corresponden a la revisión anterior; este bloque se comprobó con Gunicorn, MySQL y Redis, además de la validación automática del PR.

## Correcciones, historial y administrador nativo — 12 de noviembre de 2026

- 147 pruebas con MySQL, incluidas propiedad de registros, rechazo de versiones desactualizadas, conservación del plazo original, historial privado, preferencias de avisos, limpieza de archivos tras un fallo y pruebas concurrentes de corrección/aprobación.
- Se comprobó la protección de privilegios en el administrador nativo, la revocación de sesiones y PIN al desactivar, los avisos a ambas direcciones al cambiar correo, el cambio de contraseña propio sin perder la nueva sesión y la preservación de un hash actualizado durante una edición de perfil.
- 37 comprobaciones de navegador: ciclo de rechazo/corrección/aprobación con archivo, dos pestañas en conflicto, observaciones después de filtrar, privacidad, actualización desde Django admin, alta con redirección y corrección mediante teclado sin JavaScript. Seis roles en escritorio/móvil y detalle/formulario a 320, 768 y 1.440 píxeles, sin errores JavaScript, CSP ni desbordamientos.
- La migración 0013 se aplicó al MySQL de revisión e incorporó el registro existente al historial. La prueba de datos históricos confirma que no altera fechas, estado ni adjuntos anteriores.
- Diez consultas SQL de diagnóstico ejecutadas correctamente. Ruff, comprobación de migraciones, producción y estáticos completados.

La comprobación externa de `smtp.gmail.com:587` devolvió `ENETUNREACH` (red inaccesible) antes de autenticar. No se enviaron mensajes reales y la credencial no quedó validada frente a Google. El comando ahora distingue ese fallo de un rechazo de contraseña. La configuración privada sigue fuera del historial Git; las pruebas de correo utilizan transporte local.

Los datos de navegador fueron temporales: dos cuentas, un plazo y dos evidencias, con sus movimientos y adjunto. Se retiraron al finalizar. Se conservan las seis cuentas y los datos de revisión previos; el registro de evidencia anterior cuenta ahora con su movimiento histórico.

## Estabilidad de las pruebas de límites

La ejecución posterior a integrar el PR de evidencias cruzó una frontera de diez minutos durante la prueba de usuario/correo: el contador entró en otra ventana y la expectativa anterior dejó de corresponder con esa petición. La prueba ahora fija únicamente el reloj del middleware, manteniendo real el de la caché. Un caso adicional comprueba el bloqueo al final de una ventana, `Retry-After: 1` y el acceso en la siguiente. La batería completa consta de 148 pruebas; el comportamiento del servidor no se modifica con esta corrección.

## Agenda, cumplimiento y comunicaciones — 12 de noviembre de 2026

- 186 pruebas con MySQL (38 adicionales): seguimiento por destinatario, conservación del límite original, agrupación sin duplicados, filtros y CSV seguro, bandeja individual y masiva, CSRF, permisos, contraseña actual y límites de intentos. El reloj de la prueba nueva de límites también se fija solo en el middleware.
- Dos administradores recordando simultáneamente no duplican avisos; dos editores del mismo plazo producen un guardado y un conflicto. Se comprueban el guardado sin cambios, el archivo de plazos vencidos y la misma política desde Django admin. El campo de fecha nativo ya no mezcla un campo de fecha dividida con un control de fecha único.
- El trabajador descarta correo pendiente después de una entrega, cambio de versión, retiro de grupos, desactivación o cambio de preferencias. Las regresiones verifican que una fila eliminada no reaparece y que una cancelación concurrente no se vuelve a poner en cola tras un fallo SMTP. El latido se mantiene durante lotes largos.
- 55 comprobaciones en Chromium con los seis roles en escritorio y móvil: agenda, bandeja, seguimiento, filtros dinámicos y navegación Atrás, exportación filtrada, recordatorio adicional, lectura tras sustituir filas, dos pestañas en conflicto, administrador nativo y archivo con apertura de aviso antiguo. Agenda, evidencias asociadas y selección de notificaciones comprobadas sin JavaScript.
- Otras ocho comprobaciones de la agenda a 320, 390, 600, 768 y 1.440 píxeles confirman que la tabla personal se adapta a tarjetas y deja visibles las acciones. Sin errores JavaScript, CSP ni desbordamientos en la revisión de los paneles.
- Con 1.200 destinatarios y 12.000 evidencias, el seguimiento paginado utilizó 10 consultas y unos 135 ms en la ejecución completa local. La selección de grupos usa subconsultas sin duplicar personas y el conteo excluye las subconsultas de revisión que solo necesita la página visible. Usuarios, evidencias y reportes conservaron 9, 8 y 10 consultas, respectivamente. Estas cifras describen este entorno y conjunto de datos, no una garantía de latencia de producción.
- Migraciones `Gesicom.0014` y `notificaciones.0002` aplicadas al MySQL local tras una copia privada. Ruff, ausencia de migraciones pendientes, comprobación de producción y recopilación de estáticos correctos. Doce consultas SQL de diagnóstico completadas.

Las tres cuentas, tres plazos, dos evidencias y la publicación usados en navegador se retiraron con sus avisos. Se conservaron las seis cuentas, la evidencia con su movimiento histórico, los dos plazos y los ocho avisos previos. Los correos de pruebas utilizan captura local; Gmail continúa pendiente de validación de acceso y autenticación SMTP en el entorno de despliegue.

## Reportes accesibles y permisos de grupos — 12 de noviembre de 2026

- 216 pruebas con MySQL (30 adicionales): períodos históricos, meses inválidos o invertidos, filtros comunes, aislamiento por rol/propietario, proyectos históricos y sin clasificar, límites de calendario, CSV Unicode y protección de fórmulas. Las columnas previas del CSV se conservan y se añaden los datos de seguimiento.
- El CSV trimestral y el gráfico utilizan la misma serie, hasta el mes final elegido. Las pruebas confirman una agregación acotada tanto para uno como para doce trimestres. Con 12.000 evidencias, la descarga completa utilizó cinco consultas y unos 450 ms en este entorno. Reportes conservó diez consultas; la lista de evidencias utilizó nueve, incluida la consulta de clasificaciones históricas autorizadas.
- Las pruebas de permisos cubren contraseña y revisión obligatorias, actualización parcial sin perder otros permisos, rechazo completo de campos desconocidos, permisos homónimos de otro modelo, CSRF, límites por cuenta, autorización retirada, grupos protegidos y auditoría sin duplicar movimientos al guardar sin cambios.
- Dos editores concurrentes del mismo grupo producen un guardado y un conflicto. La edición nativa comparte esa revisión, confirma la contraseña y conserva los grupos del sistema ante renombrado, eliminación y selección mixta. Un editor de Django no puede elevar sus privilegios modificando un grupo que contenga cuentas de personal.
- 41 comprobaciones en Chromium: seis roles en reportes/evidencias a 390 y 1.440 píxeles; reportes/permisos de administración a 320, 768 y 1.440 píxeles; actualización de gráficos sin duplicar instancias; Atrás; proyectos históricos; descarga filtrada; error de rango; impresión; contraseña; conflictos entre pestañas; edición nativa y bloqueo de grupos protegidos. Reportes y filtros comprobados sin JavaScript.
- Diez comprobaciones adicionales verifican filtros al pulsar segmentos, una ventana histórica de doce trimestres en cinco anchos, restauración del valor predeterminado de trimestres, datos disponibles si no carga Chart.js y guardado de permisos sin JavaScript. El PDF de prueba contiene las cuatro tablas de datos. Se corrigió una regla anterior que las ocultaba al imprimir.
- Ruff, configuración de producción, estáticos y trece consultas SQL de diagnóstico completados. No hay nuevas migraciones ni tablas duplicadas.

Los datos visuales son temporales: tres cuentas, un grupo y 38 evidencias. Se retiran con sus sesiones y avisos al finalizar la revisión; las cuentas y registros previos se conservan. Las capturas utilizan nombres de ejemplo. Esta comprobación no activa Gmail real: la validación de acceso y autenticación SMTP sigue pendiente en el despliegue.

## Adjuntos, reintentos y conservación de entregas — 12 de noviembre de 2026

- 249 pruebas con MySQL (33 adicionales): formatos y contenido, imágenes dañadas o de resolución excesiva, estructura de Office, archivos vacíos, límites, acceso privado del personal autorizado, rutas compartidas y adjuntos ausentes. La vista de texto conserva las tildes y limita la lectura; la descarga mantiene el archivo completo.
- Las pruebas de alta cubren firma vinculada a la cuenta, caducidad, reintento después de entregar o archivar el plazo, pérdida del archivo en el navegador, datos distintos en el reintento y eliminación o reasignación de la evidencia original. Dos peticiones concurrentes del mismo UUID producen una evidencia, un archivo, un recibo y un movimiento. Un fallo revierte la escritura y permite volver a intentarlo.
- La retirada de archivos se comprueba después del commit, con referencias compartidas, rollback y eliminación de cuentas. El límite de un archivo por petición se verifica también en el servidor.
- La administración conserva plazos y fechas de evidencias existentes; una entrega nueva registra el límite original y exige un plazo activo, asignado y pendiente para su destinatario/proyecto. Se verifica que las correcciones preservan clasificaciones históricas, incluidos registros sin proyecto y plazos reclasificados después.
- 60 comprobaciones en Chromium: seis roles en formulario/listado a 390 y 1.440 píxeles; detalle y corrección a 320, 768 y 1.440; selección con imagen, quitar selección, arrastrar, errores de formato/contenido, foco y enlaces del resumen, envío asociado a plazo, reintentos sin archivo, texto largo y Windows-1252, adjunto ausente, PDF privado, permiso nativo de consulta y proyecto histórico. El alta identificada y el texto completo se comprobaron sin JavaScript. Nombres largos y selector de archivos se revisaron entre 320 y 1.440 píxeles. Sin desbordamientos, errores JavaScript ni infracciones CSP.
- Copia privada de MySQL comprobada y migración `Gesicom.0015_solicitudes_adjuntos` aplicada. El índice por nombre de archivo y los recibos no modifican registros anteriores. Ruff, migraciones, configuración de producción, estáticos, sintaxis JavaScript y catorce consultas SQL de diagnóstico completados.

Se retiraron tres cuentas, un grupo, un plazo y nueve evidencias temporales, con sus sesiones, recibos, avisos y archivos. Se conservaron las seis cuentas, la evidencia con su movimiento histórico, los dos plazos y los ocho avisos de revisión previos. El trabajador local utiliza captura de correo; esta revisión no envía mensajes reales ni valida autenticación de Gmail.
