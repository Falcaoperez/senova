from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
import re
from django.contrib.auth.models import User, Group
import logging
import traceback
from django.db import transaction, IntegrityError

logger = logging.getLogger(__name__)


RUTAS_ROLES = {
    'instructor': 'role_instructor',
    'investigador': 'role_investigador',
    'dinamizador': 'role_dinamizador',
    'coordinador': 'role_coordinador',
    'usuario': 'usuario',
}


def _validar_contraseña(contraseña1, contraseña2=None):
	errores = []

	if not contraseña1:
		errores.append('La contraseña es obligatoria.')
		return errores

	if contraseña2 and contraseña1 != contraseña2:
		errores.append('Las contraseñas no coinciden.')
		return errores

	if len(contraseña1) != 8:
		errores.append('La contraseña debe tener exactamente 8 caracteres.')

	tiene_mayuscula = re.search(r'[A-Z]', contraseña1) is not None
	tiene_digito = re.search(r'\d', contraseña1) is not None
	tiene_especial = re.search(r'[!@#$%^&*(),.?":{}|<>]', contraseña1) is not None

	if not tiene_mayuscula:
		errores.append('Debe contener al menos una letra mayúscula.')

	if not (tiene_digito or tiene_especial):
		errores.append('Debe contener al menos un número o carácter especial.')

	return errores


def login_view(request):
	rol = request.GET.get('role') or request.POST.get('role') or ''
	if rol not in RUTAS_ROLES:
		rol = ''

	mensaje_exito = None
	if request.method == 'GET' and request.GET.get('created'):
		mensaje_exito = 'Cuenta creada correctamente. Por favor inicia sesión.'

	if request.method == 'POST':
		entrada_usuario = (request.POST.get('username', '') or '').strip()
		contraseña = request.POST.get('password', '')
		recordar = request.POST.get('remember')

		usuario_para_auth = entrada_usuario
		if '@' in entrada_usuario and not User.objects.filter(username=entrada_usuario).exists():
			try:
				u = User.objects.get(email__iexact=entrada_usuario)
				usuario_para_auth = u.username
			except User.DoesNotExist:
				pass

		usuario = authenticate(request, username=usuario_para_auth, password=contraseña)
		if usuario is not None:
			login(request, usuario)
			if recordar:
				request.session.set_expiry(60 * 60 * 24 * 14)
			else:
				request.session.set_expiry(0)
			
			grupos_usuario = set(usuario.groups.values_list('name', flat=True))

			# 1. Si es Superusuario o está en el grupo 'administrador' -> Panel de Admin
			if usuario.is_superuser or 'administrador' in grupos_usuario:
				return redirect('admin_personalizado:dashboard')

			# 2. Si está en el grupo 'instructor' -> Panel de Instructor
			if 'instructor' in grupos_usuario:
				return redirect('role_instructor')

			# 3. Si el rol viene por URL/POST y coincide con un grupo del usuario -> Redirigir a ese rol
			if rol and rol in RUTAS_ROLES and rol in grupos_usuario:
				return redirect(RUTAS_ROLES[rol])

			# 4. Redirección por defecto basada en grupos prioritarios
			if 'investigador' in grupos_usuario: return redirect('role_investigador')
			if 'dinamizador' in grupos_usuario: return redirect('role_dinamizador')
			if 'coordinador' in grupos_usuario: return redirect('role_coordinador')
			
			destino = 'usuario' if 'usuario' in grupos_usuario else 'home'
			return redirect(destino)

		return render(request, 'login.html', {
			'error': 'Usuario o contraseña incorrectos',
			'role': rol,
			'username': entrada_usuario,
		})

	context = {'role': rol}
	if mensaje_exito:
		context['success'] = mensaje_exito
	return render(request, 'login.html', context)


def register_view(request):
	rol = request.GET.get('role') or request.POST.get('role') or ''
	if request.method == 'POST':
		try:
			logger.debug('register_view POST data: %s', dict(request.POST))
		except Exception:
			logger.exception('No se pudo serializar request.POST')
		nombre_usuario = (request.POST.get('username', '') or '').strip()
		correo = (request.POST.get('email', '') or '').strip().lower()
		contraseña1 = request.POST.get('password1', '')
		contraseña2 = request.POST.get('password2', '')

		errores = []
		if not nombre_usuario:
			errores.append('El usuario es obligatorio.')
		if not correo:
			errores.append('El correo es obligatorio.')

		errores.extend(_validar_contraseña(contraseña1, contraseña2))

		if User.objects.filter(username=nombre_usuario).exists():
			errores.append('Ese usuario ya existe. Prueba con otro.')

		if User.objects.filter(email=correo).exists():
			errores.append('Ese correo ya está registrado.')

		if errores:
			return render(request, 'register.html', {
				'errores': errores,
				'rol': rol,
				'nombre_usuario': nombre_usuario,
				'correo': correo,
			})

		try:
			with transaction.atomic():
				usuario = User.objects.create_user(username=nombre_usuario, email=correo, password=contraseña1)
				g, _ = Group.objects.get_or_create(name='usuario')
				usuario.groups.add(g)
				usuario.save()
				logger.info('Usuario creado desde register_view: %s (pk=%s)', usuario.username, getattr(usuario, 'pk', None))
				return redirect('/login/?created=1')
		except IntegrityError:
			errores.append('El usuario o correo ya existe.')
			return render(request, 'register.html', {
				'errores': errores,
				'rol': rol,
				'nombre_usuario': nombre_usuario,
				'correo': correo,
			})
		except Exception:
			tb = traceback.format_exc()
			logger.exception('Error creando usuario')
			errores.append('Error interno al crear la cuenta. Contacta al administrador.')
			return render(request, 'register.html', {
				'errores': errores,
				'rol': rol,
				'nombre_usuario': nombre_usuario,
				'correo': correo,
				'rastreo_debug': tb,
			})

	return render(request, 'register.html', {'rol': rol})


@login_required(login_url='login')
def panel_usuario(request):
    """Vista del panel personal del usuario."""
    return render(request, 'usuario/panel_usuario.html')


@login_required(login_url='login')
def panel_instructor(request):
    """Vista del panel personal del instructor."""
    return render(request, 'panel_instructor.html')


def logout_view(request):
    """Cerrar sesión del usuario."""
    logout(request)
    return redirect('login')