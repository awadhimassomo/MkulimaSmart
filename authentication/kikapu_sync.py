"""
Kikapu Reverse Sync Service
Syncs Mkulima Smart users to Kikapu with duplicate prevention
"""
import requests
import logging
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


class KikapuReverseSyncService:
    """
    Handles syncing Mkulima Smart users to Kikapu
    Prevents duplicates by checking if user exists first
    """
    
    @staticmethod
    def get_kikapu_base_url():
        """Get Kikapu base URL from settings"""
        return getattr(settings, 'KIKAPU_OAUTH_BASE_URL', 'http://localhost:8001')
    
    @staticmethod
    def check_user_exists_on_kikapu(phone_number):
        """
        Check if a user with this phone number exists on Kikapu
        
        Args:
            phone_number: Phone number to check
            
        Returns:
            dict: {'exists': bool, 'user_id': str or None, 'user_data': dict or None}
        """
        base_url = KikapuReverseSyncService.get_kikapu_base_url()
        check_url = f"{base_url}/api/check-user"
        
        try:
            response = requests.get(
                check_url,
                params={'phone': phone_number},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Kikapu user check for {phone_number}: {'exists' if data.get('exists') else 'not found'}")
                return {
                    'exists': data.get('exists', False),
                    'user_id': data.get('user_id'),
                    'user_data': data.get('user_data')
                }
            else:
                logger.warning(f"Kikapu user check failed with status {response.status_code}")
                return {'exists': False, 'user_id': None, 'user_data': None}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking Kikapu user: {str(e)}")
            return {'exists': False, 'user_id': None, 'user_data': None}
    
    @staticmethod
    def create_kikapu_user(mkulima_user, farm=None):
        """
        Create a new user on Kikapu
        
        Args:
            mkulima_user: Mkulima Smart User instance
            farm: Optional Farm instance
            
        Returns:
            dict: {'success': bool, 'kikapu_user_id': str or None, 'message': str}
        """
        base_url = KikapuReverseSyncService.get_kikapu_base_url()
        register_url = f"{base_url}/api/register"
        
        # Prepare registration data
        registration_data = {
            'phone_number': mkulima_user.phone_number,
            'first_name': mkulima_user.first_name or '',
            'last_name': mkulima_user.last_name or '',
            'email': mkulima_user.email or '',
            'user_type': 'BUSINESS',  # Farmers are business users on Kikapu
            'password': 'synced_from_mkulima_2024',  # Temporary password
        }
        
        # Add farm/business profile data if available
        if farm:
            registration_data['business_profile'] = {
                'business_name': farm.name,
                'location': farm.location,
                'description': farm.description or f'Synced from Mkulima Smart'
            }
        
        try:
            response = requests.post(
                register_url,
                json=registration_data,
                timeout=15
            )
            
            if response.status_code == 201:
                data = response.json()
                logger.info(f"✅ Successfully created Kikapu user for {mkulima_user.phone_number}")
                return {
                    'success': True,
                    'kikapu_user_id': data.get('user_id'),
                    'message': 'User created on Kikapu'
                }
            else:
                error_msg = response.json().get('message', 'Unknown error')
                logger.error(f"Failed to create Kikapu user: {error_msg}")
                return {
                    'success': False,
                    'kikapu_user_id': None,
                    'message': error_msg
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating Kikapu user: {str(e)}")
            return {
                'success': False,
                'kikapu_user_id': None,
                'message': str(e)
            }
    
    @staticmethod
    def sync_user_to_kikapu(mkulima_user, farm=None):
        """
        Main method to sync a Mkulima user to Kikapu with duplicate prevention
        
        This is the smart sync that:
        1. Checks if user already exists on Kikapu
        2. If exists: Just link the accounts
        3. If not exists: Create new user on Kikapu
        
        Args:
            mkulima_user: Mkulima Smart User instance
            farm: Optional Farm instance
            
        Returns:
            dict: {
                'status': 'already_exists' | 'created' | 'error',
                'kikapu_user_id': str or None,
                'message': str
            }
        """
        phone_number = mkulima_user.phone_number
        
        logger.info(f"🔄 Starting reverse sync for Mkulima user: {phone_number}")
        
        # Step 1: Check if user exists on Kikapu
        check_result = KikapuReverseSyncService.check_user_exists_on_kikapu(phone_number)
        
        if check_result['exists']:
            # User already exists on Kikapu - just link them
            logger.info(f"👥 User {phone_number} already exists on Kikapu - linking accounts")
            
            # TODO: Store the link in a mapping table (optional)
            # You could create a KikapuUserMapping model to store:
            # - mkulima_user_id
            # - kikapu_user_id
            # - synced_at
            
            return {
                'status': 'already_exists',
                'kikapu_user_id': check_result['user_id'],
                'message': f'User already exists on Kikapu. Accounts linked.',
                'user_data': check_result['user_data']
            }
        
        else:
            # User doesn't exist on Kikapu - safe to create
            logger.info(f"➕ User {phone_number} not found on Kikapu - creating new account")
            
            create_result = KikapuReverseSyncService.create_kikapu_user(mkulima_user, farm)
            
            if create_result['success']:
                logger.info(f"✅ Successfully synced {phone_number} to Kikapu")
                
                return {
                    'status': 'created',
                    'kikapu_user_id': create_result['kikapu_user_id'],
                    'message': 'User created on Kikapu and accounts linked'
                }
            else:
                logger.error(f"❌ Failed to create user on Kikapu: {create_result['message']}")
                
                return {
                    'status': 'error',
                    'kikapu_user_id': None,
                    'message': f"Failed to sync to Kikapu: {create_result['message']}"
                }


def sync_new_registration_to_kikapu(user, farm=None):
    """
    Convenience function to sync a newly registered Mkulima user to Kikapu
    Call this after successful Mkulima registration
    
    Args:
        user: Newly created Mkulima User instance
        farm: Optional Farm instance
        
    Returns:
        dict: Sync result
    """
    try:
        result = KikapuReverseSyncService.sync_user_to_kikapu(user, farm)
        
        if result['status'] in ['already_exists', 'created']:
            logger.info(f"🎉 Reverse sync successful for {user.phone_number}: {result['status']}")
        else:
            logger.warning(f"⚠️ Reverse sync had issues for {user.phone_number}: {result['message']}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Reverse sync exception for {user.phone_number}: {str(e)}")
        return {
            'status': 'error',
            'kikapu_user_id': None,
            'message': str(e)
        }
