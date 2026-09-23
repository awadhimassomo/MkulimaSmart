from django.apps import AppConfig

class EcopConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ecop'
    
    def ready(self):
        # Import signals to register them
        import ecop.signals  # noqa
