from django.urls import path

from apps.predictions.views import AIViewForTickerView

urlpatterns = [
    path("ai-view/", AIViewForTickerView.as_view(), name="predictions-ai-view"),
]
