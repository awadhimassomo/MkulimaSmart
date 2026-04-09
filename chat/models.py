from django.db import models
from django.conf import settings
from django.utils import timezone

class Thread(models.Model):
    """Chat thread that can be between multiple participants"""
    title = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_group = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Thread {self.id}: {self.title or 'Untitled'}"
    
    class Meta:
        ordering = ['-updated_at']

class ThreadParticipant(models.Model):
    """User participation in a chat thread"""
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_threads')
    joined_at = models.DateTimeField(default=timezone.now)
    is_admin = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['thread', 'user']
    
    def __str__(self):
        return f"{self.user} in Thread {self.thread_id}"

class Media(models.Model):
    """Encrypted media file storage"""
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.FileField(upload_to="enc_media/%Y/%m/%d/")
    sha256_hex = models.CharField(max_length=64)
    mime = models.CharField(max_length=100)
    size = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Media {self.id} ({self.mime[:10]}, {self.size} bytes)"
    
    class Meta:
        verbose_name_plural = "Media"

class Message(models.Model):
    """Individual message in a chat thread"""
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField(blank=True, default="")
    media = models.ForeignKey(Media, null=True, blank=True, on_delete=models.SET_NULL, related_name='messages')
    media_nonce = models.BinaryField(null=True, blank=True)   # 12 bytes
    thumb_b64 = models.TextField(blank=True, default="")
    media_sha256_hex = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    extra = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"Message {self.id} by {self.sender} in Thread {self.thread_id}"
    
    class Meta:
        ordering = ['created_at']

class MediaKeyWrap(models.Model):
    """Per-recipient wrapped encryption keys for E2E encrypted media"""
    message = models.ForeignKey(Message, related_name="keywraps", on_delete=models.CASCADE)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    wrapped_key_b64 = models.TextField()
    
    class Meta:
        unique_together = ['message', 'recipient']
    
    def __str__(self):
        return f"Key wrap for {self.recipient} in Message {self.message_id}"
