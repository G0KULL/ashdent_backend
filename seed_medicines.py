import os
import django
import sys

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import MedicineMaster

medicines = [
    {"name": "Amoxicillin 500mg", "dosage": "500mg", "frequency": "1-1-1", "sales_rate": 150.00, "notes": "Broad-spectrum antibiotic"},
    {"name": "Amoxicillin + Clavulanic Acid (Augmentin)", "dosage": "625mg", "frequency": "1-0-1", "sales_rate": 250.00, "notes": "Antibiotic for resistant infections"},
    {"name": "Metronidazole 400mg", "dosage": "400mg", "frequency": "1-1-1", "sales_rate": 80.00, "notes": "Antibiotic for anaerobic bacteria"},
    {"name": "Clindamycin 300mg", "dosage": "300mg", "frequency": "1-1-1", "sales_rate": 180.00, "notes": "Antibiotic for penicillin-allergic patients"},
    {"name": "Azithromycin 500mg", "dosage": "500mg", "frequency": "1-0-0", "sales_rate": 200.00, "notes": "Macrolide antibiotic"},
    {"name": "Cephalexin 500mg", "dosage": "500mg", "frequency": "1-1-1", "sales_rate": 120.00, "notes": "Cephalosporin antibiotic"},
    {"name": "Ibuprofen 400mg", "dosage": "400mg", "frequency": "1-0-1", "sales_rate": 60.00, "notes": "NSAID for inflammation and pain"},
    {"name": "Paracetamol 500mg", "dosage": "500mg", "frequency": "1-1-1", "sales_rate": 40.00, "notes": "Analgesic and antipyretic"},
    {"name": "Ketorolac 10mg", "dosage": "10mg", "frequency": "1-1-1", "sales_rate": 90.00, "notes": "Strong NSAID for severe pain"},
    {"name": "Diclofenac Potassium 50mg", "dosage": "50mg", "frequency": "1-0-1", "sales_rate": 70.00, "notes": "NSAID pain relief"},
    {"name": "Aceclofenac + Paracetamol", "dosage": "100mg+325mg", "frequency": "1-0-1", "sales_rate": 85.00, "notes": "Combination pain relief"},
    {"name": "Mefenamic Acid 500mg", "dosage": "500mg", "frequency": "1-1-1", "sales_rate": 95.00, "notes": "NSAID for dental pain"},
    {"name": "Naproxen 250mg", "dosage": "250mg", "frequency": "1-0-1", "sales_rate": 110.00, "notes": "Long-acting NSAID"},
    {"name": "Tramadol 50mg", "dosage": "50mg", "frequency": "1-0-1", "sales_rate": 150.00, "notes": "Opioid analgesic for severe pain"},
    {"name": "Chlorhexidine Gluconate 0.2%", "dosage": "10ml", "frequency": "1-0-1", "sales_rate": 120.00, "notes": "Antiseptic mouthwash"},
    {"name": "Povidone-Iodine 1%", "dosage": "10ml", "frequency": "1-0-1", "sales_rate": 100.00, "notes": "Antiseptic mouth gargle"},
    {"name": "Hydrogen Peroxide 1.5%", "dosage": "15ml", "frequency": "1-0-1", "sales_rate": 90.00, "notes": "Antiseptic oral rinse"},
    {"name": "Benzocaine 20% Gel", "dosage": "Topical", "frequency": "SOS", "sales_rate": 200.00, "notes": "Topical anesthetic for gums"},
    {"name": "Lidocaine 2% Viscous", "dosage": "Topical", "frequency": "SOS", "sales_rate": 180.00, "notes": "Topical anesthetic"},
    {"name": "Eugenol (Clove Oil)", "dosage": "Topical", "frequency": "SOS", "sales_rate": 50.00, "notes": "Natural sedative for toothache"},
    {"name": "Dexamethasone 0.5mg", "dosage": "0.5mg", "frequency": "1-0-1", "sales_rate": 60.00, "notes": "Corticosteroid for severe inflammation"},
    {"name": "Prednisone 5mg", "dosage": "5mg", "frequency": "1-0-0", "sales_rate": 80.00, "notes": "Corticosteroid"},
    {"name": "Nystatin 100,000 U/ml", "dosage": "1ml", "frequency": "1-1-1-1", "sales_rate": 220.00, "notes": "Antifungal oral suspension"},
    {"name": "Clotrimazole 1% Gel", "dosage": "Topical", "frequency": "1-0-1", "sales_rate": 140.00, "notes": "Antifungal for oral thrush"},
    {"name": "Acyclovir 200mg", "dosage": "200mg", "frequency": "1-1-1-1-1", "sales_rate": 250.00, "notes": "Antiviral for cold sores"},
    {"name": "Amoxicillin 250mg DT", "dosage": "250mg", "frequency": "1-1-1", "sales_rate": 100.00, "notes": "Pediatric antibiotic"},
    {"name": "Ibuprofen Suspension", "dosage": "100mg/5ml", "frequency": "SOS", "sales_rate": 80.00, "notes": "Pediatric pain relief"},
    {"name": "Paracetamol Suspension", "dosage": "120mg/5ml", "frequency": "SOS", "sales_rate": 70.00, "notes": "Pediatric fever/pain relief"}
]

print("Starting to seed dental medicines...")
count = 0
for med in medicines:
    obj, created = MedicineMaster.objects.get_or_create(
        name=med["name"],
        defaults={
            "dosage": med["dosage"],
            "frequency": med["frequency"],
            "sales_rate": med["sales_rate"],
            "notes": med["notes"],
            "stock_quantity": 100,
            "low_stock_threshold": 20,
            "purchase_rate": med["sales_rate"] * 0.7  # roughly 30% margin
        }
    )
    if created:
        print(f"Added: {med['name']}")
        count += 1
    else:
        print(f"Already exists: {med['name']}")

print(f"\nSuccessfully added {count} new dental medicines!")
