"""Publicaciones transaccionales y recuperación de formularios ya aceptados."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from Gesicom.solicitudes import crear_solicitud, verificar_solicitud

from .models import Novedad, SolicitudNovedad
from .services import publicar_novedad

DOMINIO = "gesicom.solicitud-novedad.v1"
User = get_user_model()


def crear_solicitud_novedad(usuario):
    return crear_solicitud(usuario, dominio=DOMINIO)


def verificar_solicitud_novedad(valor, usuario):
    return verificar_solicitud(
        valor,
        usuario,
        dominio=DOMINIO,
        mensaje_error="El formulario de publicación venció o no corresponde a tu cuenta. Conserva tus cambios y abre un formulario nuevo.",
    )


@dataclass(frozen=True)
class ResultadoPublicacion:
    novedad: Novedad
    nuevos_avisos: int = 0
    reutilizado: bool = False


def _exigir_autor(actor):
    autorizado = (
        User.objects.filter(pk=actor.pk, is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name="administrador"))
        .exists()
    )
    if not autorizado:
        raise PermissionDenied


def _recibos():
    return SolicitudNovedad.objects.select_related("novedad").only(
        "codigo", "usuario", "novedad__id", "novedad__creada_por"
    )


def _resultado_previo(recibo, actor):
    if not recibo.novedad_id or recibo.novedad.creada_por_id != actor.pk:
        raise ValidationError(
            "Esta publicación ya fue procesada y su registro no está disponible para este formulario. Abre un formulario nuevo para otra publicación."
        )
    return ResultadoPublicacion(recibo.novedad, reutilizado=True)


def recuperar_publicacion(actor, codigo):
    _exigir_autor(actor)
    recibo = _recibos().filter(codigo=codigo, usuario=actor).first()
    return _resultado_previo(recibo, actor) if recibo else None


def publicar_o_recuperar(actor, datos):
    with transaction.atomic():
        _exigir_autor(actor)
        recibo = None
        if codigo := datos.get("solicitud"):
            recibo, creado = SolicitudNovedad.objects.get_or_create(codigo=codigo, defaults={"usuario": actor})
            recibo = _recibos().select_for_update().get(pk=recibo.pk)
            if recibo.usuario_id != actor.pk:
                raise PermissionDenied
            if not creado:
                return _resultado_previo(recibo, actor)
        novedad = Novedad.objects.create(
            titulo=datos["titulo"],
            contenido=datos["contenido"],
            enlace=datos.get("enlace", ""),
            creada_por=actor,
        )
        novedad.grupos.set(datos.get("grupos", []))
        total = publicar_novedad(novedad)
        if recibo:
            recibo.novedad = novedad
            recibo.save(update_fields=["novedad"])
    return ResultadoPublicacion(novedad, nuevos_avisos=total)
