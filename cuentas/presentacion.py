"""Respuestas HTML progresivas sin cambiar el JSON de las rutas históricas."""

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.cache import patch_vary_headers


def prefiere_html(request):
    # Sin Accept explícito se conserva la respuesta JSON de los clientes anteriores.
    return (
        "text/html" in request.headers.get("Accept", "").lower()
        and request.get_preferred_type(["application/json", "text/html"]) == "text/html"
    )


def respuesta_recuperacion(request, datos, *, plantilla, destino=None, contexto=None, status=200):
    if not prefiere_html(request):
        response = JsonResponse(datos, status=status)
    elif destino and status < 400:
        response = redirect(destino)
    else:
        response = render(
            request,
            plantilla,
            {**(contexto or {}), "error_recuperacion": datos.get("error", "")},
            status=status,
        )
    patch_vary_headers(response, ["Accept"])
    return response
