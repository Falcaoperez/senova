# Organización del proyecto

| Carpeta | Responsabilidad |
| --- | --- |
| `SENNOVA/` | Configuración activa, rutas y middleware HTTP |
| `config/` | Configuración de Gunicorn |
| `Gesicom/` | Evidencias, reportes, páginas y recursos visuales compartidos |
| `Gesicom/selectors.py` | Consultas reutilizadas por vistas, reportes y búsqueda; visibilidad por rol |
| `Gesicom/busqueda.py` | Búsqueda autenticada, limitada por cuenta y con resultados acotados |
| `ADMIN/` | Administración de la comunidad |
| `ADMIN/selectors.py` | Agregaciones y consultas del centro de operaciones |
| `ADMIN/services.py` | Cambios de estado y roles, protección de cuentas y auditoría |
| `cuentas/` | Formularios comunes, recuperación, correo de seguridad y sesiones |
| `instructor/` | Entrada, registro y salida de la aplicación; se conservan las rutas existentes |
| `notificaciones/` | Novedades, plazos, preferencias, bandeja y cola de entrega |
| `database/` | Documentación del esquema, diagnóstico SQL y preparación de la base de pruebas |
| `scripts/` | Operación, copias de seguridad y medición de carga |
| `docs/` | Operación, seguridad, arquitectura y verificaciones |

Las migraciones permanecen dentro de sus aplicaciones, como espera Django. Los módulos de compatibilidad y las plantillas históricas que remiten a las vistas actuales no generan menús adicionales. Solo se retiran funciones sin llamadas ni rutas activas.

El centro de operaciones agrega los registros en MySQL y limita las listas recientes; los directorios y las evidencias del detalle de usuario tienen paginación. La búsqueda reutiliza la visibilidad de evidencias y solo consulta la bandeja del usuario conectado. Los resultados no se almacenan en una caché compartida: la autorización se aplica en cada petición.

Los filtros usan las mismas vistas GET con o sin JavaScript. La mejora interactiva sustituye únicamente los resultados, mantiene los parámetros en la URL y permite volver con el navegador. Los cambios de cuentas siguen siendo formularios POST con CSRF, confirmación de identidad y validación del servidor. Las acciones sensibles no se ejecutan desde la búsqueda.

Los recursos se sirven desde el proyecto: Work Sans, el emblema SENA y Chart.js. Los módulos `workspace.js`, `admin-dashboard.js` y `operations.css` separan las nuevas interacciones de los estilos y comportamientos generales.
