from django.urls import path

from apps.observer.briefing import views

app_name = "briefing"

urlpatterns = [
    path("", views.BriefingListView.as_view(), name="list"),
    path("latest/", views.BriefingLatestView.as_view(), name="latest"),
    path("run/", views.BriefingRunNowView.as_view(), name="run"),
    path("config/", views.BriefingConfigView.as_view(), name="config"),
]
