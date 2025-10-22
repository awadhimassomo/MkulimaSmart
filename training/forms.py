from django import forms
from django.utils.translation import gettext_lazy as _

from .models import CourseRating, OrganizationSubmission

class CourseRatingForm(forms.ModelForm):
    """
    Form for users to rate and review courses
    """
    class Meta:
        model = CourseRating
        fields = ['rating', 'review']
        widgets = {
            'rating': forms.NumberInput(attrs={
                'min': 1, 
                'max': 5, 
                'class': 'w-full rounded-md'
            }),
            'review': forms.Textarea(attrs={
                'rows': 4, 
                'placeholder': _('Andika maoni yako kuhusu kozi hii...'),
                'class': 'w-full rounded-md'
            })
        }
        labels = {
            'rating': _('Kiwango (1-5)'),
            'review': _('Maoni')
        }

class OrganizationSubmissionForm(forms.ModelForm):
    """
    Form for organizations to submit training materials
    """
    terms_accepted = forms.BooleanField(
        required=True,
        label=_('Nakubali Masharti na Vigezo'),
        error_messages={
            'required': _('Lazima ukubali masharti na vigezo ili kuwasilisha.')
        },
        widget=forms.CheckboxInput(attrs={'class': 'mr-2'})
    )

    class Meta:
        model = OrganizationSubmission
        fields = [
            'organization_name', 'contact_person', 'email', 'phone',
            'course_title', 'course_description', 'category',
            'materials_description', 'sample_url', 'message'
        ]
        widgets = {
            'organization_name': forms.TextInput(attrs={'class': 'w-full rounded-md'}),
            'contact_person': forms.TextInput(attrs={'class': 'w-full rounded-md'}),
            'email': forms.EmailInput(attrs={'class': 'w-full rounded-md'}),
            'phone': forms.TextInput(attrs={'class': 'w-full rounded-md'}),
            'course_title': forms.TextInput(attrs={'class': 'w-full rounded-md'}),
            'course_description': forms.Textarea(attrs={
                'rows': 3, 
                'class': 'w-full rounded-md'
            }),
            'category': forms.Select(attrs={'class': 'w-full rounded-md'}),
            'materials_description': forms.Textarea(attrs={
                'rows': 4, 
                'class': 'w-full rounded-md'
            }),
            'sample_url': forms.URLInput(attrs={'class': 'w-full rounded-md'}),
            'message': forms.Textarea(attrs={
                'rows': 3, 
                'class': 'w-full rounded-md'
            }),
        }
        labels = {
            'organization_name': _('Jina la Shirika'),
            'contact_person': _('Jina la Mtu wa Mawasiliano'),
            'email': _('Barua Pepe'),
            'phone': _('Namba ya Simu'),
            'course_title': _('Kichwa cha Kozi'),
            'course_description': _('Maelezo ya Kozi'),
            'category': _('Kategoria'),
            'materials_description': _('Maelezo ya Nyenzo'),
            'sample_url': _('URL ya Mfano (si lazima)'),
            'message': _('Ujumbe wa Ziada (si lazima)'),
        }
