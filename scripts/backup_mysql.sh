#!/bin/sh
# Copia consistente de MySQL en una ruta privada; nunca se añade a Git.
set -eu
umask 077
mkdir -p .local/backups
backup_path=".local/backups/gesicom-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
backup_sql="${backup_path%.gz}"
trap 'rm -f "$backup_sql"' EXIT
docker compose exec -T database sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF -u "$MYSQL_USER" "$MYSQL_DATABASE"' > "$backup_sql"
gzip -c "$backup_sql" > "$backup_path"
printf 'Copia guardada: %s\n' "$backup_path"
