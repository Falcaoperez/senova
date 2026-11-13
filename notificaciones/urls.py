from django.urls import path

from . import views

app_name = "notificaciones"
urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("resumen/", views.resumen, name="resumen"),
    path("leidas/", views.marcar_todas, name="marcar_todas"),
    path("seleccion/", views.lectura, name="lectura_seleccion"),
    path("preferencias/", views.preferencias, name="preferencias"),
    path("<int:pk>/abrir/", views.abrir, name="abrir"),
    path("<int:pk>/lectura/", views.lectura, name="lectura"),
    path("plazos/", views.mis_plazos, name="mis_plazos"),
    path("plazos/calendario.ics", views.calendario_ics, name="calendario_ics"),
    path("administracion/novedades/", views.novedades_admin, name="novedades_admin"),
    path("administracion/novedades/crear/", views.crear_novedad, name="crear_novedad"),
    path("administracion/plazos/", views.plazos_admin, name="plazos_admin"),
    path("administracion/plazos/crear/", views.editar_plazo, name="crear_plazo"),
    path("administracion/plazos/<int:pk>/", views.editar_plazo, name="editar_plazo"),
    path("administracion/plazos/<int:pk>/seguimiento/", views.seguimiento_plazo, name="seguimiento_plazo"),
    path("administracion/plazos/<int:pk>/exportar/", views.seguimiento_csv, name="seguimiento_csv"),
    path(
        "administracion/plazos/<int:pk>/recordar/",
        views.accion_plazo,
        {"accion": "recordar"},
        name="recordar_pendientes",
    ),
    path("administracion/plazos/<int:pk>/archivar/", views.accion_plazo, {"accion": "archivar"}, name="archivar_plazo"),
    path("administracion/correos/reintentar/", views.reintentar_correos, name="reintentar_correos"),
]
