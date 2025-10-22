from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from django.conf import settings
from django.core.validators import FileExtensionValidator
import uuid
from datetime import timedelta


class Organization(models.Model):
    """Organizations that provide training content"""
    name = models.CharField(max_length=100, verbose_name='Jina la Shirika')
    slug = models.SlugField(max_length=120, unique=True, null=True, blank=True)
    description = models.TextField(verbose_name='Maelezo', blank=True)
    logo = models.ImageField(upload_to='training/organizations/', blank=True, null=True, verbose_name='Nembo')
    website = models.URLField(blank=True, verbose_name='Tovuti')
    email = models.EmailField(blank=True, verbose_name='Barua pepe')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Namba ya simu')
    address = models.TextField(blank=True, verbose_name='Anwani')
    is_government = models.BooleanField(default=False, verbose_name='Shirika la Serikali')
    is_verified = models.BooleanField(default=False, verbose_name='Imethibitishwa')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Shirika'
        verbose_name_plural = 'Mashirika'
        ordering = ['name']


class Category(models.Model):
    """Course categories"""
    name = models.CharField(max_length=100, verbose_name='Jina la Kategoria')
    slug = models.SlugField(max_length=120, unique=True, null=True, blank=True)
    description = models.TextField(blank=True, verbose_name='Maelezo')
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome class", verbose_name='Ikoni')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, 
                            related_name='subcategories', verbose_name='Kategoria Kuu')
    order = models.PositiveIntegerField(default=0, verbose_name='Mpangilio')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Kategoria'
        verbose_name_plural = 'Kategoria'
        ordering = ['order', 'name']


class Tag(models.Model):
    """Tags for courses"""
    name = models.CharField(max_length=50, unique=True, verbose_name='Jina la Lebo')
    slug = models.SlugField(max_length=60, unique=True, null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Lebo'
        verbose_name_plural = 'Lebo'
        ordering = ['name']


class Course(models.Model):
    """Training courses"""
    LEVEL_CHOICES = [
        ('beginner', 'Mwanzo'),
        ('intermediate', 'Kati'),
        ('advanced', 'Juu'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Rasimu'),
        ('published', 'Imechapishwa'),
        ('archived', 'Imehifadhiwa'),
    ]
    
    title = models.CharField(max_length=200, verbose_name='Kichwa cha Kozi')
    slug = models.SlugField(max_length=220, unique=True, null=True, blank=True)
    subtitle = models.CharField(max_length=200, blank=True, verbose_name='Kichwa Kidogo')
    description = models.TextField(verbose_name='Maelezo')
    short_description = models.CharField(max_length=255, blank=True, verbose_name='Maelezo Mafupi')
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='courses', 
                                  verbose_name='Shirika')
    instructor_name = models.CharField(max_length=100, blank=True, verbose_name='Jina la Mkufunzi')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='courses',
                               verbose_name='Kategoria')
    tags = models.ManyToManyField(Tag, blank=True, related_name='courses', verbose_name='Lebo')
    thumbnail = models.ImageField(upload_to='training/courses/', blank=True, null=True, 
                               verbose_name='Picha Kuu')
    
    # Course details
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='beginner',
                          verbose_name='Kiwango')
    prerequisites = models.TextField(blank=True, verbose_name='Mahitaji ya Awali')
    learning_objectives = models.TextField(blank=True, verbose_name='Malengo ya Kujifunza')
    target_audience = models.CharField(max_length=200, blank=True, verbose_name='Walengwa')
    language = models.CharField(max_length=20, default='Swahili', verbose_name='Lugha')
    has_certificate = models.BooleanField(default=False, verbose_name='Ina Cheti')
    
    # Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft',
                           verbose_name='Hali')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    featured = models.BooleanField(default=False, verbose_name='Inayopendekezwa')
    view_count = models.PositiveIntegerField(default=0, verbose_name='Idadi ya Maono')
    allow_comments = models.BooleanField(default=True, verbose_name='Ruhusu Maoni')
    estimated_duration = models.PositiveIntegerField(default=0, help_text="Duration in minutes", 
                                                 verbose_name='Muda Unaokadiriwa (dakika)')
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        # Set published_at when status changes to published
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('training:course_detail', kwargs={'slug': self.slug})
    
    @property
    def lesson_count(self):
        return self.lessons.count()
    
    @property
    def is_new(self):
        # Course is considered new if published in the last 30 days
        if self.published_at:
            return (timezone.now() - self.published_at) <= timedelta(days=30)
        return False
    
    class Meta:
        verbose_name = 'Kozi'
        verbose_name_plural = 'Kozi'
        ordering = ['-created_at']


class Module(models.Model):
    """Course modules"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules',
                             verbose_name='Kozi')
    title = models.CharField(max_length=200, verbose_name='Kichwa')
    description = models.TextField(blank=True, verbose_name='Maelezo')
    order = models.PositiveIntegerField(default=0, verbose_name='Mpangilio')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    class Meta:
        verbose_name = 'Moduli'
        verbose_name_plural = 'Moduli'
        ordering = ['course', 'order']


class Lesson(models.Model):
    """Course lessons"""
    CONTENT_TYPE_CHOICES = [
        ('video', 'Video'),
        ('pdf', 'PDF'),
        ('text', 'Text'),
        ('audio', 'Audio'),
        ('animation', 'Animation'),
    ]
    
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons',
                             verbose_name='Moduli')
    title = models.CharField(max_length=200, verbose_name='Kichwa')
    slug = models.SlugField(max_length=220, unique=True, null=True, blank=True)
    description = models.TextField(blank=True, verbose_name='Maelezo')
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default='video',
                                 verbose_name='Aina ya Maudhui')
    order = models.PositiveIntegerField(default=0, verbose_name='Mpangilio')
    
    # Video content
    video_url = models.URLField(blank=True, verbose_name='URL ya Video', 
                             help_text='YouTube, Vimeo URL')
    video_file = models.FileField(
        upload_to='training/videos/', 
        blank=True, null=True, 
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'mov', 'avi', 'wmv'])],
        verbose_name='Faili la Video'
    )
    video_duration = models.PositiveIntegerField(default=0, help_text="Duration in seconds",
                                              verbose_name='Muda wa Video (sekunde)')
    
    # Document content
    document_file = models.FileField(
        upload_to='training/documents/', 
        blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'ppt', 'pptx'])],
        verbose_name='Faili la Nyaraka'
    )
    
    # Audio content
    audio_file = models.FileField(
        upload_to='training/audio/', 
        blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'ogg'])],
        verbose_name='Faili la Sauti'
    )
    
    # Text content
    text_content = models.TextField(blank=True, verbose_name='Maudhui ya Maandishi')
    
    # Allow downloading
    allow_download = models.BooleanField(default=True, verbose_name='Ruhusu Kupakua')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    view_count = models.PositiveIntegerField(default=0, verbose_name='Idadi ya Maono')
    
    def save(self, *args, **kwargs):
        if not self.slug:
            lesson_slug = slugify(self.title)
            # Make sure slug is unique
            unique_slug = f"{lesson_slug}-{uuid.uuid4().hex[:8]}"
            self.slug = unique_slug
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('training:lesson_detail', kwargs={
            'course_slug': self.module.course.slug, 
            'lesson_slug': self.slug
        })
    
    @property
    def course(self):
        return self.module.course
    
    class Meta:
        verbose_name = 'Somo'
        verbose_name_plural = 'Masomo'
        ordering = ['module', 'order']


class LessonAttachment(models.Model):
    """Additional attachments for lessons"""
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='attachments',
                             verbose_name='Somo')
    title = models.CharField(max_length=100, verbose_name='Kichwa')
    description = models.TextField(blank=True, verbose_name='Maelezo')
    file = models.FileField(upload_to='training/attachments/', verbose_name='Faili')
    order = models.PositiveIntegerField(default=0, verbose_name='Mpangilio')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.lesson.title} - {self.title}"
    
    class Meta:
        verbose_name = 'Kiambatisho cha Somo'
        verbose_name_plural = 'Viambatisho vya Masomo'
        ordering = ['lesson', 'order']


class UserProgress(models.Model):
    """Track user progress through courses"""
    PROGRESS_STATUS = [
        ('not_started', 'Bado Kuanza'),
        ('in_progress', 'Inaendelea'),
        ('completed', 'Imekamilika'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name='training_progress', verbose_name='Mtumiaji')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='user_progress',
                             verbose_name='Kozi')
    status = models.CharField(max_length=20, choices=PROGRESS_STATUS, default='not_started',
                           verbose_name='Hali')
    progress_percent = models.PositiveIntegerField(default=0, verbose_name='Asilimia ya Maendeleo')
    last_accessed = models.DateTimeField(auto_now=True, verbose_name='Ilifikishwa Mwisho')
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Ilianza')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Ilikamilika')
    
    def __str__(self):
        return f"{self.user.username} - {self.course.title}"
    
    class Meta:
        verbose_name = 'Maendeleo ya Mtumiaji'
        verbose_name_plural = 'Maendeleo ya Watumiaji'
        unique_together = ['user', 'course']


class LessonProgress(models.Model):
    """Track user progress through individual lessons"""
    COMPLETION_STATUS = [
        ('not_started', 'Bado Kuanza'),
        ('in_progress', 'Inaendelea'),
        ('completed', 'Imekamilika'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name='lesson_progress', verbose_name='Mtumiaji')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='user_progress',
                             verbose_name='Somo')
    status = models.CharField(max_length=20, choices=COMPLETION_STATUS, default='not_started',
                           verbose_name='Hali')
    watched_seconds = models.PositiveIntegerField(default=0, verbose_name='Sekunde Zilizotazamwa')
    last_position = models.PositiveIntegerField(default=0, verbose_name='Nafasi ya Mwisho (sekunde)')
    completed = models.BooleanField(default=False, verbose_name='Imekamilika')
    last_accessed = models.DateTimeField(auto_now=True, verbose_name='Ilifikishwa Mwisho')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Ilikamilika')
    
    def __str__(self):
        return f"{self.user.username} - {self.lesson.title}"
    
    class Meta:
        verbose_name = 'Maendeleo ya Somo'
        verbose_name_plural = 'Maendeleo ya Masomo'
        unique_together = ['user', 'lesson']


class CourseRating(models.Model):
    """User ratings and reviews for courses"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                           related_name='course_ratings', verbose_name='Mtumiaji')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='ratings',
                             verbose_name='Kozi')
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)], 
                                           verbose_name='Ukadiriaji')
    review = models.TextField(blank=True, verbose_name='Maoni')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.course.title} - {self.rating} stars - {self.user.username}"
    
    class Meta:
        verbose_name = 'Ukadiriaji wa Kozi'
        verbose_name_plural = 'Ukadiriaji wa Kozi'
        unique_together = ['user', 'course']
        ordering = ['-created_at']


class Certificate(models.Model):
    """Certificates for completed courses"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                           related_name='certificates', verbose_name='Mtumiaji')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='certificates',
                             verbose_name='Kozi')
    certificate_id = models.CharField(max_length=50, unique=True, editable=False,
                                   verbose_name='Namba ya Cheti')
    issued_date = models.DateTimeField(auto_now_add=True, verbose_name='Tarehe ya Utoaji')
    
    def save(self, *args, **kwargs):
        if not self.certificate_id:
            self.certificate_id = f"CERT-{uuid.uuid4().hex[:8]}-{timezone.now().strftime('%Y%m')}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.username} - {self.course.title}"
    
    class Meta:
        verbose_name = 'Cheti'
        verbose_name_plural = 'Vyeti'
        unique_together = ['user', 'course']


class OrganizationSubmission(models.Model):
    """Form for organizations to submit their training materials"""
    STATUS_CHOICES = [
        ('pending', 'Inasubiri'),
        ('approved', 'Imeidhinishwa'),
        ('rejected', 'Imekataliwa'),
    ]
    
    organization_name = models.CharField(max_length=100, verbose_name='Jina la Shirika')
    contact_person = models.CharField(max_length=100, verbose_name='Jina la Mwasiliani')
    email = models.EmailField(verbose_name='Barua pepe')
    phone = models.CharField(max_length=20, verbose_name='Namba ya simu')
    course_title = models.CharField(max_length=200, verbose_name='Kichwa cha Kozi')
    course_description = models.TextField(verbose_name='Maelezo ya Kozi')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, 
                               verbose_name='Kategoria')
    materials_description = models.TextField(verbose_name='Maelezo ya Nyenzo')
    sample_url = models.URLField(blank=True, verbose_name='URL ya Mfano')
    message = models.TextField(blank=True, verbose_name='Ujumbe wa Ziada')
    
    # Admin fields
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                           verbose_name='Hali')
    admin_notes = models.TextField(blank=True, verbose_name='Maelezo ya Msimamizi')
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name='Iliwasilishwa')
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name='Ilihaririwa')
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                   null=True, blank=True, related_name='processed_submissions',
                                   verbose_name='Ilihaririwa na')
    
    def __str__(self):
        return f"{self.organization_name} - {self.course_title}"
    
    class Meta:
        verbose_name = 'Maombi ya Shirika'
        verbose_name_plural = 'Maombi ya Mashirika'
        ordering = ['-submitted_at']
