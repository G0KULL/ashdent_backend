import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import LabTestMaster, LabTestParameter

def populate():
    tests = [
        {
            'name': 'Complete Blood Count',
            'code': 'CBC',
            'category': 'Hematology',
            'price': 450.00,
            'parameters': [
                {'name': 'Hemoglobin', 'unit': 'g/dL', 'normal_range': '13.5-17.5'},
                {'name': 'WBC Count', 'unit': 'cells/mcL', 'normal_range': '4500-11000'},
                {'name': 'Platelet Count', 'unit': 'Lakhs/cumm', 'normal_range': '1.5-4.5'},
            ]
        },
        {
            'name': 'Blood Glucose (Random)',
            'code': 'RBS',
            'category': 'Biochemistry',
            'price': 100.00,
            'parameters': [
                {'name': 'Blood Sugar', 'unit': 'mg/dL', 'normal_range': '70-140'},
            ]
        },
        {
            'name': 'Dental X-Ray (IOPA)',
            'code': 'IOPA',
            'category': 'Radiology',
            'price': 150.00,
            'parameters': []
        },
        {
            'name': 'OPG (Full Mouth X-Ray)',
            'code': 'OPG',
            'category': 'Radiology',
            'price': 800.00,
            'parameters': []
        },
        {
            'name': 'Lateral Cephalogram',
            'code': 'LAT-CEPH',
            'category': 'Radiology',
            'price': 600.00,
            'parameters': []
        },
        {
            'name': 'CBCT Scan',
            'code': 'CBCT',
            'category': 'Radiology',
            'price': 2500.00,
            'parameters': []
        },
        {
            'name': 'HIV I & II',
            'code': 'HIV',
            'category': 'Serology',
            'price': 400.00,
            'parameters': []
        },
        {
            'name': 'HBsAg (Hepatitis B)',
            'code': 'HBSAG',
            'category': 'Serology',
            'price': 350.00,
            'parameters': []
        }
    ]

    for t_data in tests:
        params = t_data.pop('parameters')
        test, created = LabTestMaster.objects.get_or_create(
            name=t_data['name'], 
            defaults=t_data
        )
        if created:
            print(f"Created Test: {test.name}")
            for p_data in params:
                LabTestParameter.objects.create(test=test, **p_data)
                print(f"  - Added Parameter: {p_data['name']}")
        else:
            print(f"Test already exists: {test.name}")

if __name__ == '__main__':
    print("Populating Lab Tests...")
    populate()
    print("Done!")
