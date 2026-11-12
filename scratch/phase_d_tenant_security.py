import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
os.environ.setdefault('DJANGO_DB_NAME', 'dental_clinic_db_migrated')
import django; django.setup()

from rest_framework.test import APIClient
from django.contrib.auth.models import User
from patients.models import (
    Company, Branch, Staff, Doctor, Patient, Appointment, Visit,
    ClinicalNotes, ToothConditionRecord, TreatmentPlan, TreatmentPlanItem,
    TreatmentRecord, PatientInvestigation, InvestigationAttachment,
    Prescription, PrescriptionItem, Estimate, Billing, BillPayment, Transaction
)

client = APIClient()

# Identify Alpha and Beta entities
comp_alpha = Company.objects.filter(code='COMP_ALPHA').first()
comp_beta = Company.objects.filter(code='COMP_BETA').first()
branch_alpha = Branch.objects.filter(company=comp_alpha).first()
branch_beta = Branch.objects.filter(company=comp_beta).first()

# Alpha records for target testing
alpha_patient = Patient.objects.filter(company=comp_alpha).first()
alpha_appt = Appointment.objects.filter(company=comp_alpha).first()
alpha_visit = Visit.objects.filter(company=comp_alpha).first()
alpha_note = ClinicalNotes.objects.filter(appointment__company=comp_alpha).first()
alpha_tc = ToothConditionRecord.objects.filter(patient=alpha_patient).first()
alpha_plan = TreatmentPlan.objects.filter(patient=alpha_patient).first()
alpha_item = TreatmentPlanItem.objects.filter(plan__patient=alpha_patient).first()
alpha_tr = TreatmentRecord.objects.filter(visit__company=comp_alpha).first()
alpha_inv = PatientInvestigation.objects.filter(patient=alpha_patient).first()
alpha_rx = Prescription.objects.filter(company=comp_alpha).first()
alpha_est = Estimate.objects.filter(company=comp_alpha).first()
alpha_bill = Billing.objects.filter(company=comp_alpha).first()
alpha_bp = BillPayment.objects.filter(company=comp_alpha).first()

print("=" * 80)
print("PHASE D: EXHAUSTIVE TENANT SECURITY TESTING")
print("=" * 80)
print(f"Alpha Company: {comp_alpha.name} ({comp_alpha.id})")
print(f"Beta Company : {comp_beta.name} ({comp_beta.id})")
print(f"Target Alpha Patient: {alpha_patient.name} ({alpha_patient.id})")

# Define all 18 endpoint test cases across domains
test_endpoints = [
    # 1. Patient Profile
    ('Patient Profile (GET)', f'/api/patient/{alpha_patient.id}/profile/', 'GET', None),
    # 2. Patient Clinical History
    ('Patient Clinical History (GET)', f'/api/patient/{alpha_patient.id}/clinical-history/', 'GET', None),
    # 3. Patient EMR Detail
    ('Patient EMR Detail (GET)', f'/api/patients/{alpha_patient.id}/emr/', 'GET', None),
    # 4. Patient EMR PDF Report
    ('EMR PDF Report (GET)', f'/api/patients/{alpha_patient.id}/emr-report/pdf/', 'GET', None),
    # 5. Patient Tooth Conditions
    ('Tooth Conditions (GET)', f'/api/patients/{alpha_patient.id}/tooth-conditions/', 'GET', None),
    # 6. Tooth Conditions Update
    ('Tooth Conditions (POST)', f'/api/patients/{alpha_patient.id}/tooth-conditions/', 'POST', {'teeth_data': {'11': 'Caries'}}),
    # 7. Treatment Plans List
    ('Treatment Plans (GET)', f'/api/patients/{alpha_patient.id}/treatment-plans/', 'GET', None),
    # 8. Treatment Plan Item Update
    ('Treatment Plan Item (PATCH)', f'/api/treatment-plan-items/{alpha_item.id if alpha_item else \"6aeef65ff054fbd01ad70ddd\"}/', 'PATCH', {'status': 'Completed'}) if alpha_item else None,
    # 9. Treatment History
    ('Treatment History (GET)', f'/api/patient/{alpha_patient.id}/treatment-history/', 'GET', None),
    # 10. Patient Unbilled Treatments
    ('Unbilled Treatments (GET)', f'/api/patients/{alpha_patient.id}/unbilled-treatments/', 'GET', None),
    # 11. Appointment by Patient
    ('Appointment by Patient (GET)', f'/api/appointment/patient/{alpha_patient.id}/', 'GET', None),
    # 12. Investigation Detail
    ('Investigation Detail (GET)', f'/api/patient-investigations/{alpha_inv.id if alpha_inv else \"6aeef65ff054fbd01ad70de0\"}/', 'GET', None) if alpha_inv else None,
    # 13. Patient Image List
    ('Patient Images (GET)', f'/api/patient-images/?patient_id={alpha_patient.id}', 'GET', None),
    # 14. Billing List
    ('Billing List (GET)', '/api/bill/list/', 'GET', None),
    # 15. Bill Payments Detail
    ('Bill Payments (GET)', f'/api/billing/{alpha_bill.id if alpha_bill else \"6aeef65ff054fbd01ad70de8\"}/payments/', 'GET', None) if alpha_bill else None,
    # 16. Record Payment
    ('Record Payment (POST)', f'/api/billing/{alpha_bill.id if alpha_bill else \"6aeef65ff054fbd01ad70de8\"}/payments/', 'POST', {'amount': 500.0, 'payment_method': 'Cash'}) if alpha_bill else None,
    # 17. Recent Payments List
    ('Recent Payments (GET)', '/api/payments/recent/', 'GET', None),
    # 18. Prescription List
    ('Prescription List (GET)', '/api/prescription/list/', 'GET', None),
    # 19. Recent Patients List
    ('Recent Patients (GET)', '/api/patients/recent/', 'GET', None),
    # 20. Payment Search
    ('Payment Search (GET)', f'/api/payments/search/?patient_id={alpha_patient.id}', 'GET', None),
]
test_endpoints = [t for t in test_endpoints if t is not None]

roles_to_test = [
    ('Super Admin', 'test_super_admin', 'SuperPass@123', None, True),
    ('Company Alpha Admin', 'test_alpha_admin', 'AdminPass@123', branch_alpha, False),
    ('Company Beta Admin', 'test_beta_admin', 'AdminPass@123', branch_beta, False),
    ('Alpha Doctor', 'test_alpha_doc', 'DocPass@123', branch_alpha, False),
    ('Beta Doctor', 'test_beta_doc', 'DocPass@123', branch_beta, False),
    ('Alpha Receptionist', 'test_alpha_rec', 'RecPass@123', branch_alpha, False),
    ('Beta Receptionist', 'test_beta_rec', 'RecPass@123', branch_beta, False),
]

matrix_results = []

for role_name, username, password, branch, is_super in roles_to_test:
    login_res = client.post('/api/login/', {'username': username, 'password': password}, format='json')
    token = login_res.data.get('access')
    headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
    if branch:
        headers['HTTP_X_BRANCH_ID'] = str(branch.id)
    client.credentials(**headers)
    
    is_beta = 'Beta' in role_name
    print(f"\n--- Testing Role: {role_name} (is_super={is_super}, is_beta={is_beta}) ---")
    
    for label, url, method, body in test_endpoints:
        if method == 'GET':
            res = client.get(url)
        elif method == 'POST':
            res = client.post(url, body, format='json')
        elif method == 'PATCH':
            res = client.patch(url, body, format='json')
            
        status_code = res.status_code
        
        # Determine pass/fail
        passed = False
        if is_beta:
            # Beta MUST receive 403 Forbidden on patient-specific endpoints,
            # or 200 with 0 Alpha records on list endpoints!
            if 'List' in label or label == 'Recent Patients (GET)':
                if isinstance(res.data, list):
                    leaked = any(str(item.get('company')) == str(comp_alpha.id) or str(item.get('patient')) == str(alpha_patient.id) for item in res.data if isinstance(item, dict))
                    passed = (status_code == 200 and not leaked)
                else:
                    passed = (status_code == 200)
            else:
                passed = (status_code in [403, 404])
        else:
            # Super Admin and Alpha users should have valid access (200 or 201)
            # (unless role-restricted, e.g. Receptionist cannot PATCH treatment plan)
            if 'Receptionist' in role_name and ('PATCH' in method or 'Item' in label):
                passed = (status_code in [200, 403]) # Acceptable if role-restricted
            else:
                passed = (status_code in [200, 201])
                
        matrix_results.append({
            'role': role_name,
            'endpoint': label,
            'url': url,
            'method': method,
            'status_code': status_code,
            'passed': passed
        })
        print(f"  [{'PASS' if passed else 'FAIL'}] {label:32} -> Status: {status_code}")

with open('ashdent-back/scratch/phase_d_security_matrix.json', 'w') as f:
    json.dump(matrix_results, f, indent=2)

total_tests = len(matrix_results)
passed_tests = sum(1 for r in matrix_results if r['passed'])
print("\n" + "=" * 80)
print(f"PHASE D SECURITY MATRIX SUMMARY: {passed_tests}/{total_tests} TESTS PASSED ({(passed_tests/total_tests)*100:.1f}%)")
print("=" * 80)

