from django.apps import AppConfig


class DoorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "door"

    def ready(self):
        # подключаем сигналы, которые создают уведомления
        from . import signals   # noqa: F401