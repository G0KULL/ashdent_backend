import os, sys
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()

from django.test import RequestFactory
from rest_framework import status
from rest_framework.test import force_authenticate
from patients.models import Company, Patient, Doctor, InvestigationMaster, PatientInvestigation
from patients.views import PatientInvestigationDetailView
from django.contrib.auth.models import User

rf = RequestFactory()
detail_view = PatientInvestigationDetailView.as_view()

# Get company A and B
comp_a = Company.objects.first()
comp_b = Company.objects.exclude(id=comp_a.id).first()
if not comp_b:
    comp_b = Company.objects.create(name="External Dental Corp")

pat_a = Patient.objects.filter(company=comp_a).first()
inv_a = PatientInvestigation.objects.create(
    company=comp_a,
    patient=pat_a,
    investigation_name="Tenant Test Scan",
    status="Requested"
)

# Create user belonging to company B
user_b = User.objects.filter(username="doc_b").first()
if not user_b:
    user_b = User.objects.create(username="doc_b", is_superuser=False)
if hasattr(user_b, 'profile'):
    user_b.profile.company = comp_b
    user_b.profile.save()

# Try to access inv_a with user_b
req = rf.get(f'/api/patient-investigations/{inv_a.id}/')
req.user = user_b
force_authenticate(req, user=user_b)
res = detail_view(req, pk=inv_a.id)

print(f"Cross-tenant GET access status: {res.status_code}")
assert res.status_code == status.HTTP_403_FORBIDDEN or res.status_code == status.HTTP_404_NOT_FOUND, f"Expected 403/404, got {res.status_code}"
print("Tenant isolation verification: PASS")

inv_a.delete()

