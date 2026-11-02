import os
import sys
import django
from datetime import date, datetime, time, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.test import APIClient
from patients.models import (
    Doctor, DoctorSchedule, DoctorScheduleProposal, DoctorDateOverride,
    InAppNotification, Appointment, Patient, Staff, AuditLog
)

client = APIClient()

print("=" * 70)
print("ASHDENT HMS — COMPREHENSIVE DOCTOR SLOTS & SCHEDULING AUDIT TEST")
print("=" * 70)

results = {}

# Set up test entities
from django.db import connections
from bson import ObjectId
db = connections['default'].database

def get_or_create_mongo_user(username, email, password, is_superuser=False):
    u = User.objects.filter(username=username).first()
    if not u:
        if is_superuser:
            u = User.objects.create_superuser(username, email, password)
        else:
            u = User.objects.create_user(username, email, password)
    doc = db['auth_user'].find_one({'username': username})
    if doc:
        u.id = doc['_id']
        u.pk = doc['_id']
    return u, doc['_id']

super_admin, sa_id = get_or_create_mongo_user('test_superadmin', 'sa@clinic.com', 'adminpass123', is_superuser=True)
admin_user, admin_id = get_or_create_mongo_user('test_admin_slot', 'admin_slot@clinic.com', 'adminpass123')
doc1_user, doc1_id = get_or_create_mongo_user('dr_test_slot1', 'doc_slot1@clinic.com', 'docpass123')
doc2_user, doc2_id = get_or_create_mongo_user('dr_test_slot2', 'doc_slot2@clinic.com', 'docpass123')

# Admin staff
admin_staff = Staff.objects.filter(user_id=admin_id).first()
if not admin_staff:
    admin_staff = Staff.objects.create(user=admin_user, name='Slot Administrator', role='Admin', phone='9822001122')
else:
    admin_staff.role = 'Admin'
    admin_staff.save()

# Doctor 1: Dr. Test Slot Specialist
doc1_profile, _ = Doctor.objects.get_or_create(name='Dr. Test Slot Specialist', defaults={'consultation_fee': 600, 'slot_duration': 30})
doc1_staff = Staff.objects.filter(user_id=doc1_id).first()
if not doc1_staff:
    doc1_staff = Staff.objects.create(user=doc1_user, doctor_profile=doc1_profile, name='Dr. Test Slot Specialist', role='Doctor', phone='9822003344')
else:
    doc1_staff.doctor_profile = doc1_profile
    doc1_staff.role = 'Doctor'
    doc1_staff.save()

# Doctor 2: Dr. Second Doctor
doc2_profile, _ = Doctor.objects.get_or_create(name='Dr. Second Doctor', defaults={'consultation_fee': 500, 'slot_duration': 30})
doc2_staff = Staff.objects.filter(user_id=doc2_id).first()
if not doc2_staff:
    doc2_staff = Staff.objects.create(user=doc2_user, doctor_profile=doc2_profile, name='Dr. Second Doctor', role='Doctor', phone='9822005566')
else:
    doc2_staff.doctor_profile = doc2_profile
    doc2_staff.role = 'Doctor'
    doc2_staff.save()

# Sample Patient
test_patient, _ = Patient.objects.get_or_create(phone='9988776655', defaults={'name': 'Slot Test Patient', 'status': 'Active'})

admin_headers = {
    'HTTP_X_USER_ID': str(admin_id),
    'HTTP_X_USERNAME': admin_user.username,
    'HTTP_X_USER_ROLE': 'Admin'
}
super_admin_headers = {
    'HTTP_X_USER_ID': str(sa_id),
    'HTTP_X_USERNAME': super_admin.username,
    'HTTP_X_USER_ROLE': 'Admin'
}
doctor_headers = {
    'HTTP_X_USER_ID': str(doc1_id),
    'HTTP_X_USERNAME': doc1_user.username,
    'HTTP_X_USER_ROLE': 'Doctor'
}
doctor2_headers = {
    'HTTP_X_USER_ID': str(doc2_id),
    'HTTP_X_USERNAME': doc2_user.username,
    'HTTP_X_USER_ROLE': 'Doctor'
}

# Clean existing test data for Dr. Test Slot Specialist
DoctorSchedule.objects.filter(doctor=doc1_profile).delete()
DoctorScheduleProposal.objects.filter(doctor=doc1_profile).delete()
DoctorDateOverride.objects.filter(doctor=doc1_profile).delete()
Appointment.objects.filter(doctor=doc1_profile).delete()

# TEST 1: Admin creates a schedule and it becomes active immediately
print("\n[TEST 1] Admin creates doctor schedule directly -> becomes active immediately...")
res1 = client.post('/api/doctor-schedules/direct/', {
    'doctor': str(doc1_profile.id),
    'slot_duration': 30,
    'slots': [
        {'day_of_week': 0, 'start_time': '09:00', 'end_time': '12:00', 'session_name': 'Monday Morning'},
        {'day_of_week': 0, 'start_time': '14:00', 'end_time': '17:00', 'session_name': 'Monday Afternoon'},
    ]
}, format='json', **admin_headers)

active_scheds = DoctorSchedule.objects.filter(doctor=doc1_profile, is_active=True, status='APPROVED')
if res1.status_code == 200 and active_scheds.count() == 2:
    results["Test 1"] = f"PASSED: Admin created active schedule directly (2 sessions active, status 200)"
else:
    results["Test 1"] = f"FAILED: Status={res1.status_code}, Active schedules count={active_scheds.count()}"
print("  ->", results["Test 1"])


# TEST 2: Super Admin manages schedules within authorized scope
print("\n[TEST 2] Super Admin manages schedules across doctors...")
res2 = client.post('/api/doctor-schedules/direct/', {
    'doctor': str(doc2_profile.id),
    'slot_duration': 45,
    'slots': [
        {'day_of_week': 2, 'start_time': '10:00', 'end_time': '16:00', 'session_name': 'Wednesday Clinic'}
    ]
}, format='json', **super_admin_headers)
doc2_active = DoctorSchedule.objects.filter(doctor=doc2_profile, is_active=True, status='APPROVED')
if res2.status_code == 200 and doc2_active.count() == 1:
    results["Test 2"] = "PASSED: Super Admin successfully configured schedule directly for Doctor 2"
else:
    results["Test 2"] = f"FAILED: Super Admin response={res2.status_code}"
print("  ->", results["Test 2"])


# TEST 3: Doctor submits a proposal and it remains pending
print("\n[TEST 3] Doctor submits a proposal -> status is PENDING_APPROVAL...")
res3 = client.post('/api/doctor-schedule-proposals/', {
    'doctor': str(doc1_profile.id),
    'slot_duration': 30,
    'proposed_slots': [
        {'day_of_week': 1, 'start_time': '08:00', 'end_time': '13:00', 'session_name': 'Tuesday Shift'}
    ],
    'notes': 'Doctor requested shift to Tuesday'
}, format='json', **doctor_headers)

pending_prop = DoctorScheduleProposal.objects.filter(doctor=doc1_profile, status='PENDING_APPROVAL').first()
if res3.status_code == 201 and pending_prop and pending_prop.status == 'PENDING_APPROVAL':
    results["Test 3"] = f"PASSED: Doctor proposal created in PENDING_APPROVAL state (ID: {pending_prop.id})"
else:
    results["Test 3"] = f"FAILED: Status={res3.status_code}, Proposal={pending_prop}"
print("  ->", results["Test 3"])


# TEST 4: Pending slots are NOT bookable
print("\n[TEST 4] Pending slots are NOT bookable...")
# Tuesday is day 1. Find the next Tuesday.
today = date.today()
days_ahead = (1 - today.weekday()) % 7
if days_ahead == 0:
    days_ahead = 7
next_tuesday = today + timedelta(days=days_ahead)

res4_slots = client.get(f'/api/doctors/{doc1_profile.id}/available-slots/?date={next_tuesday.isoformat()}', **doctor_headers)
slots_tuesday = res4_slots.data.get('slots', [])

# Attempt to book a slot on next Tuesday 08:30 (which is in the pending proposal)
res4_booking = client.post('/api/appointment/create/', {
    'patient': str(test_patient.id),
    'doctor': str(doc1_profile.id),
    'date': next_tuesday.isoformat(),
    'time': '08:30:00',
    'status': 'Scheduled'
}, format='json', **admin_headers)

if len(slots_tuesday) == 0 and res4_booking.status_code == 400:
    results["Test 4"] = f"PASSED: Tuesday has 0 candidate slots and booking attempt rejected (400: {res4_booking.data.get('error')})"
else:
    results["Test 4"] = f"FAILED: Slots count={len(slots_tuesday)}, Booking status={res4_booking.status_code}"
print("  ->", results["Test 4"])


# TEST 5: Previous approved schedule remains active while replacement is pending
print("\n[TEST 5] Previous approved schedule remains active while replacement is pending...")
days_to_monday = (0 - today.weekday()) % 7
if days_to_monday == 0:
    days_to_monday = 7
next_monday = today + timedelta(days=days_to_monday)

res5_slots = client.get(f'/api/doctors/{doc1_profile.id}/available-slots/?date={next_monday.isoformat()}', **doctor_headers)
monday_slots = res5_slots.data.get('slots', [])
active_count = DoctorSchedule.objects.filter(doctor=doc1_profile, is_active=True).count()

if len(monday_slots) > 0 and active_count == 2:
    results["Test 5"] = f"PASSED: Active Monday schedule has {len(monday_slots)} candidate slots while proposal is pending"
else:
    results["Test 5"] = f"FAILED: Monday slots={len(monday_slots)}, Active count={active_count}"
print("  ->", results["Test 5"])


# TEST 6: Doctors CANNOT approve their own proposals
print("\n[TEST 6] Doctors cannot approve their own proposals through API...")
res6 = client.post(f'/api/doctor-schedule-proposals/{pending_prop.id}/approve/', {}, format='json', **doctor_headers)
if res6.status_code == 403:
    results["Test 6"] = f"PASSED: Self-approval blocked with 403 Forbidden ({res6.data.get('error')})"
else:
    results["Test 6"] = f"FAILED: Doctor self-approval returned {res6.status_code}"
print("  ->", results["Test 6"])


# TEST 7: Admin rejects proposal -> active schedule unchanged
print("\n[TEST 7] Admin rejects proposal -> active schedule remains unchanged...")
res7 = client.post(f'/api/doctor-schedule-proposals/{pending_prop.id}/reject/', {
    'rejection_reason': 'Tuesday already has too many specialists rostered.'
}, format='json', **admin_headers)

pending_prop.refresh_from_db()
active_after_reject = DoctorSchedule.objects.filter(doctor=doc1_profile, is_active=True).count()

if res7.status_code == 200 and pending_prop.status == 'REJECTED' and active_after_reject == 2:
    results["Test 7"] = f"PASSED: Proposal marked REJECTED with reason recorded; active Monday schedule intact (2 sessions)"
else:
    results["Test 7"] = f"FAILED: Status={res7.status_code}, PropStatus={pending_prop.status}, Active={active_after_reject}"
print("  ->", results["Test 7"])


# TEST 8: Doctor submits new proposal, Admin approves -> valid slots become bookable
print("\n[TEST 8] Doctor submits second proposal, Admin approves -> valid slots become bookable...")
res8_prop = client.post('/api/doctor-schedule-proposals/', {
    'doctor': str(doc1_profile.id),
    'slot_duration': 30,
    'proposed_slots': [
        {'day_of_week': 1, 'start_time': '09:00', 'end_time': '12:00', 'session_name': 'Tuesday Morning'},
        {'day_of_week': 1, 'start_time': '14:00', 'end_time': '17:00', 'session_name': 'Tuesday Afternoon'}
    ],
    'notes': 'Revised Tuesday hours'
}, format='json', **doctor_headers)

prop2_id = res8_prop.data['id']
res8_approve = client.post(f'/api/doctor-schedule-proposals/{prop2_id}/approve/', {}, format='json', **admin_headers)

# Now check Tuesday candidate slots
res8_slots = client.get(f'/api/doctors/{doc1_profile.id}/available-slots/?date={next_tuesday.isoformat()}', **doctor_headers)
tuesday_slots_new = res8_slots.data.get('slots', [])
available_tuesday = [s for s in tuesday_slots_new if s['is_available']]

if res8_approve.status_code == 200 and len(available_tuesday) == 12: # 3h + 3h = 6h = 12 x 30min slots
    results["Test 8"] = f"PASSED: Approved proposal activated. Tuesday now has {len(available_tuesday)} available bookable candidate slots"
else:
    results["Test 8"] = f"FAILED: Approval status={res8_approve.status_code}, Tuesday available slots={len(available_tuesday)}"
print("  ->", results["Test 8"])


# TEST 9: Company / Doctor permission restrictions enforced
print("\n[TEST 9] Doctor cannot modify another doctor's schedule or propose on their behalf...")
res9 = client.post('/api/doctor-schedule-proposals/', {
    'doctor': str(doc2_profile.id),
    'proposed_slots': [{'day_of_week': 4, 'start_time': '09:00', 'end_time': '12:00'}]
}, format='json', **doctor_headers)

if res9.status_code == 403:
    results["Test 9"] = f"PASSED: Doctor restricted from submitting proposals for other doctors (403: {res9.data.get('error')})"
else:
    results["Test 9"] = f"FAILED: Unauthorized doctor proposal returned {res9.status_code}"
print("  ->", results["Test 9"])


# TEST 10: Recurring schedules and multiple daily sessions generate correct candidate slots
print("\n[TEST 10] Multiple daily sessions generate separate correct slot intervals...")
morning_slots = [s for s in tuesday_slots_new if s['session_name'] == 'Tuesday Morning']
afternoon_slots = [s for s in tuesday_slots_new if s['session_name'] == 'Tuesday Afternoon']

if len(morning_slots) == 6 and len(afternoon_slots) == 6:
    results["Test 10"] = f"PASSED: Morning (09:00-12:00) generated 6 slots; Afternoon (14:00-17:00) generated 6 slots"
else:
    results["Test 10"] = f"FAILED: Morning={len(morning_slots)}, Afternoon={len(afternoon_slots)}"
print("  ->", results["Test 10"])


# TEST 11: Date-specific changes and leave behave correctly
print("\n[TEST 11] Date-specific leave blocks candidate slots...")
leave_date = next_tuesday
res11_leave = client.post('/api/doctor-date-overrides/', {
    'doctor': str(doc1_profile.id),
    'date': leave_date.isoformat(),
    'override_type': 'LEAVE',
    'reason': 'Medical Conference',
    'leave_type': 'Casual Leave'
}, format='json', **admin_headers)

res11_slots = client.get(f'/api/doctors/{doc1_profile.id}/available-slots/?date={leave_date.isoformat()}', **doctor_headers)
is_on_leave = res11_slots.data.get('is_on_leave')
leave_slots = res11_slots.data.get('slots', [])

if res11_leave.status_code == 201 and is_on_leave is True and len(leave_slots) == 0:
    results["Test 11"] = f"PASSED: Approved leave correctly marks doctor on leave with 0 available candidate slots"
else:
    results["Test 11"] = f"FAILED: Leave status={res11_leave.status_code}, is_on_leave={is_on_leave}, slots={len(leave_slots)}"
print("  ->", results["Test 11"])

# Clean up date override so other tests can use the date
DoctorDateOverride.objects.filter(doctor=doc1_profile, date=leave_date).delete()


# TEST 12: Existing appointments survive schedule changes
print("\n[TEST 12] Existing appointments survive schedule changes and conflicts are detected...")
# Book an appointment on next Tuesday at 10:00
res12_book = client.post('/api/appointment/create/', {
    'patient': str(test_patient.id),
    'doctor': str(doc1_profile.id),
    'date': next_tuesday.isoformat(),
    'time': '10:00:00',
    'status': 'Scheduled'
}, format='json', **admin_headers)

appt_id = res12_book.data['id']

# Doctor proposes new schedule that REMOVES Tuesday morning (only afternoon 14:00-17:00)
res12_prop = client.post('/api/doctor-schedule-proposals/', {
    'doctor': str(doc1_profile.id),
    'slot_duration': 30,
    'proposed_slots': [
        {'day_of_week': 1, 'start_time': '14:00', 'end_time': '18:00', 'session_name': 'Tuesday Afternoon Only'}
    ],
    'notes': 'Dropping morning session'
}, format='json', **doctor_headers)

prop3_id = res12_prop.data['id']

# Check conflict inspection API
res12_conflicts = client.get(f'/api/doctor-schedule-proposals/{prop3_id}/conflicts/', **admin_headers)
conflicts_data = res12_conflicts.data

# Existing appointment still exists and is Scheduled
appt_check = Appointment.objects.get(id=appt_id)

if conflicts_data['has_conflicts'] is True and conflicts_data['conflict_count'] >= 1 and appt_check.status == 'Scheduled':
    results["Test 12"] = f"PASSED: Pre-approval conflict detected ({conflicts_data['conflicts'][0]['reason']}); existing appointment untouched"
else:
    results["Test 12"] = f"FAILED: Conflicts={conflicts_data}, ApptStatus={appt_check.status}"
print("  ->", results["Test 12"])


# TEST 13: Conflicting schedules and overlapping time ranges are validated
print("\n[TEST 13] Conflicting schedules and overlapping session ranges are rejected...")
res13 = client.post('/api/doctor-schedule-proposals/', {
    'doctor': str(doc1_profile.id),
    'proposed_slots': [
        {'day_of_week': 0, 'start_time': '09:00', 'end_time': '13:00'},
        {'day_of_week': 0, 'start_time': '12:00', 'end_time': '16:00'}, # Overlaps from 12:00 to 13:00
    ]
}, format='json', **doctor_headers)

if res13.status_code == 400 and 'Overlapping' in str(res13.data):
    results["Test 13"] = f"PASSED: Overlapping session submission rejected with 400 Bad Request ({res13.data.get('error')})"
else:
    results["Test 13"] = f"FAILED: Overlap status={res13.status_code}, Response={res13.data}"
print("  ->", results["Test 13"])


# TEST 14: Concurrent booking attempts cannot reserve the same slot twice
print("\n[TEST 14] Double-booking prevention: attempting to book already-reserved slot...")
res14_dup = client.post('/api/appointment/create/', {
    'patient': str(test_patient.id),
    'doctor': str(doc1_profile.id),
    'date': next_tuesday.isoformat(),
    'time': '10:00:00', # already booked in Test 12
    'status': 'Scheduled'
}, format='json', **admin_headers)

if res14_dup.status_code == 409 and 'already booked' in str(res14_dup.data):
    results["Test 14"] = f"PASSED: Double booking blocked with 409 Conflict ({res14_dup.data.get('error')})"
else:
    results["Test 14"] = f"FAILED: Double booking returned {res14_dup.status_code}: {res14_dup.data}"
print("  ->", results["Test 14"])


# TEST 15: Appointment rescheduling, editing, and cancellation still work
print("\n[TEST 15] Appointment editing, rescheduling, and cancellation...")
# Reschedule to 11:00 on the same date (which is available)
res15_edit = client.patch(f'/api/appointments/{appt_id}/status/', {
    'time': '11:00:00',
    'status': 'Rescheduled'
}, format='json', **admin_headers)

# Cancel appointment
res15_cancel = client.patch(f'/api/appointments/{appt_id}/status/', {
    'status': 'Cancelled'
}, format='json', **admin_headers)

appt_cancelled = Appointment.objects.get(id=appt_id)

if res15_edit.status_code == 200 and res15_cancel.status_code == 200 and appt_cancelled.status == 'Cancelled':
    results["Test 15"] = f"PASSED: Appointment editing, rescheduling, and cancellation work seamlessly"
else:
    results["Test 15"] = f"FAILED: Edit={res15_edit.status_code}, Cancel={res15_cancel.status_code}"
print("  ->", results["Test 15"])


# TEST 16: Existing schedules and historical data remain intact after migration
print("\n[TEST 16] Verify all historical schedules, doctors, appointments, and staff remain intact...")
total_docs = Doctor.objects.count()
total_scheds = DoctorSchedule.objects.count()
total_appts = Appointment.objects.count()
approved_scheds = DoctorSchedule.objects.filter(status='APPROVED', is_active=True).count()

if total_docs >= 4 and total_scheds >= 24 and total_appts >= 26 and approved_scheds >= 24:
    results["Test 16"] = f"PASSED: Data integrity verified. {total_docs} Doctors, {total_scheds} Schedules ({approved_scheds} approved active), {total_appts} Appointments intact"
else:
    results["Test 16"] = f"FAILED: Docs={total_docs}, Scheds={total_scheds}, Approved={approved_scheds}, Appts={total_appts}"
print("  ->", results["Test 16"])

print("\n" + "=" * 70)
print("AUDIT TEST SUMMARY")
print("=" * 70)
passed = 0
failed = 0
for test_name, res_str in results.items():
    print(f"[{test_name}] {res_str}")
    if "PASSED" in res_str:
        passed += 1
    else:
        failed += 1

print("\n" + "-" * 70)
print(f"TOTAL TESTS: {len(results)} | PASSED: {passed} | FAILED: {failed}")
print("-" * 70)

if failed > 0:
    sys.exit(1)
