from rest_framework import serializers

from operations.models import SeedlingBatch

from .models import HarvestTraceLot, TraceabilityPlanting, estimate_harvest_window, estimate_yield


class SupplierResolveSerializer(serializers.Serializer):
    scanned_code = serializers.CharField()


class TraceabilityPlantingCreateSerializer(serializers.ModelSerializer):
    supplier_batch_id = serializers.CharField(write_only=True, required=False, allow_blank=True)
    farm_id = serializers.IntegerField(write_only=True)
    harvest_trace_code = serializers.CharField(read_only=True)
    qr_token_or_payload = serializers.CharField(read_only=True)
    public_trace_url = serializers.CharField(read_only=True)
    forecast_summary = serializers.JSONField(read_only=True)

    class Meta:
        model = TraceabilityPlanting
        fields = [
            "id",
            "farm_id",
            "supplier_batch_id",
            "supplier_trace_code",
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
            "estimated_yield",
            "estimated_yield_unit",
            "harvest_trace_code",
            "qr_token_or_payload",
            "public_trace_url",
            "forecast_summary",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        request = self.context["request"]
        farm_id = attrs.pop("farm_id")
        farm = self.context["farm_queryset"].filter(id=farm_id).first()
        if not farm:
            raise serializers.ValidationError({"farm_id": "Farm not found or not accessible."})
        attrs["farm"] = farm

        supplier_batch_id = attrs.pop("supplier_batch_id", "") or attrs.get("supplier_trace_code", "")
        source_batch = None
        if supplier_batch_id:
            source_batch = SeedlingBatch.objects.filter(seedling_batch_id=supplier_batch_id).first()
            if not source_batch:
                raise serializers.ValidationError({"supplier_batch_id": "Supplier batch was not found."})
            attrs["supplier_trace_code"] = source_batch.seedling_batch_id
        attrs["source_batch"] = source_batch
        attrs["farmer"] = request.user
        return attrs

    def create(self, validated_data):
        if not validated_data.get("expected_days_to_harvest"):
            days, start, end = estimate_harvest_window(
                validated_data.get("crop_type", ""),
                validated_data.get("variety", ""),
                validated_data["planting_date"],
            )
            validated_data["expected_days_to_harvest"] = days
            validated_data["expected_harvest_start"] = start
            validated_data["expected_harvest_end"] = end
        else:
            days, start, end = estimate_harvest_window(
                validated_data.get("crop_type", ""),
                validated_data.get("variety", ""),
                validated_data["planting_date"],
                override_days=validated_data["expected_days_to_harvest"],
            )
            validated_data["expected_harvest_start"] = start
            validated_data["expected_harvest_end"] = end

        if not validated_data.get("estimated_yield"):
            validated_data["estimated_yield"] = estimate_yield(
                validated_data.get("quantity_planted"),
                validated_data.get("area_planted"),
            )
        if not validated_data.get("estimated_yield_unit"):
            validated_data["estimated_yield_unit"] = "kg"

        validated_data["prediction_summary"] = {
            "expected_days_to_harvest": validated_data.get("expected_days_to_harvest"),
            "expected_harvest_start": validated_data.get("expected_harvest_start").isoformat() if validated_data.get("expected_harvest_start") else None,
            "expected_harvest_end": validated_data.get("expected_harvest_end").isoformat() if validated_data.get("expected_harvest_end") else None,
            "estimated_yield": str(validated_data.get("estimated_yield")),
            "estimated_yield_unit": validated_data.get("estimated_yield_unit"),
        }

        planting = TraceabilityPlanting.objects.create(**validated_data)
        harvest_lot = HarvestTraceLot.objects.create(planting=planting)
        planting._traceability_harvest_lot = harvest_lot
        return planting

    def to_representation(self, instance):
        data = super().to_representation(instance)
        harvest_lot = getattr(instance, "_traceability_harvest_lot", None) or getattr(instance, "harvest_lot", None)
        data["status"] = "success"
        data["message"] = "Planting record created successfully."
        data["planting_id"] = instance.id
        data["harvest_trace_code"] = harvest_lot.trace_code
        data["qr_token_or_payload"] = harvest_lot.trace_code
        data["public_trace_url"] = harvest_lot.get_public_url()
        data["created_at"] = instance.created_at
        data["forecast_summary"] = instance.prediction_summary
        return data


class HarvestLotUpdateSerializer(serializers.ModelSerializer):
    publish = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = HarvestTraceLot
        fields = [
            "harvest_date",
            "actual_output_quantity",
            "actual_output_unit",
            "certifications",
            "public_message",
            "publish",
        ]

    def update(self, instance, validated_data):
        publish = validated_data.pop("publish", False)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if publish:
            instance.is_public = True
            instance.status = "published"
        instance.save()
        planting = instance.planting
        planting.status = "harvested"
        planting.save(update_fields=["status", "updated_at"])
        return instance


class HarvestLotSerializer(serializers.ModelSerializer):
    public_trace_url = serializers.CharField(source="get_public_url", read_only=True)

    class Meta:
        model = HarvestTraceLot
        fields = [
            "trace_code",
            "lot_code",
            "harvest_date",
            "actual_output_quantity",
            "actual_output_unit",
            "certifications",
            "public_message",
            "is_public",
            "status",
            "public_trace_url",
            "qr_code",
        ]


class InternalPlantingDetailSerializer(serializers.ModelSerializer):
    source_batch_id = serializers.CharField(source="source_batch.seedling_batch_id", read_only=True)
    supplier_name = serializers.CharField(source="source_batch.seller.seller_name", read_only=True)
    harvest_lot = HarvestLotSerializer(read_only=True)

    class Meta:
        model = TraceabilityPlanting
        fields = [
            "id",
            "planting_code",
            "status",
            "crop_type",
            "variety",
            "supplier_trace_code",
            "source_batch_id",
            "supplier_name",
            "farm",
            "farmer",
            "quantity_planted",
            "unit",
            "planting_date",
            "farming_method",
            "area_planted",
            "area_unit",
            "soil_notes",
            "notes",
            "location_summary",
            "expected_days_to_harvest",
            "expected_harvest_start",
            "expected_harvest_end",
            "estimated_yield",
            "estimated_yield_unit",
            "prediction_summary",
            "created_at",
            "updated_at",
            "harvest_lot",
        ]


class PublicHarvestTraceSerializer(serializers.ModelSerializer):
    crop_type = serializers.CharField(source="planting.crop_type")
    variety = serializers.CharField(source="planting.variety")
    farm_profile = serializers.SerializerMethodField()
    location_summary = serializers.CharField(source="planting.location_summary")
    farming_method = serializers.CharField(source="planting.farming_method")
    source_summary = serializers.SerializerMethodField()
    harvest_lot = serializers.SerializerMethodField()

    class Meta:
        model = HarvestTraceLot
        fields = [
            "status",
            "crop_type",
            "variety",
            "farm_profile",
            "location_summary",
            "farming_method",
            "source_summary",
            "harvest_lot",
            "certifications",
            "public_message",
        ]

    def get_farm_profile(self, obj):
        farm = obj.planting.farm
        return {
            "farm_name": farm.name,
            "farm_type": "Hydroponic" if farm.is_hydroponic else "Open field",
            "size_hectares": str(farm.size),
        }

    def get_source_summary(self, obj):
        batch = obj.planting.source_batch
        if not batch:
            return None
        return {
            "supplier_batch_id": batch.seedling_batch_id,
            "supplier_name": batch.seller.seller_name,
            "source_location": batch.seller.location,
            "batch_date": batch.batch_date,
            "product_type": batch.seedling_type,
            "variety": batch.variety,
            "batch_reference": batch.source_name,
        }

    def get_harvest_lot(self, obj):
        return {
            "trace_code": obj.trace_code,
            "lot_code": obj.lot_code,
            "harvest_date": obj.harvest_date,
        }
