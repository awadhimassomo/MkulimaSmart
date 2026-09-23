"""
Check what chat threads exist in the database
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MkulimaSmart.settings')
django.setup()

from gova_pp.models import FarmerMessage
from website.models import User

print("="*60)
print("CHAT THREADS IN DATABASE")
print("="*60)

threads = FarmerMessage.objects.all().order_by('-created_at')

print(f"\nTotal Threads: {threads.count()}")

if threads.count() > 0:
    print("\n" + "-"*60)
    for thread in threads[:5]:  # Show first 5 threads
        print(f"\nThread ID: {thread.id}")
        print(f"Farmer: {thread.farmer_name} ({thread.farmer_phone})")
        print(f"Subject: {thread.subject}")
        print(f"Status: {thread.status}")
        print(f"Created: {thread.created_at}")
        print(f"Message: {thread.message[:100]}...")
        print("-"*60)
    
    if threads.count() > 5:
        print(f"\n... and {threads.count() - 5} more threads")
else:
    print("\n⚠️  NO THREADS FOUND")

# Check for our test user
test_user = User.objects.filter(phone_number="+255700000001").first()
if test_user:
    test_threads = FarmerMessage.objects.filter(farmer_phone=test_user.phone_number)
    print(f"\n✅ Test user threads: {test_threads.count()}")
