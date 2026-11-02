import os
import sys
import json
import django
from datetime import date, datetime, time, timedelta
from decimal import Decimal

# Set up Django environment using project path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.utils import timezone
from django.db import connections
from django.contrib.auth.models import User
from bson import ObjectId

from patients.models import (
    Doctor, DoctorSchedule, Staff, PatientGroup, Patient, Appointment,
    ToothMaster, TreatmentMaster, Visit, ClinicalNotes, TreatmentRecord,
    Payment, Billing, BillingItem, Prescription, PrescriptionItem,
    MedicineMaster, Transaction, PatientTypeMaster, StaffLevelMaster,
    DesignationMaster, RoleMaster, PermissionMaster, DiscountMaster, OfferPackage,
    OfferPackageItem, TaxSetting, ClinicProfile, ClinicTiming, AutoNumbering,
    PharmacySettings, PatientLabOrder, PreBooking, ExpenseCategory, Expense,
    DentalLaboratory, DentalLabWork, Supplier
)

print("=" * 70)
print("  ASHDENT DENTAL HMS — LIVE WEBINAR DEMO DATASET GENERATOR")
print("=" * 70)

# -----------------------------------------------------------------------------
# STEP 1: SAFETY BACKUP OF TRANSACTIONAL DATA
# -----------------------------------------------------------------------------
backup_dir = os.path.join(BASE_DIR, 'patients', 'scratch')
os.makedirs(backup_dir, exist_ok=True)
backup_file = os.path.join(backup_dir, 'webinar_preseed_backup.json')

print(f"\n[STEP 1] Creating pre-seed safety backup to {backup_file}...")
try:
    backup_data = {
        'patients_count': Patient.objects.count(),
        'appointments_count': Appointment.objects.count(),
        'billings_count': Billing.objects.count(),
        'payments_count': Payment.objects.count(),
    }
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=2)
    print("  [OK] Pre-seed backup recorded.")
except Exception as e:
    print(f"  [WARN] Backup write error (non-fatal): {e}")


# -----------------------------------------------------------------------------
# STEP 2: CLEANUP OF TEST & ORPHAN RECORDS (PRESERVING CORE ADMIN/CONFIG)
# -----------------------------------------------------------------------------
print("\n[STEP 2] Purging test data & synthetic artifacts...")

db = connections['default'].database

# 1. Purge test patients (and everything associated)
test_patient_names = [
    'Synthetic Patient Alpha', 'Synthetic Patient Beta', 'Dev Audit Patient',
    'Audit Patient Test', 'Test Audit Patient', 'Test Patient A', 'Test Patient B',
    'Patient 01', 'patient 02', 'gokul Gopinath', 'GoKul Gopinath', 'Gayathri sunil'
]
Patient.objects.filter(name__in=test_patient_names).delete()
Patient.objects.filter(name__icontains='Test').delete()
Patient.objects.filter(name__icontains='Audit').delete()

# 2. Purge test doctors and test staff accounts
test_doc_names = [
    'Dr. Harshad Test', 'Dr. Audit Test 19542', 'Dr. Audit Test 85956',
    'Dr. Audit Test 98331', 'Dr. Verification Doctor', 'Dr. Test Audit',
    'Smith SlotTest', 'Jane Doe Test', 'Dr Devika', 'Dr arya'
]
Doctor.objects.filter(name__in=test_doc_names).delete()
Doctor.objects.filter(name__icontains='Test').delete()
Doctor.objects.filter(name__icontains='Audit').delete()

Staff.objects.filter(name__icontains='Test').delete()
Staff.objects.filter(name__icontains='Audit').delete()
Staff.objects.filter(name__in=['Dr Devika', 'Dr arya', 'Staff Without Optional Fields', 'Dr. Smith SlotTest', 'Dr. Jane Doe Test']).delete()

# Purge leftover synthetic transactional data to prevent orphan cards
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

print("  [OK] Cleaned database ready for pristine webinar dataset.")


# -----------------------------------------------------------------------------
# STEP 3: CONFIGURE CLINIC PROFILE FOR PREMIER DEMONSTRATION
# -----------------------------------------------------------------------------
print("\n[STEP 3] Updating Clinic Profile for webinar presentation...")

clinic, _ = ClinicProfile.objects.get_or_create(id=ClinicProfile.objects.first().id if ClinicProfile.objects.exists() else None)
clinic.name = "AshDent Advanced Dental & Implant Center"
clinic.specialization = "Multispeciality Dental Hospital & Digital Implantology Center"
clinic.slogan = "Precision Care for Every Smile"
clinic.phone = "+91 484 280 4500"
clinic.mobile = "+91 98470 12345"
clinic.email = "care@ashdent.demo"
clinic.website = "www.ashdent.demo"
clinic.address = "Level 3, Premier Healthcare Arcade, MG Road"
clinic.city = "Kochi"
clinic.state = "Kerala"
clinic.zip_code = "682016"
clinic.country = "India"
clinic.default_currency = "INR"
clinic.save()
print(f"  [OK] Clinic Profile: {clinic.name} ({clinic.city})")


# -----------------------------------------------------------------------------
# STEP 4: PATIENT TYPES, TREATMENTS & PHARMACY MASTERS
# -----------------------------------------------------------------------------
print("\n[STEP 4] Configuring Clinical Masters & Medicine Inventory...")

pt_regular, _ = PatientTypeMaster.objects.get_or_create(code='REGULAR', defaults={'name': 'Regular Patient', 'display_order': 1})
pt_vip, _ = PatientTypeMaster.objects.get_or_create(code='VIP', defaults={'name': 'VIP / Executive', 'display_order': 2})
pt_senior, _ = PatientTypeMaster.objects.get_or_create(code='SENIOR', defaults={'name': 'Senior Citizen', 'display_order': 3})
pt_camp, _ = PatientTypeMaster.objects.get_or_create(code='CAMP', defaults={'name': 'Free Community Camp', 'display_order': 4})

treatments_catalog = [
    {'name': 'Dental Consultation', 'price': Decimal('500.00'), 'fee_type': 'Consultation'},
    {'name': 'Dental Cleaning & Scaling', 'price': Decimal('1200.00'), 'fee_type': 'Preventive'},
    {'name': 'Deep Periodontal Curettage', 'price': Decimal('2500.00'), 'fee_type': 'Periodontics'},
    {'name': 'Composite Tooth Filling', 'price': Decimal('1500.00'), 'fee_type': 'Restorative'},
    {'name': 'Root Canal Treatment (RCT)', 'price': Decimal('4500.00'), 'fee_type': 'Endodontics'},
    {'name': 'RCT Re-treatment / Post & Core', 'price': Decimal('5500.00'), 'fee_type': 'Endodontics'},
    {'name': 'Porcelain / E-Max Crown', 'price': Decimal('6000.00'), 'fee_type': 'Prosthodontics'},
    {'name': 'Zirconia Premium Crown', 'price': Decimal('9000.00'), 'fee_type': 'Prosthodontics'},
    {'name': 'Simple Tooth Extraction', 'price': Decimal('1000.00'), 'fee_type': 'Surgery'},
    {'name': 'Surgical / Wisdom Tooth Extraction', 'price': Decimal('4000.00'), 'fee_type': 'Surgery'},
    {'name': 'Orthodontic Consultation', 'price': Decimal('800.00'), 'fee_type': 'Orthodontics'},
    {'name': 'Metal / Ceramic Braces Setup', 'price': Decimal('25000.00'), 'fee_type': 'Orthodontics'},
    {'name': 'Digital Dental X-Ray (RVG)', 'price': Decimal('300.00'), 'fee_type': 'Radiology'},
    {'name': 'Professional Teeth Whitening', 'price': Decimal('6000.00'), 'fee_type': 'Cosmetic'},
    {'name': 'Complete Denture (Per Arch)', 'price': Decimal('12000.00'), 'fee_type': 'Prosthodontics'},
]

tx_map = {}
for td in treatments_catalog:
    obj, _ = TreatmentMaster.objects.get_or_create(
        name=td['name'],
        defaults={'price': td['price'], 'fee_type': td['fee_type'], 'is_active': True}
    )
    obj.price = td['price']
    obj.fee_type = td['fee_type']
    obj.is_active = True
    obj.save()
    tx_map[td['name']] = obj

# Pharmacy: 8 Core In-Stock medicines + 1 Low-Stock Item to demonstrate alerts
medicines_catalog = [
    {'name': 'Amoxicillin 500mg', 'dosage': '1-0-1 (After Food)', 'frequency': 'Twice Daily', 'purchase_rate': Decimal('9.00'), 'sales_rate': Decimal('15.00'), 'stock': 180, 'low': 20},
    {'name': 'Augmentin 625mg', 'dosage': '1-0-1 (After Food)', 'frequency': 'Twice Daily', 'purchase_rate': Decimal('32.00'), 'sales_rate': Decimal('45.00'), 'stock': 95, 'low': 15},
    {'name': 'Paracetamol 650mg (Dolo)', 'dosage': '1-1-1 (SOS)', 'frequency': 'Thrice Daily', 'purchase_rate': Decimal('2.50'), 'sales_rate': Decimal('5.00'), 'stock': 260, 'low': 30},
    {'name': 'Ketorol DT 10mg', 'dosage': '1-0-1 (Dispersible SOS)', 'frequency': 'As Needed', 'purchase_rate': Decimal('7.00'), 'sales_rate': Decimal('12.00'), 'stock': 140, 'low': 20},
    {'name': 'Metronidazole 400mg', 'dosage': '1-0-1 (After Food)', 'frequency': 'Twice Daily', 'purchase_rate': Decimal('4.00'), 'sales_rate': Decimal('8.00'), 'stock': 110, 'low': 15},
    {'name': 'Chlorhexidine Mouthwash 0.2%', 'dosage': '10ml rinse for 30s BD', 'frequency': 'Twice Daily', 'purchase_rate': Decimal('80.00'), 'sales_rate': Decimal('120.00'), 'stock': 50, 'low': 10},
    {'name': 'Mucopain Gel 15g', 'dosage': 'Apply topically before meals', 'frequency': 'Before Food', 'purchase_rate': Decimal('55.00'), 'sales_rate': Decimal('90.00'), 'stock': 35, 'low': 10},
    {'name': 'Pantoprazole 40mg (Pan 40)', 'dosage': '1-0-0 (Empty Stomach)', 'frequency': 'Morning', 'purchase_rate': Decimal('6.00'), 'sales_rate': Decimal('10.00'), 'stock': 150, 'low': 20},
    # LOW STOCK TRIGGER ITEM
    {'name': 'Ciprofloxacin Dental Drops', 'dosage': '2 drops BD', 'frequency': 'Twice Daily', 'purchase_rate': Decimal('40.00'), 'sales_rate': Decimal('65.00'), 'stock': 4, 'low': 15},
]

for med in medicines_catalog:
    m_obj, _ = MedicineMaster.objects.get_or_create(
        name=med['name'],
        defaults={
            'dosage': med['dosage'],
            'frequency': med['frequency'],
            'purchase_rate': med['purchase_rate'],
            'sales_rate': med['sales_rate'],
            'stock_quantity': med['stock'],
            'low_stock_threshold': med['low'],
            'is_active': True
        }
    )
    m_obj.dosage = med['dosage']
    m_obj.frequency = med['frequency']
    m_obj.purchase_rate = med['purchase_rate']
    m_obj.sales_rate = med['sales_rate']
    m_obj.stock_quantity = med['stock']
    m_obj.low_stock_threshold = med['low']
    m_obj.is_active = True
    m_obj.save()

print(f"  [OK] Master catalog configured with {len(tx_map)} treatments and {len(medicines_catalog)} pharmacy medicines.")


# -----------------------------------------------------------------------------
# STEP 5: SEED 4 DOCTORS & CLINICAL STAFF
# -----------------------------------------------------------------------------
print("\n[STEP 5] Setting up 4 Specialists & Support Staff...")

doctors_config = [
    {
        'name': 'Dr. Ananya Menon',
        'username': 'dr_ananya',
        'specialization': 'General Dentistry',
        'qualification': 'BDS, MDS (General Dentistry)',
        'experience_years': 8,
        'consultation_fee': Decimal('500.00'),
        'color': '#3b82f6', # Blue
        'phone': '9847011001',
        'email': 'dr.ananya@ashdent.demo'
    },
    {
        'name': 'Dr. Rahul Nair',
        'username': 'dr_rahul',
        'specialization': 'Orthodontics & Dentofacial Orthopedics',
        'qualification': 'BDS, MDS (Orthodontics)',
        'experience_years': 7,
        'consultation_fee': Decimal('800.00'),
        'color': '#10b981', # Emerald Green
        'phone': '9847011002',
        'email': 'dr.rahul@ashdent.demo'
    },
    {
        'name': 'Dr. Meera Thomas',
        'username': 'dr_meera',
        'specialization': 'Prosthodontics & Implantology',
        'qualification': 'BDS, MDS (Prosthodontics)',
        'experience_years': 9,
        'consultation_fee': Decimal('700.00'),
        'color': '#8b5cf6', # Purple
        'phone': '9847011003',
        'email': 'dr.meera@ashdent.demo'
    },
    {
        'name': 'Dr. Arjun Kumar',
        'username': 'dr_arjun',
        'specialization': 'Oral & Maxillofacial Surgery',
        'qualification': 'BDS, MDS (OMFS)',
        'experience_years': 11,
        'consultation_fee': Decimal('1000.00'),
        'color': '#f59e0b', # Amber
        'phone': '9847011004',
        'email': 'dr.arjun@ashdent.demo'
    }
]

seeded_docs = []
DoctorSchedule.objects.all().delete()
Staff.objects.all().delete()
Doctor.objects.all().delete()

def get_or_clean_user(username, email, first_name='', last_name=''):
    db['auth_user'].delete_many({'username': username})
    user = User.objects.create_user(
        username=username,
        email=email,
        password='demo1234',
        first_name=first_name,
        last_name=last_name
    )
    user.is_staff = True
    user.save()
    return user

for d in doctors_config:
    u = get_or_clean_user(
        d['username'],
        d['email'],
        d['name'].split()[1],
        d['name'].split()[-1]
    )

    doc = Doctor.objects.create(
        name=d['name'],
        color=d['color'],
        phone=d['phone'],
        email=d['email'],
        specialization=d['specialization'],
        qualification=d['qualification'],
        experience_years=d['experience_years'],
        consultation_fee=d['consultation_fee']
    )

    Staff.objects.create(
        user=u,
        doctor_profile=doc,
        name=d['name'],
        role='Doctor',
        staff_level='Senior Consultant' if d['experience_years'] >= 8 else 'Consultant',
        phone=d['phone'],
        email=d['email'],
        gender='Female' if 'Ananya' in d['name'] or 'Meera' in d['name'] else 'Male',
        age=32 + d['experience_years'],
        base_salary=Decimal('85000.00'),
        is_active=True,
        permissions=['dashboard', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'reports', 'prescriptions']
    )

    # Mon-Sat full schedule
    for day_idx in range(6):
        DoctorSchedule.objects.create(
            doctor=doc,
            day_of_week=day_idx,
            start_time=time(9, 0),
            end_time=time(17, 30),
            is_active=True
        )
    seeded_docs.append(doc)

# Support Staff
u_rec = get_or_clean_user('receptionist_anitha', 'anitha@ashdent.demo', 'Anitha', 'Sharma')
Staff.objects.create(
    user=u_rec,
    name='Anitha Sharma',
    role='Receptionist',
    staff_level='Front Desk Executive',
    phone='9847022001',
    email='anitha@ashdent.demo',
    gender='Female',
    age=28,
    base_salary=Decimal('32000.00'),
    is_active=True,
    permissions=['dashboard', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'billing']
)

u_pharm = get_or_clean_user('pharmacist_suresh', 'suresh@ashdent.demo', 'Suresh', 'Kumar')
Staff.objects.create(
    user=u_pharm,
    name='Suresh Kumar',
    role='Pharmacist',
    staff_level='Head Pharmacist',
    phone='9847022002',
    email='suresh@ashdent.demo',
    gender='Male',
    age=36,
    base_salary=Decimal('38000.00'),
    is_active=True,
    permissions=['dashboard', 'pharmacy', 'stock', 'purchases', 'prescriptions']
)

print(f"  [OK] Created {len(seeded_docs)} Doctors + Receptionist (Anitha) + Pharmacist (Suresh).")


# -----------------------------------------------------------------------------
# STEP 6: SEED 16 REALISTIC DEMO PATIENTS
# -----------------------------------------------------------------------------
print("\n[STEP 6] Seeding 16 Realistic Dental Patients...")

patients_data = [
    {'name': 'Arjun Mathew', 'phone': '9847033001', 'dob': date(1988, 4, 12), 'gender': 'Male', 'addr': '4B Emerald Heights, MG Road', 'pin': '682016', 'pt': pt_regular, 'doc': seeded_docs[0], 'fee': Decimal('500.00')},
    {'name': 'Neha Krishnan', 'phone': '9847033002', 'dob': date(1996, 8, 24), 'gender': 'Female', 'addr': 'Skyline Apartments, Kakkanad', 'pin': '682030', 'pt': pt_vip, 'doc': seeded_docs[1], 'fee': Decimal('800.00')},
    {'name': 'Rahul Joseph', 'phone': '9847033003', 'dob': date(1992, 11, 5), 'gender': 'Male', 'addr': 'Palm Grove Colony, Marine Drive', 'pin': '682031', 'pt': pt_regular, 'doc': seeded_docs[3], 'fee': Decimal('1000.00')},
    {'name': 'Anjali Nair', 'phone': '9847033004', 'dob': date(1994, 2, 18), 'gender': 'Female', 'addr': 'Silver Oaks Estate, Edapally', 'pin': '682024', 'pt': pt_regular, 'doc': seeded_docs[0], 'fee': Decimal('500.00')},
    {'name': 'Vivek Menon', 'phone': '9847033005', 'dob': date(1983, 7, 30), 'gender': 'Male', 'addr': 'Orchid Enclave, Vyttila', 'pin': '682019', 'pt': pt_regular, 'doc': seeded_docs[2], 'fee': Decimal('700.00')},
    {'name': 'Sneha Thomas', 'phone': '9847033006', 'dob': date(1999, 12, 14), 'gender': 'Female', 'addr': 'Rose Gardens, Panampilly Nagar', 'pin': '682036', 'pt': pt_regular, 'doc': seeded_docs[0], 'fee': Decimal('500.00')},
    {'name': 'Adithya Raj', 'phone': '9847033007', 'dob': date(1964, 5, 20), 'gender': 'Male', 'addr': 'Lotus Avenue, Aluva', 'pin': '683101', 'pt': pt_senior, 'doc': seeded_docs[3], 'fee': Decimal('1000.00')},
    {'name': 'Priya Suresh', 'phone': '9847033008', 'dob': date(2001, 9, 3), 'gender': 'Female', 'addr': 'City Lights Terrace, Kaloor', 'pin': '682017', 'pt': pt_regular, 'doc': seeded_docs[1], 'fee': Decimal('800.00')},
    {'name': 'Nikhil Varma', 'phone': '9847033009', 'dob': date(1990, 3, 27), 'gender': 'Male', 'addr': 'Green Valley, Tripunithura', 'pin': '682301', 'pt': pt_regular, 'doc': seeded_docs[0], 'fee': Decimal('500.00')},
    {'name': 'Divya Mohan', 'phone': '9847033010', 'dob': date(1997, 6, 11), 'gender': 'Female', 'addr': 'Blue Mist Towers, Fort Kochi', 'pin': '682001', 'pt': pt_regular, 'doc': seeded_docs[2], 'fee': Decimal('700.00')},
    {'name': 'Akhil George', 'phone': '9847033011', 'dob': date(1993, 10, 8), 'gender': 'Male', 'addr': 'Harmony Heights, Kalamassery', 'pin': '683104', 'pt': pt_regular, 'doc': seeded_docs[1], 'fee': Decimal('800.00')},
    {'name': 'Meera Rajan', 'phone': '9847033012', 'dob': date(1958, 1, 15), 'gender': 'Female', 'addr': 'Sunshine Residency, Thrikkakara', 'pin': '682021', 'pt': pt_camp, 'doc': seeded_docs[0], 'fee': Decimal('0.00')},
    {'name': 'Kavya Ramesh', 'phone': '9847033013', 'dob': date(2003, 3, 17), 'gender': 'Female', 'addr': 'Metro View, Kadavanthra', 'pin': '682020', 'pt': pt_regular, 'doc': seeded_docs[1], 'fee': Decimal('800.00')},
    {'name': 'Harish Nambiar', 'phone': '9847033014', 'dob': date(1972, 8, 9), 'gender': 'Male', 'addr': 'Haritha Gardens, Ravipuram', 'pin': '682015', 'pt': pt_regular, 'doc': seeded_docs[2], 'fee': Decimal('700.00')},
    {'name': 'Pooja Varghese', 'phone': '9847033015', 'dob': date(1985, 11, 22), 'gender': 'Female', 'addr': 'Crystal Palace, Palarivattom', 'pin': '682025', 'pt': pt_vip, 'doc': seeded_docs[2], 'fee': Decimal('700.00')},
    {'name': 'Deepak Pillai', 'phone': '9847033016', 'dob': date(1978, 2, 4), 'gender': 'Male', 'addr': 'Waterfront Residences, Thevara', 'pin': '682013', 'pt': pt_regular, 'doc': seeded_docs[3], 'fee': Decimal('1000.00')},
]

today = timezone.localtime(timezone.now()).date()
print(f"  [INFO] Anchor System Date: {today}")

patients = {}
for pd in patients_data:
    age_calc = today.year - pd['dob'].year - ((today.month, today.day) < (pd['dob'].month, pd['dob'].day))
    p = Patient.objects.create(
        name=pd['name'],
        phone=pd['phone'],
        dob=pd['dob'],
        age=age_calc,
        gender=pd['gender'],
        address=pd['addr'],
        pincode=pd['pin'],
        status='Active',
        doctor=pd['doc'],
        patient_type=pd['pt'],
        consultation_fee=pd['fee']
    )
    patients[pd['name']] = p

print(f"  [OK] Seeded {len(patients)} Patients with complete profile information.")


# -----------------------------------------------------------------------------
# STEP 7: SEED TODAY'S LIVE CLINIC QUEUE (OCT 16, 2026)
# -----------------------------------------------------------------------------
print("\n[STEP 7] Building Today's Live Clinical Queue (Completed, Engaged, Waiting, Scheduled)...")

# Helper function to generate clean completed visit, treatment, bill, and transaction
def create_clinical_visit_record(patient, doctor, appt_date, appt_time, status, complaint, diagnosis, treatments, payment_info=None):
    appt = Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        date=appt_date,
        time=appt_time,
        status=status
    )
    
    visit = None
    cn = None
    if status in ['Completed', 'Engaged']:
        visit = Visit.objects.create(patient=patient, appointment=appt)
        cn = ClinicalNotes.objects.create(
            appointment=appt,
            chief_complaint=complaint,
            complaints=[complaint],
            observations=[diagnosis],
            diagnosis=[diagnosis],
            treatment_plan=', '.join([t['name'] for t in treatments])
        )
        
        # Treatment records with tooth numbers for Odontogram!
        total_bill = Decimal('0.00')
        for t in treatments:
            t_obj = tx_map[t['name']]
            price = t.get('price', t_obj.price)
            total_bill += price
            TreatmentRecord.objects.create(
                visit=visit,
                treatment=t_obj,
                tooth_number=t.get('tooth_number', ''),
                price=price,
                fee_type=t_obj.fee_type,
                status=t.get('status', 'Completed'),
                doctor=doctor,
                notes=t.get('notes', '')
            )
            
        if payment_info and status == 'Completed':
            paid_amount = payment_info.get('paid', total_bill)
            cash_rec = payment_info.get('cash_received', Decimal('0.00'))
            bal_ret = payment_info.get('balance_returned', Decimal('0.00'))
            bal_due = total_bill - paid_amount
            pay_method = payment_info.get('method', 'Cash')
            bill_status = 'Paid' if bal_due <= Decimal('0.00') else 'Partial'
            
            bill = Billing.objects.create(
                patient=patient,
                visit=visit,
                clinical_note=cn,
                doctor=doctor,
                bill_type='Clinical',
                total_amount=total_bill,
                paid_amount=paid_amount,
                cash_received=cash_rec,
                balance_returned=bal_ret,
                balance_amount=bal_due,
                payment_method=pay_method,
                status=bill_status,
                is_invoice=True
            )
            
            for t in treatments:
                t_obj = tx_map[t['name']]
                price = t.get('price', t_obj.price)
                BillingItem.objects.create(
                    billing=bill,
                    treatment=t_obj,
                    qty=1,
                    price=price
                )
                
            Payment.objects.create(
                patient=patient,
                visit=visit,
                doctor=doctor,
                total_amount=total_bill,
                paid_amount=paid_amount,
                cash_received=cash_rec,
                balance_returned=bal_ret,
                balance_amount=bal_due,
                payment_method=pay_method,
                transaction_id=payment_info.get('tx_id', f'TXN-{pay_method[:2].upper()}-{appt.id}'),
                transaction_date=appt_date,
                status=bill_status
            )
            
            if paid_amount > 0:
                Transaction.objects.create(
                    type='Income',
                    amount=paid_amount,
                    category='Patient Payment',
                    patient=patient,
                    doctor=doctor,
                    payment_method=pay_method,
                    date=appt_date
                )
                
            # Date alignment for past dates
            if appt_date < today:
                past_dt = timezone.make_aware(datetime.combine(appt_date, appt_time))
                db['patients_billing'].update_one({'_id': ObjectId(bill.id)}, {'$set': {'created_at': past_dt}})
                db['patients_visit'].update_one({'_id': ObjectId(visit.id)}, {'$set': {'created_at': past_dt}})

    return appt

# ----------------- TODAY (2026-10-16) APPOINTMENTS -----------------
# 1. Arjun Mathew — Completed (09:00 AM)
# ODONTOGRAM SHOWCASE PATIENT: Tooth 16 (Purple - Completed Filling), Tooth 25 (Grey - Extracted), Tooth 36 (Yellow - Planned RCT)
# PAYMENT SHOWCASE: Cash Received ₹3,000 | Balance Returned ₹500
create_clinical_visit_record(
    patient=patients['Arjun Mathew'],
    doctor=seeded_docs[0], # Dr. Ananya Menon
    appt_date=today,
    appt_time=time(9, 0),
    status='Completed',
    complaint='Toothache in lower left molar & discoloration in upper premolar',
    diagnosis='Dental Caries in 16, Chronic Pulpitis in 36, Non-restorable 25',
    treatments=[
        {'name': 'Dental Cleaning & Scaling', 'tooth_number': '', 'status': 'Completed', 'price': Decimal('1000.00')},
        {'name': 'Composite Tooth Filling', 'tooth_number': '16', 'status': 'Completed', 'price': Decimal('1500.00'), 'notes': 'Composite restoration on tooth 16 completed'},
        {'name': 'Simple Tooth Extraction', 'tooth_number': '25', 'status': 'Completed', 'price': Decimal('1000.00'), 'notes': 'Tooth 25 extracted due to root fracture'},
        {'name': 'Root Canal Treatment (RCT)', 'tooth_number': '36', 'status': 'Planned', 'price': Decimal('0.00'), 'notes': 'RCT planned for tooth 36 next week'}
    ],
    payment_info={
        'paid': Decimal('2500.00'),
        'method': 'Cash',
        'cash_received': Decimal('3000.00'),
        'balance_returned': Decimal('500.00')
    }
)

# 2. Neha Krishnan — Completed (09:45 AM)
# PAYMENT SHOWCASE: Orthodontic Braces Setup, ₹25,800 Total, ₹15,000 Paid via UPI, ₹10,800 Balance Due
create_clinical_visit_record(
    patient=patients['Neha Krishnan'],
    doctor=seeded_docs[1], # Dr. Rahul Nair
    appt_date=today,
    appt_time=time(9, 45),
    status='Completed',
    complaint='Anterior spacing and crowding',
    diagnosis='Angle Class I Malocclusion with crowding',
    treatments=[
        {'name': 'Orthodontic Consultation', 'tooth_number': '', 'status': 'Completed', 'price': Decimal('800.00')},
        {'name': 'Metal / Ceramic Braces Setup', 'tooth_number': '12, 11, 21, 22', 'status': 'Completed', 'price': Decimal('25000.00'), 'notes': 'Ceramic upper and lower brackets bonded'}
    ],
    payment_info={
        'paid': Decimal('15000.00'),
        'method': 'UPI',
        'tx_id': 'UPI-9847-ORTO-01',
        'cash_received': Decimal('0.00'),
        'balance_returned': Decimal('0.00')
    }
)

# 3. Anjali Nair — Completed (10:30 AM)
# Card Payment ₹1,700
create_clinical_visit_record(
    patient=patients['Anjali Nair'],
    doctor=seeded_docs[0], # Dr. Ananya Menon
    appt_date=today,
    appt_time=time(10, 30),
    status='Completed',
    complaint='Gingival bleeding while brushing',
    diagnosis='Marginal Gingivitis',
    treatments=[
        {'name': 'Dental Consultation', 'tooth_number': '', 'status': 'Completed', 'price': Decimal('500.00')},
        {'name': 'Dental Cleaning & Scaling', 'tooth_number': '', 'status': 'Completed', 'price': Decimal('1200.00')}
    ],
    payment_info={
        'paid': Decimal('1700.00'),
        'method': 'Card',
        'tx_id': 'POS-CARD-8831'
    }
)

# 4. Rahul Joseph — ENGAGED (11:15 AM)
# Currently in Dental Chair with Dr. Arjun Kumar
create_clinical_visit_record(
    patient=patients['Rahul Joseph'],
    doctor=seeded_docs[3], # Dr. Arjun Kumar (Surgeon)
    appt_date=today,
    appt_time=time(11, 15),
    status='Engaged',
    complaint='Severe pain & swelling in lower right jaw (Wisdom tooth)',
    diagnosis='Pericoronitis with impacted 48',
    treatments=[
        {'name': 'Surgical / Wisdom Tooth Extraction', 'tooth_number': '48', 'status': 'In-Progress', 'price': Decimal('4000.00')}
    ]
)

# 5. Sneha Thomas — WAITING (11:45 AM)
# In Waiting Lounge with Dr. Ananya Menon
Appointment.objects.create(
    patient=patients['Sneha Thomas'],
    doctor=seeded_docs[0],
    date=today,
    time=time(11, 45),
    status='Waiting'
)

# 6. Divya Mohan — WAITING (12:15 PM)
# In Waiting Lounge with Dr. Meera Thomas
Appointment.objects.create(
    patient=patients['Divya Mohan'],
    doctor=seeded_docs[2],
    date=today,
    time=time(12, 15),
    status='Waiting'
)

# 7. Vivek Menon — SCHEDULED (02:00 PM)
# Crown Trial & Odontogram Demonstration patient
# (Has past treatments seeded below)
Appointment.objects.create(
    patient=patients['Vivek Menon'],
    doctor=seeded_docs[2],
    date=today,
    time=time(14, 0),
    status='Scheduled'
)

# 8. Adithya Raj — SCHEDULED (02:45 PM)
Appointment.objects.create(
    patient=patients['Adithya Raj'],
    doctor=seeded_docs[3],
    date=today,
    time=time(14, 45),
    status='Scheduled'
)

# 9. Priya Suresh — SCHEDULED (03:30 PM)
Appointment.objects.create(
    patient=patients['Priya Suresh'],
    doctor=seeded_docs[1],
    date=today,
    time=time(15, 30),
    status='Scheduled'
)

# 10. Nikhil Varma — SCHEDULED (04:15 PM)
Appointment.objects.create(
    patient=patients['Nikhil Varma'],
    doctor=seeded_docs[0],
    date=today,
    time=time(16, 15),
    status='Scheduled'
)

print(f"  [OK] Today's queue created: 3 Completed, 1 In Chair (Engaged), 2 Waiting, 4 Scheduled.")


# -----------------------------------------------------------------------------
# STEP 8: SEED HISTORICAL WORKFLOW & ODONTOGRAMS (PAST 6 DAYS)
# -----------------------------------------------------------------------------
print("\n[STEP 8] Seeding Historical Data (Oct 10 - Oct 15) for Charts, Trends & Analytics...")

# Patient Vivek Menon past treatment records for Odontogram showcase
# Tooth 46: Completed Zirconia Crown (Purple)
# Tooth 14: Deep Caries (Yellow / Recommended)
# Tooth 18 & 28: Third Molars Extracted (Grey / Removed)
v_date = today - timedelta(days=3)
v_appt = Appointment.objects.create(
    patient=patients['Vivek Menon'],
    doctor=seeded_docs[2],
    date=v_date,
    time=time(15, 0),
    status='Completed'
)
v_visit = Visit.objects.create(patient=patients['Vivek Menon'], appointment=v_appt)
v_cn = ClinicalNotes.objects.create(
    appointment=v_appt,
    chief_complaint='Severe masticatory pain in 46 & food trapping in 14',
    complaints=['Molar pain'],
    observations=['Root treated 46 needs full crown coverage, occlusal caries in 14'],
    diagnosis=['Grossly decayed 46 post-endo, Class I caries 14'],
    treatment_plan='Zirconia crown on 46, RCT recommended for 14'
)
TreatmentRecord.objects.create(visit=v_visit, treatment=tx_map['Zirconia Premium Crown'], tooth_number='46', status='Completed', price=Decimal('9000.00'), doctor=seeded_docs[2])
TreatmentRecord.objects.create(visit=v_visit, treatment=tx_map['Simple Tooth Extraction'], tooth_number='18, 28', status='Completed', price=Decimal('2000.00'), doctor=seeded_docs[3])
TreatmentRecord.objects.create(visit=v_visit, treatment=tx_map['Root Canal Treatment (RCT)'], tooth_number='14', status='Recommended', price=Decimal('4500.00'), doctor=seeded_docs[2])

v_bill = Billing.objects.create(
    patient=patients['Vivek Menon'],
    visit=v_visit,
    clinical_note=v_cn,
    doctor=seeded_docs[2],
    bill_type='Clinical',
    total_amount=Decimal('11000.00'),
    paid_amount=Decimal('11000.00'),
    balance_amount=Decimal('0.00'),
    payment_method='Bank Transfer',
    status='Paid',
    is_invoice=True
)
BillingItem.objects.create(billing=v_bill, treatment=tx_map['Zirconia Premium Crown'], qty=1, price=Decimal('9000.00'))
BillingItem.objects.create(billing=v_bill, treatment=tx_map['Simple Tooth Extraction'], qty=2, price=Decimal('2000.00'))
Payment.objects.create(patient=patients['Vivek Menon'], visit=v_visit, doctor=seeded_docs[2], total_amount=Decimal('11000.00'), paid_amount=Decimal('11000.00'), balance_amount=Decimal('0.00'), payment_method='Bank Transfer', transaction_id='NEFT-5599201', transaction_date=v_date, status='Paid')
Transaction.objects.create(type='Income', amount=Decimal('11000.00'), category='Patient Payment', patient=patients['Vivek Menon'], doctor=seeded_docs[2], payment_method='Bank Transfer', date=v_date)

past_dt_v = timezone.make_aware(datetime.combine(v_date, time(15, 0)))
db['patients_billing'].update_one({'_id': ObjectId(v_bill.id)}, {'$set': {'created_at': past_dt_v}})
db['patients_visit'].update_one({'_id': ObjectId(v_visit.id)}, {'$set': {'created_at': past_dt_v}})


# Daily distributions across past 6 days (Sat Oct 10 to Thu Oct 15)
historical_cases = [
    # Oct 15 (Yesterday)
    {
        'patient': patients['Pooja Varghese'], 'doctor': seeded_docs[2], 'days_ago': 1, 'time': time(10, 0),
        'complaint': 'Missing lower first molar aesthetic replacement', 'diag': 'Missing 36 edentulous space',
        'txs': [{'name': 'Porcelain / E-Max Crown', 'tooth_number': '36', 'price': Decimal('6000.00')}, {'name': 'Dental Cleaning & Scaling', 'price': Decimal('1200.00')}],
        'pay': {'paid': Decimal('7200.00'), 'method': 'UPI'}
    },
    {
        'patient': patients['Akhil George'], 'doctor': seeded_docs[1], 'days_ago': 1, 'time': time(11, 30),
        'complaint': 'Routine orthodontic wire tightening', 'diag': 'Active orthodontic alignment Phase II',
        'txs': [{'name': 'Orthodontic Consultation', 'price': Decimal('800.00')}],
        'pay': {'paid': Decimal('800.00'), 'method': 'Cash', 'cash_received': Decimal('1000.00'), 'balance_returned': Decimal('200.00')}
    },
    {
        'patient': patients['Deepak Pillai'], 'doctor': seeded_docs[3], 'days_ago': 1, 'time': time(14, 0),
        'complaint': 'Mobile lower anterior tooth', 'diag': 'Grade III mobility in 31',
        'txs': [{'name': 'Simple Tooth Extraction', 'tooth_number': '31', 'price': Decimal('1000.00')}],
        'pay': {'paid': Decimal('1000.00'), 'method': 'Cash', 'cash_received': Decimal('1000.00'), 'balance_returned': Decimal('0.00')}
    },

    # Oct 14 (2 days ago)
    {
        'patient': patients['Harish Nambiar'], 'doctor': seeded_docs[2], 'days_ago': 2, 'time': time(9, 30),
        'complaint': 'Full mouth prosthetic rehabilitation consult', 'diag': 'Multiple missing teeth in upper jaw',
        'txs': [{'name': 'Complete Denture (Per Arch)', 'tooth_number': '', 'price': Decimal('12000.00')}],
        'pay': {'paid': Decimal('12000.00'), 'method': 'Bank Transfer'}
    },
    {
        'patient': patients['Kavya Ramesh'], 'doctor': seeded_docs[0], 'days_ago': 2, 'time': time(11, 0),
        'complaint': 'Discoloration of front teeth for upcoming event', 'diag': 'Fluorosis staining anterior teeth',
        'txs': [{'name': 'Professional Teeth Whitening', 'price': Decimal('6000.00')}],
        'pay': {'paid': Decimal('6000.00'), 'method': 'UPI'}
    },
    {
        'patient': patients['Meera Rajan'], 'doctor': seeded_docs[0], 'days_ago': 2, 'time': time(15, 30),
        'complaint': 'Senior dental wellness check', 'diag': 'Generalized enamel attrition',
        'txs': [{'name': 'Dental Consultation', 'price': Decimal('0.00')}],
        'pay': {'paid': Decimal('0.00'), 'method': 'Cash'}
    },

    # Oct 13 (3 days ago)
    {
        'patient': patients['Sneha Thomas'], 'doctor': seeded_docs[0], 'days_ago': 3, 'time': time(10, 15),
        'complaint': 'Sensitivity to cold drinks', 'diag': 'Cervical abrasion 23, 24',
        'txs': [{'name': 'Composite Tooth Filling', 'tooth_number': '23, 24', 'price': Decimal('3000.00')}],
        'pay': {'paid': Decimal('3000.00'), 'method': 'Card'}
    },
    {
        'patient': patients['Adithya Raj'], 'doctor': seeded_docs[3], 'days_ago': 3, 'time': time(12, 0),
        'complaint': 'Wisdom tooth swelling and trismus', 'diag': 'Impacted 38',
        'txs': [{'name': 'Surgical / Wisdom Tooth Extraction', 'tooth_number': '38', 'price': Decimal('4000.00')}],
        'pay': {'paid': Decimal('4000.00'), 'method': 'Cash', 'cash_received': Decimal('4000.00'), 'balance_returned': Decimal('0.00')}
    },
    {
        'patient': patients['Priya Suresh'], 'doctor': seeded_docs[1], 'days_ago': 3, 'time': time(16, 0),
        'complaint': 'Lingual retainer detachment', 'diag': 'Broken retainer wire',
        'txs': [{'name': 'Orthodontic Consultation', 'price': Decimal('800.00')}],
        'pay': {'paid': Decimal('800.00'), 'method': 'UPI'}
    },

    # Oct 12 (4 days ago)
    {
        'patient': patients['Nikhil Varma'], 'doctor': seeded_docs[0], 'days_ago': 4, 'time': time(9, 30),
        'complaint': 'Tartar build up and smoker stain', 'diag': 'Extrinsic stains & calculus',
        'txs': [{'name': 'Dental Cleaning & Scaling', 'price': Decimal('1200.00')}, {'name': 'Digital Dental X-Ray (RVG)', 'price': Decimal('300.00')}],
        'pay': {'paid': Decimal('1500.00'), 'method': 'Cash', 'cash_received': Decimal('2000.00'), 'balance_returned': Decimal('500.00')}
    },
    {
        'patient': patients['Divya Mohan'], 'doctor': seeded_docs[2], 'days_ago': 4, 'time': time(11, 45),
        'complaint': 'Chipped porcelain crown on upper premolar', 'diag': 'Fractured bridge pontic 15',
        'txs': [{'name': 'Porcelain / E-Max Crown', 'tooth_number': '15', 'price': Decimal('6000.00')}],
        'pay': {'paid': Decimal('6000.00'), 'method': 'Card'}
    },

    # Oct 11 (5 days ago)
    {
        'patient': patients['Arjun Mathew'], 'doctor': seeded_docs[0], 'days_ago': 5, 'time': time(10, 0),
        'complaint': 'Diagnostic evaluation for full mouth restoration', 'diag': 'Multiple restoration requirements',
        'txs': [{'name': 'Dental Consultation', 'price': Decimal('500.00')}, {'name': 'Digital Dental X-Ray (RVG)', 'price': Decimal('300.00')}],
        'pay': {'paid': Decimal('800.00'), 'method': 'UPI'}
    },
    {
        'patient': patients['Neha Krishnan'], 'doctor': seeded_docs[1], 'days_ago': 5, 'time': time(14, 30),
        'complaint': 'Initial orthodontic records & study models', 'diag': 'Orthodontic workup',
        'txs': [{'name': 'Orthodontic Consultation', 'price': Decimal('800.00')}],
        'pay': {'paid': Decimal('800.00'), 'method': 'UPI'}
    },

    # Oct 10 (6 days ago)
    {
        'patient': patients['Rahul Joseph'], 'doctor': seeded_docs[3], 'days_ago': 6, 'time': time(11, 0),
        'complaint': 'Pre-surgical wisdom tooth checkup', 'diag': 'Mesioangular impaction 48',
        'txs': [{'name': 'Dental Consultation', 'price': Decimal('500.00')}, {'name': 'Digital Dental X-Ray (RVG)', 'price': Decimal('300.00')}],
        'pay': {'paid': Decimal('800.00'), 'method': 'Cash', 'cash_received': Decimal('1000.00'), 'balance_returned': Decimal('200.00')}
    },
    {
        'patient': patients['Anjali Nair'], 'doctor': seeded_docs[0], 'days_ago': 6, 'time': time(15, 0),
        'complaint': 'Cavity checkup and initial filling', 'diag': 'Class I cavity in 45',
        'txs': [{'name': 'Composite Tooth Filling', 'tooth_number': '45', 'price': Decimal('1500.00')}],
        'pay': {'paid': Decimal('1500.00'), 'method': 'Card'}
    }
]

for hc in historical_cases:
    h_date = today - timedelta(days=hc['days_ago'])
    create_clinical_visit_record(
        patient=hc['patient'],
        doctor=hc['doctor'],
        appt_date=h_date,
        appt_time=hc['time'],
        status='Completed',
        complaint=hc['complaint'],
        diagnosis=hc['diag'],
        treatments=hc['txs'],
        payment_info=hc['pay']
    )

print(f"  [OK] Seeded {len(historical_cases)} historical cases across the past 6 days.")


# -----------------------------------------------------------------------------
# STEP 9: SEED CLINICAL EXPENSES & PRE-BOOKINGS
# -----------------------------------------------------------------------------
print("\n[STEP 9] Seeding Clinic Expenses, Future Pre-Bookings & Lab Orders...")

# 1. Realistic Expenses
expenses_data = [
    {'title': 'Composite Resins & Etch Purchase', 'cat': 'Dental Materials', 'amount': Decimal('8400.00'), 'days_ago': 2, 'vendor': '3M ESPE Healthcare'},
    {'title': 'Biomedical Waste Disposal Fee', 'cat': 'Waste Disposal & Biomedical Waste', 'amount': Decimal('3200.00'), 'days_ago': 4, 'vendor': 'Image Kerala Waste Solutions'},
    {'title': 'Clinic Electricity Bill (October)', 'cat': 'Rent & Electricity Bill', 'amount': Decimal('14800.00'), 'days_ago': 5, 'vendor': 'KSEB Commercial'},
    {'title': 'Sterilization Pouches & Suction Tips', 'cat': 'Consumables (Gloves, Glass, Suction)', 'amount': Decimal('4500.00'), 'days_ago': 1, 'vendor': 'Prime Med Surgicals'},
]

for exp in expenses_data:
    e_date = today - timedelta(days=exp['days_ago'])
    e_obj = Expense.objects.create(
        title=exp['title'],
        category=exp['cat'],
        description=f"Authorized clinical expense for {exp['title']}",
        amount=exp['amount'],
        date=e_date,
        paid_to=exp['vendor'],
        vendor=exp['vendor'],
        payment_method='Bank Transfer',
        status='Paid'
    )
    Transaction.objects.create(
        type='Expense',
        amount=exp['amount'],
        category=exp['cat'],
        notes=exp['title'],
        payment_method='Bank Transfer',
        date=e_date
    )
    e_dt = timezone.make_aware(datetime.combine(e_date, time(12, 0)))
    db['patients_expense'].update_one({'_id': ObjectId(e_obj.id)}, {'$set': {'created_at': e_dt}})

# 2. Pre-Bookings for next week
PreBooking.objects.create(name='Kavya Ramesh', phone='9847033013', expected_date=today + timedelta(days=2), notes='Full mouth scaling & polishing review', status='Confirmed')
PreBooking.objects.create(name='Harish Nambiar', phone='9847033014', expected_date=today + timedelta(days=4), notes='Denture try-in and bite registration', status='Pending')
PreBooking.objects.create(name='Dr. Lakshmi Mohan', phone='9847033099', expected_date=today + timedelta(days=5), notes='Implant specialist consultation', status='Confirmed')

# 3. Patient Lab Orders
PatientLabOrder.objects.create(
    patient=patients['Vivek Menon'],
    name='Zirconia Multilayer Crown 46',
    category='Crown & Bridge',
    price=Decimal('3500.00'),
    date=today,
    status='In Progress'
)
PatientLabOrder.objects.create(
    patient=patients['Pooja Varghese'],
    name='E-Max Aesthetic Inlay 36',
    category='Ceramic Lab',
    price=Decimal('2800.00'),
    date=today - timedelta(days=1),
    status='Delivered'
)

print("  [OK] Seeded 4 Expenses, 3 Pre-Bookings, 2 Dental Lab Orders.")


# -----------------------------------------------------------------------------
# STEP 10: DATABASE INTEGRITY & ORPHAN CHECKS
# -----------------------------------------------------------------------------
print("\n[STEP 10] Running Integrity & Consistency Verification...")

counts = {
    'doctors': Doctor.objects.count(),
    'staff': Staff.objects.count(),
    'patients': Patient.objects.count(),
    'appointments': Appointment.objects.count(),
    'today_appts': Appointment.objects.filter(date=today).count(),
    'waiting_today': Appointment.objects.filter(date=today, status='Waiting').count(),
    'engaged_today': Appointment.objects.filter(date=today, status='Engaged').count(),
    'completed_today': Appointment.objects.filter(date=today, status='Completed').count(),
    'scheduled_today': Appointment.objects.filter(date=today, status='Scheduled').count(),
    'visits': Visit.objects.count(),
    'billings': Billing.objects.count(),
    'payments': Payment.objects.count(),
    'treatment_records': TreatmentRecord.objects.count(),
    'income_txs': Transaction.objects.filter(type='Income').count(),
    'medicines': MedicineMaster.objects.count(),
    'low_stock_medicines': MedicineMaster.objects.filter(stock_quantity__lte=15).count()
}

for k, v in counts.items():
    print(f"  • {k.replace('_', ' ').title()}: {v}")

# Zero orphan assertions
assert Appointment.objects.filter(patient__isnull=True).count() == 0, "Orphan appointments detected"
assert Billing.objects.filter(patient__isnull=True).count() == 0, "Orphan billings detected"
assert Payment.objects.filter(patient__isnull=True).count() == 0, "Orphan payments detected"
assert counts['today_appts'] >= 8, f"Expected at least 8 appointments today, got {counts['today_appts']}"
assert counts['engaged_today'] >= 1, "Expected at least 1 engaged appointment in dental chair"
assert counts['waiting_today'] >= 1, "Expected at least 1 waiting patient in lounge"

print("\n" + "=" * 70)
print("  DEMO DATASET CREATION COMPLETED WITH 100% SUCCESS!")
print("=" * 70)
