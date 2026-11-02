import os
import django
import sys
from datetime import datetime, date, time, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import RequestFactory
from patients.models import Company, Branch, Doctor, DoctorSchedule, Patient, Appointment
from patients.views import AppointmentCreateView

def run_concurrency_test():
    print("=" * 70)
    print("ASHDENT HMS — REAL CONCURRENT SLOT BOOKING RACE CONDITION TEST")
    print("=" * 70)

    main_company = Company.objects.filter(code='ASHDENT').first()
    main_branch = Branch.objects.filter(code='MAIN').first()
    doctor = Doctor.objects.first()
    patient = Patient.objects.filter(company=main_company).first()

    # Find next Monday
    today = date.today()
    days_ahead = 0 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    target_date = today + timedelta(days=days_ahead)
    target_time = "10:30"

    # Ensure clean state for this slot
    Appointment.objects.filter(doctor=doctor, date=target_date, time=f"{target_time}:00").delete()
    from patients.views import release_slot_lock
    release_slot_lock(doctor.id, target_date, target_time)

    print(f"Target: Dr. {doctor.name} at {main_branch.name} on {target_date} at {target_time}")
    print("Launching 10 SIMULTANEOUS threads attempting to book the exact same slot...")

    num_threads = 10
    results = []

    def attempt_booking(thread_id):
        rf = RequestFactory()
        appt_view = AppointmentCreateView.as_view()
        req = rf.post('/api/appointment/create/', data={
            'doctor': str(doctor.id),
            'patient': str(patient.id),
            'date': str(target_date),
            'time': target_time,
            'branch': str(main_branch.id),
            'status': 'Scheduled'
        }, content_type='application/json')
        req.headers = {'X-Company-Id': str(main_company.id), 'X-Branch-Id': str(main_branch.id)}
        req._dont_enforce_csrf_checks = True
        resp = appt_view(req)
        return thread_id, resp.status_code, resp.data

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_booking, i) for i in range(num_threads)]
        for f in as_completed(futures):
            results.append(f.result())

    successes = [r for r in results if r[1] == 201]
    conflicts = [r for r in results if r[1] in [400, 409]]

    print("\n--- Concurrency Execution Results ---")
    print(f"Total concurrent requests: {num_threads}")
    print(f"Successful bookings: {len(successes)}")
    print(f"Rejected conflict requests: {len(conflicts)}")

    for t_id, status_code, data in results:
        status_label = "SUCCESS (201)" if status_code == 201 else f"REJECTED ({status_code})"
        print(f"  Thread #{t_id}: {status_label}")

    # Verify database state
    db_count = Appointment.objects.filter(
        doctor=doctor,
        date=target_date,
        time=f"{target_time}:00"
    ).exclude(status__in=['Cancelled', 'Rescheduled']).count()

    print(f"\nFinal appointments in database for slot: {db_count}")
    assert db_count == 1, f"RACE CONDITION DETECTED! Expected exactly 1 booking in database, but found {db_count}!"
    assert len(successes) == 1, f"Expected exactly 1 successful response, but got {len(successes)}!"

    print("[PASS] Concurrency control verified: Exactly ONE booking succeeded, all concurrent collisions safely rejected!")

    # Cleanup
    Appointment.objects.filter(doctor=doctor, date=target_date, time=f"{target_time}:00").delete()
    print("=" * 70)

if __name__ == '__main__':
    run_concurrency_test()
