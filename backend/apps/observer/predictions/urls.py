from django.urls import path

from apps.observer.predictions.views import (
    AIViewForTickerView,
    DivergencesView,
    PredictionDetailView,
    PredictionListView,
    PredictionStatsView,
)

urlpatterns = [
    path("", PredictionListView.as_view(), name="predictions-list"),
    path("stats/", PredictionStatsView.as_view(), name="predictions-stats"),
    path("ai-view/", AIViewForTickerView.as_view(), name="predictions-ai-view"),
    path("divergences/", DivergencesView.as_view(), name="predictions-divergences"),
    path("<int:pk>/", PredictionDetailView.as_view(), name="predictions-detail"),
]
