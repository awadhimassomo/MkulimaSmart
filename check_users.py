"""
Check what users exist in the database
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MkulimaSmart.settings')
django.setup()

from website.models import User

# Get all users
users = User.objects.all()

print("="*60)
print(f"TOTAL USERS IN DATABASE: {users.count()}")
print("="*60)

if users.count() > 0:
    print("\nUser List:")
    print("-"*60)
    for user in users[:10]:  # Show first 10 users
        print(f"\nID: {user.id}")
        print(f"Phone: {user.phone_number}")
        print(f"Name: {user.get_full_name()}")
        print(f"Is Farmer: {user.is_farmer}")
        print(f"Is Staff: {user.is_staff}")
        print(f"Is Active: {user.is_active}")
        print("-"*60)
    
    if users.count() > 10:
        print(f"\n... and {users.count() - 10} more users")
else:
    print("\n⚠️  NO USERS FOUND IN DATABASE")
    print("\nYou need to create a user first!")
