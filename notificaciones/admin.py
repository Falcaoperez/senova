from django.contrib import admin

from .forms import NovedadForm, PlazoReporteForm
from .models import CorreoPendiente, Notificacion, Novedad, PlazoReporte
from .plazos import guardar_plazo
from .services import publicar_novedad


@admin.register(Novedad)
class NovedadAdmin(admin.ModelAdmin):
    form = NovedadForm

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creada_por = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not change:
            publicar_novedad(form.instance)

    list_display = ["titulo", "creada_por", "publicada_en"]
    search_fields = ["titulo"]


@admin.register(PlazoReporte)
class PlazoReporteAdmin(admin.ModelAdmin):
    search_fields = ["titulo", "proyecto"]
    form = PlazoReporteForm
    readonly_fields = ["version", "revision", "actualizado_en", "creado_por", "creado_en"]
    list_per_page = 25

    def save_model(self, request, obj, form, change):
        guardado, _, _ = guardar_plazo(request.user, form.cleaned_data, pk=obj.pk if change else None, nativo=True)
        for field in obj._meta.concrete_fields:
            setattr(obj, field.attname, getattr(guardado, field.attname))
        obj._state = guardado._state

    def save_related(self, request, form, formsets, change):
        # El servicio ya guardó los grupos y anunció una sola vez la revisión actual.
        for formset in formsets:
            self.save_formset(request, form, formset, change=change)

    list_display = ["titulo", "proyecto", "fecha_limite", "activo"]
    list_filter = ["activo", "proyecto"]


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ["titulo", "usuario", "tipo", "creada_en", "leida_en"]
    list_select_related = ["usuario"]
    list_filter = ["tipo"]
    search_fields = ["titulo", "usuario__username"]


@admin.register(CorreoPendiente)
class CorreoAdmin(admin.ModelAdmin):
    list_display = ["notificacion_id", "estado", "intentos", "proximo_intento"]
    list_filter = ["estado"]
    readonly_fields = ["ultimo_error"]
