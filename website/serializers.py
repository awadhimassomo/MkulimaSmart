from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.password_validation import validate_password
<<<<<<< HEAD
from .models import Farm, Crop

User = get_user_model()

class FarmSerializer(serializers.ModelSerializer):
    """Serializer for farm data."""
    has_boundary_map = serializers.ReadOnlyField()

    class Meta:
        model = Farm
        fields = (
            'id', 'name', 'location', 'size', 'soil_type',
            'description', 'is_hydroponic', 'gps_latitude', 'gps_longitude',
            'gps_accuracy_meters', 'boundary_points', 'mapped_area_hectares',
            'mapping_method', 'verification_status', 'verification_notes',
            'mapping_session_status', 'mapping_started_at', 'mapping_finished_at',
            'mapping_duration_seconds', 'path_distance_meters', 'boundary_point_count',
            'last_mapped_at', 'has_boundary_map', 'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'mapped_area_hectares', 'verification_status',
            'mapping_session_status', 'mapping_started_at', 'mapping_finished_at',
            'mapping_duration_seconds', 'path_distance_meters', 'boundary_point_count',
            'last_mapped_at', 'has_boundary_map', 'created_at', 'updated_at'
        )

    def validate_boundary_points(self, value):
        if value in (None, []):
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError('Boundary points must be a list of GPS points.')

        if len(value) < 3:
            raise serializers.ValidationError('At least 3 boundary points are required.')

        normalized = []
        for point in value:
            if not isinstance(point, dict):
                raise serializers.ValidationError('Each boundary point must be an object.')

            lat = point.get('lat', point.get('latitude'))
            lng = point.get('lng', point.get('lon', point.get('longitude')))
            if lat is None or lng is None:
                raise serializers.ValidationError('Each boundary point must include lat and lng.')

            try:
                lat = float(lat)
                lng = float(lng)
            except (TypeError, ValueError):
                raise serializers.ValidationError('Boundary point coordinates must be numeric.')

            if not (-90 <= lat <= 90):
                raise serializers.ValidationError('Latitude must be between -90 and 90.')
            if not (-180 <= lng <= 180):
                raise serializers.ValidationError('Longitude must be between -180 and 180.')

            normalized.append({
                'lat': round(lat, 7),
                'lng': round(lng, 7),
                'timestamp': point.get('timestamp'),
            })

        return normalized


class FarmBoundaryUploadSerializer(serializers.Serializer):
    """Serializer for uploading walked farm boundary data."""
    gps_accuracy_meters = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    mapping_method = serializers.ChoiceField(
        choices=['manual_pin', 'walk_boundary', 'draw_boundary'],
        required=False
    )
    boundary_points = serializers.ListField(required=True)

    def validate_boundary_points(self, value):
        return FarmSerializer().validate_boundary_points(value)


class FarmMappingStartSerializer(serializers.Serializer):
    """Serializer for starting a farm mapping session."""
    gps_accuracy_meters = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    mapping_method = serializers.ChoiceField(
        choices=['manual_pin', 'walk_boundary', 'draw_boundary'],
        required=False
    )
    started_at = serializers.DateTimeField(required=False)


class FarmMappingFinishSerializer(FarmBoundaryUploadSerializer):
    """Serializer for finishing a farm mapping session."""
    finished_at = serializers.DateTimeField(required=False)


class CropSerializer(serializers.ModelSerializer):
    """Serializer for crop data."""
    class Meta:
        model = Crop
        fields = (
            'id', 'farm', 'name', 'description', 'planting_date',
            'expected_harvest_date', 'quantity', 'is_available_for_sale',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile data"""
    farms = FarmSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ('id', 'phone_number', 'email', 'first_name', 'last_name', 
                 'is_farmer', 'is_supplier', 'is_trainer', 'address',
                 'date_joined', 'farms')
        read_only_fields = ('id', 'date_joined', 'farms')
=======

User = get_user_model()

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile data"""
    class Meta:
        model = User
        fields = ('id', 'phone_number', 'email', 'first_name', 'last_name', 
                 'is_farmer', 'is_supplier', 'is_trainer', 'date_joined')
        read_only_fields = ('id', 'date_joined')
>>>>>>> 41ded11a88a936651d40cdbfd9f129ce3e3c686d


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = ('phone_number', 'email', 'first_name', 'last_name', 'password', 'password2')
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True}
        }
    
    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({"password": _("Password fields didn't match.")})
        
        # Normalize phone number
        phone_number = ''.join(c for c in attrs['phone_number'] if c.isdigit() or c == '+')
        if User.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError({"phone_number": _("A user with this phone number already exists.")})
        
        attrs['phone_number'] = phone_number
        return attrs
    
    def create(self, validated_data):
        user = User.objects.create_user(
            phone_number=validated_data['phone_number'],
            email=validated_data.get('email'),
            first_name=validated_data.get('first_name'),
            last_name=validated_data.get('last_name'),
            password=validated_data['password'],
            is_farmer=True  # Default to farmer role
        )
        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    phone_number = serializers.CharField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, attrs):
        # Normalize phone number
        phone_number = ''.join(c for c in attrs['phone_number'] if c.isdigit() or c == '+')
        attrs['phone_number'] = phone_number
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request"""
    email = serializers.EmailField(required=True)
    

class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation"""
    new_password = serializers.CharField(
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    new_password2 = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": _("Password fields didn't match.")})
        return attrs
