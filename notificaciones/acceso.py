"""Destinos actuales y autorización de avisos antes de abrirlos o enviarlos."""

from urllib.parse import urlencode, urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.urls import reverse

from Gesicom.selectors import _visible_envios
from Gesicom.utils import is_admin_or_group

from .models import Notificacion
from .selectors import destinatarios, plazos_para_usuario


def enlace_seguro(enlace):
    enlace = (enlace or "").strip()
    if not enlace or "\\" in enlace or any(ord(c) < 32 or ord(c) == 127 for c in enlace):
        return None
    try:
        parsed = urlsplit(enlace)
    except ValueError:
        return None
    if not parsed.scheme and not parsed.netloc and enlace.startswith("/") and not enlace.startswith("//"):
        return enlace
    if parsed.username or parsed.password:
        return None
    try:
        URLValidator(schemes=["http", "https"])(enlace)
        return enlace
    except ValidationError:
        return None


def destino_notificacion(aviso):
    usuario = aviso.usuario
    bandeja = reverse("notificaciones:bandeja")
    if aviso.tipo == Notificacion.Tipo.EVIDENCIA:
        if not aviso.envio_id:
            return None, "Esta evidencia ya no está disponible."
        nativo = reverse("admin:Gesicom_envio_change", args=[aviso.envio_id])
        puede_admin = usuario.is_staff and usuario.has_perm("Gesicom.view_envio")
        puede_admin = puede_admin or (usuario.is_staff and usuario.has_perm("Gesicom.change_envio"))
        if aviso.enlace == nativo and puede_admin:
            return nativo, ""
        if _visible_envios(usuario).filter(pk=aviso.envio_id).exists():
            return reverse("ver_evidencia", args=[aviso.envio_id]), ""
        if puede_admin:
            return nativo, ""
        return None, "Ya no tienes acceso a la evidencia de este aviso."
    if aviso.plazo_id:
        if not aviso.plazo.activo:
            return None, "El plazo de este aviso fue archivado."
        if is_admin_or_group(usuario, []):
            return reverse("notificaciones:seguimiento_plazo", args=[aviso.plazo_id]), ""
        if not plazos_para_usuario(usuario, pendientes=False).filter(pk=aviso.plazo_id).exists():
            return None, "El plazo ya no está asignado a tu cuenta."
        return reverse("notificaciones:mis_plazos") + "?" + urlencode({"plazo": aviso.plazo_id}), ""
    if aviso.novedad_id and not destinatarios(aviso.novedad.grupos).filter(pk=usuario.pk).exists():
        return None, "La publicación ya no está dirigida a tu cuenta."
    return enlace_seguro(aviso.enlace) or bandeja, ""


def motivo_cancelacion(aviso):
    if not aviso.usuario.is_active or not aviso.usuario.email:
        return "Cuenta inactiva o sin dirección de correo."
    _, motivo = destino_notificacion(aviso)
    if motivo:
        return motivo
    if aviso.plazo_id:
        if aviso.plazo.version != aviso.version_plazo:
            return "El plazo se actualizó después de preparar este correo."
        if aviso.tipo in {Notificacion.Tipo.RECORDATORIO, Notificacion.Tipo.VENCIMIENTO, Notificacion.Tipo.SEGUIMIENTO}:
            if aviso.usuario.envios.filter(plazo_id=aviso.plazo_id).exists():
                return "Ya existe una entrega asociada a este plazo."
    return ""
