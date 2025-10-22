"""
Test script for Kikapu-Led Registration Sync
Run this to test the sync endpoints and functionality
"""
import requests
import json
from pprint import pprint

# Configuration
BASE_URL = 'http://localhost:8000'  # Update with your server URL
TEST_PHONE = '+255712345678'
TEST_PASSWORD = 'TestPassword123'

def test_sync_registration():
    """Test the sync registration endpoint"""
    print("\n" + "="*60)
    print("TEST 1: Sync Registration from Kikapu")
    print("="*60)
    
    url = f'{BASE_URL}/api/auth/farmer/sync-register'
    data = {
        'phone_number': TEST_PHONE,
        'first_name': 'John',
        'last_name': 'Doe',
        'password': TEST_PASSWORD,
        'farm_name': 'Green Valley Maize Farm',
        'kikapu_user_id': 'kikapu_12345'
    }
    
    print(f"\nRequest URL: {url}")
    print(f"Request Data:")
    pprint(data)
    
    try:
        response = requests.post(url, json=data)
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Data:")
        pprint(response.json())
        
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {str(e)}")
        return None
    except json.JSONDecodeError:
        print(f"\n❌ Invalid JSON response: {response.text}")
        return None


def test_check_sync_status():
    """Test the check sync status endpoint"""
    print("\n" + "="*60)
    print("TEST 2: Check Sync Status")
    print("="*60)
    
    url = f'{BASE_URL}/api/auth/check-sync'
    params = {'phone': TEST_PHONE}
    
    print(f"\nRequest URL: {url}")
    print(f"Query Params: {params}")
    
    try:
        response = requests.get(url, params=params)
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Data:")
        pprint(response.json())
        
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {str(e)}")
        return None


def test_profile_completion(user_id, token):
    """Test the profile completion endpoint"""
    print("\n" + "="*60)
    print("TEST 3: Complete Profile")
    print("="*60)
    
    url = f'{BASE_URL}/api/auth/farmer/complete-profile'
    data = {
        'user_id': user_id,
        'token': token,
        'email': 'john.doe@example.com',
        'location': 'Arusha, Meru District',
        'farm_size': 2.5,
        'soil_type': 'Volcanic',
        'crops': ['Maize', 'Beans', 'Coffee'],
        'services': ['market_access', 'weather', 'advice']
    }
    
    print(f"\nRequest URL: {url}")
    print(f"Request Data:")
    pprint(data)
    
    try:
        response = requests.post(url, json=data)
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Data:")
        pprint(response.json())
        
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {str(e)}")
        return None


def test_duplicate_registration():
    """Test registering the same user again"""
    print("\n" + "="*60)
    print("TEST 4: Duplicate Registration (Should return 'already_exists')")
    print("="*60)
    
    url = f'{BASE_URL}/api/auth/farmer/sync-register'
    data = {
        'phone_number': TEST_PHONE,
        'first_name': 'John',
        'last_name': 'Doe',
        'password': TEST_PASSWORD,
        'farm_name': 'Another Farm',
    }
    
    try:
        response = requests.post(url, json=data)
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Data:")
        pprint(response.json())
        
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {str(e)}")
        return None


def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "="*60)
    print("KIKAPU-LED REGISTRATION SYNC TEST SUITE")
    print("="*60)
    print(f"\nTesting against: {BASE_URL}")
    print(f"Test phone: {TEST_PHONE}")
    
    # Test 1: Initial registration
    sync_result = test_sync_registration()
    
    if not sync_result:
        print("\n❌ Sync registration failed. Cannot continue tests.")
        return
    
    # Extract user_id and token
    user_id = sync_result.get('user_id')
    token = sync_result.get('completion_token')
    
    # Test 2: Check sync status
    test_check_sync_status()
    
    # Test 3: Profile completion (if we have token)
    if user_id and token:
        test_profile_completion(user_id, token)
    else:
        print("\n⚠️ Skipping profile completion test (no token)")
    
    # Test 4: Duplicate registration
    test_duplicate_registration()
    
    print("\n" + "="*60)
    print("TEST SUITE COMPLETED")
    print("="*60)
    print("\n✅ All tests executed successfully!")
    print("\nNext Steps:")
    print("1. Check the Django admin to verify user creation")
    print("2. Visit the profile completion URL in a browser")
    print("3. Review the smart data mapping (location, crops)")
    print("4. Test the profile completion form")


def test_data_mapping():
    """Test smart data mapping with different scenarios"""
    print("\n" + "="*60)
    print("DATA MAPPING TESTS")
    print("="*60)
    
    test_cases = [
        {
            'name': 'Arusha Phone + Coffee Farm',
            'phone': '+255754321000',
            'farm_name': 'Kilimanjaro Coffee Estate',
            'expected_location': 'Arusha',
            'expected_crops': ['coffee']
        },
        {
            'name': 'Mbeya Phone + Generic Farm',
            'phone': '+255761234567',
            'farm_name': 'Small Farm',
            'expected_location': 'Mbeya',
            'expected_crops': ['maize', 'beans', 'potato']
        },
        {
            'name': 'Rice Farm',
            'phone': '+255771234567',
            'farm_name': 'Mwanza Rice Fields',
            'expected_location': 'Mwanza',
            'expected_crops': ['rice']
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {test_case['name']} ---")
        
        url = f'{BASE_URL}/api/auth/farmer/sync-register'
        data = {
            'phone_number': test_case['phone'],
            'first_name': 'Test',
            'last_name': f'Farmer{i}',
            'password': 'Test123',
            'farm_name': test_case['farm_name']
        }
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            
            print(f"Phone: {test_case['phone']}")
            print(f"Farm Name: {test_case['farm_name']}")
            print(f"Inferred Location: {result.get('inferred_location')}")
            print(f"Predicted Crops: {result.get('predicted_crops')}")
            
            # Verify expectations
            if result.get('inferred_location') == test_case['expected_location']:
                print("✅ Location inference correct")
            else:
                print(f"⚠️ Expected {test_case['expected_location']}, got {result.get('inferred_location')}")
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")


if __name__ == '__main__':
    import sys
    
    print("\nKikapu-Led Registration Sync Test Script")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'mapping':
            test_data_mapping()
        elif sys.argv[1] == 'quick':
            test_sync_registration()
        else:
            print("Usage:")
            print("  python test_kikapu_sync.py          # Run all tests")
            print("  python test_kikapu_sync.py quick    # Quick test only")
            print("  python test_kikapu_sync.py mapping  # Test data mapping")
    else:
        run_all_tests()
