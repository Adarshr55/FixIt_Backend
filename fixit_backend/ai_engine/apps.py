from django.apps import AppConfig


class AiEngineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_engine'

    def ready(self):
        """Connect signals when Django starts."""
        from .signals import connect_signals
        connect_signals()
