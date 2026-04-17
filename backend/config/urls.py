from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/schwab/", include("apps.secrets.urls")),
    path("api/market/", include("apps.market.urls")),
    path("api/costs/", include("apps.costs.urls")),
    path("api/", include("apps.profiles.urls")),
    path("api/", include("apps.snapshots.urls")),
    path("api/", include("apps.threads.urls")),
]
