from django.urls import path

from apps.aieval import views

app_name = "aieval"

urlpatterns = [
    path("runs/", views.EvalRunListView.as_view(), name="run-list"),
    path("runs/latest/", views.EvalRunLatestView.as_view(), name="run-latest"),
]
