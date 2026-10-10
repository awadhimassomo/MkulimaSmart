from django.contrib import admin
from .models import FarmerMessage, GovernmentReply, ImageAnalysis

@admin.register(FarmerMessage)
class FarmerMessageAdmin(admin.ModelAdmin):
    list_display = ['farmer_name', 'subject', 'message_type', 'status', 'priority', 'has_image', 'created_at', 'assigned_to']
    list_filter = ['status', 'message_type', 'priority', 'has_image', 'created_at']
    search_fields = ['farmer_name', 'farmer_phone', 'subject', 'message']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['status', 'priority', 'assigned_to']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Farmer Information', {
            'fields': ('farmer_name', 'farmer_phone', 'farmer_location')
        }),
        ('Message Details', {
            'fields': ('message_type', 'subject', 'message', 'status', 'priority', 'assigned_to')
        }),
        ('Image Information', {
            'fields': ('has_image', 'image_url', 'image_file', 'image_analysis_requested'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(GovernmentReply)
class GovernmentReplyAdmin(admin.ModelAdmin):
    list_display = ['message', 'replied_by', 'reply_type', 'sent_via_sms', 'created_at']
    list_filter = ['reply_type', 'sent_via_sms', 'created_at']
    search_fields = ['message__farmer_name', 'reply_text', 'replied_by__username']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Reply Information', {
            'fields': ('message', 'replied_by', 'reply_type', 'reply_text')
        }),
        ('SMS Details', {
            'fields': ('sent_via_sms', 'sms_reference'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )

@admin.register(ImageAnalysis)
class ImageAnalysisAdmin(admin.ModelAdmin):
    list_display = ['message', 'primary_category', 'confidence_score', 'analyzed_by', 'analyzed_at']
    list_filter = ['primary_category', 'openai_model_used', 'analyzed_at']
    search_fields = ['message__farmer_name', 'analysis_text', 'recommendations']
    readonly_fields = ['analyzed_at', 'processing_time']
    
    fieldsets = (
        ('Analysis Information', {
            'fields': ('message', 'primary_category', 'analysis_text', 'confidence_score')
        }),
        ('Detected Issues & Recommendations', {
            'fields': ('detected_issues', 'recommendations')
        }),
        ('Technical Details', {
            'fields': ('analyzed_by', 'openai_model_used', 'processing_time', 'analyzed_at'),
            'classes': ('collapse',)
        })
    )


from . import officials as official_actions  # noqa: E402
from .models import GovernmentInvite, GovernmentOfficial  # noqa: E402


@admin.register(GovernmentOfficial)
class GovernmentOfficialAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'institution', 'region', 'status', 'via', 'created_at']
    list_filter = ['status', 'via', 'region']
    search_fields = ['full_name', 'institution', 'user__email']
    readonly_fields = ['user', 'staff_granted', 'decided_by', 'decided_at', 'created_at']
    actions = ['approve_selected', 'suspend_selected']

    @admin.action(description='Approve selected officers (grants dashboard access)')
    def approve_selected(self, request, queryset):
        for official in queryset.select_related('user'):
            official_actions.approve(official, request.user)

    @admin.action(description='Suspend selected officers (removes dashboard access)')
    def suspend_selected(self, request, queryset):
        for official in queryset.select_related('user'):
            official_actions.suspend(official, request.user)


@admin.register(GovernmentInvite)
class GovernmentInviteAdmin(admin.ModelAdmin):
    list_display = ['name', 'institution', 'created_at', 'expires_at', 'used_at']
    readonly_fields = ['token', 'created_at', 'used_at', 'official']
