import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from patients.models import Patient
p = Patient.objects.last()
print(type(p.id), p.id)
