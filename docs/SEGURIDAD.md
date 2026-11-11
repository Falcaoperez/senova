# Seguridad

## Acceso y recuperación

- Validación de contraseñas de Django, hash PBKDF2 y sesiones de servidor.
- PIN aleatorio de seis dígitos: solo se guarda su hash; caduca en 10 minutos y admite hasta cinco fallos.
- La contraseña solo puede cambiarse después de verificar el PIN en la misma sesión. El permiso se consume al usarlo y una nueva solicitud invalida la anterior.
- Respuestas genéricas para solicitudes de recuperación, validación CSRF y límites por cuenta e IP compartidos en Redis.
- Los encabezados reenviados solo se aceptan desde las IP configuradas en `TRUSTED_PROXY_IPS`.
- Los límites por IP de login y registro son configurables para redes compartidas; el límite por identidad continúa aplicándose.

## Datos y archivos

Las vistas comprueban el propietario o el rol revisor. Los archivos se sirven mediante respuestas autenticadas, con `nosniff` y caché privada desactivada; las URLs históricas de medios también requieren autorización. No hay un directorio público de archivos subidos.

Las plantillas escapan contenido, los gráficos usan JSON seguro y los CSV neutralizan celdas que podrían ejecutarse como fórmulas. Se aplica una política CSP con scripts, conexiones, fuentes y marcos limitados al propio origen.

## Configuración y operación

Las claves, credenciales y cuentas de revisión viven en `.env` y `.local/`, excluidos tanto de Git como de la imagen. La aplicación no crea administradores con contraseñas fijas. El contenedor se ejecuta como usuario sin privilegios.

Con `DJANGO_DEBUG=False` se exigen una clave privada y Redis. Se activan cookies seguras, redirección HTTPS y HSTS. La red de producción necesita el proxy HTTPS y los dominios reales configurados. `config/nginx.conf.example` muestra la configuración y mantiene los medios detrás de Django.

Se registran operaciones administrativas, verificaciones de PIN y cambios de revisión sin guardar datos de formularios ni secretos. Los logs rotan para limitar el uso de disco.

Las dependencias de ejecución están fijadas y se revisaron con `pip-audit`. Esta auditoría identifica vulnerabilidades conocidas de esos paquetes; no equivale a una prueba de penetración ni garantiza capacidad ilimitada.
