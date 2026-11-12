"""Mismas vistas y permisos para la página completa y sus resultados interactivos."""

from django.shortcuts import render
from django.utils.cache import patch_vary_headers


def render_panel(request, template, context=None, **kwargs):
    fragmento = request.method == "GET" and request.headers.get("X-Workspace-Fragment") == "1"
    request._gesicom_fragmento = fragmento
    datos = {
        **(context or {}),
        "base_panel": "ui/base_fragmento.html" if fragmento else "base.html",
    }
    response = render(request, template, datos, **kwargs)
    patch_vary_headers(response, ("X-Workspace-Fragment",))
    if fragmento:
        response["X-Workspace-Fragment"] = "1"
    return response
