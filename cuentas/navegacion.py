"""Destinos locales para volver a la aplicación después del acceso."""

from urllib.parse import unquote, urlencode, urlsplit

from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

ACCESOS = {"login", "login_root", "logout", "admin:login", "admin:logout"}


def destino_de_acceso(valor):
    if (
        not valor
        or len(valor) > 2048
        or not valor.startswith("/")
        or "\\" in valor
        or any(ord(c) < 32 or ord(c) == 127 for c in valor)
        or not url_has_allowed_host_and_scheme(valor, allowed_hosts=set())
    ):
        return ""
    try:
        ruta = unquote(urlsplit(valor).path)
        if (
            ruta.startswith("//")
            or "\\" in ruta
            or any(parte in {".", ".."} for parte in ruta.split("/"))
            or any(ord(c) < 32 or ord(c) == 127 for c in ruta)
        ):
            return ""
        vista = resolve(ruta)
    except (ValueError, Resolver404):
        return ""
    return "" if vista.view_name in ACCESOS else valor


def ingreso_para_lectura(request):
    destino = destino_de_acceso(request.get_full_path()) if request.method in {"GET", "HEAD"} else ""
    return reverse("login") + ("?" + urlencode({"next": destino}) if destino else "")
