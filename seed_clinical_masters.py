import os
import django
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import (
    TreatmentMaster, DiagnosisMaster, ExaminationMaster, ToothConditionMaster, DropdownMaster
)

def normalize_text(text):
    return re.sub(r'\s+', ' ', str(text)).strip()

def make_code(prefix, name, idx):
    slug = re.sub(r'[^A-Z0-9]', '', name.upper())[:6]
    return f"{prefix}-{slug or 'ITM'}-{idx:03d}"

print("[1/4] Seeding/Updating TreatmentMaster...")
tx_count = 0
for idx, tm in enumerate(TreatmentMaster.objects.all(), start=1):
    if not tm.code:
        tm.code = f"TX-{idx:03d}"
        tm.save(update_fields=['code'])
        tx_count += 1

EXTRA_TREATMENTS = [
    ("Scaling and Root Planing", 1200, "Treatment"),
    ("Root Canal Treatment", 4000, "Treatment"),
    ("Extraction", 800, "Surgery"),
    ("Composite Filling", 1500, "Restorative"),
    ("Amalgam Filling", 900, "Restorative"),
    ("Dental Crown", 6000, "Prosthodontics"),
    ("Implant", 25000, "Implantology"),
    ("EXTRACTION OF THIRD MOLAR", 3500, "Surgery"),
    ("COMPOSITE RESTORATION", 1800, "Restorative"),
    ("Pulpectomy", 2500, "Endodontics"),
    ("Zirconia Crown", 10000, "Prosthodontics"),
    ("Teeth Bleaching / Whitening", 7000, "Cosmetic"),
    ("Dental Bridge", 12000, "Prosthodontics"),
    ("Space Maintainer", 3000, "Pedodontics"),
    ("Frenectomy", 4500, "Surgery"),
]

for name, price, f_type in EXTRA_TREATMENTS:
    norm = normalize_text(name)
    existing = TreatmentMaster.objects.filter(name__iexact=norm).first()
    if not existing:
        c = f"TX-{TreatmentMaster.objects.count() + 1:03d}"
        TreatmentMaster.objects.create(name=norm, code=c, price=price, fee_type=f_type, is_active=True)
        print(f"  + Created Treatment: {norm}")

print(f"Total Treatments now: {TreatmentMaster.objects.count()}")

print("\n[2/4] Seeding/Updating DiagnosisMaster...")
INITIAL_DIAGNOSES = [
    ("Gingivitis", "Periodontics", "Inflammation of the gingival tissues"),
    ("Reversible Pulpitis", "Endodontics", "Mild pulp inflammation that subsides after stimulus removal"),
    ("Irreversible Pulpitis", "Endodontics", "Severe pulp inflammation requiring endodontic intervention"),
    ("Dental Caries", "Restorative", "Microbial disease of the calcified tissues of the teeth"),
    ("Periodontitis", "Periodontics", "Infection that damages gum tissue and can destroy jawbone"),
    ("Fractured Tooth", "Trauma", "Crack or broken cusp/crown structure of tooth"),
    ("Periapical Abscess", "Endodontics", "Collection of pus at the root tip"),
    ("Chronic Generalized Periodontitis", "Periodontics", "Widespread deep pocketing and bone loss"),
    ("Impacted Tooth / Wisdom Tooth", "Surgery", "Tooth unable to erupt normally through gum"),
    ("Tooth Wear / Attrition", "Restorative", "Loss of tooth surface due to friction or bruxism"),
    ("Missing Tooth", "Prosthodontics", "Absence of tooth due to extraction or congenital absence"),
    ("Cracked Tooth Syndrome", "Endodontics", "Incomplete fracture of vital posterior tooth"),
]

# Also import existing diagnoses from DropdownMaster
for dd in DropdownMaster.objects.filter(type='diagnosis'):
    if not any(d[0].lower() == dd.name.lower() for d in INITIAL_DIAGNOSES):
        INITIAL_DIAGNOSES.append((dd.name, "General", f"Imported from dropdown catalog: {dd.name}"))

diag_idx = 1
for name, cat, desc in INITIAL_DIAGNOSES:
    norm = normalize_text(name)
    existing = DiagnosisMaster.objects.filter(name__iexact=norm).first()
    if not existing:
        code = f"DX-{diag_idx:03d}"
        DiagnosisMaster.objects.create(name=norm, code=code, category=cat, description=desc, is_active=True, display_order=diag_idx)
        diag_idx += 1
        # Sync with DropdownMaster
        DropdownMaster.objects.get_or_create(type='diagnosis', name=norm)
        print(f"  + Created Diagnosis: {norm}")
    else:
        # Sync with DropdownMaster
        DropdownMaster.objects.get_or_create(type='diagnosis', name=existing.name)

print(f"Total Diagnoses now: {DiagnosisMaster.objects.count()}")

print("\n[3/4] Seeding/Updating ExaminationMaster...")
INITIAL_EXAMS = [
    ("Pain on palpation positive", "Clinical Test", "Tenderness elicited when palpating apical or gingival tissue"),
    ("TOP Negative", "Percussion", "No tenderness to vertical or horizontal percussion"),
    ("Sensitivity on palpation positive", "Clinical Test", "Hypersensitive reaction on tissue palpation"),
    ("Sensitivity on air blow Negative", "Thermal/Air", "No sharp sensitivity upon air blast application"),
    ("TOP positive", "Percussion", "Tenderness on percussion indicating periapical or periodontal inflammation"),
    ("Mobility Grade 1", "Mobility", "Slightly greater than physiological mobility (< 1mm horizontally)"),
    ("Mobility Grade 2", "Mobility", "Moderate mobility up to 1mm in horizontal direction"),
    ("Mobility Grade 3", "Mobility", "Severe mobility horizontally and vertically (depression in socket)"),
    ("Deep Pocket", "Periodontal", "Periodontal probing depth exceeds 4mm"),
    ("Pulp Vitality Positive", "Vitality", "Normal electric or thermal response from healthy dental pulp"),
    ("Pulp Vitality Negative", "Vitality", "Non-vital tooth with no electric or cold response"),
    ("Sinus Tract Present", "Inspection", "Draining fistulous tract on buccal or lingual mucosa"),
    ("Proximal Food Impaction", "Inspection", "Interproximal gap with trapped debris"),
    ("Marginal Discoloration", "Restoration", "Staining or breakdown at margins of existing filling"),
]

for dd in DropdownMaster.objects.filter(type='observation'):
    if not any(e[0].lower() == dd.name.lower() for e in INITIAL_EXAMS):
        INITIAL_EXAMS.append((dd.name, "Observation", f"Imported observation: {dd.name}"))

exam_idx = 1
for name, cat, desc in INITIAL_EXAMS:
    norm = normalize_text(name)
    existing = ExaminationMaster.objects.filter(name__iexact=norm).first()
    if not existing:
        code = f"EXAM-{exam_idx:03d}"
        ExaminationMaster.objects.create(name=norm, code=code, category=cat, description=desc, is_active=True, display_order=exam_idx)
        exam_idx += 1
        DropdownMaster.objects.get_or_create(type='observation', name=norm)
        print(f"  + Created Examination: {norm}")
    else:
        DropdownMaster.objects.get_or_create(type='observation', name=existing.name)

print(f"Total Examinations now: {ExaminationMaster.objects.count()}")

print("\n[4/4] Seeding/Updating ToothConditionMaster...")
INITIAL_CONDITIONS = [
    ("Teeth Removed", "COND-REMOVED", "#64748b", True, "Tooth extracted or missing from arch; blocks routine restorations"),
    ("Treatment Taken Before", "COND-TAKEN", "#a855f7", True, "Past dental treatment completed on this tooth"),
    ("Recommended To Take Treatment", "COND-RECOMMENDED", "#eab308", True, "Clinical recommendation to undergo planned dental treatment"),
    ("Healthy / No Treatment", "COND-HEALTHY", "#10b981", True, "Intact natural tooth with no current pathological condition"),
    ("Caries / Cavity", "COND-CARIES", "#f97316", False, "Active carious lesion identified on tooth structure"),
    ("Root Canal Treated", "COND-RCT", "#8b5cf6", False, "Endodontically treated root canals with obturation"),
    ("Dental Crown Placed", "COND-CROWN", "#06b6d4", False, "Full coverage prosthetic crown restoration in situ"),
    ("Dental Implant Placed", "COND-IMPLANT", "#14b8a6", False, "Osseointegrated endosseous implant fixture present"),
    ("Fractured / Chipped", "COND-FRACTURE", "#ef4444", False, "Mechanical fracture, chipped enamel or cracked cusp"),
    ("Severe Mobility", "COND-MOBILITY", "#ec4899", False, "Marked tooth mobility requiring splinting or extraction"),
]

for name, code, color, is_sys, desc in INITIAL_CONDITIONS:
    norm = normalize_text(name)
    existing = ToothConditionMaster.objects.filter(name__iexact=norm).first()
    if not existing:
        ToothConditionMaster.objects.create(name=norm, code=code, color=color, is_system=is_sys, description=desc, is_active=True)
        print(f"  + Created Tooth Condition: {norm}")

print(f"Total Tooth Conditions now: {ToothConditionMaster.objects.count()}")
print("\n[DONE] Clinical Masters seeding complete!")
