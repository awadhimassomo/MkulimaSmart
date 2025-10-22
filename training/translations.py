"""
Manual translations for the training app until gettext is properly set up.
This file provides Swahili translations for key UI elements.
"""
from django.utils.translation import gettext_lazy as _

# Common UI elements
TRANSLATIONS = {
    # Navigation and Headers
    'training': _('Mafunzo'),
    'courses': _('Kozi'),
    'categories': _('Kategoria'),
    'organizations': _('Mashirika'),
    'my_courses': _('Kozi Zangu'),
    
    # Course related
    'featured_courses': _('Kozi Zilizoteuliwa'),
    'popular_courses': _('Kozi Maarufu'),
    'new_courses': _('Kozi Mpya'),
    'free_courses': _('Kozi za Bure'),
    'course_details': _('Maelezo ya Kozi'),
    'course_content': _('Yaliyomo Kwenye Kozi'),
    'course_ratings': _('Tathmini za Kozi'),
    'enrollment': _('Usajili'),
    'enroll_now': _('Jiandikishe Sasa'),
    'already_enrolled': _('Tayari Umejiandikisha'),
    
    # Lesson related
    'lessons': _('Masomo'),
    'modules': _('Moduli'),
    'completed': _('Imekamilika'),
    'in_progress': _('Inaendelea'),
    'not_started': _('Bado Kuanza'),
    'mark_complete': _('Weka Alama ya Kukamilika'),
    'next_lesson': _('Somo Linalofuata'),
    'previous_lesson': _('Somo la Awali'),
    
    # Organization related
    'organization_profile': _('Wasifu wa Shirika'),
    'submit_materials': _('Wasilisha Nyenzo za Mafunzo'),
    'organization_submission': _('Mawasilisho ya Shirika'),
    
    # User progress
    'progress': _('Maendeleo'),
    'certificates': _('Vyeti'),
    'download_certificate': _('Pakua Cheti'),
    
    # Actions and buttons
    'submit': _('Wasilisha'),
    'cancel': _('Ghairi'),
    'save': _('Hifadhi'),
    'search': _('Tafuta'),
    'filter': _('Chuja'),
    'sort_by': _('Panga Kwa'),
    'view_all': _('Tazama Zote'),
    
    # Ratings and feedback
    'rate_this_course': _('Kadiria Kozi Hii'),
    'your_rating': _('Ukadiriaji Wako'),
    'leave_a_review': _('Andika Maoni'),
    'reviews': _('Maoni'),
    
    # Status messages
    'success': _('Imefanikiwa'),
    'error': _('Hitilafu'),
    'loading': _('Inapakia...'),
    
    # Pagination
    'next': _('Ifuatayo'),
    'previous': _('Iliyopita'),
    'page': _('Ukurasa'),
    'of': _('ya'),
    
    # Search and filters
    'search_courses': _('Tafuta Kozi'),
    'filter_by_category': _('Chuja Kwa Kategoria'),
    'filter_by_organization': _('Chuja Kwa Shirika'),
    'sort_recent': _('Mpya Zaidi'),
    'sort_popular': _('Maarufu Zaidi'),
    'sort_rating': _('Ukadiriaji wa Juu'),
}

def get_translation(key):
    """Get translation for a key if it exists, otherwise return the key."""
    return TRANSLATIONS.get(key, key)
