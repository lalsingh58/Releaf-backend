from django.apps import AppConfig


class ActionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.actions"
    verbose_name = "Green Actions"

    def ready(self):
        from . import signals  # noqa: F401
