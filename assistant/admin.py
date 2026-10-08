from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    can_delete = False
    fields = ("created_at", "role", "kind", "text", "photo", "image_url")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("farmer_name", "phone_number", "language", "needs_expert", "last_message_at")
    list_filter = ("needs_expert", "language", "channel")
    search_fields = ("phone_number", "farmer_name")
    readonly_fields = ("created_at", "last_message_at", "last_diagnosis", "last_products")
    inlines = [MessageInline]
