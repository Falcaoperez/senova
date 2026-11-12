# Seguridad

## Acceso y recuperación

- Validación de contraseñas de Django, hash PBKDF2 y sesiones de servidor.
- PIN aleatorio de seis dígitos: el verificador almacena su hash; caduca en 10 minutos y admite hasta cinco fallos. Para la entrega asíncrona se conserva una copia cifrada temporalmente, nunca texto plano.
- La contraseña solo puede cambiarse después de verificar el PIN en la misma sesión. El permiso se consume al usarlo y una nueva solicitud invalida la anterior.
- Respuestas genéricas para solicitudes de recuperación, validación CSRF y límites por cuenta e IP compartidos en Redis.
- Los encabezados reenviados solo se aceptan desde las IP configuradas en `TRUSTED_PROXY_IPS`.
- Los límites por IP de login y registro son configurables para redes compartidas; el límite por identidad continúa aplicándose.
- El usuario y su correo comparten el contador de inicio de sesión. Los cambios de perfil y el cierre de otras sesiones también limitan los intentos de contraseña actual.
- Las solicitudes se vinculan mediante HMAC al identificador, hash de contraseña y correo de la cuenta. Un cambio realizado incluso desde el administrador nativo invalida el PIN y la autorización verificada anterior.
- Los correos de seguridad se encolan en la misma transacción que la solicitud o el cambio de credenciales. No se contacta SMTP desde la recuperación web, cuya respuesta no revela si existe la cuenta ni si el proveedor falla.
- El cierre de sesión y la revocación requieren POST y CSRF. Los cambios sensibles exigen contraseña actual y confirmación de la contraseña nueva.

## Cola de seguridad y sesiones

El contenido temporal de los PIN usa Fernet, con clave derivada mediante HKDF-SHA256 de `SECRET_KEY` y un contexto exclusivo. El contenido autenticado incluye solicitud, usuario y destinatario; no puede intercambiarse entre filas. `SECRET_KEY_FALLBACKS` permite una rotación controlada. No se expone el cifrado en las pantallas de administración y se borra al enviar, cancelar o agotar reintentos.

Los trabajadores reclaman los lotes con bloqueo y arrendamiento de MySQL. Antes del envío comprueban vigencia, estado de cuenta, correo y vinculación de credenciales. Las credenciales SMTP solo se transmiten con TLS/SSL. La aceptación SMTP no garantiza entrega en el buzón; el procesamiento ofrece entrega al menos una vez ante cortes, no exactamente una vez.

El centro de seguridad limita las operaciones al propietario, pide reautenticación y elimina las sesiones de MySQL y la caché. No publica claves de sesión. Las sesiones caducan por inactividad; el cambio o la recuperación de contraseña revoca las demás o todas, respectivamente. Las respuestas privadas y de recuperación usan `Cache-Control: private, no-store`.

## Datos y archivos

Las vistas comprueban el propietario o el rol revisor. Los archivos se sirven mediante respuestas autenticadas, con `nosniff` y caché privada desactivada; las URLs históricas de medios también requieren autorización. No hay un directorio público de archivos subidos.

Las plantillas escapan contenido, los gráficos usan JSON seguro y los CSV neutralizan celdas que podrían ejecutarse como fórmulas. Se aplica una política CSP con scripts, conexiones, fuentes y marcos limitados al propio origen.

## Configuración y operación

Las claves, credenciales y cuentas de revisión viven en `.env` y `.local/`, excluidos tanto de Git como de la imagen. La aplicación no crea administradores con contraseñas fijas. El contenedor se ejecuta como usuario sin privilegios.

Con `DJANGO_DEBUG=False` se exigen una clave privada y Redis. Se activan cookies seguras, redirección HTTPS y HSTS. La red de producción necesita el proxy HTTPS y los dominios reales configurados. `config/nginx.conf.example` muestra la configuración y mantiene los medios detrás de Django.

Se registran operaciones administrativas, verificaciones de PIN y cambios de revisión sin guardar datos de formularios ni secretos. Los logs rotan para limitar el uso de disco.

Las dependencias de ejecución están fijadas y se revisaron con `pip-audit`. Esta auditoría identifica vulnerabilidades conocidas de esos paquetes; no equivale a una prueba de penetración ni garantiza capacidad ilimitada.

## Administración y búsqueda

Los cambios de roles, estado, datos o contraseña de cuentas existentes requieren la contraseña actual del administrador, POST y CSRF. Los intentos se limitan por cuenta y por IP; los campos de contraseña se marcan como sensibles para los informes de errores. Los lotes admiten hasta 100 cuentas y se validan dentro de una transacción antes de aplicar cambios. Una cuenta de administración no puede desactivarse a sí misma ni retirar su propio rol; los usuarios con `is_staff` o `is_superuser` solo pueden modificarse desde este panel por un superusuario. El servidor aplica estas reglas también a las rutas históricas de cambios individuales.

Desactivar revoca las sesiones y cancela las recuperaciones pendientes, de modo que reactivar la cuenta no restaura esos accesos. Cambiar una contraseña desde el panel usa los validadores de Django con el usuario como contexto, invalida los PIN, cierra las otras sesiones y encola un aviso. Un cambio de correo se notifica a ambas direcciones.

La búsqueda global exige sesión válida, aplica la visibilidad de evidencias y limita avisos a su destinatario y plazos a sus grupos. Solo los administradores pueden buscar otras cuentas. Cada tipo devuelve pocos resultados y cada cuenta admite 60 búsquedas por minuto; un fallo del contador devuelve un error temporal sin ejecutar las consultas. Los resultados son privados, no se almacenan en cachés de respuesta y se insertan en el navegador con `textContent`. Abrir un resultado no ejecuta operaciones sensibles.
