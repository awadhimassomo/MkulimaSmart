"""  
Django Admin Configuration for Authentication App
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import SyncOperation, ProfileCompletion, DataAccuracy


@admin.register(SyncOperation)
class SyncOperationAdmin(admin.ModelAdmin):
    """Admin interface for Sync Operations"""
    
    list_display = (
        'phone_number',
        'status_badge',
        'completion_percentage_bar',
        'inferred_location',
        'predicted_crops_display',
        'created_at'
    )
    
    list_filter = (
        'status',
        'created_at',
        'inferred_location',
    )
    
    search_fields = (
        'phone_number',
        'kikapu_user_id',
        'farm_name',
    )
    
    readonly_fields = (
        'user',
        'phone_number',
        'kikapu_user_id',
        'status',
        'inferred_location',
        'predicted_crops',
        'completion_percentage',
        'farm_name',
        'request_data',
        'response_data',
        'error_message',
        'created_at',
    )
    
    date_hierarchy = 'created_at'
    
    def status_badge(self, obj):
        """Display status as colored badge"""
        colors = {
            'created_partial': '#28a745',
            'already_exists': '#ffc107',
            'error': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 8px; '
            'border-radius: 4px; font-size: 0.85rem; font-weight: 600;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def completion_percentage_bar(self, obj):
        """Display completion percentage as progress bar"""
        percentage = obj.completion_percentage
        color = '#28a745' if percentage >= 75 else '#ffc107' if percentage >= 50 else '#dc3545'
        return format_html(
            '<div style="width: 100px; background: #e9ecef; border-radius: 4px; overflow: hidden;">' 
            '<div style="width: {}%; background: {}; color: white; text-align: center; '
            'font-size: 0.75rem; font-weight: 600; padding: 2px;">{}%</div></div>',
            percentage,
            color,
            percentage
        )
    completion_percentage_bar.short_description = 'Completion'
    
    def predicted_crops_display(self, obj):
        """Display predicted crops as comma-separated list"""
        if obj.predicted_crops:
            return ', '.join(obj.predicted_crops[:3])
        return '-'
    predicted_crops_display.short_description = 'Predicted Crops'


@admin.register(ProfileCompletion)
class ProfileCompletionAdmin(admin.ModelAdmin):
    """Admin interface for Profile Completions"""
    
    list_display = (
        'user_phone',
        'completion_improvement',
        'fields_updated_count',
        'time_to_complete_display',
        'completed_at'
    )
    
    list_filter = (
        'completed_at',
        'completion_percentage_after',
    )
    
    search_fields = (
        'user__phone_number',
        'user__first_name',
        'user__last_name',
    )
    
    readonly_fields = (
        'user',
        'sync_operation',
        'completion_percentage_before',
        'completion_percentage_after',
        'fields_updated',
        'missing_fields_before',
        'missing_fields_after',
        'time_to_complete',
        'updated_data',
        'completed_at',
    )
    
    date_hierarchy = 'completed_at'
    
    def user_phone(self, obj):
        """Display user phone number"""
        return obj.user.phone_number
    user_phone.short_description = 'Phone Number'
    
    def completion_improvement(self, obj):
        """Display completion percentage improvement"""
        improvement = obj.completion_percentage_after - obj.completion_percentage_before
        return format_html(
            '{}<span style="color: #28a745; font-weight: 600;"> → </span>{}'
            '<span style="color: #6c757d; margin-left: 8px;">(+{}%)</span>',
            f"{obj.completion_percentage_before}%",
            f"{obj.completion_percentage_after}%",
            improvement
        )
    completion_improvement.short_description = 'Completion %'
    
    def fields_updated_count(self, obj):
        """Display number of fields updated"""
        count = len(obj.fields_updated) if obj.fields_updated else 0
        return format_html(
            '<span style="background: #C5D86D; color: #1A3316; padding: 2px 8px; '
            'border-radius: 4px; font-weight: 600;">{} fields</span>',
            count
        )
    fields_updated_count.short_description = 'Fields Updated'
    
    def time_to_complete_display(self, obj):
        """Display time to complete in human-readable format"""
        if not obj.time_to_complete:
            return '-'
        
        total_seconds = int(obj.time_to_complete.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes}m"
        else:
            hours = total_seconds // 3600
            return f"{hours}h"
    time_to_complete_display.short_description = 'Time to Complete'


@admin.register(DataAccuracy)
class DataAccuracyAdmin(admin.ModelAdmin):
    """Admin interface for Data Accuracy tracking"""
    
    list_display = (
        'user_phone',
        'prediction_type',
        'accuracy_badge',
        'predicted_vs_actual',
        'created_at'
    )
    
    list_filter = (
        'prediction_type',
        'is_correct',
        'created_at',
    )
    
    search_fields = (
        'user__phone_number',
        'phone_prefix',
        'farm_name',
    )
    
    readonly_fields = (
        'user',
        'prediction_type',
        'predicted_value',
        'actual_value',
        'is_correct',
        'phone_prefix',
        'farm_name',
        'created_at',
    )
    
    date_hierarchy = 'created_at'
    
    def user_phone(self, obj):
        """Display user phone number"""
        return obj.user.phone_number
    user_phone.short_description = 'Phone Number'
    
    def accuracy_badge(self, obj):
        """Display accuracy as badge"""
        if obj.is_correct:
            return format_html(
                '<span style="background: #28a745; color: white; padding: 4px 8px; '
                'border-radius: 4px; font-weight: 600;">✓ Correct</span>'
            )
        else:
            return format_html(
                '<span style="background: #dc3545; color: white; padding: 4px 8px; '
                'border-radius: 4px; font-weight: 600;">✗ Incorrect</span>'
            )
    accuracy_badge.short_description = 'Accuracy'
    
    def predicted_vs_actual(self, obj):
        """Display predicted vs actual values"""
        if obj.prediction_type == 'location':
            predicted = obj.predicted_value.get('location', '-')
            actual = obj.actual_value.get('location', '-')
            return format_html(
                '<strong>Predicted:</strong> {}<br><strong>Actual:</strong> {}',
                predicted,
                actual
            )
        elif obj.prediction_type == 'crops':
            predicted = ', '.join(obj.predicted_value.get('crops', []))
            actual = ', '.join(obj.actual_value.get('crops', []))
            return format_html(
                '<strong>Predicted:</strong> {}<br><strong>Actual:</strong> {}',
                predicted,
                actual
            )
        return '-'
    predicted_vs_actual.short_description = 'Predicted vs Actual'
