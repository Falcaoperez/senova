#!/usr/bin/env python3
"""Genera configuración privada sin cambiar credenciales ya definidas."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / ".env"
values = {}
if path.exists():
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
for key in ["DJANGO_SECRET_KEY", "DB_PASSWORD", "MYSQL_ROOT_PASSWORD", "REDIS_PASSWORD"]:
    if not values.get(key) or values[key].startswith("replace-"):
        values[key] = secrets.token_urlsafe(48 if key == "DJANGO_SECRET_KEY" else 28)
defaults = {
    "DJANGO_DEBUG": "True",
    "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
    "DB_ENGINE": "mysql",
    "DB_NAME": "senova",
    "DB_USER": "gesicom_app",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "3307",
    "PUBLIC_BASE_URL": "http://127.0.0.1:8000",
    "EMAIL_BACKEND": "SENNOVA.email_backend.SMTPBackend",
    "EMAIL_HOST": "smtp.office365.com",
    "EMAIL_PORT": "587",
    "EMAIL_USE_TLS": "True",
    "EMAIL_USE_SSL": "False",
    "EMAIL_HOST_USER": "noresponderGESICOM@soy.sena.edu.co",
    "EMAIL_HOST_PASSWORD": "",
    "EMAIL_OAUTH2_ACCESS_TOKEN": "",
    "DEFAULT_FROM_EMAIL": "GESICOM SENA <noresponderGESICOM@soy.sena.edu.co>",
}
for key, value in defaults.items():
    values.setdefault(key, value)
values.setdefault("REDIS_URL", f"redis://:{values['REDIS_PASSWORD']}@127.0.0.1:6380/0")
if not values.get("REDIS_URL") or "replace-" in values["REDIS_URL"]:
    values["REDIS_URL"] = f"redis://:{values['REDIS_PASSWORD']}@127.0.0.1:6380/0"
path.write_text(
    "# Configuración privada: no publicar ni compartir este archivo.\n"
    + "\n".join(f"{key}={value}" for key, value in values.items())
    + "\n"
)
path.chmod(0o600)
print("Configuración privada preparada en .env. Las credenciales existentes se conservan.")
