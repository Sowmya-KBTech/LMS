from django.apps import AppConfig


class MessagingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules.messaging'
    verbose_name = 'Messaging (parent messages & chat)'
