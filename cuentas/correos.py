"""Cola transaccional de correos de seguridad; el PIN solo se descifra al enviar."""

import base64
import json
import math
import re
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connection, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from .models import CorreoSeguridad, PasswordResetToken


def _cifrador():
    keys = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return MultiFernet(
        [
            Fernet(
                base64.urlsafe_b64encode(
                    HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"gesicom-security-mail-v1").derive(
                        key.encode()
                    )
                )
            )
            for key in keys
        ]
    )


def encolar_pin(solicitud):
    payload = json.dumps(
        {
            "version": 1,
            "pin": solicitud.pin_para_envio,
            "solicitud": solicitud.pk,
            "usuario": solicitud.usuario_id,
            "destinatario": solicitud.usuario.email.casefold(),
        }
    ).encode()
    return CorreoSeguridad.objects.create(
        usuario=solicitud.usuario,
        solicitud=solicitud,
        tipo=CorreoSeguridad.Tipo.PIN,
        destinatario=solicitud.usuario.email,
        contenido_cifrado=_cifrador().encrypt(payload).decode(),
    )


def invalidar_recuperaciones(usuario):
    PasswordResetToken.objects.filter(usuario=usuario, utilizado=False).update(utilizado=True)
    CorreoSeguridad.objects.filter(usuario=usuario, tipo=CorreoSeguridad.Tipo.PIN).exclude(
        estado=CorreoSeguridad.Estado.ENVIADO
    ).update(estado=CorreoSeguridad.Estado.CANCELADO, contenido_cifrado="", bloqueado_hasta=None)


def encolar_aviso_cambio(usuario, correo_anterior=None):
    direcciones = {
        correo.strip().casefold() for correo in (usuario.email, correo_anterior) if correo and correo.strip()
    }
    for direccion in direcciones:
        CorreoSeguridad.objects.create(usuario=usuario, destinatario=direccion, tipo=CorreoSeguridad.Tipo.CAMBIO)


def _reclamar(limite):
    ahora = timezone.now()
    with transaction.atomic():
        pendientes = CorreoSeguridad.objects.filter(
            Q(estado=CorreoSeguridad.Estado.PENDIENTE)
            | Q(estado=CorreoSeguridad.Estado.PROCESANDO, bloqueado_hasta__lt=ahora),
            proximo_intento__lte=ahora,
            intentos__lt=3,
        ).order_by("pk")
        if connection.features.has_select_for_update:
            pendientes = pendientes.select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
        ids = list(pendientes.values_list("pk", flat=True)[:limite])
        CorreoSeguridad.objects.filter(pk__in=ids).update(
            estado=CorreoSeguridad.Estado.PROCESANDO,
            bloqueado_hasta=ahora + timedelta(seconds=max(600, limite * (settings.EMAIL_TIMEOUT + 15))),
        )
    return ids


def procesar_correos_seguridad(limite=25):
    enviados = 0
    transport = get_connection(fail_silently=False)
    try:
        for correo in CorreoSeguridad.objects.filter(pk__in=_reclamar(limite)).select_related(
            "usuario", "solicitud__usuario"
        ):
            solicitud = correo.solicitud
            ahora = timezone.now()
            valido = correo.usuario.is_active
            if correo.tipo == CorreoSeguridad.Tipo.PIN:
                valido = bool(
                    valido
                    and solicitud
                    and solicitud.es_valido()
                    and not solicitud.verificado_en
                    and correo.usuario.email.casefold() == correo.destinatario.casefold()
                )
            if not valido:
                correo.estado = CorreoSeguridad.Estado.CANCELADO
                correo.contenido_cifrado = ""
            else:
                try:
                    if solicitud:
                        try:
                            payload = json.loads(_cifrador().decrypt(correo.contenido_cifrado.encode()))
                        except (ValueError, TypeError):
                            raise InvalidToken from None
                        if (
                            not isinstance(payload, dict)
                            or payload.get("version") != 1
                            or payload.get("solicitud") != solicitud.pk
                            or payload.get("usuario") != correo.usuario_id
                            or payload.get("destinatario") != correo.destinatario.casefold()
                        ):
                            raise InvalidToken
                        pin = payload.get("pin", "")
                        if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{6}", pin):
                            raise InvalidToken
                        context = {
                            "pin": pin,
                            "minutos": max(1, math.ceil((solicitud.expira_en - ahora).total_seconds() / 60)),
                        }
                        template = "cuentas/correo_pin"
                        subject = "Tu PIN de recuperación de GESICOM"
                    else:
                        context = {"enlace": settings.PUBLIC_BASE_URL.rstrip("/") + "/password-reset/"}
                        template = "cuentas/correo_cambio"
                        subject = "Se actualizaron las credenciales de tu cuenta GESICOM"
                    message = EmailMultiAlternatives(
                        subject,
                        render_to_string(template + ".txt", context),
                        settings.DEFAULT_FROM_EMAIL,
                        [correo.destinatario],
                        connection=transport,
                    )
                    message.attach_alternative(render_to_string(template + ".html", context), "text/html")
                    transport.open()
                    if message.send(fail_silently=False) != 1:
                        raise RuntimeError("El transporte no aceptó el mensaje.")
                    correo.estado = CorreoSeguridad.Estado.ENVIADO
                    correo.enviado_en = timezone.now()
                    correo.contenido_cifrado = ""
                    correo.ultimo_error = ""
                    enviados += 1
                except InvalidToken:
                    correo.estado = CorreoSeguridad.Estado.CANCELADO
                    correo.contenido_cifrado = ""
                    correo.ultimo_error = "El contenido ya no se puede descifrar. Solicita un PIN nuevo."
                    if solicitud:
                        PasswordResetToken.objects.filter(pk=solicitud.pk).update(utilizado=True)
                except Exception:
                    correo.intentos += 1
                    correo.estado = (
                        CorreoSeguridad.Estado.ERROR if correo.intentos >= 3 else CorreoSeguridad.Estado.PENDIENTE
                    )
                    correo.proximo_intento = timezone.now() + timedelta(seconds=30 * 2**correo.intentos)
                    correo.ultimo_error = "El proveedor no aceptó el envío. Revisa la configuración privada del correo."
                    if correo.estado == CorreoSeguridad.Estado.ERROR:
                        correo.contenido_cifrado = ""
                        if solicitud:
                            PasswordResetToken.objects.filter(pk=solicitud.pk).update(utilizado=True)
                    transport.close()
            # Una cancelación concurrente no debe volver a activar un correo.
            CorreoSeguridad.objects.filter(pk=correo.pk, estado=CorreoSeguridad.Estado.PROCESANDO).update(
                estado=correo.estado,
                intentos=correo.intentos,
                proximo_intento=correo.proximo_intento,
                bloqueado_hasta=None,
                enviado_en=correo.enviado_en,
                contenido_cifrado=correo.contenido_cifrado,
                ultimo_error=correo.ultimo_error,
            )
    finally:
        transport.close()
    return enviados
