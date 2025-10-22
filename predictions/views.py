from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, TemplateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.urls import reverse
from django.utils import timezone
from django.db.models import Avg, Count, Q, F, Case, When, Value, FloatField
from django.db.models.functions import Coalesce
from django.contrib import messages
import json
from datetime import timedelta
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action

from website.models import Farm, WeatherData
from .models import CropData, SoilData, PredictionResult, Notification
from .serializers import CropDataSerializer, SoilDataSerializer, PredictionResultSerializer, PredictionRequestSerializer, NotificationSerializer
from .prediction_engine import PredictionManager
from .forms import ManualRainObservationForm

import logging
logger = logging.getLogger(__name__)


class CropDataViewSet(viewsets.ModelViewSet):
    """API endpoint for crop data"""
    queryset = CropData.objects.all()
    serializer_class = CropDataSerializer
    
    def get_queryset(self):
        """Filter by farm_id if provided"""
        queryset = CropData.objects.all()
        farm_id = self.request.query_params.get('farm_id')
        if farm_id:
            queryset = queryset.filter(farm_id=farm_id)
        return queryset


class SoilDataViewSet(viewsets.ModelViewSet):
    """API endpoint for soil data"""
    queryset = SoilData.objects.all()
    serializer_class = SoilDataSerializer
    
    def get_queryset(self):
        """Filter by farm_id if provided"""
        queryset = SoilData.objects.all()
        farm_id = self.request.query_params.get('farm_id')
        if farm_id:
            queryset = queryset.filter(farm_id=farm_id)
        return queryset


class PredictionResultViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for prediction results (read-only)"""
    queryset = PredictionResult.objects.all()
    serializer_class = PredictionResultSerializer
    
    def get_queryset(self):
        """Filter by farm_id and type if provided"""
        queryset = PredictionResult.objects.all()
        
        farm_id = self.request.query_params.get('farm_id')
        if farm_id:
            queryset = queryset.filter(farm_id=farm_id)
            
        pred_type = self.request.query_params.get('type')
        if pred_type:
            queryset = queryset.filter(type=pred_type)
            
        return queryset
    
    @action(detail=False, methods=['get'])
    def latest(self, request):
        """Get the latest prediction for each type for a farm"""
        farm_id = request.query_params.get('farm_id')
        if not farm_id:
            return Response({"error": "farm_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            farm = Farm.objects.get(pk=farm_id)
        except Farm.DoesNotExist:
            return Response({"error": f"Farm with id {farm_id} not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Get the latest prediction for each type
        latest_predictions = {}
        for pred_type in ['rainfall', 'yield', 'pest', 'irrigation', 'planting']:
            try:
                prediction = PredictionResult.objects.filter(farm=farm, type=pred_type).latest('created_at')
                latest_predictions[pred_type] = PredictionResultSerializer(prediction).data
            except PredictionResult.DoesNotExist:
                latest_predictions[pred_type] = None
                
        return Response(latest_predictions)


class GeneratePredictionView(APIView):
    """API endpoint for generating predictions on demand"""
    
    def post(self, request, format=None):
        """Generate a prediction"""
        serializer = PredictionRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        farm_id = serializer.validated_data['farm_id']
        pred_type = serializer.validated_data['type']
        
        try:
            farm = Farm.objects.get(pk=farm_id)
        except Farm.DoesNotExist:
            return Response({"error": f"Farm with id {farm_id} not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Initialize prediction manager
        manager = PredictionManager()
        
        # Generate prediction based on type
        success = False
        if pred_type == 'rainfall':
            days = serializer.validated_data.get('days', 14)
            success = manager.forecast_rainfall(farm_id, days=days)
            
        elif pred_type == 'pest':
            crop_type = serializer.validated_data.get('crop_type')
            if not crop_type:
                return Response({"error": "crop_type is required for pest/disease predictions"}, status=status.HTTP_400_BAD_REQUEST)
            success = manager.assess_pest_disease_risk(farm_id, crop_type)
            
        elif pred_type == 'yield':
            crop_id = serializer.validated_data.get('crop_id')
            if not crop_id:
                return Response({"error": "crop_id is required for yield predictions"}, status=status.HTTP_400_BAD_REQUEST)
            success = manager.predict_yield(crop_id)
            
        else:
            return Response({"error": f"Prediction type {pred_type} not supported yet"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Return the result
        if success:
            try:
                prediction = PredictionResult.objects.filter(farm=farm, type=pred_type).latest('created_at')
                return Response(PredictionResultSerializer(prediction).data)
            except PredictionResult.DoesNotExist:
                return Response({"error": "Prediction generation failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({"error": "Prediction generation failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RainObservationFormView(FormView):
    """View for manual rain observations by farmers"""
    template_name = 'predictions/rain_observation_form.html'
    form_class = ManualRainObservationForm
    success_url = '/predictions/rain-observation/thanks/'
    
    def form_valid(self, form):
        """Process the valid form data"""
        farm = form.cleaned_data['farm']
        date = form.cleaned_data['date']
        rainfall_mm = form.cleaned_data['rainfall_mm']
        notes = form.cleaned_data.get('notes', '')
        
        # Save the observation to WeatherData
        weather_data = WeatherData.objects.create(
            farm=farm,
            date=date,
            rainfall_mm=rainfall_mm,
            temperature=None,  # Manual rain observations might not include temperature
            humidity=None,     # or humidity
            source='manual_observation',
            notes=notes
        )
        
        # Check if there are any warnings to display
        warnings = getattr(form, 'warnings', {})
        if warnings:
            for field, msgs in warnings.items():
                for msg in msgs:
                    messages.warning(self.request, msg)
        
        # Show success message
        messages.success(
            self.request, 
            f'Rain observation of {rainfall_mm}mm on {date} has been recorded for {farm.name}. '
            f'Thank you for contributing to better weather predictions!'
        )
        
        # Trigger a new rainfall forecast with the new data
        try:
            manager = PredictionManager()
            manager.forecast_rainfall(farm.id)
        except Exception as e:
            logger.error(f"Error updating rainfall forecast: {str(e)}")
        
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        """Add extra context for the template"""
        context = super().get_context_data(**kwargs)
        context['title'] = 'Record Rain Observation'
        context['description'] = 'Your rain observations help us improve weather predictions for all farmers.'
        return context


def rain_observation_thanks(request):
    """Thank you page after submitting a rain observation"""
    return render(request, 'predictions/rain_observation_thanks.html', {
        'title': 'Thank You',
        'message': 'Your rain observation has been recorded and will help improve our predictions.'
    })


class NotificationViewSet(viewsets.ModelViewSet):
    """API endpoint for user notifications"""
    serializer_class = NotificationSerializer
    
    def get_queryset(self):
        """Filter notifications to only show those belonging to the current user"""
        user = self.request.user
        queryset = Notification.objects.filter(user=user)
        
        # Filter by read/unread if specified
        read_status = self.request.query_params.get('read')
        if read_status == 'true':
            queryset = queryset.filter(read_at__isnull=False)
        elif read_status == 'false':
            queryset = queryset.filter(read_at__isnull=True)
            
        # Filter by category if specified
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
            
        # Filter by priority if specified
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
            
        return queryset
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'status': 'notification marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        user = request.user
        count = Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=timezone.now())
        return Response({'status': f'{count} notifications marked as read'})


class NotificationDashboardView(LoginRequiredMixin, ListView):
    """Dashboard view for user notifications"""
    model = Notification
    template_name = 'predictions/notifications_dashboard.html'
    context_object_name = 'notifications'
    paginate_by = 10
    
    def get_queryset(self):
        """Get notifications for the current user"""
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        """Add additional context for the template"""
        context = super().get_context_data(**kwargs)
        context['unread_count'] = Notification.objects.filter(user=self.request.user, read_at__isnull=True).count()
        context['title'] = 'Notification Dashboard'
        return context


class NotificationDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a notification"""
    model = Notification
    template_name = 'predictions/notification_detail.html'
    context_object_name = 'notification'
    
    def get_object(self, queryset=None):
        """Get the notification and mark it as read"""
        obj = super().get_object(queryset)
        if not obj.is_read:
            obj.mark_as_read()
        return obj
    
    def get_context_data(self, **kwargs):
        """Add additional context for the template"""
        context = super().get_context_data(**kwargs)
        context['title'] = self.object.title
        return context


@login_required
def mark_notification_read(request, pk):
    """Mark a notification as read and redirect back to referrer"""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_as_read()
    
    # Redirect back to the referring page or notifications dashboard
    redirect_url = request.META.get('HTTP_REFERER')
    if not redirect_url:
        redirect_url = reverse('predictions:notifications_dashboard')
    
    return redirect(redirect_url)


@login_required
def mark_all_notifications_read(request):
    """Mark all notifications for the current user as read"""
    count = Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    
    messages.success(request, f'{count} notification(s) marked as read.')
    
    # Redirect back to the referring page or notifications dashboard
    redirect_url = request.META.get('HTTP_REFERER')
    if not redirect_url:
        redirect_url = reverse('predictions:notifications_dashboard')
    
    return redirect(redirect_url)


# Admin Dashboard Views
def is_admin(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(is_admin)
def prediction_quality_dashboard(request):
    """Admin dashboard view for monitoring prediction quality"""
    from .models import RainPrediction, RainObservation, Farm
    
    # Date ranges
    today = timezone.now().date()
    last_week = today - timedelta(days=7)
    last_month = today - timedelta(days=30)
    
    # Basic statistics
    total_predictions = RainPrediction.objects.count()
    total_last_week = RainPrediction.objects.filter(created_at__gte=last_week).count()
    total_previous_week = RainPrediction.objects.filter(
        created_at__lt=last_week,
        created_at__gte=last_week - timedelta(days=7)
    ).count()
    
    # Calculate prediction trend (percent change)
    if total_previous_week > 0:
        prediction_trend = ((total_last_week - total_previous_week) / total_previous_week) * 100
    else:
        prediction_trend = 0
    
    # Manual observations
    manual_observations = RainObservation.objects.filter(source='manual').count()
    observations_last_month = RainObservation.objects.filter(
        source='manual',
        date__gte=last_month
    ).count()
    observations_previous_month = RainObservation.objects.filter(
        source='manual',
        date__lt=last_month,
        date__gte=last_month - timedelta(days=30)
    ).count()
    
    # Calculate observation trend
    if observations_previous_month > 0:
        observation_trend = ((observations_last_month - observations_previous_month) / 
                            observations_previous_month) * 100
    else:
        observation_trend = 0
    
    # Accuracy calculation
    # For simplicity, we'll define accuracy as the percentage of predictions that correctly 
    # predicted rain when it actually rained, or no rain when it didn't rain
    predictions_with_observations = RainPrediction.objects.filter(
        end_date__lte=today
    ).annotate(
        has_rain_obs=Coalesce(Count('rainobservation'), 0),
        actual_value=Case(
            When(rainobservation__did_rain=True, then=Value(1)),
            When(rainobservation__did_rain=False, then=Value(0)),
            default=None,
            output_field=FloatField()
        )
    ).exclude(actual_value=None)
    
    correct_predictions = predictions_with_observations.filter(
        Q(predicted_value__gt=0.5, actual_value=1) | 
        Q(predicted_value__lte=0.5, actual_value=0)
    ).count()
    
    total_evaluated = predictions_with_observations.count()
    accuracy_pct = round((correct_predictions / total_evaluated * 100) if total_evaluated > 0 else 0)
    
    # Calculate accuracy trend
    last_month_predictions = predictions_with_observations.filter(created_at__gte=last_month)
    last_month_correct = last_month_predictions.filter(
        Q(predicted_value__gt=0.5, actual_value=1) | 
        Q(predicted_value__lte=0.5, actual_value=0)
    ).count()
    
    prev_month_predictions = predictions_with_observations.filter(
        created_at__lt=last_month,
        created_at__gte=last_month - timedelta(days=30)
    )
    prev_month_correct = prev_month_predictions.filter(
        Q(predicted_value__gt=0.5, actual_value=1) | 
        Q(predicted_value__lte=0.5, actual_value=0)
    ).count()
    
    last_month_accuracy = (last_month_correct / last_month_predictions.count() * 100) if last_month_predictions.count() > 0 else 0
    prev_month_accuracy = (prev_month_correct / prev_month_predictions.count() * 100) if prev_month_predictions.count() > 0 else 0
    
    accuracy_trend = last_month_accuracy - prev_month_accuracy
    
    # Active farms
    active_farms = Farm.objects.filter(rainprediction__created_at__gte=last_month).distinct().count()
    
    # Prediction types and their accuracy
    prediction_types = ['1-Day', '3-Day', '7-Day', '14-Day', '30-Day']
    prediction_type_accuracy = []
    
    for days in [1, 3, 7, 14, 30]:
        days_predictions = predictions_with_observations.filter(days_ahead=days)
        days_correct = days_predictions.filter(
            Q(predicted_value__gt=0.5, actual_value=1) | 
            Q(predicted_value__lte=0.5, actual_value=0)
        ).count()
        
        type_accuracy = round((days_correct / days_predictions.count() * 100) if days_predictions.count() > 0 else 0)
        prediction_type_accuracy.append(type_accuracy)
    
    # Recent predictions with actual outcomes for display
    recent_predictions = predictions_with_observations.order_by('-created_at')[:10]
    recent_predictions_data = []
    
    for pred in recent_predictions:
        observation = RainObservation.objects.filter(
            date=pred.end_date,
            farm=pred.farm
        ).first()
        
        # Calculate accuracy for this prediction
        prediction_accuracy = None
        if observation:
            predicted_rain = pred.predicted_value > 0.5
            actual_rain = observation.did_rain
            prediction_accuracy = 100 if predicted_rain == actual_rain else 0
        
        recent_predictions_data.append({
            'created_at': pred.created_at,
            'farm': pred.farm,
            'type': f'{pred.days_ahead}-Day',
            'predicted_value': f'{pred.predicted_value:.2f}' if pred.predicted_value > 0.5 else 'No Rain',
            'actual_value': 'Rain' if observation and observation.did_rain else 'No Rain' if observation else None,
            'accuracy': prediction_accuracy
        })
    
    # Convert to JSON for the chart
    prediction_types_json = json.dumps(prediction_types)
    prediction_type_accuracy_json = json.dumps(prediction_type_accuracy)
    
    context = {
        'title': 'Prediction Quality Dashboard',
        'total_predictions': total_predictions,
        'accuracy_pct': accuracy_pct,
        'manual_observations': manual_observations,
        'active_farms': active_farms,
        'prediction_trend': round(prediction_trend),
        'accuracy_trend': round(accuracy_trend),
        'observation_trend': round(observation_trend),
        'prediction_types': prediction_types_json,
        'prediction_type_accuracy': prediction_type_accuracy_json,
        'recent_predictions': recent_predictions_data,
    }
    
    return render(request, 'admin/predictions/dashboard.html', context)
