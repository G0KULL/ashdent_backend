import os
import django
from pymongo import MongoClient

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from patients.models import Staff, RoleMaster, PatientTypeMaster, DropdownMaster, TreatmentMaster, TaxSetting

def flush_all_data():
    print("Connecting to MongoDB...")
    client = MongoClient('mongodb://localhost:27017/')
    db = client['dental_clinic_db']
    
    collection_names = db.list_collection_names()
    print(f"Found {len(collection_names)} collections: {collection_names}")
    
    for c_name in collection_names:
        if not c_name.startswith('system.'):
            print(f"Dropping collection: {c_name}")
            db.drop_collection(c_name)
            
    print("Database collections dropped successfully!")
    
    # 1. Create Base Super Admin
    print("Initializing base Super Admin...")
    user = User.objects.create_superuser(
        username='admin',
        password='password123',
        first_name='Dr. Navas Kp',
        email='admin@dentalclinic.com'
    )
    
    Staff.objects.create(
        user=user,
        name='Dr. Navas Kp',
        role='Admin',
        phone='9876543210',
        email='admin@dentalclinic.com'
    )
    print("[OK] Super Admin created: username='admin', password='password123' (is_superuser=True)")
    
    # 2. Seed Default System Roles
    print("Initializing system RoleMaster records...")
    default_roles = [
        {'name': 'Admin', 'description': 'System and Operational Administration', 'is_system_role': True},
        {'name': 'Doctor', 'description': 'Medical and Clinical Practitioner', 'is_system_role': True},
        {'name': 'Pharmacist', 'description': 'Pharmacy and Stock Management', 'is_system_role': True},
        {'name': 'Receptionist', 'description': 'Front Desk and Appointment Scheduling', 'is_system_role': True},
        {'name': 'Accountant', 'description': 'Financial and Billing Management', 'is_system_role': True},
        {'name': 'Dental Assistant', 'description': 'Clinical Assistance and Patient Support', 'is_system_role': True},
    ]
    for r in default_roles:
        RoleMaster.objects.create(**r)
    print(f"[OK] Seeded {len(default_roles)} default role masters.")
    
    # 3. Seed Default Patient Types
    print("Initializing Patient Types...")
    patient_types = [
        {'name': 'Regular Patient', 'code': 'REG', 'description': 'Standard walk-in patient'},
        {'name': 'VIP Patient', 'code': 'VIP', 'description': 'Priority / Executive patient'},
        {'name': 'Senior Citizen', 'code': 'SNR', 'description': 'Senior citizen discount'},
        {'name': 'Insurance / Corporate', 'code': 'CORP', 'description': 'Corporate or insurance claim patient'},
    ]
    for pt in patient_types:
        PatientTypeMaster.objects.create(**pt)
    print(f"[OK] Seeded {len(patient_types)} patient type masters.")

    # 4. Seed Dropdowns
    print("Initializing Clinical Dropdowns...")
    dropdowns = [
        ('complaint', 'Tooth Ache'),
        ('complaint', 'Bleeding Gums'),
        ('observation', 'Gingivitis'),
        ('investigation', 'IOPA'),
        ('diagnosis', 'Pulpitis'),
        ('payment_method', 'Cash'),
        ('payment_method', 'Card'),
        ('payment_method', 'UPI / Online'),
    ]
    for dtype, name in dropdowns:
        DropdownMaster.objects.create(type=dtype, name=name)
    print("[OK] Seeded basic clinical dropdowns.")

    # 5. Seed Tax Setting (if TaxSetting model exists)
    try:
        TaxSetting.objects.create(name='GST', percentage=18.0, is_active=True)
        print("[OK] Seeded default tax setting (18% GST).")
    except Exception as e:
        print(f"[NOTE] Skipped tax setting: {e}")
    
    print("\nDATABASE FLUSH & RE-INITIALIZATION COMPLETE!")

if __name__ == '__main__':
    flush_all_data()
