from django import forms
from django.contrib import admin
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import URLValidator
from django.db import connection
from django.utils import timezone

from notificaciones.services import notificar_revision

from .models import Envio, InstructorProfile, MovimientoEvidencia
from .services import (
    ConflictoEvidencia,
    comprobar_version,
    registrar_movimiento,
    retirar_adjunto_sustituido,
    transaccion_evidencia,
)
from .validators import validar_archivo_evidencia

admin.site.site_header = "GESICOM · SENA"
admin.site.site_title = "GESICOM SENA"
admin.site.index_title = "Administración del sistema"


class EvidenciaAdminForm(forms.ModelForm):
    version_actual = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)

    class Meta:
        model = Envio
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["version_actual"] = self.instance.version
            self.fields["version_actual"].required = True

    def clean(self):
        data = super().clean()
        if self.instance.pk and data.get("version_actual"):
            queryset = Envio.objects.all()
            if connection.in_atomic_block:
                queryset = queryset.select_for_update()
            vigente = queryset.filter(pk=self.instance.pk).first()
            if not vigente:
                raise forms.ValidationError("La evidencia ya no está disponible.")
            try:
                comprobar_version(vigente, data["version_actual"])
            except ConflictoEvidencia as error:
                raise forms.ValidationError(error.messages) from None
        return data

    def clean_archivo_evidencia(self):
        archivo = self.cleaned_data.get("archivo_evidencia")
        if isinstance(archivo, UploadedFile):
            validar_archivo_evidencia(archivo)
        return archivo

    def clean_link_evidencia(self):
        enlace = self.cleaned_data.get("link_evidencia")
        if enlace:
            URLValidator(schemes=["http", "https"])(enlace)
        return enlace


@admin.register(Envio)
class EnvioAdmin(admin.ModelAdmin):
    form = EvidenciaAdminForm
    list_display = ["nombre", "usuario", "proyecto", "fecha_envio", "aprobada", "rechazada", "version"]
    list_select_related = ["usuario", "plazo"]
    list_filter = ["proyecto", "aprobada", "rechazada"]
    search_fields = ["nombre", "usuario__username", "usuario__email"]
    autocomplete_fields = ["usuario", "plazo"]
    list_per_page = 25
    readonly_fields = ["registrado_en", "fecha_envio", "limite_aplicado", "version", "actualizado_en"]

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method != "POST":
            return super().changeform_view(request, object_id, form_url, extra_context)
        with transaccion_evidencia() as nuevos:
            request._gesicom_adjuntos = nuevos
            return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        anterior = Envio.objects.select_for_update().get(pk=obj.pk) if change else None
        cambios = set(form.changed_data) - {"version_actual"}
        if anterior and cambios:
            obj.version = anterior.version + 1
        if not anterior or cambios:
            obj.actualizado_en = timezone.now()
        if obj.archivo_evidencia and not obj.archivo_evidencia._committed:
            getattr(request, "_gesicom_adjuntos", []).append(
                (obj, anterior.archivo_evidencia.name if anterior else None)
            )
        super().save_model(request, obj, form, change)
        if anterior:
            retirar_adjunto_sustituido(obj, anterior.archivo_evidencia.name, anterior.archivo_evidencia.storage)
        if not anterior or cambios:
            accion = MovimientoEvidencia.Accion.ADMINISTRACION if anterior else MovimientoEvidencia.Accion.REGISTRO
            if anterior and anterior.estado != obj.estado:
                accion = MovimientoEvidencia.Accion.REVISION
            registrar_movimiento(
                obj, request.user, accion, "Actualización realizada desde la administración del sistema."
            )
        if anterior and anterior.estado != obj.estado:
            notificar_revision(obj)


@admin.register(MovimientoEvidencia)
class MovimientoEvidenciaAdmin(admin.ModelAdmin):
    list_display = ["envio", "version", "accion", "estado", "actor", "creado_en"]
    list_filter = ["accion", "estado"]
    list_select_related = ["envio", "actor"]
    search_fields = ["envio__nombre", "actor__username"]
    readonly_fields = ["envio", "version", "accion", "estado", "actor", "detalle", "creado_en"]
    list_per_page = 25

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstructorProfile)
class InstructorProfileAdmin(admin.ModelAdmin):
    list_display = ["usuario", "especialidad"]
    list_select_related = ["usuario"]
    autocomplete_fields = ["usuario"]
    search_fields = ["usuario__username", "especialidad"]


# Rol se conserva como tabla histórica; la autorización utiliza auth.Group.
