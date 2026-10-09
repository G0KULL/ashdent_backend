import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import DropdownMaster, TreatmentMaster

# --- DROPDOWNS ---
dropdowns = [
    ('complaint', 'Fractured Filling'),
    ('complaint', 'Tooth Ache'),
    ('complaint', 'Cavity'),
    ('complaint', 'Bleeding Gums'),
    
    ('observation', 'Impacted Tooth'),
    ('observation', 'Gingivitis'),
    ('observation', 'Enamel Attrition'),
    
    ('investigation', 'RVG'),
    ('investigation', 'OPG'),
    ('investigation', 'IOPA'),
    
    ('diagnosis', 'Enamel Hypoplasia'),
    ('diagnosis', 'Pulpitis'),
    ('diagnosis', 'Periodontitis'),
    
    ('treatment', 'Root Canal'),
    ('treatment', 'Cleaning'),
    ('treatment', 'Crown'),
    ('treatment', 'Extraction'),
]

for dtype, name in dropdowns:
    DropdownMaster.objects.get_or_create(type=dtype, name=name)

# --- TREATMENTS ---
treatments = [
    ('Root Canal', 5000.00),
    ('Cleaning', 1500.00),
    ('Crown', 8000.00),
    ('Extraction', 2000.00),
]

for name, price in treatments:
    TreatmentMaster.objects.get_or_create(name=name, defaults={'price': price})

print("Sample data populated!")
