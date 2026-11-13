"""Recuperación en tres pasos: solicitar PIN, verificarlo y elegir contraseña."""

import re

from django.conf import settings
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .correos import encolar_aviso_cambio, encolar_pin, invalidar_recuperaciones
from .models import PasswordResetToken
from .presentacion import respuesta_recuperacion
from .sesiones import cerrar_sesiones

User = get_user_model()
SESSION_PROOF = "recuperacion_verificada"


@require_http_methods(["GET"])
@never_cache
def password_reset_form(request):
    return render(request, "Registro/password_reset_form.html")


@require_http_methods(["POST"])
@sensitive_post_parameters()
@never_cache
def olvide_password(request):
    email = request.POST.get("email", "").strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return respuesta_recuperacion(
            request,
            {"error": "Ingresa un correo válido."},
            plantilla="Registro/password_reset_form.html",
            contexto={"email": email[:254]},
            status=400,
        )
    request.session.pop(SESSION_PROOF, None)
    request.session["recuperacion_correo"] = email
    request.session["recuperacion_expira"] = (
        timezone.now() + timezone.timedelta(minutes=settings.PASSWORD_RESET_PIN_MINUTES)
    ).isoformat()
    users = list(User.objects.filter(email__iexact=email, is_active=True)[:2])
    if len(users) == 1:
        user = users[0]
        with transaction.atomic():
            User.objects.select_for_update().get(pk=user.pk)
            invalidar_recuperaciones(user)
            solicitud = PasswordResetToken.crear_para_usuario(user)
            encolar_pin(solicitud)
    else:
        # Igual que el backend de autenticación de Django: trabajo de hash también
        # para cuentas ausentes, sin SMTP ni consultas sobre la existencia en la respuesta.
        make_password("solicitud-de-recuperacion-sin-cuenta")
    return respuesta_recuperacion(
        request,
        {"mensaje": "Si el correo tiene una cuenta activa, recibirás un PIN de seis dígitos."},
        plantilla="Registro/password_reset_form.html",
        destino="password_reset_update",
    )


def _contexto_pin(request, email=None):
    return {
        "email": (
            email
            if email is not None
            else request.session.get("recuperacion_correo", request.GET.get("email", "").strip())
        )[:254],
        "expires": request.session.get("recuperacion_expira", ""),
        "minutos": settings.PASSWORD_RESET_PIN_MINUTES,
    }


@require_http_methods(["GET"])
@never_cache
def password_reset_update(request):
    if _solicitud_verificada(request):
        return redirect("password_reset_new")
    return render(
        request,
        "Registro/password_reset_update.html",
        _contexto_pin(request),
    )


@require_http_methods(["POST"])
@sensitive_post_parameters()
@never_cache
def verificar_pin(request):
    email = request.POST.get("email", "").strip().lower()
    codigo = request.POST.get("codigo", "").strip()
    error = None
    if not re.fullmatch(r"\d{6}", codigo, flags=re.ASCII):
        return respuesta_recuperacion(
            request,
            {"error": "Ingresa un PIN de seis dígitos."},
            plantilla="Registro/password_reset_update.html",
            contexto=_contexto_pin(request, email),
            status=400,
        )
    with transaction.atomic():
        solicitud = (
            PasswordResetToken.objects.select_for_update()
            .select_related("usuario")
            .filter(usuario__email__iexact=email, usuario__is_active=True, utilizado=False)
            .order_by("-creado_en")
            .first()
        )
        if not solicitud or not solicitud.es_valido() or solicitud.verificado_en is not None:
            error = "El PIN no es válido o ha caducado. Solicita uno nuevo."
        elif not check_password(codigo, solicitud.token):
            solicitud.intentos += 1
            solicitud.save(update_fields=["intentos"])
            error = "El PIN no es válido o ha caducado."
        else:
            solicitud.verificado_en = timezone.now()
            solicitud.save(update_fields=["verificado_en"])
            request.session.cycle_key()
            request.session[SESSION_PROOF] = solicitud.pk
            request.session["recuperacion_correo"] = email
    return respuesta_recuperacion(
        request,
        {"error": error} if error else {"mensaje": "PIN verificado. Ya puedes crear una nueva contraseña."},
        plantilla="Registro/password_reset_update.html",
        contexto=_contexto_pin(request, email),
        destino="password_reset_new",
        status=400 if error else 200,
    )


def _solicitud_verificada(request, lock=False):
    pk = request.session.get(SESSION_PROOF)
    if not isinstance(pk, int):
        return None
    queryset = PasswordResetToken.objects.select_for_update() if lock else PasswordResetToken.objects
    solicitud = queryset.select_related("usuario").filter(pk=pk, usuario__is_active=True).first()
    if not solicitud or not solicitud.es_valido() or solicitud.verificado_en is None:
        return None
    return solicitud


@require_http_methods(["GET"])
@never_cache
def password_reset_new(request):
    solicitud = _solicitud_verificada(request)
    if not solicitud:
        return redirect("password_reset")
    return render(request, "Registro/password_reset_new.html", {"correo_verificado": solicitud.usuario.email})


@require_http_methods(["POST"])
@sensitive_post_parameters()
@never_cache
def restablecer_password(request):
    password = request.POST.get("password", "")
    confirmation = request.POST.get("password_confirm", "")
    if not password or password != confirmation:
        return respuesta_recuperacion(
            request,
            {"error": "Las contraseñas deben coincidir."},
            plantilla="Registro/password_reset_new.html",
            status=400,
        )
    error, status, correo_verificado = None, 200, ""
    with transaction.atomic():
        solicitud = _solicitud_verificada(request, lock=True)
        if not solicitud:
            error, status = "Verifica primero el PIN de recuperación.", 403
        else:
            correo_verificado = solicitud.usuario.email
            try:
                validate_password(password, solicitud.usuario)
            except ValidationError as validacion:
                error, status = " ".join(validacion.messages), 400
            else:
                solicitud.usuario.set_password(password)
                solicitud.usuario.save(update_fields=["password"])
                invalidar_recuperaciones(solicitud.usuario)
                encolar_aviso_cambio(solicitud.usuario)
                cerrar_sesiones(solicitud.usuario)
                request.session.pop(SESSION_PROOF, None)
                request.session.pop("recuperacion_correo", None)
                request.session.pop("recuperacion_expira", None)
                logout(request)
    return respuesta_recuperacion(
        request,
        {"error": error} if error else {"mensaje": "Contraseña cambiada con éxito."},
        plantilla="Registro/password_reset_new.html",
        destino="password_reset_complete",
        contexto={"correo_verificado": correo_verificado},
        status=status,
    )
