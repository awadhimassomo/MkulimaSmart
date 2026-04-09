from django.urls import path

from . import api_views

app_name = "operations_api"

urlpatterns = [
    path("dashboard/", api_views.OperationsDashboardAPIView.as_view(), name="dashboard"),
    path("sellers/", api_views.InputSellerListCreateAPIView.as_view(), name="seller_list"),
    path("seedling-batches/", api_views.SeedlingBatchListCreateAPIView.as_view(), name="batch_list"),
    path("planting-records/", api_views.PlantingRecordListCreateAPIView.as_view(), name="planting_record_list"),
    path("planting-records/<int:pk>/", api_views.PlantingRecordDetailAPIView.as_view(), name="planting_record_detail"),
    path("planting-records/<int:planting_record_id>/activities/", api_views.FarmActivityListCreateAPIView.as_view(), name="activity_list"),
    path("planting-records/<int:planting_record_id>/input-usage/", api_views.FarmInputUsageListCreateAPIView.as_view(), name="input_usage_list"),
    path("planting-records/<int:planting_record_id>/inspections/", api_views.InspectionLogListCreateAPIView.as_view(), name="inspection_list"),
    path("exports/kikapu/", api_views.KikapuExportAPIView.as_view(), name="kikapu_export"),
]
