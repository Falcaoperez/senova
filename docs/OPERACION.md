# Operación

## Notificaciones

El alta de una novedad o plazo crea avisos en lotes y prepara la cola de correo. La petición web no espera el envío de mensajes a todos los destinatarios.

```bash
python manage.py procesar_notificaciones --continuo --intervalo 30 --lote 50
```

El trabajador genera recordatorios y vencimientos, omite usuarios que ya entregaron el reporte y reclama mensajes con bloqueos de MySQL. Dos trabajadores no toman el mismo lote activo. Los errores de envío se reintentan con espera creciente hasta cinco veces. Después pueden reactivarse desde la página administrativa de Novedades.

El estado visible del procesador se guarda en Redis. La bandeja funciona aunque SMTP esté temporalmente indisponible. Las preferencias se vuelven a comprobar justo antes de enviar. Los avisos de recuperación usan el transporte SMTP directamente y no se confirman si falla.

La cola ofrece entrega al menos una vez: un corte justo después de la aceptación del proveedor y antes de registrar el resultado puede producir una repetición. Los avisos internos por novedad/fase de plazo sí se deduplican con restricciones de la base de datos.

## Plazos y entregas

Las fechas se muestran en `America/Bogota`. El usuario puede asociar una evidencia a un plazo de su grupo y proyecto. Se conserva la fecha límite aplicable al registro y se identifica una entrega tardía. Entregar el reporte detiene los avisos pendientes de ese plazo; la aprobación se gestiona por separado.

Cambiar la fecha de un plazo incrementa su versión y permite emitir los avisos de la nueva programación. Para una entrega distinta, crea otro plazo.

## Correo de producción

La cuenta remitente debe existir y tener autorización SMTP. El perfil local de Mailpit captura correos; no valida el acceso a Microsoft 365 ni envía mensajes reales. Para producción, usa `compose.yml` sin el perfil de desarrollo y añade una credencial autorizada en la configuración privada.

Si se utiliza OAuth2, la renovación del token corresponde al servicio de identidad del despliegue. Comprueba la conexión con `python manage.py comprobar_correo`; no imprime secretos ni envía mensajes.

## Capacidad

`WEB_WORKERS` y `WEB_THREADS` acotan la concurrencia y las conexiones. Los listados se paginan y las estadísticas se agrupan en SQL. El número de cuentas almacenadas no se convierte en el número de procesos o conexiones abiertos.

La capacidad real depende del hardware, consultas, conexiones SMTP y tamaño de archivos. Consulta las mediciones en `VERIFICACION.md` antes de ajustar el número de trabajadores o el límite de conexiones de MySQL.

## Salud y copias

`/health/` devuelve un estado mínimo tras comprobar base de datos y caché. No muestra credenciales ni detalles internos. Docker utiliza esta ruta para supervisar la aplicación.

Realiza copias de MySQL y del volumen de medios. Verifica una restauración independiente antes de reemplazar datos de una instalación existente.
