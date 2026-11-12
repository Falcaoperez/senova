-- Diagnóstico de solo lectura. Ejecutar con la base de GESICOM seleccionada.
-- No extrae contraseñas, PIN, contenidos cifrados ni claves de sesión.
SELECT DATABASE() AS base_actual, @@version AS version_mysql,
       @@character_set_database AS juego_caracteres, @@collation_database AS cotejamiento,
       @@sql_mode AS modo_sql;

SELECT table_name AS tabla, engine AS motor, table_collation AS cotejamiento,
       table_rows AS filas_estimadas, ROUND((data_length + index_length) / 1024 / 1024, 2) AS megabytes
FROM information_schema.tables
WHERE table_schema = DATABASE()
ORDER BY table_name;

SELECT table_name AS tabla, index_name AS indice, non_unique AS permite_duplicados,
       GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ', ') AS columnas
FROM information_schema.statistics
WHERE table_schema = DATABASE()
GROUP BY table_name, index_name, non_unique
ORDER BY table_name, index_name;

SELECT COUNT(*) AS cuentas, SUM(is_active = 1) AS activas, SUM(is_active = 0) AS inactivas
FROM auth_user;

SELECT COUNT(*) AS evidencias, SUM(aprobada = 1) AS aprobadas, SUM(rechazada = 1) AS rechazadas,
       SUM(aprobada = 0 AND rechazada = 0) AS pendientes
FROM Gesicom_envio;

SELECT estado, COUNT(*) AS total FROM notificaciones_correopendiente GROUP BY estado;
SELECT tipo, estado, COUNT(*) AS total FROM cuentas_correoseguridad GROUP BY tipo, estado;
SELECT COUNT(*) AS sesiones_caducadas FROM django_session WHERE expire_date <= UTC_TIMESTAMP();
SELECT COUNT(*) AS recuperaciones_caducadas
FROM cuentas_passwordresettoken WHERE used = 0 AND expires_at <= UTC_TIMESTAMP();

SELECT accion, estado, COUNT(*) AS movimientos
FROM Gesicom_movimientoevidencia GROUP BY accion, estado;

-- Plazos y cola: no incluye contenidos ni direcciones personales.
SELECT activo, COUNT(*) AS plazos, SUM(fecha_limite <= UTC_TIMESTAMP()) AS vencidos
FROM notificaciones_plazoreporte GROUP BY activo;
SELECT tipo, COUNT(*) AS avisos, SUM(leida_en IS NOT NULL) AS leidos
FROM notificaciones_notificacion GROUP BY tipo;
