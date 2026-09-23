from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _

from .models import (
    Organization, Category, Tag, Course, Module, Lesson,
    LessonAttachment, UserProgress, LessonProgress,
    CourseRating, Certificate, OrganizationSubmission
)
from .forms import CourseRatingForm, OrganizationSubmissionForm


def training_home(request):
    """Home page for the training platform"""
    featured_courses = Course.objects.filter(status='published', featured=True)[:6]
    new_courses = Course.objects.filter(
        status='published',
        published_at__gte=timezone.now() - timezone.timedelta(days=30)
    ).exclude(id__in=featured_courses.values_list('id', flat=True))[:6]
    
    popular_courses = Course.objects.filter(status='published').order_by('-view_count')[:6]
    
    categories = Category.objects.filter(parent__isnull=True).annotate(
        course_count=Count('courses')
    ).filter(course_count__gt=0).order_by('-course_count')[:8]
    
    organizations = Organization.objects.filter(is_verified=True, courses__status='published')\
        .annotate(course_count=Count('courses')).filter(course_count__gt=0)\
        .order_by('-course_count')[:8]
    
    # Add mock courses if no real courses exist (for design preview)
    show_mock_data = request.GET.get('show_mock', False) or (len(featured_courses) == 0 and len(new_courses) == 0 and len(popular_courses) == 0)
    
    if show_mock_data:
        # Create mock course objects
        from django.utils.text import slugify
        from collections import namedtuple
        from datetime import datetime, timedelta
        
        MockModule = namedtuple('MockModule', ['title', 'lessons'])
        MockLesson = namedtuple('MockLesson', ['title', 'duration'])
        
        class MockCourse:
            def __init__(self, id, title, description, level, featured=False, view_count=0, image_url=None):
                self.id = id
                self.title = title
                self.description = description
                self.short_description = description[:100] + '...' if len(description) > 100 else description
                self.slug = slugify(title)
                self.level = level
                self.featured = featured
                self.view_count = view_count
                self.published_at = datetime.now() - timedelta(days=id % 30)
                self.image_url = image_url or f'https://placehold.co/800x600?text={slugify(title)}'
                self.lesson_count = id % 10 + 5  # 5-14 lessons
                self.estimated_duration = (id % 5) + 1  # 1-5 hours
                
                # Mock modules and lessons
                self.modules = self._create_mock_modules()
                
            def _create_mock_modules(self):
                modules = []
                module_count = (self.id % 3) + 1  # 1-3 modules
                
                for i in range(module_count):
                    lesson_count = (self.id % 4) + 2  # 2-5 lessons per module
                    lessons = []
                    
                    for j in range(lesson_count):
                        lessons.append(MockLesson(
                            title=f'Lesson {j+1}: Sample lesson title for module {i+1}',
                            duration=f'{(j+1) * 10} mins'
                        ))
                    
                    modules.append(MockModule(
                        title=f'Module {i+1}: Introduction to topic {i+1}',
                        lessons=lessons
                    ))
                
                return modules
                
            def get_level_display(self):
                levels = {
                    'beginner': 'Beginner',
                    'intermediate': 'Intermediate',
                    'advanced': 'Advanced'
                }
                return levels.get(self.level, 'All Levels')
                
            @property
            def image(self):
                # Mock the image property to return an object with a url attribute
                class MockImage:
                    def __init__(self, url):
                        self.url = url
                
                return MockImage(self.image_url)
        
        # Create mock course instances
        mock_courses = [
            MockCourse(1, 'Mazoezi Bora ya Kilimo (Tanzania)', 'Kozi ya vitendo ya GAP kwa wakulima wadogo Tanzania: udongo, maji, upandaji, IPM, uvunaji, baada ya mavuno, kumbukumbu, masoko, usalama, na mbinu za tabianchi — bila kutegemea mbolea za viwandani.', 'beginner', True, 1500, 'https://placehold.co/800x600/2A9D8F/FFF?text=Kilimo+Tanzania'),
            MockCourse(2, 'Usimamizi wa Maji Shambani', 'Mbinu za kuhifadhi na kusimamia maji shambani, pamoja na teknolojia za umwagiliaji nafuu kwa wakulima wadogo.', 'intermediate', True, 1200, 'https://placehold.co/800x600/264653/FFF?text=Usimamizi+wa+Maji'),
            MockCourse(3, 'Kilimo cha Mbogamboga', 'Jifunze mbinu za kupanda, kutunza na kuvuna mbogamboga kwa uzalishaji wa juu na kibiashara.', 'beginner', False, 950, 'https://placehold.co/800x600/E76F51/FFF?text=Mbogamboga'),
            MockCourse(4, 'Ufugaji wa Kuku Kienyeji', 'Mafunzo kamili kuhusu ufugaji wa kuku wa kienyeji: ulishaji, makazi, magonjwa, masoko na usimamizi wa biashara ndogo.', 'intermediate', False, 1100, 'https://placehold.co/800x600/F4A261/FFF?text=Kuku+Kienyeji'),
            MockCourse(5, 'Ufugaji wa Nyuki na Uzalishaji Asali', 'Mbinu za kisasa za ufugaji nyuki, uvunaji asali na bidhaa zingine za nyuki kwa tija na faida.', 'beginner', True, 880, 'https://placehold.co/800x600/E9C46A/FFF?text=Ufugaji+Nyuki'),
            MockCourse(6, 'Kilimo Kinachostahimili Mabadiliko ya Tabianchi', 'Jifunze mbinu za kupunguza athari za mabadiliko ya tabianchi, ukame na mafuriko kupitia kilimo kinachozingatia mazingira.', 'intermediate', False, 1300, 'https://placehold.co/800x600/2A9D8F/FFF?text=Tabianchi')
        ]
        
        # Update context with mock data
        featured_courses = [c for c in mock_courses if c.featured][:6]
        new_courses = sorted([c for c in mock_courses if not c.featured], key=lambda x: x.published_at, reverse=True)[:6]
        popular_courses = sorted(mock_courses, key=lambda x: x.view_count, reverse=True)[:6]
    
    context = {
        'featured_courses': featured_courses,
        'new_courses': new_courses,
        'popular_courses': popular_courses,
        'categories': categories,
        'organizations': organizations,
        'courses': mock_courses if show_mock_data else (featured_courses or popular_courses or new_courses),  # Show all mock courses if using mock data
        'show_mock_data': show_mock_data
    }
    
    return render(request, 'training/home.html', context)


@login_required
def course_list(request):
    """List all published courses"""
    all_courses = Course.objects.filter(status='published')

    # Search query
    query = request.GET.get('q', '')
    if query:
        all_courses = all_courses.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__name__icontains=query)
        ).distinct()
    
    # Filter options
    level = request.GET.get('level')
    if level:
        all_courses = all_courses.filter(level=level)
    
    organization = request.GET.get('organization')
    if organization:
        all_courses = all_courses.filter(organization__slug=organization)
    
    # Sorting options
    sort = request.GET.get('sort', 'recent')
    if sort == 'popular':
        all_courses = all_courses.order_by('-view_count')
    elif sort == 'rating':
        all_courses = all_courses.annotate(avg_rating=Avg('ratings__rating')).order_by('-avg_rating')
    else:  # Default: recent
        all_courses = all_courses.order_by('-published_at')
    
    # Pagination
    paginator = Paginator(all_courses, 12)  # 12 courses per page
    page = request.GET.get('page')
    try:
        courses = paginator.page(page)
    except PageNotAnInteger:
        courses = paginator.page(1)
    except EmptyPage:
        courses = paginator.page(paginator.num_pages)
    
    # Sidebar filters
    categories = Category.objects.filter(parent__isnull=True).annotate(
        course_count=Count('courses')
    ).filter(course_count__gt=0).order_by('name')
    
    organizations = Organization.objects.filter(courses__status='published')\
        .annotate(course_count=Count('courses')).filter(course_count__gt=0)\
        .order_by('name').distinct()
    
    context = {
        'courses': courses,
        'categories': categories, 
        'organizations': organizations,
        'selected_level': level,
        'selected_org': organization,
        'sort': sort,
        'query': query,
    }
    
    return render(request, 'training/course_list.html', context)


@login_required
def course_list_by_category(request, category_slug):
    """List courses by category"""
    category = get_object_or_404(Category, slug=category_slug)
    
    # Include courses from child categories
    category_ids = [category.id]
    child_categories = category.subcategories.all()
    if child_categories.exists():
        category_ids.extend(child_categories.values_list('id', flat=True))
    
    courses = Course.objects.filter(status='published', category_id__in=category_ids)
    
    # Filter options
    level = request.GET.get('level')
    if level:
        courses = courses.filter(level=level)
    
    # Sorting options
    sort = request.GET.get('sort', 'recent')
    if sort == 'popular':
        courses = courses.order_by('-view_count')
    elif sort == 'rating':
        courses = courses.annotate(avg_rating=Avg('ratings__rating')).order_by('-avg_rating')
    else:  # Default: recent
        courses = courses.order_by('-published_at')
    
    # Pagination
    paginator = Paginator(courses, 12)  # 12 courses per page
    page = request.GET.get('page')
    try:
        courses = paginator.page(page)
    except PageNotAnInteger:
        courses = paginator.page(1)
    except EmptyPage:
        courses = paginator.page(paginator.num_pages)
    
    context = {
        'category': category,
        'courses': courses,
        'child_categories': child_categories,
        'selected_level': level,
        'sort': sort,
    }
    
    return render(request, 'training/course_list_by_category.html', context)


@login_required
def course_list_by_tag(request, tag_slug):
    """List courses by tag"""
    tag = get_object_or_404(Tag, slug=tag_slug)
    courses = Course.objects.filter(status='published', tags=tag)
    
    # Sorting options
    sort = request.GET.get('sort', 'recent')
    if sort == 'popular':
        courses = courses.order_by('-view_count')
    elif sort == 'rating':
        courses = courses.annotate(avg_rating=Avg('ratings__rating')).order_by('-avg_rating')
    else:  # Default: recent
        courses = courses.order_by('-published_at')
    
    # Pagination
    paginator = Paginator(courses, 12)  # 12 courses per page
    page = request.GET.get('page')
    try:
        courses = paginator.page(page)
    except PageNotAnInteger:
        courses = paginator.page(1)
    except EmptyPage:
        courses = paginator.page(paginator.num_pages)
    
    context = {
        'tag': tag,
        'courses': courses,
        'sort': sort,
    }
    
    return render(request, 'training/course_list_by_tag.html', context)


@login_required
def course_list_by_organization(request, organization_slug):
    """List courses by organization"""
    organization = get_object_or_404(Organization, slug=organization_slug)
    courses = Course.objects.filter(status='published', organization=organization)
    
    # Sorting options
    sort = request.GET.get('sort', 'recent')
    if sort == 'popular':
        courses = courses.order_by('-view_count')
    elif sort == 'rating':
        courses = courses.annotate(avg_rating=Avg('ratings__rating')).order_by('-avg_rating')
    else:  # Default: recent
        courses = courses.order_by('-published_at')
    
    # Pagination
    paginator = Paginator(courses, 12)  # 12 courses per page
    page = request.GET.get('page')
    try:
        courses = paginator.page(page)
    except PageNotAnInteger:
        courses = paginator.page(1)
    except EmptyPage:
        courses = paginator.page(paginator.num_pages)
    
    context = {
        'organization': organization,
        'courses': courses,
        'sort': sort,
    }
    
    return render(request, 'training/course_list_by_organization.html', context)


@login_required
def course_search(request):
    """Search courses"""
    query = request.GET.get('q', '')
    courses = None
    
    if query:
        courses = Course.objects.filter(
            Q(title__icontains=query) | 
            Q(subtitle__icontains=query) | 
            Q(description__icontains=query) | 
            Q(instructor_name__icontains=query) |
            Q(organization__name__icontains=query),
            status='published'
        ).distinct()
        
        # Sorting options
        sort = request.GET.get('sort', 'relevance')
        if sort == 'popular':
            courses = courses.order_by('-view_count')
        elif sort == 'rating':
            courses = courses.annotate(avg_rating=Avg('ratings__rating')).order_by('-avg_rating')
        elif sort == 'recent':
            courses = courses.order_by('-published_at')
        # Default is relevance, no specific sorting
        
        # Pagination
        paginator = Paginator(courses, 12)  # 12 courses per page
        page = request.GET.get('page')
        try:
            courses = paginator.page(page)
        except PageNotAnInteger:
            courses = paginator.page(1)
        except EmptyPage:
            courses = paginator.page(paginator.num_pages)
    
    context = {
        'query': query,
        'courses': courses,
        'sort': request.GET.get('sort', 'relevance'),
    }
    
    return render(request, 'training/course_search.html', context)


@login_required
def course_detail(request, slug):
    """Course detail view"""
    course = get_object_or_404(Course, slug=slug, status='published')
    
    # Increment view count
    course.view_count += 1
    course.save(update_fields=['view_count'])
    
    # Get modules and lessons
    modules = course.modules.all().order_by('order')
    
    # Check if user is enrolled
    is_enrolled = False
    user_progress = None
    if request.user.is_authenticated:
        try:
            user_progress = UserProgress.objects.get(user=request.user, course=course)
            is_enrolled = True
        except UserProgress.DoesNotExist:
            pass
    
    # Get ratings and reviews
    ratings = course.ratings.all().order_by('-created_at')[:5]
    avg_rating = ratings.aggregate(avg=Avg('rating'))['avg'] or 0
    rating_count = course.ratings.count()
    
    # Check if user has already rated
    user_has_rated = False
    if request.user.is_authenticated:
        user_has_rated = course.ratings.filter(user=request.user).exists()
    
    # Related courses (same category)
    related_courses = Course.objects.filter(
        category=course.category, status='published'
    ).exclude(id=course.id).order_by('-published_at')[:4]
    
    context = {
        'course': course,
        'modules': modules,
        'ratings': ratings,
        'avg_rating': avg_rating,
        'rating_count': rating_count,
        'is_enrolled': is_enrolled,
        'user_progress': user_progress,
        'user_has_rated': user_has_rated,
        'related_courses': related_courses,
    }
    
    return render(request, 'training/course_detail.html', context)


@login_required
def module_detail(request, course_slug, module_id):
    """Module detail view"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    module = get_object_or_404(Module, id=module_id, course=course)
    
    # Get lessons
    lessons = module.lessons.all().order_by('order')
    
    # Check user progress
    lesson_progress = {}
    if request.user.is_authenticated:
        progress_objects = LessonProgress.objects.filter(
            user=request.user, lesson__module=module
        )
        for progress in progress_objects:
            lesson_progress[progress.lesson.id] = progress
    
    context = {
        'course': course,
        'module': module,
        'lessons': lessons,
        'lesson_progress': lesson_progress,
    }
    
    return render(request, 'training/module_detail.html', context)


@login_required
def lesson_detail(request, course_slug, lesson_slug):
    """Lesson detail view"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    lesson = get_object_or_404(Lesson, slug=lesson_slug, module__course=course)
    
    # Increment view count
    lesson.view_count += 1
    lesson.save(update_fields=['view_count'])
    
    # Get module and other lessons in module
    module = lesson.module
    lessons_in_module = module.lessons.all().order_by('order')
    
    # Get attachments
    attachments = lesson.attachments.all().order_by('order')
    
    # Get next and previous lessons
    next_lesson = None
    prev_lesson = None
    for i, l in enumerate(lessons_in_module):
        if l.id == lesson.id:
            if i > 0:
                prev_lesson = lessons_in_module[i-1]
            if i < len(lessons_in_module) - 1:
                next_lesson = lessons_in_module[i+1]
            break
    
    # Get or create lesson progress
    lesson_progress = None
    if request.user.is_authenticated:
        lesson_progress, created = LessonProgress.objects.get_or_create(
            user=request.user, lesson=lesson,
            defaults={'status': 'in_progress'}
        )
        
        # If not created now but status was 'not_started', update to 'in_progress'
        if not created and lesson_progress.status == 'not_started':
            lesson_progress.status = 'in_progress'
            lesson_progress.save()
    
    context = {
        'course': course,
        'module': module,
        'lesson': lesson,
        'lessons_in_module': lessons_in_module,
        'attachments': attachments,
        'next_lesson': next_lesson,
        'prev_lesson': prev_lesson,
        'lesson_progress': lesson_progress,
    }
    
    return render(request, 'training/lesson_detail.html', context)


@login_required
def my_courses(request):
    """Show user's enrolled courses"""
    user_courses = UserProgress.objects.filter(user=request.user).select_related('course')
    
    # Filter by status if requested
    status_filter = request.GET.get('status')
    if status_filter and status_filter in ['not_started', 'in_progress', 'completed']:
        user_courses = user_courses.filter(status=status_filter)
    
    # Sort by last accessed by default
    user_courses = user_courses.order_by('-last_accessed')
    
    # Get certificates
    certificates = Certificate.objects.filter(user=request.user)
    cert_course_ids = certificates.values_list('course_id', flat=True)
    
    context = {
        'user_courses': user_courses,
        'certificates': certificates,
        'cert_course_ids': cert_course_ids,
        'status_filter': status_filter or 'all',
    }
    
    return render(request, 'training/my_courses.html', context)


@login_required
def enroll_course(request, course_slug):
    """Enroll in a course"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Check if already enrolled
    if UserProgress.objects.filter(user=request.user, course=course).exists():
        messages.info(request, _('You are already enrolled in this course.'))
        return redirect('training:course_detail', slug=course_slug)
    
    # Create enrollment
    UserProgress.objects.create(user=request.user, course=course, status='not_started')
    
    messages.success(request, _('Successfully enrolled in this course.'))
    return redirect('training:course_detail', slug=course_slug)


@login_required
@require_POST
def mark_lesson_completed(request, course_slug, lesson_slug):
    """Mark a lesson as completed"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    lesson = get_object_or_404(Lesson, slug=lesson_slug, module__course=course)
    
    # Update lesson progress
    lesson_progress, created = LessonProgress.objects.get_or_create(
        user=request.user, lesson=lesson,
        defaults={'status': 'completed', 'completed': True, 'completed_at': timezone.now()}
    )
    
    if not created:
        lesson_progress.status = 'completed'
        lesson_progress.completed = True
        lesson_progress.completed_at = timezone.now()
        lesson_progress.save()
    
    # Update course progress
    course_progress, _ = UserProgress.objects.get_or_create(
        user=request.user, course=course,
        defaults={'status': 'in_progress'}
    )
    
    # Calculate overall course progress
    total_lessons = Lesson.objects.filter(module__course=course).count()
    completed_lessons = LessonProgress.objects.filter(
        user=request.user, lesson__module__course=course, completed=True
    ).count()
    
    if total_lessons > 0:
        progress_percent = int((completed_lessons / total_lessons) * 100)
        course_progress.progress_percent = progress_percent
        
        # Check if course is completed
        if completed_lessons == total_lessons:
            course_progress.status = 'completed'
            course_progress.completed_at = timezone.now()
            
            # Generate certificate if course has certificate option
            if course.has_certificate and not Certificate.objects.filter(user=request.user, course=course).exists():
                Certificate.objects.create(user=request.user, course=course)
        else:
            course_progress.status = 'in_progress'
            
        course_progress.save()
    
    # If AJAX request, return JSON response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'progress_percent': course_progress.progress_percent})
    
    # Otherwise redirect to next lesson if available
    next_lesson = Lesson.objects.filter(
        module__course=course, order__gt=lesson.order, module=lesson.module
    ).order_by('order').first()
    
    if not next_lesson:
        # Try to get first lesson of next module
        next_module = Module.objects.filter(
            course=course, order__gt=lesson.module.order
        ).order_by('order').first()
        
        if next_module:
            next_lesson = next_module.lessons.order_by('order').first()
    
    if next_lesson:
        return redirect('training:lesson_detail', course_slug=course_slug, lesson_slug=next_lesson.slug)
    else:
        return redirect('training:course_detail', slug=course_slug)


@login_required
def generate_certificate(request, course_slug):
    """Generate/view certificate for a completed course"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Check if user has completed the course
    try:
        progress = UserProgress.objects.get(user=request.user, course=course)
        if progress.status != 'completed':
            messages.error(request, _('You need to complete this course to get a certificate.'))
            return redirect('training:course_detail', slug=course_slug)
    except UserProgress.DoesNotExist:
        messages.error(request, _('You are not enrolled in this course.'))
        return redirect('training:course_detail', slug=course_slug)
    
    # Get or create certificate
    certificate, created = Certificate.objects.get_or_create(
        user=request.user, course=course
    )
    
    context = {
        'certificate': certificate,
        'course': course,
    }
    
    return render(request, 'training/certificate.html', context)


def organization_list(request):
    """List all verified organizations"""
    organizations = Organization.objects.filter(is_verified=True)\
        .annotate(course_count=Count('courses', filter=Q(courses__status='published')))\
        .filter(course_count__gt=0).order_by('name')
    
    # Pagination
    paginator = Paginator(organizations, 12)  # 12 orgs per page
    page = request.GET.get('page')
    try:
        organizations = paginator.page(page)
    except PageNotAnInteger:
        organizations = paginator.page(1)
    except EmptyPage:
        organizations = paginator.page(paginator.num_pages)
    
    context = {
        'organizations': organizations,
    }
    
    return render(request, 'training/organization_list.html', context)


def organization_detail(request, slug):
    """Organization detail view"""
    organization = get_object_or_404(Organization, slug=slug, is_verified=True)
    
    courses = Course.objects.filter(organization=organization, status='published')\
        .order_by('-published_at')
    
    # Pagination
    paginator = Paginator(courses, 9)  # 9 courses per page
    page = request.GET.get('page')
    try:
        courses = paginator.page(page)
    except PageNotAnInteger:
        courses = paginator.page(1)
    except EmptyPage:
        courses = paginator.page(paginator.num_pages)
    
    context = {
        'organization': organization,
        'courses': courses,
    }
    
    return render(request, 'training/organization_detail.html', context)


@login_required
@require_POST
def rate_course(request, course_slug):
    """Rate a course"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Check if user is enrolled
    try:
        UserProgress.objects.get(user=request.user, course=course)
    except UserProgress.DoesNotExist:
        messages.error(request, _('You need to be enrolled in this course to rate it.'))
        return redirect('training:course_detail', slug=course_slug)
    
    # Get or create rating
    try:
        rating = CourseRating.objects.get(user=request.user, course=course)
        form = CourseRatingForm(request.POST, instance=rating)
    except CourseRating.DoesNotExist:
        form = CourseRatingForm(request.POST)
    
    if form.is_valid():
        rating = form.save(commit=False)
        rating.user = request.user
        rating.course = course
        rating.save()
        messages.success(request, _('Your rating has been submitted.'))
    else:
        messages.error(request, _('Error submitting your rating.'))
    
    return redirect('training:course_detail', slug=course_slug)


def organization_submission(request):
    """Form for organizations to submit training materials"""
    if request.method == 'POST':
        form = OrganizationSubmissionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('training:submission_thank_you')
    else:
        form = OrganizationSubmissionForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'training/organization_submission.html', context)


def submission_thank_you(request):
    """Thank you page after submission"""
    return render(request, 'training/submission_thank_you.html')
