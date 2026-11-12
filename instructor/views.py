import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

logger = logging.getLogger(__name__)


RUTAS_ROLES = {
    "instructor": "role_instructor",
    "investigador": "role_investigador",
    "dinamizador": "role_dinamizador",
    "coordinador": "role_coordinador",
    "usuario": "usuario",
}


@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def login_view(request):
    rol = request.GET.get("role") or request.POST.get("role") or ""
    if rol not in RUTAS_ROLES:
        rol = ""

    mensaje_exito = None
    if request.method == "GET" and request.GET.get("created"):
        mensaje_exito = "Cuenta creada correctamente. Por favor inicia sesión."

    if request.method == "POST":
        entrada_usuario = (request.POST.get("username", "") or "").strip()
        contraseña = request.POST.get("password", "")
        recordar = request.POST.get("remember")

        usuario_para_auth = entrada_usuario
        if "@" in entrada_usuario and not User.objects.filter(username=entrada_usuario).exists():
            try:
                u = User.objects.get(email__iexact=entrada_usuario)
                usuario_para_auth = u.username
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                pass

        usuario = authenticate(request, username=usuario_para_auth, password=contraseña)
        if usuario is not None:
            login(request, usuario)
            if recordar:
                request.session.set_expiry(60 * 60 * 24 * 14)
            else:
                request.session.set_expiry(0)

            grupos_usuario = set(usuario.groups.values_list("name", flat=True))

            # 1. Si es Superusuario o está en el grupo 'administrador' -> Panel de Admin
            if usuario.is_superuser or "administrador" in grupos_usuario:
                return redirect("admin_personalizado:dashboard")

            # 2. Si está en el grupo 'instructor' -> Panel de Instructor
            if "instructor" in grupos_usuario:
                return redirect("role_instructor")

            # 3. Si el rol viene por URL/POST y coincide con un grupo del usuario -> Redirigir a ese rol
            if rol and rol in RUTAS_ROLES and rol in grupos_usuario:
                return redirect(RUTAS_ROLES[rol])

            # 4. Redirección por defecto basada en grupos prioritarios
            if "investigador" in grupos_usuario:
                return redirect("role_investigador")
            if "dinamizador" in grupos_usuario:
                return redirect("role_dinamizador")
            if "coordinador" in grupos_usuario:
                return redirect("role_coordinador")

            destino = "usuario" if "usuario" in grupos_usuario else "home"
            return redirect(destino)

        return render(
            request,
            "login.html",
            {
                "error": "Usuario o contraseña incorrectos",
                "role": rol,
                "username": entrada_usuario,
            },
        )

    context = {"role": rol}
    if mensaje_exito:
        context["success"] = mensaje_exito
    return render(request, "login.html", context)


@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def register_view(request):
    from cuentas.forms import RegistroForm

    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                usuario = form.save()
                grupo, _ = Group.objects.get_or_create(name="usuario")
                usuario.groups.add(grupo)
            return redirect("/login/?created=1")
        except IntegrityError:
            form.add_error(None, "El usuario o correo ya está registrado.")
    errores = [str(error) for items in form.errors.values() for error in items] if request.method == "POST" else []
    return render(
        request,
        "register.html",
        {
            "errores": errores,
            "rol": "",
            "nombre_usuario": request.POST.get("username", ""),
            "correo": request.POST.get("email", ""),
        },
    )


@require_POST
def logout_view(request):
    """Cerrar sesión del usuario."""
    logout(request)
    return redirect("login")
