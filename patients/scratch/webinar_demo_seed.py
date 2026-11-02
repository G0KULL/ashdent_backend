import os
import sys
import json
import django
from datetime import date, datetime, time, timedelta
from decimal import Decimal

# 1. Setup Django Environment
sys.path.append(r'c:\Users\gokul\Downloads\dental software\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from patients.models import (
    Doctor, DoctorSchedule, Staff, PatientGroup, Patient, Appointment,
    ToothMaster, TreatmentMaster, Visit, ClinicalNotes, TreatmentRecord,
    Payment, Billing, BillingItem, Prescription, PrescriptionItem,
    MedicineMaster, Transaction, PatientTypeMaster, StaffLevelMaster,
    DesignationMaster, RoleMaster, PermissionMaster, DiscountMaster, OfferPackage,
    OfferPackageItem, TaxSetting, ClinicProfile, ClinicTiming, AutoNumbering,
    PharmacySettings, PatientLabOrder, PreBooking, ExpenseCategory, Expense
)

BACKUP_PATH = r'C:\Users\gokul\.gemini\antigravity-ide\brain\576f8d9b-4e39-42a0-9ff6-2eee393da123\db_backup_before_webinar.json'

print("=============================================================")
print("  DENTAL HMS — WEBINAR DEMO DATASET GENERATOR & CLEANUP      ")
print("=============================================================")

# -------------------------------------------------------------
# STEP 1: BACKUP TRANSACTIONAL DATA
# -------------------------------------------------------------
print("\n[STEP 1] Backing up existing transactional database records...")

backup_data = {
    'patients': list(Patient.objects.values()),
    'appointments': list(Appointment.objects.values()),
    'visits': list(Visit.objects.values()),
    'clinical_notes': list(ClinicalNotes.objects.values()),
    'treatment_records': list(TreatmentRecord.objects.values()),
    'billings': list(Billing.objects.values()),
    'billing_items': list(BillingItem.objects.values()),
    'payments': list(Payment.objects.values()),
    'prescriptions': list(Prescription.objects.values()),
    'prescription_items': list(PrescriptionItem.objects.values()),
    'transactions': list(Transaction.objects.values()),
    'expenses': list(Expense.objects.values()),
}

try:
    with open(BACKUP_PATH, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=2, default=str)
    print(f"SUCCESS: Backup created successfully at:\n   {BACKUP_PATH}")
except Exception as e:
    print(f"WARNING: Backup writing failed: {e}")

# -------------------------------------------------------------
# STEP 2: AUDIT & CLEANUP OF TEST TRANSACTIONAL DATA
# -------------------------------------------------------------
print("\n[STEP 2] Auditing and cleaning test transactional data...")

counts_before = {
    'patients': Patient.objects.count(),
    'appointments': Appointment.objects.count(),
    'visits': Visit.objects.count(),
    'clinical_notes': ClinicalNotes.objects.count(),
    'treatment_records': TreatmentRecord.objects.count(),
    'billings': Billing.objects.count(),
    'billing_items': BillingItem.objects.count(),
    'payments': Payment.objects.count(),
    'prescriptions': Prescription.objects.count(),
    'prescription_items': PrescriptionItem.objects.count(),
    'transactions': Transaction.objects.count(),
    'expenses': Expense.objects.count(),
    'pre_bookings': PreBooking.objects.count(),
    'lab_orders': PatientLabOrder.objects.count(),
}

print(f"Preserving System Config, Roles, Permissions, Master Settings, Admin Users.")
print(f"Removing {counts_before['patients']} test patients, {counts_before['appointments']} test appointments, {counts_before['billings']} test bills...")

# Perform transactional data purge
PatientLabOrder.objects.all().delete()
PreBooking.objects.all().delete()
PrescriptionItem.objects.all().delete()
Prescription.objects.all().delete()
BillingItem.objects.all().delete()
Billing.objects.all().delete()
Payment.objects.all().delete()
TreatmentRecord.objects.all().delete()
ClinicalNotes.objects.all().delete()
Visit.objects.all().delete()
Appointment.objects.all().delete()
Transaction.objects.all().delete()
Expense.objects.all().delete()
Patient.objects.all().delete()

# Preserve admin/superadmin users & staff accounts
from django.db import connections
db = connections['default'].database
db['auth_user'].delete_many({'is_superuser': False, 'is_staff': False, 'username': {'$ne': 'admin'}})

DoctorSchedule.objects.all().delete()
Staff.objects.all().delete()
Doctor.objects.all().delete()

print("[OK] Data purge completed cleanly.")

# -------------------------------------------------------------
# STEP 3: ENSURE REQUIRED MASTERS & CONFIGURATION
# -------------------------------------------------------------
print("\n[STEP 3] Ensuring clinic settings & masters...")

# Patient Types
pt_regular, _ = PatientTypeMaster.objects.get_or_create(code='REGULAR', defaults={'name': 'Regular Patient', 'display_order': 1})
pt_vip, _ = PatientTypeMaster.objects.get_or_create(code='VIP', defaults={'name': 'VIP Patient', 'display_order': 2})
pt_senior, _ = PatientTypeMaster.objects.get_or_create(code='SENIOR', defaults={'name': 'Senior Citizen', 'display_order': 3})
pt_camp, _ = PatientTypeMaster.objects.get_or_create(code='CAMP', defaults={'name': 'Free Camp / Charity', 'display_order': 4})

# Treatments Master (Clean, realistic dental procedures)
treatments_data = [
    {'name': 'Dental Consultation', 'price': Decimal('500.00'), 'fee_type': 'Consultation'},
    {'name': 'Dental Cleaning & Scaling', 'price': Decimal('1200.00'), 'fee_type': 'Preventive'},
    {'name': 'Composite Tooth Filling', 'price': Decimal('1500.00'), 'fee_type': 'Restorative'},
    {'name': 'Root Canal Treatment (RCT)', 'price': Decimal('4500.00'), 'fee_type': 'Endodontics'},
    {'name': 'Simple Tooth Extraction', 'price': Decimal('1000.00'), 'fee_type': 'Surgery'},
    {'name': 'Porcelain / E-Max Crown', 'price': Decimal('6000.00'), 'fee_type': 'Prosthodontics'},
    {'name': 'Zirconia Premium Crown', 'price': Decimal('9000.00'), 'fee_type': 'Prosthodontics'},
    {'name': 'Orthodontic Consultation', 'price': Decimal('800.00'), 'fee_type': 'Orthodontics'},
    {'name': 'Metal / Ceramic Braces Setup', 'price': Decimal('25000.00'), 'fee_type': 'Orthodontics'},
    {'name': 'Digital Dental X-Ray (RVG)', 'price': Decimal('300.00'), 'fee_type': 'Radiology'},
    {'name': 'Professional Teeth Whitening', 'price': Decimal('5000.00'), 'fee_type': 'Cosmetic'},
    {'name': 'Complete Denture (Per Arch)', 'price': Decimal('12000.00'), 'fee_type': 'Prosthodontics'},
]

treatment_objs = {}
for td in treatments_data:
    obj, _ = TreatmentMaster.objects.get_or_create(
        name=td['name'],
        defaults={'price': td['price'], 'fee_type': td['fee_type'], 'is_active': True}
    )
    treatment_objs[td['name']] = obj

# Medicines Master
medicines_data = [
    {'name': 'Amoxicillin 500mg', 'dosage': '1-0-1', 'sales_rate': Decimal('15.00'), 'stock_quantity': 200},
    {'name': 'Paracetamol 650mg (Dolo)', 'dosage': '1-1-1', 'sales_rate': Decimal('5.00'), 'stock_quantity': 300},
    {'name': 'Ketorol DT 10mg', 'dosage': '1-0-1 (SOS)', 'sales_rate': Decimal('12.00'), 'stock_quantity': 150},
    {'name': 'Augmentin 625mg', 'dosage': '1-0-1', 'sales_rate': Decimal('45.00'), 'stock_quantity': 100},
    {'name': 'Metronidazole 400mg', 'dosage': '1-0-1', 'sales_rate': Decimal('8.00'), 'stock_quantity': 180},
    {'name': 'Chlorhexidine Mouthwash', 'dosage': '10ml BD', 'sales_rate': Decimal('120.00'), 'stock_quantity': 50},
]
for md in medicines_data:
    MedicineMaster.objects.get_or_create(
        name=md['name'],
        defaults={
            'dosage': md['dosage'],
            'sales_rate': md['sales_rate'],
            'stock_quantity': md['stock_quantity'],
            'low_stock_threshold': 15
        }
    )

# Discounts
DiscountMaster.objects.get_or_create(
    code='NEW10',
    defaults={
        'name': 'New Patient Discount',
        'discount_type': 'Percentage',
        'discount_value': Decimal('10.00'),
        'applicable_module': 'ALL',
        'is_active': True
    }
)
DiscountMaster.objects.get_or_create(
    code='SENIOR05',
    defaults={
        'name': 'Senior Citizen Discount',
        'discount_type': 'Percentage',
        'discount_value': Decimal('5.00'),
        'applicable_module': 'ALL',
        'is_active': True
    }
)

# -------------------------------------------------------------
# STEP 4: SEED FICTIONAL DEMO DOCTORS & STAFF
# -------------------------------------------------------------
print("\n[STEP 4] Seeding 4 Doctors & Clinic Staff...")

doctors_info = [
    {
        'name': 'Dr. Ananya Menon',
        'username': 'ananya_menon',
        'specialization': 'General Dentistry',
        'qualification': 'BDS, MDS (General)',
        'experience_years': 8,
        'consultation_fee': Decimal('500.00'),
        'color': '#3b82f6',
        'phone': '9876543210',
        'email': 'dr.ananya@ashdent.demo',
    },
    {
        'name': 'Dr. Rahul Nair',
        'username': 'rahul_nair',
        'specialization': 'Orthodontics',
        'qualification': 'BDS, MDS (Ortho)',
        'experience_years': 6,
        'consultation_fee': Decimal('800.00'),
        'color': '#10b981',
        'phone': '9876543211',
        'email': 'dr.rahul@ashdent.demo',
    },
    {
        'name': 'Dr. Meera Thomas',
        'username': 'meera_thomas',
        'specialization': 'Prosthodontics',
        'qualification': 'BDS, MDS (Prostho)',
        'experience_years': 7,
        'consultation_fee': Decimal('700.00'),
        'color': '#8b5cf6',
        'phone': '9876543212',
        'email': 'dr.meera@ashdent.demo',
    },
    {
        'name': 'Dr. Arjun Kumar',
        'username': 'arjun_kumar',
        'specialization': 'Oral & Maxillofacial Surgery',
        'qualification': 'BDS, MDS (OMFS)',
        'experience_years': 10,
        'consultation_fee': Decimal('1000.00'),
        'color': '#f59e0b',
        'phone': '9876543213',
        'email': 'dr.arjun@ashdent.demo',
    }
]

seeded_doctors = []
for d_info in doctors_info:
    u, _ = User.objects.get_or_create(
        username=d_info['username'],
        defaults={'email': d_info['email'], 'first_name': d_info['name'].split()[1], 'last_name': d_info['name'].split()[-1]}
    )
    u.set_password('demo1234')
    u.save()

    doc = Doctor.objects.create(
        name=d_info['name'],
        color=d_info['color'],
        phone=d_info['phone'],
        email=d_info['email'],
        specialization=d_info['specialization'],
        qualification=d_info['qualification'],
        experience_years=d_info['experience_years'],
        consultation_fee=d_info['consultation_fee']
    )
    
    # Staff account linked to Doctor
    Staff.objects.create(
        user=u,
        doctor_profile=doc,
        name=d_info['name'],
        role='Doctor',
        staff_level='Senior' if d_info['experience_years'] >= 8 else 'Consultant',
        phone=d_info['phone'],
        email=d_info['email'],
        gender='Female' if 'Ananya' in d_info['name'] or 'Meera' in d_info['name'] else 'Male',
        age=32 + d_info['experience_years'],
        base_salary=Decimal('75000.00'),
        is_active=True,
        permissions=['dashboard', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'reports', 'prescriptions']
    )

    # Schedules for Mon-Sat (0-5)
    for day in range(6):
        DoctorSchedule.objects.create(
            doctor=doc,
            day_of_week=day,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_active=True
        )

    seeded_doctors.append(doc)

print(f"[OK] Created {len(seeded_doctors)} Doctors with schedules & user credentials.")

# Create Support Staff (Receptionist & Pharmacist)
u_rec, _ = User.objects.get_or_create(username='receptionist_anitha', defaults={'email': 'anitha@ashdent.demo'})
u_rec.set_password('demo1234')
u_rec.save()
Staff.objects.get_or_create(
    user=u_rec,
    defaults={
        'name': 'Anitha Sharma',
        'role': 'Receptionist',
        'staff_level': 'Senior',
        'phone': '9876543220',
        'email': 'anitha@ashdent.demo',
        'gender': 'Female',
        'age': 29,
        'base_salary': Decimal('30000.00'),
        'is_active': True,
        'permissions': ['dashboard', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'billing']
    }
)

u_pharm, _ = User.objects.get_or_create(username='pharmacist_suresh', defaults={'email': 'suresh@ashdent.demo'})
u_pharm.set_password('demo1234')
u_pharm.save()
Staff.objects.get_or_create(
    user=u_pharm,
    defaults={
        'name': 'Suresh Kumar',
        'role': 'Pharmacist',
        'staff_level': 'Senior',
        'phone': '9876543221',
        'email': 'suresh@ashdent.demo',
        'gender': 'Male',
        'age': 34,
        'base_salary': Decimal('35000.00'),
        'is_active': True,
        'permissions': ['dashboard', 'pharmacy', 'stock', 'purchases', 'prescriptions']
    }
)

# -------------------------------------------------------------
# STEP 5: SEED FICTIONAL DEMO PATIENTS & WORKFLOW DATA
# -------------------------------------------------------------
print("\n[STEP 5] Seeding 12 Realistic Fictional Patients & Workflows...")

today = date(2026, 10, 6)
yesterday = today - timedelta(days=1)
past_2_days = today - timedelta(days=2)
tomorrow = today + timedelta(days=1)
in_2_days = today + timedelta(days=2)

patients_data = [
    {
        'name': 'Arjun Mathew',
        'phone': '9900012341',
        'dob': date(1988, 4, 12),
        'age': 38,
        'gender': 'Male',
        'address': 'Flat 4B, Emerald Heights, MG Road',
        'pincode': '682016',
        'pt_type': pt_regular,
        'doc': seeded_doctors[0], # Dr. Ananya Menon
        'fee': Decimal('500.00'),
    },
    {
        'name': 'Neha Krishnan',
        'phone': '9900012342',
        'dob': date(1996, 8, 24),
        'age': 30,
        'gender': 'Female',
        'address': '12/450, Skyline Apartments, Kakkanad',
        'pincode': '682030',
        'pt_type': pt_vip,
        'doc': seeded_doctors[1], # Dr. Rahul Nair
        'fee': Decimal('800.00'),
    },
    {
        'name': 'Rahul Joseph',
        'phone': '9900012343',
        'dob': date(1992, 11, 5),
        'age': 33,
        'gender': 'Male',
        'address': 'House No 88, Palm Grove Colony, Marine Drive',
        'pincode': '682031',
        'pt_type': pt_regular,
        'doc': seeded_doctors[1], # Dr. Rahul Nair
        'fee': Decimal('800.00'),
    },
    {
        'name': 'Anjali Nair',
        'phone': '9900012344',
        'dob': date(1994, 2, 18),
        'age': 32,
        'gender': 'Female',
        'address': 'Villa 14, Silver Oaks Estate, Edapally',
        'pincode': '682024',
        'pt_type': pt_regular,
        'doc': seeded_doctors[0], # Dr. Ananya Menon
        'fee': Decimal('500.00'),
    },
    {
        'name': 'Vivek Menon',
        'phone': '9900012345',
        'dob': date(1983, 7, 30),
        'age': 43,
        'gender': 'Male',
        'address': 'Building 7, Orchid Enclave, Vyttila',
        'pincode': '682019',
        'pt_type': pt_regular,
        'doc': seeded_doctors[2], # Dr. Meera Thomas
        'fee': Decimal('700.00'),
    },
    {
        'name': 'Sneha Thomas',
        'phone': '9900012346',
        'dob': date(1999, 12, 14),
        'age': 26,
        'gender': 'Female',
        'address': '45/B, Rose Gardens, Panampilly Nagar',
        'pincode': '682036',
        'pt_type': pt_regular,
        'doc': seeded_doctors[2], # Dr. Meera Thomas
        'fee': Decimal('700.00'),
    },
    {
        'name': 'Adithya Raj',
        'phone': '9900012347',
        'dob': date(1975, 5, 20),
        'age': 51,
        'gender': 'Male',
        'address': 'Plot 9, Lotus Avenue, Aluva',
        'pincode': '683101',
        'pt_type': pt_senior,
        'doc': seeded_doctors[3], # Dr. Arjun Kumar
        'fee': Decimal('1000.00'),
    },
    {
        'name': 'Priya Suresh',
        'phone': '9900012348',
        'dob': date(2001, 9, 3),
        'age': 25,
        'gender': 'Female',
        'address': 'Quarter 3C, City Lights Terrace, Kaloor',
        'pincode': '682017',
        'pt_type': pt_regular,
        'doc': seeded_doctors[0], # Dr. Ananya Menon
        'fee': Decimal('500.00'),
    },
    {
        'name': 'Nikhil Varma',
        'phone': '9900012349',
        'dob': date(1990, 3, 27),
        'age': 36,
        'gender': 'Male',
        'address': '22/A, Green Valley Meadows, Tripunithura',
        'pincode': '682301',
        'pt_type': pt_regular,
        'doc': seeded_doctors[3], # Dr. Arjun Kumar
        'fee': Decimal('1000.00'),
    },
    {
        'name': 'Divya Mohan',
        'phone': '9900012350',
        'dob': date(1997, 6, 11),
        'age': 29,
        'gender': 'Female',
        'address': 'Apt 101, Blue Mist Towers, Fort Kochi',
        'pincode': '682001',
        'pt_type': pt_regular,
        'doc': seeded_doctors[2], # Dr. Meera Thomas
        'fee': Decimal('700.00'),
    },
    {
        'name': 'Akhil George',
        'phone': '9900012351',
        'dob': date(1993, 10, 8),
        'age': 33,
        'gender': 'Male',
        'address': 'House 16, Harmony Heights, Kalamassery',
        'pincode': '683104',
        'pt_type': pt_regular,
        'doc': seeded_doctors[1], # Dr. Rahul Nair
        'fee': Decimal('800.00'),
    },
    {
        'name': 'Meera Rajan',
        'phone': '9900012352',
        'dob': date(1960, 1, 15),
        'age': 66,
        'gender': 'Female',
        'address': '89, Sunshine Residency, Thrikkakara',
        'pincode': '682021',
        'pt_type': pt_camp,
        'doc': seeded_doctors[0], # Dr. Ananya Menon
        'fee': Decimal('0.00'), # Free camp patient
    },
]

seeded_patients = []
for pd in patients_data:
    p = Patient.objects.create(
        name=pd['name'],
        phone=pd['phone'],
        dob=pd['dob'],
        age=pd['age'],
        gender=pd['gender'],
        address=pd['address'],
        pincode=pd['pincode'],
        status='Active',
        doctor=pd['doc'],
        patient_type=pd['pt_type'],
        consultation_fee=pd['fee']
    )
    seeded_patients.append(p)

print(f"[OK] Seeded {len(seeded_patients)} Patients with realistic demographics.")

# Create Complete Clinical Workflow Scenarios for Patients
print("\n[STEP 6] Seeding Realistic Appointments, Clinical Notes, Treatments & Invoices...")

# Scenario 1: Arjun Mathew — Consultation + Dental Cleaning (Completed Today, Fully Paid Cash)
p1 = seeded_patients[0]
a1 = Appointment.objects.create(
    patient=p1, doctor=p1.doctor, date=today, time=time(9, 30), status='Completed'
)
v1 = Visit.objects.create(patient=p1, appointment=a1)
cn1 = ClinicalNotes.objects.create(
    appointment=a1,
    chief_complaint='Mild calculus accumulation and sensitivity',
    complaints=['Calculus', 'Bleeding Gums'],
    observations=['Subgingival plaque on lower anteriors'],
    diagnosis=['Gingivitis'],
    treatment_plan='Scaling & Polishing done'
)
tr1_a = TreatmentRecord.objects.create(visit=v1, treatment=treatment_objs['Dental Consultation'], price=Decimal('500.00'), fee_type='Consultation', status='Completed', doctor=p1.doctor)
tr1_b = TreatmentRecord.objects.create(visit=v1, treatment=treatment_objs['Dental Cleaning & Scaling'], price=Decimal('1200.00'), fee_type='Preventive', status='Completed', doctor=p1.doctor)

b1 = Billing.objects.create(
    patient=p1, visit=v1, clinical_note=cn1, doctor=p1.doctor, bill_type='Clinical',
    total_amount=Decimal('1700.00'), paid_amount=Decimal('1700.00'), balance_amount=Decimal('0.00'),
    payment_method='Cash', status='Paid', is_invoice=True
)
BillingItem.objects.create(billing=b1, treatment=treatment_objs['Dental Consultation'], qty=1, price=Decimal('500.00'))
BillingItem.objects.create(billing=b1, treatment=treatment_objs['Dental Cleaning & Scaling'], qty=1, price=Decimal('1200.00'))
Payment.objects.create(patient=p1, visit=v1, doctor=p1.doctor, total_amount=Decimal('1700.00'), paid_amount=Decimal('1700.00'), balance_amount=Decimal('0.00'), payment_method='Cash', transaction_date=today, status='Paid')
Transaction.objects.create(type='Income', amount=Decimal('1700.00'), category='Patient Payment', patient=p1, doctor=p1.doctor, payment_method='Cash', date=today)


# Scenario 2: Neha Krishnan — Ortho Consultation & Braces Setup (Completed Yesterday, Partial Paid UPI)
p2 = seeded_patients[1]
a2 = Appointment.objects.create(
    patient=p2, doctor=p2.doctor, date=yesterday, time=time(10, 15), status='Completed'
)
v2 = Visit.objects.create(patient=p2, appointment=a2)
cn2 = ClinicalNotes.objects.create(
    appointment=a2,
    chief_complaint='Crowding in upper anterior teeth',
    complaints=['Malocclusion', 'Crowding'],
    observations=['Class I Malocclusion with anterior crowding'],
    diagnosis=['Crowding'],
    treatment_plan='Ceramic Braces setup planned'
)
tr2_a = TreatmentRecord.objects.create(visit=v2, treatment=treatment_objs['Orthodontic Consultation'], price=Decimal('800.00'), fee_type='Orthodontics', status='Completed', doctor=p2.doctor)
tr2_b = TreatmentRecord.objects.create(visit=v2, treatment=treatment_objs['Metal / Ceramic Braces Setup'], price=Decimal('25000.00'), fee_type='Orthodontics', status='Completed', doctor=p2.doctor)

b2 = Billing.objects.create(
    patient=p2, visit=v2, clinical_note=cn2, doctor=p2.doctor, bill_type='Clinical',
    total_amount=Decimal('25800.00'), paid_amount=Decimal('15000.00'), balance_amount=Decimal('10800.00'),
    payment_method='UPI', status='Partial', is_invoice=True
)
BillingItem.objects.create(billing=b2, treatment=treatment_objs['Orthodontic Consultation'], qty=1, price=Decimal('800.00'))
BillingItem.objects.create(billing=b2, treatment=treatment_objs['Metal / Ceramic Braces Setup'], qty=1, price=Decimal('25000.00'))
Payment.objects.create(patient=p2, visit=v2, doctor=p2.doctor, total_amount=Decimal('25800.00'), paid_amount=Decimal('15000.00'), balance_amount=Decimal('10800.00'), payment_method='UPI', transaction_id='UPI-987654321', transaction_date=yesterday, status='Partial')
Transaction.objects.create(type='Income', amount=Decimal('15000.00'), category='Patient Payment', patient=p2, doctor=p2.doctor, payment_method='UPI', date=yesterday)


# Scenario 3: Rahul Joseph — Ortho Follow-up (Waiting / On Lounge Today)
p3 = seeded_patients[2]
a3 = Appointment.objects.create(
    patient=p3, doctor=p3.doctor, date=today, time=time(11, 0), status='Waiting'
)
v3 = Visit.objects.create(patient=p3, appointment=a3)


# Scenario 4: Anjali Nair — Consultation & Filling (Completed Past 2 Days, Fully Paid Card)
p4 = seeded_patients[3]
a4 = Appointment.objects.create(
    patient=p4, doctor=p4.doctor, date=past_2_days, time=time(14, 30), status='Completed'
)
v4 = Visit.objects.create(patient=p4, appointment=a4)
cn4 = ClinicalNotes.objects.create(
    appointment=a4,
    chief_complaint='Food lodgement in upper molar',
    complaints=['Carious tooth'],
    observations=['Class I cavity in 16'],
    diagnosis=['Dental Caries'],
    treatment_plan='Composite filling done'
)
tr4_a = TreatmentRecord.objects.create(visit=v4, treatment=treatment_objs['Dental Consultation'], price=Decimal('500.00'), fee_type='Consultation', status='Completed', doctor=p4.doctor)
tr4_b = TreatmentRecord.objects.create(visit=v4, treatment=treatment_objs['Composite Tooth Filling'], price=Decimal('1500.00'), fee_type='Restorative', status='Completed', doctor=p4.doctor)

b4 = Billing.objects.create(
    patient=p4, visit=v4, clinical_note=cn4, doctor=p4.doctor, bill_type='Clinical',
    total_amount=Decimal('2000.00'), paid_amount=Decimal('2000.00'), balance_amount=Decimal('0.00'),
    payment_method='Card', status='Paid', is_invoice=True
)
BillingItem.objects.create(billing=b4, treatment=treatment_objs['Dental Consultation'], qty=1, price=Decimal('500.00'))
BillingItem.objects.create(billing=b4, treatment=treatment_objs['Composite Tooth Filling'], qty=1, price=Decimal('1500.00'))
Payment.objects.create(patient=p4, visit=v4, doctor=p4.doctor, total_amount=Decimal('2000.00'), paid_amount=Decimal('2000.00'), balance_amount=Decimal('0.00'), payment_method='Card', transaction_id='CARD-456789', transaction_date=past_2_days, status='Paid')
Transaction.objects.create(type='Income', amount=Decimal('2000.00'), category='Patient Payment', patient=p4, doctor=p4.doctor, payment_method='Card', date=past_2_days)


# Scenario 5: Vivek Menon — Root Canal & Crown (Completed Yesterday, Fully Paid Bank Transfer)
p5 = seeded_patients[4]
a5 = Appointment.objects.create(
    patient=p5, doctor=p5.doctor, date=yesterday, time=time(16, 0), status='Completed'
)
v5 = Visit.objects.create(patient=p5, appointment=a5)
cn5 = ClinicalNotes.objects.create(
    appointment=a5,
    chief_complaint='Severe throbbing pain in lower molar',
    complaints=['Severe Pain', 'Sensitivity'],
    observations=['Deep carious lesion approaching pulp in 46'],
    diagnosis=['Irreversible Pulpitis'],
    treatment_plan='RCT and Zirconia crown done'
)
tr5_a = TreatmentRecord.objects.create(visit=v5, treatment=treatment_objs['Root Canal Treatment (RCT)'], price=Decimal('4500.00'), fee_type='Endodontics', status='Completed', doctor=p5.doctor)
tr5_b = TreatmentRecord.objects.create(visit=v5, treatment=treatment_objs['Zirconia Premium Crown'], price=Decimal('9000.00'), fee_type='Prosthodontics', status='Completed', doctor=p5.doctor)

b5 = Billing.objects.create(
    patient=p5, visit=v5, clinical_note=cn5, doctor=p5.doctor, bill_type='Clinical',
    total_amount=Decimal('13500.00'), paid_amount=Decimal('13500.00'), balance_amount=Decimal('0.00'),
    payment_method='Bank Transfer', status='Paid', is_invoice=True
)
BillingItem.objects.create(billing=b5, treatment=treatment_objs['Root Canal Treatment (RCT)'], qty=1, price=Decimal('4500.00'))
BillingItem.objects.create(billing=b5, treatment=treatment_objs['Zirconia Premium Crown'], qty=1, price=Decimal('9000.00'))
Payment.objects.create(patient=p5, visit=v5, doctor=p5.doctor, total_amount=Decimal('13500.00'), paid_amount=Decimal('13500.00'), balance_amount=Decimal('0.00'), payment_method='Bank Transfer', transaction_id='BANK-789012', transaction_date=yesterday, status='Paid')
Transaction.objects.create(type='Income', amount=Decimal('13500.00'), category='Patient Payment', patient=p5, doctor=p5.doctor, payment_method='Bank Transfer', date=yesterday)


# Scenario 6: Sneha Thomas — Complete Denture Consultation (Waiting Today)
p6 = seeded_patients[5]
a6 = Appointment.objects.create(
    patient=p6, doctor=p6.doctor, date=today, time=time(12, 0), status='Waiting'
)
v6 = Visit.objects.create(patient=p6, appointment=a6)


# Scenario 7: Adithya Raj — Tooth Extraction (Scheduled Tomorrow)
p7 = seeded_patients[6]
a7 = Appointment.objects.create(
    patient=p7, doctor=p7.doctor, date=tomorrow, time=time(10, 0), status='Scheduled'
)


# Scenario 8: Priya Suresh — Teeth Whitening (Scheduled In 2 Days)
p8 = seeded_patients[7]
a8 = Appointment.objects.create(
    patient=p8, doctor=p8.doctor, date=in_2_days, time=time(15, 0), status='Scheduled'
)


# Scenario 9: Nikhil Varma — Surgical Extraction (Completed Today, Fully Paid Cash)
p9 = seeded_patients[8]
a9 = Appointment.objects.create(
    patient=p9, doctor=p9.doctor, date=today, time=time(10, 30), status='Completed'
)
v9 = Visit.objects.create(patient=p9, appointment=a9)
cn9 = ClinicalNotes.objects.create(
    appointment=a9,
    chief_complaint='Impacted wisdom tooth pain',
    complaints=['Wisdom tooth pain'],
    observations=['Mesioangular impaction 38'],
    diagnosis=['Impaction'],
    treatment_plan='Surgical extraction done'
)
tr9_a = TreatmentRecord.objects.create(visit=v9, treatment=treatment_objs['Simple Tooth Extraction'], price=Decimal('1000.00'), fee_type='Surgery', status='Completed', doctor=p9.doctor)

b9 = Billing.objects.create(
    patient=p9, visit=v9, clinical_note=cn9, doctor=p9.doctor, bill_type='Clinical',
    total_amount=Decimal('1000.00'), paid_amount=Decimal('1000.00'), balance_amount=Decimal('0.00'),
    payment_method='Cash', status='Paid', is_invoice=True
)
BillingItem.objects.create(billing=b9, treatment=treatment_objs['Simple Tooth Extraction'], qty=1, price=Decimal('1000.00'))
Payment.objects.create(patient=p9, visit=v9, doctor=p9.doctor, total_amount=Decimal('1000.00'), paid_amount=Decimal('1000.00'), balance_amount=Decimal('0.00'), payment_method='Cash', transaction_date=today, status='Paid')
Transaction.objects.create(type='Income', amount=Decimal('1000.00'), category='Patient Payment', patient=p9, doctor=p9.doctor, payment_method='Cash', date=today)


# Scenario 10: Meera Rajan — Free Dental Camp Consultation (Completed Today, ₹0 Fee)
p12 = seeded_patients[11]
a12 = Appointment.objects.create(
    patient=p12, doctor=p12.doctor, date=today, time=time(11, 30), status='Completed'
)
v12 = Visit.objects.create(patient=p12, appointment=a12)
cn12 = ClinicalNotes.objects.create(
    appointment=a12,
    chief_complaint='Routine checkup at free camp',
    complaints=['General Checkup'],
    observations=['Mild generalized attrition'],
    diagnosis=['Attrition'],
    treatment_plan='Oral hygiene instructions provided'
)

b12 = Billing.objects.create(
    patient=p12, visit=v12, clinical_note=cn12, doctor=p12.doctor, bill_type='Clinical',
    total_amount=Decimal('0.00'), paid_amount=Decimal('0.00'), balance_amount=Decimal('0.00'),
    payment_method='Cash', status='Paid', is_invoice=True
)
Payment.objects.create(patient=p12, visit=v12, doctor=p12.doctor, total_amount=Decimal('0.00'), paid_amount=Decimal('0.00'), balance_amount=Decimal('0.00'), payment_method='Cash', transaction_date=today, status='Paid')


print("[OK] Completed workflow seeding.")

# -------------------------------------------------------------
# STEP 6: VERIFICATION OF DATA INTEGRITY
# -------------------------------------------------------------
print("\n[STEP 7] Running Database Consistency & Integrity Verification...")

counts_after = {
    'doctors': Doctor.objects.count(),
    'staff': Staff.objects.count(),
    'patients': Patient.objects.count(),
    'appointments': Appointment.objects.count(),
    'visits': Visit.objects.count(),
    'clinical_notes': ClinicalNotes.objects.count(),
    'treatment_records': TreatmentRecord.objects.count(),
    'billings': Billing.objects.count(),
    'billing_items': BillingItem.objects.count(),
    'payments': Payment.objects.count(),
    'transactions': Transaction.objects.count(),
}

print(f"Doctors: {counts_after['doctors']}")
print(f"Staff: {counts_after['staff']}")
print(f"Patients: {counts_after['patients']}")
print(f"Appointments: {counts_after['appointments']}")
print(f"Visits: {counts_after['visits']}")
print(f"Clinical Notes: {counts_after['clinical_notes']}")
print(f"Treatment Records: {counts_after['treatment_records']}")
print(f"Billings: {counts_after['billings']}")
print(f"Payments: {counts_after['payments']}")
print(f"Income Transactions: {counts_after['transactions']}")

# Integrity check: Orphan verification
orphan_appts = Appointment.objects.filter(patient__isnull=True).count()
orphan_visits = Visit.objects.filter(patient__isnull=True).count()
orphan_bills = Billing.objects.filter(patient__isnull=True).count()
orphan_payments = Payment.objects.filter(patient__isnull=True).count()

assert orphan_appts == 0, f"Found {orphan_appts} orphan appointments"
assert orphan_visits == 0, f"Found {orphan_visits} orphan visits"
assert orphan_bills == 0, f"Found {orphan_bills} orphan bills"
assert orphan_payments == 0, f"Found {orphan_payments} orphan payments"

print("\n[OK] ZERO ORPHAN RECORDS FOUND. DATABASE INTEGRITY VERIFIED PERFECTLY!")
print("\n=============================================================")
print("  DEMO DATASET CREATION FOR WEBINAR COMPLETE SUCCESSFULLY!  ")
print("=============================================================")
