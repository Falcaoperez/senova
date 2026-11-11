"""Revocación compatible con la caché y la base de datos de sesiones de Django."""

from importlib import import_module

from django.conf import settings

from .models import SesionUsuario

VERSION_SEGURIDAD = 1
CLAVE_VERSION = "gesicom_seguridad_version"


def cerrar_sesiones(usuario, conservar=None):
    keys = list(
        SesionUsuario.objects.filter(usuario=usuario).exclude(sesion_id=conservar).values_list("sesion_id", flat=True)
    )
    store = import_module(settings.SESSION_ENGINE).SessionStore
    for key in keys:
        store(session_key=key).delete()
    return len(keys)
