"""
Kikapu-Led Registration Sync Services
Handles smart data mapping and synchronization between Kikapu and Mkulima Smart
"""
import re
import json
from typing import Dict, List, Optional, Tuple
from django.contrib.auth import get_user_model
from website.models import Farm, Crop
from django.db import transaction
from django.utils.crypto import get_random_string
from django.utils import timezone

User = get_user_model()


class MkulimaSyncService:
    """
    Service for syncing farmer registrations from Kikapu to Mkulima Smart
    with intelligent data inference and mapping
    """
    
    # Regional phone prefix to location mapping for Tanzania
    PHONE_REGION_MAP = {
        '255': {
            '75': 'Arusha',
            '76': 'Mbeya',
            '77': 'Mwanza',
            '78': 'Dodoma',
            '68': 'Dar es Salaam',
            '69': 'Dar es Salaam',
            '71': 'Kilimanjaro',
            '72': 'Tanga',
            '73': 'Morogoro',
            '74': 'Iringa',
        }
    }
    
    # Common crop keywords for smart prediction
    CROP_KEYWORDS = {
        'maize': ['maize', 'corn', 'mahindi'],
        'beans': ['bean', 'maharagwe'],
        'rice': ['rice', 'mchele'],
        'potato': ['potato', 'viazi'],
        'coffee': ['coffee', 'kahawa'],
        'tea': ['tea', 'chai'],
        'vegetables': ['vegetable', 'mboga', 'tomato', 'onion', 'cabbage'],
        'fruits': ['fruit', 'mango', 'banana', 'orange', 'matunda'],
    }
    
    # Default crop combinations by region
    DEFAULT_CROPS_BY_REGION = {
        'Arusha': ['maize', 'beans', 'coffee'],
        'Mbeya': ['maize', 'beans', 'potato'],
        'Mwanza': ['rice', 'maize', 'vegetables'],
        'Dodoma': ['maize', 'beans'],
        'Kilimanjaro': ['coffee', 'maize', 'beans'],
        'Morogoro': ['rice', 'maize', 'vegetables'],
        'default': ['maize', 'beans']  # Most common in Tanzania
    }
    
    @classmethod
    def infer_location_from_phone(cls, phone_number: str) -> str:
        """
        Infer the farmer's location from their phone number prefix
        
        Args:
            phone_number: The farmer's phone number
            
        Returns:
            Inferred location or 'Tanzania' as default
        """
        # Clean phone number
        clean_phone = re.sub(r'[^\d+]', '', phone_number)
        
        # Handle different phone formats
        if clean_phone.startswith('+255'):
            prefix = clean_phone[4:6]
        elif clean_phone.startswith('255'):
            prefix = clean_phone[3:5]
        elif clean_phone.startswith('0'):
            prefix = clean_phone[1:3]
        else:
            return 'Tanzania'
        
        # Look up region
        return cls.PHONE_REGION_MAP.get('255', {}).get(prefix, 'Tanzania')
    
    @classmethod
    def predict_crops_from_farm_name(cls, farm_name: str, location: str = 'Tanzania') -> List[str]:
        """
        Predict crops based on farm name and location
        
        Args:
            farm_name: Name of the farm
            location: Farm location
            
        Returns:
            List of predicted crop names
        """
        if not farm_name:
            return cls.DEFAULT_CROPS_BY_REGION.get(location, cls.DEFAULT_CROPS_BY_REGION['default'])
        
        farm_name_lower = farm_name.lower()
        predicted_crops = []
        
        # Check for crop keywords in farm name
        for crop, keywords in cls.CROP_KEYWORDS.items():
            if any(keyword in farm_name_lower for keyword in keywords):
                predicted_crops.append(crop)
        
        # If no crops detected from name, use regional defaults
        if not predicted_crops:
            predicted_crops = cls.DEFAULT_CROPS_BY_REGION.get(
                location, 
                cls.DEFAULT_CROPS_BY_REGION['default']
            )
        
        return predicted_crops[:3]  # Return max 3 crops
    
    @classmethod
    def calculate_profile_completion(cls, user_data: Dict) -> Tuple[int, List[str]]:
        """
        Calculate profile completion percentage and list missing fields
        
        Args:
            user_data: Dictionary of user data
            
        Returns:
            Tuple of (completion_percentage, list_of_missing_fields)
        """
        # Define required fields with their weights
        fields = {
            'first_name': 10,
            'last_name': 10,
            'phone_number': 15,
            'email': 5,
            'location': 15,
            'farm_size': 15,
            'crops': 15,
            'farm_type': 5,
            'soil_type': 5,
            'services_needed': 5,
        }
        
        total_weight = sum(fields.values())
        current_weight = 0
        missing_fields = []
        
        for field, weight in fields.items():
            value = user_data.get(field)
            if value and value != '' and value != []:
                current_weight += weight
            else:
                missing_fields.append(field)
        
        completion_percentage = int((current_weight / total_weight) * 100)
        return completion_percentage, missing_fields
    
    @classmethod
    @transaction.atomic
    def sync_from_kikapu(cls, kikapu_data: Dict) -> Dict:
        """
        Sync farmer registration from Kikapu to Mkulima Smart
        Creates a partial profile with intelligent defaults
        
        Args:
            kikapu_data: Registration data from Kikapu
            {
                'phone_number': str,
                'first_name': str,
                'last_name': str,
                'password': str,
                'farm_name': str (optional),
                'kikapu_user_id': str (optional)
            }
            
        Returns:
            Dictionary with sync result and user information
        """
        phone_number = kikapu_data.get('phone_number')
        
        # Check if user already exists
        existing_user = User.objects.filter(phone_number=phone_number).first()
        if existing_user:
            completion_pct = cls._get_user_completion_percentage(existing_user)
            
            # Log sync operation
            from .models import SyncOperation
            SyncOperation.objects.create(
                user=existing_user,
                phone_number=phone_number,
                kikapu_user_id=kikapu_data.get('kikapu_user_id', ''),
                status='already_exists',
                completion_percentage=completion_pct,
                farm_name=kikapu_data.get('farm_name', ''),
                request_data=kikapu_data,
                response_data={'message': 'User already exists'}
            )
            
            return {
                'status': 'already_exists',
                'user_id': existing_user.id,
                'message': 'User already registered on Mkulima Smart',
                'completion_percentage': completion_pct
            }
        
        # Infer location from phone
        inferred_location = cls.infer_location_from_phone(phone_number)
        
        # Predict crops from farm name if provided
        farm_name = kikapu_data.get('farm_name', '')
        predicted_crops = cls.predict_crops_from_farm_name(farm_name, inferred_location)
        
        # Create user with partial profile
        user = User.objects.create_user(
            phone_number=phone_number,
            password=kikapu_data.get('password'),
            first_name=kikapu_data.get('first_name', ''),
            last_name=kikapu_data.get('last_name', ''),
            is_farmer=True,
            is_active=True
        )
        
        # Create default farm with smart defaults
        farm = Farm.objects.create(
            name=farm_name or f"{user.get_full_name()}'s Farm",
            location=inferred_location,
            size=1.0,  # Default 1 hectare for smallholder
            owner=user,
            description=f"Farm synced from Kikapu. Location inferred from phone prefix."
        )
        
        # Create predicted crops
        for crop_name in predicted_crops:
            Crop.objects.create(
                name=crop_name.capitalize(),
                farm=farm,
                description=f"Predicted crop based on location and farm name"
            )
        
        # Generate completion token
        completion_token = get_random_string(32)
        
        # Store sync metadata in user's profile (we can add a JSON field or separate model)
        # For now, we'll return it in the response
        
        # Calculate completion percentage
        user_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone_number': user.phone_number,
            'email': user.email,
            'location': farm.location,
            'farm_size': float(farm.size) if farm.size else None,
            'crops': list(farm.crops.values_list('name', flat=True)),
            'farm_type': '',
            'soil_type': farm.soil_type,
            'services_needed': [],
        }
        
        completion_percentage, missing_fields = cls.calculate_profile_completion(user_data)
        
        # Log sync operation
        from .models import SyncOperation
        sync_op = SyncOperation.objects.create(
            user=user,
            phone_number=phone_number,
            kikapu_user_id=kikapu_data.get('kikapu_user_id', ''),
            status='created_partial',
            inferred_location=inferred_location,
            predicted_crops=predicted_crops,
            completion_percentage=completion_percentage,
            farm_name=farm_name,
            request_data=kikapu_data,
            response_data={
                'user_id': user.id,
                'farm_id': farm.id,
                'completion_percentage': completion_percentage,
                'missing_fields': missing_fields
            }
        )
        
        return {
            'status': 'created_partial',
            'user_id': user.id,
            'farm_id': farm.id,
            'phone_number': user.phone_number,
            'full_name': user.get_full_name(),
            'inferred_location': inferred_location,
            'predicted_crops': predicted_crops,
            'completion_token': completion_token,
            'completion_percentage': completion_percentage,
            'missing_fields': missing_fields,
            'profile_setup_url': f'/auth/complete-profile?token={completion_token}&user_id={user.id}',
            'message': 'User created successfully. Profile completion recommended.'
        }
    
    @classmethod
    def _get_user_completion_percentage(cls, user: User) -> int:
        """Get completion percentage for existing user"""
        farms = user.farms.all()
        if not farms:
            return 30  # Basic info only
        
        farm = farms.first()
        user_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone_number': user.phone_number,
            'email': user.email,
            'location': farm.location,
            'farm_size': float(farm.size) if farm.size else None,
            'crops': list(farm.crops.values_list('name', flat=True)),
            'farm_type': '',
            'soil_type': farm.soil_type,
            'services_needed': [],
        }
        
        completion_percentage, _ = cls.calculate_profile_completion(user_data)
        return completion_percentage
    
    @classmethod
    @transaction.atomic
    def complete_profile(cls, user_id: int, completion_data: Dict) -> Dict:
        """
        Complete a partial farmer profile with additional information
        
        Args:
            user_id: ID of the user to update
            completion_data: Additional profile data
            
        Returns:
            Dictionary with completion result
        """
        try:
            user = User.objects.get(id=user_id)
            farm = user.farms.first()
            
            if not farm:
                return {
                    'status': 'error',
                    'message': 'No farm found for user'
                }
            
            # Update user fields
            if completion_data.get('email'):
                user.email = completion_data['email']
            if completion_data.get('address'):
                user.address = completion_data['address']
            user.save()
            
            # Update farm fields
            if completion_data.get('location'):
                farm.location = completion_data['location']
            if completion_data.get('farm_size'):
                farm.size = completion_data['farm_size']
            if completion_data.get('soil_type'):
                farm.soil_type = completion_data['soil_type']
            if completion_data.get('farm_description'):
                farm.description = completion_data['farm_description']
            farm.save()
            
            # Update crops if provided
            if completion_data.get('crops'):
                # Remove predicted crops
                farm.crops.filter(description__contains='Predicted crop').delete()
                
                # Add confirmed crops
                for crop_name in completion_data['crops']:
                    Crop.objects.get_or_create(
                        name=crop_name,
                        farm=farm,
                        defaults={'description': 'User confirmed crop'}
                    )
            
            # Calculate new completion percentage
            user_data = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone_number': user.phone_number,
                'email': user.email,
                'location': farm.location,
                'farm_size': float(farm.size) if farm.size else None,
                'crops': list(farm.crops.values_list('name', flat=True)),
                'farm_type': '',
                'soil_type': farm.soil_type,
                'services_needed': completion_data.get('services', []),
            }
            
            completion_percentage, missing_fields = cls.calculate_profile_completion(user_data)
            
            # Calculate completion before
            old_user_data = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone_number': user.phone_number,
                'email': '' if not completion_data.get('email') else user.email,
                'location': farm.location if not completion_data.get('location') else '',
                'farm_size': float(farm.size) if farm.size and not completion_data.get('farm_size') else None,
                'crops': [] if completion_data.get('crops') else list(farm.crops.values_list('name', flat=True)),
                'farm_type': '',
                'soil_type': farm.soil_type if not completion_data.get('soil_type') else '',
                'services_needed': [],
            }
            old_completion_percentage, old_missing_fields = cls.calculate_profile_completion(old_user_data)
            
            # Log profile completion
            from .models import ProfileCompletion, SyncOperation, DataAccuracy
            
            # Find the most recent sync operation for this user
            sync_op = SyncOperation.objects.filter(user=user).order_by('-created_at').first()
            
            # Calculate time to complete
            time_to_complete = None
            if sync_op:
                time_to_complete = timezone.now() - sync_op.created_at
            
            # Determine which fields were updated
            fields_updated = [key for key in completion_data.keys() if completion_data[key] and key not in ['user_id', 'token']]
            
            ProfileCompletion.objects.create(
                user=user,
                sync_operation=sync_op,
                completion_percentage_before=old_completion_percentage,
                completion_percentage_after=completion_percentage,
                fields_updated=fields_updated,
                missing_fields_before=old_missing_fields,
                missing_fields_after=missing_fields,
                time_to_complete=time_to_complete,
                updated_data=completion_data
            )
            
            # Track data accuracy if we have predictions
            if sync_op:
                # Location accuracy
                if completion_data.get('location') and sync_op.inferred_location:
                    is_correct = sync_op.inferred_location.lower() in completion_data['location'].lower()
                    DataAccuracy.objects.create(
                        user=user,
                        prediction_type='location',
                        predicted_value={'location': sync_op.inferred_location},
                        actual_value={'location': completion_data['location']},
                        is_correct=is_correct,
                        phone_prefix=user.phone_number[:6] if user.phone_number else '',
                        farm_name=sync_op.farm_name
                    )
                
                # Crop accuracy
                if completion_data.get('crops') and sync_op.predicted_crops:
                    actual_crops = [c.lower() for c in completion_data['crops']]
                    predicted_crops = [c.lower() for c in sync_op.predicted_crops]
                    is_correct = any(crop in actual_crops for crop in predicted_crops)
                    DataAccuracy.objects.create(
                        user=user,
                        prediction_type='crops',
                        predicted_value={'crops': sync_op.predicted_crops},
                        actual_value={'crops': completion_data['crops']},
                        is_correct=is_correct,
                        phone_prefix=user.phone_number[:6] if user.phone_number else '',
                        farm_name=sync_op.farm_name
                    )
                
                # Send webhook to Kikapu with enhanced profile data
                kikapu_user_id = sync_op.kikapu_user_id if sync_op else None
                if kikapu_user_id:
                    try:
                        from .webhooks import send_profile_completion_webhook
                        webhook_result = send_profile_completion_webhook(
                            user=user,
                            kikapu_user_id=kikapu_user_id,
                            completion_percentage=completion_percentage
                        )
                        
                        if webhook_result['success']:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.info(f"Successfully sent profile completion webhook to Kikapu for user {user.id}")
                        elif not webhook_result.get('skipped'):
                            logger.warning(f"Failed to send webhook to Kikapu: {webhook_result.get('error')}")
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Error sending webhook to Kikapu: {str(e)}")
            
            return {
                'status': 'success',
                'user_id': user.id,
                'completion_percentage': completion_percentage,
                'missing_fields': missing_fields,
                'message': 'Profile completed successfully'
            }
            
        except User.DoesNotExist:
            return {
                'status': 'error',
                'message': 'User not found'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
