"""Exportación iCalendar privada, sin invitaciones ni sincronización externa."""

import datetime
import uuid
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.http import StreamingHttpResponse
from django.urls import reverse
from django.utils import timezone


def escapar_texto(value):
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(c for c in value if c == "\n" or ord(c) >= 32 and ord(c) != 127)
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def plegar_linea(value):
    linea, tamano = "", 0
    for caracter in value:
        longitud = len(caracter.encode("utf-8"))
        if tamano + longitud > 75:
            yield linea + "\r\n"
            linea, tamano = " ", 1
        linea += caracter
        tamano += longitud
    yield linea + "\r\n"


def fecha_utc(value):
    return value.astimezone(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")


def base_publica():
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    try:
        url = urlsplit(base)
        puerto = url.port
        if (
            url.scheme in {"http", "https"}
            and url.hostname
            and (puerto is None or 0 < puerto < 65536)
            and "\\" not in base
            and not (url.username or url.password or url.query or url.fragment)
            and not any(ord(c) < 33 or ord(c) == 127 for c in base)
        ):
            return base
    except ValueError:
        pass
    return None


def lineas_calendario(queryset, base, ahora):
    yield from [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GESICOM//Agenda de entregas//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Mis plazos · GESICOM",
    ]
    for plazo in queryset.order_by("fecha_limite", "pk").iterator(chunk_size=200):
        estado = (
            "Entregado"
            if plazo.entregado and plazo.a_tiempo
            else "Entregado fuera de plazo"
            if plazo.entregado
            else "Vencido sin entrega"
            if plazo.fecha_limite <= ahora
            else "Pendiente"
        )
        descripcion = f"Proyecto: {plazo.proyecto or 'Todos los proyectos'}\nEstado: {estado}"
        if plazo.descripcion:
            descripcion += "\n\n" + plazo.descripcion
        uid = uuid.uuid5(uuid.NAMESPACE_URL, f"{base or 'urn:gesicom:agenda'}/plazos/{plazo.pk}")
        yield "BEGIN:VEVENT"
        yield f"UID:{uid}@gesicom"
        yield "DTSTAMP:" + fecha_utc(ahora)
        yield "LAST-MODIFIED:" + fecha_utc(plazo.actualizado_en or plazo.creado_en)
        yield f"SEQUENCE:{plazo.revision}"
        yield "DTSTART:" + fecha_utc(plazo.fecha_limite)
        yield "SUMMARY:" + escapar_texto(plazo.titulo or "Plazo de reporte")
        yield "DESCRIPTION:" + escapar_texto(descripcion)
        yield "CATEGORIES:GESICOM," + escapar_texto(plazo.proyecto or "Reportes")
        yield "STATUS:CONFIRMED"
        yield "TRANSP:TRANSPARENT"
        if base:
            yield "URL:" + base + reverse("notificaciones:mis_plazos") + "?" + urlencode({"plazo": plazo.pk})
        yield "END:VEVENT"
    yield "END:VCALENDAR"


def respuesta_calendario(queryset, mes=""):
    base, ahora = base_publica(), timezone.now()

    def contenido():
        for linea in lineas_calendario(queryset, base, ahora):
            yield from plegar_linea(linea)

    nombre = "mis-plazos" + ("-" + mes if mes else "") + ".ics"
    response = StreamingHttpResponse(contenido(), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre}"'
    response["Cache-Control"] = "private, no-store"
    return response
