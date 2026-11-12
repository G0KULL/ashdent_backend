import os, sys, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
os.environ.setdefault('DJANGO_DB_NAME', 'dental_clinic_db_migrated')
import django; django.setup()

from rest_framework.test import APIClient
from django.contrib.auth.models import User
from patients.models import Company, Branch, Staff, Doctor, Patient, Appointment, Visit, ClinicalNotes, TreatmentPlan, TreatmentPlanItem, Estimate, Billing, BillPayment, TreatmentMaster
from decimal import Decimal

print("=" * 70)
print("STAGE 4: 20 CLINICAL & FINANCIAL WORKFLOW VERIFICATIONS")
print("Target Database: dental_clinic_db_migrated")
print("=" * 70)

client = APIClient()

workflow_results = []

def record_workflow(test_num, name, passed, details):
    status = "PASS" if passed else "FAIL"
    workflow_results.append({
        "test_num": test_num,
        "name": name,
        "status": status,
        "details": details
    })
    print(f"[{status}] Test {test_num:02d} - {name}: {details}")

# --- Setup Test Environment and Auth Tokens ---
company_a, _ = Company.objects.get_or_create(code="COMP_ALPHA", defaults={"name": "Alpha Dental Care", "is_active": True})
branch_a, _ = Branch.objects.get_or_create(code="BR_ALPHA_MAIN", company=company_a, defaults={"name": "Alpha Central", "is_active": True})

company_b, _ = Company.objects.get_or_create(code="COMP_BETA", defaults={"name": "Beta Dental Care", "is_active": True})
branch_b, _ = Branch.objects.get_or_create(code="BR_BETA_MAIN", company=company_b, defaults={"name": "Beta Central", "is_active": True})

# Alpha Admin
user_a, _ = User.objects.get_or_create(username="wf_admin_alpha", defaults={"email": "wf_admin_alpha@ashdent.test"})
user_a.set_password("AlphaPass@123")
user_a.save()
staff_a, _ = Staff.objects.get_or_create(
    user=user_a,
    defaults={
        "name": "Alpha Admin", "role": "Admin", "company": company_a,
        "primary_branch": branch_a, "accessible_branches": [str(branch_a.id)]
    }
)
staff_a.company = company_a
staff_a.primary_branch = branch_a
staff_a.save()

# Alpha Doctor
doc_a, _ = Doctor.objects.get_or_create(name="Dr. Alpha Specialist", defaults={"company": company_a, "primary_branch": branch_a, "specialization": "Endodontics"})
doc_a.company = company_a
doc_a.primary_branch = branch_a
doc_a.save()

# Beta Admin
user_b, _ = User.objects.get_or_create(username="wf_admin_beta", defaults={"email": "wf_admin_beta@ashdent.test"})
user_b.set_password("BetaPass@123")
user_b.save()
staff_b, _ = Staff.objects.get_or_create(
    user=user_b,
    defaults={
        "name": "Beta Admin", "role": "Admin", "company": company_b,
        "primary_branch": branch_b, "accessible_branches": [str(branch_b.id)]
    }
)
staff_b.company = company_b
staff_b.primary_branch = branch_b
staff_b.save()

# Login Alpha Admin
login_res = client.post('/api/login/', {'username': 'wf_admin_alpha', 'password': 'AlphaPass@123'}, format='json')
alpha_token = login_res.data.get('access')
client.credentials(HTTP_AUTHORIZATION=f'Bearer {alpha_token}', HTTP_X_BRANCH_ID=str(branch_a.id))

# Ensure Dr. Alpha has weekly schedule configured and approved
sched_res = client.post('/api/doctor-schedules/direct/', {
    'doctor_id': str(doc_a.id),
    'branch_id': str(branch_a.id),
    'mode': 'FULL_WEEK',
    'slots': [{'day_of_week': i, 'start_time': '09:00:00', 'end_time': '18:00:00', 'is_available': True} for i in range(7)]
}, format='json')

created_data = {}

# 1. Patient Registration
Patient.objects.filter(phone='9845012345').delete()
res1 = client.post('/api/patient/create/', {
    'firstName': 'Arthur',
    'lastName': 'Dentist',
    'phone': '9845012345',
    'gender': 'Male',
    'age': 35,
    'city': 'Bangalore',
    'doctor_id': str(doc_a.id)
}, format='json')
p_id = res1.data.get('id') or (res1.data.get('patient', {}).get('id'))
created_data['patient_id'] = p_id
record_workflow(1, "Patient Registration", res1.status_code in [200, 201] and p_id is not None, f"Patient ID: {p_id}")

# 2. Patient Profile Retrieval
res2 = client.get(f'/api/patient/{p_id}/profile/')
pat_data = res2.data.get('patient', {}) if isinstance(res2.data, dict) else {}
record_workflow(2, "Patient Profile Retrieval", res2.status_code == 200 and 'Arthur' in str(pat_data.get('name')), f"Name: {pat_data.get('name')}")

# 3. Patient Search (Name and Phone)
res3 = client.get('/api/patient/search/?q=Arthur')
search_list = res3.data if isinstance(res3.data, list) else res3.data.get('patients', [])
matches = [p for p in search_list if str(p.get('id')) == str(p_id)]
record_workflow(3, "Patient Search by Name & Phone", res3.status_code == 200 and len(matches) > 0, f"Found {len(matches)} matching Arthur Dent")

# 4. Doctor Schedule Slot Retrieval
res4 = client.get(f'/api/doctors/{doc_a.id}/available-slots/?date=2026-11-20')
slots = res4.data.get('available_slots') or res4.data.get('slots') or []
record_workflow(4, "Doctor Available Slot Retrieval", res4.status_code == 200 and len(slots) > 0, f"Retrieved {len(slots)} slots")

# 5. Appointment Booking
from django.db import connections
connections['default'].database['patients_slot_lock'].delete_many({'doctor_id': str(doc_a.id)})
Appointment.objects.filter(doctor=doc_a, date='2026-11-20', time='10:00').delete()
res5 = client.post('/api/appointment/create/', {
    'patient': str(p_id),
    'doctor': str(doc_a.id),
    'branch': str(branch_a.id),
    'date': '2026-11-20',
    'time': '10:00',
    'reason': 'Tooth pain in lower molar'
}, format='json')
appt_id = str(res5.data.get('id')) if res5.data.get('id') else None
created_data['appointment_id'] = appt_id
record_workflow(5, "Appointment Booking", res5.status_code in [200, 201] and appt_id is not None, f"Appt ID: {appt_id}")

# 6. Appointment Slot Conflict Detection
res6 = client.post('/api/appointment/create/', {
    'patient': str(p_id),
    'doctor': str(doc_a.id),
    'branch': str(branch_a.id),
    'date': '2026-11-20',
    'time': '10:00',
    'reason': 'Duplicate slot booking test'
}, format='json')
conflict_detected = (res6.status_code in [400, 409]) or ('conflict' in str(res6.data).lower() or 'already' in str(res6.data).lower())
record_workflow(6, "Appointment Conflict Detection", conflict_detected, f"Conflict response status: {res6.status_code}, error: {res6.data.get('error')}")

# 7. Appointment Status Lifecycle Update
res7 = client.patch(f'/api/appointments/{appt_id}/status/', {'status': 'Completed'}, format='json')
record_workflow(7, "Appointment Status Lifecycle (Completed)", res7.status_code == 200 and res7.data.get('status') == 'Completed', f"Status: {res7.data.get('status')}")

# 8. Visit Creation Linked to Appointment
res8 = client.post('/api/visit/get-or-create/', {
    'appointment_id': str(appt_id),
    'patient_id': str(p_id)
}, format='json')
visit_id = res8.data.get('visit_id') or res8.data.get('id')
created_data['visit_id'] = visit_id
record_workflow(8, "Visit Generation", res8.status_code in [200, 201] and visit_id is not None, f"Visit ID: {visit_id}")

# 9. Clinical Notes Entry
res9 = client.post('/api/clinical-notes/save/', {
    'appointment_id': str(appt_id),
    'patient_id': str(p_id),
    'doctor_id': str(doc_a.id),
    'complaints': 'Severe nocturnal pain in lower right molar 46',
    'observations': 'Deep occlusal caries approaching pulp on tooth 46',
    'diagnosis': 'Irreversible Pulpitis',
    'notes': 'Advised Root Canal Treatment and ceramic crown'
}, format='json')
note_id = res9.data.get('id') or (res9.data.get('clinical_notes', {}).get('id'))
created_data['note_id'] = note_id
record_workflow(9, "Clinical Notes Entry", res9.status_code in [200, 201] and note_id is not None, f"Note ID: {note_id}")

# 10. Tooth Condition / Odontogram Notation
res10 = client.post(f'/api/patients/{p_id}/tooth-conditions/', {
    'appointment_id': str(appt_id),
    'visit_id': str(visit_id),
    'teeth_data': {
        '46': {'condition': 'Deep Caries', 'surface': 'MOD', 'status': 'Needs Treatment'}
    }
}, format='json')
record_workflow(10, "Tooth Condition / Odontogram Notation", res10.status_code in [200, 201], "Tooth 46 marked Deep Caries")

# 11. Clinical Masters Dynamic Registration
res11 = client.post('/api/masters/auto-create/', {
    'type': 'diagnosis',
    'name': 'Acute Irreversible Pulpitis'
}, format='json')
record_workflow(11, "Clinical Masters Dynamic Registration", res11.status_code in [200, 201], "Master diagnosis registered")

# 12. Treatment Plan Creation
res12 = client.post(f'/api/patients/{p_id}/treatment-plans/', {
    'title': 'Root Canal Treatment & Crown (46)',
    'status': 'Proposed',
    'items': [
        {
            'tooth_number': '46',
            'procedure_name': 'Molar Root Canal Therapy',
            'cost': 4500.00,
            'status': 'Proposed',
            'surface': 'MOD'
        },
        {
            'tooth_number': '46',
            'procedure_name': 'Zirconia Crown',
            'cost': 7500.00,
            'status': 'Proposed',
            'surface': 'All'
        }
    ]
}, format='json')
plan_id = res12.data.get('plan_id') or res12.data.get('id')
created_data['plan_id'] = plan_id
record_workflow(12, "Treatment Plan Creation", res12.status_code in [200, 201] and plan_id is not None, f"Plan ID: {plan_id}")

# 13. Treatment Plan Items Retrieval
res13 = client.get(f'/api/patients/{p_id}/treatment-plans/')
plan_items_count = len(res13.data[0].get('items', [])) if (isinstance(res13.data, list) and len(res13.data) > 0) else 0
record_workflow(13, "Treatment Plan Items Retrieval", res13.status_code == 200 and plan_items_count >= 2, f"Found {plan_items_count} items in plan")

# 14. Estimate Generation from Treatment Plan
res14 = client.post(f'/api/patients/{p_id}/estimates/', {
    'treatment_plan_id': str(plan_id),
    'title': 'Estimate for Tooth 46 RCT & Crown',
    'discount': 500.00,
    'items': [
        {'procedure_name': 'Molar Root Canal Therapy', 'unit_price': 4500.00, 'quantity': 1},
        {'procedure_name': 'Zirconia Crown', 'unit_price': 7500.00, 'quantity': 1}
    ]
}, format='json')
estimate_id = res14.data.get('id') or (res14.data.get('estimate', {}).get('id'))
created_data['estimate_id'] = estimate_id
record_workflow(14, "Estimate Generation", res14.status_code in [200, 201] and estimate_id is not None, f"Estimate ID: {estimate_id}")

# 15. Treatment Record Progression
t_master, _ = TreatmentMaster.objects.get_or_create(name='Molar Root Canal Therapy', defaults={'price': Decimal('4500.00'), 'is_active': True})
res15 = client.post('/api/treatment-record/create/', {
    'visit': str(visit_id),
    'treatment': str(t_master.id),
    'tooth_number': '46',
    'doctor_id': str(doc_a.id)
}, format='json')
record_workflow(15, "Treatment Record Creation", res15.status_code in [200, 201], "Treatment record started")

# 16. Prescription Creation with Items
res16 = client.post('/api/prescription/add/', {
    'patient': str(p_id),
    'doctor': str(doc_a.id),
    'visit': str(visit_id),
    'items': [
        {'medicine_name': 'Amoxicillin 500mg', 'dosage': '1-0-1', 'duration': '5 days', 'timing': 'After Food'},
        {'medicine_name': 'Ketorolac 10mg', 'dosage': '1-0-1', 'duration': '3 days', 'timing': 'SOS'}
    ]
}, format='json')
record_workflow(16, "Prescription Creation & Dispensation Items", res16.status_code in [200, 201], "Prescription recorded")

# 17. Billing Invoice Conversion from Estimate
selected_estimate_items = [{'estimate_item_id': str(item['id']), 'quantity': 1} for item in res14.data.get('items', [])]
res17 = client.post(f'/api/estimates/{estimate_id}/convert-to-bill/', {'items': selected_estimate_items}, format='json')
billing_id = res17.data.get('bill_id') or res17.data.get('billing_id') or res17.data.get('id')
created_data['billing_id'] = billing_id
bill_obj = Billing.objects.filter(id=billing_id).first()
total_amt = bill_obj.total_amount if bill_obj else 0
record_workflow(17, "Billing Invoice Generation", res17.status_code in [200, 201] and billing_id is not None, f"Bill ID: {billing_id}, Total: {total_amt}")

# 18. Partial Bill Payment Recording
res18 = client.post(f'/api/billing/{billing_id}/payments/', {
    'amount': 4000.00,
    'payment_method': 'UPI',
    'notes': 'Partial advance payment for RCT stage 1'
}, format='json')
bill_obj.refresh_from_db()
bal_after_partial = bill_obj.balance_amount
record_workflow(18, "Partial Payment Recording", res18.status_code in [200, 201] and bill_obj.paid_amount == Decimal('4000.00'), f"Paid: {bill_obj.paid_amount}, Remaining Balance: {bal_after_partial}")

# 19. Full Bill Settlement
res19 = client.post(f'/api/billing/{billing_id}/payments/', {
    'amount': float(bal_after_partial),
    'payment_method': 'Card',
    'notes': 'Final settlement on crown delivery'
}, format='json')
bill_obj.refresh_from_db()
record_workflow(19, "Full Bill Settlement", res19.status_code in [200, 201] and bill_obj.balance_amount == Decimal('0.00') and bill_obj.status == 'Paid', f"Balance: {bill_obj.balance_amount}, Status: {bill_obj.status}")

# 20. Multi-Tenant Cross-Company Isolation Verification
login_beta = client.post('/api/login/', {'username': 'wf_admin_beta', 'password': 'BetaPass@123'}, format='json')
beta_token = login_beta.data.get('access')
client.credentials(HTTP_AUTHORIZATION=f'Bearer {beta_token}', HTTP_X_BRANCH_ID=str(branch_b.id))

res20_p = client.get(f'/api/patient/{p_id}/profile/')
res20_b = client.get(f'/api/estimates/{estimate_id}/')
res20_plans = client.get(f'/api/patients/{p_id}/treatment-plans/')

tenant_blocked = (res20_p.status_code in [403, 404]) and (res20_b.status_code in [403, 404]) and (res20_plans.status_code in [403, 404])
record_workflow(20, "Cross-Company Tenant Isolation Verification", tenant_blocked, f"Alpha Patient profile from Beta: {res20_p.status_code}, Estimate: {res20_b.status_code}, Treatment plans: {res20_plans.status_code}")

print("\n" + "=" * 70)
passed_cnt = sum(1 for r in workflow_results if r['status'] == 'PASS')
failed_cnt = sum(1 for r in workflow_results if r['status'] == 'FAIL')
print(f"WORKFLOW TEST SUMMARY: {passed_cnt} PASSED, {failed_cnt} FAILED out of {len(workflow_results)}")
print("=" * 70)

with open('ashdent-back/scratch/workflow_test_results.json', 'w', encoding='utf-8') as f:
    json.dump({
        'summary': {'passed': passed_cnt, 'failed': failed_cnt, 'total': len(workflow_results)},
        'tests': workflow_results
    }, f, indent=2)
