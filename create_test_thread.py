"""
Create a test chat thread for the test user
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MkulimaSmart.settings')
django.setup()

from gova_pp.models import FarmerMessage
from website.models import User

print("="*60)
print("CREATE TEST CHAT THREAD")
print("="*60)

# Get test user
test_user = User.objects.filter(phone_number="+255700000001").first()

if not test_user:
    print("\n❌ Test user not found!")
    print("Please run create_test_user.py first")
    exit(1)

print(f"\n✅ Test user found: {test_user.get_full_name()} ({test_user.phone_number})")

# Create a test thread
thread = FarmerMessage.objects.create(
    farmer_name=test_user.get_full_name(),
    farmer_phone=test_user.phone_number,
    farmer_location="Test Location, Arusha",
    message_type="inquiry",
    subject="Test Thread for API Testing",
    message="This is a test message created for API authentication testing. The farmer is asking about crop disease management.",
    status="new",
    priority="medium",
    has_image=False,
)

print(f"\n✅ Thread created successfully!")
print(f"Thread ID: {thread.id}")
print(f"Subject: {thread.subject}")
print(f"Status: {thread.status}")
print(f"Created: {thread.created_at}")

print("\n" + "="*60)
print("UPDATE YOUR TEST SCRIPT")
print("="*60)
print(f"\nIn test_chat_authentication.py, update:")
print(f"THREAD_ID = {thread.id}")
print("\nThen run: python test_chat_authentication.py")
print("="*60)
