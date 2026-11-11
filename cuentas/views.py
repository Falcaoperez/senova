"""Recuperación en tres pasos: solicitar PIN, verificarlo y elegir contraseña."""

import re

from django.conf import settings
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .correos import encolar_aviso_cambio, encolar_pin, invalidar_recuperaciones
from .models import PasswordResetToken
from .sesiones import cerrar_sesiones

User = get_user_model()
SESSION_PROOF = "recuperacion_verificada"


@require_http_methods(["GET"])
def password_reset_form(request):
    return render(request, "Registro/password_reset_form.html")


@require_http_methods(["POST"])
@sensitive_post_parameters()
def olvide_password(request):
    email = request.POST.get("email", "").strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"error": "Ingresa un correo válido."}, status=400)
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
    return JsonResponse({"mensaje": "Si el correo tiene una cuenta activa, recibirás un PIN de seis dígitos."})


@require_http_methods(["GET"])
def password_reset_update(request):
    return render(
        request,
        "Registro/password_reset_update.html",
        {
            "email": request.session.get("recuperacion_correo", request.GET.get("email", "").strip()),
            "expires": request.session.get("recuperacion_expira", ""),
            "minutos": settings.PASSWORD_RESET_PIN_MINUTES,
        },
    )


@require_http_methods(["POST"])
@sensitive_post_parameters()
def verificar_pin(request):
    email = request.POST.get("email", "").strip().lower()
    codigo = request.POST.get("codigo", "").strip()
    if not re.fullmatch(r"\d{6}", codigo, flags=re.ASCII):
        return JsonResponse({"error": "Ingresa un PIN de seis dígitos."}, status=400)
    with transaction.atomic():
        solicitud = (
            PasswordResetToken.objects.select_for_update()
            .select_related("usuario")
            .filter(usuario__email__iexact=email, usuario__is_active=True, utilizado=False)
            .order_by("-creado_en")
            .first()
        )
        if not solicitud or not solicitud.es_valido() or solicitud.verificado_en is not None:
            return JsonResponse({"error": "El PIN no es válido o ha caducado. Solicita uno nuevo."}, status=400)
        if not check_password(codigo, solicitud.token):
            solicitud.intentos += 1
            solicitud.save(update_fields=["intentos"])
            return JsonResponse({"error": "El PIN no es válido o ha caducado."}, status=400)
        solicitud.verificado_en = timezone.now()
        solicitud.save(update_fields=["verificado_en"])
        request.session.cycle_key()
        request.session[SESSION_PROOF] = solicitud.pk
        request.session["recuperacion_correo"] = email
    return JsonResponse({"mensaje": "PIN verificado. Ya puedes crear una nueva contraseña."})


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
def password_reset_new(request):
    if not _solicitud_verificada(request):
        return redirect("password_reset")
    return render(request, "Registro/password_reset_new.html")


@require_http_methods(["POST"])
@sensitive_post_parameters()
def restablecer_password(request):
    password = request.POST.get("password", "")
    confirmation = request.POST.get("password_confirm", "")
    if not password or password != confirmation:
        return JsonResponse({"error": "Las contraseñas deben coincidir."}, status=400)
    with transaction.atomic():
        solicitud = _solicitud_verificada(request, lock=True)
        if not solicitud:
            return JsonResponse({"error": "Verifica primero el PIN de recuperación."}, status=403)
        try:
            validate_password(password, solicitud.usuario)
        except ValidationError as error:
            return JsonResponse({"error": " ".join(error.messages)}, status=400)
        solicitud.usuario.set_password(password)
        solicitud.usuario.save(update_fields=["password"])
        invalidar_recuperaciones(solicitud.usuario)
        encolar_aviso_cambio(solicitud.usuario)
        cerrar_sesiones(solicitud.usuario)
        request.session.pop(SESSION_PROOF, None)
        request.session.pop("recuperacion_correo", None)
        request.session.pop("recuperacion_expira", None)
        logout(request)
    return JsonResponse({"mensaje": "Contraseña cambiada con éxito."})
