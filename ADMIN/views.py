from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, Permission, User
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render


def _requerir_administrador(usuario):
    """Verifica que el usuario tenga el rol de administrador o sea superuser."""
    return usuario.is_superuser or usuario.groups.filter(name="administrador").exists()


def _validar_contraseña(contraseña):
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    try:
        validate_password(contraseña)
    except ValidationError as error:
        return error.messages
    return []


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def panel_control(request):
    """Panel principal del control de administración."""
    total_usuarios = User.objects.count()
    total_grupos = Group.objects.count()
    usuarios_activos = User.objects.filter(is_active=True).count()
    from cuentas.models import CorreoSeguridad
    from notificaciones.models import CorreoPendiente

    estados = {}
    for model in (CorreoSeguridad, CorreoPendiente):
        for row in model.objects.values("estado").annotate(total=Count("pk")):
            estados[row["estado"]] = estados.get(row["estado"], 0) + row["total"]

    # Calcular porcentaje de usuarios activos
    if total_usuarios > 0:
        usuarios_activos_porcentaje = round((usuarios_activos / total_usuarios) * 100)
    else:
        usuarios_activos_porcentaje = 0

    context = {
        "usuarios_recientes": User.objects.order_by("-date_joined")[:5],
        "total_usuarios": total_usuarios,
        "total_grupos": total_grupos,
        "usuarios_activos": usuarios_activos,
        "usuarios_activos_porcentaje": usuarios_activos_porcentaje,
        "correo_remitente": settings.DEFAULT_FROM_EMAIL,
        "correo_pruebas": settings.EMAIL_HOST in {"localhost", "127.0.0.1", "mailpit", "senova-mailpit"},
        "correo_credencial": bool(settings.EMAIL_HOST_PASSWORD or settings.EMAIL_OAUTH2_ACCESS_TOKEN),
        "correo_trabajador": bool(cache.get("notificaciones:trabajador")),
        "correos_pendientes": estados.get("pendiente", 0) + estados.get("procesando", 0),
        "correos_errores": estados.get("error", 0),
    }
    return render(request, "admin_personalizado/dashboard_modern.html", context)


@user_passes_test(_requerir_administrador, login_url="access_denied")
def usuarios(request):
    """Lista de usuarios con paginación y búsqueda."""
    lista_usuarios = User.objects.all().prefetch_related("groups").order_by("-date_joined")
    busqueda = request.GET.get("q", "").strip()
    if busqueda:
        lista_usuarios = lista_usuarios.filter(
            Q(username__icontains=busqueda)
            | Q(email__icontains=busqueda)
            | Q(first_name__icontains=busqueda)
            | Q(last_name__icontains=busqueda)
        )

    # Paginación
    paginador = Paginator(lista_usuarios, 10)
    numero_pagina = request.GET.get("page")
    usuarios = paginador.get_page(numero_pagina)

    context = {
        "usuarios": usuarios,
        "grupos_disponibles": Group.objects.all().order_by("name"),
        "busqueda": request.GET.get("q", "").strip(),
    }
    return render(request, "admin_personalizado/usuarios.html", context)


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def permisos(request):
    """Gestión de permisos de grupos."""
    grupos = Group.objects.all().order_by("name")
    grupo_seleccionado = None
    permisos = []

    # Si se envió el formulario
    if request.method == "POST":
        id_grupo = request.POST.get("group")
        if id_grupo:
            try:
                grupo_seleccionado = Group.objects.get(id=id_grupo)

                # Procesar cada permiso enviado
                for clave, valor in request.POST.items():
                    if clave.startswith("perm_") and "_1" in clave:
                        # Extraer el codename del permiso
                        codename = clave.replace("perm_", "").replace("_1", "")
                        permission_value = valor

                        # Buscar el permiso en la base de datos
                        try:
                            origen = {
                                "add_envio": "Gesicom",
                                "change_envio": "Gesicom",
                                "delete_envio": "Gesicom",
                                "view_envio": "Gesicom",
                                "change_user": "auth",
                                "view_logentry": "admin",
                            }.get(codename)
                            if not origen:
                                continue
                            permiso = Permission.objects.get(codename=codename, content_type__app_label=origen)

                            # Si es "permitido", agregar el permiso al grupo
                            if permission_value == "allowed":
                                grupo_seleccionado.permissions.add(permiso)
                            # Si es "denegado" o "heredado", remover el permiso del grupo
                            else:
                                grupo_seleccionado.permissions.remove(permiso)
                        except Permission.DoesNotExist:
                            # El permiso no existe, ignorar
                            pass

                messages.success(request, f"Permisos del grupo {grupo_seleccionado.name} actualizados correctamente.")
                return redirect(f"{request.path}?group={id_grupo}")
            except Group.DoesNotExist:
                messages.error(request, "El grupo seleccionado no existe.")

    # Obtener el grupo seleccionado para mostrar
    id_grupo = request.GET.get("group")
    if id_grupo:
        try:
            grupo_seleccionado = Group.objects.get(id=id_grupo)
        except Group.DoesNotExist:
            messages.error(request, "El grupo seleccionado no existe.")

    # Preparar los datos de permisos para mostrar
    if grupo_seleccionado:
        # Obtener todos los permisos del grupo
        permisos_grupo = grupo_seleccionado.permissions.all()
        nombres_permisos = [p.codename for p in permisos_grupo]

        # Definir las acciones a mostrar
        datos_permisos = [
            {
                "etiqueta": "Crear",
                "nombre_codigo": "add_envio",
                "estado_1": "allowed" if "add_envio" in nombres_permisos else "inherited",
                "estado_2": "allowed",
            },
            {
                "etiqueta": "Borrar",
                "nombre_codigo": "delete_envio",
                "estado_1": "allowed" if "delete_envio" in nombres_permisos else "inherited",
                "estado_2": "inherited",
            },
            {
                "etiqueta": "Editar",
                "nombre_codigo": "change_envio",
                "estado_1": "allowed" if "change_envio" in nombres_permisos else "inherited",
                "estado_2": "allowed",
            },
            {
                "etiqueta": "Editar estado",
                "nombre_codigo": "change_user",
                "estado_1": "allowed" if "change_user" in nombres_permisos else "inherited",
                "estado_2": "allowed",
            },
            {
                "etiqueta": "Acceso a la interfaz de administración",
                "nombre_codigo": "view_logentry",
                "estado_1": "allowed" if "view_logentry" in nombres_permisos else "inherited",
                "estado_2": "inherited",
            },
            {
                "etiqueta": "Solo opciones de configuración",
                "nombre_codigo": "view_envio",
                "estado_1": "allowed" if "view_envio" in nombres_permisos else "inherited",
                "estado_2": "inherited",
            },
        ]

        permisos = datos_permisos

    context = {
        "grupos": grupos,
        "grupo_seleccionado": grupo_seleccionado,
        "permisos": permisos,
    }
    return render(request, "admin_personalizado/permisos.html", context)


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def gestionar_usuarios(request):
    """Gestiona la lista de usuarios del sistema."""

    if request.method == "POST":
        # Procesar actualización masiva de roles
        usuarios_actualizados = 0
        for key, value in request.POST.items():
            if key.startswith("role_") and value != "__keep__":
                try:
                    usuario_id = int(key.replace("role_", ""))
                    usuario = User.objects.get(id=usuario_id)

                    grupo = Group.objects.get(id=int(value)) if value else None
                    usuario.groups.set([grupo] if grupo else [])
                    usuarios_actualizados += 1
                except (ValueError, User.DoesNotExist, Group.DoesNotExist):
                    continue

        messages.success(request, f"Se actualizaron {usuarios_actualizados} usuarios correctamente.")
        return redirect("admin_personalizado:gestionar_usuarios")

    busqueda = request.GET.get("q", "").strip()

    lista_usuarios = User.objects.all().prefetch_related("groups").order_by("-date_joined")

    # Filtrar por búsqueda
    if busqueda:
        lista_usuarios = lista_usuarios.filter(
            Q(username__icontains=busqueda)
            | Q(email__icontains=busqueda)
            | Q(first_name__icontains=busqueda)
            | Q(last_name__icontains=busqueda)
        )

    grupos_disponibles = Group.objects.all().order_by("name")

    context = {
        "usuarios": Paginator(lista_usuarios, 25).get_page(request.GET.get("page")),
        "busqueda": busqueda,
        "grupos_disponibles": grupos_disponibles,
    }
    return render(request, "admin_personalizado/gestionar_usuarios_modern.html", context)


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def crear_usuario(request):
    from django.db import IntegrityError

    from cuentas.forms import CrearUsuarioForm

    form = CrearUsuarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                usuario = form.save()
            messages.success(request, f'Usuario "{usuario.username}" creado correctamente.')
            return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario.pk)
        except IntegrityError:
            form.add_error(None, "El usuario o correo ya está registrado.")
    return render(
        request,
        "admin_personalizado/crear_usuario.html",
        {
            "grupos_disponibles": Group.objects.order_by("name"),
            "errores": [str(error) for items in form.errors.values() for error in items]
            if request.method == "POST"
            else [],
            "nombre_usuario": request.POST.get("username", ""),
            "correo": request.POST.get("email", ""),
            "nombre": request.POST.get("first_name", ""),
            "apellido": request.POST.get("last_name", ""),
        },
    )


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def detalle_usuario(request, usuario_id):
    """Detalle y edición de un usuario."""
    from Gesicom.models import Envio

    usuario = get_object_or_404(User, id=usuario_id)
    grupos_disponibles = Group.objects.all()
    grupos_usuario = usuario.groups.all()

    # Obtener evidencias del usuario
    evidencias = Envio.objects.filter(usuario=usuario).order_by("-fecha_envio")

    # Calcular estadísticas de evidencias
    total_evidencias = evidencias.count()
    evidencias_con_archivo = evidencias.exclude(archivo_evidencia="").count()
    evidencias_con_link = evidencias.exclude(link_evidencia="").exclude(link_evidencia=None).count()

    if request.method == "POST":
        accion = request.POST.get("action")

        if accion == "update_profile":
            from cuentas.forms import EditarUsuarioForm

            form = EditarUsuarioForm(request.POST, instance=usuario)
            if form.is_valid():
                form.save()
                messages.success(request, f"Perfil de {usuario.username} actualizado correctamente.")
            else:
                for errores in form.errors.values():
                    for error in errores:
                        messages.error(request, error)

        elif accion == "update_status":
            activo = request.POST.get("is_active") == "on"
            usuario.is_active = activo
            usuario.save()
            estado = "activado" if activo else "desactivado"
            messages.success(request, f"Usuario {usuario.username} {estado} correctamente.")

        elif accion == "update_groups":
            ids_grupos = request.POST.getlist("grupos")
            usuario.groups.set(ids_grupos)
            messages.success(request, f"Grupos del usuario {usuario.username} actualizados.")

        elif accion == "change_password":
            nueva_contraseña = request.POST.get("nueva_password", "")
            confirmar_contraseña = request.POST.get("confirmar_password", "")

            errores = _validar_contraseña(nueva_contraseña)

            if nueva_contraseña != confirmar_contraseña:
                errores.append("Las contraseñas no coinciden.")

            if errores:
                for error in errores:
                    messages.error(request, error)
            else:
                usuario.set_password(nueva_contraseña)
                usuario.save()
                messages.success(request, f"Contraseña de {usuario.username} cambiada correctamente.")

        return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario_id)

    context = {
        "usuario": usuario,
        "grupos_disponibles": grupos_disponibles,
        "grupos_usuario": grupos_usuario,
        "evidencias": evidencias,
        "total_evidencias": total_evidencias,
        "evidencias_con_archivo": evidencias_con_archivo,
        "evidencias_con_link": evidencias_con_link,
    }
    return render(request, "admin_personalizado/detalle_usuario_modern.html", context)


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def asignar_grupo(request, usuario_id):
    """Endpoint para asignar/remover grupos de usuarios."""
    usuario = get_object_or_404(User, id=usuario_id)

    if request.method == "POST":
        accion = request.POST.get("accion")
        id_grupo = request.POST.get("grupo_id")

        try:
            grupo = Group.objects.get(id=id_grupo)

            if accion == "agregar":
                usuario.groups.add(grupo)
                mensaje = f'Rol "{grupo.name}" agregado al usuario {usuario.username}'
            elif accion == "quitar":
                usuario.groups.remove(grupo)
                mensaje = f'Rol "{grupo.name}" eliminado del usuario {usuario.username}'
            else:
                return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario_id)

            messages.success(request, mensaje)
        except Group.DoesNotExist:
            messages.error(request, "El grupo seleccionado no existe.")

    return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario_id)


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def activar_desactivar(request, usuario_id):
    """Endpoint para activar/desactivar usuarios."""
    usuario = get_object_or_404(User, id=usuario_id)

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "activar":
            usuario.is_active = True
            usuario.save()
            messages.success(request, f"Usuario {usuario.username} activado correctamente.")
        elif accion == "desactivar":
            usuario.is_active = False
            usuario.save()
            messages.success(request, f"Usuario {usuario.username} desactivado correctamente.")

    return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario_id)
