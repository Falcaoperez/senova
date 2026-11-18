"""Identificadores por cuenta con dominios de firma separados por formulario."""

import uuid

from django.core import signing
from django.core.exceptions import ValidationError

SALT = "gesicom.solicitud-evidencia.v1"
VIGENCIA = 24 * 60 * 60
ERROR_EVIDENCIA = (
    "El formulario venció o ya no corresponde a tu cuenta. Abre uno nuevo y vuelve a seleccionar el archivo; "
    "conserva el texto antes de recargar."
)


def crear_solicitud(usuario, *, dominio=SALT):
    return signing.dumps({"usuario": usuario.pk, "codigo": str(uuid.uuid4())}, salt=dominio)


def verificar_solicitud(valor, usuario, *, dominio=SALT, mensaje_error=ERROR_EVIDENCIA):
    try:
        datos = signing.loads(valor, salt=dominio, max_age=VIGENCIA)
        if datos["usuario"] != usuario.pk:
            raise ValueError
        return uuid.UUID(datos["codigo"])
    except (signing.BadSignature, ValueError, TypeError, KeyError):
        raise ValidationError(mensaje_error) from None
