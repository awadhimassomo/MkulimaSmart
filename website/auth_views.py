from django.shortcuts import redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, FormView
from django.urls import reverse_lazy
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
import logging
import json

from .forms import FarmerRegistrationForm, FarmerLoginForm

logger = logging.getLogger(__name__)


class FarmerRegistrationView(CreateView):
    """View for farmer registration"""

    form_class = FarmerRegistrationForm
    template_name = 'auth/register_fixed.html'
    success_url = reverse_lazy('website:dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('website:home')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        requested_type = self.request.GET.get("user_type")
        if requested_type in {"farmer", "supplier"}:
            initial["user_type"] = requested_type
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["requested_user_type"] = self.request.GET.get("user_type", "")
        return context

    def form_valid(self, form):
        user_type = form.cleaned_data.get('user_type')
        farm_data = None
        crops = []

        if user_type == 'farmer':
            farm_data = {
                'name': self.request.POST.get('farm_name', f"{form.cleaned_data['first_name']}'s Farm"),
                'location': self.request.POST.get('location', ''),
                'size': float(self.request.POST.get('farm_size', 0) or 0),
                'soil_type': self.request.POST.get('soil_type', ''),
                'description': self.request.POST.get('farm_description', ''),
            }

            crops = self.request.POST.getlist('crops')

            fruits_data = self.request.POST.get('fruits_data', '')
            if fruits_data:
                try:
                    crops.extend(json.loads(fruits_data))
                except Exception:
                    pass

            other_crops_data = self.request.POST.get('other_crops_data', '')
            if other_crops_data:
                try:
                    crops.extend(json.loads(other_crops_data))
                except Exception:
                    pass

        user = form.save(
            commit=True,
            farm_data=farm_data,
            crops_data=crops,
        )
        self.object = user

        login(self.request, user)

        messages.success(self.request, _('Registration successful! Welcome to Mkulima Smart.'))

        logger.info(f"User {user.id} registered successfully")
        if farm_data:
            logger.info(f"Farm: {farm_data.get('name')} - Location: {farm_data.get('location')}")
            logger.info(f"Crops: {', '.join(crops) if crops else 'None'}")

        if user.is_farmer:
            try:
                from authentication.kikapu_sync import sync_new_registration_to_kikapu

                farm = user.farms.first()
                sync_result = sync_new_registration_to_kikapu(user, farm)

                if sync_result['status'] == 'created':
                    logger.info(f"User synced to Kikapu: {sync_result['kikapu_user_id']}")
                elif sync_result['status'] == 'already_exists':
                    logger.info('User already exists on Kikapu; accounts linked')
                else:
                    logger.warning(f"Kikapu sync issue: {sync_result['message']}")
            except Exception as e:
                logger.error(f"Kikapu sync error (non-fatal): {str(e)}")

        if user.is_supplier:
            return redirect('marketplace:supplier_dashboard')

        return redirect(self.success_url)

    def form_invalid(self, form):
        logger.error("=" * 60)
        logger.error("FARMER REGISTRATION - Form Invalid")
        logger.error(f"Errors: {json.dumps(form.errors.as_json(), indent=2)}")
        logger.error("POST Data:")
        for key, value in self.request.POST.items():
            if 'password' not in key.lower():
                logger.error(f"  {key}: {value}")
        logger.error("=" * 60)

        phone_errors = form.errors.get('phone_number', [])
        if phone_errors:
            phone_error_text = ' '.join(str(error) for error in phone_errors)
            messages.error(self.request, phone_error_text)
        else:
            messages.error(self.request, _('Please correct the errors below.'))

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["requested_user_type"] = self.request.GET.get("user_type", "")
        return context

    def form_valid(self, form):
        phone_number = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        user = authenticate(self.request, phone_number=phone_number, password=password)

        if user is not None and (user.is_farmer or user.is_supplier or user.is_staff):
            login(self.request, user)
            messages.success(
                self.request,
                _('Successfully logged in as %(name)s') % {'name': user.get_full_name() or user.phone_number},
            )
            if user.is_supplier:
                return redirect('marketplace:supplier_dashboard')
            return super().form_valid(form)

        messages.error(self.request, _('Invalid phone number or password.'))
        return self.form_invalid(form)


def logout_view(request):
    """Log out the current user"""
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, _('You have been logged out.'))
    return redirect('website:home')


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
