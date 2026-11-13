"""Composición del proyecto; cada aplicación mantiene sus propias rutas."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from .health import health

urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("administrador/", include("ADMIN.urls")),
    path("notificaciones/", include("notificaciones.urls")),
    path("", include("instructor.urls")),
    path("", include("Gesicom.urls")),
    path("", include("cuentas.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
