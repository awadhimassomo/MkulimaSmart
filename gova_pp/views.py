from django.shortcuts import render, get_object_or_404, redirect
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.paginator import Paginator
from functools import wraps
import json
import openai
from django.conf import settings
from .models import FarmerMessage, ImageAnalysis, Alert

# Make credits import optional
try:
    from credits.views import send_card_sms
    CREDITS_AVAILABLE = True
except ImportError:
    CREDITS_AVAILABLE = False
    print("Credits module not available. SMS functionality will be disabled.")

import json
import time
import base64
import requests
import jwt
from datetime import datetime, timedelta
from openai import OpenAI
from django.db.models import Q, Count
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .models import FarmerMessage, GovernmentReply, ImageAnalysis

def government_login_required(view_func):
    """Custom login required decorator that redirects to government login page"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('gova_pp:login')
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'You do not have permission to access the government dashboard.')
            return redirect('gova_pp:login')
        return view_func(request, *args, **kwargs)
    return wrapper

def government_login(request):
    """Login view for government dashboard"""
    if request.user.is_authenticated:
        return redirect('gova_pp:dashboard')
    
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')
        password = request.POST.get('password')
        
        if phone_number and password:
            user = authenticate(request, phone_number=phone_number, password=password)
            if user is not None:
                # Check if user has permission to access government dashboard
                if user.is_staff or user.is_superuser:
                    login(request, user)
                    messages.success(request, f'Welcome to GOV  APP Dashboard, {user.get_full_name() or user.phone_number}!')
                    return redirect('gova_pp:dashboard')
                else:
                    messages.error(request, 'You do not have permission to access the government dashboard.')
            else:
                messages.error(request, 'Invalid phone number or password.')
        else:
            messages.error(request, 'Please enter both phone number and password.')
    
    return render(request, 'gova_pp/login.html')

def government_logout(request):
    """Logout view for government dashboard"""
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('gova_pp:login')

@government_login_required
def dashboard(request):
    """Main GOV APP dashboard"""
    # Get statistics
    total_messages = FarmerMessage.objects.count()
    new_messages = FarmerMessage.objects.filter(status='new').count()
    in_progress_messages = FarmerMessage.objects.filter(status='in_progress').count()
    urgent_messages = FarmerMessage.objects.filter(priority='urgent').count()
    image_requests = FarmerMessage.objects.filter(image_analysis_requested=True).count()
    
    # Get recent messages
    recent_messages = FarmerMessage.objects.select_related('assigned_to').prefetch_related('replies')[:10]
    
    # Get messages assigned to current user
    my_messages = FarmerMessage.objects.filter(assigned_to=request.user, status__in=['new', 'in_progress'])[:5]
    
    # Get recent image analyses
    recent_analyses = ImageAnalysis.objects.select_related('message').order_by('-analyzed_at')[:5]
    
    context = {
        'total_messages': total_messages,
        'new_messages': new_messages,
        'in_progress_messages': in_progress_messages,
        'urgent_messages': urgent_messages,
        'image_requests': image_requests,
        'recent_messages': recent_messages,
        'my_messages': my_messages,
        'recent_analyses': recent_analyses,
    }
    
    return render(request, 'gova_pp/dashboard.html', context)

@government_login_required
def messages_list(request):
    """List all farmer messages with filtering"""
    messages_queryset = FarmerMessage.objects.select_related('assigned_to').prefetch_related('replies')
    
    # Apply filters
    status_filter = request.GET.get('status')
    message_type_filter = request.GET.get('message_type')
    priority_filter = request.GET.get('priority')
    search_query = request.GET.get('search')
    
    if status_filter:
        messages_queryset = messages_queryset.filter(status=status_filter)
    if message_type_filter:
        messages_queryset = messages_queryset.filter(message_type=message_type_filter)
    if priority_filter:
        messages_queryset = messages_queryset.filter(priority=priority_filter)
    if search_query:
        messages_queryset = messages_queryset.filter(
            Q(farmer_name__icontains=search_query) |
            Q(subject__icontains=search_query) |
            Q(message__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(messages_queryset, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'message_type_filter': message_type_filter,
        'priority_filter': priority_filter,
        'search_query': search_query,
        'message_types': FarmerMessage.MESSAGE_TYPES,
        'status_choices': FarmerMessage.STATUS_CHOICES,
        'priority_choices': [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')],
    }
    
    return render(request, 'gova_pp/messages_list.html', context)

@government_login_required
def message_detail(request, message_id):
    """View and reply to a specific farmer message"""
    message = get_object_or_404(FarmerMessage, id=message_id)
    replies = message.replies.all().order_by('created_at')
    
    # Check if message has image analysis
    analysis = None
    try:
        analysis = message.analysis
    except ImageAnalysis.DoesNotExist:
        pass
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'reply':
            reply_text = request.POST.get('reply_text')
            reply_type = request.POST.get('reply_type', 'answer')
            send_sms_option = request.POST.get('send_sms') == 'on'
            
            if reply_text:
                # Create reply
                reply = GovernmentReply.objects.create(
                    message=message,
                    replied_by=request.user,
                    reply_text=reply_text,
                    reply_type=reply_type
                )
                
                # Send SMS if requested
                if message.farmer_phone and CREDITS_AVAILABLE:
                    try:
                        sms_response = send_card_sms(
                            phone_number=message.farmer_phone,
                            message=f"RE: {message.subject}\n\n{reply_text}",
                            sender_id='GOVA-PP',
                            is_unicode=True
                        )
                        # Log SMS response for debugging
                        print(f"SMS Response: {sms_response}")
                    except Exception as e:
                        print(f"Failed to send SMS: {str(e)}")
                        messages.warning(request, "Message sent but SMS notification failed.")
                elif message.farmer_phone and not CREDITS_AVAILABLE:
                    print("SMS not sent: Credits module not available")
                else:
                    messages.success(request, 'Reply sent successfully!')
                
                # Update message status
                message.status = 'replied'
                message.save()
                
                return redirect('gova_pp:message_detail', message_id=message.id)
        
        elif action == 'update_status':
            new_status = request.POST.get('status')
            if new_status in dict(FarmerMessage.STATUS_CHOICES):
                message.status = new_status
                message.save()
                messages.success(request, f'Message status updated to {new_status}')
                return redirect('gova_pp:message_detail', message_id=message.id)
        
        elif action == 'assign':
            message.assigned_to = request.user
            message.status = 'in_progress'
            message.save()
            messages.success(request, 'Message assigned to you!')
            return redirect('gova_pp:message_detail', message_id=message.id)
    
    # Generate JWT token for WebSocket authentication
    payload = {
        'uid': request.user.id,  # Using 'uid' to match the middleware's expected key
        'phone_number': request.user.phone_number,
        'exp': datetime.utcnow() + timedelta(hours=24),
        'thread_id': str(message_id)
    }
    jwt_token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    
    context = {
        'message': message,
        'replies': replies,
        'analysis': analysis,
        'reply_types': [('answer', 'Answer'), ('advice', 'Agricultural Advice'), ('referral', 'Referral'), ('follow_up', 'Follow-up Question')],
        'status_choices': FarmerMessage.STATUS_CHOICES,
        'jwt_token': jwt_token,
    }
    
    return render(request, 'gova_pp/message_detail.html', context)

@login_required
@require_http_methods(["POST"])
def analyze_image(request, message_id):
    """Analyze image using OpenAI Vision API"""
    message = get_object_or_404(FarmerMessage, id=message_id)
    
    if not (message.image_url or message.image_file):
        return JsonResponse({'error': 'No image found for this message'}, status=400)
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=getattr(settings, 'OPENAI_API_KEY', None))
        
        if not client.api_key:
            return JsonResponse({'error': 'OpenAI API key not configured'}, status=500)
        
        start_time = time.time()
        
        # Prepare image input
        image_input = None
        if message.image_url:
            image_input = {
                "type": "image_url",
                "image_url": {
                    "url": message.image_url,
                    "detail": "high"
                }
            }
        elif message.image_file:
            # Convert uploaded file to base64
            with open(message.image_file.path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                image_input = {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "high"
                    }
                }
        
        # Create analysis prompt
        analysis_prompt = (
            "You are an agricultural expert AI assistant. Analyze this image from a farmer and provide:"
            "1. Detailed description of what you see\n"
            "2. Identify any crop diseases, pests, or plant health issues\n"
            "3. Assess soil conditions if visible\n"
            "4. Provide specific agricultural recommendations\n"
            "5. Suggest immediate actions the farmer should take\n\n"
            "Focus on practical, actionable advice for Tanzanian farming conditions."
        )
        
        # Make API call to OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": analysis_prompt},
                    image_input
                ]
            }],
            max_tokens=1000
        )
        
        processing_time = time.time() - start_time
        analysis_text = response.choices[0].message.content
        
        # Extract recommendations and detected issues
        recommendations = ""
        detected_issues = []
        
        # Simple keyword-based categorization
        primary_category = 'other'
        if any(word in analysis_text.lower() for word in ['disease', 'fungal', 'bacterial', 'viral']):
            primary_category = 'crop_disease'
        elif any(word in analysis_text.lower() for word in ['pest', 'insect', 'bug', 'aphid']):
            primary_category = 'pest_infestation'
        elif any(word in analysis_text.lower() for word in ['nutrient', 'deficiency', 'nitrogen', 'phosphorus']):
            primary_category = 'nutrient_deficiency'
        elif any(word in analysis_text.lower() for word in ['soil', 'drainage', 'ph']):
            primary_category = 'soil_condition'
        elif any(word in analysis_text.lower() for word in ['healthy', 'growth', 'plant health']):
            primary_category = 'plant_health'
        elif any(word in analysis_text.lower() for word in ['harvest', 'ripe', 'ready']):
            primary_category = 'harvest_readiness'
        
        # Create or update analysis
        analysis, created = ImageAnalysis.objects.get_or_create(
            message=message,
            defaults={
                'analysis_text': analysis_text,
                'recommendations': recommendations,
                'analyzed_by': request.user,
                'primary_category': primary_category,
                'processing_time': processing_time,
            }
        )
        
        if not created:
            # Update existing analysis
            analysis.analysis_text = analysis_text
            analysis.recommendations = recommendations
            analysis.analyzed_by = request.user
            analysis.primary_category = primary_category
            analysis.processing_time = processing_time
            analysis.analyzed_at = timezone.now()
            analysis.save()
        
        # Mark message as having analysis
        message.image_analysis_requested = True
        message.save()
        
        return JsonResponse({
            'success': True,
            'analysis': {
                'text': analysis_text,
                'category': primary_category,
                'processing_time': round(processing_time, 2),
                'analyzed_at': analysis.analyzed_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Analysis failed: {str(e)}'}, status=500)


@government_login_required
def alerts(request):
    """Alerts management page for sending notifications to farmers"""
    alerts_list = Alert.objects.all()
    
    # Get statistics for context
    total_alerts = alerts_list.count()
    active_alerts = alerts_list.filter(status='active').count()
    draft_alerts = alerts_list.filter(status='draft').count()
    
    # Pagination
    paginator = Paginator(alerts_list, 10)
    page_number = request.GET.get('page')
    alerts_page = paginator.get_page(page_number)
    
    context = {
        'alerts': alerts_page,
        'total_alerts': total_alerts,
        'active_alerts': active_alerts,
        'draft_alerts': draft_alerts,
    }
    
    return render(request, 'gova_pp/alerts.html', context)


@government_login_required
@require_http_methods(["POST"])
def create_alert(request):
    """Create a new alert"""
    try:
        data = json.loads(request.body)
        
        alert = Alert.objects.create(
            title=data.get('title'),
            body=data.get('body'),  # Changed from message to body
            location=data.get('location', ''),
            alert_type=data.get('alert_type', 'general'),
            priority=data.get('priority', 'medium'),
            is_urgent=data.get('is_urgent', False),
            target_regions=data.get('target_regions', ''),
            target_crops=data.get('target_crops', ''),
            scheduled_at=timezone.now() if data.get('send_immediately') else None,
            expires_at=None,
            created_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'alert_id': alert.id,
            'message': 'Alert created successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@government_login_required
@require_http_methods(["POST"])
def send_alert(request, alert_id):
    """Send alert to farmers via SMS"""
    try:
        alert = get_object_or_404(Alert, id=alert_id)
        
        # Get farmers to send to
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Get farmers (users who are not staff/superuser and have phone numbers)
        farmers = User.objects.filter(
            is_staff=False, 
            is_superuser=False,
            phone__isnull=False
        ).exclude(phone='')
        
        sent_count = 0
        failed_count = 0
        
        # Compose SMS message
        sms_message = f"KIKAPU ALERT: {alert.title}\n\n{alert.body}\n\nLocation: {alert.location}\n\nPriority: {alert.get_priority_display()}"
        
        # Send SMS to each farmer
        for farmer in farmers:
            try:
                # Send SMS to farmer if credits module is available
                if hasattr(settings, 'CREDITS_AVAILABLE') and settings.CREDITS_AVAILABLE:
                    try:
                        response = send_card_sms(
                            phone=farmer.phone,
                            message=sms_message,
                            sender="KIKAPU",
                            reference=f"ALERT_{alert.id}_{farmer.id}"
                        )
                        sent_count += 1
                    except Exception as e:
                        print(f"Failed to send SMS to {farmer.phone}: {str(e)}")
                        failed_count += 1
                else:
                    print(f"SMS not sent to {farmer.phone}: Credits module not available")
                    failed_count += 1
                    
            except Exception as e:
                failed_count += 1
                print(f"Failed to send SMS to {farmer.phone}: {e}")
        
        # Update alert status
        alert.status = 'active'
        alert.sms_sent = True
        alert.sms_sent_at = timezone.now()
        alert.recipients_count = sent_count
        alert.save()
        
        return JsonResponse({
            'success': True,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'message': f'Alert sent to {sent_count} farmers successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@government_login_required
@require_http_methods(["POST"])
def delete_alert(request, alert_id):
    """Delete an alert"""
    try:
        alert = get_object_or_404(Alert, id=alert_id)
        alert.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Alert deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@government_login_required
def delete_alert(request, alert_id):
    if request.method == 'POST':
        try:
            alert = Alert.objects.get(id=alert_id)
            alert.delete()
            messages.success(request, 'Alert deleted successfully!')
        except Alert.DoesNotExist:
            messages.error(request, 'Alert not found.')
        except Exception as e:
            messages.error(request, f'Error deleting alert: {str(e)}')
    
    return redirect('gova_pp:alerts')


@government_login_required
def reports(request):
    """Reports dashboard for government officers"""
    from django.utils import timezone
    from django.db.models import Count, Q, Sum
    from datetime import timedelta
    
    # Get date ranges
    now = timezone.now()
    last_30_days = now - timedelta(days=30)
    last_7_days = now - timedelta(days=7)
    
    # Alert statistics
    total_alerts = Alert.objects.count()
    alerts_last_30_days = Alert.objects.filter(timestamp__gte=last_30_days).count()
    alerts_last_7_days = Alert.objects.filter(timestamp__gte=last_7_days).count()
    active_alerts = Alert.objects.filter(status='active').count()
    
    # Alert types breakdown
    alert_types = Alert.objects.values('alert_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # SMS statistics
    sms_sent = Alert.objects.filter(sms_sent=True).count()
    total_recipients = Alert.objects.aggregate(
        total=Sum('recipients_count')
    )['total'] or 0
    
    # Recent alerts for quick overview
    recent_alerts = Alert.objects.order_by('-timestamp')[:5]
    
    # Messages statistics (if available)
    try:
        from .models import Message
        total_messages = Message.objects.count()
        messages_last_30_days = Message.objects.filter(timestamp__gte=last_30_days).count()
        unread_messages = Message.objects.filter(is_read=False).count()
    except:
        total_messages = 0
        messages_last_30_days = 0
        unread_messages = 0
    
    context = {
        'total_alerts': total_alerts,
        'alerts_last_30_days': alerts_last_30_days,
        'alerts_last_7_days': alerts_last_7_days,
        'active_alerts': active_alerts,
        'alert_types': alert_types,
        'sms_sent': sms_sent,
        'total_recipients': total_recipients,
        'recent_alerts': recent_alerts,
        'total_messages': total_messages,
        'messages_last_30_days': messages_last_30_days,
        'unread_messages': unread_messages,
    }
    
    return render(request, 'gova_pp/reports.html', context)


@government_login_required
@require_http_methods(["POST"])
def delete_message_image(request, message_id):
    """Delete image from a farmer message"""
    try:
        message = get_object_or_404(FarmerMessage, id=message_id)
        
        # Delete the image file if it exists
        if message.image_file:
            try:
                message.image_file.delete(save=False)
            except Exception as e:
                print(f"Error deleting image file: {e}")
        
        # Clear image-related fields
        message.image_url = None
        message.image_file = None
        message.has_image = False
        message.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Image deleted successfully'
        })
        
    except FarmerMessage.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Message not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def receive_farmer_message(request):
    """API endpoint to receive messages from Mkulima Smart app"""
    try:
        data = json.loads(request.body)
        
        # Create farmer message
        message = FarmerMessage.objects.create(
            farmer_name=data.get('farmer_name'),
            farmer_phone=data.get('farmer_phone'),
            farmer_location=data.get('farmer_location', ''),
            message_type=data.get('message_type', 'inquiry'),
            subject=data.get('subject'),
            message=data.get('message'),
            priority=data.get('priority', 'medium'),
            has_image=data.get('has_image', False),
            image_url=data.get('image_url'),
            image_analysis_requested=data.get('image_analysis_requested', False)
        )
        
        return JsonResponse({
            'success': True,
            'message_id': message.id,
            'status': 'Message received successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
