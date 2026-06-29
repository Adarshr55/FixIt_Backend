from django.apps import AppConfig


class ServicesConfig(AppConfig):
    name = 'services'

    def ready(self):
        # trigger ai_engine to embed categories and services on save
        from ai_engine.signals import connect_signals
        connect_signals()
