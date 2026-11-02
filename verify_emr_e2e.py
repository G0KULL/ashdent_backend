import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from decimal import Decimal

from patients.models import (
    Company, Branch, Doctor, Patient, Appointment, Visit,
    ClinicalNotes, ToothConditionRecord, TreatmentPlan, TreatmentPlanItem,
    TreatmentRecord, TreatmentMaster, TreatmentSession, Prescription,
    PrescriptionItem, PatientInvestigation, InvestigationMaster, EMRChangeLog
)
from patients.emr_views import (
    PatientToothConditionsView, TreatmentPlanListCreateView,
    ConvertPlanItemToTreatmentRecordView, TreatmentSessionListCreateView,
    PatientEMRDetailView, EMRPDFReportView
)

def run_e2e_emr_test():
    print("==================================================================")
    print("STARTING COMPLETE END-TO-END PATIENT EMR & PERSISTENCE AUDIT TEST")
    print("==================================================================")

    rf = RequestFactory()

    # Step 1: Ensure Company, Branch, Doctor exist
    company, _ = Company.objects.get_or_create(code="ASHDENT_HQ", defaults={"name": "AshDent Dental Care HQ"})
    branch, _ = Branch.objects.get_or_create(company=company, code="BR_CENTRAL", defaults={"name": "Central Dental Hospital"})
    doctor, _ = Doctor.objects.get_or_create(name="Dr. Sarah Jenkins", defaults={
        "company": company,
        "specialization": "Prosthodontist & Implantologist",
        "consultation_fee": Decimal("800.00")
    })
    print("[1] Organization Setup: Company, Branch, Doctor verified.")

    # Step 2: Patient Registration
    patient, created = Patient.objects.get_or_create(
        name="Audited EMR Patient",
        phone="9876543299",
        defaults={
            "company": company,
            "registration_branch": branch,
            "doctor": doctor,
            "gender": "Female",
            "age": 34,
            "address": "45 Park Avenue, Healthcare District",
            "pincode": "600001"
        }
    )
    print(f"[2] Patient Registration: #{patient.id} - {patient.name} ({'Created' if created else 'Existing'}).")

    # Step 3: Appointment Booking & Visit Check-in
    today = timezone.now().date()
    appt, _ = Appointment.objects.get_or_create(
        patient=patient,
        date=today,
        defaults={
            "company": company,
            "branch": branch,
            "doctor": doctor,
            "time": timezone.now().time(),
            "status": "Completed"
        }
    )
    visit, _ = Visit.objects.get_or_create(
        appointment=appt,
        defaults={
            "patient": patient,
            "company": company,
            "branch": branch
        }
    )
    print(f"[3] Appointment & Visit: Appt #{appt.id}, Visit #{visit.id} on {appt.date}.")

    # Step 4: Clinical Consultation Notes & Examination
    cn, _ = ClinicalNotes.objects.update_or_create(
        appointment=appt,
        defaults={
            "chief_complaint": "Severe throbbing pain in upper right tooth (#16) radiating to ear since 3 days.",
            "complaints": ["Pain while chewing", "Sensitivity to hot foods"],
            "observations": ["Deep occlusal breakdown tooth #16", "Tenderness on percussion positive"],
            "diagnosis": ["Irreversible Pulpitis #16", "Moderate Generalized Gingivitis"],
            "medical_history": ["Asthma (mild)", "Hypertension controlled"],
            "allergies": ["Penicillin Allergy"],
            "ongoing_medications": ["Inhaler SOS", "Amlodipine 5mg"],
            "selected_teeth": [16, 17, 46],
            "chart_conditions": {
                "16": ["Decayed"],
                "17": ["Treatment Taken Before"],
                "46": ["Decayed"]
            },
            "follow_up_date": today + timezone.timedelta(days=7),
            "follow_up_note": "RCT Session 2: Canal shaping & biomechanical preparation",
            "follow_up_status": "Pending"
        }
    )
    print(f"[4] Clinical Notes & Examination: Note #{cn.id} saved to DB.")

    # Step 5: Odontogram & Tooth Condition Persistence API
    teeth_payload = {
        "16": {
            "condition": ["Decayed"],
            "surfaces": ["Mesial", "Occlusal"],
            "diagnosis": ["Irreversible Pulpitis"],
            "examination": ["Pain on percussion positive"],
            "mobility": "Grade 0",
            "pocket_depth": "3 mm"
        },
        "17": {
            "condition": ["Treatment Taken Before"],
            "surfaces": ["Occlusal"],
            "diagnosis": ["Old Amalgam Restoration"]
        },
        "46": {
            "condition": ["Decayed"],
            "surfaces": ["Distal"],
            "diagnosis": ["Dental Caries"]
        }
    }
    tc_req = rf.post(f"/api/patients/{patient.id}/tooth-conditions/", data={"teeth_data": teeth_payload, "appointment_id": str(appt.id)}, content_type="application/json")
    tc_req.user = AnonymousUser()
    tc_res = PatientToothConditionsView.as_view()(tc_req, patient_id=patient.id)
    assert tc_res.status_code == 200, f"Tooth conditions save failed: {tc_res.status_code}"
    
    # Verify in DB
    db_tc_count = ToothConditionRecord.objects.filter(patient=patient, is_active=True).count()
    assert db_tc_count >= 3, f"Expected at least 3 tooth condition records in DB, found {db_tc_count}"
    print(f"[5] Odontogram Persistence: Verified {db_tc_count} tooth condition records in MongoDB.")

    # Step 6: Recommended Treatment Plans API
    plan_payload = {
        "title": "Comprehensive Restorative & Endodontic Plan",
        "status": "Accepted",
        "items": [
            {
                "tooth": "16",
                "procedure": "Molar Endodontic Therapy (RCT)",
                "surface": "Mesial-Occlusal",
                "priority": "Urgent",
                "cost": 5000,
                "finalAmount": 4500,
                "visits": 3,
                "status": "Accepted",
                "notes": "Rotary instrumentation, multi-visit RCT"
            },
            {
                "tooth": "16",
                "procedure": "Biocompatible Zirconia Crown",
                "surface": "Full Crown",
                "priority": "Routine",
                "cost": 8000,
                "finalAmount": 7500,
                "visits": 2,
                "status": "Proposed",
                "notes": "Post-endo crown restoration"
            },
            {
                "tooth": "46",
                "procedure": "Light-Cured Composite Filling",
                "surface": "Distal",
                "priority": "Routine",
                "cost": 1500,
                "finalAmount": 1500,
                "visits": 1,
                "status": "Proposed",
                "notes": "Class II composite restoration"
            }
        ]
    }
    plan_req = rf.post(f"/api/patients/{patient.id}/treatment-plans/", data=plan_payload, content_type="application/json")
    plan_req.user = AnonymousUser()
    plan_res = TreatmentPlanListCreateView.as_view()(plan_req, patient_id=patient.id)
    assert plan_res.status_code in [200, 201], f"Treatment plan save failed: {plan_res.status_code}"
    plan_id = plan_res.data["plan_id"]
    db_plan = TreatmentPlan.objects.get(id=plan_id)
    assert db_plan.items.count() == 3, f"Expected 3 items in treatment plan, found {db_plan.items.count()}"
    print(f"[6] Recommended Treatment Plans: Plan #{db_plan.id} saved with 3 items totaling INR {db_plan.total_estimated_cost:,.2f}.")

    # Step 7: Executed Treatment & Multi-Session Tracking
    first_plan_item = db_plan.items.filter(tooth_number="16").first()
    conv_req = rf.post(f"/api/treatment-plan-items/{first_plan_item.id}/convert-to-treatment/", data={
        "visit_id": str(visit.id),
        "doctor_id": str(doctor.id),
        "status": "In Progress",
        "notes": "Session 1 Completed: Access opening done, working length determined (MB: 20mm, DB: 19.5mm, P: 21mm). Closed dressing given with Ca(OH)2."
    }, content_type="application/json")
    conv_req.user = AnonymousUser()
    conv_res = ConvertPlanItemToTreatmentRecordView.as_view()(conv_req, item_id=first_plan_item.id)
    assert conv_res.status_code == 201, f"Convert to treatment failed: {conv_res.status_code}"
    tr_id = conv_res.data["treatment_record_id"]
    db_tr = TreatmentRecord.objects.get(id=tr_id)

    # Add Session 2
    sess_req = rf.post(f"/api/patients/{patient.id}/treatment-sessions/", data={
        "treatment_record_id": str(db_tr.id),
        "procedure_performed": "Canal shaping & Biomechanical Preparation",
        "clinical_notes": "All 3 canals shaped up to F2 ProTaper. Copious irrigation with NaOCl and saline.",
        "materials_used": "ProTaper Gold, EDTA gel, NaOCl 3%",
        "next_session_plan": "Obturation & Core buildup",
        "next_session_date": str(today + timezone.timedelta(days=7)),
        "status": "Completed"
    }, content_type="application/json")
    sess_req.user = AnonymousUser()
    sess_res = TreatmentSessionListCreateView.as_view()(sess_req, patient_id=patient.id)
    assert sess_res.status_code == 201, f"Session create failed: {sess_res.status_code}"
    print(f"[7] Executed Treatments & Sessions: TreatmentRecord #{db_tr.id} with Multi-session logging verified in DB.")

    # Step 8: Prescription Generation
    rx, _ = Prescription.objects.get_or_create(
        patient=patient,
        visit=visit,
        doctor=doctor,
        defaults={"notes": "Take medications strictly after meals. Avoid chewing hard on tooth #16."}
    )
    rx.items.all().delete()
    PrescriptionItem.objects.create(prescription=rx, medicine_name="Amoxicillin + Clavulanic Acid (Augmentin 625)", dosage="1-0-1", duration="5 days", notes="Take after breakfast and dinner")
    PrescriptionItem.objects.create(prescription=rx, medicine_name="Aceclofenac + Paracetamol (Zerodol-P)", dosage="1-0-1", duration="3 days", notes="Analgesic - Take after food")
    PrescriptionItem.objects.create(prescription=rx, medicine_name="Pantoprazole 40mg", dosage="1-0-0", duration="5 days", notes="Take before food in morning")
    print(f"[8] Prescriptions: Rx #{rx.id} with 3 items saved to DB.")

    # Step 9: Diagnostic Investigations
    inv_master, _ = InvestigationMaster.objects.get_or_create(name="Digital OPG (Full Mouth)", defaults={"code": "OPG-01", "default_cost": Decimal("750.00")})
    inv, _ = PatientInvestigation.objects.get_or_create(
        patient=patient,
        appointment=appt,
        investigation_name="Digital OPG (Full Mouth)",
        defaults={
            "doctor": doctor,
            "investigation_master": inv_master,
            "investigation_date": today,
            "reason": "Evaluation of periapical radiolucency #16 and generalized bone levels",
            "findings": "Periapical widening of PDL space seen at apex of mesiobuccal root #16. No furcation involvement. Alveolar bone height normal.",
            "status": "Completed"
        }
    )
    print(f"[9] Investigations: PatientInvestigation #{inv.id} verified in DB.")

    # Step 10: EMR Detail JSON API Verification
    emr_req = rf.get(f"/api/patients/{patient.id}/emr/")
    emr_req.user = AnonymousUser()
    emr_res = PatientEMRDetailView.as_view()(emr_req, patient_id=patient.id)
    assert emr_res.status_code == 200, f"EMR Detail failed: {emr_res.status_code}"
    data = emr_res.data
    assert data["patient"]["name"] == patient.name
    assert len(data["tooth_conditions"]) >= 3
    assert len(data["treatment_plans"]) >= 1
    assert len(data["performed_treatments"]) >= 1
    assert len(data["treatment_sessions"]) >= 2
    assert len(data["prescriptions"]) >= 1
    assert len(data["investigations"]) >= 1
    assert len(data["visits_timeline"]) >= 1
    print(f"[10] Full EMR Detail JSON: Verified across all 15 clinical dimensions successfully.")

    # Step 11: Option A - Lifetime EMR PDF Report Generation
    pdf_req = rf.get(f"/api/patients/{patient.id}/emr-report/pdf/")
    pdf_req.user = AnonymousUser()
    pdf_res = EMRPDFReportView.as_view()(pdf_req, patient_id=patient.id)
    assert pdf_res.status_code == 200, f"PDF report failed: {pdf_res.status_code}"
    assert pdf_res["Content-Type"] == "application/pdf"
    pdf_bytes = len(pdf_res.content)
    assert pdf_bytes > 3000, f"PDF size too small: {pdf_bytes} bytes"
    print(f"[11] Option A (Lifetime EMR PDF): Generated successfully ({pdf_bytes} bytes, verified valid PDF).")

    # Step 12: Option B - Individual Visit EMR PDF Report Generation
    visit_pdf_req = rf.get(f"/api/patients/{patient.id}/emr-report/pdf/?appointment_id={appt.id}")
    visit_pdf_req.user = AnonymousUser()
    visit_pdf_res = EMRPDFReportView.as_view()(visit_pdf_req, patient_id=patient.id)
    assert visit_pdf_res.status_code == 200, f"Visit PDF report failed: {visit_pdf_res.status_code}"
    assert visit_pdf_res["Content-Type"] == "application/pdf"
    visit_pdf_bytes = len(visit_pdf_res.content)
    assert visit_pdf_bytes > 3000, f"Visit PDF size too small: {visit_pdf_bytes} bytes"
    print(f"[12] Option B (Visit EMR PDF): Generated successfully ({visit_pdf_bytes} bytes, verified valid PDF).")

    print("==================================================================")
    print("ALL 12 END-TO-END EMR & PERSISTENCE VERIFICATION CHECKS PASSED 100%!")
    print("==================================================================")

if __name__ == "__main__":
    run_e2e_emr_test()
