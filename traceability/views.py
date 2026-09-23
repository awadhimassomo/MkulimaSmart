from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from operations.models import SeedlingBatch
from website.models import Farm

from .models import HarvestTraceLot, TraceabilityPlanting
from .serializers import (
    HarvestLotSerializer,
    HarvestLotUpdateSerializer,
    InternalPlantingDetailSerializer,
    PublicHarvestTraceSerializer,
    SupplierResolveSerializer,
    TraceabilityPlantingCreateSerializer,
)


class SupplierQRResolveAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SupplierResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        scanned_code = serializer.validated_data["scanned_code"].strip()
        supplier_batch_id = scanned_code.split("|", 1)[0]
        batch = SeedlingBatch.objects.select_related("seller").filter(seedling_batch_id=supplier_batch_id).first()
        if not batch:
            return Response(
                {
                    "status": "not_found",
                    "message": "Supplier traceability code was not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "status": "success",
                "supplier_batch_id": batch.seedling_batch_id,
                "supplier_name": batch.seller.seller_name,
                "crop_type": batch.seedling_type,
                "variety": batch.variety,
                "source_location": batch.seller.location,
                "organic_status": None,
                "batch_reference": batch.source_name,
                "batch_date": batch.batch_date,
                "message": "Supplier traceability details resolved successfully.",
            }
        )


class TraceabilityPlantingCreateAPIView(generics.CreateAPIView):
    serializer_class = TraceabilityPlantingCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        farm_queryset = Farm.objects.all()
        if not self.request.user.is_staff:
            farm_queryset = farm_queryset.filter(owner=self.request.user)
        context["farm_queryset"] = farm_queryset
        return context


class TraceabilityPlantingDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = InternalPlantingDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = TraceabilityPlanting.objects.select_related("farm", "farmer", "source_batch", "source_batch__seller").prefetch_related()

    def get_queryset(self):
        queryset = TraceabilityPlanting.objects.select_related(
            "farm",
            "farmer",
            "source_batch",
            "source_batch__seller",
            "harvest_lot",
        )
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(farmer=self.request.user)

    def patch(self, request, *args, **kwargs):
        planting = self.get_object()
        mutable_fields = {
            "crop_type",
            "variety",
            "quantity_planted",
            "unit",
            "planting_date",
            "farming_method",
            "area_planted",
            "area_unit",
            "soil_notes",
            "notes",
            "expected_days_to_harvest",
        }
        for key in list(request.data.keys()):
            if key not in mutable_fields:
                return Response(
                    {"status": "error", "message": f"Field '{key}' cannot be updated through this endpoint."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        for key, value in request.data.items():
            setattr(planting, key, value)
        planting.save()
        data = InternalPlantingDetailSerializer(planting).data
        data["status"] = "success"
        data["message"] = "Planting record updated successfully."
        return Response(data)


class HarvestLotCreateOrUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, planting_id):
        planting_qs = TraceabilityPlanting.objects.select_related("harvest_lot")
        if not request.user.is_staff:
            planting_qs = planting_qs.filter(farmer=request.user)
        planting = planting_qs.filter(id=planting_id).first()
        if not planting:
            return Response({"status": "not_found", "message": "Planting record not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = HarvestLotUpdateSerializer(instance=planting.harvest_lot, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        harvest_lot = serializer.save()
        data = HarvestLotSerializer(harvest_lot).data
        data["status"] = "success"
        data["message"] = "Harvest traceability lot updated successfully."
        return Response(data)


class HarvestPublicLookupAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, trace_code):
        lot = HarvestTraceLot.objects.select_related("planting", "planting__farm", "planting__source_batch", "planting__source_batch__seller").filter(trace_code=trace_code).first()
        if not lot or not lot.is_public or lot.status != "published":
            return Response(
                {
                    "status": "not_available",
                    "message": "This harvest traceability record is not available for public viewing.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        data = PublicHarvestTraceSerializer(lot).data
        data["status"] = "success"
        return Response(data)


class HarvestQRCodeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, trace_code):
        lot_qs = HarvestTraceLot.objects.select_related("planting")
        if not request.user.is_staff:
            lot_qs = lot_qs.filter(planting__farmer=request.user)
        lot = lot_qs.filter(trace_code=trace_code).first()
        if not lot:
            return Response({"status": "not_found", "message": "Harvest traceability code not found."}, status=status.HTTP_404_NOT_FOUND)

        if not lot.qr_code:
            lot.ensure_qr_code()
            lot.save(update_fields=["qr_code"])

        return Response(
            {
                "status": "success",
                "trace_code": lot.trace_code,
                "public_trace_url": lot.get_public_url(),
                "qr_image_url": lot.qr_code.url if lot.qr_code else None,
                "message": "Harvest QR details generated successfully.",
            }
        )
