from django.urls import include, path

from keycafe_api.views import frontend_index, health

urlpatterns = [
    path("", frontend_index, name="frontend"),
    path("api/", include("keycafe_api.urls")),
    path("healthz/", health, name="health"),
]
