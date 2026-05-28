from django.urls import path

from apps.briefing import views

app_name = "briefing"

urlpatterns = [
    path("config/", views.BriefingConfigView.as_view(), name="config"),
]
