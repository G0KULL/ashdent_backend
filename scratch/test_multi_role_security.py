import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
os.environ['DJANGO_DB_NAME'] = 'dental_clinic_db_migrated'
import django; django.setup()

from rest_framework.test import APIClient
from django.contrib.auth.models import User
from patients.models import Patient, Company, Branch, Staff, Doctor, Billing, Appointment, Visit, Prescription, TreatmentPlan

client = APIClient()

comp_alpha = Company.objects.filter(code='COMP_ALPHA').first()
comp_beta = Company.objects.filter(code='COMP_BETA').first()
branch_alpha = Branch.objects.filter(company=comp_alpha).first()
branch_beta = Branch.objects.filter(company=comp_beta).first()
alpha_pt = Patient.objects.filter(company=comp_alpha).first()
alpha_bill = Billing.objects.filter(company=comp_alpha).first()
alpha_appt = Appointment.objects.filter(company=comp_alpha).first()
alpha_rx = Prescription.objects.filter(company=comp_alpha).first()

# Create or verify users
def get_or_create_user(username, password, role, company, branch, is_super=False):
    u = User.objects.filter(username=username).first()
    if not u:
        if is_super:
            u = User.objects.create_superuser(username, f'{username}@example.com', password)
        else:
            u = User.objects.create_user(username, f'{username}@example.com', password)
    else:
        u.set_password(password)
        u.is_superuser = is_super
        u.save()

    if not is_super:
        staff = Staff.objects.filter(user_id=u.pk).first()
        if not staff:
            staff = Staff.objects.create(
                user=u,
                name=username,
                role=role,
                company=company,
                primary_branch=branch,
                is_active=True
            )
        else:
            staff.role = role
            staff.company = company
            staff.primary_branch = branch
            staff.save()
            
        if role == 'Doctor':
            if not getattr(staff, 'doctor_profile', None):
                doc = Doctor.objects.create(
                    name=f"Dr. {username}",
                    specialization="General",
                    company=company,
                    primary_branch=branch
                )
                staff.doctor_profile = doc
                staff.save()
    return u

u_super = get_or_create_user('test_super_admin', 'SuperPass@123', 'Super Admin', None, None, is_super=True)
u_alpha_admin = get_or_create_user('test_alpha_admin', 'AdminPass@123', 'Admin', comp_alpha, branch_alpha)
u_beta_admin = get_or_create_user('test_beta_admin', 'AdminPass@123', 'Admin', comp_beta, branch_beta)
u_alpha_doc = get_or_create_user('test_alpha_doc', 'DocPass@123', 'Doctor', comp_alpha, branch_alpha)
u_beta_doc = get_or_create_user('test_beta_doc', 'DocPass@123', 'Doctor', comp_beta, branch_beta)
u_alpha_rec = get_or_create_user('test_alpha_rec', 'RecPass@123', 'Receptionist', comp_alpha, branch_alpha)
u_beta_rec = get_or_create_user('test_beta_rec', 'RecPass@123', 'Receptionist', comp_beta, branch_beta)

roles = [
    ('Super Admin', 'test_super_admin', 'SuperPass@123', None, True),
    ('Company Alpha Admin', 'test_alpha_admin', 'AdminPass@123', branch_alpha, False),
    ('Company Beta Admin', 'test_beta_admin', 'AdminPass@123', branch_beta, False),
    ('Alpha Doctor', 'test_alpha_doc', 'DocPass@123', branch_alpha, False),
    ('Beta Doctor', 'test_beta_doc', 'DocPass@123', branch_beta, False),
    ('Alpha Receptionist', 'test_alpha_rec', 'RecPass@123', branch_alpha, False),
    ('Beta Receptionist', 'test_beta_rec', 'RecPass@123', branch_beta, False),
]

role_test_matrix = []

print("=" * 80)
print("MULTI-ROLE CROSS-TENANT SECURITY MATRIX VERIFICATION")
print("=" * 80)

for role_name, username, password, branch, is_super in roles:
    login_res = client.post('/api/login/', {'username': username, 'password': password}, format='json')
    token = login_res.data.get('access')
    headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
    if branch:
        headers['HTTP_X_BRANCH_ID'] = str(branch.id)
    client.credentials(**headers)
    
    # 1. Access Alpha Patient EMR
    res_emr = client.get(f'/api/patients/{alpha_pt.id}/emr/')
    # 2. Access Alpha Patient Tooth Conditions
    res_tc = client.get(f'/api/patients/{alpha_pt.id}/tooth-conditions/')
    # 3. Access Alpha Bills list
    res_bills = client.get('/api/bill/list/')
    # 4. Access Alpha Bill payment
    res_bp = client.get(f'/api/billing/{alpha_bill.id}/payments/') if alpha_bill else None
    
    # Expected:
    # Super Admin: 200 OK across all
    # Alpha users: 200 OK on Alpha patient/bill
    # Beta users: 403 Forbidden on Alpha patient/bill
    is_beta = 'Beta' in role_name
    emr_expected = 200 if (is_super or not is_beta) else 403
    bills_leaked = any(str(b.get('id')) == str(alpha_bill.id) for b in res_bills.data) if (alpha_bill and isinstance(res_bills.data, list)) else False
    if role_name == 'Alpha Doctor':
        bills_expected_leak = False
    else:
        bills_expected_leak = True if (is_super or not is_beta) else False
    
    emr_pass = (res_emr.status_code == emr_expected)
    tc_pass = (res_tc.status_code == emr_expected)
    bills_pass = (bills_leaked == bills_expected_leak)
    bp_pass = (res_bp.status_code == emr_expected) if res_bp else True
    
    overall = emr_pass and tc_pass and bills_pass and bp_pass
    
    entry = {
        'role': role_name,
        'username': username,
        'emr_status': res_emr.status_code,
        'tc_status': res_tc.status_code,
        'bill_payment_status': res_bp.status_code if res_bp else 'N/A',
        'alpha_bill_in_list': bills_leaked,
        'overall_pass': overall
    }
    role_test_matrix.append(entry)
    print(f"[{'PASS' if overall else 'FAIL'}] {role_name:22} | EMR: {res_emr.status_code} (Exp {emr_expected}) | TC: {res_tc.status_code} | BP: {entry['bill_payment_status']} | AlphaBillLeaked: {bills_leaked}")

with open('ashdent-back/scratch/role_security_matrix.json', 'w') as f:
    json.dump(role_test_matrix, f, indent=2)

print("=" * 80)
print(f"MULTI-ROLE AUDIT: {sum(1 for r in role_test_matrix if r['overall_pass'])}/{len(role_test_matrix)} ROLES PASSED")
print("=" * 80)
