import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections
from bson import ObjectId

db = connections['default'].database

print("Auditing Patient EMR Data Relationships...")

emr_collections = [
    'patients_patient',
    'patients_appointment',
    'patients_visit',
    'patients_clinicalnotes',
    'patients_toothconditionrecord',
    'patients_treatmentplan',
    'patients_treatmentplanitem',
    'patients_treatmentrecord',
    'patients_treatmentsession',
    'patients_patientinvestigation',
    'patients_investigationattachment',
    'patients_prescription',
    'patients_prescriptionitem'
]

emr_report = {}

# 1. Total counts
counts = {c: db[c].count_documents({}) for c in emr_collections}
print("EMR Collection Counts:", counts)

# 2. Check referential integrity from EMR collections to Patient
patient_ids = set(db['patients_patient'].distinct('_id'))
patient_company_map = {str(p['_id']): str(p.get('company_id')) for p in db['patients_patient'].find({}, {'company_id': 1})}

# Check appointment -> patient & company
appts = list(db['patients_appointment'].find())
appt_patient_orphans = 0
appt_company_mismatch = 0
for a in appts:
    pid = a.get('patient_id')
    if pid and pid not in patient_ids:
        appt_patient_orphans += 1
    if pid and str(pid) in patient_company_map:
        p_comp = patient_company_map[str(pid)]
        a_comp = str(a.get('company_id'))
        if p_comp != 'None' and a_comp != 'None' and p_comp != a_comp:
            appt_company_mismatch += 1

# Check visits -> patient & appointment
visits = list(db['patients_visit'].find())
visit_patient_orphans = 0
visit_appt_orphans = 0
visit_patient_appt_mismatch = 0
appt_ids = set(db['patients_appointment'].distinct('_id'))
appt_patient_map = {str(a['_id']): str(a.get('patient_id')) for a in appts}

for v in visits:
    pid = v.get('patient_id')
    aid = v.get('appointment_id')
    if pid and pid not in patient_ids:
        visit_patient_orphans += 1
    if aid and aid not in appt_ids:
        visit_appt_orphans += 1
    if aid and pid and str(aid) in appt_patient_map:
        if appt_patient_map[str(aid)] != str(pid):
            visit_patient_appt_mismatch += 1

# Check clinical notes
notes = list(db['patients_clinicalnotes'].find())
notes_without_visit = 0
notes_without_appt = 0
notes_patient_orphans = 0
visit_ids = set(db['patients_visit'].distinct('_id'))

for n in notes:
    aid = n.get('appointment_id')
    vid = n.get('visit_id')
    if not vid:
        notes_without_visit += 1
    if not aid:
        notes_without_appt += 1

# Check treatment plans
plans = list(db['patients_treatmentplan'].find())
plans_without_patient = 0
plans_patient_orphans = 0
for p in plans:
    pid = p.get('patient_id')
    if not pid:
        plans_without_patient += 1
    elif pid not in patient_ids:
        plans_patient_orphans += 1

# Check treatment records
records = list(db['patients_treatmentrecord'].find())
records_without_patient = 0
records_without_visit = 0
for r in records:
    if not r.get('patient_id'):
        records_without_patient += 1
    if not r.get('visit_id'):
        records_without_visit += 1

# Check prescriptions
prescriptions = list(db['patients_prescription'].find())
rx_without_patient = 0
rx_without_visit = 0
rx_without_appt = 0
for rx in prescriptions:
    if not rx.get('patient_id'):
        rx_without_patient += 1
    if not rx.get('visit_id'):
        rx_without_visit += 1
    if not rx.get('appointment_id'):
        rx_without_appt += 1

# Check tooth condition records
tooth_conds = list(db['patients_toothconditionrecord'].find())
tc_without_patient = 0
tc_without_visit = 0
for tc in tooth_conds:
    if not tc.get('patient_id'):
        tc_without_patient += 1
    if not tc.get('visit_id'):
        tc_without_visit += 1

emr_report = {
    'counts': counts,
    'appointments': {
        'total': len(appts),
        'patient_orphans': appt_patient_orphans,
        'company_mismatches': appt_company_mismatch
    },
    'visits': {
        'total': len(visits),
        'patient_orphans': visit_patient_orphans,
        'appointment_orphans': visit_appt_orphans,
        'patient_appointment_mismatches': visit_patient_appt_mismatch
    },
    'clinical_notes': {
        'total': len(notes),
        'without_visit': notes_without_visit,
        'without_appointment': notes_without_appt
    },
    'treatment_plans': {
        'total': len(plans),
        'without_patient': plans_without_patient,
        'patient_orphans': plans_patient_orphans
    },
    'treatment_records': {
        'total': len(records),
        'without_patient': records_without_patient,
        'without_visit': records_without_visit
    },
    'prescriptions': {
        'total': len(prescriptions),
        'without_patient': rx_without_patient,
        'without_visit': rx_without_visit,
        'without_appointment': rx_without_appt
    },
    'tooth_condition_records': {
        'total': len(tooth_conds),
        'without_patient': tc_without_patient,
        'without_visit': tc_without_visit
    }
}

out_path = 'ashdent-back/scratch/step5_emr_report.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(emr_report, f, indent=2)

print("EMR Relationship Audit complete! Saved to", out_path)
print(json.dumps(emr_report, indent=2))

