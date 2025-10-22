"""
Serializers for the predictions app models
"""
from rest_framework import serializers
from .models import CropData, SoilData, PredictionResult, Notification
import datetime


class CropDataSerializer(serializers.ModelSerializer):
    """Serializer for CropData model"""
    
    class Meta:
        model = CropData
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class SoilDataSerializer(serializers.ModelSerializer):
    """Serializer for SoilData model"""
    
    class Meta:
        model = SoilData
        fields = '__all__'
        read_only_fields = ['created_at']


class PredictionResultSerializer(serializers.ModelSerializer):
    """Serializer for PredictionResult model"""
    
    class Meta:
        model = PredictionResult
        fields = '__all__'
        read_only_fields = ['created_at']
    
    def to_representation(self, instance):
        """Enhance the representation with additional fields"""
        data = super().to_representation(instance)
        
        # Add is_recent flag to show if prediction is fresh
        data['is_recent'] = instance.is_recent
        
        # Add readable type name
        data['type_display'] = instance.get_type_display()
        
        return data


class PredictionRequestSerializer(serializers.Serializer):
    """Serializer for prediction request parameters"""
    farm_id = serializers.IntegerField()
    days = serializers.IntegerField(required=False, default=14)
    type = serializers.ChoiceField(choices=[
        'rainfall', 'yield', 'pest', 'irrigation', 'planting'
    ])
    crop_type = serializers.CharField(required=False, allow_blank=True)
    crop_id = serializers.IntegerField(required=False)
    date = serializers.DateField(required=False, default=lambda: datetime.date.today())


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model"""
    is_read = serializers.BooleanField(read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    absolute_url = serializers.CharField(source='get_absolute_url', read_only=True)
    time_since = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['created_at', 'read_at']
    
    def get_time_since(self, obj):
        """Returns a human-readable string of time since the notification was created"""
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = now - obj.created_at
        
        days = diff.days
        seconds = diff.seconds
        
        if days > 30:
            return f"{days // 30} month{'s' if days // 30 != 1 else ''} ago"
        elif days > 0:
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds >= 3600:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds >= 60:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "just now"
