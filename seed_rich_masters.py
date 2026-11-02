import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import (
    PatientTypeMaster, StaffLevelMaster, DesignationMaster, RoleMaster,
    DiscountMaster, OfferPackage
)

def seed_rich_masters():
    print("=" * 60)
    print("SEEDING RICH MASTERS MODULE DATA")
    print("=" * 60)

    # 1. PATIENT TYPES
    patient_types = [
        {'name': 'Regular Patient', 'code': 'REG', 'description': 'Standard walk-in patient with standard pricing', 'display_order': 1},
        {'name': 'VIP Patient', 'code': 'VIP', 'description': 'Executive / priority patient with concierge care', 'display_order': 2},
        {'name': 'Senior Citizen', 'code': 'SNR', 'description': 'Senior citizens eligible for special healthcare discounts', 'display_order': 3},
        {'name': 'Corporate / Insurance', 'code': 'CORP', 'description': 'Empaneled corporate employee or insured patient', 'display_order': 4},
        {'name': 'Student / Dependent', 'code': 'STU', 'description': 'Students and registered dependents', 'display_order': 5},
        {'name': 'Staff / Internal', 'code': 'STAFF', 'description': 'Internal clinic staff member or direct relative', 'display_order': 6},
    ]

    count_pt = 0
    for data in patient_types:
        obj, created = PatientTypeMaster.objects.get_or_create(code=data['code'], defaults=data)
        if not created:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
        count_pt += 1
    print(f"[OK] Patient Types: {count_pt} records configured.")

    # 2. SYSTEM ROLES
    roles = [
        {'name': 'Admin', 'code': 'ADMIN', 'description': 'Full administrative control over clinic operations, staff, and settings', 'is_system_role': True},
        {'name': 'Doctor', 'code': 'DOCTOR', 'description': 'Clinical practitioner handling diagnosis, treatments, and prescriptions', 'is_system_role': True},
        {'name': 'Pharmacist', 'code': 'PHARMACIST', 'description': 'Pharmacy inventory, medicine dispensation, and stock management', 'is_system_role': True},
        {'name': 'Receptionist', 'code': 'RECEPTIONIST', 'description': 'Front desk manager handling registrations, appointments, and billing', 'is_system_role': True},
        {'name': 'Accountant', 'code': 'ACCOUNTANT', 'description': 'Financial audits, clinic expense tracking, and salary management', 'is_system_role': True},
        {'name': 'Dental Assistant', 'code': 'ASSISTANT', 'description': 'Clinical chairside assistance and instrument sterilization', 'is_system_role': True},
        {'name': 'Lab Technician', 'code': 'LAB_TECH', 'description': 'Pathology and dental lab work coordinator', 'is_system_role': False},
        {'name': 'Hygienist', 'code': 'HYGIENIST', 'description': 'Preventive oral care and scaling specialist', 'is_system_role': False},
    ]

    count_role = 0
    for data in roles:
        obj, created = RoleMaster.objects.get_or_create(name=data['name'], defaults=data)
        if not created:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
        count_role += 1
    print(f"[OK] Roles: {count_role} records configured.")

    # 3. STAFF LEVELS
    staff_levels = [
        {'name': 'Intern / Trainee', 'code': 'L1', 'description': 'Entry-level trainee undergoing orientation', 'display_order': 1},
        {'name': 'Junior Staff', 'code': 'L2', 'description': 'Junior clinical or administrative staff member', 'display_order': 2},
        {'name': 'Senior Staff', 'code': 'L3', 'description': 'Experienced practitioner or senior staff member', 'display_order': 3},
        {'name': 'Lead / Department Head', 'code': 'L4', 'description': 'Head of department or clinical supervisor', 'display_order': 4},
        {'name': 'Consultant / Specialist', 'code': 'L5', 'description': 'Visiting specialist or senior consultant', 'display_order': 5},
    ]

    count_sl = 0
    for data in staff_levels:
        obj, created = StaffLevelMaster.objects.get_or_create(code=data['code'], defaults=data)
        if not created:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
        count_sl += 1
    print(f"[OK] Staff Levels: {count_sl} records configured.")

    # 4. DESIGNATIONS
    designations = [
        {'name': 'Chief Dental Surgeon', 'code': 'CDS', 'description': 'Clinical director and primary dental surgeon', 'display_order': 1},
        {'name': 'Senior Orthodontist', 'code': 'SR_ORTHO', 'description': 'Specialist in braces, aligners, and jaw correction', 'display_order': 2},
        {'name': 'Endodontist', 'code': 'ENDO', 'description': 'Specialist in root canal treatments and microscopic endodontics', 'display_order': 3},
        {'name': 'Pediatric Dentist', 'code': 'PEDO', 'description': 'Specialist in infant and child dental care', 'display_order': 4},
        {'name': 'Oral & Maxillofacial Surgeon', 'code': 'ORAL_SURG', 'description': 'Specialist in complex extractions and jaw surgery', 'display_order': 5},
        {'name': 'Front Desk Manager', 'code': 'FDM', 'description': 'Head of patient reception, concierge, and scheduling', 'display_order': 6},
        {'name': 'Lead Pharmacist', 'code': 'LEAD_PHARM', 'description': 'Pharmacy manager overseeing medicine supply chain', 'display_order': 7},
        {'name': 'Senior Accountant', 'code': 'SR_ACCT', 'description': 'Financial manager handling revenue audits and payroll', 'display_order': 8},
    ]

    count_desig = 0
    for data in designations:
        obj, created = DesignationMaster.objects.get_or_create(code=data['code'], defaults=data)
        if not created:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
        count_desig += 1
    print(f"[OK] Designations: {count_desig} records configured.")

    # 5. DISCOUNTS
    discounts = [
        {
            'name': 'Senior Citizen Discount', 'code': 'DISC_SNR',
            'description': '15% concession for registered senior citizens',
            'discount_type': 'Percentage', 'discount_value': 15.00,
            'applicable_module': 'BILLING', 'max_discount': 2000.00, 'is_active': True
        },
        {
            'name': 'Corporate Preferred Discount', 'code': 'DISC_CORP',
            'description': '10% privilege discount for corporate partner employees',
            'discount_type': 'Percentage', 'discount_value': 10.00,
            'applicable_module': 'BILLING', 'max_discount': 1500.00, 'is_active': True
        },
        {
            'name': 'Festive Smile Voucher', 'code': 'DISC_FEST',
            'description': 'Flat ₹500 discount on treatments above ₹3,000',
            'discount_type': 'Fixed Amount', 'discount_value': 500.00,
            'applicable_module': 'BILLING', 'max_discount': 500.00, 'is_active': True
        },
        {
            'name': 'Family Bundle Discount', 'code': 'DISC_FAM',
            'description': '12% discount for family member group consultations',
            'discount_type': 'Percentage', 'discount_value': 12.00,
            'applicable_module': 'BILLING', 'max_discount': 1200.00, 'is_active': True
        },
        {
            'name': 'Student Care Concession', 'code': 'DISC_STU',
            'description': '10% concession for school & college students',
            'discount_type': 'Percentage', 'discount_value': 10.00,
            'applicable_module': 'BILLING', 'max_discount': 1000.00, 'is_active': True
        },
    ]

    count_disc = 0
    for data in discounts:
        obj, created = DiscountMaster.objects.get_or_create(code=data['code'], defaults=data)
        if not created:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
        count_disc += 1
    print(f"[OK] Discounts: {count_disc} records configured.")

    # 6. OFFER PACKAGES
    packages = [
        {
            'name': 'Complete Smile Makeover', 'code': 'PKG_SMILE',
            'description': 'Full mouth scaling, stain removal, whitening, and high-gloss polish',
            'package_type': 'Combo Treatment', 'original_price': 7500.00, 'package_price': 4999.00,
            'discount_type': 'Flat Amount', 'discount_value': 2501.00, 'validity_days': 365, 'is_active': True
        },
        {
            'name': 'Executive Dental Checkup Pack', 'code': 'PKG_EXEC',
            'description': 'Comprehensive consultation, digital OPG X-ray, ultrasonic scaling, and fluoride treatment',
            'package_type': 'Combo Treatment', 'original_price': 2500.00, 'package_price': 1499.00,
            'discount_type': 'Flat Amount', 'discount_value': 1001.00, 'validity_days': 180, 'is_active': True
        },
        {
            'name': 'Kids Preventive Care Package', 'code': 'PKG_KIDS',
            'description': 'Pediatric examination, cavity sealants (2 teeth), and protective fluoride varnish',
            'package_type': 'Membership Plan', 'original_price': 1800.00, 'package_price': 999.00,
            'discount_type': 'Flat Amount', 'discount_value': 801.00, 'validity_days': 180, 'is_active': True
        },
        {
            'name': 'Ortho Starter Package', 'code': 'PKG_ORTHO',
            'description': 'Orthodontic specialist evaluation, 3D study models, intraoral photography & treatment roadmap',
            'package_type': 'Seasonal Offer', 'original_price': 4500.00, 'package_price': 2999.00,
            'discount_type': 'Flat Amount', 'discount_value': 1501.00, 'validity_days': 365, 'is_active': True
        },
    ]

    count_pkg = 0
    for data in packages:
        obj, created = OfferPackage.objects.get_or_create(code=data['code'], defaults=data)
        if not created:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
        count_pkg += 1
    print(f"[OK] Offer Packages: {count_pkg} records configured.")

    print("=" * 60)
    print("MASTERS SEEDING COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == '__main__':
    seed_rich_masters()
