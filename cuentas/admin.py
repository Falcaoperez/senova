from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q

from .correos import encolar_aviso_cambio, invalidar_recuperaciones
from .forms import validar_correo_unico
from .models import CorreoSeguridad, PasswordResetToken, RegistroSeguridad, SesionUsuario
from .sesiones import cerrar_sesiones

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


class CambioPasswordAdminSeguro(AdminPasswordChangeForm):
    def save(self, commit=True):
        with transaction.atomic():
            usuario = super().save(commit=False)
            if commit:
                vigente = User.objects.select_for_update().get(pk=usuario.pk)
                vigente.password = usuario.password
                vigente.save(update_fields=["password"])
                usuario = self.user = vigente
                invalidar_recuperaciones(usuario)
                cerrar_sesiones(usuario)
                encolar_aviso_cambio(usuario)
            return usuario


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = CambioUsuarioAdmin
    add_form = AltaUsuarioAdmin
    change_password_form = CambioPasswordAdminSeguro
    list_display = ["username", "email", "first_name", "last_name", "is_active", "is_staff"]
    add_fieldsets = ((None, {"classes": ["wide"], "fields": ["username", "email", "password1", "password2"]}),)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.exclude(
                Q(is_superuser=True) | Q(is_staff=True) | Q(groups__name="administrador")
            ).distinct()
        return queryset

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            fields += ("is_staff", "is_superuser", "groups", "user_permissions")
        return fields

    def get_form(self, request, obj=None, **kwargs):
        original = super().get_form(request, obj, **kwargs)

        class FormularioProtegido(original):
            def clean(self):
                data = super().clean()
                if self.instance.pk == request.user.pk:
                    for name in ("is_active", "is_staff", "is_superuser"):
                        if getattr(request.user, name) and data.get(name) is False:
                            self.add_error(name, "No puedes retirar tu propio acceso administrativo.")
                return data

        return FormularioProtegido

    def save_model(self, request, obj, form, change):
        anterior = User.objects.select_for_update().get(pk=obj.pk) if change else None
        if anterior:
            # La contraseña se cambia por su formulario específico; no restaurar un hash obsoleto.
            obj.password = anterior.password
        super().save_model(request, obj, form, change)
        if not anterior:
            return
        sensible = (anterior.email.casefold(), anterior.username, anterior.password) != (
            obj.email.casefold(),
            obj.username,
            obj.password,
        )
        if sensible or (anterior.is_active and not obj.is_active):
            invalidar_recuperaciones(obj)
            conservar = request.session.session_key if obj.pk == request.user.pk and obj.is_active else None
            cerrar_sesiones(obj, conservar=conservar)
        if sensible:
            encolar_aviso_cambio(obj, anterior.email)
        if form.changed_data:
            RegistroSeguridad.objects.create(actor=request.user, accion="admin:cuenta", ruta=request.path[:255])

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or obj.pk != request.user.pk)

    def delete_queryset(self, request, queryset):
        if queryset.filter(pk=request.user.pk).exists():
            raise PermissionDenied("No puedes eliminar tu propia cuenta administrativa.")
        super().delete_queryset(request, queryset)


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
