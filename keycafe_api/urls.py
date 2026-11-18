from django.urls import path

from . import views

urlpatterns = [
    path("config/", views.config, name="config"),
    path("groups/", views.groups, name="groups"),
    path("groups/<str:group_id>/", views.group_detail, name="group-detail"),
    path("inventory/", views.inventory, name="inventory"),
    path("keys/", views.keys, name="keys"),
]
