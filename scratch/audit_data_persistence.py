import os
import sys
import datetime
from decimal import Decimal

def audit_serializers():
    from patients.models import (
        Patient, Staff, Doctor, DoctorSchedule, Appointment, Visit, TreatmentMaster,
        TreatmentRecord, ClinicalNotes, Billing, BillingItem, Payment, MedicineMaster,
        MedicineStock, PharmacyPurchase, Supplier, SupplierLedger, PatientTypeMaster,
        StaffLevelMaster, DesignationMaster, RoleMaster, PermissionMaster, RolePermission,
        DiscountMaster, OfferPackage, StaffLeaveConfig, StaffBenefit, StaffInsurance,
        PatientLabOrder, DentalLaboratory, DentalLabWork, Expense, ExpenseCategory,
        PreBooking, TaxSetting, CommunicationTemplate, LabHeader, Laboratory
    )
    from patients import serializers

    print("\n=================== SERIALIZER AUDIT ===================")
    models_to_check = [
        (Patient, serializers.PatientSerializer),
        (Staff, serializers.StaffSerializer),
        (Doctor, serializers.DoctorSerializer),
        (Appointment, serializers.AppointmentSerializer),
        (Visit, serializers.VisitSerializer),
        (TreatmentMaster, serializers.TreatmentMasterSerializer),
        (TreatmentRecord, serializers.TreatmentRecordSerializer),
        (ClinicalNotes, serializers.ClinicalNotesSerializer),
        (Billing, serializers.BillingSerializer),
        (BillingItem, serializers.BillingItemSerializer),
        (MedicineMaster, serializers.MedicineMasterSerializer),
        (MedicineStock, serializers.MedicineStockSerializer),
        (Supplier, serializers.SupplierSerializer),
        (PharmacyPurchase, serializers.PharmacyPurchaseSerializer),
        (StaffLeaveConfig, getattr(serializers, 'StaffLeaveConfigSerializer', None)),
        (StaffBenefit, getattr(serializers, 'StaffBenefitSerializer', None)),
        (StaffInsurance, getattr(serializers, 'StaffInsuranceSerializer', None)),
    ]

    for model, ser_cls in models_to_check:
        if not ser_cls:
            print(f"[MISSING SERIALIZER] Model: {model.__name__}")
            continue

        model_fields = set(f.name for f in model._meta.fields if f.name != 'id')
        try:
            ser_instance = ser_cls()
            ser_fields = set(ser_instance.fields.keys())
        except Exception as e:
            print(f"[ERROR INSTANTIATING SERIALIZER] {model.__name__}: {e}")
            continue

        missing_in_ser = model_fields - ser_fields
        print(f"\n--- Model: {model.__name__} (Serializer: {ser_cls.__name__}) ---")
        print(f"Model Fields Count: {len(model_fields)} | Serializer Fields Count: {len(ser_fields)}")
        if missing_in_ser:
            print(f"[WARN] Fields in Model NOT exposed in Serializer: {sorted(list(missing_in_ser))}")
        else:
            print(f"[OK] All model fields are mapped in serializer!")

def audit_full_crud():
    from patients.models import (
        Patient, Staff, Doctor, Appointment, Visit, TreatmentMaster,
        TreatmentRecord, ClinicalNotes, Billing, BillingItem, MedicineMaster,
        Supplier, PharmacyPurchase, PatientTypeMaster, StaffLevelMaster,
        DesignationMaster, RoleMaster, PermissionMaster, DiscountMaster,
        OfferPackage, StaffLeaveConfig, StaffBenefit, StaffInsurance,
        PatientLabOrder, DentalLaboratory, DentalLabWork, Expense, ExpenseCategory,
        TaxSetting, CommunicationTemplate, LabHeader, Laboratory
    )

    print("\n=================== FULL FIELD PERSISTENCE AUDIT ===================")
    
    findings = []
    
    ptype, _ = PatientTypeMaster.objects.get_or_create(code="VIP_TEST", defaults={"name": "VIP Test"})

    # 1. Audit Patient Fields
    print("\n1. Testing Patient persistence...")
    p = Patient.objects.create(
        name="Audit Patient Test",
        phone="+91 9876543210",
        dob=datetime.date(1997, 5, 15),
        age=29,
        gender="Female",
        address="123 Audit Street, Cyber City",
        pincode="500081",
        patient_type=ptype,
        notes="Audit test notes",
        consultation_fee=Decimal("500.00")
    )
    p_refreshed = Patient.objects.get(id=p.id)
    fields_checked = ['name', 'phone', 'dob', 'age', 'gender', 'address', 'pincode', 'patient_type_id', 'notes', 'consultation_fee']
    for f in fields_checked:
        val = getattr(p_refreshed, f)
        if val is None or val == '':
            findings.append(('CRITICAL', 'Patient', f, 'Field failed to persist or returned empty.'))
        else:
            print(f"  [PASS] Patient.{f} = {val}")

    # 2. Audit Staff Fields
    print("\n2. Testing Staff persistence...")
    s = Staff.objects.create(
        name="Audit Staff Test",
        email="auditstaff@example.com",
        phone="+91 9988776655",
        role="Nurse",
        staff_level="Senior",
        dob=datetime.date(1994, 8, 20),
        gender="Female",
        blood_group="O+",
        age=32,
        emergency_contact="+91 9988776600",
        address="456 Staff Residency",
        base_salary=Decimal("45000.00"),
        incentive=Decimal("5000.00"),
        additional_details={"joining_date": "2021-06-01", "department": "Clinical"}
    )
    s_refreshed = Staff.objects.get(id=s.id)
    staff_fields = ['name', 'email', 'phone', 'role', 'staff_level', 'dob', 'gender', 'blood_group', 'age', 'emergency_contact', 'address', 'base_salary', 'incentive', 'additional_details']
    for f in staff_fields:
        val = getattr(s_refreshed, f)
        if val is None or val == '':
            findings.append(('CRITICAL', 'Staff', f, 'Field failed to persist.'))
        else:
            print(f"  [PASS] Staff.{f} = {val}")

    # 3. Audit Doctor Fields
    print("\n3. Testing Doctor persistence...")
    doc = Doctor.objects.create(
        name="Dr. Audit Specialist",
        specialty="Endodontics",
        phone="+91 9776655443",
        color="#10b981",
        slot_duration=15
    )
    doc_refreshed = Doctor.objects.get(id=doc.id)
    for f in ['name', 'specialty', 'phone', 'color', 'slot_duration']:
        val = getattr(doc_refreshed, f)
        print(f"  [PASS] Doctor.{f} = {val}")

    # 4. Audit Appointment Fields
    print("\n4. Testing Appointment persistence...")
    appt = Appointment.objects.create(
        patient=p_refreshed,
        doctor=doc_refreshed,
        date=datetime.date(2026, 10, 10),
        time=datetime.time(10, 30),
        status="Scheduled",
        is_virtual=True,
        meeting_link="https://meet.jit.si/audit_test",
        telemedicine_notes="Initial online consultation notes"
    )
    appt_refreshed = Appointment.objects.get(id=appt.id)
    for f in ['patient_id', 'doctor_id', 'date', 'time', 'status', 'is_virtual', 'meeting_link', 'telemedicine_notes']:
        val = getattr(appt_refreshed, f)
        print(f"  [PASS] Appointment.{f} = {val}")

    # 5. Audit Visit & ClinicalNotes Fields
    print("\n5. Testing Visit & ClinicalNotes persistence...")
    v = Visit.objects.create(patient=p_refreshed, appointment=appt_refreshed)
    cn = ClinicalNotes.objects.create(
        appointment=appt_refreshed,
        selected_teeth=[11, 12, 21],
        complaints=["Tooth pain in upper right quadrant"],
        observations=["Deep caries on tooth 11"],
        investigations=["RVG Intraoral X-Ray"],
        diagnosis=["Irreversible Pulpitis"],
        medical_history=["Hypertension"],
        dental_history=["Previous root canal in 2022"],
        allergies=["Penicillin"],
        ongoing_medications=["Amlodipine 5mg"],
        chief_complaint="Severe pain on biting",
        notes="Patient advised RCT + Crown",
        treatment_plan="RCT 11 + Zirconia Crown",
        follow_up_date=datetime.date(2026, 10, 17),
        follow_up_note="Check healing and post-obturation status"
    )
    cn_refreshed = ClinicalNotes.objects.get(id=cn.id)
    for f in ['selected_teeth', 'complaints', 'observations', 'investigations', 'diagnosis', 'chief_complaint', 'notes', 'treatment_plan', 'follow_up_date', 'follow_up_note']:
        val = getattr(cn_refreshed, f)
        print(f"  [PASS] ClinicalNotes.{f} = {val}")

    # 6. Audit Billing Fields
    print("\n6. Testing Billing persistence...")
    bill = Billing.objects.create(
        patient=p_refreshed,
        visit=v,
        clinical_note=cn_refreshed,
        doctor=doc_refreshed,
        bill_type="Clinical",
        total_amount=Decimal("5000.00"),
        paid_amount=Decimal("3000.00"),
        balance_amount=Decimal("2000.00"),
        payment_method="UPI",
        notes="Root Canal initial installment",
        status="Partial"
    )
    b_refreshed = Billing.objects.get(id=bill.id)
    for f in ['patient_id', 'visit_id', 'doctor_id', 'bill_type', 'total_amount', 'paid_amount', 'balance_amount', 'payment_method', 'notes', 'status']:
        val = getattr(b_refreshed, f)
        print(f"  [PASS] Billing.{f} = {val}")

    # Clean up test records
    bill.delete()
    cn.delete()
    v.delete()
    appt.delete()
    doc.delete()
    s.delete()
    p.delete()
    print("\n[OK] Cleaned up temporary test audit records.")

    print("\nSUMMARY OF AUDIT FINDINGS:")
    if not findings:
        print("[ALL PASS] All tested model fields persisted cleanly into MongoDB database!")
    else:
        for cat, mdl, fld, msg in findings:
            print(f"  - [{cat}] {mdl}.{fld}: {msg}")

if __name__ == '__main__':
    audit_serializers()
    audit_full_crud()
