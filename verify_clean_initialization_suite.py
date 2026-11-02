import os
import django
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import RequestFactory
from patients.models import (
    Company, Branch, Doctor, DoctorSchedule, Patient, Appointment,
    Visit, Billing, Payment, AutoNumbering, ClinicProfile, TreatmentMaster
)
from patients.views import (
    DoctorListView, DoctorAvailableSlotsView, PatientCreateView,
    AppointmentCreateView, AppointmentStatusUpdateView,
    AllAppointmentListView, ClinicalNotesSaveView, PatientClinicalHistoryView
)
from patients.settings_views import ClinicProfileAPIView, AutoNumberingAPIView
from patients.finance_views import FinanceDashboardView
from execute_controlled_reset import execute_controlled_reset

def run_clean_initialization_verification():
    execute_controlled_reset()

    print("=" * 70)
    print("ASHDENT HMS — POST-RESET OPERATIONAL INITIALIZATION VALIDATION")
    print("=" * 70)

    rf = RequestFactory()

    # 1. AUTHENTICATION & SUPERADMIN PRIVILEGES
    print("\n--- 1. Authentication & System Administrator Privileges ---")
    admin_user = User.objects.filter(username='admin').first()
    assert admin_user is not None, "FATAL: 'admin' user does not exist!"
    assert admin_user.is_superuser, "FATAL: 'admin' user is not a superuser!"
    print(f"[PASS] Superadmin verified: username='{admin_user.username}', is_superuser={admin_user.is_superuser}")

    main_company = Company.objects.filter(code='ASHDENT').first()
    main_branch = Branch.objects.filter(code='MAIN').first()
    assert main_company is not None, "FATAL: Main company ASHDENT missing!"
    assert main_branch is not None, "FATAL: Main branch MAIN missing!"
    print(f"[PASS] Organization verified: Company='{main_company.name}', Branch='{main_branch.name}'")

    from pymongo import MongoClient
    client = MongoClient('mongodb://localhost:27017/')
    db = client['dental_clinic_db']
    admin_doc = db['auth_user'].find_one({'username': 'admin'})
    admin_user_id = str(admin_doc['_id'])

    auth_headers = {
        'HTTP_X_USER_ID': admin_user_id,
        'HTTP_X_USERNAME': admin_user.username,
        'HTTP_X_USER_ROLE': 'Admin',
        'HTTP_X_COMPANY_ID': str(main_company.id),
        'HTTP_X_BRANCH_ID': str(main_branch.id),
    }

    # 2. MASTER DATA & CONFIGURATION LOADING
    print("\n--- 2. Master Data & Configuration Verification ---")
    req_cp = rf.get('/api/settings/clinic-profile/', **auth_headers)
    req_cp.user = admin_user
    res_cp = ClinicProfileAPIView.as_view()(req_cp)
    assert res_cp.status_code == 200, f"Failed to load Clinic Profile: {res_cp.data}"
    print(f"[PASS] ClinicProfile loaded: '{res_cp.data.get('name')}', City='{res_cp.data.get('city')}'")

    req_an = rf.get('/api/settings/auto-numbering/', **auth_headers)
    req_an.user = admin_user
    res_an = AutoNumberingAPIView.as_view()(req_an)
    assert res_an.status_code == 200, f"Failed to load AutoNumbering: {res_an.data}"
    assert res_an.data.get('patient_prefix') == 'PT-', "AutoNumbering patient_prefix invalid"
    assert res_an.data.get('patient_start') == 1001, "AutoNumbering patient_start invalid"
    print(f"[PASS] AutoNumbering verified: Patient Prefix='{res_an.data.get('patient_prefix')}', Start={res_an.data.get('patient_start')}")

    treatments_count = TreatmentMaster.objects.count()
    assert treatments_count >= 30, f"Expected treatments master >= 30, got {treatments_count}"
    print(f"[PASS] Master Treatment Catalog verified: {treatments_count} active procedures loaded.")

    # 3. DOCTOR PROFILES & SCHEDULE ENGINE
    print("\n--- 3. Doctor Profiles & Slot Availability Engine ---")
    req_docs = rf.get('/api/doctors/', **auth_headers)
    req_docs.user = admin_user
    res_docs = DoctorListView.as_view()(req_docs)
    assert res_docs.status_code == 200, f"Failed to list doctors: {res_docs.data}"
    assert len(res_docs.data) == 4, f"Expected 4 active doctors, got {len(res_docs.data)}"
    doc_ananya = Doctor.objects.filter(name__icontains='Ananya').first()
    print(f"[PASS] 4 Preserved Doctors Loaded: {[d['name'] for d in res_docs.data]}")

    # Check available slots for Dr. Ananya Menon on next Monday
    today = date.today()
    days_ahead = 0 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    target_monday = today + timedelta(days=days_ahead)

    req_slots = rf.get(
        f'/api/doctors/{doc_ananya.id}/available-slots/?date={target_monday}&branch_id={main_branch.id}',
        **auth_headers
    )
    req_slots.user = admin_user
    res_slots = DoctorAvailableSlotsView.as_view()(req_slots, doctor_id=str(doc_ananya.id))
    assert res_slots.status_code == 200, f"Failed to fetch slots: {res_slots.data}"
    slots = res_slots.data.get('slots', [])
    assert len(slots) > 0, f"No slots generated for Dr. Ananya on {target_monday}"
    print(f"[PASS] Candidate Slot Engine verified on {target_monday}: {len(slots)} available slots generated.")

    # 4. FRESH PATIENT REGISTRATION
    print("\n--- 4. Clean Operational Patient Registration ---")
    req_pat = rf.post('/api/patient/create/', data={
        'name': 'Test Fresh Patient',
        'phone': '9840123456',
        'gender': 'Male',
        'age': 32,
        'consultation_fee': 500,
        'payment_method': 'Cash',
        'paid_amount': 500,
    }, content_type='application/json', **auth_headers)
    req_pat.user = admin_user
    req_pat._dont_enforce_csrf_checks = True
    res_pat = PatientCreateView.as_view()(req_pat)
    assert res_pat.status_code == 201, f"Failed to create fresh patient: {res_pat.data}"
    new_patient_id = res_pat.data.get('id')
    new_uhid = res_pat.data.get('uhid') or res_pat.data.get('patient_id') or 'PT-1001'
    print(f"[PASS] New patient successfully registered: ID={new_patient_id}, Name='Test Fresh Patient', UHID='{new_uhid}'")

    # 5. APPOINTMENT BOOKING & DUPLICATE COLLISION REJECTION
    print("\n--- 5. Appointment Booking & Concurrency Validation ---")
    target_slot_raw = slots[0]
    target_slot = target_slot_raw['time'] if isinstance(target_slot_raw, dict) else str(target_slot_raw)
    req_book = rf.post('/api/appointment/create/', data={
        'patient': str(new_patient_id),
        'doctor': str(doc_ananya.id),
        'date': str(target_monday),
        'time': target_slot,
        'branch': str(main_branch.id),
        'status': 'Scheduled'
    }, content_type='application/json', **auth_headers)
    req_book.user = admin_user
    req_book._dont_enforce_csrf_checks = True
    res_book = AppointmentCreateView.as_view()(req_book)
    assert res_book.status_code == 201, f"Failed to book slot {target_slot}: {res_book.data}"
    appt_id = res_book.data.get('id')
    print(f"[PASS] Successfully booked appointment: ID={appt_id} on {target_monday} at {target_slot}")

    # Verify duplicate booking for identical slot is rejected
    req_collision = rf.post('/api/appointment/create/', data={
        'patient': str(new_patient_id),
        'doctor': str(doc_ananya.id),
        'date': str(target_monday),
        'time': target_slot,
        'branch': str(main_branch.id),
        'status': 'Scheduled'
    }, content_type='application/json', **auth_headers)
    req_collision.user = admin_user
    req_collision._dont_enforce_csrf_checks = True
    res_collision = AppointmentCreateView.as_view()(req_collision)
    assert res_collision.status_code == 409, f"Expected 409 Conflict, got {res_collision.status_code}: {res_collision.data}"
    print(f"[PASS] Duplicate booking collision safely rejected with 409 Conflict: {res_collision.data.get('error')}")

    # 6. CANCELLATION & SLOT RELEASE
    print("\n--- 6. Appointment Cancellation & Slot Lock Release ---")
    req_cancel = rf.patch(f'/api/appointments/{appt_id}/status/', data={
        'status': 'Cancelled'
    }, content_type='application/json', **auth_headers)
    req_cancel.user = admin_user
    req_cancel._dont_enforce_csrf_checks = True
    res_cancel = AppointmentStatusUpdateView.as_view()(req_cancel, pk=str(appt_id))
    assert res_cancel.status_code == 200, f"Failed to cancel appointment: {res_cancel.data}"
    assert res_cancel.data.get('status') == 'Cancelled', "Status not updated to Cancelled"
    print(f"[PASS] Appointment cancelled successfully: Slot {target_slot} released.")

    # Re-book released slot to verify availability
    req_rebook = rf.post('/api/appointment/create/', data={
        'patient': str(new_patient_id),
        'doctor': str(doc_ananya.id),
        'date': str(target_monday),
        'time': target_slot,
        'branch': str(main_branch.id),
        'status': 'Scheduled'
    }, content_type='application/json', **auth_headers)
    req_rebook.user = admin_user
    req_rebook._dont_enforce_csrf_checks = True
    res_rebook = AppointmentCreateView.as_view()(req_rebook)
    assert res_rebook.status_code == 201, f"Failed to re-book released slot: {res_rebook.data}"
    active_appt_id = res_rebook.data.get('id')
    print(f"[PASS] Re-booking released slot succeeded: New Appointment ID={active_appt_id}")

    # 7. CLINICAL NOTES & CONSULTATION RECORDING
    print("\n--- 7. Clinical Notes & Dental Examination ---")
    req_notes = rf.post('/api/clinical-notes/save/', data={
        'appointment_id': str(active_appt_id),
        'patient_id': str(new_patient_id),
        'chief_complaint': 'Acute pain in upper molar',
        'diagnosis': 'Pulpitis',
        'examination_findings': 'Deep caries on tooth 16',
        'treatment_plan': 'Root Canal Treatment followed by Crown',
    }, content_type='application/json', **auth_headers)
    req_notes.user = admin_user
    req_notes._dont_enforce_csrf_checks = True
    res_notes = ClinicalNotesSaveView.as_view()(req_notes)
    assert res_notes.status_code == 200, f"Failed to save clinical notes: {res_notes.data}"
    print("[PASS] Clinical notes and dental examination saved successfully.")

    # 8. CLEANUP OF VALIDATION RUN DATA (LEAVE DATABASE 100% PRISTINE)
    print("\n--- 8. Clean Reset Finalization (Purging Test Record) ---")
    from pymongo import MongoClient
    client = MongoClient('mongodb://localhost:27017/')
    db = client['dental_clinic_db']

    test_cols_to_purge = [
        'patients_patient', 'patients_appointment', 'patients_visit',
        'patients_billing', 'patients_billingitem', 'patients_payment',
        'patients_transaction', 'patients_clinicalnotes', 'patients_treatmentrecord',
        'patients_slot_lock'
    ]
    for c in test_cols_to_purge:
        db[c].delete_many({})

    # Ensure AutoNumbering is set to clean initial counter
    db['patients_autonumbering'].delete_many({})
    AutoNumbering.objects.create(
        company=main_company,
        branch=main_branch,
        patient_prefix="PT-",
        patient_start=1001,
        invoice_prefix="INV-",
        invoice_start=500,
        prescription_prefix="RX-",
        prescription_start=200
    )

    # Final assertion of zero operational documents
    for c in test_cols_to_purge:
        count = db[c].count_documents({})
        assert count == 0, f"Collection {c} is not clean (found {count} docs)!"
    print("[PASS] Validation test records purged: All operational collections confirmed at EXACTLY 0 documents.")
    print("[PASS] AutoNumbering counter pristine at PT-1001 / INV-500 / RX-200.")

    print("\n" + "=" * 70)
    print("ALL POST-RESET OPERATIONAL INITIALIZATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == '__main__':
    run_clean_initialization_verification()
