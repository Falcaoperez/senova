"""Rutas de evidencias, reportes, perfiles y páginas de GESICOM."""

from django.urls import path

from . import views
from .busqueda import buscar

urlpatterns = [
    path("home/", views.home, name="home"),
    path("usuario/", views.role_usuario, name="usuario"),
    path("nosotros/", views.nosotros, name="nosotros"),
    path("contacto/", views.contacto, name="contacto"),
    path("ayuda/", views.ayuda, name="ayuda"),
    path("portal/", views.portal, name="portal"),
    path("roles/instructor/", views.role_instructor, name="role_instructor"),
    path("roles/instructor-table/", views.tabla_instructor, name="instructor_table"),
    path("roles/investigador/", views.role_investigador, name="role_investigador"),
    path("roles/dinamizador/", views.role_dinamizador, name="role_dinamizador"),
    path("roles/coordinador/", views.role_coordinador, name="role_coordinador"),
    path("evidencia/", views.evidencia, name="evidencia"),
    path("evidencias/", views.evidencias_list, name="evidencias_list"),
    path("api/busqueda/", buscar, name="busqueda_global"),
    path("evidencias/<int:pk>/archivo/", views.archivo_evidencia, name="archivo_evidencia"),
    path("media/<path:ruta>", views.archivo_por_ruta, name="archivo_por_ruta"),
    path("evidencias/<int:pk>/ver/", views.ver_evidencia, name="ver_evidencia"),
    path("evidencias/<int:pk>/corregir/", views.evidencia, name="corregir_evidencia"),
    path("evidencias/<int:pk>/set_aprobada/", views.set_aprobada, name="set_aprobada"),
    path(
        "evidencias/<int:envio_id>/actualizar-observaciones/",
        views.actualizar_observaciones,
        name="actualizar_observaciones",
    ),
    path("access-denied/", views.access_denied, name="access_denied"),
    path("administracion/", views.admin_menu, name="admin_menu"),
    path("proyecciones/", views.proyecciones, name="proyecciones"),
    path("reportes/", views.reportes, name="reportes"),
    path("reportes.csv", views.reportes_csv, name="reportes_csv"),
    path("reportes_trimestrales.csv", views.reportes_trimestrales_csv, name="reportes_trimestrales_csv"),
    path("editar_perfil/", views.editar_perfil, name="editar_perfil"),
]
