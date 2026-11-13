# Consultas de diagnóstico

`diagnostico.sql` consulta metadatos y contadores de motor, cotejamiento, índices, cuentas, evidencias, colas, sesiones, plazos y recibos. Selecciona primero la base de la instalación. No contiene operaciones de escritura ni devuelve contraseñas, PIN, cuerpos de correo, archivos o claves de sesión. Las cifras de filas de `information_schema` son estimaciones.

Las consultas no crean el esquema ni reemplazan migraciones. La base y cuenta independientes de pruebas se preparan con `python scripts/preparar_mysql.py --aplicar --con-pruebas`, siguiendo la [guía de permisos mínimos](../seguridad/README.md); las copias reales se guardan en almacenamiento privado. El [modelo documentado](../documentacion/modelo.md) describe las relaciones de las tablas.

La actividad administrativa se consulta desde **Centro de operaciones → Actividad reciente → Ver historial**, con permisos, paginación, filtros y CSV. Esa pantalla lee `cuentas_registroseguridad`; no requiere modificar datos desde SQL ni habilitar acceso directo a la base para el usuario del portal.
