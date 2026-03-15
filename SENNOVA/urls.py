from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from Gesicom import views as gesicom_views
from instructor import views as usuarios_views
from cuentas import views as cuentas_views

urlpatterns = [

    path('admin/', admin.site.urls),
    path('administrador/', include('ADMIN.urls')),
    path('', usuarios_views.login_view, name='login_root'),
    path('login/', usuarios_views.login_view, name='login'),
    path('logout/', usuarios_views.logout_view, name='logout'),
    path('register/', usuarios_views.register_view, name='register'),
    
    path('home/', gesicom_views.home, name='home'),
    path('usuario/', gesicom_views.role_usuario, name='usuario'),
    path('nosotros/', gesicom_views.nosotros, name='nosotros'),
    path('contacto/', gesicom_views.contacto, name='contacto'),
    path('ayuda/', gesicom_views.ayuda, name='ayuda'),
    path('portal/', gesicom_views.portal, name='portal'),
    
    path('roles/instructor/', gesicom_views.role_instructor, name='role_instructor'),
    path('roles/instructor-table/', gesicom_views.instructor_table, name='instructor_table'),
    path('roles/investigador/', gesicom_views.role_investigador, name='role_investigador'),
    path('roles/dinamizador/', gesicom_views.role_dinamizador, name='role_dinamizador'),
    path('roles/coordinador/', gesicom_views.role_coordinador, name='role_coordinador'),
    
    path('evidencia/', gesicom_views.evidencia, name='evidencia'),
    path('evidencias/', gesicom_views.evidencias_list, name='evidencias_list'),
    path('evidencias/<int:pk>/ver/', gesicom_views.ver_evidencia, name='ver_evidencia'),
    path('evidencias/<int:pk>/set_aprobada/', gesicom_views.set_aprobada, name='set_aprobada'),
    
    path('access-denied/', gesicom_views.access_denied, name='access_denied'),
    path('administracion/', gesicom_views.admin_menu, name='admin_menu'),
    path('proyecciones/', gesicom_views.proyecciones, name='proyecciones'),
    path('reportes/', gesicom_views.reportes, name='reportes'),
    path('reportes.csv', gesicom_views.reportes_csv, name='reportes_csv'),
    path('reportes_trimestrales.csv', gesicom_views.reportes_trimestrales_csv, name='reportes_trimestrales_csv'),
    
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='Registro/password_reset_form.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='Registro/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='Registro/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='Registro/password_reset_complete.html'), name='password_reset_complete'),
    
    # Endpoints AJAX/JSON para flujo de restablecimiento personalizado
    path('api/olvide_password/', cuentas_views.olvide_password, name='olvide_password'),
    path('api/restablecer_password/', cuentas_views.restablecer_password, name='restablecer_password'),
    path('api/debug-tokens/', cuentas_views.debug_tokens, name='debug_tokens'),  # Solo en DEBUG=True
    path('editar_perfil/', gesicom_views.editar_perfil, name='editar_perfil'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
