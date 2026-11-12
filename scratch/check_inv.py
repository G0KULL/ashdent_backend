import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from patients.models import Patient, Doctor, InvestigationMaster, PatientInvestigation, InvestigationAttachment

print("Patients count:", Patient.objects.count())
print("Doctors count:", Doctor.objects.count())
print("InvestigationMaster count:", InvestigationMaster.objects.count())
print("PatientInvestigation count:", PatientInvestigation.objects.count())
print("InvestigationAttachment count:", InvestigationAttachment.objects.count())

for m in InvestigationMaster.objects.all()[:10]:
    print(f"Master: id={m.id}, name={m.name}, code={m.code}, company={m.company_id}")

for doc in Doctor.objects.all()[:5]:
    print(f"Doctor: id={doc.id}, name={doc.name}")

for inv in PatientInvestigation.objects.all()[:5]:
    print(f"Investigation: id={inv.id}, patient={inv.patient_id}, name={inv.investigation_name}, status={inv.status}, files={inv.attachments.count()}")
