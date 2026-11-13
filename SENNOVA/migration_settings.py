"""Configuración exclusiva de la tarea de migración; no se usa para servir HTTP."""

from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .settings import *

DATABASES = deepcopy(DATABASES)
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    usuario = env("DB_MIGRATION_USER", default="")
    password = env("DB_MIGRATION_PASSWORD", default="")
    if not usuario or not password or usuario == DATABASES["default"]["USER"]:
        raise ImproperlyConfigured("Configura una cuenta privada DB_MIGRATION_USER distinta de la de ejecución.")
    DATABASES["default"].update(USER=usuario, PASSWORD=password, CONN_MAX_AGE=0)
