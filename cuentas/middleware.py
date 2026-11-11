from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from SENNOVA.middleware import client_ip

from .models import SesionUsuario
from .sesiones import CLAVE_VERSION, VERSION_SEGURIDAD


class SesionesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resumen = request.path_info == "/notificaciones/resumen/"

        def acceso_caducado():
            response = JsonResponse(
                {"error": "La sesión terminó. Ingresa de nuevo para continuar.", "login_url": reverse("login")},
                status=401,
            )
            response["Cache-Control"] = "private, no-store"
            return response

        if resumen and not request.user.is_authenticated:
            return acceso_caducado()
        if request.user.is_authenticated and request.session.session_key:
            request._gesicom_private = True
            if request.session.get(CLAVE_VERSION) != VERSION_SEGURIDAD:
                logout(request)
                messages.info(request, "La seguridad de las sesiones se actualizó. Ingresa de nuevo para continuar.")
                return acceso_caducado() if resumen else redirect("login")
            ahora = timezone.now()
            try:
                sesion, _ = SesionUsuario.objects.get_or_create(
                    sesion_id=request.session.session_key,
                    defaults={
                        "usuario": request.user,
                        "direccion_ip": client_ip(request),
                        "agente": request.META.get("HTTP_USER_AGENT", "")[:200],
                    },
                )
                if settings.SESSION_IDLE_TIMEOUT and ahora - sesion.ultimo_uso > timedelta(
                    seconds=settings.SESSION_IDLE_TIMEOUT
                ):
                    logout(request)
                    messages.info(request, "Tu sesión terminó por inactividad. Ingresa de nuevo para continuar.")
                    return acceso_caducado() if resumen else redirect("login")
                if not resumen and ahora - sesion.ultimo_uso >= timedelta(seconds=60):
                    SesionUsuario.objects.filter(pk=sesion.pk).update(ultimo_uso=ahora, direccion_ip=client_ip(request))
            except DatabaseError:
                return JsonResponse(
                    {"error": "No se pudo verificar la sesión. Intenta de nuevo más tarde."}, status=503
                )
        return self.get_response(request)
