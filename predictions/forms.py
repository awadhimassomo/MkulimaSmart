"""
Forms for the predictions app
"""
from django import forms
from website.models import Farm
import datetime


class ManualRainObservationForm(forms.Form):
    """Form for manual rain observations by farmers"""
    farm = forms.ModelChoiceField(
        queryset=Farm.objects.all(),
        help_text="Select your farm"
    )
    date = forms.DateField(
        initial=datetime.date.today,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Date of the rain observation"
    )
    rainfall_mm = forms.FloatField(
        min_value=0,
        max_value=500,  # Reasonable upper limit for daily rainfall
        help_text="Amount of rainfall in millimeters (mm)"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text="Any additional observations (optional)"
    )
    
    def clean_date(self):
        """Ensure date is not in the future"""
        date = self.cleaned_data.get('date')
        if date > datetime.date.today():
            raise forms.ValidationError("Rain observation date cannot be in the future")
        return date
        
    def clean_rainfall_mm(self):
        """Additional validation for rainfall amount"""
        rainfall = self.cleaned_data.get('rainfall_mm')
        if rainfall > 300:
            # This is an extremely high value, add warning but still allow
            self.add_warning('rainfall_mm', 'This is an unusually high rainfall amount. Please verify your measurement.')
        return rainfall
    
    def add_warning(self, field, message):
        """Add a warning message to a field without preventing form submission"""
        if not hasattr(self, '_warnings'):
            self._warnings = {}
        if field not in self._warnings:
            self._warnings[field] = []
        self._warnings[field].append(message)
    
    @property
    def warnings(self):
        """Return any warnings raised during validation"""
        return getattr(self, '_warnings', {})
