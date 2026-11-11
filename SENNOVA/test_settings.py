from .settings import *

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
