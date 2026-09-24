from django.urls import path

from . import views

urlpatterns = [
    path("config/", views.config, name="config"),
    path("groups/", views.groups, name="groups"),
    path("keys/", views.keys, name="keys"),
]
