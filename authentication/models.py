"""  
Authentication Models
Tracks sync operations and profile completions for analytics
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class SyncOperation(models.Model):
    """
    Tracks each sync operation from Kikapu to Mkulima Smart
    Used for analytics and monitoring
    """
    STATUS_CHOICES = [
        ('created_partial', 'Created Partial Profile'),
        ('already_exists', 'User Already Exists'),
        ('error', 'Error During Sync'),
    ]
    
    # User information
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sync_operations')
    phone_number = models.CharField(max_length=15)
    kikapu_user_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Sync details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    inferred_location = models.CharField(max_length=200, blank=True)
    predicted_crops = models.JSONField(default=list)
    completion_percentage = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0
    )
    
    # Request data
    farm_name = models.CharField(max_length=200, blank=True)
    request_data = models.JSONField(default=dict)  # Store full request for debugging
    
    # Response data
    response_data = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Sync Operation'
        verbose_name_plural = 'Sync Operations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['phone_number']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Sync {self.phone_number} - {self.status} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class ProfileCompletion(models.Model):
    """
    Tracks profile completion events
    Measures user engagement and data quality
    """
    # User information
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profile_completions')
    sync_operation = models.ForeignKey(
        SyncOperation, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='completions'
    )
    
    # Completion details
    completion_percentage_before = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    completion_percentage_after = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # Fields updated
    fields_updated = models.JSONField(default=list)  # List of field names that were updated
    missing_fields_before = models.JSONField(default=list)
    missing_fields_after = models.JSONField(default=list)
    
    # Time metrics
    time_to_complete = models.DurationField(null=True, blank=True)  # Time from sync to completion
    
    # Updated data
    updated_data = models.JSONField(default=dict)
    
    # Timestamps
    completed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Profile Completion'
        verbose_name_plural = 'Profile Completions'
        ordering = ['-completed_at']
        indexes = [
            models.Index(fields=['-completed_at']),
            models.Index(fields=['user']),
        ]
    
    def __str__(self):
        return f"Completion {self.user.phone_number} - {self.completion_percentage_after}% - {self.completed_at.strftime('%Y-%m-%d')}"


class DataAccuracy(models.Model):
    """
    Tracks accuracy of smart predictions vs actual user data
    Helps improve the prediction algorithms
    """
    PREDICTION_TYPES = [
        ('location', 'Location Prediction'),
        ('crops', 'Crop Prediction'),
        ('farm_size', 'Farm Size Prediction'),
    ]
    
    # Reference
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='data_accuracy')
    prediction_type = models.CharField(max_length=20, choices=PREDICTION_TYPES)
    
    # Prediction vs Actual
    predicted_value = models.JSONField()  # What we predicted
    actual_value = models.JSONField()  # What user confirmed
    is_correct = models.BooleanField(default=False)
    
    # Context
    phone_prefix = models.CharField(max_length=10, blank=True)
    farm_name = models.CharField(max_length=200, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Data Accuracy'
        verbose_name_plural = 'Data Accuracy Records'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['prediction_type']),
            models.Index(fields=['is_correct']),
        ]
    
    def __str__(self):
        status = '✓' if self.is_correct else '✗'
        return f"{status} {self.prediction_type} - {self.user.phone_number}"
