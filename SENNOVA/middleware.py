"""Límites compartidos por identidad e IP, y trazabilidad sin cuerpos de petición."""

import hashlib
import ipaddress
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.http import JsonResponse

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
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

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
                return JsonResponse(
                    {"error": "El servicio de acceso está temporalmente ocupado. Intenta más tarde."}, status=503
                )
            if attempts > limit:
                response = JsonResponse(
                    {"error": "Demasiados intentos. Espera unos minutos antes de volver a intentarlo."}, status=429
                )
                response["Retry-After"] = str(window - int(time.time()) % window)
                return response
        return None


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        if (
            request.method == "POST"
            and match
            and (
                match.namespace in {"admin_personalizado", "notificaciones"}
                or match.url_name in {"verificar_pin", "restablecer_password", "set_aprobada"}
            )
        ):
            from cuentas.models import RegistroSeguridad

            try:
                RegistroSeguridad.objects.create(
                    actor=request.user if request.user.is_authenticated else None,
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
        return response
