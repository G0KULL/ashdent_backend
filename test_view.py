import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import RequestFactory
from patients.views import PatientClinicalHistoryView

factory = RequestFactory()
request = factory.get('/api/patient/6a040c8cc6cc1c8130f5ccc9/clinical-history/')
view = PatientClinicalHistoryView.as_view()
try:
    response = view(request, patient_id='6a040c8cc6cc1c8130f5ccc9')
    print("Response Status:", response.status_code)
except Exception as e:
    print("Exception:", e)
    import traceback
    traceback.print_exc()
