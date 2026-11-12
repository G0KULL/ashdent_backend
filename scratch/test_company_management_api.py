import sys, os
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

from rest_framework.test import APIClient
from django.contrib.auth.models import User
from patients.models import Company, Branch, Staff, Patient

client = APIClient()

print("=" * 80)
print("TESTING COMPANY MANAGEMENT API & PERMISSIONS")
print("=" * 80)

# 1. Test unauthenticated request
res = client.get('/api/companies/')
print(f"Unauthenticated GET /api/companies/ -> Status: {res.status_code} (Expected: 401)")
assert res.status_code == 401, f"Expected 401, got {res.status_code}"

# 2. Test Super Admin login
login_super = client.post('/api/login/', {'username': 'admin', 'password': 'admin123'}, format='json')
assert login_super.status_code == 200, f"Super admin login failed: {login_super.data}"
token_super = login_super.data['access']
client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_super}')

# List companies
res = client.get('/api/companies/')
print(f"Super Admin GET /api/companies/ -> Status: {res.status_code}, Found {len(res.data)} companies")
assert res.status_code == 200

# 3. Create a clean test company
new_comp_code = 'TEST_DEL_CO'
Company.objects.filter(code=new_comp_code).delete()

payload = {
    'name': 'Test Deletable Company',
    'code': new_comp_code,
    'email': 'contact@testdeletable.com',
    'phone': '+91 9876543210',
    'contact_person': 'Dr. Test Administrator',
    'address': '123 Health Ave, Medical City',
    'registration_number': 'REG-123456',
    'tax_number': 'GSTIN-987654321'
}

res_create = client.post('/api/companies/', payload, format='json')
print(f"Super Admin POST /api/companies/ -> Status: {res_create.status_code}")
assert res_create.status_code == 201, f"Create failed: {res_create.data}"
test_comp_id = res_create.data['id']
print(f"Created Company ID: {test_comp_id}, Name: {res_create.data['name']}, Code: {res_create.data['code']}")

# Test duplicate code rejection
res_dup = client.post('/api/companies/', payload, format='json')
print(f"Duplicate POST /api/companies/ -> Status: {res_dup.status_code} (Expected: 400)")
assert res_dup.status_code == 400

# 4. Test Edit Company
edit_payload = {
    'name': 'Test Deletable Company (Updated)',
    'contact_person': 'Dr. Updated Person'
}
res_edit = client.patch(f'/api/companies/{test_comp_id}/', edit_payload, format='json')
print(f"Super Admin PATCH /api/companies/{test_comp_id}/ -> Status: {res_edit.status_code}, Name: {res_edit.data.get('name')}")
assert res_edit.status_code == 200
assert res_edit.data['name'] == 'Test Deletable Company (Updated)'

# 5. Test Dependency Check (initial clean company has 1 auto-created main branch, 0 operational records)
res_dep = client.get(f'/api/companies/{test_comp_id}/dependency-check/')
print(f"Dependency Check -> Can Delete: {res_dep.data.get('can_delete')}, Deps: {res_dep.data.get('dependent_records')}")
assert res_dep.status_code == 200
assert res_dep.data['can_delete'] == True

# 6. Add an operational record (e.g. Patient) and verify deletion is BLOCKED
comp_obj = Company.objects.get(pk=test_comp_id)
pat = Patient.objects.create(name="Temp Test Patient", company=comp_obj)
print(f"Created temporary patient {pat.name} ({pat.id}) for company {comp_obj.name}")

res_dep_blocked = client.get(f'/api/companies/{test_comp_id}/dependency-check/')
print(f"Dependency Check after adding patient -> Can Delete: {res_dep_blocked.data.get('can_delete')}")
assert res_dep_blocked.data['can_delete'] == False

res_del_blocked = client.delete(f'/api/companies/{test_comp_id}/')
print(f"DELETE /api/companies/{test_comp_id}/ with patient -> Status: {res_del_blocked.status_code} (Expected: 400)")
assert res_del_blocked.status_code == 400
assert 'Cannot permanently delete company' in res_del_blocked.data.get('error', '')

# Deactivate/Reactivate test
res_deact = client.patch(f'/api/companies/{test_comp_id}/', {'is_active': False}, format='json')
print(f"Deactivate Company -> Status: {res_deact.status_code}, is_active: {res_deact.data.get('is_active')}")
assert res_deact.data['is_active'] == False

res_react = client.patch(f'/api/companies/{test_comp_id}/', {'is_active': True}, format='json')
print(f"Reactivate Company -> Status: {res_react.status_code}, is_active: {res_react.data.get('is_active')}")
assert res_react.data['is_active'] == True

# Clean up patient so company can be deleted
pat.delete()

# 7. Test successful permanent delete of clean company
res_del_ok = client.delete(f'/api/companies/{test_comp_id}/')
print(f"DELETE /api/companies/{test_comp_id}/ after patient removed -> Status: {res_del_ok.status_code}")
assert res_del_ok.status_code == 200
assert not Company.objects.filter(pk=test_comp_id).exists()
print("Clean company deleted successfully and verified removed from database!")

# 8. Test Regular Admin / Staff restrictions
# Login as doctor or non-superadmin
login_doc = client.post('/api/login/', {'username': 'test_alpha_doc', 'password': 'DocPass@123'}, format='json')
if login_doc.status_code == 200:
    token_doc = login_doc.data['access']
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_doc}')
    res_doc_post = client.post('/api/companies/', {'name': 'Hacked Co', 'code': 'HACK'}, format='json')
    print(f"Doctor POST /api/companies/ -> Status: {res_doc_post.status_code} (Expected: 403)")
    assert res_doc_post.status_code == 403
    res_doc_del = client.delete(f'/api/companies/6ae8789e3196288d38aadf8f/')
    print(f"Doctor DELETE /api/companies/ -> Status: {res_doc_del.status_code} (Expected: 403)")
    assert res_doc_del.status_code == 403

print("\nALL BACKEND COMPANY MANAGEMENT API TESTS PASSED SUCCESSFULLY!")

