from django.apps import AppConfig


class NotificacionesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notificaciones"
    verbose_name = "Comunicación y plazos"

    def ready(self):
        import notificaciones.signals  # noqa: F401
