from rest_framework import serializers
from .models import (
    EcopGroup, EcopGroupMember, EcopJoinRequest, 
    EcopCommitment, EcopFarmerCommitment
)
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Serializer for user details."""
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'phone_number']
        read_only_fields = ['id']

class EcopGroupSerializer(serializers.ModelSerializer):
    """Serializer for EcopGroup model."""
    founder_name = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    
    class Meta:
        model = EcopGroup
        fields = [
            'id', 'group_name', 'primary_crop', 'location', 'founder',
            'founder_name', 'member_count', 'created_at', 'is_active'
        ]
        read_only_fields = ['id', 'founder', 'founder_name', 'member_count', 'created_at']
    
    def get_founder_name(self, obj):
        return obj.founder_name
    
    def get_member_count(self, obj):
        return obj.member_count
    
    def validate_group_name(self, value):
        # Case-insensitive check for existing group name
        if EcopGroup.objects.filter(group_name__iexact=value).exists():
            raise serializers.ValidationError("A group with this name already exists.")
        return value

class EcopGroupMemberSerializer(serializers.ModelSerializer):
    """Serializer for EcopGroupMember model."""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = EcopGroupMember
        fields = ['id', 'user', 'joined_at', 'is_active']
        read_only_fields = ['id', 'user', 'joined_at']

class EcopJoinRequestSerializer(serializers.ModelSerializer):
    """Serializer for EcopJoinRequest model."""
    farmer_name = serializers.SerializerMethodField()
    farmer_phone = serializers.SerializerMethodField()
    group_name = serializers.SerializerMethodField()
    
    class Meta:
        model = EcopJoinRequest
        fields = [
            'id', 'group', 'group_name', 'farmer', 'farmer_name', 'farmer_phone',
            'status', 'created_at', 'responded_at', 'response_note'
        ]
        read_only_fields = [
            'id', 'farmer', 'farmer_name', 'farmer_phone', 'group_name',
            'created_at', 'responded_at'
        ]
    
    def get_farmer_name(self, obj):
        return obj.farmer.get_full_name()
    
    def get_farmer_phone(self, obj):
        return obj.farmer.phone_number
    
    def get_group_name(self, obj):
        return obj.group.group_name

class EcopCommitmentSerializer(serializers.ModelSerializer):
    """Serializer for EcopCommitment model."""
    group_name = serializers.SerializerMethodField()
    farmer_count = serializers.SerializerMethodField()
    buyer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = EcopCommitment
        fields = [
            'id', 'group', 'group_name', 'crop', 'total_volume', 'status',
            'created_at', 'locked_at', 'matched_at', 'buyer', 'buyer_name',
            'agreed_price', 'farmer_count'
        ]
        read_only_fields = [
            'id', 'group_name', 'created_at', 'locked_at', 'matched_at',
            'buyer_name', 'farmer_count'
        ]
    
    def get_group_name(self, obj):
        return obj.group_name
    
    def get_farmer_count(self, obj):
        return obj.farmer_count
    
    def get_buyer_name(self, obj):
        if obj.buyer:
            return obj.buyer.get_full_name()
        return None

class EcopFarmerCommitmentSerializer(serializers.ModelSerializer):
    """Serializer for EcopFarmerCommitment model."""
    farmer_name = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    
    class Meta:
        model = EcopFarmerCommitment
        fields = [
            'id', 'commitment', 'farmer', 'farmer_name', 'phone_number',
            'volume', 'is_paid', 'paid_at'
        ]
        read_only_fields = ['id', 'farmer_name', 'phone_number', 'paid_at']
    
    def get_farmer_name(self, obj):
        return obj.farmer_name
    
    def get_phone_number(self, obj):
        return obj.phone_number

# Request/Response Serializers
class CreateGroupSerializer(serializers.ModelSerializer):
    """Serializer for creating a new Ecop group."""
    class Meta:
        model = EcopGroup
        fields = ['group_name', 'primary_crop', 'location']

class JoinGroupRequestSerializer(serializers.Serializer):
    """Serializer for join group request."""
    group_id = serializers.IntegerField()
    
    def validate_group_id(self, value):
        if not EcopGroup.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Group not found or inactive.")
        return value

class RespondJoinRequestSerializer(serializers.Serializer):
    """Serializer for responding to join requests."""
    request_id = serializers.IntegerField()
    approve = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True)
    
    def validate_request_id(self, value):
        try:
            return EcopJoinRequest.objects.get(id=value, status='pending')
        except EcopJoinRequest.DoesNotExist:
            raise serializers.ValidationError("Pending join request not found.")

class LockCommitmentSerializer(serializers.Serializer):
    """Serializer for locking a commitment."""
    crop = serializers.CharField(max_length=100)
    total_volume = serializers.DecimalField(max_digits=10, decimal_places=2)
    farmer_commitments = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField(),
            allow_empty=False
        ),
        min_length=1
    )
    
    def validate(self, data):
        # Add custom validation for farmer_commitments
        for fc in data['farmer_commitments']:
            if 'farmer_id' not in fc or 'volume' not in fc:
                raise serializers.ValidationError(
                    "Each farmer commitment must include 'farmer_id' and 'volume'"
                )
        return data
