"""Escrituras de evidencias serializadas, con historial y control de versiones."""

import logging
from contextlib import contextmanager
from dataclasses import dataclass

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from notificaciones.models import PlazoReporte
from notificaciones.services import notificar_correccion, notificar_revision, plazos_para_usuario

from .models import Envio, MovimientoEvidencia, SolicitudEnvio
from .validators import validar_archivo_evidencia

logger = logging.getLogger(__name__)


class ConflictoEvidencia(ValidationError):
    def __init__(self):
        super().__init__(
            "La evidencia cambió mientras la consultabas. Abre la versión actual y revisa los cambios antes de guardar."
        )


def comprobar_version(envio, version):
    # Las rutas de revisión históricas pueden omitirla. Los formularios actuales siempre la envían.
    if version in (None, ""):
        return
    try:
        vigente = int(version) == envio.version
    except (ValueError, TypeError):
        vigente = False
    if not vigente:
        raise ConflictoEvidencia()


def _revisor_autorizado(actor, roles):
    return (
        User.objects.filter(pk=actor.pk, is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name__in=["administrador", *roles]))
        .exists()
    )


def registrar_movimiento(envio, actor, accion, detalle=""):
    return MovimientoEvidencia.objects.create(
        envio=envio, actor=actor, accion=accion, version=envio.version, estado=envio.estado, detalle=detalle
    )


def _archivo_sin_referencias(storage, nombre):
    try:
        if nombre and not Envio.objects.filter(archivo_evidencia=nombre).exists():
            storage.delete(nombre)
    except Exception:
        logger.warning("No se pudo retirar un adjunto sustituido de evidencia.")


@contextmanager
def transaccion_evidencia():
    nuevos = []
    try:
        with transaction.atomic():
            yield nuevos
    except Exception:
        # El almacenamiento no participa en la transacción SQL: retirar solo los archivos nuevos huérfanos.
        for envio, anterior in nuevos:
            archivo = envio.archivo_evidencia
            if archivo and archivo._committed and archivo.name != anterior:
                _archivo_sin_referencias(archivo.storage, archivo.name)
        raise


def retirar_adjunto_sustituido(envio, nombre_anterior, storage):
    if nombre_anterior and nombre_anterior != envio.archivo_evidencia.name:
        transaction.on_commit(lambda: _archivo_sin_referencias(storage, nombre_anterior))


@dataclass(frozen=True)
class ResultadoRegistro:
    envio: Envio
    reutilizado: bool = False


def registrar_evidencia(actor, datos):
    return registrar_o_recuperar(actor, datos).envio


def _resultado_previo(solicitud, actor):
    if not solicitud.envio_id or solicitud.envio.usuario_id != actor.pk:
        raise ValidationError(
            "Este formulario ya fue procesado y su registro no está disponible. Abre un formulario nuevo para otra evidencia."
        )
    return ResultadoRegistro(solicitud.envio, reutilizado=True)


def recuperar_registro(actor, codigo):
    solicitud = SolicitudEnvio.objects.filter(codigo=codigo, usuario=actor).select_related("envio").first()
    return _resultado_previo(solicitud, actor) if solicitud else None


def registrar_o_recuperar(actor, datos):
    if not User.objects.filter(pk=actor.pk, is_active=True).exists():
        raise PermissionDenied
    with transaccion_evidencia() as nuevos:
        solicitud = None
        if codigo := datos.get("solicitud"):
            solicitud, creada = SolicitudEnvio.objects.get_or_create(codigo=codigo, defaults={"usuario": actor})
            solicitud = SolicitudEnvio.objects.select_for_update().get(pk=solicitud.pk)
            if solicitud.usuario_id != actor.pk:
                raise PermissionDenied
            if not creada:
                return _resultado_previo(solicitud, actor)
        if datos.get("archivo"):
            validar_archivo_evidencia(datos["archivo"])
        envio = Envio(
            usuario=actor,
            nombre=datos["nombre"],
            proyecto=datos["proyecto"],
            tipo_evidencia=", ".join(datos.get("evidencias", [])) or "Sin especificar",
            link_evidencia=datos.get("linkArchivo") or None,
            archivo_evidencia=datos.get("archivo"),
            observaciones=datos.get("observaciones", ""),
        )
        plazo = datos.get("plazo")
        if plazo:
            plazo = PlazoReporte.objects.select_for_update().filter(pk=plazo.pk).first()
            if not plazo or not plazos_para_usuario(actor).filter(pk=plazo.pk).exists():
                raise ValidationError("El plazo ya no está disponible para tu cuenta. Actualiza el formulario.")
            if plazo.proyecto and plazo.proyecto != datos["proyecto"]:
                raise ValidationError("El proyecto debe coincidir con el plazo seleccionado.")
        envio.plazo = plazo
        envio.actualizado_en = envio.registrado_en
        envio.limite_aplicado = plazo.fecha_limite if plazo else None
        if datos.get("archivo"):
            nuevos.append((envio, None))
        envio.save()
        registrar_movimiento(envio, actor, MovimientoEvidencia.Accion.REGISTRO)
        if solicitud:
            solicitud.envio = envio
            solicitud.save(update_fields=["envio"])
    return ResultadoRegistro(envio)


def corregir_evidencia(actor, pk, datos):
    if not User.objects.filter(pk=actor.pk, is_active=True).exists():
        raise PermissionDenied
    if datos.get("archivo"):
        validar_archivo_evidencia(datos["archivo"])
    with transaccion_evidencia() as nuevos:
        envio = Envio.objects.select_for_update().filter(pk=pk, usuario=actor).first()
        if not envio:
            raise Http404
        if not datos.get("version"):
            raise ConflictoEvidencia()
        comprobar_version(envio, datos["version"])
        if envio.aprobada:
            raise PermissionDenied("Una evidencia aprobada no se puede corregir.")
        if envio.plazo_id:
            plazo = PlazoReporte.objects.select_for_update().get(pk=envio.plazo_id)
            if plazo.proyecto and plazo.proyecto != datos["proyecto"] and datos["proyecto"] != envio.proyecto:
                raise ValidationError("El proyecto debe coincidir con el plazo seleccionado.")
        anterior_archivo = envio.archivo_evidencia.name
        storage = envio.archivo_evidencia.storage
        for campo in ("nombre", "proyecto"):
            setattr(envio, campo, datos[campo])
        envio.tipo_evidencia = ", ".join(datos.get("evidencias", [])) or "Sin especificar"
        envio.link_evidencia = datos.get("linkArchivo") or None
        if datos.get("archivo"):
            envio.archivo_evidencia = datos["archivo"]
            nuevos.append((envio, anterior_archivo))
        elif datos.get("eliminar_archivo"):
            envio.archivo_evidencia = ""
        envio.aprobada = envio.rechazada = False
        envio.version += 1
        envio.actualizado_en = timezone.now()
        envio.save(
            update_fields=[
                "nombre",
                "proyecto",
                "tipo_evidencia",
                "link_evidencia",
                "archivo_evidencia",
                "aprobada",
                "rechazada",
                "version",
                "actualizado_en",
            ]
        )
        registrar_movimiento(envio, actor, MovimientoEvidencia.Accion.CORRECCION, datos["motivo"])
        previo = (
            envio.historial.filter(
                accion=MovimientoEvidencia.Accion.REVISION,
                actor__is_active=True,
            )
            .select_related("actor")
            .first()
        )
        if previo and previo.actor_id != actor.pk:
            revisor = previo.actor
            if _revisor_autorizado(revisor, ["coordinador", "dinamizador"]):
                notificar_correccion(envio, revisor)
            elif revisor.is_staff and revisor.has_perm("Gesicom.change_envio"):
                notificar_correccion(envio, revisor, enlace=reverse("admin:Gesicom_envio_change", args=[envio.pk]))
        retirar_adjunto_sustituido(envio, anterior_archivo, storage)
    return envio


@transaction.atomic
def revisar_evidencia(actor, pk, aprobada, *, version=None):
    if not _revisor_autorizado(actor, ["coordinador", "dinamizador"]):
        raise PermissionDenied
    envio = Envio.objects.select_for_update().filter(pk=pk).first()
    if not envio:
        raise Http404
    comprobar_version(envio, version)
    if (envio.aprobada, envio.rechazada) == (aprobada, not aprobada):
        return envio, False
    envio.aprobada, envio.rechazada = aprobada, not aprobada
    envio.version += 1
    envio.actualizado_en = timezone.now()
    envio.save(update_fields=["aprobada", "rechazada", "version", "actualizado_en"])
    registrar_movimiento(envio, actor, MovimientoEvidencia.Accion.REVISION)
    notificar_revision(envio)
    return envio, True


@transaction.atomic
def observar_evidencia(actor, pk, texto, *, version=None):
    if not _revisor_autorizado(actor, []):
        raise PermissionDenied
    if len(texto) > 2000:
        raise ValidationError("Las observaciones admiten hasta 2000 caracteres.")
    envio = Envio.objects.select_for_update().filter(pk=pk).first()
    if not envio:
        raise Http404
    comprobar_version(envio, version)
    if (envio.observaciones or "") == texto:
        return envio
    envio.observaciones = texto
    envio.version += 1
    envio.actualizado_en = timezone.now()
    envio.save(update_fields=["observaciones", "version", "actualizado_en"])
    registrar_movimiento(envio, actor, MovimientoEvidencia.Accion.OBSERVACION, texto)
    notificar_revision(envio)
    return envio
