from django.urls import path

from . import views

app_name = "market"

urlpatterns = [
    path("quotes/", views.quotes, name="quotes"),
    path("ohlc/", views.ohlc, name="ohlc"),
    path("positions/", views.positions, name="positions"),
    path("context/", views.context, name="context"),
    path("chain/", views.chain, name="chain"),
]
