from django.contrib import admin
from django.contrib.auth.models import User
from .models import PasswordResetToken


# Desregistrar el UserAdmin por defecto de Django para usar nuestro personalizado
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    readonly_fields = ('date_joined', 'last_login')
    fieldsets = (
        ('Información de Cuenta', {'fields': ('username', 'email')}),
        ('Información Personal', {'fields': ('first_name', 'last_name')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas Importantes', {'fields': ('date_joined', 'last_login'), 'classes': ('collapse',)}),
    )


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'creado_en', 'expira_en', 'utilizado', 'es_valido')
    list_filter = ('utilizado', 'creado_en', 'expira_en')
    search_fields = ('usuario__email', 'usuario__username', 'token')
    readonly_fields = ('token', 'creado_en', 'expira_en')
    
    def es_valido(self, obj):
        return obj.es_valido()
    es_valido.boolean = True
    es_valido.short_description = "¿Válido?"
