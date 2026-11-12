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

## Correcciones e historial de evidencias

El propietario puede corregir una evidencia pendiente o rechazada; una aprobada permanece cerrada para ese flujo. La corrección conserva propietario, primera entrega, fecha de envío y límite aplicado. Si se cambia el proyecto, debe coincidir con el plazo asociado. Se puede conservar la clasificación original aunque el plazo se haya reclasificado después; también se conservan proyectos históricos o sin clasificar. Las observaciones del revisor no se sustituyen desde el formulario del propietario. Al guardar vuelve a revisión y se avisa al último revisor que conserve autorización, respetando sus preferencias de correo.

Las escrituras bloquean la fila de evidencia en MySQL y comparan su versión. Los formularios actuales y el administrador nativo incluyen esa versión; un cambio desactualizado se rechaza sin guardar. Las rutas históricas de revisión aún aceptan clientes que omitan la versión, pero serializan sus cambios y no duplican avisos cuando el estado ya coincide. El formulario de corrección exige siempre una versión válida.

`Gesicom_movimientoevidencia` registra actor, acción, estado, versión, detalle y fecha, con una identidad única por evidencia/versión. La consulta del historial aplica la misma visibilidad de la evidencia y tiene paginación. El administrador de Django solo permite consultar movimientos. Los registros anteriores se incorporan como un estado histórico, sin inventar autores ni revisiones pasadas.

Los formularios de creación, corrección y administración validan los adjuntos y los enlaces HTTP/HTTPS. Si un guardado con archivo falla, se retiran los archivos nuevos que no quedaron referenciados. Los adjuntos sustituidos se retiran después de confirmar la transacción, siempre que ningún otro registro los use. No se conserva un archivo completo de versiones de adjuntos; el historial registra los movimientos, no copias del contenido.

## Protección del administrador nativo

Un operador con permisos de edición de usuarios no puede modificar cuentas de superusuario, personal administrativo ni del grupo administrador. Los indicadores de privilegios, los grupos y los permisos individuales son de solo lectura para esos operadores. El superusuario conserva la gestión de esas cuentas, con protección frente a retirar su propio acceso o eliminarse en una operación masiva.

Los cambios de correo o contraseña y la desactivación invalidan recuperaciones y revocan sesiones también desde el administrador de Django. El cambio de contraseña usa una actualización limitada a ese campo; una edición de perfil no restaura un hash de contraseña antiguo si hubo un cambio concurrente. Se encolan avisos de cambios de credenciales sin abrir SMTP desde el formulario.

## Adjuntos y reintentos de alta

Los formularios nuevos incluyen un identificador firmado, válido durante 24 horas y vinculado al usuario. La firma no sustituye CSRF ni la autorización. Una restricción primaria UUID y el bloqueo del recibo en MySQL evitan que dos peticiones del mismo formulario creen dos evidencias. El reintento recupera el primer resultado sin modificarlo, incluso si ya no aparece el plazo en la lista de pendientes o el navegador perdió el archivo. Si el registro fue eliminado o reasignado, no se vuelve a crear ni se revela su nuevo destino. Abrir un formulario nuevo permite una entrega independiente. Por compatibilidad, los clientes históricos que omitan el identificador conservan el comportamiento de alta anterior.

Las cargas admiten un archivo por petición, hasta 10 MB, y rechazan archivos vacíos. Además de la extensión se comprueban firmas básicas de PDF, formatos binarios de Office, RAR y ZIP; las imágenes JPEG/PNG pasan por Pillow y se limitan a 25 millones de píxeles. Los documentos DOCX/XLSX/PPTX deben contener las partes esperadas, con límites para su directorio y sin cifrado. No se extraen comprimidos ni se ejecuta contenido en el servidor. Estas comprobaciones no constituyen un antivirus ni certifican que un documento sea válido en todas sus aplicaciones.

La vista privada reconoce el contenido antes de ofrecer una previsualización. Los formatos históricos desconocidos o incompatibles con su extensión se descargan sin ejecución como HTML. El texto se inserta con `textContent`, admite UTF-8, UTF-16/32 con marca y Windows-1252, y limita la lectura del origen a 64 KB. Un adjunto ausente conserva la evidencia y su historial; no se ofrece una vista rota.

El personal activo de Django con permiso explícito `view_envio` o `change_envio` puede consultar los adjuntos desde su administración. Esto no amplía la visibilidad de listas ni detalles públicos de GESICOM. Al eliminar una evidencia, el archivo se retira después de confirmar la transacción y solo si no quedan referencias; un rollback conserva el archivo. El administrador nativo no permite cambiar el plazo original de una evidencia existente y, al crear una nueva entrega asociada, valida destinatario/proyecto y conserva el límite aplicado.

## Actualizaciones de la campana

El resumen solo acepta lectura GET/HEAD y consulta los avisos de `request.user`; no admite elegir otro destinatario. La respuesta detallada limita títulos, fechas, lectura y rutas a los cuatro avisos más recientes. Las respuestas son privadas y no se almacenan en caché. La reutilización del conteo dura únicamente la petición actual y verifica la identidad de la cuenta.

El cliente valida la respuesta y las rutas del mismo origen, inserta los títulos como texto y conserva POST con CSRF al construir los formularios. No abre directamente el destino externo de una notificación; el servidor vuelve a comprobar su autorización al abrirla. Las actualizaciones se cancelan al ocultar la página, no se solapan y no mantienen viva una sesión inactiva. Un fallo de red conserva la última lista disponible sin mostrar detalles internos.

## Respuestas parciales y filtros del directorio

La representación parcial se selecciona únicamente en las vistas previstas y mediante una cabecera GET exacta. No selecciona una plantilla proporcionada por el usuario ni evita los decoradores de acceso, la visibilidad de evidencias o CSRF. Las acciones conservan sus formularios POST y la versión vigente; la respuesta mantiene `Vary: X-Workspace-Fragment` y el control de caché privado. Los resultados de la búsqueda o de otro usuario no se comparten entre peticiones.

El directorio valida los roles contra el catálogo que muestra, sin convertir identificadores arbitrarios a enteros de la base de datos. Cadenas de dígitos excesivas, símbolos numéricos no válidos, estados desconocidos o búsquedas demasiado largas producen un error visible y una lista vacía. La validación no cambia las reglas de las operaciones administrativas.

La protección de ediciones conserva los datos en memoria de la página. No copia observaciones, contraseñas ni permisos a almacenamiento persistente del navegador o al estado del historial. Cancelar una actualización no envía el formulario editado ni guarda sus cambios.
