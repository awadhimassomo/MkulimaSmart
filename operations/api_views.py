from django.db.models import Count
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FarmActivity, FarmInputUsage, InputSeller, InspectionLog, PlantingRecord, SeedlingBatch
from .serializers import (
    FarmActivitySerializer,
    FarmInputUsageSerializer,
    InputSellerSerializer,
    InspectionLogSerializer,
    PlantingRecordSerializer,
    SeedlingBatchSerializer,
)


class InputSellerListCreateAPIView(generics.ListCreateAPIView):
    queryset = InputSeller.objects.all().order_by("seller_name")
    serializer_class = InputSellerSerializer
    permission_classes = [permissions.IsAuthenticated]


class SeedlingBatchListCreateAPIView(generics.ListCreateAPIView):
    queryset = SeedlingBatch.objects.select_related("seller").all()
    serializer_class = SeedlingBatchSerializer
    permission_classes = [permissions.IsAuthenticated]


class PlantingRecordListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = PlantingRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = PlantingRecord.objects.select_related("farmer", "farm", "seedling_batch")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(farmer=self.request.user)


class PlantingRecordDetailAPIView(generics.RetrieveAPIView):
    serializer_class = PlantingRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = PlantingRecord.objects.select_related("farmer", "farm", "seedling_batch")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(farmer=self.request.user)


class FarmActivityListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = FarmActivitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = FarmActivity.objects.select_related("planting_record", "created_by")
        planting_record_id = self.kwargs.get("planting_record_id")
        if planting_record_id:
            queryset = queryset.filter(planting_record_id=planting_record_id)
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(planting_record__farmer=self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class FarmInputUsageListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = FarmInputUsageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = FarmInputUsage.objects.select_related("planting_record")
        planting_record_id = self.kwargs.get("planting_record_id")
        if planting_record_id:
            queryset = queryset.filter(planting_record_id=planting_record_id)
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(planting_record__farmer=self.request.user)


class InspectionLogListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = InspectionLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = InspectionLog.objects.select_related("planting_record", "visited_by")
        planting_record_id = self.kwargs.get("planting_record_id")
        if planting_record_id:
            queryset = queryset.filter(planting_record_id=planting_record_id)
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(planting_record__farmer=self.request.user)

    def perform_create(self, serializer):
        serializer.save(visited_by=self.request.user)


class KikapuExportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = PlantingRecord.objects.select_related("farm", "seedling_batch")
        if not request.user.is_staff:
            queryset = queryset.filter(farmer=request.user)

        payload = [
            {
                "planting_cycle_id": record.planting_cycle_id,
                "crop_type": record.crop_type,
                "planting_date": record.planting_date,
                "expected_harvest_date": record.expected_harvest_date,
                "expected_quantity": record.expected_quantity or record.expected_yield,
                "expected_yield": record.expected_yield,
                "farm_location": record.farm_location or record.location or record.farm.location,
                "region": record.region,
                "farmer_name": record.farmer_name or record.farmer.get_full_name(),
                "farmer_phone": record.farmer_phone or record.farmer.phone_number,
                "farm_name": record.farm_name or record.farm.name,
                "verification_status": record.verification_status,
                "farm_id": record.farm_id,
                "farmer_id": record.farmer_id,
                "seedling_batch_id": record.seedling_batch.seedling_batch_id if record.seedling_batch else None,
            }
            for record in queryset
        ]
        return Response({"count": len(payload), "results": payload})


class OperationsDashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        base_records = PlantingRecord.objects.select_related("farm")
        if not request.user.is_staff:
            base_records = base_records.filter(farmer=request.user)

        return Response(
            {
                "input_sellers": InputSeller.objects.count(),
                "seedling_batches": SeedlingBatch.objects.count(),
                "planting_records": base_records.count(),
                "upcoming_expected_harvests": base_records.filter(expected_harvest_date__gte=timezone.now().date()).count(),
                "farms_not_verified": base_records.exclude(verification_status="verified").count(),
                "recent_activities": FarmActivity.objects.count(),
                "records_by_crop": list(base_records.values("crop_type").annotate(total=Count("id")).order_by("-total")),
            }
        )
