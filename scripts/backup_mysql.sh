#!/bin/sh
# Copia consistente de MySQL en una ruta privada; nunca se añade a Git.
set -eu
umask 077
mkdir -p .local/backups
chmod 700 .local/backups
backup_sql=$(mktemp .local/backups/.gesicom-XXXXXXXX)
backup_path=".local/backups/gesicom-$(date -u +%Y%m%dT%H%M%SZ)-${backup_sql##*-}.sql.gz"
backup_pending="$backup_sql.gz"
trap 'rm -f "$backup_sql" "$backup_pending"' EXIT
trap 'exit 1' HUP INT TERM
# El operador accede por el socket del contenedor. Django nunca recibe esta clave.
if [ -n "${MYSQL_CONTAINER:-}" ]; then
    docker exec "$MYSQL_CONTAINER" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF -uroot "$MYSQL_DATABASE"' > "$backup_sql"
else
    docker compose exec -T database sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF -uroot "$MYSQL_DATABASE"' > "$backup_sql"
fi
gzip -c "$backup_sql" > "$backup_pending"
mv "$backup_pending" "$backup_path"
printf 'Copia guardada: %s\n' "$backup_path"
