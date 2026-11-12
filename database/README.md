# Base de datos

El esquema se crea únicamente con las migraciones de Django. No se mantiene una segunda definición SQL de las tablas.

```bash
python manage.py migrate
```

MySQL utiliza InnoDB, UTF-8 completo (`utf8mb4`), modo estricto, claves foráneas e índices para usuario/fecha, proyecto/fecha, estado y notificaciones pendientes. La conexión de aplicación está limitada a su esquema. Las contraseñas de MySQL y Redis se generan en `.env`, fuera de Git.

## Entidades

- `auth_user`, grupos y permisos: cuentas y autorización.
- `Gesicom_envio`: evidencias, autor, archivo/enlace, revisión y asociación con el plazo.
- `Gesicom_solicitudenvio`: recibos internos para recuperar el resultado de un reintento del mismo formulario.
- `notificaciones_plazoreporte`: destinatarios, proyecto, fecha límite, recordatorio y versión.
- `notificaciones_novedad`: publicaciones y grupos destinatarios.
- `notificaciones_notificacion`: bandeja individual y fecha de lectura.
- `notificaciones_correopendiente`: estado, arrendamiento y reintentos de correo.
- `notificaciones_preferenciasnotificacion`: preferencias personales.
- `cuentas_passwordresettoken`: hash del PIN, caducidad, intentos y verificación.
- `cuentas_registroseguridad`: actor, acción, fecha e IP, sin contraseñas ni cuerpos de petición.

Un índice único sobre el correo normalizado evita duplicados incluso con altas simultáneas; permite cuentas de mantenimiento sin correo. Una restricción impide que una evidencia esté aprobada y rechazada a la vez. Cada aviso de novedad o fase de un plazo tiene una identidad única por destinatario.

## Actualización de instalaciones anteriores

Las migraciones conservan las tablas y sus relaciones. Si detectan correos duplicados, se detienen antes de crear el índice para que se corrijan las cuentas afectadas. Las solicitudes del mecanismo antiguo de recuperación se invalidan. La cuenta automática histórica `admin@example.com`, si aún conserva la contraseña pública original, se desactiva; no se elimina su información.

## Copias y restauración

```bash
sh scripts/backup_mysql.sh
```

El respaldo consistente se guarda comprimido dentro de `.local/backups/`, con permisos privados. Las copias y credenciales nunca se añaden a Git. Las restauraciones se verifican primero en una base vacía independiente; después se compara el número de cuentas y registros. En la revisión se comprobó una restauración con las seis cuentas locales.

`preparar_pruebas.sql` crea y autoriza exclusivamente la base `test_senova` para las pruebas locales con los nombres predeterminados. No es parte del arranque de producción.

## Navegación del esquema y diagnóstico

- [Relaciones, tablas e integridad](documentacion/modelo.md).
- [Consultas de diagnóstico de solo lectura](consultas/diagnostico.sql): motor, cotejamiento, índices y contadores de operación. Selecciona la base de la instalación antes de ejecutarlas; las cifras de `information_schema.tables.table_rows` son estimaciones.
- `cuentas_correoseguridad` contiene el estado de entrega de PIN y cambios de credenciales; `cuentas_sesionusuario` enlaza cada sesión con su propietario. Sus datos confidenciales no aparecen en el diagnóstico.

El SQL de diagnóstico y la documentación pueden versionarse. Los respaldos reales, datos personales, contraseñas y credenciales permanecen en almacenamiento privado. Consulta también [la organización del proyecto](../docs/ARQUITECTURA.md).

`Gesicom_movimientoevidencia` conserva los movimientos de creación, corrección, revisión y observaciones. La versión única por evidencia evita registrar dos cambios con la misma identidad. La primera entrega y el límite aplicado permanecen en `Gesicom_envio`; la fecha de corrección se consulta en el historial.

La migración `Gesicom.0015_solicitudes_adjuntos` añade recibos con UUID único y un índice de nombres de archivo. No rellena recibos históricos ni modifica las evidencias existentes. Los recibos sin evidencia se conservan como constancia de un formulario ya procesado; no deben purgarse automáticamente junto con sus adjuntos.
