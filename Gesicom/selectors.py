"""Consultas de evidencias y resúmenes, compartidas por vistas, búsquedas y reportes."""

import datetime

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

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


def _evidencias_context(request, incluir_graficos=False):
    home_url = _home_url_for_user(request.user)
    consulta = _filtered_envios(request).select_related("usuario")
    proyecto = request.GET.get("proyecto", "")
    inicio = request.GET.get("start", "")
    fin = request.GET.get("end", "")
    termino_busqueda = (request.GET.get("q") or "").strip()
    estado = request.GET.get("estado", "")
    orden = request.GET.get("order", "fecha_envio")
    direccion = request.GET.get("dir", "desc")
    permitidos = {"fecha_envio", "nombre", "proyecto", "tipo_evidencia"}
    if orden in permitidos:
        criterio_orden = orden if direccion == "asc" else f"-{orden}"
        consulta = consulta.order_by(criterio_orden, "-pk")
    else:
        consulta = consulta.order_by("-fecha_envio", "-pk")
    paginador = Paginator(consulta, 10)
    numero_pagina = request.GET.get("page")
    objeto_pagina = paginador.get_page(numero_pagina)
    hoy = timezone.localdate()
    hace_30 = hoy - datetime.timedelta(days=30)
    hace_60 = hoy - datetime.timedelta(days=60)
    resumen = consulta.aggregate(
        total=Count("pk"),
        nuevas=Count("pk", filter=Q(fecha_envio__gte=hace_30)),
        anteriores=Count("pk", filter=Q(fecha_envio__gte=hace_60, fecha_envio__lt=hace_30)),
        aprobadas=Count("pk", filter=Q(aprobada=True)),
        rechazadas=Count("pk", filter=Q(rechazada=True)),
        aprobadas_recientes=Count("pk", filter=Q(aprobada=True, fecha_envio__gte=hace_30)),
        aprobadas_anteriores=Count("pk", filter=Q(aprobada=True, fecha_envio__gte=hace_60, fecha_envio__lt=hace_30)),
        pendientes=Count("pk", filter=Q(aprobada=False, rechazada=False)),
    )
    total_envios = resumen["total"]
    nuevas_30d, nuevas_prev_30d = resumen["nuevas"], resumen["anteriores"]
    aprobadas, rechazadas = resumen["aprobadas"], resumen["rechazadas"]
    aprobadas_30d, aprobadas_prev_30d = resumen["aprobadas_recientes"], resumen["aprobadas_anteriores"]

    def cambio_porcentaje(current, previous):
        try:
            if previous == 0:
                return None if current == 0 else 100.0
            return round(((current - previous) / previous) * 100, 1)
        except Exception:
            return None

    pct_nuevas = cambio_porcentaje(nuevas_30d, nuevas_prev_30d)
    pct_aprobadas = cambio_porcentaje(aprobadas_30d, aprobadas_prev_30d)
    pct_total = cambio_porcentaje(nuevas_30d, nuevas_prev_30d)
    pct_nuevas_abs = abs(pct_nuevas) if pct_nuevas is not None else None
    pct_aprobadas_abs = abs(pct_aprobadas) if pct_aprobadas is not None else None
    pct_total_abs = abs(pct_total) if pct_total is not None else None
    opciones_proyectos = list(Envio.PROYECTO_CHOICES)
    try:
        num_quarters = max(1, min(12, int(request.GET.get("quarters", 4))))
    except (ValueError, TypeError):
        num_quarters = 4
    categorias_labels, categorias_data = [], []
    trimestres_labels, datos_trimestrales_nuevas, datos_trimestrales_aprobadas = [], [], []
    usuarios_labels, usuarios_data = [], []
    if incluir_graficos:
        from django.db.models.functions import ExtractQuarter, ExtractYear

        proyectos = dict(
            consulta.values("proyecto").annotate(total=Count("pk")).order_by().values_list("proyecto", "total")
        )
        for code, label in Envio.PROYECTO_CHOICES:
            if proyectos.get(code):
                categorias_labels.append(label)
                categorias_data.append(proyectos[code])
        trimestral = (
            consulta.annotate(anio=ExtractYear("fecha_envio"), trimestre=ExtractQuarter("fecha_envio"))
            .values("anio", "trimestre")
            .annotate(nuevas=Count("pk"), aprobadas=Count("pk", filter=Q(aprobada=True)))
            .order_by()
        )
        mapa = {(row["anio"], row["trimestre"]): row for row in trimestral}
        serial = hoy.year * 4 + (hoy.month - 1) // 3
        for valor in range(serial - num_quarters + 1, serial + 1):
            anio, trimestre = valor // 4, valor % 4 + 1
            row = mapa.get((anio, trimestre), {})
            trimestres_labels.append(f"Q{trimestre} {anio}")
            datos_trimestrales_nuevas.append(row.get("nuevas", 0))
            datos_trimestrales_aprobadas.append(row.get("aprobadas", 0))
        top = (
            consulta.values("usuario__first_name", "usuario__last_name", "usuario__username")
            .annotate(total=Count("pk"))
            .order_by("-total")[:6]
        )
        for row in top:
            nombre = (
                " ".join(filter(None, [row["usuario__first_name"], row["usuario__last_name"]]))
                or row["usuario__username"]
                or "Usuario"
            )
            usuarios_labels.append(nombre)
            usuarios_data.append(row["total"])
    es_admin = is_admin_or_group(request.user, [])

    context = {
        "envios": objeto_pagina,
        "proyecto": proyecto,
        "order": orden,
        "dir": direccion,
        "start": inicio,
        "end": fin,
        "opciones_proyectos": opciones_proyectos,
        "total_envios": total_envios,
        "nuevas_30d": nuevas_30d,
        "aprobadas": aprobadas,
        "rechazadas": rechazadas,
        "pendientes": resumen["pendientes"],
        "categorias_labels_json": categorias_labels,
        "categorias_data_json": categorias_data,
        "trimestres_labels_json": trimestres_labels,
        "datos_trimestrales_nuevas_json": datos_trimestrales_nuevas,
        "datos_trimestrales_aprobadas_json": datos_trimestrales_aprobadas,
        "usuarios_labels_json": usuarios_labels,
        "usuarios_data_json": usuarios_data,
        "pct_nuevas": pct_nuevas,
        "pct_aprobadas": pct_aprobadas,
        "pct_total": pct_total,
        "pct_nuevas_abs": pct_nuevas_abs,
        "pct_aprobadas_abs": pct_aprobadas_abs,
        "pct_total_abs": pct_total_abs,
        "aprobadas_30d": aprobadas_30d,
        "home_url": home_url,
        "es_admin": es_admin,
        "puede_revisar": is_admin_or_group(request.user, ["coordinador", "dinamizador"]),
        "q": termino_busqueda,
        "estado": estado,
        "quarters": num_quarters,
        "next_direction": "desc" if direccion == "asc" else "asc",
        "status_chart": [aprobadas, resumen["pendientes"], rechazadas],
    }
    return context


def _visible_envios(user):
    queryset = Envio.objects.all()
    if is_admin_or_group(user, ["coordinador", "dinamizador"]):
        return queryset
    return queryset.filter(usuario=user)


def _panel_context(user, role):
    from notificaciones.services import plazos_para_usuario

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
        "recientes": envios.order_by("-fecha_envio", "-pk")[:5],
        "proximos_plazos": plazos_para_usuario(user).filter(fecha_limite__gte=timezone.now())[:3],
    }


def _filtered_envios(request):
    queryset = _visible_envios(request.user)
    proyecto = request.GET.get("proyecto", "")
    if proyecto:
        queryset = queryset.filter(proyecto=proyecto)
    queryset = apply_date_filters(queryset, request.GET.get("start", ""), request.GET.get("end", ""))
    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(nombre__icontains=query) | Q(tipo_evidencia__icontains=query) | Q(observaciones__icontains=query)
        )
    estado = request.GET.get("estado", "")
    if estado == "aprobada":
        queryset = queryset.filter(aprobada=True)
    elif estado == "rechazada":
        queryset = queryset.filter(rechazada=True)
    elif estado == "pendiente":
        queryset = queryset.filter(aprobada=False, rechazada=False)
    return queryset
