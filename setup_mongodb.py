# -*- coding: utf-8 -*-
"""
=======================================================
  DENTAL CLINIC - MONGODB MASTER SETUP SCRIPT
  Run this once to:
    1. Apply all migrations
    2. Create admin superuser
    3. Seed Doctors, Patients, Appointments
    4. Seed Dropdown options (clinical)
    5. Seed Medicines & Treatment Master
    6. Seed Communication Templates & Tax Settings
=======================================================
Usage:
    cd backend
    python setup_mongodb.py
"""

import os
import sys
import django
from datetime import date, time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

# ---- 0. Run Migrations -------------------------------------------------------
print("\n[1/7] Running migrations...")
from django.core.management import call_command
try:
    call_command('migrate', '--run-syncdb', verbosity=0)
    print("      [OK] Migrations done.")
except Exception as e:
    print("      [NOTE] Migration step: " + str(e))

# ---- 1. Create Admin User ----------------------------------------------------
print("\n[2/7] Creating admin user...")
from django.contrib.auth.models import User
from patients.models import Staff

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'
ADMIN_NAME     = 'Dr. Navas Kp'

try:
    if not User.objects.filter(username=ADMIN_USERNAME).exists():
        user = User.objects.create_superuser(
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            first_name=ADMIN_NAME,
            email='admin@dentalclinic.com'
        )
        if not Staff.objects.filter(name=ADMIN_NAME).exists():
            Staff.objects.create(user=user, name=ADMIN_NAME, role='Admin', phone='9876543210')
        print("      [CREATED] Admin user  ->  username: '" + ADMIN_USERNAME + "'  |  password: '" + ADMIN_PASSWORD + "'")
    else:
        print("      [EXISTS] Admin '" + ADMIN_USERNAME + "' already exists - skipped.")
except Exception as e:
    print("      [ERROR] Admin creation failed: " + str(e))

# ---- 2. Seed Doctors ---------------------------------------------------------
print("\n[3/7] Seeding doctors...")
from patients.models import Doctor

doctors_data = [
    {'name': 'Dr. Navas Kp',   'color': '#3498db', 'specialization': 'General Dentist',  'consultation_fee': 500},
    {'name': 'Dr. Priya Nair', 'color': '#e74c3c', 'specialization': 'Orthodontist',      'consultation_fee': 700},
    {'name': 'Dr. Arjun Das',  'color': '#2ecc71', 'specialization': 'Oral Surgeon',      'consultation_fee': 800},
]

created_doctors = []
for d in doctors_data:
    obj, created = Doctor.objects.get_or_create(
        name=d['name'],
        defaults={
            'color': d['color'],
            'specialization': d['specialization'],
            'consultation_fee': d['consultation_fee'],
        }
    )
    created_doctors.append(obj)
    tag = '[CREATED]' if created else '[EXISTS] '
    print("      " + tag + " " + d['name'])

# ---- 3. Seed Patients --------------------------------------------------------
print("\n[4/7] Seeding patients...")
from patients.models import Patient

patients_data = [
    {'name': 'Arjun Menon',    'phone': '9876543210', 'dob': date(1992, 4, 15),  'gender': 'Male',   'age': 33},
    {'name': 'Priya Krishnan', 'phone': '9123456789', 'dob': date(1988, 9, 22),  'gender': 'Female', 'age': 37},
    {'name': 'Rahul Kumar',    'phone': '9988776655', 'dob': date(1995, 12, 1),  'gender': 'Male',   'age': 30},
    {'name': 'Lakshmi Devi',   'phone': '9871234560', 'dob': date(1975, 3, 8),   'gender': 'Female', 'age': 51},
    {'name': 'Mohammed Rafiq', 'phone': '9765432109', 'dob': date(2000, 7, 19),  'gender': 'Male',   'age': 25},
]

created_patients = []
for p in patients_data:
    obj, created = Patient.objects.get_or_create(
        phone=p['phone'],
        defaults={
            'name':   p['name'],
            'dob':    p['dob'],
            'gender': p['gender'],
            'age':    p['age'],
            'status': 'Active',
        }
    )
    created_patients.append(obj)
    tag = '[CREATED]' if created else '[EXISTS] '
    print("      " + tag + " " + p['name'] + " (" + p['phone'] + ")")

# ---- 4. Seed Appointments ----------------------------------------------------
print("\n[5/7] Seeding appointments...")
from patients.models import Appointment

today = date.today()

appointments_data = [
    {'patient': created_patients[0], 'doctor': created_doctors[0], 'time': time(9, 0),  'status': 'Scheduled'},
    {'patient': created_patients[1], 'doctor': created_doctors[0], 'time': time(10, 0), 'status': 'Waiting'},
    {'patient': created_patients[2], 'doctor': created_doctors[1], 'time': time(11, 0), 'status': 'Engaged'},
    {'patient': created_patients[3], 'doctor': created_doctors[1], 'time': time(12, 0), 'status': 'Completed'},
    {'patient': created_patients[4], 'doctor': created_doctors[2], 'time': time(14, 0), 'status': 'Scheduled'},
]

for a in appointments_data:
    exists = Appointment.objects.filter(patient=a['patient'], date=today, time=a['time']).exists()
    if not exists:
        Appointment.objects.create(
            patient=a['patient'],
            doctor=a['doctor'],
            date=today,
            time=a['time'],
            status=a['status'],
        )
        print("      [CREATED] " + a['patient'].name + " @ " + str(a['time']) + " [" + a['status'] + "]")
    else:
        print("      [EXISTS]  " + a['patient'].name + " @ " + str(a['time']))

# ---- 5. Seed Dropdown Options ------------------------------------------------
print("\n[6/7] Seeding dropdown options...")
from patients.models import DropdownMaster

DROPDOWN_DATA = {
    'complaint': [
        'Toothache / Severe Pain', 'Sensitivity to Cold/Hot', 'Swelling in Gums',
        'Bleeding during Brushing', 'Broken / Chipped Tooth', 'Loose Tooth',
        'Missing Tooth / Gap', 'Yellow / Stained Teeth', 'Bad Breath',
        'Food Lodgement / Gaps', 'Decayed Tooth / Hole', 'Wisdom Tooth Pain',
        'Bleeding Gums', 'Difficulty in Chewing',
    ],
    'observation': [
        'Deep Occlusal Caries', 'Proximal Caries', 'Pulp Exposure Seen',
        'Gingival Inflammation', 'Grade I Mobility', 'Grade II Mobility',
        'Fractured Crown Portion', 'Periapical Abscess', 'Impacted 3rd Molar',
        'Supra-gingival Calculus', 'Root Piece Present', 'Gingival Recession',
    ],
    'diagnosis': [
        'Acute Irreversible Pulpitis', 'Chronic Irreversible Pulpitis', 'Reversible Pulpitis',
        'Acute Periapical Periodontitis', 'Chronic Generalized Periodontitis',
        'Dental Caries (Class I/II/III/IV/V)', 'Impacted / Mesioangular Tooth',
        'Gingivitis', 'Pericoronitis', 'Alveolar Bone Loss', 'Root Canal Failure',
    ],
    'investigation': [
        'IOPA X-Ray', 'Bitewing X-Ray', 'OPG (Full Mouth X-Ray)', 'CBCT Scan',
        'Blood Glucose (PP/Fasting)', 'Blood Count (CBC)', 'Pulp Vitality Test',
    ],
    'treatment': [
        'Root Canal Treatment (RCT)', 'Simple Extraction', 'Surgical Extraction',
        'Scaling & Polishing', 'Deep Scaling / Currettage', 'Composite Filling',
        'GIC Restoration', 'Dental Bridge (3 Unit)', 'Dental Implant',
        'PFM Crown', 'Zirconia Crown', 'Orthodontic Braces', 'Complete Denture',
        'Partial Denture', 'Bleaching / Whitening',
    ],
    'medical_history': [
        'Diabetes Mellitus', 'Hypertension (High BP)', 'Thyroid Disorder',
        'Asthma / Respiratory Issues', 'Pregnancy', 'Heart Valve Issue',
        'Bleeding Disorder', 'Epilepsy / Fits', 'Drug Allergy (Penicillin)',
        'Drug Allergy (Sulfa)', 'History of Surgery', 'Osteoporosis',
    ],
    'payment_method': ['Cash', 'Card', 'UPI', 'Cheque', 'Insurance', 'Online'],
}

dd_count = 0
for d_type, names in DROPDOWN_DATA.items():
    for name in names:
        _, created = DropdownMaster.objects.get_or_create(type=d_type, name=name)
        if created:
            dd_count += 1

print("      [OK] " + str(dd_count) + " new dropdown items added.")

# ---- 6. Seed Medicines, Treatments, Templates, Taxes ------------------------
print("\n[7/7] Seeding medicines, treatments, templates & taxes...")
from patients.models import MedicineMaster, TreatmentMaster, CommunicationTemplate, TaxSetting

medicines = [
    {'name': 'Paracetamol',   'dosage': '500mg', 'frequency': '1-0-1', 'notes': 'After food'},
    {'name': 'Amoxicillin',   'dosage': '500mg', 'frequency': '1-1-1', 'notes': 'Antibiotic'},
    {'name': 'Ibuprofen',     'dosage': '400mg', 'frequency': '1-0-1', 'notes': 'Painkiller'},
    {'name': 'Metronidazole', 'dosage': '400mg', 'frequency': '1-1-1', 'notes': 'For infection'},
    {'name': 'Augmentin',     'dosage': '625mg', 'frequency': '1-0-1', 'notes': 'Potent antibiotic'},
    {'name': 'Ondansetron',   'dosage': '4mg',   'frequency': '1-0-1', 'notes': 'For nausea'},
    {'name': 'Pantoprazole',  'dosage': '40mg',  'frequency': '1-0-0', 'notes': 'Before food'},
    {'name': 'Diclofenac',    'dosage': '50mg',  'frequency': '1-0-1', 'notes': 'Strong painkiller'},
    {'name': 'Cetirizine',    'dosage': '10mg',  'frequency': '0-0-1', 'notes': 'For allergy'},
]
med_count = 0
for m in medicines:
    _, created = MedicineMaster.objects.get_or_create(
        name=m['name'],
        defaults={'dosage': m['dosage'], 'frequency': m['frequency'], 'notes': m['notes']}
    )
    if created:
        med_count += 1
print("      [OK] " + str(med_count) + " new medicines added.")

treatments = [
    {'name': 'Consultation',          'price': 300,   'fee_type': 'Consultation'},
    {'name': 'Root Canal Treatment',  'price': 4000,  'fee_type': 'Treatment'},
    {'name': 'Simple Extraction',     'price': 500,   'fee_type': 'Treatment'},
    {'name': 'Surgical Extraction',   'price': 1500,  'fee_type': 'Treatment'},
    {'name': 'Scaling & Polishing',   'price': 800,   'fee_type': 'Treatment'},
    {'name': 'Composite Filling',     'price': 1000,  'fee_type': 'Treatment'},
    {'name': 'GIC Restoration',       'price': 600,   'fee_type': 'Treatment'},
    {'name': 'PFM Crown',             'price': 5000,  'fee_type': 'Prosthetics'},
    {'name': 'Zirconia Crown',        'price': 8000,  'fee_type': 'Prosthetics'},
    {'name': 'Dental Implant',        'price': 25000, 'fee_type': 'Prosthetics'},
    {'name': 'Complete Denture',      'price': 12000, 'fee_type': 'Prosthetics'},
    {'name': 'Orthodontic Braces',    'price': 20000, 'fee_type': 'Orthodontics'},
    {'name': 'IOPA X-Ray',            'price': 200,   'fee_type': 'X-Ray'},
    {'name': 'OPG Full Mouth X-Ray',  'price': 700,   'fee_type': 'X-Ray'},
    {'name': 'Bleaching / Whitening', 'price': 5000,  'fee_type': 'Cosmetic'},
]
treat_count = 0
for t in treatments:
    _, created = TreatmentMaster.objects.get_or_create(
        name=t['name'],
        defaults={'price': t['price'], 'fee_type': t['fee_type']}
    )
    if created:
        treat_count += 1
print("      [OK] " + str(treat_count) + " new treatments added.")

templates = [
    {'category': 'Appointment', 'type': 'Confirmation',
     'text': 'Dear {patient}, your appointment with {doctor} is confirmed for {date} at {time}. Clinic: {clinic}'},
    {'category': 'Follow-up',   'type': 'Reminder',
     'text': 'Dear {patient}, reminder for your follow-up on {date} at {time}. Thank you, {clinic}.'},
    {'category': 'Billing',     'type': 'Payment Receipt',
     'text': 'Dear {patient}, payment received. Thank you! - {clinic}'},
    {'category': 'Greeting',    'type': 'Welcome',
     'text': 'Welcome to {clinic}, {patient}! Looking forward to giving you a perfect smile.'},
]
t_count = 0
for t in templates:
    _, created = CommunicationTemplate.objects.get_or_create(
        category=t['category'], type=t['type'], defaults={'text': t['text']}
    )
    if created:
        t_count += 1
print("      [OK] " + str(t_count) + " new communication templates added.")

taxes = [
    {'name': 'GST 5%',  'rate': 5.00},
    {'name': 'GST 12%', 'rate': 12.00},
    {'name': 'GST 18%', 'rate': 18.00},
]
tax_count = 0
for tx in taxes:
    _, created = TaxSetting.objects.get_or_create(name=tx['name'], defaults={'rate': tx['rate']})
    if created:
        tax_count += 1
print("      [OK] " + str(tax_count) + " new tax settings added.")

# ---- Done --------------------------------------------------------------------
print("\n" + "="*55)
print("  SETUP COMPLETE!")
print("="*55)
print("  Admin Login  ->  username : " + ADMIN_USERNAME)
print("               ->  password : " + ADMIN_PASSWORD)
print("  Django Admin ->  http://127.0.0.1:8000/admin/")
print("="*55 + "\n")
