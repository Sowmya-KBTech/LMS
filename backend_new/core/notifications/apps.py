from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core.notifications'
    verbose_name = 'Notifications & Emails'

    def ready(self):
        import core.notifications.signals  # noqa: F401
