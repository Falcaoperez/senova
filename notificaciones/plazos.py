"""Operaciones de agenda con bloqueo, control de edición y avisos idempotentes."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from cuentas.models import RegistroSeguridad

from .models import CorreoPendiente, Notificacion, PlazoReporte
from .selectors import destinatarios
from .services import _crear_avisos, anunciar_plazo

User = get_user_model()
CAMPOS = ("titulo", "descripcion", "proyecto", "fecha_limite", "recordatorio_horas", "activo")


class ConflictoPlazo(ValidationError):
    def __init__(self):
        super().__init__("El plazo cambió en otra sesión. Abre la versión actual antes de guardar.", code="conflicto")


def _autorizar(actor, nativo=False, crear=False):
    actual = User.objects.filter(pk=actor.pk, is_active=True).first()
    if not actual:
        raise PermissionDenied
    if actual.is_superuser or actual.groups.filter(name="administrador").exists():
        return
    permiso = "notificaciones.add_plazoreporte" if crear else "notificaciones.change_plazoreporte"
    if not (nativo and actual.is_staff and actual.has_perm(permiso)):
        raise PermissionDenied


def comprobar_revision(plazo, revision):
    try:
        valida = int(revision) == plazo.revision
    except (TypeError, ValueError):
        valida = False
    if not valida:
        raise ConflictoPlazo()


def _cancelar_anteriores(plazo):
    CorreoPendiente.objects.filter(notificacion__plazo=plazo, estado__in=["pendiente", "procesando", "error"]).update(
        estado=CorreoPendiente.Estado.CANCELADO,
        bloqueado_hasta=None,
        ultimo_error="El plazo se actualizó o fue archivado.",
    )


@transaction.atomic
def guardar_plazo(actor, datos, *, pk=None, nativo=False):
    _autorizar(actor, nativo=nativo, crear=pk is None)
    plazo = (
        PlazoReporte.objects.select_for_update().filter(pk=pk).first()
        if pk is not None
        else PlazoReporte(creado_por=actor)
    )
    if not plazo:
        raise Http404
    if pk is not None:
        comprobar_revision(plazo, datos.get("revision_actual"))
    grupos = {grupo.pk for grupo in datos.get("grupos", [])}
    actuales = set(plazo.grupos.values_list("pk", flat=True)) if pk is not None else set()
    cambios = pk is None or grupos != actuales or any(getattr(plazo, field) != datos[field] for field in CAMPOS)
    if not cambios:
        return plazo, 0, False
    if pk is not None:
        _cancelar_anteriores(plazo)
        plazo.revision += 1
        plazo.version += 1
    for field in CAMPOS:
        setattr(plazo, field, datos[field])
    plazo.actualizado_en = timezone.now()
    plazo.save()
    plazo.grupos.set(grupos)
    total = anunciar_plazo(plazo) if plazo.activo else 0
    RegistroSeguridad.objects.create(
        actor=actor, accion="admin:plazo_guardado", ruta=reverse("notificaciones:editar_plazo", args=[plazo.pk])
    )
    return plazo, total, True


@transaction.atomic
def archivar_plazo(actor, pk, revision):
    _autorizar(actor)
    plazo = PlazoReporte.objects.select_for_update().filter(pk=pk).first()
    if not plazo:
        raise Http404
    comprobar_revision(plazo, revision)
    if plazo.activo:
        plazo.activo = False
        plazo.revision += 1
        plazo.version += 1
        plazo.actualizado_en = timezone.now()
        plazo.save(update_fields=["activo", "revision", "version", "actualizado_en"])
        _cancelar_anteriores(plazo)
        RegistroSeguridad.objects.create(
            actor=actor, accion="admin:plazo_archivado", ruta=reverse("notificaciones:editar_plazo", args=[pk])
        )
    return plazo


@transaction.atomic
def recordar_pendientes(actor, pk, revision):
    _autorizar(actor)
    plazo = PlazoReporte.objects.select_for_update().filter(pk=pk).first()
    if not plazo:
        raise Http404
    comprobar_revision(plazo, revision)
    if not plazo.activo:
        raise ValidationError("El plazo está archivado y no admite recordatorios.")
    usuarios = destinatarios(plazo.grupos).exclude(envios__plazo=plazo)
    fecha = timezone.localtime(plazo.fecha_limite).strftime("%d/%m/%Y a las %H:%M")
    total = _crear_avisos(
        usuarios,
        tipo=Notificacion.Tipo.SEGUIMIENTO,
        plazo=plazo,
        titulo=f"Entrega pendiente: {plazo.titulo}"[:180],
        mensaje=f"Tu reporte aún no tiene una entrega registrada. Fecha límite: {fecha}. {plazo.descripcion}",
        enlace=reverse("notificaciones:mis_plazos") + f"?plazo={plazo.pk}",
    )
    if total:
        RegistroSeguridad.objects.create(
            actor=actor, accion="admin:recordar_pendientes", ruta=reverse("notificaciones:seguimiento_plazo", args=[pk])
        )
    return total
