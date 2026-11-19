"""Creación masiva e idempotente de avisos; el SMTP se procesa fuera de las vistas."""

import uuid
from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connection, transaction
from django.db.models import DateTimeField, DurationField, Exists, ExpressionWrapper, F, OuterRef, Q, Value
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import (
    CorreoPendiente,
    Notificacion,
    PlazoReporte,
    PreferenciasNotificacion,
)
from .selectors import destinatarios
from .selectors import plazos_para_usuario as plazos_para_usuario

User = get_user_model()


def _crear_avisos(users, *, tipo, titulo, mensaje, enlace="", novedad=None, plazo=None, envio=None):
    """Evita un INSERT por usuario y respeta las preferencias de correo."""
    user_ids = sorted(users.values_list("pk", flat=True))
    if not user_ids:
        return 0
    source = {"novedad": novedad} if novedad else {"plazo": plazo, "version_plazo": plazo.version} if plazo else {}
    if source:
        existentes = set(
            Notificacion.objects.filter(tipo=tipo, usuario_id__in=user_ids, **source).values_list(
                "usuario_id", flat=True
            )
        )
        user_ids = [pk for pk in user_ids if pk not in existentes]
    if not user_ids:
        return 0
    lote = uuid.uuid4()
    with transaction.atomic():
        Notificacion.objects.bulk_create(
            [
                Notificacion(
                    lote_id=lote,
                    usuario_id=pk,
                    tipo=tipo,
                    titulo=titulo,
                    mensaje=mensaje,
                    enlace=enlace,
                    envio=envio,
                    **source,
                )
                for pk in user_ids
            ],
            batch_size=500,
            ignore_conflicts=True,
        )
        creados = list(Notificacion.objects.filter(lote_id=lote).values_list("pk", "usuario_id"))
        preference = (
            "correo_novedades"
            if tipo == Notificacion.Tipo.NOVEDAD
            else "correo_evidencias"
            if tipo == Notificacion.Tipo.EVIDENCIA
            else "correo_plazos"
        )
        desactivados = set(
            PreferenciasNotificacion.objects.filter(usuario_id__in=user_ids, **{preference: False}).values_list(
                "usuario_id", flat=True
            )
        )
        CorreoPendiente.objects.bulk_create(
            [CorreoPendiente(notificacion_id=pk) for pk, user_id in creados if user_id not in desactivados],
            batch_size=500,
            ignore_conflicts=True,
        )
    return len(creados)


def publicar_novedad(novedad):
    return _crear_avisos(
        destinatarios(novedad.grupos),
        tipo=Notificacion.Tipo.NOVEDAD,
        titulo=novedad.titulo,
        mensaje=novedad.contenido,
        enlace=novedad.enlace or reverse("notificaciones:bandeja"),
        novedad=novedad,
    )


def anunciar_plazo(plazo):
    fecha = timezone.localtime(plazo.fecha_limite).strftime("%d/%m/%Y a las %H:%M")
    return _crear_avisos(
        destinatarios(plazo.grupos),
        tipo=Notificacion.Tipo.APERTURA,
        titulo=f"Nuevo plazo: {plazo.titulo}",
        mensaje=f"Fecha límite: {fecha}. {plazo.descripcion}",
        enlace=reverse("evidencia") + f"?plazo={plazo.pk}",
        plazo=plazo,
    )


def sincronizar_plazos(ahora=None):
    ahora = ahora or timezone.now()
    # MySQL y SQLite representan DurationField como microsegundos. Multiplicar
    # enteros evita que el backend de MySQL genere INTERVAL anidados.
    anticipacion = ExpressionWrapper(F("recordatorio_horas") * Value(3_600_000_000), output_field=DurationField())
    tope = ExpressionWrapper(Value(ahora, output_field=DateTimeField()) + anticipacion, output_field=DateTimeField())
    plazos = (
        PlazoReporte.objects.filter(activo=True, fecha_limite__lte=tope)
        .only("pk", "titulo", "fecha_limite", "recordatorio_horas", "version")
        .order_by("fecha_limite", "pk")
    )
    total = 0
    for plazo in plazos.iterator(chunk_size=100):
        tipo = Notificacion.Tipo.VENCIMIENTO if ahora >= plazo.fecha_limite else Notificacion.Tipo.RECORDATORIO
        estado = "Venció el plazo" if tipo == Notificacion.Tipo.VENCIMIENTO else "Se acerca el plazo"
        fecha = timezone.localtime(plazo.fecha_limite).strftime("%d/%m/%Y a las %H:%M")
        avisados = Notificacion.objects.filter(
            usuario_id=OuterRef("pk"), plazo=plazo, version_plazo=plazo.version, tipo=tipo
        )
        users = destinatarios(plazo.grupos).exclude(envios__plazo=plazo).filter(~Exists(avisados))
        total += _crear_avisos(
            users,
            tipo=tipo,
            titulo=f"{estado}: {plazo.titulo}",
            mensaje=f"La fecha límite es {fecha}. Aún no aparece un reporte asociado a tu cuenta.",
            enlace=reverse("evidencia") + f"?plazo={plazo.pk}",
            plazo=plazo,
        )
    return total


def notificar_revision(envio):
    if not envio.usuario_id:
        return 0
    estado = "aprobada" if envio.aprobada else "rechazada" if envio.rechazada else "en revisión"
    return _crear_avisos(
        User.objects.filter(pk=envio.usuario_id, is_active=True),
        tipo=Notificacion.Tipo.EVIDENCIA,
        titulo=f"Evidencia {estado}: {envio.nombre}",
        mensaje=envio.observaciones or f"Tu evidencia del proyecto {envio.proyecto} está {estado}.",
        enlace=reverse("ver_evidencia", args=[envio.pk]),
        envio=envio,
    )


def notificar_correccion(envio, revisor, *, enlace=None):
    return _crear_avisos(
        User.objects.filter(pk=revisor.pk, is_active=True),
        tipo=Notificacion.Tipo.EVIDENCIA,
        titulo=f"Corrección por revisar: {envio.nombre}"[:180],
        mensaje=f"Se actualizó una evidencia que revisaste. Versión {envio.version}. Consulta los cambios y su historial.",
        enlace=enlace or reverse("ver_evidencia", args=[envio.pk]),
        envio=envio,
    )


def procesar_correos(limite=50):
    """Reclama por lotes y comprueba que cada aviso siga siendo pertinente antes de SMTP."""
    from django.core.cache import cache

    from .acceso import destino_notificacion, motivo_cancelacion

    ahora = timezone.now()
    bloqueado_hasta = ahora + timedelta(seconds=max(600, limite * (settings.EMAIL_TIMEOUT + 15)))
    with transaction.atomic():
        candidatos = CorreoPendiente.objects.filter(
            Q(estado=CorreoPendiente.Estado.PENDIENTE)
            | Q(estado=CorreoPendiente.Estado.PROCESANDO, bloqueado_hasta__lt=ahora),
            proximo_intento__lte=ahora,
            intentos__lt=5,
        ).order_by("pk")
        if connection.features.has_select_for_update:
            candidatos = candidatos.select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
        ids = list(candidatos.values_list("pk", flat=True)[:limite])
        CorreoPendiente.objects.filter(pk__in=ids).update(
            estado=CorreoPendiente.Estado.PROCESANDO,
            bloqueado_hasta=bloqueado_hasta,
        )
    enviados = 0
    transport = get_connection(fail_silently=False)
    latido = ahora
    try:
        for pk in ids:
            if (timezone.now() - latido).total_seconds() >= 30:
                cache.set("notificaciones:trabajador", timezone.now().isoformat(), timeout=120)
                latido = timezone.now()
            correo = (
                CorreoPendiente.objects.filter(
                    pk=pk,
                    estado=CorreoPendiente.Estado.PROCESANDO,
                    bloqueado_hasta=bloqueado_hasta,
                    bloqueado_hasta__gt=timezone.now(),
                )
                .select_related(
                    "notificacion__usuario__preferencias_notificacion", "notificacion__plazo", "notificacion__novedad"
                )
                .first()
            )
            if not correo:
                continue
            notification = correo.notificacion
            user = notification.usuario
            preferencias = getattr(user, "preferencias_notificacion", None)
            campo = (
                "correo_novedades"
                if notification.tipo == Notificacion.Tipo.NOVEDAD
                else "correo_evidencias"
                if notification.tipo == Notificacion.Tipo.EVIDENCIA
                else "correo_plazos"
            )
            motivo = motivo_cancelacion(notification)
            if preferencias and not getattr(preferencias, campo):
                motivo = "El usuario desactivó este tipo de avisos por correo."
            aceptado = False
            if motivo:
                correo.estado = CorreoPendiente.Estado.CANCELADO
                correo.ultimo_error = motivo
            else:
                try:
                    destino, _ = destino_notificacion(notification)
                    link = urljoin(settings.PUBLIC_BASE_URL.rstrip("/") + "/", destino)
                    context = {"notificacion": notification, "usuario": user, "enlace": link}
                    message = EmailMultiAlternatives(
                        notification.titulo,
                        render_to_string("notificaciones/correo.txt", context),
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                        connection=transport,
                    )
                    message.attach_alternative(render_to_string("notificaciones/correo.html", context), "text/html")
                    transport.open()
                    if message.send(fail_silently=False) != 1:
                        raise RuntimeError("El mensaje no fue aceptado por el transporte.")
                    correo.estado = CorreoPendiente.Estado.ENVIADO
                    correo.enviado_en = timezone.now()
                    correo.ultimo_error = ""
                    aceptado = True
                    enviados += 1
                except Exception:
                    correo.intentos += 1
                    correo.estado = (
                        CorreoPendiente.Estado.ERROR if correo.intentos >= 5 else CorreoPendiente.Estado.PENDIENTE
                    )
                    correo.proximo_intento = timezone.now() + timedelta(minutes=min(60, 2**correo.intentos))
                    correo.ultimo_error = "El proveedor no aceptó el envío; revisa la configuración SMTP."
                    transport.close()
            # Un resultado tardío no sobrescribe otra reclamación. Si SMTP ya
            # aceptó un aviso cancelado durante el envío, se conserva ese hecho.
            pertenece = Q(
                estado=CorreoPendiente.Estado.PROCESANDO,
                bloqueado_hasta=bloqueado_hasta,
            )
            if aceptado:
                pertenece |= Q(estado=CorreoPendiente.Estado.CANCELADO, bloqueado_hasta__isnull=True)
            CorreoPendiente.objects.filter(pertenece, pk=correo.pk).update(
                estado=correo.estado,
                intentos=correo.intentos,
                proximo_intento=correo.proximo_intento,
                ultimo_error=correo.ultimo_error,
                enviado_en=correo.enviado_en,
                bloqueado_hasta=None,
            )
    finally:
        transport.close()
    return enviados
