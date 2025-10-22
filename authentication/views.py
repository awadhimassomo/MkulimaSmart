"""  
Authentication views for Mkulima Smart
Handles Kikapu-Led Registration sync and profile completion
"""
import json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.core.cache import cache
from .services import MkulimaSyncService
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def sync_register_from_kikapu(request):
    """
    API endpoint for Kikapu to register farmers on Mkulima Smart
    Creates a partial profile with intelligent defaults
    
    POST /api/auth/farmer/sync-register
    
    Request Body:
    {
        "phone_number": "+255712345678",
        "first_name": "John",
        "last_name": "Doe",
        "password": "secure_password",
        "farm_name": "Green Valley Farm" (optional),
        "kikapu_user_id": "12345" (optional)
    }
    
    Returns:
    {
        "status": "created_partial" | "already_exists" | "error",
        "user_id": int,
        "completion_token": str,
        "completion_percentage": int,
        "profile_setup_url": str,
        "message": str
    }
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['phone_number', 'password']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return JsonResponse({
                'status': 'error',
                'message': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=400)
        
        # Sync from Kikapu
        result = MkulimaSyncService.sync_from_kikapu(data)
        
        # Store completion token in cache for 7 days
        if result.get('completion_token'):
            cache_key = f"profile_completion_{result['completion_token']}"
            cache.set(cache_key, result['user_id'], timeout=60*60*24*7)  # 7 days
        
        # Log the sync
        logger.info(f"Kikapu sync: {result['status']} - User {result.get('user_id')} - Phone {data['phone_number']}")
        
        status_code = 200 if result['status'] != 'error' else 400
        return JsonResponse(result, status=status_code)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Kikapu sync error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


def profile_completion_page(request):
    """
    Render the profile completion page for synced users
    Shows pre-filled data and prompts for missing information
    
    GET /auth/complete-profile?token=<completion_token>&user_id=<user_id>
    """
    token = request.GET.get('token')
    user_id = request.GET.get('user_id')
    
    if not token or not user_id:
        return render(request, 'auth/error.html', {
            'error_title': 'Invalid Link',
            'error_message': 'Profile completion link is invalid or expired.'
        })
    
    # Verify token
    cache_key = f"profile_completion_{token}"
    cached_user_id = cache.get(cache_key)
    
    if not cached_user_id or str(cached_user_id) != str(user_id):
        return render(request, 'auth/error.html', {
            'error_title': 'Expired Link',
            'error_message': 'This profile completion link has expired. Please login to complete your profile.'
        })
    
    try:
        user = User.objects.get(id=user_id)
        farm = user.farms.first()
        
        # Get current data and missing fields
        user_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone_number': user.phone_number,
            'email': user.email,
            'location': farm.location if farm else '',
            'farm_size': float(farm.size) if farm and farm.size else 1.0,
            'crops': list(farm.crops.values_list('name', flat=True)) if farm else [],
            'soil_type': farm.soil_type if farm else '',
        }
        
        completion_percentage, missing_fields = MkulimaSyncService.calculate_profile_completion(user_data)
        
        context = {
            'user': user,
            'farm': farm,
            'user_data': user_data,
            'completion_percentage': completion_percentage,
            'missing_fields': missing_fields,
            'token': token,
            'available_crops': ['Maize', 'Beans', 'Rice', 'Potato', 'Coffee', 'Tea', 'Vegetables', 'Fruits'],
            'soil_types': ['Clay', 'Sandy', 'Loam', 'Volcanic', 'Black Cotton'],
        }
        
        return render(request, 'auth/profile_completion.html', context)
        
    except User.DoesNotExist:
        return render(request, 'auth/error.html', {
            'error_title': 'User Not Found',
            'error_message': 'User account not found. Please register again.'
        })


@csrf_exempt
@require_http_methods(["POST"])
def complete_profile_submit(request):
    """
    Handle profile completion form submission
    
    POST /api/auth/farmer/complete-profile
    """
    try:
        data = json.loads(request.body)
        
        user_id = data.get('user_id')
        token = data.get('token')
        
        if not user_id or not token:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing user_id or token'
            }, status=400)
        
        # Verify token
        cache_key = f"profile_completion_{token}"
        cached_user_id = cache.get(cache_key)
        
        if not cached_user_id or str(cached_user_id) != str(user_id):
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid or expired token'
            }, status=400)
        
        # Complete profile
        result = MkulimaSyncService.complete_profile(user_id, data)
        
        # Invalidate token after successful completion
        if result['status'] == 'success':
            cache.delete(cache_key)
            logger.info(f"Profile completed for user {user_id}")
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Profile completion error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def check_sync_status(request):
    """
    Check if a phone number is already registered on Mkulima Smart
    
    GET /api/auth/check-sync?phone=<phone_number>
    """
    phone_number = request.GET.get('phone')
    
    if not phone_number:
        return JsonResponse({
            'status': 'error',
            'message': 'Phone number is required'
        }, status=400)
    
    user = User.objects.filter(phone_number=phone_number).first()
    
    if user:
        completion_percentage = MkulimaSyncService._get_user_completion_percentage(user)
        return JsonResponse({
            'status': 'exists',
            'user_id': user.id,
            'registered': True,
            'completion_percentage': completion_percentage,
            'needs_completion': completion_percentage < 100
        })
    else:
        return JsonResponse({
            'status': 'not_found',
            'registered': False
        })
