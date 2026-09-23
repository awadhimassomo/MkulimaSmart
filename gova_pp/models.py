import os
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator

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


def chat_media_upload_path(instance, filename):
    """Generate upload path for chat media files"""
    ext = filename.split('.')[-1].lower()
    # Generate a unique filename with timestamp and random string
    unique_id = f"{int(timezone.now().timestamp())}_{uuid.uuid4().hex[:8]}"
    filename = f"{unique_id}.{ext}"
    # Create a path like: chat_media/user_id/YYYY/MM/DD/filename.extension
    date_path = timezone.now().strftime('%Y/%m/%d')
    return os.path.join('chat_media', str(instance.uploaded_by.id), date_path, filename)


class ChatMedia(models.Model):
    """
    Model for storing chat media files (images, documents, etc.)
    """
    MEDIA_TYPES = [
        ('image', 'Image'),
        ('document', 'Document'),
        ('audio', 'Audio'),
        ('video', 'Video'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(
        upload_to=chat_media_upload_path,
        validators=[
            FileExtensionValidator(allowed_extensions=[
                'jpg', 'jpeg', 'png', 'gif', 'webp',  # Images
                'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods',  # Documents
                'mp3', 'wav', 'ogg', 'm4a',  # Audio
                'mp4', 'mov', 'avi', 'webm', 'mkv',  # Video
                'txt', 'csv', 'json', 'zip', 'rar'  # Text & Archives
            ])
        ]
    )
    file_name = models.CharField(max_length=255, help_text="Original filename")
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, help_text="File MIME type")
    message_type = models.CharField(
        max_length=10, 
        choices=MEDIA_TYPES, 
        default='document',
        help_text="Type of media file"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='uploaded_chat_media',
        help_text="User who uploaded the file"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, help_text="When the file was uploaded")
    expires_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the file should expire (optional)"
    )
    is_encrypted = models.BooleanField(
        default=False,
        help_text="Whether the file is encrypted"
    )
    encryption_key = models.TextField(
        blank=True, 
        null=True, 
        help_text="Encryption key (if applicable)"
    )
    
    thumbnail = models.ImageField(
        upload_to='chat_media/thumbnails/', 
        blank=True, 
        null=True,
        help_text="Thumbnail for image files"
    )

    def save(self, *args, **kwargs):
        # Generate thumbnail if it's an image and doesn't have one
        if self.file and self.is_image() and not self.thumbnail:
            try:
                self.make_thumbnail()
            except Exception as e:
                # Don't block saving if thumbnail generation fails
                print(f"Error generating thumbnail: {e}")
                
        super().save(*args, **kwargs)

    def make_thumbnail(self):
        from PIL import Image
        from io import BytesIO
        from django.core.files.base import ContentFile
        
        # Open the original image
        img = Image.open(self.file)
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
            
        # Resize maintaining aspect ratio
        img.thumbnail((300, 300))
        
        # Save to memory
        thumb_io = BytesIO()
        img.save(thumb_io, 'JPEG', quality=85)
        
        # Create a filename for the thumbnail
        name = os.path.basename(self.file.name)
        thumb_name = f"thumb_{name}"
        
        # Save the thumbnail to the field
        self.thumbnail.save(thumb_name, ContentFile(thumb_io.getvalue()), save=False)
    
    # Add a method to get the public URL for the file
    def get_absolute_url(self):
        """Get the absolute URL for this media file"""
        if not self.file or not hasattr(self.file, 'url'):
            return ""
        
        # Check if we're in debug mode
        debug = getattr(settings, 'DEBUG', False)
        
        if not debug:
            return self.file.url
            
        # In debug mode, try to get the current request for better URL construction
        try:
            # Try to get request from thread local
            from threading import local
            _thread_locals = local()
            
            if hasattr(_thread_locals, 'request'):
                request = _thread_locals.request
            else:
                # Fallback to creating a dummy request with default values
                from django.http import HttpRequest
                request = HttpRequest()
                request.META = {}
                request.META['SERVER_NAME'] = 'localhost'
                request.META['SERVER_PORT'] = '8000'
            
            # Build the URL
            scheme = 'https' if getattr(request, 'is_secure', lambda: False)() else 'http'
            host = request.get_host() if hasattr(request, 'get_host') else 'localhost:8000'
            
            # Ensure we have a proper host
            if not host or host == 'testserver':
                host = 'localhost:8000'
            
            # Ensure the URL is properly formatted
            file_url = self.file.url
            if not file_url.startswith('/'):
                file_url = f'/{file_url}'
            
            return f"{scheme}://{host}{file_url}"
                
        except Exception as e:
            # If anything fails, fall back to a simple URL
            return f"http://localhost:8000{self.file.url}"
        
        # In production, use the storage's URL method
        return self.file.url
    
    # Add a property for backward compatibility
    @property
    def file_url(self):
        return self.get_absolute_url()
        
    def __str__(self):
        return f"{self.file_name} ({self.get_message_type_display()})"
        
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Chat Media'
        verbose_name_plural = 'Chat Media'
    
    # Metadata
    width = models.PositiveIntegerField(null=True, blank=True, help_text="Image width in pixels")
    height = models.PositiveIntegerField(null=True, blank=True, help_text="Image height in pixels")
    duration = models.FloatField(null=True, blank=True, help_text="Media duration in seconds")
    
    class Meta:
        verbose_name = 'Chat Media'
        verbose_name_plural = 'Chat Media'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.file_name} ({self.get_message_type_display()})"
    
    def file_url(self):
        """Get the full URL for the file"""
        if self.file and hasattr(self.file, 'url'):
            return self.file.url
        return None
    
    def file_extension(self):
        """Get the file extension in lowercase"""
        return os.path.splitext(self.file_name)[1].lower()
    
    def is_image(self):
        """Check if the file is an image"""
        return self.mime_type.startswith('image/') or self.file_extension() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    
    def is_document(self):
        """Check if the file is a document"""
        return self.mime_type.startswith('application/') or self.file_extension() in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv']
    
    def is_media(self):
        """Check if the file is a media file (audio/video)"""
        return self.mime_type.startswith(('audio/', 'video/')) or self.file_extension() in ['.mp3', '.wav', '.ogg', '.mp4', '.mov', '.avi']
    
    def delete(self, *args, **kwargs):
        """Delete the file from storage when the model is deleted"""
        if self.file:
            storage, path = self.file.storage, self.file.path
            super().delete(*args, **kwargs)
            storage.delete(path)
        else:
            super().delete(*args, **kwargs)


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
        ('farmer_reply', 'Farmer Reply'),
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
