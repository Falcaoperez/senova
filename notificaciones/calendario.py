"""Distribución mensual de plazos ya filtrados y autorizados por la agenda."""

import datetime
from collections import defaultdict

from django.utils import timezone

MAX_PLAZOS_CALENDARIO = 500


def limites_mes(mes):
    siguiente = datetime.date(mes.year + mes.month // 12, mes.month % 12 + 1, 1)
    return tuple(timezone.make_aware(datetime.datetime.combine(fecha, datetime.time.min)) for fecha in (mes, siguiente))


def meses_vecinos(mes):
    anterior = None if mes == datetime.date(1000, 1, 1) else (mes - datetime.timedelta(days=1)).strftime("%Y-%m")
    siguiente = None if mes == datetime.date(9998, 12, 1) else limites_mes(mes)[1].strftime("%Y-%m")
    return anterior, siguiente


def cuadricula_mensual(queryset, mes):
    plazos = list(queryset.order_by("fecha_limite", "pk")[: MAX_PLAZOS_CALENDARIO + 1])
    truncado = len(plazos) > MAX_PLAZOS_CALENDARIO
    dias = defaultdict(list)
    for plazo in plazos[:MAX_PLAZOS_CALENDARIO]:
        dias[timezone.localtime(plazo.fecha_limite).date()].append(plazo)
    inicio = mes - datetime.timedelta(days=mes.weekday())
    hoy = timezone.localdate()
    celdas = []
    for indice in range(42):
        fecha = inicio + datetime.timedelta(days=indice)
        celdas.append({"fecha": fecha, "es_mes": fecha.month == mes.month, "hoy": fecha == hoy, "plazos": dias[fecha]})
    anterior, siguiente = meses_vecinos(mes)
    return {
        "dias_calendario": celdas,
        "mes_fecha": mes,
        "mes_anterior": anterior,
        "mes_siguiente": siguiente,
        "calendario_truncado": truncado,
        "total_calendario": min(len(plazos), MAX_PLAZOS_CALENDARIO),
        "dias_semana": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    }
