from django.contrib import admin

from .forms import NovedadForm, PlazoReporteForm
from .models import CorreoPendiente, Notificacion, Novedad, PlazoReporte
from .services import anunciar_plazo, publicar_novedad


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

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creado_por = request.user
        elif "fecha_limite" in form.changed_data:
            obj.version += 1
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if form.instance.activo:
            anunciar_plazo(form.instance)

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
