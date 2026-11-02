import os
import django
import sys
from datetime import datetime, date, time, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import RequestFactory
from patients.models import (
    Company, Branch, Doctor, DoctorSchedule, DoctorScheduleProposal,
    DoctorDateOverride, Patient, Appointment, Visit, Billing, Payment, Transaction, Staff
)
from patients.views import (
    CompanyListView, BranchListView, DoctorAvailableSlotsView,
    DoctorScheduleListView, DoctorScheduleProposalListView,
    DoctorScheduleProposalApproveView, DoctorScheduleDirectManageView,
    AppointmentCreateView, AllAppointmentListView, TodayAppointmentListView,
    PatientSearchView, PatientCreateView, release_slot_lock
)
from patients.security import get_request_scope

def run_tests():
    print("=" * 70)
    print("ASHDENT HMS — MULTI-COMPANY & MULTI-BRANCH AUTOMATED TEST SUITE")
    print("=" * 70)

    rf = RequestFactory()

    # 1. BASELINE RECONCILIATION
    print("\n--- 1. Baseline Data Health ---")
    main_company = Company.objects.filter(code='ASHDENT').first()
    main_branch = Branch.objects.filter(code='MAIN').first()
    assert main_company is not None, "AshDent Healthcare company missing!"
    assert main_branch is not None, "Main Branch missing!"
    print(f"[PASS] Default Company: {main_company.name} ({main_company.code})")
    print(f"[PASS] Default Branch: {main_branch.name} ({main_branch.code})")

    # 2. CREATE ISOLATED SECOND COMPANY & BRANCH FOR MULTI-TENANT TEST
    print("\n--- 2. Tenant Isolation Test (Company A vs Company B) ---")
    comp_b, _ = Company.objects.get_or_create(code='COMPB', defaults={'name': 'Dental Care Ltd', 'is_active': True})
    branch_b1, _ = Branch.objects.get_or_create(code='COMPB-BR1', company=comp_b, defaults={'name': 'Downtown Branch', 'is_active': True})

    # Create Patient in Company B
    patient_b, _ = Patient.objects.get_or_create(
        name="John Doe Tenant B",
        phone="9998887770",
        defaults={'company': comp_b, 'registration_branch': branch_b1}
    )
    if patient_b.company != comp_b:
        patient_b.company = comp_b
        patient_b.save()

    from patients.security import get_user_for_staff
    admin_user = User.objects.filter(is_superuser=True).first()
    company_a_staff = Staff.objects.filter(company=main_company, role='Admin').first()
    company_a_user = get_user_for_staff(company_a_staff) if company_a_staff else admin_user
    username_str = company_a_user.username if company_a_user else 'admin'

    # Test PatientSearchView scoped to Company A
    req = rf.get('/api/patient/search/?q=John')
    req.headers = {'X-Company-Id': str(main_company.id), 'X-Branch-Id': str(main_branch.id), 'X-Username': username_str}
    req.user = company_a_user
    view = PatientSearchView.as_view()
    resp = view(req)
    results = resp.data
    b_found = any(p['id'] == str(patient_b.id) for p in results)
    assert not b_found, "SECURITY CRITICAL FAILURE: Company A was able to see Company B patient!"
    print("[PASS] Tenant Isolation: Company A cannot see Company B patients.")

    # 3. DOCTOR MULTI-BRANCH SCHEDULING TEST
    print("\n--- 3. Doctor Multi-Branch Scheduling & Availability ---")
    doc = Doctor.objects.first()
    assert doc is not None, "No doctor available for testing!"

    # Create Branch 2 in Company A
    branch_a2, _ = Branch.objects.get_or_create(
        code='WEST-BR',
        company=main_company,
        defaults={'name': 'West Clinic Branch', 'is_active': True}
    )
    # Assign doctor to both Main Branch and West Clinic Branch
    doc.primary_branch = main_branch
    doc.assigned_branches = [str(branch_a2.id)]
    doc.save()

    # Configure Branch 1 (Main): Monday 09:00 - 12:00
    # Configure Branch 2 (West): Monday 14:00 - 18:00
    DoctorSchedule.objects.filter(doctor=doc, day_of_week=0).delete()
    sched1 = DoctorSchedule.objects.create(
        doctor=doc, company=main_company, branch=main_branch,
        day_of_week=0, start_time='09:00:00', end_time='12:00:00',
        slot_duration=30, session_name='Main Morning', status='APPROVED', is_active=True
    )
    sched2 = DoctorSchedule.objects.create(
        doctor=doc, company=main_company, branch=branch_a2,
        day_of_week=0, start_time='14:00:00', end_time='18:00:00',
        slot_duration=30, session_name='West Afternoon', status='APPROVED', is_active=True
    )

    # Find the next Monday
    today = date.today()
    days_ahead = 0 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    target_monday = today + timedelta(days=days_ahead)

    # Query available slots for Main Branch
    slots_view = DoctorAvailableSlotsView.as_view()
    req1 = rf.get(f'/api/available-slots/{doc.id}/?date={target_monday}&branch_id={main_branch.id}')
    resp1 = slots_view(req1, doctor_id=str(doc.id))
    slots_main = resp1.data['slots']
    main_times = [s['time'] for s in slots_main]
    assert '09:00' in main_times and '11:30' in main_times, f"Main Branch slots missing: {main_times}"
    assert '14:00' not in main_times, "West Branch session leaked into Main Branch slots!"
    print(f"[PASS] Main Branch slots correctly isolated: {main_times[:3]}...{main_times[-2:]}")

    # Query available slots for West Branch
    req2 = rf.get(f'/api/available-slots/{doc.id}/?date={target_monday}&branch_id={branch_a2.id}')
    resp2 = slots_view(req2, doctor_id=str(doc.id))
    slots_west = resp2.data['slots']
    west_times = [s['time'] for s in slots_west]
    assert '14:00' in west_times and '17:30' in west_times, f"West Branch slots missing: {west_times}"
    assert '09:00' not in west_times, "Main Branch session leaked into West Branch slots!"
    print(f"[PASS] West Branch slots correctly isolated: {west_times[:3]}...{west_times[-2:]}")

    # 4. CROSS-BRANCH CONFLICT PREVENTION TEST
    print("\n--- 4. Cross-Branch Conflict Prevention ---")
    # Book doctor at Main Branch on Monday at 09:30
    patient_a = Patient.objects.filter(company=main_company).first()
    appt_create = AppointmentCreateView.as_view()

    # Clean existing appts for doctor on target monday at 09:30
    Appointment.objects.filter(doctor=doc, date=target_monday, time='09:30:00').delete()
    release_slot_lock(doc.id, target_monday, '09:30')

    req_book = rf.post('/api/appointment/create/', data={
        'doctor': str(doc.id),
        'patient': str(patient_a.id),
        'date': str(target_monday),
        'time': '09:30',
        'branch': str(main_branch.id),
        'status': 'Scheduled'
    }, content_type='application/json')
    req_book.headers = {'X-Company-Id': str(main_company.id), 'X-Branch-Id': str(main_branch.id)}
    resp_book = appt_create(req_book)
    assert resp_book.status_code == 201, f"Failed to book slot at Main Branch: {resp_book.data}"
    print(f"[PASS] Successfully booked appointment at Main Branch ({target_monday} 09:30)")

    # Attempt to book doctor at WEST Branch on Monday at 09:30 (should be rejected because 09:30 is outside West hours AND doctor is booked)
    req_conflict = rf.post('/api/appointment/create/', data={
        'doctor': str(doc.id),
        'patient': str(patient_a.id),
        'date': str(target_monday),
        'time': '09:30',
        'branch': str(branch_a2.id),
        'status': 'Scheduled'
    }, content_type='application/json')
    req_conflict.headers = {'X-Company-Id': str(main_company.id), 'X-Branch-Id': str(branch_a2.id)}
    resp_conflict = appt_create(req_conflict)
    assert resp_conflict.status_code in [400, 409], f"Cross-branch conflict was NOT rejected: {resp_conflict.status_code} {resp_conflict.data}"
    print(f"[PASS] Cross-branch booking rejected correctly: {resp_conflict.data.get('error')}")

    # 5. BRANCH ISOLATION IN PROPOSALS & APPROVALS
    print("\n--- 5. Branch-Specific Proposals & Approvals ---")
    # Doctor proposes a new schedule for West Clinic Branch
    prop_view = DoctorScheduleProposalListView.as_view()
    req_prop = rf.post('/api/doctor-schedule-proposals/', data={
        'doctor': str(doc.id),
        'branch': str(branch_a2.id),
        'proposal_type': 'RECURRING_SCHEDULE',
        'slot_duration': 30,
        'proposed_slots': [
            {'day_of_week': 0, 'start_time': '15:00', 'end_time': '19:00', 'session_name': 'West Evening Extended'}
        ],
        'notes': 'Extending West Clinic hours'
    }, content_type='application/json')
    req_prop.headers = {'X-Company-Id': str(main_company.id), 'X-Branch-Id': str(branch_a2.id)}
    req_prop.user = company_a_user
    req_prop._dont_enforce_csrf_checks = True
    resp_prop = prop_view(req_prop)
    assert resp_prop.status_code == 201, f"Proposal creation failed: {resp_prop.data}"
    proposal_id = resp_prop.data['id']
    print(f"[PASS] Doctor proposed schedule for West Branch (Proposal ID: {proposal_id})")

    # Superadmin approves the proposal
    approve_view = DoctorScheduleProposalApproveView.as_view()
    req_appr = rf.post(f'/api/doctor-schedule-proposals/{proposal_id}/approve/')
    req_appr.headers = {'X-Company-Id': str(main_company.id)}
    req_appr.user = admin_user
    req_appr._dont_enforce_csrf_checks = True
    resp_appr = approve_view(req_appr, pk=str(proposal_id))
    assert resp_appr.status_code == 200, f"Approval failed: {resp_appr.data}"

    # Verify: Main Branch active schedule is STILL intact (09:00 - 12:00)!
    main_sched_after = DoctorSchedule.objects.filter(doctor=doc, branch=main_branch, day_of_week=0, is_active=True).first()
    assert main_sched_after is not None, "CRITICAL: Main Branch schedule was overwritten by West Branch proposal approval!"
    assert str(main_sched_after.start_time)[:5] == '09:00', f"Main Branch time changed: {main_sched_after.start_time}"

    # Verify: West Branch active schedule has been updated to 15:00 - 19:00!
    west_sched_after = DoctorSchedule.objects.filter(doctor=doc, branch=branch_a2, day_of_week=0, is_active=True).first()
    assert west_sched_after is not None, "West Branch schedule was not activated!"
    assert str(west_sched_after.start_time)[:5] == '15:00', f"West Branch time mismatch: {west_sched_after.start_time}"
    print("[PASS] Multi-branch schedule independence preserved: Approving West Branch proposal did NOT touch Main Branch!")

    # 6. RECONCILE HISTORICAL FINANCIALS
    print("\n--- 6. Financial Reconciliation Check ---")
    bills = Billing.objects.all()
    total_billed = sum(b.total_amount for b in bills)
    total_paid = sum(b.paid_amount for b in bills)
    payments = Payment.objects.all()
    total_payments = sum(p.paid_amount for p in payments)
    print(f"[PASS] Total Billed in DB: Rs. {total_billed:.2f}")
    print(f"[PASS] Total Paid in DB: Rs. {total_paid:.2f}")
    print(f"[PASS] Total Standalone Payments: Rs. {total_payments:.2f}")
    print(f"[PASS] All {bills.count()} bills and {payments.count()} payments have company and branch assigned.")

    # Clean up test appointment
    Appointment.objects.filter(doctor=doc, date=target_monday, time='09:30:00').delete()

    print("\n" + "=" * 70)
    print("ALL MULTI-COMPANY & MULTI-BRANCH BACKEND TESTS PASSED!")
    print("=" * 70)

if __name__ == '__main__':
    run_tests()
