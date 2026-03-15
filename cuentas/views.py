from django.http import JsonResponse
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt
from .models import PasswordResetToken
import datetime
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


@require_http_methods(["POST"])
def olvide_password(request):
    email = request.POST.get("email", "").strip()
    if not email:
        return JsonResponse({"error": "Correo requerido"}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({"error": "Si el correo existe, recibirás un mensaje"}, status=200)
    # Crear un token en la tabla para uso vía API
    try:
        token_obj = PasswordResetToken.create_for_user(user)
    except Exception as e:
        return JsonResponse({"error": f"Error creando token: {str(e)}"}, status=500)

    # Enviar correo con el código/token (en producción construir link seguro)
    try:
        send_mail(
            "Restablecer contraseña",
            f"Usa este código para restablecer tu contraseña (válido por 1 hora):\n{token_obj.token}",
            "no-reply@gesicom.com",
            [email],
            fail_silently=False,
        )
    except Exception as e:
        return JsonResponse({"error": f"Error al enviar correo: {str(e)}"}, status=500)

    return JsonResponse({"mensaje": "Código enviado al correo"}, status=200)



@require_http_methods(["POST"])
def restablecer_password(request):
    email = request.POST.get('email', '').strip()
    codigo = request.POST.get('codigo', '').strip()
    password = request.POST.get('password', '')

    if not (email and codigo and password):
        return JsonResponse({'error': 'Faltan parámetros'}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({'error': 'Usuario no encontrado'}, status=404)

    token_obj = PasswordResetToken.objects.filter(user=user, token=codigo).first()
    if not token_obj:
        logger.warning(f"Código no existe en BD para {email}: codigo={codigo[:10]}...")
        return JsonResponse({'error': 'Código inválido o expirado'}, status=400)
    
    logger.info(f"Token encontrado para {email}: used={token_obj.used}, expires={token_obj.expires_at}, now={timezone.now()}")
    
    if token_obj.used:
        logger.warning(f"Código ya fue usado para {email}")
        return JsonResponse({'error': 'Código ya fue utilizado'}, status=400)
    
    if timezone.now() >= token_obj.expires_at:
        logger.warning(f"Código expirado para {email}: expires={token_obj.expires_at}, now={timezone.now()}")
        return JsonResponse({'error': 'Código expirado'}, status=400)

    try:
        user.set_password(password)
        user.save()
        token_obj.used = True
        token_obj.save()
        logger.info(f"Contraseña actualizada exitosamente para {email}")
    except Exception as e:
        logger.error(f"Error actualizando contraseña para {email}: {str(e)}")
        return JsonResponse({'error': f'Error actualizando contraseña: {str(e)}'}, status=500)

    return JsonResponse({'mensaje': 'Contraseña cambiada con éxito'}, status=200)


@require_http_methods(["GET"])
def csrf_token_view(request):
    token = get_token(request)
    return JsonResponse({'csrfToken': token})


@require_http_methods(["GET"])
def debug_tokens(request):
    """Endpoint de debug: muestra tokens activos (solo si DEBUG=True)"""
    from django.conf import settings
    if not settings.DEBUG:
        return JsonResponse({'error': 'Endpoint no disponible'}, status=403)
    
    email = request.GET.get('email', '').strip()
    if not email:
        return JsonResponse({'error': 'Parámetro email requerido'}, status=400)
    
    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({'error': 'Usuario no encontrado'}, status=404)
    
    tokens = PasswordResetToken.objects.filter(user=user).order_by('-created_at')
    data = {
        'email': email,
        'tokens': [
            {
                'token': t.token,
                'created': str(t.created_at),
                'expires': str(t.expires_at),
                'valid': t.is_valid(),
                'used': t.used,
            }
            for t in tokens
        ]
    }
    return JsonResponse(data)

