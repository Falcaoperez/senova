from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.contrib import messages
from django.db import transaction, models
from django.db.models import Q
import re


def _requerir_administrador(usuario):
	"""Verifica que el usuario tenga el rol de administrador o sea superuser."""
	return usuario.is_superuser or usuario.groups.filter(name='administrador').exists()


def _validar_contraseña(contraseña):
	"""Valida que la contraseña cumpla con los requisitos."""
	errores = []
	
	if not contraseña:
		errores.append('La contraseña es obligatoria.')
		return errores
	
	if len(contraseña) != 8:
		errores.append('La contraseña debe tener exactamente 8 caracteres.')
	
	tiene_mayuscula = re.search(r'[A-Z]', contraseña) is not None
	tiene_digito = re.search(r'\d', contraseña) is not None
	tiene_especial = re.search(r'[!@#$%^&*(),.?":{}|<>]', contraseña) is not None
	
	if not tiene_mayuscula:
		errores.append('Debe contener al menos una letra mayúscula.')
	
	if not (tiene_digito or tiene_especial):
		errores.append('Debe contener al menos un número o carácter especial.')
	
	return errores


@login_required
@user_passes_test(_requerir_administrador, login_url='access_denied')
def panel_control(request):
	"""Panel principal del control de administración."""
	total_usuarios = User.objects.count()
	total_grupos = Group.objects.count()
	usuarios_activos = User.objects.filter(is_active=True).count()

	# Calcular porcentaje de usuarios activos
	if total_usuarios > 0:
		usuarios_activos_porcentaje = round((usuarios_activos / total_usuarios) * 100)
	else:
		usuarios_activos_porcentaje = 0

	context = {
		'total_usuarios': total_usuarios,
		'total_grupos': total_grupos,
		'usuarios_activos': usuarios_activos,
		'usuarios_activos_porcentaje': usuarios_activos_porcentaje,
	}
	return render(request, 'admin_personalizado/dashboard_modern.html', context)


@user_passes_test(_requerir_administrador, login_url='access_denied')
def usuarios(request):
	"""Lista de usuarios con paginación y búsqueda."""
	lista_usuarios = User.objects.all().prefetch_related('groups').order_by('-date_joined')

	# Paginación
	paginador = Paginator(lista_usuarios, 10)
	numero_pagina = request.GET.get('page')
	usuarios = paginador.get_page(numero_pagina)

	context = {
		'usuarios': usuarios,
	}
	return render(request, 'admin_personalizado/usuarios.html', context)


@login_required
@user_passes_test(_requerir_administrador, login_url='access_denied')
def permisos(request):
	"""Gestión de permisos de grupos."""
	grupos = Group.objects.all().order_by('name')
	grupo_seleccionado = None
	permisos = []

	# Si se envió el formulario
	if request.method == 'POST':
		id_grupo = request.POST.get('group')
		if id_grupo:
			try:
				grupo_seleccionado = Group.objects.get(id=id_grupo)

				# Procesar cada permiso enviado
				for clave, valor in request.POST.items():
					if clave.startswith('perm_') and '_1' in clave:
						# Extraer el codename del permiso
						codename = clave.replace('perm_', '').replace('_1', '')
						permission_value = valor

						# Buscar el permiso en la base de datos
						try:
							permiso = Permission.objects.get(codename=codename)

							# Si es "permitido", agregar el permiso al grupo
							if permission_value == 'allowed':
								grupo_seleccionado.permissions.add(permiso)
							# Si es "denegado" o "heredado", remover el permiso del grupo
							else:
								grupo_seleccionado.permissions.remove(permiso)
						except Permission.DoesNotExist:
							# El permiso no existe, ignorar
							pass

				messages.success(request, f'Permisos del grupo {grupo_seleccionado.name} actualizados correctamente.')
				return redirect(f"{request.path}?group={id_grupo}")
			except Group.DoesNotExist:
				messages.error(request, 'El grupo seleccionado no existe.')

	# Obtener el grupo seleccionado para mostrar
	id_grupo = request.GET.get('group')
	if id_grupo:
		try:
			grupo_seleccionado = Group.objects.get(id=id_grupo)
		except Group.DoesNotExist:
			messages.error(request, 'El grupo seleccionado no existe.')

	# Preparar los datos de permisos para mostrar
	if grupo_seleccionado:
		# Obtener todos los permisos del grupo
		permisos_grupo = grupo_seleccionado.permissions.all()
		nombres_permisos = [p.codename for p in permisos_grupo]

		# Definir las acciones a mostrar
		datos_permisos = [
			{
				'etiqueta': 'Configurar',
				'nombre_codigo': 'change_envio',
				'estado_1': 'allowed' if 'change_envio' in nombres_permisos else 'inherited',
				'estado_2': 'allowed',
			},
			{
				'etiqueta': 'Crear',
				'nombre_codigo': 'add_envio',
				'estado_1': 'allowed' if 'add_envio' in nombres_permisos else 'inherited',
				'estado_2': 'allowed',
			},
			{
				'etiqueta': 'Borrar',
				'nombre_codigo': 'delete_envio',
				'estado_1': 'allowed' if 'delete_envio' in nombres_permisos else 'inherited',
				'estado_2': 'inherited',
			},
			{
				'etiqueta': 'Editar',
				'nombre_codigo': 'change_envio',
				'estado_1': 'allowed' if 'change_envio' in nombres_permisos else 'inherited',
				'estado_2': 'allowed',
			},
			{
				'etiqueta': 'Editar estado',
				'nombre_codigo': 'change_user',
				'estado_1': 'allowed' if 'change_user' in nombres_permisos else 'inherited',
				'estado_2': 'allowed',
			},
			{
				'etiqueta': 'Acceso a la interfaz de administración',
				'nombre_codigo': 'view_logentry',
				'estado_1': 'allowed' if 'view_logentry' in nombres_permisos else 'inherited',
				'estado_2': 'inherited',
			},
			{
				'etiqueta': 'Solo opciones de configuración',
				'nombre_codigo': 'view_envio',
				'estado_1': 'allowed' if 'view_envio' in nombres_permisos else 'inherited',
				'estado_2': 'inherited',
			},
		]

		permisos = datos_permisos

	context = {
		'grupos': grupos,
		'grupo_seleccionado': grupo_seleccionado,
		'permisos': permisos,
	}
	return render(request, 'admin_personalizado/permisos.html', context)


@login_required
@user_passes_test(_requerir_administrador, login_url='access_denied')
def gestionar_usuarios(request):
	"""Gestiona la lista de usuarios del sistema."""

	if request.method == 'POST':
		# Procesar actualización masiva de roles
		usuarios_actualizados = 0
		for key, value in request.POST.items():
			if key.startswith('role_'):
				try:
					usuario_id = int(key.replace('role_', ''))
					usuario = User.objects.get(id=usuario_id)

					# Limpiar grupos existentes y asignar nuevo rol si se seleccionó
					usuario.groups.clear()
					if value:
						grupo = Group.objects.get(id=int(value))
						usuario.groups.add(grupo)
					usuarios_actualizados += 1
				except (ValueError, User.DoesNotExist, Group.DoesNotExist):
					continue

		messages.success(request, f'Se actualizaron {usuarios_actualizados} usuarios correctamente.')
		return redirect('admin_personalizado:gestionar_usuarios')

	busqueda = request.GET.get('q', '').strip()

	lista_usuarios = User.objects.all().prefetch_related('groups').order_by('-date_joined')

	# Filtrar por búsqueda
	if busqueda:
		lista_usuarios = lista_usuarios.filter(
			Q(username__icontains=busqueda) |
			Q(email__icontains=busqueda) |
			Q(first_name__icontains=busqueda) |
			Q(last_name__icontains=busqueda)
		)

	grupos_disponibles = Group.objects.all().order_by('name')

	context = {
		'usuarios': lista_usuarios,
		'busqueda': busqueda,
		'grupos_disponibles': grupos_disponibles,
	}
	return render(request, 'admin_personalizado/gestionar_usuarios_modern.html', context)


@login_required
@user_passes_test(_requerir_administrador, login_url='access_denied')
def crear_usuario(request):
	"""Crea un nuevo usuario desde el panel de administración."""
	grupos_disponibles = Group.objects.all()
	
	if request.method == 'POST':
		nombre_usuario = request.POST.get('username', '').strip()
		correo = request.POST.get('email', '').strip().lower()
		contraseña = request.POST.get('password', '')
		confirmar_contraseña = request.POST.get('password_confirm', '')
		nombre = request.POST.get('first_name', '').strip()
		apellido = request.POST.get('last_name', '').strip()
		ids_grupos = request.POST.getlist('grupos')
		
		errores = []
		
		# Validaciones
		if not nombre_usuario:
			errores.append('El nombre de usuario es obligatorio.')
		elif User.objects.filter(username=nombre_usuario).exists():
			errores.append('Ese nombre de usuario ya existe.')
		
		if not correo:
			errores.append('El correo es obligatorio.')
		elif User.objects.filter(email=correo).exists():
			errores.append('Ese correo ya está registrado.')
		
		errores.extend(_validar_contraseña(contraseña))
		
		if contraseña != confirmar_contraseña:
			errores.append('Las contraseñas no coinciden.')
		
		if errores:
			contexto = {
				'grupos_disponibles': grupos_disponibles,
				'errores': errores,
				'nombre_usuario': nombre_usuario,
				'correo': correo,
				'nombre': nombre,
				'apellido': apellido,
			}
			return render(request, 'admin_personalizado/crear_usuario.html', contexto)
		
		try:
			with transaction.atomic():
				usuario = User.objects.create_user(
					username=nombre_usuario,
					email=correo,
					password=contraseña,
					first_name=nombre,
					last_name=apellido,
					is_active=True  # 👈 IMPORTANTE: Asegurar que el usuario sea activo
				)
				
				# Asignar grupos si se seleccionaron
				if ids_grupos:
					grupos = Group.objects.filter(id__in=ids_grupos)
					usuario.groups.set(grupos)
				
				messages.success(request, f'Usuario "{nombre_usuario}" creado correctamente y está ACTIVO.')
				return redirect('admin_personalizado:detalle_usuario', usuario_id=usuario.id)
		
		except Exception as e:
			messages.error(request, f'Error al crear el usuario: {str(e)}')
	
	context = {
		'grupos_disponibles': grupos_disponibles,
	}
	return render(request, 'admin_personalizado/crear_usuario.html', context)


@login_required
@user_passes_test(_requerir_administrador, login_url='access_denied')
def detalle_usuario(request, usuario_id):
	"""Detalle y edición de un usuario."""
	from Gesicom.models import Envio

	usuario = get_object_or_404(User, id=usuario_id)
	grupos_disponibles = Group.objects.all()
	grupos_usuario = usuario.groups.all()

	# Obtener evidencias del usuario
	evidencias = Envio.objects.filter(usuario=usuario).order_by('-fecha_envio')

	# Calcular estadísticas de evidencias
	total_evidencias = evidencias.count()
	evidencias_con_archivo = evidencias.exclude(archivo_evidencia='').count()
	evidencias_con_link = evidencias.exclude(link_evidencia='').exclude(link_evidencia=None).count()

	if request.method == 'POST':
		accion = request.POST.get('action')

		if accion == 'update_profile':
			usuario.first_name = request.POST.get('first_name', '').strip()
			usuario.last_name = request.POST.get('last_name', '').strip()
			usuario.email = request.POST.get('email', '').strip()
			usuario.save()
			messages.success(request, f'Perfil de {usuario.username} actualizado correctamente.')

		elif accion == 'update_status':
			activo = request.POST.get('is_active') == 'on'
			usuario.is_active = activo
			usuario.save()
			estado = "activado" if activo else "desactivado"
			messages.success(request, f'Usuario {usuario.username} {estado} correctamente.')

		elif accion == 'update_groups':
			ids_grupos = request.POST.getlist('grupos')
			usuario.groups.set(ids_grupos)
			messages.success(request, f'Grupos del usuario {usuario.username} actualizados.')

		elif accion == 'change_password':
			nueva_contraseña = request.POST.get('nueva_password', '')
			confirmar_contraseña = request.POST.get('confirmar_password', '')

			errores = _validar_contraseña(nueva_contraseña)

			if nueva_contraseña != confirmar_contraseña:
				errores.append('Las contraseñas no coinciden.')

			if errores:
				for error in errores:
					messages.error(request, error)
			else:
				usuario.set_password(nueva_contraseña)
				usuario.save()
				messages.success(request, f'Contraseña de {usuario.username} cambiada correctamente.')

		return redirect('admin_personalizado:detalle_usuario', usuario_id=usuario_id)

	context = {
		'usuario': usuario,
		'grupos_disponibles': grupos_disponibles,
		'grupos_usuario': grupos_usuario,
		'evidencias': evidencias,
		'total_evidencias': total_evidencias,
		'evidencias_con_archivo': evidencias_con_archivo,
		'evidencias_con_link': evidencias_con_link,
	}
	return render(request, 'admin_personalizado/detalle_usuario_modern.html', context)


@login_required
@user_passes_test(_requerir_administrador, login_url='access_denied')
def asignar_grupo(request, usuario_id):
	"""Endpoint para asignar/remover grupos de usuarios."""
	usuario = get_object_or_404(User, id=usuario_id)
	
	if request.method == 'POST':
		accion = request.POST.get('accion')
		id_grupo = request.POST.get('grupo_id')
		
		try:
			grupo = Group.objects.get(id=id_grupo)
			
			if accion == 'agregar':
				usuario.groups.add(grupo)
				mensaje = f'Rol "{grupo.name}" agregado al usuario {usuario.username}'
			elif accion == 'quitar':
				usuario.groups.remove(grupo)
				mensaje = f'Rol "{grupo.name}" eliminado del usuario {usuario.username}'
			else:
				return redirect('admin_personalizado:detalle_usuario', usuario_id=usuario_id)
			
			messages.success(request, mensaje)
		except Group.DoesNotExist:
			messages.error(request, 'El grupo seleccionado no existe.')
	
	return redirect('admin_personalizado:detalle_usuario', usuario_id=usuario_id)


@login_required
@user_passes_test(_requerir_administrador, login_url='access_denied')
def activar_desactivar(request, usuario_id):
	"""Endpoint para activar/desactivar usuarios."""
	usuario = get_object_or_404(User, id=usuario_id)
	
	if request.method == 'POST':
		accion = request.POST.get('accion')
		
		if accion == 'activar':
			usuario.is_active = True
			usuario.save()
			messages.success(request, f'Usuario {usuario.username} activado correctamente.')
		elif accion == 'desactivar':
			usuario.is_active = False
			usuario.save()
			messages.success(request, f'Usuario {usuario.username} desactivado correctamente.')
	
	return redirect('admin_personalizado:detalle_usuario', usuario_id=usuario_id)


