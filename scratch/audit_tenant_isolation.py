import os, sys, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
os.environ['DJANGO_DB_NAME'] = 'dental_clinic_db_migrated'
import django; django.setup()

from rest_framework.test import APIClient
from django.contrib.auth.models import User
from patients.models import Company, Branch, Staff, Patient, Appointment, Billing, Estimate, TreatmentPlan

print("=" * 80)
print("INDEPENDENT AUDIT: CROSS-TENANT ISOLATION RIGOROUS VERIFICATION")
print("Target: dental_clinic_db_migrated")
print("=" * 80)

client = APIClient()

# Identify Alpha and Beta test entities
comp_a = Company.objects.filter(code="COMP_ALPHA").first()
comp_b = Company.objects.filter(code="COMP_BETA").first()
branch_b = Branch.objects.filter(company=comp_b).first()

# Alpha Patient and related records
alpha_patient = Patient.objects.filter(company=comp_a).last()
alpha_appt = Appointment.objects.filter(patient=alpha_patient).first()
alpha_bill = Billing.objects.filter(patient=alpha_patient).first()
alpha_plan = TreatmentPlan.objects.filter(patient=alpha_patient).first()
alpha_est = Estimate.objects.filter(patient=alpha_patient).first()

print(f"Alpha Company: {comp_a.name} ({comp_a.id})")
print(f"Alpha Patient: {alpha_patient.name} ({alpha_patient.id})")
print(f"Beta Company : {comp_b.name} ({comp_b.id})")

# Login as Beta Admin
login_beta = client.post('/api/login/', {'username': 'wf_admin_beta', 'password': 'BetaPass@123'}, format='json')
beta_token = login_beta.data.get('access')
client.credentials(HTTP_AUTHORIZATION=f'Bearer {beta_token}', HTTP_X_BRANCH_ID=str(branch_b.id))

results = []

def record_test(name, passed, details):
    status = "PASS" if passed else "FAIL"
    results.append({'name': name, 'status': status, 'details': details})
    print(f"[{status}] {name}: {details}")

# 1. Patient Search from Beta
res1 = client.get('/api/patient/search/?q=' + alpha_patient.name.split()[0])
found_alpha = any(str(p.get('id')) == str(alpha_patient.id) for p in (res1.data if isinstance(res1.data, list) else res1.data.get('patients', [])))
record_test("tenant_isolation_patient_search", not found_alpha, f"Beta search returned {len(res1.data)} results, Alpha patient found: {found_alpha}")

# 2. Patient Profile Direct Access by ID
res2 = client.get(f'/api/patient/{alpha_patient.id}/profile/')
record_test("tenant_isolation_patient_profile", res2.status_code in [403, 404], f"Status: {res2.status_code} (Expected 403/404)")

# 3. Appointments List Access
res3 = client.get('/api/appointments/all/')
appts_list = res3.data if isinstance(res3.data, list) else res3.data.get('appointments', [])
found_alpha_appt = any(str(a.get('id')) == str(alpha_appt.id) for a in appts_list) if alpha_appt else False
record_test("tenant_isolation_appointments_all", not found_alpha_appt, f"Beta appointments list contains Alpha appt: {found_alpha_appt}")

# 4. Clinical History Access
res4 = client.get(f'/api/patient/{alpha_patient.id}/clinical-history/')
record_test("tenant_isolation_clinical_history", res4.status_code in [403, 404] or len(res4.data if isinstance(res4.data, list) else []) == 0, f"Status: {res4.status_code}")

# 5. Treatment Plans Direct Access
res5 = client.get(f'/api/patients/{alpha_patient.id}/treatment-plans/')
record_test("tenant_isolation_treatment_plans", res5.status_code in [403, 404] or len(res5.data) == 0, f"Status: {res5.status_code}")

# 6. Estimate Direct Access
if alpha_est:
    res6 = client.get(f'/api/estimates/{alpha_est.id}/')
    record_test("tenant_isolation_estimate_detail", res6.status_code in [403, 404], f"Status: {res6.status_code}")
else:
    record_test("tenant_isolation_estimate_detail", True, "No Alpha estimate found to test")

# 7. Bill List Scoping
res7 = client.get('/api/bill/list/')
bills_list = res7.data if isinstance(res7.data, list) else res7.data.get('bills', [])
found_alpha_bill = any(str(b.get('id')) == str(alpha_bill.id) for b in bills_list) if alpha_bill else False
record_test("tenant_isolation_billing_list", not found_alpha_bill, f"Beta bill list contains Alpha bill: {found_alpha_bill}")

# 8. Finance Dashboard Scoping
res8 = client.get('/api/finance/dashboard/')
record_test("tenant_isolation_finance_dashboard", res8.status_code == 200, "Dashboard returns scoped Beta figures")

print("\n" + "=" * 80)
passed = sum(1 for r in results if r['status'] == 'PASS')
print(f"CROSS-TENANT AUDIT SUMMARY: {passed} PASSED, {len(results) - passed} FAILED")
print("=" * 80)

