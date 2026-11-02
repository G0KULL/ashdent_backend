import os
import sys
import random
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from patients.models import Staff, Doctor
from rest_framework.test import APIClient
from django.db import connections

client = APIClient()
admin_user = User.objects.filter(is_superuser=True).first()
if not admin_user:
    admin_user = User.objects.create_superuser('admin_test', 'admin@test.com', 'adminpass')
client.force_authenticate(user=admin_user)
headers = {'HTTP_X_USERNAME': admin_user.username, 'HTTP_X_USER_ROLE': 'Admin'}

print("=" * 60)
print("STAFF ONBOARDING WIZARD - BACKEND CONFIRM PASSWORD AUDIT TESTS")
print("=" * 60)

def rand_str():
    return str(random.randint(10000, 99999))

def base_payload():
    r = rand_str()
    return {
        "basic_details": {
            "name": f"Dr. Audit Test {r}",
            "phone": f"98111{r}",
            "email": f"audit_{r}@testclinic.com",
            "emergency_contact": "9123456789",
            "gender": "Male",
            "dob": "1992-04-10",
            "age": 34,
            "blood_group": "A+",
            "address": "456 Test Lane",
            "pincode": "110020",
            "city": "New Delhi",
            "state": "Delhi",
            "country": "India",
            "status": "Active"
        },
        "employment": {
            "role": "Doctor",
            "staff_level": "Senior",
            "joining_date": "2026-01-01",
            "base_salary": 80000,
            "additional_details": {
                "qualification": "BDS, MDS",
                "specialization": "Prosthodontics",
                "license_no": f"DENT-LIC-{r}",
                "registration_council": "Dental Council of India",
                "experience_years": 6,
                "consultation_fee": 700
            }
        },
        "login": {
            "username": f"dr_audit_{r}",
            "password": "Dental@123",
            "confirm_password": "Dental@123"
        },
        "leave_configs": [
            { "leave_type": "Casual Leave", "annual_entitlement": 12, "is_paid": True, "allow_carry_forward": True, "max_carry_forward": 6 }
        ],
        "benefits": [],
        "insurance": { "is_enabled": False },
        "permissions": ["appointments", "prescriptions"]
    }

# -------------------------------------------------------------
# Test 1: Mismatched passwords submitted directly to API
# -------------------------------------------------------------
p_mismatch = base_payload()
p_mismatch["login"]["password"] = "Dental@123"
p_mismatch["login"]["confirm_password"] = "Dental@456"

u_count_before = User.objects.count()
s_count_before = Staff.objects.count()

res_mismatch = client.post('/api/staff/onboarding/', p_mismatch, format='json', **headers)
print("Test 1 - Mismatch Status Code:", res_mismatch.status_code)
print("Test 1 - Response:", res_mismatch.data)

assert res_mismatch.status_code == 400, f"Expected 400, got {res_mismatch.status_code}"
assert res_mismatch.data.get('errors', {}).get('confirm_password') == 'Passwords do not match.'
assert User.objects.count() == u_count_before, "No User record should be created"
assert Staff.objects.count() == s_count_before, "No Staff record should be created"
print("[OK] Test 1: Mismatched passwords rejected, no User/Staff created.")

# -------------------------------------------------------------
# Test 2: Empty confirm_password submitted with password
# -------------------------------------------------------------
p_empty_confirm = base_payload()
p_empty_confirm["login"]["password"] = "Dental@123"
p_empty_confirm["login"]["confirm_password"] = ""

res_empty_confirm = client.post('/api/staff/onboarding/', p_empty_confirm, format='json', **headers)
print("Test 2 - Empty Confirmation Status Code:", res_empty_confirm.status_code)
print("Test 2 - Response:", res_empty_confirm.data)

assert res_empty_confirm.status_code == 400, f"Expected 400, got {res_empty_confirm.status_code}"
assert res_empty_confirm.data.get('errors', {}).get('confirm_password') == 'Please confirm your password.'
assert User.objects.count() == u_count_before, "No User record created on empty confirm"
assert Staff.objects.count() == s_count_before, "No Staff record created on empty confirm"
print("[OK] Test 2: Empty confirm password rejected cleanly.")

# -------------------------------------------------------------
# Test 3: Empty password submitted
# -------------------------------------------------------------
p_empty_pwd = base_payload()
p_empty_pwd["login"]["password"] = ""
p_empty_pwd["login"]["confirm_password"] = "Dental@123"

res_empty_pwd = client.post('/api/staff/onboarding/', p_empty_pwd, format='json', **headers)
assert res_empty_pwd.status_code == 400
assert res_empty_pwd.data.get('errors', {}).get('password') == 'Password is required.'
assert User.objects.count() == u_count_before
assert Staff.objects.count() == s_count_before
print("[OK] Test 3: Empty password rejected cleanly.")

# -------------------------------------------------------------
# Test 4: Valid matching passwords
# -------------------------------------------------------------
p_valid = base_payload()
valid_username = p_valid["login"]["username"]
raw_password = "Dental@SecurePassword123"
p_valid["login"]["password"] = raw_password
p_valid["login"]["confirm_password"] = raw_password

res_valid = client.post('/api/staff/onboarding/', p_valid, format='json', **headers)
print("Test 4 - Valid Registration Status Code:", res_valid.status_code)
assert res_valid.status_code == 201, f"Expected 201, got {res_valid.status_code}: {res_valid.data}"

staff_id = res_valid.data['id']
created_staff = Staff.objects.get(pk=staff_id)
created_user = User.objects.get(username=valid_username)

# Verify secure password hashing
assert created_user.password != raw_password, "Raw password must NEVER be stored in User"
assert not created_user.password.startswith("Dental@"), "Password must be hashed"
assert created_user.check_password(raw_password) == True, "Django check_password must verify against secure hash"
print("[OK] Test 4: Valid registration succeeded, password securely hashed via Django PBKDF2.")

# -------------------------------------------------------------
# Test 5: Verify confirm_password is never persisted anywhere
# -------------------------------------------------------------
assert not hasattr(created_staff, 'confirm_password'), "Staff model has no confirm_password field"
assert not hasattr(created_user, 'confirm_password'), "User model has no confirm_password field"
assert 'confirm_password' not in created_staff.additional_details, "confirm_password not persisted in additional_details"
print("[OK] Test 5: Verified confirm_password is not stored in database.")

# -------------------------------------------------------------
# Test 6: Verify StaffCreateView (/api/staff/create/) confirm_password validation
# -------------------------------------------------------------
r_staff = rand_str()
res_staff_create_mismatch = client.post('/api/staff/create/', {
    "name": f"Assistant {r_staff}",
    "phone": f"98333{r_staff}",
    "gender": "Female",
    "dob": "1994-06-01",
    "age": 32,
    "blood_group": "B+",
    "address": "Assistant Address",
    "role": "Receptionist",
    "staff_level": "Junior",
    "status": "Active",
    "username": f"rec_{r_staff}",
    "password": "Dental@123",
    "confirm_password": "Dental@Mismatch99",
    "additional_details": {
        "qualification": "Graduate",
        "experience_years": 2
    }
}, format='json', **headers)

assert res_staff_create_mismatch.status_code == 400
assert res_staff_create_mismatch.data.get('errors', {}).get('confirm_password') == 'Passwords do not match.'
print("[OK] Test 6: StaffCreateView also enforces confirm_password validation.")

# Clean up test accounts directly in mongo
db = connections['default'].database
db['auth_user'].delete_many({'username': valid_username})
db['patients_staff'].delete_many({'name': p_valid['basic_details']['name']})
db['patients_doctor'].delete_many({'name': p_valid['basic_details']['name']})
print("[OK] Cleaned up temporary test user and staff records.")

print("=" * 60)
print("ALL BACKEND CONFIRM PASSWORD AUDIT TESTS PASSED CLEANLY!")
print("=" * 60)
