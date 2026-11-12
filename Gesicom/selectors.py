"""Consultas de evidencias y resúmenes, compartidas por vistas, búsquedas y reportes."""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse

from .models import Envio
from .utils import apply_date_filters, is_admin_or_group, user_roles


def _home_url_for_user(user):
    if is_admin_or_group(user, []):
        return reverse("admin_personalizado:dashboard")
    roles = user_roles(user)
    for role in ["instructor", "investigador", "dinamizador", "coordinador"]:
        if role in roles:
            return reverse("role_" + role)
    return reverse("usuario") if "usuario" in roles else reverse("home")


def _filtros(request):
    from .filtros import FiltrosEvidenciasForm

    if not hasattr(request, "_filtros_evidencias"):
        request._filtros_evidencias = FiltrosEvidenciasForm(request.GET, visibles=_visible_envios(request.user))
        request._filtros_evidencias.is_valid()
    return request._filtros_evidencias


def _resumen_envios(consulta):
    return consulta.aggregate(
        total=Count("pk"),
        aprobadas=Count("pk", filter=Q(aprobada=True)),
        pendientes=Count("pk", filter=Q(aprobada=False, rechazada=False)),
        rechazadas=Count("pk", filter=Q(rechazada=True)),
    )


def _ordenar_envios(consulta, datos):
    campo = datos.get("order", "fecha_envio")
    direccion = datos.get("dir", "desc")
    return consulta.order_by(campo if direccion == "asc" else "-" + campo, "pk" if direccion == "asc" else "-pk")


def _evidencias_context(request):
    form = _filtros(request)
    datos = form.cleaned_data
    consulta = _ordenar_envios(_filtered_envios(request), datos).select_related("usuario")
    resumen = _resumen_envios(consulta)
    return {
        "envios": Paginator(consulta, 10).get_page(request.GET.get("page")),
        "total_envios": resumen["total"],
        "aprobadas": resumen["aprobadas"],
        "rechazadas": resumen["rechazadas"],
        "pendientes": resumen["pendientes"],
        "home_url": _home_url_for_user(request.user),
        "es_admin": is_admin_or_group(request.user, []),
        "puede_revisar": is_admin_or_group(request.user, ["coordinador", "dinamizador"]),
        "filtros_form": form,
        "opciones_proyectos": form.fields["proyecto"].choices[1:],
        "q": request.GET.get("q", "")[:100],
        "estado": request.GET.get("estado", ""),
        "start": request.GET.get("start", ""),
        "end": request.GET.get("end", ""),
        "proyecto": request.GET.get("proyecto", ""),
        "plazo_scope": datos.get("plazo") or "",
        "usuario_scope": datos.get("usuario") or "",
        "order": datos.get("order", "fecha_envio"),
        "dir": datos.get("dir", "desc"),
        "next_direction": "desc" if datos.get("dir") == "asc" else "asc",
    }


def _visible_envios(user):
    queryset = Envio.objects.all()
    if is_admin_or_group(user, ["coordinador", "dinamizador"]):
        return queryset
    return queryset.filter(usuario=user)


def _panel_context(user, role):
    from notificaciones.selectors import plazos_para_usuario, resumen_agenda

    envios = _visible_envios(user)
    resumen = envios.aggregate(
        total=Count("pk"),
        aprobadas=Count("pk", filter=Q(aprobada=True)),
        pendientes=Count("pk", filter=Q(aprobada=False, rechazada=False)),
        rechazadas=Count("pk", filter=Q(rechazada=True)),
    )
    return {
        "panel_role": role,
        "total_envios": resumen["total"],
        "aprobadas": resumen["aprobadas"],
        "pendientes": resumen["pendientes"],
        "rechazadas": resumen["rechazadas"],
        "recientes": envios.select_related("usuario").order_by("-registrado_en", "-pk")[:5],
        "proximos_plazos": plazos_para_usuario(user).order_by("fecha_limite", "pk")[:3],
        "agenda": resumen_agenda(user),
        "mis_correcciones": Envio.objects.filter(usuario=user, rechazada=True).count(),
        "revisiones": envios.filter(aprobada=False, rechazada=False)
        .select_related("usuario")
        .order_by("registrado_en", "pk")[:5]
        if is_admin_or_group(user, ["coordinador", "dinamizador"])
        else [],
    }


def _filtered_envios(request):
    from .filtros import SIN_PROYECTO

    queryset = _visible_envios(request.user)
    form = _filtros(request)
    if not form.is_valid():
        return queryset.none()
    datos = form.cleaned_data
    for campo in ("plazo", "usuario"):
        if datos.get(campo):
            queryset = queryset.filter(**{campo + "_id": datos[campo]})
    proyecto = datos["proyecto"]
    if proyecto:
        queryset = queryset.filter(proyecto="" if proyecto == SIN_PROYECTO else proyecto)
    queryset = apply_date_filters(queryset, datos["start"], datos["end"])
    if datos["q"]:
        queryset = queryset.filter(
            Q(nombre__icontains=datos["q"])
            | Q(tipo_evidencia__icontains=datos["q"])
            | Q(observaciones__icontains=datos["q"])
        )
    estado = datos["estado"]
    if estado == "aprobada":
        queryset = queryset.filter(aprobada=True)
    elif estado == "rechazada":
        queryset = queryset.filter(rechazada=True)
    elif estado == "pendiente":
        queryset = queryset.filter(aprobada=False, rechazada=False)
    return queryset
