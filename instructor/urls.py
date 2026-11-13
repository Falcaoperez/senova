"""Entrada, registro y salida; se conservan los nombres y las rutas públicas."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.login_view, name="login_root"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
]
