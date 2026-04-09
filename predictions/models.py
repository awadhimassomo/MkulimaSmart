from django.db import models
from django.utils import timezone
from django.urls import reverse
from website.models import Farm, User


class CropData(models.Model):
    """Model to store crop planting information"""
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='crops')
    crop_type = models.CharField(max_length=100)
    variety = models.CharField(max_length=100, blank=True)
    planting_date = models.DateField()
    expected_harvest_date = models.DateField(null=True, blank=True)
    field_size_acres = models.FloatField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.crop_type} at {self.farm.name} (planted: {self.planting_date})"
    
    class Meta:
        ordering = ['-planting_date']


class SoilData(models.Model):
    """Model to store soil information"""
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='soil_tests', null=True, blank=True)
    lat = models.FloatField()
    lon = models.FloatField()
    date = models.DateField(default=timezone.now)
    ph = models.FloatField(help_text="Soil pH (0-14)")
    moisture = models.FloatField(help_text="Soil moisture (%)")
    organic_matter = models.FloatField(help_text="Organic matter content (%)", null=True, blank=True)
    nitrogen = models.FloatField(help_text="Nitrogen content (mg/kg)", null=True, blank=True)
    phosphorus = models.FloatField(help_text="Phosphorus content (mg/kg)", null=True, blank=True)
    potassium = models.FloatField(help_text="Potassium content (mg/kg)", null=True, blank=True)
    source = models.CharField(max_length=100, default="manual")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        location = f"{self.farm.name}" if self.farm else f"({self.lat}, {self.lon})"
        return f"Soil data for {location} on {self.date}"
    
    class Meta:
        ordering = ['-date']


class PredictionResult(models.Model):
    """Model to store prediction results from various prediction models"""
    TYPE_CHOICES = [
        ('rainfall', 'Rainfall Prediction'),
        ('yield', 'Yield Prediction'),
        ('pest', 'Pest/Disease Risk'),
        ('irrigation', 'Irrigation Advice'),
        ('planting', 'Planting Calendar'),
    ]
    
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='predictions')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    prediction_data = models.JSONField(help_text="JSON containing prediction details")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_type_display()} for {self.farm.name} on {self.created_at.date()}"
    
    class Meta:
        ordering = ['-created_at']
        
    @property
    def is_recent(self):
        """Check if the prediction was created recently (within the last 24 hours)"""
        return (timezone.now() - self.created_at).days < 1


class Notification(models.Model):
    """Model for storing in-app notifications to users"""
    CATEGORY_CHOICES = [
        ('prediction', 'Prediction Update'),
        ('weather', 'Weather Alert'),
        ('pest', 'Pest/Disease Alert'),
        ('system', 'System Notification'),
        ('tip', 'Farming Tip'),
    ]
    
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    title = models.CharField(max_length=100)
    message = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    link = models.CharField(max_length=255, blank=True, help_text="Optional relative URL for more information")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.title} ({self.get_category_display()} - {self.get_priority_display()}) for {self.user.username}"
    
    def mark_as_read(self):
        """Mark the notification as read"""
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=['read_at'])
    
    @property
    def is_read(self):
        """Check if the notification has been read"""
        return self.read_at is not None
    
    def get_absolute_url(self):
        """Get the URL to view the notification details"""
        if self.link:
            return self.link
        return reverse('predictions:notification_detail', args=[str(self.id)])
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'read_at']),
        ]
