import os, sys
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from patients.models import Patient, Appointment, Company

for p in Patient.objects.all():
    print(f"Patient id={p.id}, name={p.name}, patient_id={getattr(p, 'patient_id', '')}, company={p.company_id}")

print("\nAppointments:")
for a in Appointment.objects.all()[:5]:
    print(f"Appt id={a.id}, patient={a.patient_id}, doctor={a.doctor_id}, date={a.appointment_date}")

