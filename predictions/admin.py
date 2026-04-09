from django.contrib import admin
from django.utils import timezone
from .models import CropData, SoilData, PredictionResult, Notification


@admin.register(CropData)
class CropDataAdmin(admin.ModelAdmin):
    list_display = ('crop_type', 'farm', 'planting_date', 'field_size_acres')
    list_filter = ('crop_type', 'farm')
    search_fields = ('crop_type', 'farm__name', 'variety')
    date_hierarchy = 'planting_date'


@admin.register(SoilData)
class SoilDataAdmin(admin.ModelAdmin):
    list_display = ('farm', 'date', 'ph', 'moisture', 'source')
    list_filter = ('farm', 'source')
    search_fields = ('farm__name', 'notes')
    date_hierarchy = 'date'


@admin.register(PredictionResult)
class PredictionResultAdmin(admin.ModelAdmin):
    list_display = ('farm', 'type', 'created_at', 'is_recent')
    list_filter = ('type', 'farm')
    search_fields = ('farm__name',)
    date_hierarchy = 'created_at'
    
    def has_change_permission(self, request, obj=None):
        # Predictions should be read-only
        return False
    
    def has_add_permission(self, request):
        # Predictions should be created only via PredictionManager
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'farm', 'category', 'priority', 'created_at', 'is_read')
    list_filter = ('category', 'priority')
    search_fields = ('title', 'message', 'user__username', 'farm__name')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'read_at')
    
    actions = ['mark_as_read', 'mark_as_unread']
    
    def is_read(self, obj):
        return obj.read_at is not None
    is_read.boolean = True
    is_read.short_description = 'Read'
    
    def mark_as_read(self, request, queryset):
        updated = queryset.filter(read_at__isnull=True).update(read_at=timezone.now())
        self.message_user(request, f'{updated} notification(s) marked as read.')
    mark_as_read.short_description = 'Mark selected notifications as read'
    
    def mark_as_unread(self, request, queryset):
        updated = queryset.filter(read_at__isnull=False).update(read_at=None)
        self.message_user(request, f'{updated} notification(s) marked as unread.')
    mark_as_unread.short_description = 'Mark selected notifications as unread'
