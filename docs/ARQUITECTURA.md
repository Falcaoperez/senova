# Organización del proyecto

| Carpeta | Responsabilidad |
| --- | --- |
| `SENNOVA/` | Configuración activa, rutas y middleware HTTP |
| `config/` | Configuración de Gunicorn |
| `Gesicom/` | Evidencias, reportes, páginas y recursos visuales compartidos |
| `Gesicom/forms.py` | Validaciones compartidas de creación y corrección, con compatibilidad para el enlace histórico |
| `Gesicom/services.py` | Transacciones de evidencia, control de versiones, historial y ciclo de sustitución de adjuntos |
| `Gesicom/solicitudes.py` | Firma y comprobación de identificadores de formulario vinculados a la cuenta |
| `Gesicom/adjuntos.py` | Formatos admitidos, comprobaciones de contenido y lectura limitada de texto |
| `Gesicom/archivos.py` | Acceso autorizado a adjuntos y metadatos de disponibilidad |
| `Gesicom/interfaz.py` | Renderizado completo o del contenido del panel con las mismas vistas y permisos |
| `Gesicom/templates/ui/paginacion.html` | Paginación común para evidencias, administración y notificaciones |
| `Gesicom/templates/ui/reloj_colombia.html` | Reloj compartido en el pie de las páginas autenticadas, con referencia inicial del servidor |
| `ADMIN/forms.py` | Validación del directorio contra el catálogo de roles mostrado |
| `Gesicom/filtros.py` | Validación y normalización de filtros compartidos, con errores visibles y descarga cerrada ante parámetros inválidos |
| `Gesicom/reportes.py` | Series históricas, resúmenes autorizados y filas exportables |
| `Gesicom/exportaciones.py` | Respuesta CSV común y recorrido con cursor por identificador u orden validado, con SQL limitado; Unicode y neutralización de fórmulas |
| `Gesicom/selectors.py` | Consultas reutilizadas por vistas, reportes y búsqueda; visibilidad por rol |
| `Gesicom/busqueda.py` | Búsqueda autenticada, limitada por cuenta y con resultados acotados |
| `ADMIN/` | Administración de la comunidad |
| `ADMIN/selectors.py` | Agregaciones y consultas del centro de operaciones |
| `ADMIN/permisos.py` | Catálogo de permisos, protección de grupos, revisión y transacciones compartidas con Django admin |
| `ADMIN/admin.py` | Formularios nativos de grupo con confirmación, revisión y conservación de los roles del sistema |
| `ADMIN/services.py` | Cambios de estado y roles, protección de cuentas y auditoría |
| `ADMIN/auditoria.py` | Consultas filtradas, etiquetas y filas CSV del historial administrativo |
| `cuentas/` | Formularios comunes, recuperación, correo de seguridad y sesiones |
| `cuentas/navegacion.py` | Validación del destino local de acceso y retorno de consultas al caducar la sesión |
| `cuentas/seguridad.py` | Lista personal de sesiones, filtros y metadatos de presentación; las operaciones conservan reautenticación |
| `instructor/` | Entrada, registro y salida de la aplicación; se conservan las rutas existentes |
| `notificaciones/` | Novedades, plazos, preferencias, bandeja y cola de entrega |
| `notificaciones/novedades.py` | Filtros administrativos y métricas agrupadas de las novedades de la página visible |
| `notificaciones/publicacion.py` | Alta transaccional y recuperación de novedades mediante recibos del formulario |
| `notificaciones/exportaciones.py` | Filas del seguimiento con campos visibles y fecha explícita de Colombia |
| `notificaciones/resumen.py` | Conteo y cuatro avisos recientes compartidos durante una petición, sin caché entre cuentas |
| `notificaciones/calendario.py` | Límites mensuales de Colombia y distribución acotada de plazos en 42 días |
| `notificaciones/icalendar.py` | Descarga privada iCalendar con SQL acotado, escape de texto y plegado UTF-8 sin dependencias adicionales |
| `database/` | Documentación del esquema, diagnóstico SQL y preparación de la base de pruebas |
| `scripts/` | Operación, copias de seguridad y medición de carga |
| `docs/` | Operación, seguridad, arquitectura y verificaciones |

Cada aplicación mantiene sus propias rutas en `urls.py`. `SENNOVA/urls.py` compone estos archivos y conserva los nombres públicos anteriores, junto con los accesos de compatibilidad de `core/`. Las pruebas se agrupan en seis carpetas `tests/`, por aplicación y por funcionalidad; la configuración `SENNOVA.test_settings` conserva su ruta. La [guía de desarrollo](DESARROLLO.md) incluye el mapa de archivos y los comandos por módulo.

Las migraciones permanecen dentro de sus aplicaciones, como espera Django. Los módulos de compatibilidad y las plantillas históricas que remiten a las vistas actuales no generan menús adicionales. Solo se retiran funciones sin llamadas ni rutas activas.

El centro de operaciones agrega los registros en MySQL y limita las listas recientes; los directorios y las evidencias del detalle de usuario tienen paginación. La búsqueda reutiliza la visibilidad de evidencias y solo consulta la bandeja del usuario conectado. Los resultados no se almacenan en una caché compartida: la autorización se aplica en cada petición.

`destinatarios` combina en una consulta SQL las cuentas activas, la ausencia de grupos asignados y la pertenencia actual mediante `EXISTS`. No necesita leer primero los identificadores de grupo ni confiar en una precarga anterior. Las novedades y el seguimiento comparten esa selección. El trabajador filtra en MySQL los plazos cuya ventana de aviso ya empezó y excluye entregas y avisos del mismo tipo y versión antes de materializar destinatarios. La creación mantiene su comprobación adicional y unicidad transaccional.

El listado administrativo de novedades utiliza `FiltrosNovedadesForm`. La audiencia y los estados de correo se filtran con `Exists`, sin unir grupos a los conteos. Primero se cuentan y seleccionan 20 publicaciones con identidad mínima del autor y grupos precargados; después se agrupan las notificaciones y su correo uno a uno únicamente para esos identificadores. Así no se agrupan todos los avisos para calcular la paginación ni se recortan los totales de una novedad al filtrar por un estado. La interfaz reutiliza el controlador de navegación existente para actualizar conjuntamente la cola general y la lista en dos regiones, con los filtros fuera de las regiones sustituidas.

Los filtros usan las mismas vistas GET con o sin JavaScript. La mejora interactiva sustituye únicamente los resultados, mantiene los parámetros en la URL y permite volver con el navegador. Los cambios de cuentas siguen siendo formularios POST con CSRF, confirmación de identidad y validación del servidor. Las acciones sensibles no se ejecutan desde la búsqueda.

Los recursos se sirven desde el proyecto: Work Sans, el emblema SENA y Chart.js. `search.js` gestiona la búsqueda, `workspace.js` las acciones administrativas y `admin-dashboard.js` el centro de operaciones; los estilos compartidos de estas interacciones permanecen en `operations.css`.

El inicio de sesión valida `next` mediante `cuentas/navegacion.py` y lo conserva en el formulario incluso ante credenciales incorrectas. Solo acepta rutas locales conocidas de hasta 2.048 caracteres; comprueba también el camino decodificado y excluye acceso/salida y segmentos ambiguos. El middleware conserva la consulta en las redirecciones HTML de GET/HEAD por inactividad o versión antigua de sesión. La navegación de retorno no sustituye los permisos de la vista de destino.

La campana, la búsqueda, las acciones de bandeja y las observaciones emiten `session:expired` al detectar la caducidad. Un único manejador en `sena.js` utiliza la entrada local configurada en el documento y añade la ruta, consulta y fragmento actuales; no toma el destino de un JSON remoto. No guarda campos ni repite operaciones POST. El formulario funciona sin JavaScript y usa los estilos informativos existentes, sin otro panel ni controlador independiente. El acceso añade `no-store` también para visitantes anónimos.

`Gesicom/admin.py` utiliza las mismas reglas de versiones y registro de movimientos. El formulario de corrección reutiliza `formulario.html`; no añade un segundo panel de evidencias. Los estilos de ese flujo están en `evidencias.css`. La tabla de movimientos es de solo lectura en la administración.

`reports.js` destruye las instancias anteriores de Chart.js al actualizar resultados y reconstruye cuatro gráficos con el estado autorizado del servidor. Las tablas se generan en HTML y se usan sin JavaScript y al imprimir. No se mantienen consultas trimestrales distintas para pantalla y CSV.

Las exportaciones de evidencias y auditoría utilizan `iterar_ordenados`: cada lectura de filas lleva `LIMIT 500` y un cursor por el campo de orden y la clave primaria en la misma dirección. Así conservan los ocho órdenes del reporte y el historial por fecha descendente, con los empates resueltos dentro de SQL y su colación. Directorio y seguimiento usan el mismo recorrido mediante `iterar_por_id`. Un máximo inicial de identificador deja fuera altas posteriores; las consultas vuelven a aplicar los filtros de alcance en cada lote. El CSV de evidencias solo carga sus campos y las identidades mínimas de propietario y plazo, sin hashes, correo ni descripciones. Las columnas de fecha indicadas como Colombia fijan `America/Bogota`.

El alta de evidencias utiliza `SolicitudEnvio` como recibo interno, sin panel ni permisos adicionales. Su UUID único y el bloqueo transaccional de MySQL permiten recuperar el primer registro aceptado cuando llegan reintentos del mismo formulario. El recibo, la evidencia y el movimiento se confirman juntos; un fallo retira también el archivo nuevo que haya quedado sin referencia. Al eliminar la evidencia se conserva el recibo sin destino para que un reintento no la vuelva a crear.

La publicación desde el formulario personalizado utiliza `SolicitudNovedad`. El recibo con UUID único, la novedad, sus grupos y los avisos/correos preparados se confirman en una misma transacción. Las peticiones concurrentes de un formulario se coordinan mediante el bloqueo de su recibo, sin bloquear globalmente las cuentas administradoras. El reintento devuelve el primer resultado y no aplica los nuevos campos. La eliminación de la novedad conserva el recibo sin destino para impedir su recreación. La consulta de recuperación verifica de nuevo que el autor esté activo y autorizado.

`Gesicom/solicitudes.py` conserva el protocolo de evidencias y permite indicar un dominio de firma distinto para novedades: las identificaciones se ligan a la cuenta y vencen a las 24 horas. `sena.js` restaura el botón y su icono al recibir `pageshow` persistente en estos formularios identificados, conservando los campos y el identificador. Los clientes antiguos que no envían identificación y el alta nativa de Django mantienen su comportamiento previo; esta recuperación se aplica al formulario personalizado identificado. La cola SMTP conserva su entrega al menos una vez.

Los archivos compartidos se buscan por nombre indexado y se retiran después del commit solo si ninguna evidencia los referencia. La consulta de disponibilidad no modifica registros históricos. Las vistas de texto leen como máximo 64 KB del origen, más un byte para detectar truncamiento; la descarga conserva el archivo completo.

`notifications.js` concentra la actualización de la campana en todos los paneles autenticados; `sena.js` conserva las interacciones generales y la caducidad visible del PIN. La lista inicial se genera en `notificaciones/avisos_recientes.html`, con POST y CSRF, para funcionar también sin JavaScript. Las actualizaciones utilizan el mismo resumen autorizado y crean los elementos con `textContent`; no incorporan HTML de los títulos. La bandeja y el procesador de contexto comparten el conteo únicamente dentro de la misma petición.

`navigation.js` gestiona los filtros, la paginación, el historial y las ediciones pendientes de los paneles interactivos. `search.js` y `workspace.js` no duplican ese controlador. Las solicitudes GET con `X-Workspace-Fragment: 1` usan `ui/base_fragmento.html` y omiten la cabecera y sus consultas de avisos. Las mismas vistas generan el documento completo sin esa cabecera HTTP. `Vary` identifica ambas representaciones y la respuesta privada conserva `no-store`.

El estado del historial contiene solo un identificador del documento y un índice, sin datos de formularios. Una navegación cancelada o fallida vuelve a la entrada aplicada sin borrar Adelante. Las nuevas ediciones cancelan las actualizaciones en curso; los eventos de cambio generados al retirar un campo enfocado no se confunden con otra edición del usuario. Los fragmentos se comprueban antes de sustituir regiones y cada consulta tiene un tiempo máximo de espera.

La lista, el calendario y la descarga de **Mis plazos** comparten `FiltrosAgendaForm` y `agenda_filtrada`: validan búsqueda, proyecto, estado, identificador y mes antes de consultar. La pertenencia actual a los grupos y las entregas de la cuenta se resuelven con subconsultas `Exists`, sin una consulta por evento. La cuadrícula admite hasta 500 plazos por mes y avisa si hay más; la lista paginada y la descarga conservan todos los resultados autorizados. El calendario reutiliza el panel y el controlador de navegación existentes, sin tablas ni rutas de administración duplicadas.

La descarga iCalendar reutiliza `iterar_ordenados` por `fecha_limite` e identificador ascendente, con un corte inicial de clave primaria y lecturas de hasta 500 filas. En MySQL, `iterator(chunk_size=...)` por sí solo no limita las filas de la consulta ni impide que el controlador las almacene completas; el recorrido compartido aplica `LIMIT 500` en SQL. Solo se seleccionan identidad, título, descripción, proyecto, fechas y revisión, junto con las anotaciones de entrega. Los filtros, el estado activo y la pertenencia a grupos se consultan de nuevo en cada lote. No se congela una instantánea de ediciones: un lote ya leído puede terminar de enviarse y las fechas modificadas durante el recorrido pueden afectar a los lotes siguientes.

`FiltrosBandejaForm` valida búsqueda, tipo, lectura, identificador y fechas antes de consultar o marcar resultados. `inbox.js` envía los formularios de lectura con CSRF y solicita una actualización al controlador de navegación compartido. `workspace:refresh` conserva la consulta aplicada y espera si hay una búsqueda o actualización en curso. `notifications:changed` solicita el contador vigente mediante el controlador existente de la campana. Las acciones nativas conservan su redirección cuando no se solicita el protocolo JSON.

`clock.js` y `clock.css` presentan un único reloj en el pie del documento completo. Los fragmentos no lo reconstruyen. El cliente reutiliza dos formateadores `Intl.DateTimeFormat` en `America/Bogota`, actualiza los segundos y pausa el temporizador al ocultar la página. El componente obtiene una sola referencia temporal del servidor para su estado inicial; el reloj no consulta la base de datos ni un servicio de hora.

El centro de seguridad usa `FiltrosSesionesForm` para distinguir todas las sesiones, la actual y las otras. Una expresión SQL ordena primero la actual y después actividad e identificador descendentes; la lista lee solo los metadatos de 20 filas por página. No carga el contenido ni la clave de cada sesión al preparar las tarjetas. El estado de inactividad reutiliza el límite estricto del middleware y no elimina registros durante la lectura. La plantilla fija Colombia para los horarios. `security.css` concentra su presentación y retira las reglas antiguas de `sena.css`. Los filtros y formularios usan navegación nativa y funcionan sin JavaScript. La paginación compartida admite enlaces anteriores/siguientes explícitos para conservar únicamente los parámetros validados de esta vista.
