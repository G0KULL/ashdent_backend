import os, sys, json, pymongo
from bson import ObjectId

client = pymongo.MongoClient('mongodb://localhost:27017/')
src = client['dental_clinic_db']
mig = client['dental_clinic_db_migrated']

test_records_spec = [
    ('patients_patient', '6aeef65ef054fbd01ad70dd3', 'Patient Arthur Dentist'),
    ('patients_appointment', '6aeef65ef054fbd01ad70dd4', 'Appointment on 2026-11-20'),
    ('patients_slot_lock', '6aeef65ef054fbd01ad70dd5', 'Slot lock for Arthur Dentist appt'),
    ('patients_visit', '6aeef65ef054fbd01ad70dd6', 'Visit encounter for Arthur Dentist'),
    ('patients_clinicalnotes', '6aeef65ef054fbd01ad70dd7', 'Clinical notes for Arthur Dentist'),
    ('patients_toothcondition', '6aeef65ef054fbd01ad70dd8', 'Tooth 46 condition'),
    ('patients_treatmentplan', '6aeef65ef054fbd01ad70ddc', 'Treatment plan for Arthur Dentist'),
    ('patients_treatmentplanitem', '6aeef65ef054fbd01ad70ddd', 'Treatment item 1 (Tooth 46 RCT)'),
    ('patients_treatmentplanitem', '6aeef65ef054fbd01ad70dde', 'Treatment item 2 (Tooth 46 Crown)'),
    ('patients_estimate', '6aeef65ff054fbd01ad70de0', 'Estimate for Arthur Dentist'),
    ('patients_treatmentrecord', '6aeef65ff054fbd01ad70de5', 'Treatment record for Tooth 46'),
    ('patients_prescription', '6aeef65ff054fbd01ad70de6', 'Prescription for Arthur Dentist'),
    ('patients_prescriptionitem', '6aeef65ff054fbd01ad70de7', 'Prescription item (Amoxicillin)'),
    ('patients_billing', '6aeef65ff054fbd01ad70de8', 'Invoice for Arthur Dentist'),
    ('patients_billpayment', '6aeef65ff054fbd01ad70de9', 'BillPayment partial (₹4,000)'),
    ('patients_billpayment', '6aeef65ff054fbd01ad70deb', 'BillPayment final (₹8,000)')
]

preview_report = []

print("=" * 80)
print("BLOCKER 2: PRE-CLEANUP VALIDATION & PREVIEW REPORT")
print("Target: dental_clinic_db_migrated")
print("=" * 80)

for coll_name, doc_id, desc in test_records_spec:
    mig_doc = mig[coll_name].find_one({'_id': ObjectId(doc_id)})
    src_doc = src[coll_name].find_one({'_id': ObjectId(doc_id)})
    
    in_mig = mig_doc is not None
    in_src = src_doc is not None # MUST BE FALSE
    
    # Check relationships
    pt_id = None
    if mig_doc:
        pt_id = str(mig_doc.get('patient_id') or mig_doc.get('patient') or '')
        
    preview_report.append({
        'collection': coll_name,
        'id': doc_id,
        'description': desc,
        'exists_in_target_migrated': in_mig,
        'exists_in_production_src': in_src,
        'patient_ref': pt_id,
        'is_arthur_dentist': (pt_id == '6aeef65ef054fbd01ad70dd3' or doc_id == '6aeef65ef054fbd01ad70dd3')
    })
    
    print(f"[{'FOUND' if in_mig else 'MISSING'}] {coll_name:28} | ID: {doc_id} | In Prod: {in_src} | PtRef: {pt_id}")

with open('ashdent-back/scratch/cleanup_preview.json', 'w') as f:
    json.dump(preview_report, f, indent=2)

all_found_in_mig = all(r['exists_in_target_migrated'] for r in preview_report)
none_in_src = not any(r['exists_in_production_src'] for r in preview_report)
all_belong_to_arthur = all(r['is_arthur_dentist'] for r in preview_report)

print("\nPREVIEW SUMMARY:")
print(f"  All 16 exact test records present in target: {all_found_in_mig}")
print(f"  Zero records present in production:         {none_in_src}")
print(f"  All records confirmed Arthur Dentist:        {all_belong_to_arthur}")

