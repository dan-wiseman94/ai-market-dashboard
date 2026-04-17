from django.urls import path

from . import views

app_name = "secrets_app"

urlpatterns = [
    path("authorize/", views.schwab_authorize, name="authorize"),
    path("callback/", views.schwab_callback, name="callback"),
    path("status/", views.schwab_status, name="status"),
]
