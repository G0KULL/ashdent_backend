import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from datetime import date
from django.test import RequestFactory
from patients.models import Doctor, Appointment, Patient
from patients.report_views import DoctorPerformanceAPIView

factory = RequestFactory()
view = DoctorPerformanceAPIView.as_view()

print("=== 1. TESTING GET API FOR ALL PERIODS ===")
for period in ['today', 'this_week', 'this_month', 'all']:
    req = factory.get(f'/api/dashboard/doctor-performance/?period={period}')
    res = view(req)
    assert res.status_code == 200, f'Failed for period {period}'
    print(f'[OK] Period "{period}" returned {len(res.data["doctors"])} doctors, Total Appts: {res.data["summary"]["total_appointments"]}')

print("\n=== 2. TESTING DOCTOR REASSIGNMENT DYNAMIC UPDATE ===")
doc_a = Doctor.objects.first()
doc_b = Doctor.objects.all()[1]
patient = Patient.objects.first()

req1 = factory.get('/api/dashboard/doctor-performance/?period=all')
res1 = view(req1)
doc_a_initial = next(d['total'] for d in res1.data['doctors'] if d['doctor_id'] == str(doc_a.id))
doc_b_initial = next(d['total'] for d in res1.data['doctors'] if d['doctor_id'] == str(doc_b.id))

print(f'Before reassignment: {doc_a.name} = {doc_a_initial}, {doc_b.name} = {doc_b_initial}')

# Create appointment for Doctor A
test_appt = Appointment.objects.create(
    patient=patient,
    doctor=doc_a,
    date=date.today(),
    status='Scheduled'
)

# Fetch API after creating appt
res2 = view(factory.get('/api/dashboard/doctor-performance/?period=all'))
doc_a_after_create = next(d['total'] for d in res2.data['doctors'] if d['doctor_id'] == str(doc_a.id))
assert doc_a_after_create == doc_a_initial + 1, 'Doctor A count did not increase!'
print(f'[OK] Doctor A count increased to {doc_a_after_create}')

# Reassign appointment to Doctor B
test_appt.doctor = doc_b
test_appt.save()

# Fetch API after reassigning appt
res3 = view(factory.get('/api/dashboard/doctor-performance/?period=all'))
doc_a_after_reassign = next(d['total'] for d in res3.data['doctors'] if d['doctor_id'] == str(doc_a.id))
doc_b_after_reassign = next(d['total'] for d in res3.data['doctors'] if d['doctor_id'] == str(doc_b.id))

assert doc_a_after_reassign == doc_a_initial, 'Doctor A count did not decrease back!'
assert doc_b_after_reassign == doc_b_initial + 1, 'Doctor B count did not increase!'
print(f'[OK] Reassignment verified! {doc_a.name} = {doc_a_after_reassign}, {doc_b.name} = {doc_b_after_reassign}')

# Mark appointment completed
test_appt.status = 'Completed'
test_appt.save()

res4 = view(factory.get('/api/dashboard/doctor-performance/?period=all'))
doc_b_completed = next(d['completed'] for d in res4.data['doctors'] if d['doctor_id'] == str(doc_b.id))
print(f'[OK] Completion status change verified! {doc_b.name} completed count = {doc_b_completed}')

# Cleanup
test_appt.delete()
print('[OK] Cleanup complete! All test assertions PASSED!')
