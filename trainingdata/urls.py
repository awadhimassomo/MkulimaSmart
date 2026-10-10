from django.urls import path

from . import views

app_name = "training_data"

urlpatterns = [
    path("", views.station, name="station"),
    path("<int:pk>/save/", views.save, name="save"),
    path("dataset/", views.dataset, name="dataset"),
    path("dataset/export/", views.export, name="export"),
]
