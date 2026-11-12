"""Acceso a adjuntos privados y metadatos para presentar su disponibilidad."""

from pathlib import Path

from .adjuntos import FORMATOS, vista_adjunto
from .models import Envio
from .selectors import _visible_envios


def archivos_visibles(usuario):
    if not usuario.is_authenticated or not usuario.is_active:
        return Envio.objects.none()
    if usuario.is_staff and (usuario.has_perm("Gesicom.view_envio") or usuario.has_perm("Gesicom.change_envio")):
        return Envio.objects.all()
    return _visible_envios(usuario)


def informacion_adjunto(envio):
    datos = {
        "archivo_disponible": False,
        "archivo_nombre": "",
        "archivo_tamano": None,
        "archivo_formato": "Archivo",
        "preview_kind": "other",
    }
    if not envio.archivo_evidencia:
        return datos
    nombre = Path(envio.archivo_evidencia.name).name
    datos.update(archivo_nombre=nombre, archivo_formato=FORMATOS.get(Path(nombre).suffix.lower(), ("Archivo", None))[0])
    try:
        with envio.archivo_evidencia.open("rb") as archivo:
            tipo, _ = vista_adjunto(archivo, nombre)
            datos.update(archivo_disponible=True, archivo_tamano=archivo.file.size, preview_kind=tipo)
    except OSError:
        pass
    return datos
