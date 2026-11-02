import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from patients.models import DropdownMaster

DATA = {
    'complaint': [
        'Toothache / Severe Pain', 'Sensitivity to Cold/Hot', 'Swelling in Gums', 
        'Bleeding during Brushing', 'Broken / Chipped Tooth', 'Loose Tooth', 
        'Missing Tooth / Gap', 'Yellow / Stained Teeth', 'Bad Breath', 
        'Food Lodgement / Gaps', 'Decayed Tooth / Hole', 'Sharp Edge irritating Tongue',
        'Mobile Cap / Crown', 'Wisdom Tooth Pain', 'Bleeding Gums', 'Difficulty in Chewing'
    ],
    'observation': [
        'Deep Occlusal Caries', 'Proximal Caries', 'Pulp Exposure Seen', 
        'Gingival Inflammation', 'Grade I Mobility', 'Grade II Mobility', 
        'Grade III Mobility', 'Fractured Crown Portion', 'Periapical Abscess', 
        'Impacted 3rd Molar', 'Supra-gingival Calculus', 'Sub-gingival Calculus',
        'Root Piece Present', 'Generalized Attrition', 'Abrasion / Erosion',
        'Open Contact', 'Gingival Recession'
    ],
    'diagnosis': [
        'Acute Irreversible Pulpitis', 'Chronic Irreversible Pulpitis', 'Reversible Pulpitis', 
        'Acute Periapical Periodontitis', 'Chronic Generalized Periodontitis', 
        'Dental Caries (Class I/II/III/IV/V)', 'Impacted / Mesioangular Tooth', 
        'Apical Periodontitis', 'Gingivitis', 'Pericoronitis', 'Alveolar Bone Loss',
        'Edentulous Arch', 'Root Canal Failure'
    ],
    'investigation': [
        'IOPA X-Ray', 'Bitewing X-Ray', 'OPG (Full Mouth X-Ray)', 'CBCT Scan',
        'Blood Glucose (PP/Fasting)', 'Blood Count (CBC)', 'Bleeding/Clotting Time',
        'Pulp Vitality Test', 'Diagnostic Impression', 'Study Models'
    ],
    'treatment': [
        'Root Canal Treatment (RCT)', 'Simple Extraction', 'Surgical Extraction', 
        'Scaling & Polishing', 'Deep Scaling / Currettage', 'Composite Filling', 
        'GIC Restoration', 'Dental Bridge (3 Unit)', 'Dental Implant', 
        'PFM Crown', 'Zirconia Crown', 'Orthodontic Braces', 'Complete Denture',
        'Partial Denture', 'Bleaching / Whitening'
    ],
    'medical_history': [
        'Diabetes Mellitus', 'Hypertension (High BP)', 'Thyroid Disorder', 
        'Asthma / Respiratory Issues', 'Pregnancy', 'Heart Valve Issue', 
        'Bleeding Disorder', 'Epilepsy / Fits', 'Drug Allergy (Penicillin)', 
        'Drug Allergy (Sulfa)', 'History of Surgery', 'Osteoporosis'
    ]
}

def populate():
    count = 0
    for d_type, names in DATA.items():
        for name in names:
            obj, created = DropdownMaster.objects.get_or_create(type=d_type, name=name)
            if created:
                count += 1
    print(f"Added {count} new dropdown items.")

if __name__ == '__main__':
    populate()
