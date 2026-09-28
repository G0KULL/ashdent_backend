import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
from patients.models import Patient
for p in Patient.objects.all()[:5]:
    print(p.id, p.name)
