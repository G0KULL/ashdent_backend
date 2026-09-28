import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
django.setup()

from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password

# Find admin user
users = list(User.objects.filter(username='admin'))
print(f"Found {len(users)} user(s) with username 'admin'")

for u in users:
    print(f"  ID: {u.id}, superuser: {u.is_superuser}, active: {u.is_active}, first_name: {u.first_name}")

if users:
    admin = users[0]
    new_pw = make_password('password123')
    # Use queryset update to avoid the duplicate insert bug in django_mongodb_backend
    updated = User.objects.filter(username='admin').update(password=new_pw)
    print(f"\nUpdated {updated} record(s). Password set to: password123")
    
    # Verify we can authenticate
    from django.contrib.auth import authenticate
    result = authenticate(username='admin', password='password123')
    if result:
        print(f"✅ Authentication SUCCESS! Role will resolve from staff profile.")
    else:
        print("❌ Authentication still failing — check staff_profile link.")
        from patients.models import Staff
        staffs = list(Staff.objects.filter(username='admin')) if hasattr(Staff, 'username') else []
        print(f"Staff with username=admin: {staffs}")
else:
    print("No admin user found!")
