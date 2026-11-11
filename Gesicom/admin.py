from django.contrib import admin

from .models import Envio, InstructorProfile

admin.site.site_header = "GESICOM · SENA"
admin.site.site_title = "GESICOM SENA"
admin.site.index_title = "Administración del sistema"


@admin.register(Envio)
class EnvioAdmin(admin.ModelAdmin):
    list_display = ["nombre", "usuario", "proyecto", "fecha_envio", "aprobada", "rechazada"]
    list_select_related = ["usuario", "plazo"]
    list_filter = ["proyecto", "aprobada", "rechazada"]
    search_fields = ["nombre", "usuario__username", "usuario__email"]
    autocomplete_fields = ["usuario", "plazo"]
    list_per_page = 25
    readonly_fields = ["registrado_en", "fecha_envio", "limite_aplicado"]


@admin.register(InstructorProfile)
class InstructorProfileAdmin(admin.ModelAdmin):
    list_display = ["usuario", "especialidad"]
    list_select_related = ["usuario"]
    autocomplete_fields = ["usuario"]
    search_fields = ["usuario__username", "especialidad"]


# Rol se conserva como tabla histórica; la autorización utiliza auth.Group.
