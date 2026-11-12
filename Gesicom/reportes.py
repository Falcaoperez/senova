"""Estadísticas y series históricas compartidas por la pantalla y su exportación."""

import calendar
import datetime

from django.db.models import Count, Q
from django.db.models.functions import ExtractQuarter, ExtractYear
from django.urls import reverse
from django.utils import timezone

from .filtros import ESTADOS, SIN_PROYECTO
from .models import Envio
from .selectors import _filtered_envios, _filtros, _ordenar_envios, _resumen_envios


def limites_trimestres(form):
    fin = form.mes("end") or timezone.localdate()
    serial = fin.year * 4 + (fin.month - 1) // 3
    desde = max(4000, serial - form.cleaned_data.get("quarters", 4) + 1)
    primero = datetime.date(desde // 4, (desde % 4) * 3 + 1, 1)
    ultimo_mes = (serial % 4) * 3 + 3
    ultimo = datetime.date(fin.year, ultimo_mes, calendar.monthrange(fin.year, ultimo_mes)[1])
    return desde, serial, primero, ultimo


def serie_trimestral(consulta, form):
    if not form.is_valid():
        return []
    desde, hasta, primero, ultimo = limites_trimestres(form)
    agrupado = (
        consulta.filter(fecha_envio__range=(primero, ultimo))
        .annotate(anio=ExtractYear("fecha_envio"), trimestre=ExtractQuarter("fecha_envio"))
        .values("anio", "trimestre")
        .annotate(nuevas=Count("pk"), aprobadas=Count("pk", filter=Q(aprobada=True)))
        .order_by()
    )
    mapa = {(f["anio"], f["trimestre"]): f for f in agrupado}
    filas = []
    for serial in range(desde, hasta + 1):
        anio, trimestre = serial // 4, serial % 4 + 1
        fila = mapa.get((anio, trimestre), {})
        filas.append(
            {"etiqueta": f"Q{trimestre} {anio}", "nuevas": fila.get("nuevas", 0), "aprobadas": fila.get("aprobadas", 0)}
        )
    return filas


def contexto_reportes(request):
    form = _filtros(request)
    consulta = _filtered_envios(request)
    resumen = _resumen_envios(consulta)
    serie = serie_trimestral(consulta, form)
    proyectos = []
    nombres = dict(Envio.PROYECTO_CHOICES)
    for fila in consulta.values("proyecto").annotate(total=Count("pk")).order_by("-total", "proyecto"):
        codigo = fila["proyecto"]
        proyectos.append(
            {
                "codigo": codigo or SIN_PROYECTO,
                "nombre": nombres.get(codigo, codigo) or "Sin proyecto",
                "total": fila["total"],
            }
        )
    usuarios = []
    for fila in (
        consulta.values("usuario_id", "usuario__first_name", "usuario__last_name", "usuario__username")
        .annotate(total=Count("pk"))
        .order_by("-total", "usuario_id")[:6]
    ):
        nombre = (
            " ".join(filter(None, [fila["usuario__first_name"], fila["usuario__last_name"]]))
            or fila["usuario__username"]
            or "Cuenta no disponible"
        )
        usuarios.append(
            {
                "id": fila["usuario_id"],
                "nombre": nombre,
                "usuario": fila["usuario__username"] or "",
                "total": fila["total"],
            }
        )
    estados = [
        {"codigo": "aprobada", "nombre": "Aprobadas", "total": resumen["aprobadas"]},
        {"codigo": "pendiente", "nombre": "En revisión", "total": resumen["pendientes"]},
        {"codigo": "rechazada", "nombre": "Rechazadas", "total": resumen["rechazadas"]},
    ]
    consulta_url = form.consulta_url()
    return {
        "filtros_form": form,
        "total_envios": resumen["total"],
        "aprobadas": resumen["aprobadas"],
        "pendientes": resumen["pendientes"],
        "rechazadas": resumen["rechazadas"],
        "serie_trimestral": serie,
        "ultimo_trimestre": serie[-1]["etiqueta"] if serie else "",
        "proyectos_resumen": proyectos,
        "usuarios_resumen": usuarios,
        "estados_resumen": estados,
        "serie_total": sum(f["nuevas"] for f in serie),
        "generado_en": timezone.now(),
        "trimestres_labels_json": [f["etiqueta"] for f in serie],
        "datos_trimestrales_nuevas_json": [f["nuevas"] for f in serie],
        "datos_trimestrales_aprobadas_json": [f["aprobadas"] for f in serie],
        "categorias_labels_json": [f["nombre"] for f in proyectos],
        "categorias_data_json": [f["total"] for f in proyectos],
        "proyectos_codes": [f["codigo"] for f in proyectos],
        "usuarios_labels_json": [f["nombre"] for f in usuarios],
        "usuarios_data_json": [f["total"] for f in usuarios],
        "status_chart": [f["total"] for f in estados],
        "download_query": consulta_url,
        "detalle_url": reverse("evidencias_list") + consulta_url,
    }


def filas_evidencias(request):
    consulta = _ordenar_envios(_filtered_envios(request), _filtros(request).cleaned_data).select_related(
        "usuario", "plazo"
    )
    yield [
        "fecha_envio",
        "nombre",
        "proyecto",
        "tipo_evidencia",
        "link_evidencia",
        "observaciones",
        "estado",
        "usuario",
        "primera_entrega_colombia",
        "plazo",
        "limite_aplicado_colombia",
        "fuera_de_plazo",
    ]

    def fecha(value):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S") if value else ""

    for envio in consulta.iterator(chunk_size=500):
        yield [
            envio.fecha_envio.isoformat(),
            envio.nombre,
            envio.proyecto,
            envio.tipo_evidencia,
            envio.link_evidencia or "",
            (envio.observaciones or "").replace("\r\n", " ").replace("\n", " "),
            dict(ESTADOS)[envio.estado],
            envio.usuario.username if envio.usuario else "",
            fecha(envio.registrado_en),
            envio.plazo.titulo if envio.plazo else "",
            fecha(envio.limite_aplicado),
            "Sí" if envio.entrega_tardia else "No",
        ]
