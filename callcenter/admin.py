from django.contrib import admin

from .models import Agronomist, Case, Invite


@admin.register(Agronomist)
class AgronomistAdmin(admin.ModelAdmin):
    list_display = ("full_name", "company", "is_active", "is_available", "last_seen")
    list_filter = ("is_active", "is_available")
    search_fields = ("full_name", "user__email")
    raw_id_fields = ("user", "company")


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "created_at", "expires_at", "used_at")
    readonly_fields = ("token", "created_at", "used_at", "agronomist")
    raw_id_fields = ("company", "created_by")


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("pk", "conversation", "status", "agronomist", "answered_by_ai", "waiting_since", "last_activity_at")
    list_filter = ("status", "answered_by_ai")
    raw_id_fields = ("conversation", "agronomist")
