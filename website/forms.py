from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import User, Farm, Crop
import json

class FarmerRegistrationForm(UserCreationForm):
    """Form for farmer registration"""
    phone_number = forms.CharField(
        label=_("Phone Number"),
        max_length=15,
        help_text=_("Enter your phone number (e.g., +255XXXXXXXXX)"),
    )
    
    first_name = forms.CharField(
        label=_("First Name"),
        max_length=30,
        required=True,
    )
    
    last_name = forms.CharField(
        label=_("Last Name"),
        max_length=150,
        required=True,
    )
    
    email = forms.EmailField(
        label=_("Email"),
        required=False,
        help_text=_("Optional. Used for password resets and notifications.")
    )
    
    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput,
        help_text=_("Your password must contain at least 8 characters."),
    )
    
    password2 = forms.CharField(
        label=_("Confirm Password"),
        strip=False,
        widget=forms.PasswordInput,
    )
    
    class Meta:
        model = User
        fields = ('phone_number', 'first_name', 'last_name', 'email')
    
    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        # Normalize phone number
        phone_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
        if User.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError(_("A user with this phone number already exists."))
        return phone_number
    
    def save(self, commit=True, farm_data=None, crops_data=None):
        """Save user and optionally create farm and crops"""
        user = super().save(commit=False)
        user.is_farmer = True
        if commit:
            user.save()
            
            # Create farm if farm data provided
            if farm_data:
                farm = Farm.objects.create(
                    owner=user,
                    name=farm_data.get('name', f"{user.get_full_name()}'s Farm"),
                    location=farm_data.get('location', ''),
                    size=farm_data.get('size', 0),
                    soil_type=farm_data.get('soil_type', ''),
                    description=farm_data.get('description', '')
                )
                
                # Create crops if crops data provided
                if crops_data:
                    from django.utils import timezone
                    from datetime import timedelta
                    
                    for crop_name in crops_data:
                        if crop_name and crop_name.strip():
                            Crop.objects.create(
                                farm=farm,
                                name=crop_name.strip(),
                                planting_date=timezone.now().date(),  # Default to today
                                expected_harvest_date=timezone.now().date() + timedelta(days=120),  # Default 4 months from now
                                quantity=0,  # Default quantity
                                is_available_for_sale=False  # Not for sale by default
                            )
        
        return user


class FarmerLoginForm(AuthenticationForm):
    """
    Form for farmer login. Uses phone number instead of username.
    """
    username = forms.CharField(
        label=_("Phone Number"),
        widget=forms.TextInput(attrs={'autofocus': True})
    )
    
    def clean_username(self):
        phone_number = self.cleaned_data.get('username')
        # Normalize phone number
        return ''.join(c for c in phone_number if c.isdigit() or c == '+')
