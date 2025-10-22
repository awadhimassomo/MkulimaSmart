from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, FormView
from django.urls import reverse_lazy
from django.contrib.auth.views import (
    PasswordResetView, 
    PasswordResetDoneView, 
    PasswordResetConfirmView,
    PasswordResetCompleteView
)
import logging
import json

from .forms import FarmerRegistrationForm, FarmerLoginForm

logger = logging.getLogger(__name__)

class FarmerRegistrationView(CreateView):
    """View for farmer registration"""
    form_class = FarmerRegistrationForm
    template_name = 'auth/register.html'
    success_url = reverse_lazy('website:dashboard')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('website:home')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        # Extract farm and crop data from POST
        farm_data = {
            'name': self.request.POST.get('farm_name', f"{form.cleaned_data['first_name']}'s Farm"),
            'location': self.request.POST.get('location', ''),
            'size': float(self.request.POST.get('farm_size', 0) or 0),
            'soil_type': self.request.POST.get('soil_type', ''),
            'description': self.request.POST.get('farm_description', '')
        }
        
        # Extract crops from checkboxes
        crops = self.request.POST.getlist('crops')  # Get all checked crops
        
        # Add dynamic fruits if provided
        fruits_data = self.request.POST.get('fruits_data', '')
        if fruits_data:
            try:
                import json
                fruits = json.loads(fruits_data)
                crops.extend(fruits)
            except:
                pass
        
        # Add other crops if provided
        other_crops_data = self.request.POST.get('other_crops_data', '')
        if other_crops_data:
            try:
                import json
                other_crops = json.loads(other_crops_data)
                crops.extend(other_crops)
            except:
                pass
        
        # Save user with farm and crops
        user = form.save(commit=True, farm_data=farm_data, crops_data=crops)
        self.object = user
        
        # Log in the user
        login(self.request, user)
        
        messages.success(
            self.request, 
            _('Registration successful! Welcome to Mkulima Smart.')
        )
        
        logger.info(f"✅ User {user.id} registered successfully!")
        logger.info(f"Farm: {farm_data.get('name')} - Location: {farm_data.get('location')}")
        logger.info(f"Crops: {', '.join(crops) if crops else 'None'}")
        logger.info("="*60)
        
        # Sync to Kikapu with duplicate prevention
        try:
            from authentication.kikapu_sync import sync_new_registration_to_kikapu
            
            # Get the farm that was just created
            farm = user.farms.first()
            
            # Sync to Kikapu
            sync_result = sync_new_registration_to_kikapu(user, farm)
            
            if sync_result['status'] == 'created':
                logger.info(f"🔄 User synced to Kikapu: {sync_result['kikapu_user_id']}")
            elif sync_result['status'] == 'already_exists':
                logger.info(f"👥 User already exists on Kikapu - accounts linked")
            else:
                logger.warning(f"⚠️ Kikapu sync issue: {sync_result['message']}")
                
        except Exception as e:
            # Don't fail registration if sync fails
            logger.error(f"❌ Kikapu sync error (non-fatal): {str(e)}")
        
        return redirect(self.success_url)
    
    def form_invalid(self, form):
        logger.error("="*60)
        logger.error("FARMER REGISTRATION - Form Invalid")
        logger.error(f"Errors: {json.dumps(form.errors.as_json(), indent=2)}")
        logger.error("POST Data:")
        for key, value in self.request.POST.items():
            if 'password' not in key.lower():
                logger.error(f"  {key}: {value}")
        logger.error("="*60)
        
        messages.error(
            self.request, 
            _('Please correct the errors below.')
        )
        return super().form_invalid(form)


class FarmerLoginView(FormView):
    """View for farmer login"""
    form_class = FarmerLoginForm
    template_name = 'auth/login.html'
    success_url = reverse_lazy('website:dashboard')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('website:home')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        phone_number = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        user = authenticate(
            self.request, 
            phone_number=phone_number, 
            password=password
        )
        
        if user is not None and user.is_farmer:
            login(self.request, user)
            messages.success(
                self.request, 
                _('Successfully logged in as %(name)s') % {'name': user.get_full_name() or user.phone_number}
            )
            return super().form_valid(form)
        else:
            messages.error(
                self.request, 
                _('Invalid phone number or password.')
            )
            return self.form_invalid(form)


def logout_view(request):
    """Log out the current user"""
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, _('You have been logged out.'))
    return redirect('website:home')


# Password Reset Views
class CustomPasswordResetView(PasswordResetView):
    template_name = 'auth/password_reset.html'
    email_template_name = 'auth/emails/password_reset_email.html'
    subject_template_name = 'auth/emails/password_reset_subject.txt'
    success_url = reverse_lazy('website:password_reset_done')


class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'auth/password_reset_done.html'


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'auth/password_reset_confirm.html'
    success_url = reverse_lazy('website:password_reset_complete')


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'auth/password_reset_complete.html'
