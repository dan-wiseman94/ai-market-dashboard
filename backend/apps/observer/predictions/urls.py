from django.urls import path

from apps.observer.predictions.views import AIViewForTickerView, DivergencesView

urlpatterns = [
    path("ai-view/", AIViewForTickerView.as_view(), name="predictions-ai-view"),
    path("divergences/", DivergencesView.as_view(), name="predictions-divergences"),
]
