from django.urls import path
from . import views

app_name = 'training'

urlpatterns = [
    # Home/landing page for training platform
    path('', views.training_home, name='home'),
    
    # Course listings
    path('courses/', views.course_list, name='course_list'),
    path('courses/category/<slug:category_slug>/', views.course_list_by_category, name='course_list_by_category'),
    path('courses/tag/<slug:tag_slug>/', views.course_list_by_tag, name='course_list_by_tag'),
    path('courses/organization/<slug:organization_slug>/', views.course_list_by_organization, name='course_list_by_organization'),
    path('courses/search/', views.course_search, name='course_search'),
    
    # Course detail and lessons
    path('course/<slug:slug>/', views.course_detail, name='course_detail'),
    path('course/<slug:course_slug>/module/<int:module_id>/', views.module_detail, name='module_detail'),
    path('course/<slug:course_slug>/lesson/<slug:lesson_slug>/', views.lesson_detail, name='lesson_detail'),
    
    # User progress and enrollments
    path('my-courses/', views.my_courses, name='my_courses'),
    path('enroll/<slug:course_slug>/', views.enroll_course, name='enroll_course'),
    path('mark-completed/<slug:course_slug>/<slug:lesson_slug>/', views.mark_lesson_completed, name='mark_lesson_completed'),
    path('certificate/<slug:course_slug>/', views.generate_certificate, name='generate_certificate'),
    
    # Organizations
    path('organizations/', views.organization_list, name='organization_list'),
    path('organization/<slug:slug>/', views.organization_detail, name='organization_detail'),
    
    # Course ratings and reviews
    path('rate-course/<slug:course_slug>/', views.rate_course, name='rate_course'),
    
    # Organization submission form
    path('submit-training/', views.organization_submission, name='organization_submission'),
    path('submit-training/thank-you/', views.submission_thank_you, name='submission_thank_you'),
]
