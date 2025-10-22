from django.db import models
from django.conf import settings
from django.utils import timezone

class FarmerMessage(models.Model):
    """Messages from farmers through Mkulima Smart app"""
    MESSAGE_TYPES = [
        ('inquiry', 'General Inquiry'),
        ('complaint', 'Complaint'),
        ('request', 'Request for Help'),
        ('report', 'Field Report'),
        ('image_analysis', 'Image Analysis Request'),
    ]
    
    STATUS_CHOICES = [
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('replied', 'Replied'),
        ('resolved', 'Resolved'),
        ('archived', 'Archived'),
    ]
    
    farmer_name = models.CharField(max_length=100)
    farmer_phone = models.CharField(max_length=20)
    farmer_location = models.CharField(max_length=200, blank=True)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='inquiry')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.CharField(max_length=10, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ], default='medium')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_messages')
    
    # Image analysis fields
    has_image = models.BooleanField(default=False)
    image_url = models.URLField(blank=True, null=True)
    image_file = models.ImageField(upload_to='farmer_images/', blank=True, null=True)
    image_analysis_requested = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.farmer_name} - {self.subject[:50]}"

class GovernmentReply(models.Model):
    """Government replies to farmer messages"""
    message = models.ForeignKey(FarmerMessage, on_delete=models.CASCADE, related_name='replies')
    replied_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reply_text = models.TextField()
    reply_type = models.CharField(max_length=20, choices=[
        ('answer', 'Answer'),
        ('advice', 'Agricultural Advice'),
        ('referral', 'Referral'),
        ('follow_up', 'Follow-up Question'),
    ], default='answer')
    created_at = models.DateTimeField(default=timezone.now)
    sent_via_sms = models.BooleanField(default=False)
    sms_reference = models.CharField(max_length=50, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Reply to {self.message.farmer_name} by {self.replied_by.phone_number}"

class ImageAnalysis(models.Model):
    """AI-powered image analysis results"""
    message = models.OneToOneField(FarmerMessage, on_delete=models.CASCADE, related_name='analysis')
    analysis_text = models.TextField()
    confidence_score = models.FloatField(null=True, blank=True)
    detected_issues = models.JSONField(default=list, blank=True)  # List of detected agricultural issues
    recommendations = models.TextField(blank=True)
    analyzed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    analyzed_at = models.DateTimeField(default=timezone.now)
    openai_model_used = models.CharField(max_length=50, default='gpt-4o-mini')
    processing_time = models.FloatField(null=True, blank=True)  # seconds
    
    # Analysis categories
    ANALYSIS_CATEGORIES = [
        ('crop_disease', 'Crop Disease'),
        ('pest_infestation', 'Pest Infestation'),
        ('nutrient_deficiency', 'Nutrient Deficiency'),
        ('soil_condition', 'Soil Condition'),
        ('plant_health', 'Plant Health'),
        ('harvest_readiness', 'Harvest Readiness'),
        ('other', 'Other'),
    ]
    
    primary_category = models.CharField(max_length=20, choices=ANALYSIS_CATEGORIES, default='other')
    
    class Meta:
        ordering = ['-analyzed_at']
        
    def __str__(self):
        return f"Analysis for {self.message.farmer_name} - {self.primary_category}"


class Alert(models.Model):
    """Model for government alerts and notifications"""
    
    ALERT_TYPES = [
        ('weather', 'Weather Change'),
        ('pest', 'Pest Infestation'),
        ('flood', 'Flood Risk'),
        ('market', 'Market Price Change'),
        ('disease', 'Livestock Disease'),
        ('advisory', 'General Advisory'),
        ('emergency', 'Emergency Alert'),
        ('general', 'General Information'),
    ]
    
    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    title = models.CharField(max_length=200)
    body = models.TextField()  # Changed from 'message' to 'body' as suggested
    location = models.CharField(max_length=100, help_text="Region/District/Village affected")
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES, default='general')
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='medium')
    is_urgent = models.BooleanField(default=False, help_text="Mark as urgent for immediate attention")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    
    # Targeting options
    target_regions = models.CharField(max_length=500, blank=True, help_text="Comma-separated list of regions")
    target_crops = models.CharField(max_length=500, blank=True, help_text="Comma-separated list of crops")
    
    # Scheduling
    timestamp = models.DateTimeField(auto_now_add=True)  # Changed from created_at to timestamp as suggested
    updated_at = models.DateTimeField(auto_now=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, help_text="When to send the alert")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When the alert expires")
    
    # Creator tracking
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_alerts')
    
    # SMS and notification tracking
    sms_sent = models.BooleanField(default=False)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    recipients_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-timestamp']
        
    def __str__(self):
        return f"{self.alert_type.upper()} - {self.title}"
    
    def is_active(self):
        """Check if alert is currently active"""
        from django.utils import timezone
        now = timezone.now()
        
        if self.status != 'active':
            return False
            
        if self.scheduled_at and self.scheduled_at > now:
            return False
            
        if self.expires_at and self.expires_at < now:
            return False
            
        return True
    
    def get_priority_color(self):
        """Get Bootstrap color class for priority"""
        colors = {
            'low': 'success',
            'medium': 'warning',
            'high': 'danger',
            'critical': 'dark'
        }
        return colors.get(self.priority, 'secondary')
