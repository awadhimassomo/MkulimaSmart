from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Organization, Category, Tag, Course, Module, Lesson,
    LessonAttachment, UserProgress, LessonProgress,
    CourseRating, Certificate, OrganizationSubmission
)


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ['title', 'content_type', 'order']
    show_change_link = True


class LessonAttachmentInline(admin.TabularInline):
    model = LessonAttachment
    extra = 1
    fields = ['title', 'file', 'order']


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_government', 'is_verified', 'website', 'email']
    list_filter = ['is_government', 'is_verified']
    search_fields = ['name', 'description', 'email']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'order', 'course_count']
    list_filter = ['parent']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    
    def course_count(self, obj):
        return obj.courses.count()
    course_count.short_description = 'Idadi ya Kozi'


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'organization', 'category', 'level', 'status', 
                   'has_certificate', 'featured', 'view_count', 'created_at']
    list_filter = ['status', 'level', 'category', 'organization', 'has_certificate', 'featured']
    search_fields = ['title', 'description', 'short_description', 'instructor_name']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['view_count']
    filter_horizontal = ['tags']
    date_hierarchy = 'created_at'
    inlines = [ModuleInline]
    
    fieldsets = (
        ('Taarifa za Msingi', {
            'fields': ('title', 'slug', 'subtitle', 'description', 'short_description', 
                      'organization', 'instructor_name', 'thumbnail')
        }),
        ('Aina na Vipengele', {
            'fields': ('category', 'tags', 'level', 'language', 'has_certificate')
        }),
        ('Maelezo zaidi', {
            'fields': ('prerequisites', 'learning_objectives', 'target_audience', 'estimated_duration')
        }),
        ('Usimamizi', {
            'fields': ('status', 'featured', 'allow_comments', 'view_count', 'published_at')
        }),
    )


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order', 'lesson_count']
    list_filter = ['course']
    search_fields = ['title', 'description']
    inlines = [LessonInline]
    
    def lesson_count(self, obj):
        return obj.lessons.count()
    lesson_count.short_description = 'Idadi ya Masomo'


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'module', 'content_type', 'order', 'view_count', 'has_content']
    list_filter = ['content_type', 'module__course']
    search_fields = ['title', 'description', 'text_content']
    inlines = [LessonAttachmentInline]
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['view_count']
    
    fieldsets = (
        ('Taarifa za Msingi', {
            'fields': ('module', 'title', 'slug', 'description', 'content_type', 'order')
        }),
        ('Maudhui ya Video', {
            'fields': ('video_url', 'video_file', 'video_duration'),
            'classes': ('collapse',),
        }),
        ('Maudhui ya Nyaraka', {
            'fields': ('document_file',),
            'classes': ('collapse',),
        }),
        ('Maudhui ya Sauti', {
            'fields': ('audio_file',),
            'classes': ('collapse',),
        }),
        ('Maudhui ya Maandishi', {
            'fields': ('text_content',),
            'classes': ('collapse',),
        }),
        ('Vipengele vya Ziada', {
            'fields': ('allow_download', 'view_count')
        }),
    )
    
    def has_content(self, obj):
        if obj.content_type == 'video':
            return bool(obj.video_url or obj.video_file)
        elif obj.content_type == 'pdf':
            return bool(obj.document_file)
        elif obj.content_type == 'audio':
            return bool(obj.audio_file)
        elif obj.content_type == 'text':
            return bool(obj.text_content)
        return False
    has_content.short_description = 'Ina Maudhui'
    has_content.boolean = True


@admin.register(LessonAttachment)
class LessonAttachmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'lesson', 'file', 'order', 'created_at']
    list_filter = ['lesson__module__course']
    search_fields = ['title', 'description']


@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'course', 'status', 'progress_percent', 'started_at', 'completed_at']
    list_filter = ['status', 'course']
    search_fields = ['user__username', 'user__email', 'course__title']
    readonly_fields = ['started_at']
    date_hierarchy = 'started_at'


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'lesson', 'get_course', 'status', 'watched_seconds', 
                   'completed', 'last_accessed']
    list_filter = ['status', 'completed', 'lesson__module__course']
    search_fields = ['user__username', 'user__email', 'lesson__title']
    
    def get_course(self, obj):
        return obj.lesson.module.course
    get_course.short_description = 'Kozi'
    get_course.admin_order_field = 'lesson__module__course__title'


@admin.register(CourseRating)
class CourseRatingAdmin(admin.ModelAdmin):
    list_display = ['user', 'course', 'rating', 'has_review', 'created_at']
    list_filter = ['rating', 'course']
    search_fields = ['user__username', 'user__email', 'review', 'course__title']
    readonly_fields = ['created_at']
    
    def has_review(self, obj):
        return bool(obj.review)
    has_review.boolean = True
    has_review.short_description = 'Ina Maoni'


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ['certificate_id', 'user', 'course', 'issued_date']
    list_filter = ['course']
    search_fields = ['certificate_id', 'user__username', 'user__email', 'course__title']
    readonly_fields = ['certificate_id', 'issued_date']


@admin.register(OrganizationSubmission)
class OrganizationSubmissionAdmin(admin.ModelAdmin):
    list_display = ['organization_name', 'contact_person', 'email', 'course_title', 
                   'status', 'submitted_at', 'processed_at']
    list_filter = ['status', 'category']
    search_fields = ['organization_name', 'contact_person', 'email', 'course_title', 
                    'course_description']
    readonly_fields = ['submitted_at']
    actions = ['approve_submission', 'reject_submission']
    
    fieldsets = (
        ('Taarifa za Shirika', {
            'fields': ('organization_name', 'contact_person', 'email', 'phone')
        }),
        ('Taarifa za Kozi', {
            'fields': ('course_title', 'course_description', 'category', 
                      'materials_description', 'sample_url', 'message')
        }),
        ('Usimamizi', {
            'fields': ('status', 'admin_notes', 'submitted_at', 'processed_at', 'processed_by')
        }),
    )
    
    def approve_submission(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='approved', 
                                processed_at=timezone.now(), 
                                processed_by=request.user)
        self.message_user(request, f"{updated} submission(s) have been approved.")
    approve_submission.short_description = "Idhinisha maombi yaliyochaguliwa"
    
    def reject_submission(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='rejected', 
                                processed_at=timezone.now(), 
                                processed_by=request.user)
        self.message_user(request, f"{updated} submission(s) have been rejected.")
    reject_submission.short_description = "Kataa maombi yaliyochaguliwa"
