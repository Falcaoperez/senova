"""Límites compartidos por identidad e IP, y trazabilidad sin cuerpos de petición."""

import hashlib
import ipaddress
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def client_ip(request):
    remote = request.META.get("REMOTE_ADDR", "")
    if remote in settings.TRUSTED_PROXY_IPS:
        candidate = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    try:
        return str(ipaddress.ip_address(remote))
    except ValueError:
        return "127.0.0.1"


class RateLimitMiddleware:
    RULES = {
        "login": (settings.LOGIN_IP_LIMIT, 600, 10),
        "login_root": (settings.LOGIN_IP_LIMIT, 600, 10),
        "register": (settings.REGISTRATION_IP_LIMIT, 3600, 5),
        "olvide_password": (20, 900, 3),
        "verificar_pin": (40, 600, 10),
        "restablecer_password": (30, 600, 10),
        "editar_perfil": (100, 600, 10),
        "revocar_sesion": (100, 600, 10),
        "cerrar_otras_sesiones": (100, 600, 10),
        "gestionar_usuarios": (1000, 600, 40),
        "detalle_usuario": (1000, 600, 40),
        "activar_desactivar": (1000, 600, 40),
        "asignar_grupo": (1000, 600, 40),
        "evidencia": (1000, 600, 40),
        "corregir_evidencia": (1000, 600, 40),
        "set_aprobada": (2000, 600, 200),
        "actualizar_observaciones": (2000, 600, 100),
        "recordar_pendientes": (1000, 600, 20),
        "archivar_plazo": (1000, 600, 20),
        "permisos": (1000, 600, 20),
        "auth_group_change": (1000, 600, 20),
        "auth_group_add": (1000, 600, 20),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def _error(request, message, status):
        name = request.resolver_match.url_name
        if name in {
            "olvide_password",
            "verificar_pin",
            "restablecer_password",
        } or "application/json" in request.headers.get("Accept", ""):
            return JsonResponse({"error": message}, status=status)
        route = (
            "evidencias_list"
            if name in {"evidencia", "corregir_evidencia", "set_aprobada", "actualizar_observaciones"}
            else "admin_personalizado:gestionar_usuarios"
            if request.resolver_match.namespace == "admin_personalizado"
            else "admin:auth_group_changelist"
            if name in {"auth_group_change", "auth_group_add"}
            else "notificaciones:plazos_admin"
            if request.resolver_match.namespace == "notificaciones"
            else "centro_seguridad"
            if name in {"revocar_sesion", "cerrar_otras_sesiones"}
            else "editar_perfil"
            if name == "editar_perfil"
            else "register"
            if name == "register"
            else "login"
        )
        # Sin procesadores de contexto: esta pantalla también funciona si Redis falla.
        html = render_to_string(
            "cuentas/error_acceso.html", {"mensaje": message, "estado": status, "volver": reverse(route)}
        )
        return HttpResponse(html, status=status)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST" or not settings.RATE_LIMITS_ENABLED:
            return None
        name = request.resolver_match.url_name
        if name == "login_root":
            name = "login"
        rule = self.RULES.get(name)
        if not rule:
            return None
        ip_limit, window, identity_limit = rule
        identity = (request.POST.get("email") or request.POST.get("username") or "").strip().casefold()
        if name == "login" and identity:
            from django.contrib.auth import get_user_model

            usuarios = get_user_model().objects.only("pk")
            cuenta = usuarios.filter(username__iexact=identity).first()
            if cuenta is None and "@" in identity:
                cuenta = usuarios.filter(email__iexact=identity).first()
            if cuenta:
                identity = f"usuario:{cuenta.pk}"
        elif request.user.is_authenticated:
            identity = f"usuario:{request.user.pk}"
        identities = [(f"ip:{client_ip(request)}", ip_limit)]
        if identity:
            identities.append((f"account:{identity}", identity_limit))
        # Contadores de ventana fija: add/incr son atómicos en Redis.
        bucket = int(time.time()) // window
        for subject, limit in identities:
            key = "limite:" + hashlib.sha256(f"{name}:{subject}:{bucket}".encode()).hexdigest()
            try:
                if cache.add(key, 1, timeout=window + 1):
                    attempts = 1
                else:
                    attempts = cache.incr(key)
            except Exception:
                return self._error(request, "El servicio de acceso está temporalmente ocupado. Intenta más tarde.", 503)
            if attempts > limit:
                response = self._error(
                    request, "Demasiados intentos. Espera unos minutos antes de volver a intentarlo.", 429
                )
                response["Retry-After"] = str(window - int(time.time()) % window)
                return response
        return None


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        anterior = request.user if request.user.is_authenticated else None
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        if (
            request.method == "POST"
            and match
            and (
                match.namespace in {"admin_personalizado", "notificaciones"}
                or match.url_name
                in {
                    "login",
                    "login_root",
                    "logout",
                    "olvide_password",
                    "verificar_pin",
                    "restablecer_password",
                    "set_aprobada",
                    "editar_perfil",
                    "revocar_sesion",
                    "cerrar_otras_sesiones",
                }
            )
        ):
            from cuentas.models import RegistroSeguridad

            try:
                RegistroSeguridad.objects.create(
                    actor=request.user if request.user.is_authenticated else anterior,
                    accion=f"{match.view_name}:{response.status_code}"[:80],
                    ruta=request.path[:255],
                    direccion_ip=client_ip(request),
                )
            except DatabaseError:
                logger.error("No se pudo guardar un evento de auditoría.")
        return response


# Alias para configuraciones anteriores, sin mantener un segundo limitador.
MiddlewareLimiteVelocidad = RateLimitMiddleware


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "frame-src 'self'; frame-ancestors 'self'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        response["Referrer-Policy"] = "same-origin"
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        user = getattr(request, "user", None)
        private = getattr(request, "_gesicom_private", False) or (user and user.is_authenticated)
        recovery = request.path.startswith(("/password-reset/", "/reset/", "/api/"))
        if (private or recovery) and "no-store" not in response.get("Cache-Control", ""):
            response["Cache-Control"] = "private, no-store"
            response["Pragma"] = "no-cache"
        return response
