from django.urls import path

from apps.recall.views import recall_related, recall_search, recall_status

urlpatterns = [
    path("", recall_search),
    path("related/", recall_related),
    path("status/", recall_status),
]
