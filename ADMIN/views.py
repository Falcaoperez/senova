from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters

from cuentas.correos import encolar_aviso_cambio, invalidar_recuperaciones
from cuentas.forms import ConfirmarPasswordForm, EditarUsuarioForm
from cuentas.sesiones import cerrar_sesiones

from .selectors import centro_operaciones
from .services import cambiar_estados, cambiar_roles, registrar_cambio, validar_destino


def _requerir_administrador(usuario):
    """Verifica que el usuario tenga el rol de administrador o sea superuser."""
    return usuario.is_superuser or usuario.groups.filter(name="administrador").exists()


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def panel_control(request):
    return render(request, "admin_personalizado/dashboard_modern.html", centro_operaciones(request.GET.get("periodo")))


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
@sensitive_post_parameters()
def gestionar_usuarios(request):
    if request.method == "POST":
        form = ConfirmarPasswordForm(request.POST, usuario=request.user)
        if not form.is_valid():
            messages.error(request, "Confirma tu contraseña actual para administrar las cuentas.")
            return redirect("admin_personalizado:gestionar_usuarios")
        try:
            accion = request.POST.get("accion", "roles")
            if accion in {"activar", "desactivar"}:
                total = cambiar_estados(request.user, request.POST.getlist("usuarios"), activo=accion == "activar")
                messages.success(request, f"Se cambió el estado de {total} cuentas.")
            elif accion == "roles":
                cambios = {}
                for key, value in request.POST.items():
                    if key.startswith("role_") and value != "__keep__":
                        try:
                            pk = int(key.removeprefix("role_"))
                            cambios[pk] = [int(value)] if value else []
                        except ValueError:
                            raise ValidationError("Selecciona un usuario y un rol válidos.") from None
                total = cambiar_roles(request.user, cambios)
                messages.success(request, f"Se actualizaron los roles de {total} cuentas.")
            else:
                raise ValidationError("Selecciona una acción válida.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        return redirect("admin_personalizado:gestionar_usuarios")
    busqueda = request.GET.get("q", "").strip()[:100]
    estado = request.GET.get("estado", "")
    rol = request.GET.get("rol", "")
    lista = User.objects.prefetch_related("groups").order_by("-date_joined", "-pk")
    if busqueda:
        lista = lista.filter(
            Q(username__icontains=busqueda)
            | Q(email__icontains=busqueda)
            | Q(first_name__icontains=busqueda)
            | Q(last_name__icontains=busqueda)
        )
    if estado in {"activo", "inactivo"}:
        lista = lista.filter(is_active=estado == "activo")
    if rol.isdigit():
        lista = lista.filter(groups__pk=rol)
    return render(
        request,
        "admin_personalizado/gestionar_usuarios_modern.html",
        {
            "usuarios": Paginator(lista, 25).get_page(request.GET.get("page")),
            "busqueda": busqueda,
            "estado": estado,
            "rol": rol,
            "grupos_disponibles": Group.objects.order_by("name"),
        },
    )


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
def crear_usuario(request):
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
@sensitive_post_parameters()
def detalle_usuario(request, usuario_id):
    from Gesicom.models import Envio

    usuario = get_object_or_404(User, pk=usuario_id)
    if request.method == "POST":
        if not ConfirmarPasswordForm(request.POST, usuario=request.user).is_valid():
            messages.error(request, "Confirma tu contraseña actual para modificar esta cuenta.")
            return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario_id)
        try:
            with transaction.atomic():
                usuario = User.objects.select_for_update().get(pk=usuario_id)
                validar_destino(request.user, usuario)
                accion = request.POST.get("action")
                if accion == "update_profile":
                    form = EditarUsuarioForm(request.POST, instance=usuario)
                    correo_anterior = usuario.email
                    if not form.is_valid():
                        raise ValidationError([str(e) for errors in form.errors.values() for e in errors])
                    form.save()
                    if correo_anterior.casefold() != usuario.email.casefold():
                        invalidar_recuperaciones(usuario)
                        encolar_aviso_cambio(usuario, correo_anterior)
                        cerrar_sesiones(
                            usuario, conservar=request.session.session_key if usuario.pk == request.user.pk else None
                        )
                    registrar_cambio(request.user, usuario, "perfil")
                    messages.success(request, "Datos del usuario actualizados.")
                elif accion == "update_status":
                    cambiar_estados(request.user, [usuario.pk], activo=request.POST.get("is_active") == "on")
                    messages.success(request, "Estado de la cuenta actualizado.")
                elif accion == "update_groups":
                    try:
                        ids = [int(pk) for pk in request.POST.getlist("grupos")]
                    except ValueError:
                        raise ValidationError("Selecciona roles válidos.") from None
                    cambiar_roles(request.user, {usuario.pk: ids})
                    messages.success(request, "Roles de la cuenta actualizados.")
                elif accion == "change_password":
                    form = SetPasswordForm(
                        usuario,
                        {
                            "new_password1": request.POST.get("nueva_password", ""),
                            "new_password2": request.POST.get("confirmar_password", ""),
                        },
                    )
                    if not form.is_valid():
                        raise ValidationError([str(e) for errors in form.errors.values() for e in errors])
                    form.save()
                    invalidar_recuperaciones(usuario)
                    encolar_aviso_cambio(usuario)
                    if usuario.pk == request.user.pk:
                        update_session_auth_hash(request, usuario)
                    cerrar_sesiones(
                        usuario, conservar=request.session.session_key if usuario.pk == request.user.pk else None
                    )
                    registrar_cambio(request.user, usuario, "password")
                    messages.success(request, "Contraseña actualizada. Las otras sesiones se cerraron.")
                else:
                    raise ValidationError("Selecciona una acción válida.")
        except IntegrityError:
            messages.error(request, "El correo ya está registrado. Usa otra dirección.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario_id)
    evidencias = Envio.objects.filter(usuario=usuario).order_by("-fecha_envio", "-pk")
    totales = evidencias.aggregate(
        total=Count("pk"),
        archivos=Count("pk", filter=~Q(archivo_evidencia="") & Q(archivo_evidencia__isnull=False)),
        enlaces=Count("pk", filter=~Q(link_evidencia="") & Q(link_evidencia__isnull=False)),
    )
    busqueda = request.GET.get("q", "").strip()[:100]
    if busqueda:
        evidencias = evidencias.filter(Q(nombre__icontains=busqueda) | Q(tipo_evidencia__icontains=busqueda))
    return render(
        request,
        "admin_personalizado/detalle_usuario_modern.html",
        {
            "usuario": usuario,
            "grupos_disponibles": Group.objects.order_by("name"),
            "grupos_usuario": usuario.groups.all(),
            "evidencias": Paginator(evidencias, 25).get_page(request.GET.get("page")),
            "total_evidencias": totales["total"],
            "evidencias_con_archivo": totales["archivos"],
            "evidencias_con_link": totales["enlaces"],
            "busqueda": busqueda,
            "cuenta_protegida": (usuario.is_staff or usuario.is_superuser) and not request.user.is_superuser,
        },
    )


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
@sensitive_post_parameters()
def asignar_grupo(request, usuario_id):
    usuario = get_object_or_404(User, pk=usuario_id)
    if request.method == "POST":
        try:
            if not ConfirmarPasswordForm(request.POST, usuario=request.user).is_valid():
                raise ValidationError("Confirma tu contraseña actual para cambiar los roles.")
            with transaction.atomic():
                usuario = User.objects.select_for_update().get(pk=usuario_id)
                grupo = Group.objects.get(pk=request.POST.get("grupo_id"))
                ids = set(usuario.groups.values_list("pk", flat=True))
                if request.POST.get("accion") == "agregar":
                    ids.add(grupo.pk)
                elif request.POST.get("accion") == "quitar":
                    ids.discard(grupo.pk)
                else:
                    raise ValidationError("Selecciona una acción válida.")
                cambiar_roles(request.user, {usuario.pk: ids})
            messages.success(request, "Roles de la cuenta actualizados.")
        except (Group.DoesNotExist, ValueError, TypeError):
            messages.error(request, "El grupo seleccionado no existe.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario_id)


@login_required
@user_passes_test(_requerir_administrador, login_url="access_denied")
@sensitive_post_parameters()
def activar_desactivar(request, usuario_id):
    get_object_or_404(User, pk=usuario_id)
    if request.method == "POST":
        try:
            if not ConfirmarPasswordForm(request.POST, usuario=request.user).is_valid():
                raise ValidationError("Confirma tu contraseña actual para cambiar el estado.")
            accion = request.POST.get("accion")
            if accion not in {"activar", "desactivar"}:
                raise ValidationError("Selecciona una acción válida.")
            cambiar_estados(request.user, [usuario_id], activo=accion == "activar")
            messages.success(request, "Estado de la cuenta actualizado.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return redirect("admin_personalizado:detalle_usuario", usuario_id=usuario_id)
