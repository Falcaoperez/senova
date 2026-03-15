from django.urls import path
from . import views

app_name = 'admin_personalizado'

urlpatterns = [
    path('', views.panel_control, name='dashboard'),
    path('usuarios/', views.usuarios, name='usuarios'),
    path('gestionar-usuarios/', views.gestionar_usuarios, name='gestionar_usuarios'),
    path('usuario/<int:usuario_id>/', views.detalle_usuario, name='detalle_usuario'),
    path('usuario/<int:usuario_id>/asignar-grupo/', views.asignar_grupo, name='asignar_grupo'),
    path('usuario/<int:usuario_id>/activar-desactivar/', views.activar_desactivar, name='activar_desactivar'),
    path('crear-usuario/', views.crear_usuario, name='crear_usuario'),
    path('permisos/', views.permisos, name='permisos'),
]
