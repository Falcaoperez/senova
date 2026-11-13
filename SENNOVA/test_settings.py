from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .settings import *

DATABASES = deepcopy(DATABASES)
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    usuario = env("DB_TEST_USER", default="")
    password = env("DB_TEST_PASSWORD", default="")
    if not usuario or not password or usuario == DATABASES["default"]["USER"]:
        raise ImproperlyConfigured("Configura DB_TEST_USER y DB_TEST_PASSWORD para una cuenta exclusiva de pruebas.")
    nombre = "test_" + DATABASES["default"]["NAME"]
    if len(nombre) > 64:
        raise ImproperlyConfigured("El nombre de la base no permite crear un esquema independiente de pruebas.")
    DATABASES["default"].update(USER=usuario, PASSWORD=password, NAME=nombre)
    DATABASES["default"]["TEST"]["NAME"] = nombre

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "gesicom-tests"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
RATE_LIMITS_ENABLED = False
DATABASES["default"]["CONN_MAX_AGE"] = 0
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
