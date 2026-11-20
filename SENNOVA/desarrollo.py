"""Rutas y perfil privado de desarrollo; utilizable antes de instalar Django."""

import os
import secrets
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VARIABLES_LOCALES = {
    "DJANGO_SETTINGS_MODULE": "SENNOVA.local_settings",
    "DJANGO_DEBUG": "True",
    "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
    "DB_ENGINE": "sqlite",
    "REDIS_URL": "",
    "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
    "EMAIL_HOST": "",
    "EMAIL_HOST_USER": "",
    "EMAIL_HOST_PASSWORD": "",
    "EMAIL_OAUTH2_ACCESS_TOKEN": "",
    "EMAIL_PORT": "587",
    "EMAIL_USE_TLS": "False",
    "EMAIL_USE_SSL": "False",
    "DEFAULT_FROM_EMAIL": "GESICOM <no-reply@gesicom.local>",
    "PUBLIC_BASE_URL": "http://127.0.0.1:8000",
    "CSRF_TRUSTED_ORIGINS": "http://localhost:8000,http://127.0.0.1:8000",
    "TRUST_PROXY_HTTPS": "False",
    "TRUSTED_PROXY_IPS": "",
}


def carpeta_local(raiz=RAIZ):
    return raiz / ".local" / "desarrollo"


def archivo_perfil(raiz=RAIZ):
    return carpeta_local(raiz) / "perfil.env"


def crear_configuracion_local(raiz=RAIZ):
    carpeta_local(raiz).mkdir(parents=True, exist_ok=True, mode=0o700)
    valores = {**VARIABLES_LOCALES, "DJANGO_SECRET_KEY": secrets.token_urlsafe(48)}
    try:
        descriptor = os.open(archivo_perfil(raiz), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        archivo.write("# Perfil privado de desarrollo. No publicar este archivo.\n")
        archivo.write("\n".join(f"{clave}={valor}" for clave, valor in valores.items()) + "\n")
    return True


def entorno_local(raiz=RAIZ, *, puerto=8000):
    if not 1024 <= puerto <= 65535:
        raise ValueError("El puerto local debe estar entre 1024 y 65535.")
    return {
        **os.environ,
        **VARIABLES_LOCALES,
        "DJANGO_ENV_FILE": str(archivo_perfil(raiz)),
        "DJANGO_LOG_DIR": str(carpeta_local(raiz) / "logs"),
        "GESICOM_LOCAL_PORT": str(puerto),
        "PUBLIC_BASE_URL": f"http://127.0.0.1:{puerto}",
        "CSRF_TRUSTED_ORIGINS": f"http://localhost:{puerto},http://127.0.0.1:{puerto}",
    }


def python_del_entorno(raiz=RAIZ, *, windows=None):
    windows = os.name == "nt" if windows is None else windows
    return raiz / ".venv" / ("Scripts/python.exe" if windows else "bin/python")
