"""
The farming assistant's conversations. One Conversation per farmer per channel (today:
WhatsApp, via Kikapu's number); every message in both directions is kept so the chat
can carry on ("what about the second one?") and staff can see what farmers asked.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q


class Conversation(models.Model):
    CHANNEL_CHOICES = [("whatsapp", "WhatsApp (via Kikapu)")]

    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="whatsapp")
    phone_number = models.CharField(max_length=20, help_text="E.164, e.g. +255712345678")
    farmer_name = models.CharField(max_length=120, blank=True)
    farmer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="assistant_conversations"
    )
    language = models.CharField(max_length=5, default="sw")
    region = models.CharField(max_length=60, blank=True)
    last_diagnosis = models.JSONField(blank=True, null=True)
    last_products = models.JSONField(blank=True, default=list)
    needs_expert = models.BooleanField(default=False, help_text="The latest photo needs an extension officer.")
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_message_at"]
        constraints = [models.UniqueConstraint(fields=["channel", "phone_number"], name="unique_assistant_conversation")]

    def __str__(self):
        return f"{self.farmer_name or self.phone_number} ({self.channel})"


class Message(models.Model):
    ROLE_CHOICES = [("farmer", "Farmer"), ("assistant", "Assistant")]
    KIND_CHOICES = [("text", "Text"), ("image", "Photo")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="text")
    text = models.TextField(blank=True, help_text="The message, or the caption sent with a photo.")
    photo = models.ImageField(upload_to="assistant/photos/", blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True)
    external_id = models.CharField(max_length=128, blank=True, help_text="WhatsApp message id, used to ignore duplicate deliveries.")
    in_reply_to = models.ForeignKey("self", on_delete=models.SET_NULL, blank=True, null=True, related_name="replies")
    payload = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "external_id"], condition=~Q(external_id=""), name="unique_assistant_external_message"
            ),
        ]

    def __str__(self):
        return f"{self.role} {self.kind} #{self.pk}"
