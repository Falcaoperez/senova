"""Consultas de agenda, bandeja y cumplimiento sin cargar listas completas."""

from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.utils import timezone

from Gesicom.models import Envio

from .models import Notificacion, PlazoReporte

User = get_user_model()


def destinatarios(grupos):
    queryset = User.objects.filter(is_active=True)
    ids = [grupo.pk for grupo in grupos.all()]
    miembros = User.groups.through.objects.filter(group_id__in=ids).values("user_id")
    return queryset.filter(pk__in=miembros) if ids else queryset


def plazos_para_usuario(user, pendientes=True):
    grupos = user.groups.values_list("pk", flat=True)
    asignaciones = PlazoReporte.grupos.through.objects.filter(plazoreporte_id=OuterRef("pk"))
    queryset = PlazoReporte.objects.filter(activo=True).filter(
        ~Exists(asignaciones) | Exists(asignaciones.filter(group_id__in=grupos))
    )
    if pendientes:
        queryset = queryset.exclude(envios__usuario=user)
    return queryset


def plazos_con_entregas(user):
    entregas = Envio.objects.filter(plazo_id=OuterRef("pk"), usuario=user)
    a_tiempo = entregas.filter(Q(limite_aplicado__isnull=True) | Q(registrado_en__lte=F("limite_aplicado")))
    return plazos_para_usuario(user, pendientes=False).annotate(entregado=Exists(entregas), a_tiempo=Exists(a_tiempo))


def resumen_agenda(user):
    ahora = timezone.now()
    return plazos_con_entregas(user).aggregate(
        total=Count("pk", distinct=True),
        entregados=Count("pk", distinct=True, filter=Q(entregado=True)),
        vencidos=Count("pk", distinct=True, filter=Q(entregado=False, fecha_limite__lte=ahora)),
        pendientes=Count("pk", distinct=True, filter=Q(entregado=False, fecha_limite__gt=ahora)),
        tardios=Count("pk", distinct=True, filter=Q(entregado=True, a_tiempo=False)),
    )


def agenda_filtrada(user, params):
    queryset = plazos_con_entregas(user)
    q = params.get("q", "").strip()[:100]
    if q:
        queryset = queryset.filter(Q(titulo__icontains=q) | Q(descripcion__icontains=q))
    proyecto = params.get("proyecto", "")
    if proyecto:
        queryset = queryset.filter(proyecto=proyecto)
    pk = params.get("plazo", "")
    if pk.isascii() and pk.isdigit() and len(pk) <= 18:
        queryset = queryset.filter(pk=pk)
    estado = params.get("estado", "")
    if estado in {"pendiente", "vencido"}:
        queryset = queryset.filter(entregado=False)
        queryset = (
            queryset.filter(fecha_limite__lte=timezone.now())
            if estado == "vencido"
            else queryset.filter(fecha_limite__gt=timezone.now())
        )
    elif estado == "entregado":
        queryset = queryset.filter(entregado=True)
    elif estado == "tardia":
        queryset = queryset.filter(entregado=True, a_tiempo=False)
    return queryset.order_by("entregado", "fecha_limite", "pk")


def avisos_filtrados(user, params):
    queryset = Notificacion.objects.filter(usuario=user)
    q = params.get("q", "").strip()[:100]
    if q:
        queryset = queryset.filter(Q(titulo__icontains=q) | Q(mensaje__icontains=q))
    if params.get("tipo") in dict(Notificacion.Tipo.choices):
        queryset = queryset.filter(tipo=params["tipo"])
    estado = params.get("estado", "")
    if estado in {"pendiente", "leida"}:
        queryset = queryset.filter(leida_en__isnull=estado == "pendiente")
    pk = params.get("aviso", "")
    if pk.isascii() and pk.isdigit() and len(pk) <= 18:
        queryset = queryset.filter(pk=pk)
    return queryset


def seguimiento_destinatarios(plazo):
    entregas = Envio.objects.filter(plazo=plazo, usuario_id=OuterRef("pk"))
    a_tiempo = entregas.filter(Q(limite_aplicado__isnull=True) | Q(registrado_en__lte=F("limite_aplicado")))
    ultima = entregas.order_by("-registrado_en", "-pk")
    avisados = Notificacion.objects.filter(
        plazo=plazo, version_plazo=plazo.version, tipo=Notificacion.Tipo.SEGUIMIENTO, usuario_id=OuterRef("pk")
    )
    return (
        destinatarios(plazo.grupos)
        .annotate(
            entregado=Exists(entregas),
            a_tiempo=Exists(a_tiempo),
            recordado=Exists(avisados),
            ultima_entrega=Subquery(ultima.values("registrado_en")[:1]),
            ultima_aprobada=Subquery(ultima.values("aprobada")[:1]),
            ultima_rechazada=Subquery(ultima.values("rechazada")[:1]),
        )
        .order_by("username", "pk")
    )


def resumen_seguimiento(plazo):
    # Excluir las subconsultas de la última evidencia del conteo global: solo se
    # necesitan en las 25 filas de la página, no para cada destinatario del plazo.
    resumen = (
        seguimiento_destinatarios(plazo)
        .values("pk", "entregado", "a_tiempo", "recordado")
        .aggregate(
            total=Count("pk", distinct=True),
            entregados=Count("pk", distinct=True, filter=Q(entregado=True)),
            puntuales=Count("pk", distinct=True, filter=Q(a_tiempo=True)),
            tardios=Count("pk", distinct=True, filter=Q(entregado=True, a_tiempo=False)),
            pendientes=Count("pk", distinct=True, filter=Q(entregado=False)),
            sin_recordatorio=Count("pk", distinct=True, filter=Q(entregado=False, recordado=False)),
        )
    )
    resumen["a_tiempo"] = resumen.pop("puntuales")
    return resumen


def seguimiento_filtrado(plazo, params):
    queryset = seguimiento_destinatarios(plazo)
    q = params.get("q", "").strip()[:100]
    if q:
        queryset = queryset.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    estado = params.get("estado", "")
    if estado == "pendiente":
        queryset = queryset.filter(entregado=False)
    elif estado == "entregado":
        queryset = queryset.filter(entregado=True)
    elif estado == "tardia":
        queryset = queryset.filter(entregado=True, a_tiempo=False)
    elif estado == "a_tiempo":
        queryset = queryset.filter(a_tiempo=True)
    return queryset
