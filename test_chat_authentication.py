"""
Test script to verify JWT authentication for chat API endpoints
"""
import requests
import json

# Configuration
BASE_URL = "http://192.168.1.197:8000/en/gova-pp"  # Server IP address

# Test credentials - using test farmer account
PHONE_NUMBER = "+255700000001"  # Test Farmer (created by create_test_user.py)
PASSWORD = "Test123456"  # Test password
THREAD_ID = 27  # Test thread created by create_test_thread.py

def test_obtain_token():
    """Test obtaining a JWT token"""
    print("\n" + "="*60)
    print("STEP 1: Obtaining JWT Token")
    print("="*60)
    
    url = f"{BASE_URL}/api/token/"
    payload = {
        "phone_number": PHONE_NUMBER,
        "password": PASSWORD
    }
    
    print(f"\nURL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(url, json=payload)
    
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 200:
        token = response.json().get('token')
        print(f"\n✅ SUCCESS: Token obtained")
        return token
    else:
        print(f"\n❌ FAILED: Could not obtain token")
        return None

def test_get_thread_messages(token, thread_id):
    """Test getting messages from a thread with JWT token"""
    print("\n" + "="*60)
    print(f"STEP 2: Getting Messages from Thread {thread_id}")
    print("="*60)
    
    url = f"{BASE_URL}/api/chat/threads/{thread_id}/messages/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"\nURL: {url}")
    print(f"Headers: {json.dumps(headers, indent=2)}")
    
    response = requests.get(url, headers=headers)
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        print(f"\n✅ SUCCESS: Messages retrieved")
        return True
    else:
        print(f"Response: {response.text}")
        print(f"\n❌ FAILED: Could not get messages")
        return False

def test_post_message(token, thread_id):
    """Test posting a message to a thread with JWT token"""
    print("\n" + "="*60)
    print(f"STEP 3: Posting Message to Thread {thread_id}")
    print("="*60)
    
    url = f"{BASE_URL}/api/chat/threads/{thread_id}/messages/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": "Test message sent via authenticated API"
    }
    
    print(f"\nURL: {url}")
    print(f"Headers: {json.dumps(headers, indent=2)}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(url, json=payload, headers=headers)
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code in [200, 201]:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        print(f"\n✅ SUCCESS: Message posted")
        return True
    else:
        print(f"Response: {response.text}")
        print(f"\n❌ FAILED: Could not post message")
        return False

def main():
    """Run all authentication tests"""
    print("\n" + "="*60)
    print("MKULIMA SMART - CHAT API AUTHENTICATION TEST")
    print("="*60)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Phone Number: {PHONE_NUMBER}")
    print(f"Thread ID: {THREAD_ID}")
    
    # Step 1: Get token
    token = test_obtain_token()
    
    if not token:
        print("\n" + "="*60)
        print("❌ TEST SUITE FAILED: Could not obtain token")
        print("="*60)
        print("\nPlease check:")
        print("1. The BASE_URL is correct")
        print("2. The PHONE_NUMBER exists in the database")
        print("3. The PASSWORD is correct")
        print("4. The Django server is running")
        return
    
    # Step 2: Get thread messages
    test_get_thread_messages(token, THREAD_ID)
    
    # Step 3: Post a message
    test_post_message(token, THREAD_ID)
    
    print("\n" + "="*60)
    print("✅ TEST SUITE COMPLETED")
    print("="*60)

if __name__ == "__main__":
    main()
