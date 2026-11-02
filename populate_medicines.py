import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import MedicineMaster

medicines = [
    {"name": "Paracetamol", "dosage": "500mg", "frequency": "1-0-1", "notes": "After food"},
    {"name": "Amoxicillin", "dosage": "500mg", "frequency": "1-1-1", "notes": "Antibiotic"},
    {"name": "Ibuprofen", "dosage": "400mg", "frequency": "1-0-1", "notes": "Painkiller"},
    {"name": "Metronidazole", "dosage": "400mg", "frequency": "1-1-1", "notes": "For infection"},
    {"name": "Augmentin", "dosage": "625mg", "frequency": "1-0-1", "notes": "Potent antibiotic"},
    {"name": "Ondansetron", "dosage": "4mg", "frequency": "1-0-1", "notes": "For nausea"},
    {"name": "Pantoprazole", "dosage": "40mg", "frequency": "1-0-0", "notes": "Before food"},
    {"name": "Diclofenac", "dosage": "50mg", "frequency": "1-0-1", "notes": "Strong painkiller"},
    {"name": "Cetirizine", "dosage": "10mg", "frequency": "0-0-1", "notes": "For allergy"},
]

for m in medicines:
    MedicineMaster.objects.get_or_create(
        name=m['name'],
        defaults={'dosage': m['dosage'], 'frequency': m['frequency'], 'notes': m['notes']}
    )

print(f"Populated {len(medicines)} medicines.")
