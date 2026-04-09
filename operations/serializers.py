from rest_framework import serializers

from .models import FarmActivity, FarmInputUsage, InputSeller, InspectionLog, PlantingRecord, SeedlingBatch


class InputSellerSerializer(serializers.ModelSerializer):
    class Meta:
        model = InputSeller
        fields = "__all__"


class SeedlingBatchSerializer(serializers.ModelSerializer):
    scan_url = serializers.CharField(source="get_absolute_scan_url", read_only=True)

    class Meta:
        model = SeedlingBatch
        fields = "__all__"


class FarmActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = FarmActivity
        fields = "__all__"
        read_only_fields = ["created_by", "created_at"]


class FarmInputUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = FarmInputUsage
        fields = "__all__"


class InspectionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionLog
        fields = "__all__"
        read_only_fields = ["visited_by", "created_at"]


class PlantingRecordSerializer(serializers.ModelSerializer):
    activities = FarmActivitySerializer(many=True, read_only=True)
    input_usages = FarmInputUsageSerializer(many=True, read_only=True)
    inspection_logs = InspectionLogSerializer(many=True, read_only=True)

    class Meta:
        model = PlantingRecord
        fields = "__all__"
        read_only_fields = ["planting_cycle_id", "created_at", "updated_at"]
