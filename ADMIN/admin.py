"""Los grupos nativos comparten la política de permisos de GESICOM."""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters

from .permisos import ROLES_SISTEMA, GrupoNativoForm, grupo_protegido, guardar_grupo_nativo


class GrupoSeguroAdmin(GroupAdmin):
    form = GrupoNativoForm
    list_per_page = 25

    def get_fields(self, request, obj=None):
        if obj and not self.has_change_permission(request, obj):
            return ["name", "permissions"]
        return ["name", "permissions", "revision_actual", "contrasena_actual"]

    def get_readonly_fields(self, request, obj=None):
        return ["name"] if obj and obj.name in ROLES_SISTEMA else []

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)

        class FormularioDePeticion(base):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, usuario=request.user, **form_kwargs)

        return FormularioDePeticion

    def has_change_permission(self, request, obj=None):
        permitido = super().has_change_permission(request, obj)
        return permitido and (obj is None or request.user.is_superuser or not grupo_protegido(obj))

    def has_delete_permission(self, request, obj=None):
        permitido = super().has_delete_permission(request, obj)
        return permitido and (
            obj is None or (obj.name not in ROLES_SISTEMA and (request.user.is_superuser or not grupo_protegido(obj)))
        )

    def delete_queryset(self, request, queryset):
        if any(not self.has_delete_permission(request, obj) for obj in queryset):
            raise PermissionDenied
        super().delete_queryset(request, queryset)

    @method_decorator(sensitive_post_parameters("contrasena_actual"))
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        actual = guardar_grupo_nativo(request.user, form.cleaned_data, pk=obj.pk if change else None)
        for campo in obj._meta.concrete_fields:
            setattr(obj, campo.attname, getattr(actual, campo.attname))
        obj._state = actual._state

    def save_related(self, request, form, formsets, change):
        for formset in formsets:
            self.save_formset(request, form, formset, change=change)


if admin.site.is_registered(Group):
    admin.site.unregister(Group)
admin.site.register(Group, GrupoSeguroAdmin)
