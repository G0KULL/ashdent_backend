import os
import django
from pymongo import MongoClient

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from patients.models import (
    Company, Branch, Doctor, DoctorSchedule, Staff,
    ClinicProfile, AutoNumbering, RoleMaster, TreatmentMaster, DiagnosisMaster
)

def execute_controlled_reset():
    print("=" * 70)
    print("ASHDENT HMS — CONTROLLED DATABASE RESET & CLEAN INITIALIZATION")
    print("=" * 70)

    client = MongoClient('mongodb://localhost:27017/')
    db = client['dental_clinic_db']

    # 1. Operational collections to clear
    operational_collections = [
        'patients_patient',
        'patients_patient_groups',
        'patients_appointment',
        'patients_visit',
        'patients_clinicalnotes',
        'patients_treatmentrecord',
        'patients_patientlaborder',
        'patients_prescription',
        'patients_prescriptionitem',
        'patients_billing',
        'patients_billingitem',
        'patients_payment',
        'patients_transaction',
        'patients_expense',
        'patients_prebooking',
        'patients_slot_lock',
        'patients_doctordateoverride',
        'patients_doctorscheduleproposal',
        'patients_communicationlog',
        'patients_inappnotification',
        'patients_auditlog',
        'patients_staffbenefit',
        'patients_staffinsurance',
    ]

    print("\n--- Phase 4: Clearing Operational & Transactional Collections ---")
    deletion_results = {}
    for col_name in operational_collections:
        if col_name in db.list_collection_names():
            res = db[col_name].delete_many({})
            deletion_results[col_name] = res.deleted_count
            print(f"  [CLEARED] {col_name}: {res.deleted_count} documents deleted (current count: 0)")
        else:
            deletion_results[col_name] = 0
            print(f"  [SKIPPED] {col_name}: collection does not exist")

    # 2. Reinitialize Group D: AutoNumbering & Configuration
    print("\n--- Phase 4 (Group D): Reinitializing AutoNumbering Configuration ---")
    main_company = Company.objects.filter(code='ASHDENT').first()
    main_branch = Branch.objects.filter(code='MAIN').first()

    # Clear existing autonumbering if any
    db['patients_autonumbering'].delete_many({})

    # Seed fresh AutoNumbering for Main Branch
    auto_num = AutoNumbering.objects.create(
        company=main_company,
        branch=main_branch,
        patient_prefix="PT-",
        patient_start=1001,
        invoice_prefix="INV-",
        invoice_start=500,
        prescription_prefix="RX-",
        prescription_start=200
    )
    print(f"  [INITIALIZED] AutoNumbering: Patient PT-{auto_num.patient_start}, Invoice INV-{auto_num.invoice_start}, RX-{auto_num.prescription_start}")

    # Verify Clinic Profile is bound to Main Branch & Company
    cp = ClinicProfile.objects.first()
    if cp:
        if not cp.company_id and main_company:
            cp.company = main_company
        if not cp.branch_id and main_branch:
            cp.branch = main_branch
        cp.save()
        print(f"  [VERIFIED] ClinicProfile: '{cp.name}' linked to {main_company} / {main_branch}")

    # 3. Verification of Preserved Application-Critical Data
    print("\n--- Verification of Preserved Master & Authentication Records ---")
    users_count = User.objects.count()
    staff_count = Staff.objects.count()
    doctors_count = Doctor.objects.count()
    schedules_count = DoctorSchedule.objects.count()
    companies_count = Company.objects.count()
    branches_count = Branch.objects.count()
    treatments_count = TreatmentMaster.objects.count()
    diagnoses_count = DiagnosisMaster.objects.count()
    roles_count = RoleMaster.objects.count()

    print(f"  Users Preserved: {users_count}")
    print(f"  Staff Preserved: {staff_count}")
    print(f"  Doctors Preserved: {doctors_count}")
    print(f"  Doctor Recurring Schedules Preserved: {schedules_count}")
    print(f"  Companies Preserved: {companies_count}")
    print(f"  Branches Preserved: {branches_count}")
    print(f"  Treatments Preserved: {treatments_count}")
    print(f"  Diagnoses Preserved: {diagnoses_count}")
    print(f"  System Roles Preserved: {roles_count}")

    assert users_count >= 1, "Error: No users found!"
    assert doctors_count == 4, f"Error: Expected 4 doctors preserved, got {doctors_count}!"
    assert schedules_count == 26, f"Error: Expected 26 schedules preserved, got {schedules_count}!"
    assert companies_count >= 1, "Error: No company found!"
    assert branches_count >= 1, "Error: No branch found!"
    assert treatments_count > 0, "Error: Treatments master missing!"

    print("\n" + "=" * 70)
    print("CONTROLLED RESET & CLEAN INITIALIZATION EXECUTED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == '__main__':
    execute_controlled_reset()
