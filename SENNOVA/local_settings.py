"""Perfil exclusivo de VS Code: datos aislados, SQLite y correo en consola."""

import os

from decouple import RepositoryEnv
from django.core.exceptions import ImproperlyConfigured

from .desarrollo import RAIZ, archivo_perfil, carpeta_local, entorno_local

perfil = archivo_perfil(RAIZ)
if not perfil.is_file():
    raise ImproperlyConfigured("Prepara el perfil local con: python scripts/configurar_entorno.py --inicio-rapido")
secreto = RepositoryEnv(str(perfil)).data.get("DJANGO_SECRET_KEY", "")
if len(secreto) < 40 or secreto.startswith("django-insecure"):
    raise ImproperlyConfigured("El perfil local necesita una DJANGO_SECRET_KEY privada de al menos 40 caracteres.")

# El perfil explícito no hereda conexiones ni credenciales de producción.
try:
    os.environ.update(entorno_local(RAIZ, puerto=int(os.environ.get("GESICOM_LOCAL_PORT", "8000"))))
except ValueError as error:
    raise ImproperlyConfigured("GESICOM_LOCAL_PORT debe ser un puerto entre 1024 y 65535.") from error
os.environ["DJANGO_SECRET_KEY"] = secreto

from .settings import *  # noqa: E402

LOCAL_DIR = carpeta_local(RAIZ)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": LOCAL_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
# Compartida entre la web y el trabajador, sin un servicio Redis adicional.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "gesicom_cache_desarrollo",
        "KEY_PREFIX": "gesicom-local",
    }
}
MEDIA_ROOT = LOCAL_DIR / "media"
STATIC_ROOT = LOCAL_DIR / "staticfiles"
for carpeta in (MEDIA_ROOT, STATIC_ROOT):
    carpeta.mkdir(parents=True, exist_ok=True, mode=0o700)
