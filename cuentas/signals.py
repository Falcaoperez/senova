from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from SENNOVA.middleware import client_ip

from .models import SesionUsuario
from .sesiones import CLAVE_VERSION, VERSION_SEGURIDAD


@receiver(user_logged_in, dispatch_uid="cuentas.registrar_sesion_autenticada")
def registrar_login(sender, request, user, **kwargs):
    if request:
        # login() vacía la sesión al cambiar de usuario. Materializa la nueva
        # antes de registrar su clave y la versión de seguridad.
        if not request.session.session_key:
            request.session.create()
        request.session[CLAVE_VERSION] = VERSION_SEGURIDAD
        SesionUsuario.objects.update_or_create(
            sesion_id=request.session.session_key,
            defaults={
                "usuario": user,
                "ultimo_uso": timezone.now(),
                "direccion_ip": client_ip(request),
                "agente": request.META.get("HTTP_USER_AGENT", "")[:200],
            },
        )
