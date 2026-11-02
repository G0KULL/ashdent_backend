import os
import django
from datetime import date, time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import Doctor, Patient, Appointment

# Clear existing objects if needed
Doctor.objects.all().delete()
Patient.objects.all().delete()
Appointment.objects.all().delete()

if not Doctor.objects.exists():
    d1 = Doctor.objects.create(name='Dr. Navas Kp', color='#3498db')
    d2 = Doctor.objects.create(name='Dr. Smith', color='#e74c3c')
else:
    d1 = Doctor.objects.first()
    d2 = Doctor.objects.last()

if not Patient.objects.exists():
    p1 = Patient.objects.create(registration_id='REG-001', rec_no='REC-001', first_name='Arjun', last_name='Menon', mobile='9876543210', dob=date(1992, 4, 15), gender='Male')
    p2 = Patient.objects.create(registration_id='REG-002', rec_no='REC-002', first_name='Priya', last_name='Menon', mobile='9123456789', dob=date(1988, 9, 22), gender='Female')
    p3 = Patient.objects.create(registration_id='REG-003', rec_no='REC-003', first_name='Rahul', last_name='Krishna', mobile='9988776655', dob=date(1995, 12, 1), gender='Male')
else:
    p1 = Patient.objects.all()[0]
    p2 = Patient.objects.all()[1]
    p3 = Patient.objects.all()[2]

if not Appointment.objects.exists():
    t_today = date.today()
    
    # Scheduled
    Appointment.objects.create(patient=p1, doctor_obj=d1, date=t_today, time=time(9, 30), status='Scheduled', visit_type='New')
    # Waiting
    Appointment.objects.create(patient=p2, doctor_obj=d1, date=t_today, time=time(10, 15), status='Waiting', visit_type='Revisit')
    # Engaged
    Appointment.objects.create(patient=p3, doctor_obj=d2, date=t_today, time=time(11, 0), status='Engaged', visit_type='New')
    # Completed
    Appointment.objects.create(patient=p1, doctor_obj=d2, date=t_today, time=time(8, 0), status='Completed', visit_type='Revisit')

print("Mock data populated!")
