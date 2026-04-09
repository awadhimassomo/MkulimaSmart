"""
Webhook Service for Kikapu Integration
Sends enhanced profile data back to Kikapu when profiles are completed
"""
import requests
import json
import logging
from typing import Dict, Optional
from django.conf import settings
from django.contrib.auth import get_user_model
from website.models import Farm, Crop

User = get_user_model()
logger = logging.getLogger(__name__)


class KikapuWebhookService:
    """
    Service for sending webhook notifications to Kikapu
    when farmer profiles are completed or updated
    """
    
    def __init__(self):
        self.webhook_url = getattr(settings, 'KIKAPU_WEBHOOK_URL', None)
        self.webhook_secret = getattr(settings, 'KIKAPU_WEBHOOK_SECRET', None)
        self.timeout = getattr(settings, 'KIKAPU_WEBHOOK_TIMEOUT', 10)
        self.max_retries = getattr(settings, 'KIKAPU_WEBHOOK_MAX_RETRIES', 3)
    
    def send_profile_completion(
        self, 
        user: User, 
        kikapu_user_id: Optional[str] = None,
        completion_percentage: int = 100
    ) -> Dict:
        """
        Send profile completion webhook to Kikapu
        
        Args:
            user: The User object
            kikapu_user_id: The original Kikapu user ID
            completion_percentage: Profile completion percentage
            
        Returns:
            Dictionary with webhook delivery status
        """
        if not self.webhook_url:
            logger.warning("Kikapu webhook URL not configured. Skipping webhook.")
            return {
                'success': False,
                'error': 'Webhook URL not configured',
                'skipped': True
            }
        
        # Get user's farm data
        farm = user.farms.first()
        if not farm:
            logger.warning(f"No farm found for user {user.id}. Skipping webhook.")
            return {
                'success': False,
                'error': 'No farm data available',
                'skipped': True
            }
        
        # Prepare enhanced profile data
        payload = self._prepare_payload(user, farm, kikapu_user_id, completion_percentage)
        
        # Send webhook with retry logic
        return self._send_with_retry(payload)
    
    def send_profile_update(
        self, 
        user: User, 
        updated_fields: list,
        kikapu_user_id: Optional[str] = None
    ) -> Dict:
        """
        Send profile update webhook to Kikapu
        
        Args:
            user: The User object
            updated_fields: List of fields that were updated
            kikapu_user_id: The original Kikapu user ID
            
        Returns:
            Dictionary with webhook delivery status
        """
        if not self.webhook_url:
            return {
                'success': False,
                'error': 'Webhook URL not configured',
                'skipped': True
            }
        
        farm = user.farms.first()
        if not farm:
            return {
                'success': False,
                'error': 'No farm data available',
                'skipped': True
            }
        
        # Prepare update payload
        payload = self._prepare_payload(user, farm, kikapu_user_id)
        payload['event_type'] = 'profile_updated'
        payload['updated_fields'] = updated_fields
        
        return self._send_with_retry(payload)
    
    def _prepare_payload(
        self, 
        user: User, 
        farm: Farm, 
        kikapu_user_id: Optional[str],
        completion_percentage: Optional[int] = None
    ) -> Dict:
        """
        Prepare webhook payload with enhanced profile data
        """
        # Get crops
        crops = list(farm.crops.values_list('name', flat=True))
        
        payload = {
            'event_type': 'profile_completed',
            'timestamp': user.date_joined.isoformat() if user.date_joined else None,
            
            # User identification
            'kikapu_user_id': kikapu_user_id,
            'mkulima_user_id': user.id,
            'phone_number': user.phone_number,
            
            # Enhanced profile data
            'enhanced_data': {
                # Personal info
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'full_name': user.get_full_name(),
                
                # Farm details
                'farm_name': farm.name,
                'location': farm.location,
                'farm_size': float(farm.size) if farm.size else None,
                'farm_size_unit': 'hectares',
                'soil_type': farm.soil_type,
                'farm_description': farm.description,
                'is_hydroponic': farm.is_hydroponic,
                
                # Crops
                'crops': crops,
                'crop_count': len(crops),
                
                # Metadata
                'completion_percentage': completion_percentage,
                'profile_complete': completion_percentage >= 100 if completion_percentage else False,
                'has_email': bool(user.email),
                'has_address': bool(user.address),
            },
            
            # System metadata
            'source': 'mkulima_smart',
            'webhook_version': '1.0'
        }
        
        return payload
    
    def _send_with_retry(self, payload: Dict) -> Dict:
        """
        Send webhook with retry logic
        """
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mkulima-Smart-Webhook/1.0'
        }
        
        # Add webhook secret if configured
        if self.webhook_secret:
            headers['X-Webhook-Secret'] = self.webhook_secret
        
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Sending webhook to Kikapu (attempt {attempt}/{self.max_retries})")
                logger.debug(f"Webhook payload: {json.dumps(payload, indent=2)}")
                
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                
                logger.info(f"Webhook sent successfully to Kikapu. Status: {response.status_code}")
                
                return {
                    'success': True,
                    'status_code': response.status_code,
                    'response_data': response.json() if response.content else {},
                    'attempts': attempt
                }
                
            except requests.exceptions.Timeout as e:
                last_error = f"Timeout after {self.timeout}s"
                logger.warning(f"Webhook timeout on attempt {attempt}: {str(e)}")
                
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {str(e)}"
                logger.warning(f"Webhook connection error on attempt {attempt}: {str(e)}")
                
            except requests.exceptions.HTTPError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text}"
                logger.error(f"Webhook HTTP error on attempt {attempt}: {str(e)}")
                # Don't retry on 4xx errors (client errors)
                if 400 <= e.response.status_code < 500:
                    break
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected webhook error on attempt {attempt}: {str(e)}")
        
        # All retries failed
        logger.error(f"Webhook failed after {self.max_retries} attempts. Last error: {last_error}")
        
        return {
            'success': False,
            'error': last_error,
            'attempts': self.max_retries
        }


# Convenience function for easy webhook sending
def send_profile_completion_webhook(
    user: User, 
    kikapu_user_id: Optional[str] = None,
    completion_percentage: int = 100
) -> Dict:
    """
    Convenience function to send profile completion webhook
    
    Usage:
        from authentication.webhooks import send_profile_completion_webhook
        result = send_profile_completion_webhook(user, kikapu_user_id="12345")
    """
    webhook_service = KikapuWebhookService()
    return webhook_service.send_profile_completion(
        user, 
        kikapu_user_id, 
        completion_percentage
    )


def send_profile_update_webhook(
    user: User, 
    updated_fields: list,
    kikapu_user_id: Optional[str] = None
) -> Dict:
    """
    Convenience function to send profile update webhook
    
    Usage:
        from authentication.webhooks import send_profile_update_webhook
        result = send_profile_update_webhook(
            user, 
            updated_fields=['location', 'crops'],
            kikapu_user_id="12345"
        )
    """
    webhook_service = KikapuWebhookService()
    return webhook_service.send_profile_update(
        user, 
        updated_fields,
        kikapu_user_id
    )
