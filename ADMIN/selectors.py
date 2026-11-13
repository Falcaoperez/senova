"""Consultas acotadas del centro de operaciones, sin cargar directorios completos."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone

from cuentas.models import CorreoSeguridad, RegistroSeguridad
from Gesicom.models import Envio
from notificaciones.models import CorreoPendiente, PlazoReporte

from .auditoria import IDENTIDAD_ACTOR, etiqueta_accion


def centro_operaciones(periodo):
    dias = int(periodo) if str(periodo) in {"7", "30", "90"} else 30
    hoy = timezone.localdate()
    inicio = hoy - timedelta(days=dias - 1)
    anteriores = inicio - timedelta(days=dias)
    envios = Envio.objects.all()
    resumen = envios.aggregate(
        total=Count("pk"),
        pendientes=Count("pk", filter=Q(aprobada=False, rechazada=False)),
        aprobadas=Count("pk", filter=Q(aprobada=True)),
        rechazadas=Count("pk", filter=Q(rechazada=True)),
        recibidas=Count("pk", filter=Q(fecha_envio__range=(inicio, hoy))),
        anteriores=Count("pk", filter=Q(fecha_envio__gte=anteriores, fecha_envio__lt=inicio)),
    )
    comunidad = User.objects.aggregate(total=Count("pk"), activos=Count("pk", filter=Q(is_active=True)))
    serie = dict(
        envios.filter(fecha_envio__range=(inicio, hoy))
        .values("fecha_envio")
        .annotate(total=Count("pk"))
        .order_by()
        .values_list("fecha_envio", "total")
    )
    fechas = [inicio + timedelta(days=offset) for offset in range(dias)]
    proyectos = list(envios.values("proyecto").annotate(total=Count("pk")).order_by("-total", "proyecto"))
    for proyecto in proyectos:
        proyecto["porcentaje"] = round(proyecto["total"] * 100 / resumen["total"]) if resumen["total"] else 0
    ahora = timezone.now()
    proximos = PlazoReporte.objects.filter(activo=True, fecha_limite__gte=ahora)
    estados = {}
    for modelo in (CorreoSeguridad, CorreoPendiente):
        for fila in modelo.objects.values("estado").annotate(total=Count("pk")):
            estados[fila["estado"]] = estados.get(fila["estado"], 0) + fila["total"]
    actividad = []
    recientes = RegistroSeguridad.objects.select_related("actor").only("accion", "creado_en", *IDENTIDAD_ACTOR)[:6]
    for registro in recientes:
        actividad.append(
            {
                "etiqueta": etiqueta_accion(registro.accion),
                "actor": (registro.actor.get_full_name() or registro.actor.username) if registro.actor else "Sistema",
                "fecha": registro.creado_en,
            }
        )
    return {
        "periodo": str(dias),
        "inicio_periodo": inicio,
        "fin_periodo": hoy,
        "resumen": resumen,
        "variacion": resumen["recibidas"] - resumen["anteriores"],
        "total_usuarios": comunidad["total"],
        "usuarios_activos": comunidad["activos"],
        "proximos_plazos": proximos.count(),
        "plazos_proximos": proximos[:4],
        "evidencias_pendientes": envios.filter(aprobada=False, rechazada=False).select_related("usuario")[:5],
        "usuarios_recientes": User.objects.only("id", "username", "first_name", "last_name", "is_active")
        .order_by("-date_joined", "-pk")
        .prefetch_related("groups")[:5],
        "actividad_reciente": actividad,
        "proyectos": proyectos,
        "actividad_grafico": {
            "labels": [fecha.strftime("%d/%m") for fecha in fechas],
            "valores": [serie.get(fecha, 0) for fecha in fechas],
        },
        "actividad_tabla": [{"fecha": fecha, "total": serie.get(fecha, 0)} for fecha in fechas],
        "correo_remitente": settings.DEFAULT_FROM_EMAIL,
        "correo_pruebas": settings.EMAIL_HOST in {"localhost", "127.0.0.1", "mailpit", "senova-mailpit"},
        "correo_credencial": bool(settings.EMAIL_HOST_PASSWORD or settings.EMAIL_OAUTH2_ACCESS_TOKEN),
        "correo_trabajador": bool(cache.get("notificaciones:trabajador")),
        "correos_pendientes": estados.get("pendiente", 0) + estados.get("procesando", 0),
        "correos_errores": estados.get("error", 0),
    }
