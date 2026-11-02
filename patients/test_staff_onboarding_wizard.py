import os
import sys
import django

# Setup Django environment
backend_path = r'c:\Users\gokul\Downloads\dental software\backend'
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from patients.models import Staff, Doctor, StaffLeaveConfig, StaffBenefit, StaffInsurance
from rest_framework.test import APIClient

client = APIClient()
admin_user = User.objects.filter(is_superuser=True).first()
if admin_user:
    client.force_authenticate(user=admin_user)
    client.credentials(HTTP_X_USERNAME=admin_user.username, HTTP_X_USER_ROLE='Admin')

print("=" * 60)
print("RUNNING STAFF ONBOARDING WIZARD REGRESSION TESTS")
print("=" * 60)

# Helper function to generate unique username & phone
import random
def rand_str(): return str(random.randint(10000, 99999))

# 1. TEST DOCTOR ONBOARDING (FULL NESTED PAYLOAD)
doctor_username = f"dr_test_{rand_str()}"
doctor_phone = f"98765{rand_str()}"
doctor_email = f"dr_{rand_str()}@testclinic.com"

payload_doctor = {
    "basic_details": {
        "name": "Dr. Verification Doctor",
        "phone": doctor_phone,
        "email": doctor_email,
        "emergency_contact": "9123456789",
        "gender": "Male",
        "dob": "1990-05-15",
        "age": 36,
        "blood_group": "O+",
        "address": "123 Health Street",
        "pincode": "110016",
        "city": "New Delhi",
        "state": "Delhi",
        "country": "India",
        "status": "Active"
    },
    "employment": {
        "role": "Doctor",
        "staff_level": "Senior",
        "joining_date": "2026-01-01",
        "base_salary": 75000,
        "additional_details": {
            "qualification": "BDS, MDS",
            "specialization": "Orthodontics",
            "license_no": f"DENT-REG-{rand_str()}",
            "registration_council": "State Dental Council",
            "experience_years": 8,
            "consultation_fee": 600
        }
    },
    "login": {
        "username": doctor_username,
        "password": "Password@123"
    },
    "leave_configs": [
        { "leave_type": "Casual Leave", "annual_entitlement": 12, "is_paid": True, "allow_carry_forward": True, "max_carry_forward": 6 },
        { "leave_type": "Paid Leave", "annual_entitlement": 15, "is_paid": True, "allow_carry_forward": True, "max_carry_forward": 5 },
        { "leave_type": "Unpaid Leave", "annual_entitlement": 30, "is_paid": False, "allow_carry_forward": False, "max_carry_forward": 0 }
    ],
    "benefits": [
        { "benefit_name": "Health Benefit", "benefit_type": "Allowance", "amount": 2500, "description": "Medical Allowance" }
    ],
    "insurance": {
        "is_enabled": True,
        "provider": "HDFC ERGO Health",
        "policy_number": f"POL-2026-{rand_str()}",
        "policy_type": "Group Health Insurance",
        "coverage_amount": 500000,
        "employee_contribution": 1000,
        "employer_contribution": 3000,
        "start_date": "2026-01-01",
        "expiry_date": "2026-12-31",
        "status": "Active",
        "notes": "Full cashless coverage"
    },
    "permissions": ["add-patients", "appointments", "today-patients", "prescriptions", "billing"]
}

res = client.post('/api/staff/onboarding/', payload_doctor, format='json')
print("TEST 1 - Doctor Onboarding Status Code:", res.status_code)
print("TEST 1 - Response:", res.data)
assert res.status_code == 201
staff_id = res.data['id']

# Verify database state
staff_obj = Staff.objects.get(pk=staff_id)
assert staff_obj.name == "Dr. Verification Doctor"
assert staff_obj.role == "Doctor"
assert staff_obj.doctor_profile is not None
assert staff_obj.doctor_profile.specialization == "Orthodontics"
print("[OK] Doctor profile & staff record created cleanly")

# Verify Leave Configs
leaves = StaffLeaveConfig.objects.filter(staff=staff_obj)
assert leaves.count() == 3
print("[OK] 3 Leave Configuration entries created cleanly")

# Verify Benefits
bens = StaffBenefit.objects.filter(staff=staff_obj)
assert bens.count() == 1
assert bens[0].benefit_name == "Health Benefit"
print("[OK] Staff Benefit entry created cleanly")

# Verify Insurance
ins = StaffInsurance.objects.filter(staff=staff_obj)
assert ins.count() == 1
assert ins[0].provider == "HDFC ERGO Health"
print("[OK] Staff Insurance policy created cleanly")

# 2. TEST INSURANCE UPDATE & RENEWAL
renew_payload = {
    "provider": "Star Health Insurance",
    "policy_number": f"STAR-2027-{rand_str()}",
    "policy_type": "Executive Health Policy",
    "coverage_amount": 1000000,
    "employee_contribution": 1500,
    "employer_contribution": 4500,
    "start_date": "2027-01-01",
    "expiry_date": "2027-12-31",
    "status": "Active"
}

res_renew = client.post(f'/api/staff/{staff_id}/insurance/', renew_payload, format='json')
assert res_renew.status_code == 201
print("[OK] Insurance policy renewed / history entry created:", res_renew.data)

all_policies = StaffInsurance.objects.filter(staff=staff_obj)
assert all_policies.count() == 2
print("[OK] Preserved historical insurance records during policy renewal (Count =", all_policies.count(), ")")

# 3. TEST OPTIONAL EMAIL & EMERGENCY CONTACT
no_email_phone = f"98765{rand_str()}"
no_email_user = f"no_email_{rand_str()}"
payload_no_email = {
    "basic_details": {
        "name": "Staff Without Optional Fields",
        "phone": no_email_phone,
        "email": "", # Optional
        "emergency_contact": "", # Optional
        "gender": "Female",
        "dob": "1995-08-20",
        "age": 31,
        "blood_group": "B+",
        "address": "45 Market Street",
        "status": "Active"
    },
    "employment": {
        "role": "Receptionist",
        "staff_level": "Junior",
        "base_salary": 25000,
        "additional_details": {
            "qualification": "Graduate",
            "experience_years": 2
        }
    },
    "login": {
        "username": no_email_user,
        "password": "Password@123"
    },
    "permissions": ["add-patients", "appointments"]
}

res_no_email = client.post('/api/staff/onboarding/', payload_no_email, format='json')
assert res_no_email.status_code == 201
print("[OK] Staff created successfully without optional email & emergency contact")

# 4. TEST DUPLICATE USERNAME VALIDATION (MUST BLOCK)
dup_user_payload = dict(payload_no_email)
dup_user_payload["basic_details"] = dict(payload_no_email["basic_details"])
dup_user_payload["basic_details"]["phone"] = f"98765{rand_str()}" # New phone
dup_user_payload["login"] = { "username": no_email_user, "password": "Password@123" } # Duplicate username

res_dup_u = client.post('/api/staff/onboarding/', dup_user_payload, format='json')
assert res_dup_u.status_code == 400
assert 'Username already exists' in str(res_dup_u.data)
print("[OK] Blocked duplicate username cleanly with 400 error")

# 5. TEST DUPLICATE PHONE VALIDATION (MUST BLOCK)
dup_phone_payload = dict(payload_no_email)
dup_phone_payload["basic_details"] = dict(payload_no_email["basic_details"])
dup_phone_payload["basic_details"]["phone"] = no_email_phone # Duplicate phone
dup_phone_payload["login"] = { "username": f"user_{rand_str()}", "password": "Password@123" } # New username

res_dup_p = client.post('/api/staff/onboarding/', dup_phone_payload, format='json')
assert res_dup_p.status_code == 400
assert 'Phone number' in str(res_dup_p.data)
print("[OK] Blocked duplicate phone number cleanly with 400 error")

print("=" * 60)
print("ALL STAFF ONBOARDING WIZARD REGRESSION TESTS PASSED CLEANLY!")
print("=" * 60)
