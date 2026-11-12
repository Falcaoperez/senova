from importlib import import_module

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .forms import ConfirmarPasswordForm
from .models import SesionUsuario
from .sesiones import cerrar_sesiones


def _contexto(request, error=None):
    registros = SesionUsuario.objects.filter(
        usuario=request.user, sesion__expire_date__gt=timezone.now()
    ).select_related("sesion")
    pagina = Paginator(registros, 20).get_page(request.GET.get("page"))
    for sesion in pagina:
        sesion.es_actual = sesion.sesion_id == request.session.session_key
    return {"sesiones": pagina, "error_seguridad": error, "inactividad_minutos": settings.SESSION_IDLE_TIMEOUT // 60}


@login_required
def centro_seguridad(request):
    return render(request, "cuentas/seguridad.html", _contexto(request))


@login_required
@require_POST
@sensitive_post_parameters()
def revocar_sesion(request, pk):
    sesion = get_object_or_404(SesionUsuario, pk=pk, usuario=request.user)
    form = ConfirmarPasswordForm(request.POST, usuario=request.user)
    if not form.is_valid():
        return render(
            request,
            "cuentas/seguridad.html",
            _contexto(request, "Confirma tu contraseña actual para cerrar una sesión."),
            status=400,
        )
    if sesion.sesion_id == request.session.session_key:
        logout(request)
        return redirect("login")
    store = import_module(settings.SESSION_ENGINE).SessionStore
    store(session_key=sesion.sesion_id).delete()
    messages.success(request, "La sesión seleccionada se cerró correctamente.")
    return redirect("centro_seguridad")


@login_required
@require_POST
@sensitive_post_parameters()
def cerrar_otras_sesiones(request):
    form = ConfirmarPasswordForm(request.POST, usuario=request.user)
    if not form.is_valid():
        return render(
            request,
            "cuentas/seguridad.html",
            _contexto(request, "Confirma tu contraseña actual para cerrar las otras sesiones."),
            status=400,
        )
    total = cerrar_sesiones(request.user, conservar=request.session.session_key)
    messages.success(request, f"Se cerraron {total} sesiones. Tu sesión actual continúa abierta.")
    return redirect("centro_seguridad")
