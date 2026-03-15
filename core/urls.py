"""
Rutas (URLconf) del proyecto SENNOVA.

`urlpatterns` asocia las rutas HTTP con las vistas correspondientes.
Los comentarios y nombres están en español para facilitar la exposición:
- Las rutas principales (`login`, `register`, `home`, etc.) apuntan a vistas
    definidas en las apps `INSTRUCTOR` y `GESICOM`.
- También hay rutas para el panel de administración y el flujo de
    recuperación de contraseña (password reset) usando las vistas de Django.

En desarrollo se añaden también las rutas para servir archivos `media`.
"""
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from Gesicom import views as gesicom_views
from instructor import views as usuarios_views
from cuentas import views as cuentas_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', usuarios_views.login_view, name='login_root'),
    path('login/', usuarios_views.login_view, name='login'),
    path('register/', usuarios_views.register_view, name='register'),
    path('usuario/', usuarios_views.panel_usuario, name='usuario'),
    path('logout/', usuarios_views.logout_view, name='logout'),
    path('home/', gesicom_views.home, name='home'),
    path('nosotros/', gesicom_views.nosotros, name='nosotros'),
    path('contacto/', gesicom_views.contacto, name='contacto'),
    path('ayuda/', gesicom_views.ayuda, name='ayuda'),
    path('portal/', gesicom_views.portal, name='portal'),
    
    path('roles/instructor/', gesicom_views.role_instructor, name='role_instructor'),
    path('roles/instructor-table/', gesicom_views.tabla_instructor, name='instructor_table'),
    path('roles/investigador/', gesicom_views.role_investigador, name='role_investigador'),
    path('roles/dinamizador/', gesicom_views.role_dinamizador, name='role_dinamizador'),
    path('roles/coordinador/', gesicom_views.role_coordinador, name='role_coordinador'),
    path('access-denied/', gesicom_views.access_denied, name='access_denied'),
    # Panel de administración
    path('administracion/', gesicom_views.admin_menu, name='admin_menu'),
    path('proyecciones/', gesicom_views.proyecciones, name='proyecciones'),
    # Password reset
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='Registro/password_reset_form.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='Registro/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='Registro/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='Registro/password_reset_complete.html'), name='password_reset_complete'),
    # Endpoints AJAX/JSON para flujo de restablecimiento personalizado
    path('api/olvide_password/', cuentas_views.olvide_password, name='olvide_password'),
    path('api/restablecer_password/', cuentas_views.restablecer_password, name='restablecer_password'),
]

# Servir archivos `media` (subidos por usuarios) únicamente en desarrollo.
# En producción estos archivos deben servirse mediante el servidor web o CDN.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
