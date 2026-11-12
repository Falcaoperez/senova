"""Identificadores firmados por cuenta para recuperar un envío ya aceptado."""

import uuid

from django.core import signing
from django.core.exceptions import ValidationError

SALT = "gesicom.solicitud-evidencia.v1"
VIGENCIA = 24 * 60 * 60


def crear_solicitud(usuario):
    return signing.dumps({"usuario": usuario.pk, "codigo": str(uuid.uuid4())}, salt=SALT)


def verificar_solicitud(valor, usuario):
    try:
        datos = signing.loads(valor, salt=SALT, max_age=VIGENCIA)
        if datos["usuario"] != usuario.pk:
            raise ValueError
        return uuid.UUID(datos["codigo"])
    except (signing.BadSignature, ValueError, TypeError, KeyError):
        raise ValidationError(
            "El formulario venció o ya no corresponde a tu cuenta. Abre uno nuevo y vuelve a seleccionar el archivo; conserva el texto antes de recargar."
        ) from None
