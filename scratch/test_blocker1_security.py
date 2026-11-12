import sys, os
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
os.environ['DJANGO_DB_NAME'] = 'dental_clinic_db_migrated'
import django; django.setup()

from rest_framework.test import APIClient
from patients.models import Patient, Company, Branch, Appointment, Billing, Prescription

client = APIClient()

# Identify Alpha and Beta
comp_alpha = Company.objects.filter(code='COMP_ALPHA').first()
comp_beta = Company.objects.filter(code='COMP_BETA').first()
branch_alpha = Branch.objects.filter(company=comp_alpha).first()
branch_beta = Branch.objects.filter(company=comp_beta).first()

# Alpha Patient
alpha_pt = Patient.objects.filter(company=comp_alpha).first()
print(f"Alpha Company: {comp_alpha.name} ({comp_alpha.id})")
print(f"Alpha Patient: {alpha_pt.name} ({alpha_pt.id})")
print(f"Beta Company : {comp_beta.name} ({comp_beta.id})")

# 1. Login as Beta Admin
login_beta = client.post('/api/login/', {'username': 'wf_admin_beta', 'password': 'BetaPass@123'}, format='json')
beta_token = login_beta.data.get('access')
client.credentials(HTTP_AUTHORIZATION=f'Bearer {beta_token}', HTTP_X_BRANCH_ID=str(branch_beta.id))

print("\n" + "=" * 80)
print("TESTING 9 REMEDIATED ENDPOINTS FROM BETA ADMIN (MUST NOT LEAK ALPHA DATA)")
print("=" * 80)

tests = [
    ("01. BillingListView (/api/bill/list/)", f"/api/bill/list/", "GET", None),
    ("02. PatientEMRDetailView (/api/patients/<id>/emr/)", f"/api/patients/{alpha_pt.id}/emr/", "GET", None),
    ("03. PatientToothConditionsView (/api/patients/<id>/tooth-conditions/)", f"/api/patients/{alpha_pt.id}/tooth-conditions/", "GET", None),
    ("04. PatientTreatmentHistoryView (/api/patient/<id>/treatment-history/)", f"/api/patient/{alpha_pt.id}/treatment-history/", "GET", None),
    ("05. RecentPaymentsView (/api/payments/recent/)", f"/api/payments/recent/", "GET", None),
    ("06. PrescriptionListView (/api/prescription/list/)", f"/api/prescription/list/", "GET", None),
    ("07. AppointmentByPatientView (/api/appointment/patient/<id>/)", f"/api/appointment/patient/{alpha_pt.id}/", "GET", None),
    ("08. PatientUnbilledTreatmentsView (/api/patients/<id>/unbilled-treatments/)", f"/api/patients/{alpha_pt.id}/unbilled-treatments/", "GET", None),
    ("09. RecentPatientsView (/api/patients/recent/)", f"/api/patients/recent/", "GET", None),
]

all_passed = True
results = []

for label, url, method, body in tests:
    res = client.get(url)
    status_code = res.status_code
    
    # Check criteria:
    # Patient-specific views must return 403 Forbidden!
    # List views must return 200 with 0 Alpha records!
    passed = False
    details = ""
    
    if any(k in label for k in ['EMR', 'ToothConditions', 'TreatmentHistory', 'AppointmentByPatient', 'UnbilledTreatments']):
        passed = (status_code == 403)
        details = f"Status: {status_code} (Expected 403 Forbidden)"
    elif 'BillingListView' in label:
        passed = (status_code == 200 and len(res.data) == 0) # Beta has 0 bills currently
        details = f"Status: {status_code}, Returned {len(res.data)} bills (0 Alpha bills leaked)"
    elif 'RecentPayments' in label:
        passed = (status_code == 200 and len(res.data) == 0)
        details = f"Status: {status_code}, Returned {len(res.data)} payments"
    elif 'PrescriptionList' in label:
        passed = (status_code == 200 and len(res.data) == 0)
        details = f"Status: {status_code}, Returned {len(res.data)} prescriptions"
    elif 'RecentPatients' in label:
        # Check that none of the returned patients belong to Alpha
        returned_alpha = any(str(p.get('company')) == str(comp_alpha.id) or p.get('name') == alpha_pt.name for p in res.data)
        passed = (status_code == 200 and not returned_alpha)
        details = f"Status: {status_code}, Returned {len(res.data)} patients, Alpha leaked: {returned_alpha}"
        
    print(f"[{'PASS' if passed else 'FAIL'}] {label}\n       -> {details}")
    if not passed:
        all_passed = False
    results.append({'label': label, 'passed': passed, 'details': details})

print("\n" + "=" * 80)
print(f"SECURITY AUDIT RESULT: {'ALL 9 PASSED' if all_passed else 'SOME FAILED'}")
print("=" * 80)

