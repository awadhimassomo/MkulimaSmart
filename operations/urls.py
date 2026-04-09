from django.urls import path

from . import views

app_name = "operations"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sellers/", views.seller_list, name="seller_list"),
    path("sellers/new/", views.seller_create, name="seller_create"),
    path("seedling-batches/", views.batch_list, name="batch_list"),
    path("seedling-batches/new/", views.batch_create, name="batch_create"),
    path("seedling-batches/<int:pk>/", views.batch_detail, name="batch_detail"),
    path("seedling-batches/<int:pk>/qr/", views.batch_qr_print, name="batch_qr_print"),
    path("seedling-batches/<int:pk>/qr.png", views.batch_qr_image, name="batch_qr_image"),
    path("seedling-batches/scan/<str:seedling_batch_id>/", views.batch_scan, name="batch_scan"),
    path("planting-records/", views.planting_record_list, name="planting_record_list"),
    path("planting-records/intake/<str:seedling_batch_id>/", views.planting_record_qr_intake, name="planting_qr_intake"),
    path("planting-records/new/", views.planting_record_create, name="planting_create"),
    path("planting-records/from-batch/<str:seedling_batch_id>/", views.planting_record_create, name="planting_create_from_batch"),
    path("planting-records/<int:pk>/", views.planting_record_detail, name="planting_record_detail"),
    path("planting-records/<int:pk>/activities/new/", views.add_activity, name="add_activity"),
    path("planting-records/<int:pk>/inputs/new/", views.add_input_usage, name="add_input_usage"),
    path("planting-records/<int:pk>/inspections/new/", views.add_inspection, name="add_inspection"),
]
