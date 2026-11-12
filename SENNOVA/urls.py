from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from cuentas import seguridad as seguridad_views
from cuentas import views as cuentas_views
from Gesicom import views as gesicom_views
from Gesicom.busqueda import buscar
from instructor import views as usuarios_views

from .health import health

urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("administrador/", include("ADMIN.urls")),
    path("notificaciones/", include("notificaciones.urls")),
    path("", usuarios_views.login_view, name="login_root"),
    path("login/", usuarios_views.login_view, name="login"),
    path("logout/", usuarios_views.logout_view, name="logout"),
    path("register/", usuarios_views.register_view, name="register"),
    path("home/", gesicom_views.home, name="home"),
    path("usuario/", gesicom_views.role_usuario, name="usuario"),
    path("nosotros/", gesicom_views.nosotros, name="nosotros"),
    path("contacto/", gesicom_views.contacto, name="contacto"),
    path("ayuda/", gesicom_views.ayuda, name="ayuda"),
    path("portal/", gesicom_views.portal, name="portal"),
    path("roles/instructor/", gesicom_views.role_instructor, name="role_instructor"),
    path("roles/instructor-table/", gesicom_views.tabla_instructor, name="instructor_table"),
    path("roles/investigador/", gesicom_views.role_investigador, name="role_investigador"),
    path("roles/dinamizador/", gesicom_views.role_dinamizador, name="role_dinamizador"),
    path("roles/coordinador/", gesicom_views.role_coordinador, name="role_coordinador"),
    path("evidencia/", gesicom_views.evidencia, name="evidencia"),
    path("evidencias/", gesicom_views.evidencias_list, name="evidencias_list"),
    path("api/busqueda/", buscar, name="busqueda_global"),
    path("evidencias/<int:pk>/archivo/", gesicom_views.archivo_evidencia, name="archivo_evidencia"),
    path("media/<path:ruta>", gesicom_views.archivo_por_ruta, name="archivo_por_ruta"),
    path("evidencias/<int:pk>/ver/", gesicom_views.ver_evidencia, name="ver_evidencia"),
    path("evidencias/<int:pk>/set_aprobada/", gesicom_views.set_aprobada, name="set_aprobada"),
    path(
        "evidencias/<int:envio_id>/actualizar-observaciones/",
        gesicom_views.actualizar_observaciones,
        name="actualizar_observaciones",
    ),
    path("access-denied/", gesicom_views.access_denied, name="access_denied"),
    path("administracion/", gesicom_views.admin_menu, name="admin_menu"),
    path("proyecciones/", gesicom_views.proyecciones, name="proyecciones"),
    path("reportes/", gesicom_views.reportes, name="reportes"),
    path("reportes.csv", gesicom_views.reportes_csv, name="reportes_csv"),
    path("reportes_trimestrales.csv", gesicom_views.reportes_trimestrales_csv, name="reportes_trimestrales_csv"),
    path("password-reset/", cuentas_views.password_reset_form, name="password_reset"),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="Registro/password_reset_done.html"),
        name="password_reset_done",
    ),
    path("password-reset/update/", cuentas_views.password_reset_update, name="password_reset_update"),
    path("reset/<uidb64>/<token>/", RedirectView.as_view(pattern_name="password_reset"), name="password_reset_confirm"),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="Registro/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    # Endpoints AJAX/JSON para flujo de restablecimiento personalizado
    path("api/olvide_password/", cuentas_views.olvide_password, name="olvide_password"),
    path("password-reset/new/", cuentas_views.password_reset_new, name="password_reset_new"),
    path("api/verificar_pin/", cuentas_views.verificar_pin, name="verificar_pin"),
    path("api/restablecer_password/", cuentas_views.restablecer_password, name="restablecer_password"),
    path("editar_perfil/", gesicom_views.editar_perfil, name="editar_perfil"),
    path("mi-cuenta/seguridad/", seguridad_views.centro_seguridad, name="centro_seguridad"),
    path("mi-cuenta/sesiones/<int:pk>/cerrar/", seguridad_views.revocar_sesion, name="revocar_sesion"),
    path("mi-cuenta/sesiones/cerrar-otras/", seguridad_views.cerrar_otras_sesiones, name="cerrar_otras_sesiones"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
