import os
import sys
import io

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from django.test import RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import force_authenticate

from patients.models import (
    Company, Branch, Patient, Doctor, Appointment,
    InvestigationMaster, PatientInvestigation, InvestigationAttachment
)
from patients.views import (
    PatientInvestigationListView, PatientInvestigationDetailView,
    PatientInvestigationHistoryView, InvestigationAttachmentDetailView
)
from django.contrib.auth.models import User

print("=== STARTING ASHDENT INVESTIGATION INTEGRATION TEST ===")

# 1. Setup Test Fixtures
company = Company.objects.first()
if not company:
    company = Company.objects.create(name="AshDent HealthCorp")

branch = Branch.objects.filter(company=company).first()
if not branch:
    branch = Branch.objects.create(name="Main Clinic Branch", company=company)

user = User.objects.filter(is_superuser=True).first()
if not user:
    user = User.objects.create(username="test_admin", is_superuser=True, email="admin@ashdent.com")

patient = Patient.objects.filter(company=company).first()
if not patient:
    patient = Patient.objects.create(
        name="Test Patient Inv",
        phone="9876543210",
        company=company,
        registration_branch=branch
    )

doctor = Doctor.objects.first()
if not doctor:
    doctor = Doctor.objects.create(name="Dr. Ash Dent Test")

master = InvestigationMaster.objects.first()
if not master:
    master = InvestigationMaster.objects.create(
        name="Digital OPG Panoramic",
        code="OPG-01",
        company=company
    )

print(f"Company: {company.name} ({company.id})")
print(f"Branch: {branch.name} ({branch.id})")
print(f"Patient: {patient.name} ({patient.id})")
print(f"Doctor: {doctor.name} ({doctor.id})")
print(f"Master: {master.name} ({master.id})")

rf = RequestFactory()

# 2. Test Investigation Creation with File Upload (PDF)
print("\n--- TEST 1: CREATE INVESTIGATION WITH PDF REPORT ---")
pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
uploaded_pdf = SimpleUploadedFile("diagnostic_report.pdf", pdf_content, content_type="application/pdf")

post_data = {
    'patient': patient.id,
    'doctor': doctor.id,
    'investigation_master': master.id,
    'investigation_name': 'Digital OPG Panoramic',
    'investigation_date': '2026-11-12',
    'status': 'Requested',
    'reason': 'Evaluation of lower right 3rd molar impaction',
    'findings': 'Horizontally impacted 48 with roots approximating inferior alveolar nerve canal',
    'remarks': 'CBCT recommended prior to surgical disimpaction',
    'files': [uploaded_pdf]
}

req = rf.post('/api/patient-investigations/', post_data, format='multipart')
req.user = user
force_authenticate(req, user=user)

view = PatientInvestigationListView.as_view()
res = view(req)
print("Create response status:", res.status_code)
assert res.status_code == status.HTTP_201_CREATED, f"Failed creation: {res.data}"
created_data = res.data
inv_id = created_data['id']
print(f"Created Investigation ID: {inv_id}")
print(f"Status: {created_data['status']}")
print(f"Doctor: {created_data['doctor_name']}")
print(f"Patient: {created_data['patient_name']}")
print(f"Attachments count: {len(created_data.get('attachments', []))}")
assert len(created_data['attachments']) == 1, "Attachment was not created"
attachment_id = created_data['attachments'][0]['id']
print(f"Attachment ID: {attachment_id}, Name: {created_data['attachments'][0]['file_name']}")

# 3. Test Detail GET
print("\n--- TEST 2: GET INVESTIGATION DETAIL ---")
req = rf.get(f'/api/patient-investigations/{inv_id}/')
req.user = user
force_authenticate(req, user=user)
detail_view = PatientInvestigationDetailView.as_view()
res = detail_view(req, pk=inv_id)
print("Detail status:", res.status_code)
assert res.status_code == status.HTTP_200_OK
assert res.data['id'] == inv_id
assert res.data['reason'] == 'Evaluation of lower right 3rd molar impaction'

# 4. Test Lifecycle Transitions (Requested -> In Progress -> Completed)
print("\n--- TEST 3: STATUS LIFECYCLE TRANSITION ---")
# Transition to In Progress
req = rf.patch(f'/api/patient-investigations/{inv_id}/', {'status': 'In Progress'}, content_type='application/json')
req.user = user
force_authenticate(req, user=user)
res = detail_view(req, pk=inv_id)
assert res.status_code == status.HTTP_200_OK
assert res.data['status'] == 'In Progress'
print("Transitioned to: In Progress")

# Transition to Completed with updated findings
req = rf.patch(f'/api/patient-investigations/{inv_id}/', {
    'status': 'Completed',
    'findings': 'Confirmed: Surgical extraction completed without nerve injury.'
}, content_type='application/json')
req.user = user
force_authenticate(req, user=user)
res = detail_view(req, pk=inv_id)
assert res.status_code == status.HTTP_200_OK
assert res.data['status'] == 'Completed'
assert 'Surgical extraction completed' in res.data['findings']
print("Transitioned to: Completed with updated findings")

# 5. Test Patient History Listing
print("\n--- TEST 4: PATIENT INVESTIGATION HISTORY ---")
req = rf.get(f'/api/patients/{patient.id}/investigations-history/')
req.user = user
force_authenticate(req, user=user)
history_view = PatientInvestigationHistoryView.as_view()
res = history_view(req, patient_id=patient.id)
assert res.status_code == status.HTTP_200_OK
assert len(res.data) >= 1
assert any(item['id'] == inv_id for item in res.data)
print(f"History verified: {len(res.data)} investigation(s) found for patient")

# 6. Test Attachment Deletion
print("\n--- TEST 5: ATTACHMENT DELETION ---")
req = rf.delete(f'/api/investigation-attachments/{attachment_id}/')
req.user = user
force_authenticate(req, user=user)
att_view = InvestigationAttachmentDetailView.as_view()
res = att_view(req, pk=attachment_id)
assert res.status_code == status.HTTP_200_OK
print(f"Attachment {attachment_id} deleted successfully")

# Verify attachment removed from investigation
inv_obj = PatientInvestigation.objects.get(id=inv_id)
assert inv_obj.attachments.count() == 0, "Attachment should have been removed"

# 7. Test Investigation Deletion
print("\n--- TEST 6: INVESTIGATION DELETION ---")
req = rf.delete(f'/api/patient-investigations/{inv_id}/')
req.user = user
force_authenticate(req, user=user)
res = detail_view(req, pk=inv_id)
assert res.status_code == status.HTTP_200_OK
assert not PatientInvestigation.objects.filter(id=inv_id).exists()
print(f"Investigation {inv_id} deleted cleanly")

print("\n=== ALL INVESTIGATION INTEGRATION TESTS PASSED PERFECTLY! ===")
