"""Listado administrativo y métricas agrupadas solo para su página visible."""

from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Prefetch, Q

from .models import CorreoPendiente, Notificacion, Novedad

CAMPOS_METRICAS = (
    "destinatarios_total",
    "leidas_total",
    "enviados_total",
    "pendientes_total",
    "errores_total",
    "cancelados_total",
    "correos_total",
)


def novedades_filtradas(form):
    consulta = (
        Novedad.objects.select_related("creada_por")
        .only(
            "pk",
            "titulo",
            "contenido",
            "enlace",
            "publicada_en",
            "creada_por__id",
            "creada_por__username",
            "creada_por__first_name",
            "creada_por__last_name",
        )
        .prefetch_related(Prefetch("grupos", queryset=Group.objects.only("pk", "name").order_by("name")))
        .order_by("-publicada_en", "-pk")
    )
    if not form.is_valid():
        return consulta.none()
    datos = form.cleaned_data
    if q := datos["q"]:
        consulta = consulta.filter(Q(titulo__icontains=q) | Q(contenido__icontains=q))
    asignaciones = Novedad.grupos.through.objects.filter(novedad_id=OuterRef("pk"))
    if datos["audiencia"] == "general":
        consulta = consulta.filter(~Exists(asignaciones))
    elif datos["audiencia"] == "grupos":
        consulta = consulta.filter(Exists(asignaciones))
    if estado := datos["correo"]:
        correos = CorreoPendiente.objects.filter(notificacion__novedad_id=OuterRef("pk"))
        if estado == "sin_correo":
            consulta = consulta.filter(~Exists(correos))
        else:
            estados = ["pendiente", "procesando"] if estado == "pendientes" else [estado]
            consulta = consulta.filter(Exists(correos.filter(estado__in=estados)))
    return consulta


def pagina_novedades(form, numero=None):
    pagina = Paginator(novedades_filtradas(form), 20).get_page(numero)
    registros = list(pagina.object_list)
    pagina.object_list = registros
    if not registros:
        return pagina
    # Correo es uno a uno con el aviso: no se une la relación de grupos al contar.
    metricas = (
        Notificacion.objects.filter(novedad_id__in=[n.pk for n in registros])
        .values("novedad_id")
        .annotate(
            destinatarios_total=Count("pk"),
            leidas_total=Count("pk", filter=Q(leida_en__isnull=False)),
            enviados_total=Count("correo", filter=Q(correo__estado="enviado")),
            pendientes_total=Count("correo", filter=Q(correo__estado__in=["pendiente", "procesando"])),
            errores_total=Count("correo", filter=Q(correo__estado="error")),
            cancelados_total=Count("correo", filter=Q(correo__estado="cancelado")),
            correos_total=Count("correo"),
        )
        .order_by()
    )
    por_novedad = {fila["novedad_id"]: fila for fila in metricas}
    for novedad in registros:
        fila = por_novedad.get(novedad.pk, {})
        for campo in CAMPOS_METRICAS:
            setattr(novedad, campo, fila.get(campo, 0))
        novedad.sin_correo_total = novedad.destinatarios_total - novedad.correos_total
        novedad.lectura_porcentaje = (
            round(novedad.leidas_total * 100 / novedad.destinatarios_total) if novedad.destinatarios_total else 0
        )
    return pagina
