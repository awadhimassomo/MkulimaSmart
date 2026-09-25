from django.contrib import admin

from .models import Discussion, Reply


class ReplyInline(admin.TabularInline):
    model = Reply
    extra = 0
    readonly_fields = ("author", "created_at")


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ("title", "crop", "seed_variety", "author", "kind", "reply_count", "is_active", "created_at")
    list_filter = ("kind", "is_active", "crop")
    search_fields = ("title", "body", "crop", "seed_variety", "author__phone_number")
    readonly_fields = ("reply_count", "created_at", "updated_at")
    inlines = [ReplyInline]
    actions = ["deactivate", "activate"]

    @admin.action(description="Hide selected discussions")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Show selected discussions")
    def activate(self, request, queryset):
        queryset.update(is_active=True)


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ("discussion", "author", "created_at")
    search_fields = ("body", "author__phone_number")
