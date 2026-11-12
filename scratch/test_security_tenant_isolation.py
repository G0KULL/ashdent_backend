import os
import sys

sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth.models import User
from patients.models import Company, Branch, Staff, Doctor, Patient, Appointment
from rest_framework_simplejwt.tokens import RefreshToken

print("=" * 60)
print("ASHDENT HMS: AUTOMATED SECURITY & TENANT ISOLATION TEST SUITE")
print("=" * 60)

client = APIClient()

# -------------------------------------------------------------
# 1. AUTHENTICATION & HEADER SPOOFING PROTECTION TESTS
# -------------------------------------------------------------
print("\n--- TEST GROUP 1: AUTHENTICATION & HEADER SPOOFING ---")

endpoints_to_test = [
    '/api/appointments/all/',
    '/api/patient/search/',
    '/api/bill/list/',
    '/api/finance/dashboard/',
    '/api/staff/list/',
    '/api/doctors/',
    '/api/pharmacy/queue/'
]

for ep in endpoints_to_test:
    res = client.get(ep)
    assert res.status_code == 401, f"Failed on {ep}: expected 401, got {res.status_code}"
print("[PASS] All protected endpoints returned 401 for unauthenticated requests.")

# 1.2 Header spoofing (X-User-Id / X-Username without valid Bearer token)
res = client.get('/api/patient/search/', HTTP_X_USER_ID='fake_user_id', HTTP_X_USERNAME='admin')
assert res.status_code == 401, f"Expected 401 on spoofed header, got {res.status_code}"

res = client.get('/api/finance/dashboard/', HTTP_X_USER_ID='fake_user_id', HTTP_X_USER_ROLE='Admin')
assert res.status_code == 401, f"Expected 401 on spoofed header, got {res.status_code}"
print("[PASS] Client-supplied identity headers (X-User-Id, X-Username, X-User-Role) are rejected with 401.")

# 1.3 Public endpoints
res = client.get('/api/website-appointments/')
assert res.status_code == 401, f"Expected 401 for GET /website-appointments/, got {res.status_code}"

res = client.post('/api/website-appointments/', {'name': 'Online Inquirer', 'phone': '9876543210', 'preferred_date': '2026-11-20'})
assert res.status_code in [201, 400], f"Expected 201/400 for POST /website-appointments/, got {res.status_code}"
print("[PASS] Public endpoint rules strictly enforced: POST /website-appointments/ is open, GET is protected.")

# -------------------------------------------------------------
# 2. LOGIN, JWT TOKENS & REFRESH ROTATION
# -------------------------------------------------------------
print("\n--- TEST GROUP 2: LOGIN & JWT TOKEN ROTATION ---")

# Setup Test Users
company_a, _ = Company.objects.get_or_create(code="TEST_COMP_A", defaults={"name": "Company Alpha", "is_active": True})
branch_a1, _ = Branch.objects.get_or_create(code="BR_A1", company=company_a, defaults={"name": "Alpha Main Branch", "is_active": True})
branch_a2, _ = Branch.objects.get_or_create(code="BR_A2", company=company_a, defaults={"name": "Alpha Sub Branch", "is_active": True})

company_b, _ = Company.objects.get_or_create(code="TEST_COMP_B", defaults={"name": "Company Beta", "is_active": True})
branch_b1, _ = Branch.objects.get_or_create(code="BR_B1", company=company_b, defaults={"name": "Beta Main Branch", "is_active": True})

# Admin for Company A
user_admin_a, _ = User.objects.get_or_create(username="admin_alpha", defaults={"email": "admin_alpha@ashdent.test"})
user_admin_a.set_password("AlphaPass@123")
user_admin_a.save()
staff_admin_a, _ = Staff.objects.get_or_create(
    user=user_admin_a,
    defaults={
        "name": "Alpha Admin", "role": "Admin", "company": company_a,
        "primary_branch": branch_a1, "accessible_branches": [str(branch_a1.id), str(branch_a2.id)]
    }
)
staff_admin_a.company = company_a
staff_admin_a.primary_branch = branch_a1
staff_admin_a.save()

# Doctor for Company A
user_doc_a, _ = User.objects.get_or_create(username="doc_alpha", defaults={"email": "doc_alpha@ashdent.test"})
user_doc_a.set_password("DocPass@123")
user_doc_a.save()
doc_a_prof, _ = Doctor.objects.get_or_create(name="Dr. Alpha Doctor", phone="9988776655", defaults={"company": company_a, "specialization": "Orthodontics"})
doc_a_prof.company = company_a
doc_a_prof.save()
staff_doc_a, _ = Staff.objects.get_or_create(
    user=user_doc_a,
    defaults={
        "name": "Dr. Alpha Doctor", "role": "Doctor", "company": company_a,
        "primary_branch": branch_a1, "doctor_profile": doc_a_prof
    }
)
staff_doc_a.company = company_a
staff_doc_a.save()

# Receptionist for Company A (Ordinary Staff)
user_rec_a, _ = User.objects.get_or_create(username="rec_alpha", defaults={"email": "rec_alpha@ashdent.test"})
user_rec_a.set_password("RecPass@123")
user_rec_a.save()
staff_rec_a, _ = Staff.objects.get_or_create(
    user=user_rec_a,
    defaults={
        "name": "Alpha Receptionist", "role": "Receptionist", "company": company_a,
        "primary_branch": branch_a1, "accessible_branches": [str(branch_a1.id)]
    }
)
staff_rec_a.company = company_a
staff_rec_a.save()

# Admin for Company B
user_admin_b, _ = User.objects.get_or_create(username="admin_beta", defaults={"email": "admin_beta@ashdent.test"})
user_admin_b.set_password("BetaPass@123")
user_admin_b.save()
staff_admin_b, _ = Staff.objects.get_or_create(
    user=user_admin_b,
    defaults={
        "name": "Beta Admin", "role": "Admin", "company": company_b,
        "primary_branch": branch_b1, "accessible_branches": [str(branch_b1.id)]
    }
)
staff_admin_b.company = company_b
staff_admin_b.save()

# Doctor for Company B
user_doc_b, _ = User.objects.get_or_create(username="doc_beta", defaults={"email": "doc_beta@ashdent.test"})
user_doc_b.set_password("BetaDoc@123")
user_doc_b.save()
doc_b_prof, _ = Doctor.objects.get_or_create(name="Dr. Beta Doctor", phone="9112233445", defaults={"company": company_b, "specialization": "Periodontics"})
doc_b_prof.company = company_b
doc_b_prof.save()
staff_doc_b, _ = Staff.objects.get_or_create(
    user=user_doc_b,
    defaults={
        "name": "Dr. Beta Doctor", "role": "Doctor", "company": company_b,
        "primary_branch": branch_b1, "doctor_profile": doc_b_prof
    }
)
staff_doc_b.company = company_b
staff_doc_b.save()

# Test Login for Admin Alpha
login_res = client.post('/api/login/', {'username': 'admin_alpha', 'password': 'AlphaPass@123'}, format='json')
assert login_res.status_code == 200, f"Login failed: {login_res.data}"
tokens_a = login_res.data
assert 'access' in tokens_a and 'refresh' in tokens_a
print("[PASS] Login successful; issued access and refresh tokens.")

# Test Token Refresh
ref_res = client.post('/api/token/refresh/', {'refresh': tokens_a['refresh']}, format='json')
assert ref_res.status_code == 200, f"Token refresh failed: {ref_res.data}"
assert 'access' in ref_res.data
print("[PASS] Token refresh returned fresh access token.")

# -------------------------------------------------------------
# 3. COMPANY TENANT ISOLATION TESTS
# -------------------------------------------------------------
print("\n--- TEST GROUP 3: COMPANY TENANT ISOLATION ---")

token_admin_a = tokens_a['access']
token_admin_b = str(RefreshToken.for_user(user_admin_b).access_token)
token_rec_a = str(RefreshToken.for_user(user_rec_a).access_token)

# Create Patient under Company B
patient_b, _ = Patient.objects.get_or_create(
    phone="9998887770",
    name="Patient In Beta Clinic",
    defaults={
        "company": company_b,
        "registration_branch": branch_b1,
        "gender": "Female",
        "age": 30
    }
)
patient_b.company = company_b
patient_b.save()

# 3.1 Company A Admin should NOT see Patient B in search
search_res = client.get('/api/patient/search/?q=Beta', HTTP_AUTHORIZATION=f'Bearer {token_admin_a}')
assert search_res.status_code == 200
found_ids = [str(p.get('id')) for p in search_res.data]
assert str(patient_b.id) not in found_ids, "Security breach: Company A found Patient belonging to Company B!"
print("[PASS] Cross-tenant patient isolation: Company A search does not return Company B patients.")

# 3.2 Company A Admin directly accessing Patient B profile should be rejected (403/404)
profile_res = client.get(f'/api/patient/{patient_b.id}/', HTTP_AUTHORIZATION=f'Bearer {token_admin_a}')
assert profile_res.status_code in [403, 404], f"Expected 403/404 for cross-company patient profile, got {profile_res.status_code}"
print("[PASS] Cross-tenant patient detail access blocked (403/404).")

# 3.3 Company A Admin cannot book appointment with Doctor belonging to Company B
appt_payload = {
    'patient': str(patient_b.id),
    'doctor': str(doc_b_prof.id),
    'branch': str(branch_a1.id),
    'date': '2026-11-25',
    'time': '10:00:00'
}
appt_res = client.post('/api/appointment/create/', appt_payload, HTTP_AUTHORIZATION=f'Bearer {token_admin_a}', format='json')
assert appt_res.status_code == 400, f"Expected 400 for cross-tenant appointment booking, got {appt_res.status_code}"
print("[PASS] Cross-tenant appointment reference rejected (cannot reference doctor/patient from another company).")

# 3.4 Staff List isolation: Company A Admin only sees Company A staff
staff_list_res = client.get('/api/staff/list/', HTTP_AUTHORIZATION=f'Bearer {token_admin_a}')
assert staff_list_res.status_code == 200
returned_staff_ids = [str(s.get('id')) for s in staff_list_res.data]
assert str(staff_admin_b.id) not in returned_staff_ids, "Security breach: Company A staff list leaked Company B staff!"
print("[PASS] Cross-tenant staff list isolation: Staff from other companies are not visible.")

# 3.5 Staff Update isolation: Company A Admin cannot modify Company B staff
staff_up_res = client.put(f'/api/staff/{staff_admin_b.id}/update/', {'name': 'Hacked Beta Admin'}, HTTP_AUTHORIZATION=f'Bearer {token_admin_a}', format='json')
assert staff_up_res.status_code in [403, 404], f"Expected 403/404 on cross-tenant staff modification, got {staff_up_res.status_code}"
print("[PASS] Cross-tenant staff modification blocked.")

# -------------------------------------------------------------
# 4. BRANCH ISOLATION TESTS
# -------------------------------------------------------------
print("\n--- TEST GROUP 4: BRANCH ISOLATION ---")

# 4.1 Company A Admin attempts to book at Company B's branch -> Must be rejected (403)
appt_branch_b = {
    'patient': 'non_existent',
    'doctor': str(doc_a_prof.id),
    'branch': str(branch_b1.id),
    'date': '2026-11-25',
    'time': '11:00:00'
}
res = client.post('/api/appointment/create/', appt_branch_b, HTTP_AUTHORIZATION=f'Bearer {token_admin_a}', format='json')
assert res.status_code == 403, f"Expected 403 for unauthorized branch of another company, got {res.status_code}"
print("[PASS] Access to branch of another company rejected with 403 Forbidden.")

# -------------------------------------------------------------
# 5. ROLE PRIVILEGE ESCALATION PREVENTION TESTS
# -------------------------------------------------------------
print("\n--- TEST GROUP 5: ROLE PERMISSIONS & ESCALATION PREVENTION ---")

# 5.1 Ordinary Staff (Receptionist) attempting to view staff management list -> 403 Forbidden
rec_staff_res = client.get('/api/staff/list/', HTTP_AUTHORIZATION=f'Bearer {token_rec_a}')
assert rec_staff_res.status_code == 403, f"Expected 403 for ordinary staff accessing /api/staff/list/, got {rec_staff_res.status_code}"
print("[PASS] Ordinary staff access to admin staff endpoint rejected with 403 Forbidden.")

# 5.2 Application Admin attempting to create Super Admin account -> Rejected (403)
escalation_payload = {
    'name': 'Rogue Super Admin',
    'username': 'rogue_super',
    'password': 'Password@123',
    'role': 'Super Admin',
    'staff_level': 'Senior',
    'phone': '9811223344',
    'gender': 'Male',
    'age': 35,
    'dob': '1990-01-01',
    'blood_group': 'O+',
    'address': 'Test City'
}
esc_res = client.post('/api/staff/create/', escalation_payload, HTTP_AUTHORIZATION=f'Bearer {token_admin_a}', format='json')
assert esc_res.status_code == 403, f"Expected 403 when Application Admin tries to create Super Admin, got {esc_res.status_code}"
print("[PASS] Application Admin privilege escalation blocked (cannot create Super Admin).")

# 5.3 Application Admin attempting to create another Admin account -> Rejected (403)
admin_create_payload = dict(escalation_payload, role='Admin', username='second_admin', phone='9811223345')
adm_res = client.post('/api/staff/create/', admin_create_payload, HTTP_AUTHORIZATION=f'Bearer {token_admin_a}', format='json')
assert adm_res.status_code == 403, f"Expected 403 when Application Admin tries to create Admin, got {adm_res.status_code}"
print("[PASS] Application Admin cannot create other Admin accounts (403 Forbidden).")

print("\n" + "=" * 60)
print(">>> ALL 12 SECURITY & TENANT ISOLATION TESTS PASSED WITH 100% SUCCESS! <<<")
print("=" * 60)
