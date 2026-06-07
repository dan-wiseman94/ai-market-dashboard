from django.urls import path

from apps.analytics import aieval_views as views

app_name = "aieval"

urlpatterns = [
    path("runs/", views.EvalRunListView.as_view(), name="run-list"),
    path("runs/latest/", views.EvalRunLatestView.as_view(), name="run-latest"),
]
