from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .forms import validar_correo_unico
from .models import CorreoSeguridad, PasswordResetToken, RegistroSeguridad, SesionUsuario

User = get_user_model()


class CambioUsuarioAdmin(UserChangeForm):
    def clean_email(self):
        correo = self.cleaned_data.get("email", "")
        return validar_correo_unico(correo, self.instance.pk) if correo else correo


class AltaUsuarioAdmin(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        fields = ["username", "email"]

    def clean_email(self):
        return validar_correo_unico(self.cleaned_data["email"])


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = CambioUsuarioAdmin
    add_form = AltaUsuarioAdmin
    list_display = ["username", "email", "first_name", "last_name", "is_active", "is_staff"]
    add_fieldsets = ((None, {"classes": ["wide"], "fields": ["username", "email", "password1", "password2"]}),)


@admin.register(PasswordResetToken)
class RecuperacionAdmin(admin.ModelAdmin):
    list_display = ["id", "usuario", "creado_en", "expira_en", "intentos", "utilizado"]
    fields = ["usuario", "creado_en", "expira_en", "intentos", "verificado_en", "utilizado"]
    readonly_fields = fields
    list_filter = ["utilizado"]
    search_fields = ["usuario__username", "usuario__email"]
    list_select_related = ["usuario"]

    def has_add_permission(self, request):
        return False


@admin.register(RegistroSeguridad)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ["accion", "actor", "direccion_ip", "creado_en"]
    list_select_related = ["actor"]
    readonly_fields = ["accion", "actor", "direccion_ip", "ruta", "creado_en"]
    list_filter = ["accion"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CorreoSeguridad)
class CorreoSeguridadAdmin(admin.ModelAdmin):
    list_display = ["id", "tipo", "usuario", "estado", "intentos", "creado_en"]
    list_filter = ["tipo", "estado"]
    list_select_related = ["usuario"]
    fields = [
        "usuario",
        "destinatario",
        "tipo",
        "estado",
        "intentos",
        "creado_en",
        "proximo_intento",
        "enviado_en",
        "ultimo_error",
    ]
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SesionUsuario)
class SesionUsuarioAdmin(admin.ModelAdmin):
    list_display = ["usuario", "creada_en", "ultimo_uso", "direccion_ip"]
    list_select_related = ["usuario"]
    fields = ["usuario", "creada_en", "ultimo_uso", "direccion_ip", "agente"]
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
