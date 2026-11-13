"""Recuperación y control de sesiones, incluidas las rutas históricas."""

from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from . import seguridad, views

urlpatterns = [
    path("password-reset/", views.password_reset_form, name="password_reset"),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="Registro/password_reset_done.html"),
        name="password_reset_done",
    ),
    path("password-reset/update/", views.password_reset_update, name="password_reset_update"),
    path("reset/<uidb64>/<token>/", RedirectView.as_view(pattern_name="password_reset"), name="password_reset_confirm"),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="Registro/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("api/olvide_password/", views.olvide_password, name="olvide_password"),
    path("password-reset/new/", views.password_reset_new, name="password_reset_new"),
    path("api/verificar_pin/", views.verificar_pin, name="verificar_pin"),
    path("api/restablecer_password/", views.restablecer_password, name="restablecer_password"),
    path("mi-cuenta/seguridad/", seguridad.centro_seguridad, name="centro_seguridad"),
    path("mi-cuenta/sesiones/<int:pk>/cerrar/", seguridad.revocar_sesion, name="revocar_sesion"),
    path("mi-cuenta/sesiones/cerrar-otras/", seguridad.cerrar_otras_sesiones, name="cerrar_otras_sesiones"),
]
