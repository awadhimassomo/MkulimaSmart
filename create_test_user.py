"""
Create a test farmer user for API testing
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MkulimaSmart.settings')
django.setup()

from website.models import User

# Test user credentials
TEST_PHONE = "+255700000001"
TEST_PASSWORD = "Test123456"
TEST_FIRST_NAME = "Test"
TEST_LAST_NAME = "Farmer"

print("="*60)
print("CREATE TEST FARMER USER")
print("="*60)

# Check if user already exists
existing_user = User.objects.filter(phone_number=TEST_PHONE).first()

if existing_user:
    print(f"\n✅ User already exists!")
    print(f"Phone: {existing_user.phone_number}")
    print(f"Name: {existing_user.get_full_name()}")
    print(f"Is Farmer: {existing_user.is_farmer}")
    print(f"\n🔄 Updating password to: {TEST_PASSWORD}")
    
    # Update password
    existing_user.set_password(TEST_PASSWORD)
    existing_user.save()
    
    print("✅ Password updated successfully!")
else:
    print(f"\n📝 Creating new test farmer user...")
    print(f"Phone: {TEST_PHONE}")
    print(f"Password: {TEST_PASSWORD}")
    
    # Create new user
    user = User.objects.create_user(
        phone_number=TEST_PHONE,
        password=TEST_PASSWORD,
        first_name=TEST_FIRST_NAME,
        last_name=TEST_LAST_NAME,
        is_farmer=True,
        is_active=True
    )
    
    print(f"\n✅ User created successfully!")
    print(f"User ID: {user.id}")
    print(f"Name: {user.get_full_name()}")

print("\n" + "="*60)
print("TEST CREDENTIALS")
print("="*60)
print(f"Phone Number: {TEST_PHONE}")
print(f"Password: {TEST_PASSWORD}")
print("\nYou can now use these credentials to test the API!")
print("="*60)
