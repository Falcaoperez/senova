"""Resumen privado reutilizable durante una sola petición, sin caché entre cuentas."""

from .models import Notificacion


def resumen_de_peticion(request, *, recientes=False):
    usuario = request.user
    if not usuario.is_authenticated or not usuario.is_active:
        return {"pendientes": 0, "recientes": []}
    resumen = getattr(request, "_gesicom_resumen_avisos", None)
    if resumen is None or resumen["usuario"] != usuario.pk:
        resumen = {
            "usuario": usuario.pk,
            "pendientes": Notificacion.objects.filter(usuario=usuario, leida_en__isnull=True).count(),
        }
        request._gesicom_resumen_avisos = resumen
    if recientes and "recientes" not in resumen:
        resumen["recientes"] = list(
            Notificacion.objects.filter(usuario=usuario).only("titulo", "creada_en", "leida_en")[:4]
        )
    return resumen
