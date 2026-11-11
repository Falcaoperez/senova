from django.apps import AppConfig


class GesicomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "Gesicom"

    def ready(self):
        import Gesicom.signals  # noqa: F401
