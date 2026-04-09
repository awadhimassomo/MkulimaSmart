from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils.translation import gettext_lazy as _
from operations.models import InputSeller
from .models import User, Farm, Crop
import json

class FarmerRegistrationForm(UserCreationForm):
    """Form for farmer registration"""
    user_type = forms.ChoiceField(
        label=_("Account Type"),
        choices=[('farmer', 'Farmer'), ('supplier', 'Supplier')],
        required=True,
        help_text=_("Select your account type"),
    )
    
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
    supplier_business_name = forms.CharField(label=_("Business Name"), max_length=255, required=False)
    supplier_location = forms.CharField(label=_("Business Location"), max_length=255, required=False)
    supplier_seller_type = forms.ChoiceField(label=_("Seller Type"), choices=InputSeller.SELLER_TYPE_CHOICES, required=False)
    supplier_products_offered = forms.MultipleChoiceField(
        label=_("Products You Sell"),
        choices=InputSeller.PRODUCT_CATEGORY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    supplier_certification_details = forms.CharField(
        label=_("Certificates or Compliance Details"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_("Optional. Add certificate names, permit numbers, or compliance notes."),
    )
    supplier_certificate_file = forms.FileField(
        label=_("Certificate File"),
        required=False,
        help_text=_("Optional. Upload a certificate, permit, or compliance document."),
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
        fields = ('user_type', 'phone_number', 'first_name', 'last_name', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for _, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("placeholder", field.label)
            elif not isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("placeholder", field.label)
    
    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        # Normalize phone number
        phone_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
        if User.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError(_("A user with this phone number already exists."))
        return phone_number

    def clean(self):
        cleaned_data = super().clean()
        user_type = cleaned_data.get('user_type')

        if user_type in {'farmer', 'supplier'}:
            if not cleaned_data.get('first_name'):
                self.add_error('first_name', _("This field is required for this account type."))
            if not cleaned_data.get('last_name'):
                self.add_error('last_name', _("This field is required for this account type."))

        if user_type == 'supplier':
            if not cleaned_data.get('supplier_business_name'):
                self.add_error('supplier_business_name', _("Business name is required for supplier accounts."))
            if not cleaned_data.get('supplier_location'):
                self.add_error('supplier_location', _("Business location is required for supplier accounts."))
            if not cleaned_data.get('supplier_seller_type'):
                self.add_error('supplier_seller_type', _("Seller type is required for supplier accounts."))
            if not cleaned_data.get('supplier_products_offered'):
                self.add_error('supplier_products_offered', _("Choose at least one product category you sell."))

        return cleaned_data

    def save(self, commit=True, farm_data=None, crops_data=None):
        """Save user and optionally create farm and crops"""
        user = super().save(commit=False)
        
        # Set user type based on selection
        user_type = self.cleaned_data.get('user_type', 'farmer')
        if user_type == 'farmer':
            user.is_farmer = True
            user.is_supplier = False
        elif user_type == 'supplier':
            user.is_farmer = False
            user.is_supplier = True
        
        if commit:
            user.save()
            
            # Create farm only if user is a farmer and farm data is provided
            if user.is_farmer and farm_data:
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
