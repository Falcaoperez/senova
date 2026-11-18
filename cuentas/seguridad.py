from datetime import timedelta
from importlib import import_module

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST, require_safe

from .forms import ConfirmarPasswordForm, FiltrosSesionesForm
from .models import SesionUsuario
from .sesiones import cerrar_sesiones


def _contexto(request, error=None):
    ahora = timezone.now()
    actual = request.session.session_key
    filtros = FiltrosSesionesForm(request.GET)
    valido = filtros.is_valid()
    registros = (
        SesionUsuario.objects.filter(usuario=request.user, sesion__expire_date__gt=ahora)
        .only("pk", "agente", "direccion_ip", "creada_en", "ultimo_uso")
        .annotate(
            es_actual=Case(When(sesion_id=actual, then=Value(True)), default=Value(False), output_field=BooleanField())
        )
        .order_by("-es_actual", "-ultimo_uso", "-pk")
    )
    if not valido:
        registros = registros.none()
    elif filtros.cleaned_data["estado"] == "actual":
        registros = registros.filter(sesion_id=actual)
    elif filtros.cleaned_data["estado"] == "otras":
        registros = registros.exclude(sesion_id=actual)
    pagina = Paginator(registros, 20).get_page(request.GET.get("page"))
    limite = ahora - timedelta(seconds=settings.SESSION_IDLE_TIMEOUT) if settings.SESSION_IDLE_TIMEOUT else None
    for sesion in pagina:
        sesion.es_inactiva = limite is not None and sesion.ultimo_uso < limite

    def enlace(numero):
        return reverse("centro_seguridad") + filtros.consulta_url(pagina=numero)

    return {
        "sesiones": pagina,
        "filtros_form": filtros,
        "error_seguridad": error,
        "inactividad_minutos": settings.SESSION_IDLE_TIMEOUT // 60,
        "url_actualizar": enlace(pagina.number) if valido else None,
        "url_anterior": enlace(pagina.previous_page_number()) if pagina.has_previous() else None,
        "url_siguiente": enlace(pagina.next_page_number()) if pagina.has_next() else None,
    }


@login_required
@require_safe
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
