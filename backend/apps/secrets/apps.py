from django.apps import AppConfig


class SecretsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.secrets"
    label = "secrets_app"  # "secrets" would collide with Python's stdlib
