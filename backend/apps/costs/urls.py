from django.urls import path

from . import views

urlpatterns = [
    path("today/", views.costs_today, name="costs-today"),
]
