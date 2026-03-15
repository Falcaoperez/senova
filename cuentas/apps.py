# Configuración de la app 'cuentas' (nombre y ajustes por defecto).
from django.apps import AppConfig


class CuentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cuentas'
