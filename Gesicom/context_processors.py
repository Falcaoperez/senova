"""Contexto común: identidad visual, navegación y avisos del usuario autenticado."""

from django.urls import reverse

from .models import Envio
from .utils import user_roles


def interface(request):
    user = request.user
    groups = user_roles(user) if user.is_authenticated else set()
    admin = user.is_authenticated and (user.is_superuser or "administrador" in groups)
    role = (
        "administrador"
        if admin
        else next(
            (
                name
                for name in ["instructor", "investigador", "dinamizador", "coordinador", "usuario"]
                if name in groups
            ),
            "usuario",
        )
    )
    panel = (
        "admin_personalizado:dashboard"
        if admin
        else ("usuario" if "usuario" in groups else "home")
        if role == "usuario"
        else "role_" + role
    )
    current = request.resolver_match.view_name if request.resolver_match else ""
    items = [
        ("Mi espacio", panel, "grid"),
        ("Evidencias", "evidencias_list", "folder"),
        ("Enviar evidencia", "evidencia", "upload"),
        ("Reportes", "reportes", "chart"),
    ]
    if admin:
        items += [
            ("Usuarios", "admin_personalizado:gestionar_usuarios", "users"),
            ("Permisos", "admin_personalizado:permisos", "shield"),
            ("Novedades", "notificaciones:novedades_admin", "bell"),
            ("Plazos de reportes", "notificaciones:plazos_admin", "clock"),
        ]
    else:
        items.append(("Mis plazos", "notificaciones:mis_plazos", "clock"))
    navigation = []
    for label, route, glyph in items:
        active = current == route
        if route == "admin_personalizado:gestionar_usuarios":
            active = current in [
                "admin_personalizado:gestionar_usuarios",
                "admin_personalizado:usuarios",
                "admin_personalizado:detalle_usuario",
                "admin_personalizado:crear_usuario",
            ]
        if route == "notificaciones:novedades_admin":
            active = current in ["notificaciones:novedades_admin", "notificaciones:crear_novedad"]
        if route == "notificaciones:plazos_admin":
            active = current in [
                "notificaciones:plazos_admin",
                "notificaciones:crear_plazo",
                "notificaciones:editar_plazo",
            ]
        navigation.append({"label": label, "url": reverse(route), "icon": glyph, "active": active})
    pendientes = 0
    recientes = []
    if user.is_authenticated:
        from notificaciones.models import Notificacion

        avisos = Notificacion.objects.filter(usuario=user)
        pendientes = avisos.filter(leida_en__isnull=True).count()
        recientes = list(avisos.only("titulo", "creada_en", "leida_en")[:4])
    return {
        "proyectos_evidencia": Envio.PROYECTO_CHOICES,
        "tipos_evidencia": [
            ("planeacion", "Planeación"),
            ("ejecucion", "Ejecución"),
            ("evaluacion", "Evaluación"),
            ("informe", "Informe Final"),
        ],
        "ui_role": role.capitalize(),
        "ui_admin": admin,
        "ui_reviewer": admin or bool(groups & {"coordinador", "dinamizador"}),
        "ui_panel_url": reverse(panel),
        "ui_navigation": navigation,
        "ui_notificaciones_pendientes": pendientes,
        "ui_notificaciones_recientes": recientes,
    }
