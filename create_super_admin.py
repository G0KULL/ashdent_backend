import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from patients.models import Staff, Company
from django.db import connections

def create_super_admin():
    username = 'superadmin'
    password = 'password123'
    email = 'superadmin@dental.com'
    name = 'Global Super Admin'

    db = connections['default'].database

    # Check if user already exists
    user = User.objects.filter(username=username).first()
    if not user:
        user = User.objects.create_superuser(
            username=username,
            password=password,
            email=email,
            first_name='Global',
            last_name='Super Admin'
        )
        print(f"Created User '{username}'")
    else:
        new_pw = make_password(password)
        User.objects.filter(username=username).update(password=new_pw, is_superuser=True)
        print(f"Updated password & superuser status for existing user '{username}'")

    # Ensure main company exists
    company = Company.objects.first()
    if not company:
        company = Company.objects.create(name="Main Dental Clinic", code="MAIN")

    # Create or update Staff profile
    u_doc = db['auth_user'].find_one({'username': username})
    user_obj_id = u_doc['_id'] if u_doc else user.pk

    staff = Staff.objects.filter(user_id=user_obj_id).first()
    if not staff:
        staff = Staff.objects.create(
            user_id=user_obj_id,
            name=name,
            first_name='Global',
            last_name='Super Admin',
            role='Admin',
            is_super_admin=True,
            company=company,
            phone='9990001112',
            email=email,
            permissions=['income-analytics', 'expense-manager', 'billing', 'pharmacy', 'stock', 'prescriptions', 'lab', 'users', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'follow-ups', 'pre-bookings', 'communication', 'tele-medicine', 'website-appointment', 'purchases', 'doctors', 'settings', 'pathology-lab', 'dental-lab']
        )
        print(f"Created Staff profile with is_super_admin=True for '{username}'")
    else:
        staff.is_super_admin = True
        staff.company = company
        staff.save()
        print(f"Updated Staff profile for '{username}' to is_super_admin=True")

    print(f"\n[SUCCESS] Super Admin account ready:")
    print(f"   Username: {username}")
    print(f"   Password: {password}")

if __name__ == '__main__':
    create_super_admin()
