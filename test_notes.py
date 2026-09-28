import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from patients.models import Patient, ClinicalNotes

p = Patient.objects.filter(name__icontains='ashfaq').first()
print('Patient:', p)
if p:
    notes = ClinicalNotes.objects.filter(appointment__patient=p)
    print('Notes count:', notes.count())
    for n in notes:
        print(n.id, n.appointment.date, n.appointment.id, n.chief_complaint)
