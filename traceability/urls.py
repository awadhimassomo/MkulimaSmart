from django.urls import path

from . import views

app_name = "traceability"

urlpatterns = [
    path("supplier/resolve/", views.SupplierQRResolveAPIView.as_view(), name="supplier_resolve"),
    path("plantings/", views.TraceabilityPlantingCreateAPIView.as_view(), name="planting_create"),
    path("plantings/<int:pk>/", views.TraceabilityPlantingDetailAPIView.as_view(), name="planting_detail"),
    path("plantings/<int:planting_id>/harvest/", views.HarvestLotCreateOrUpdateAPIView.as_view(), name="planting_harvest"),
    path("harvest/<str:trace_code>/public/", views.HarvestPublicLookupAPIView.as_view(), name="harvest_public_lookup"),
    path("harvest/<str:trace_code>/qr/", views.HarvestQRCodeAPIView.as_view(), name="harvest_qr"),
]
