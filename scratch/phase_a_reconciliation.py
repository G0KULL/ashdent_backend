import os, sys, json, pymongo
from bson import ObjectId

client = pymongo.MongoClient('mongodb://localhost:27017/')
src = client['dental_clinic_db']
mig = client['dental_clinic_db_migrated']
bak = client['dental_clinic_db_migrated_pre_cleanup_backup']

print("=" * 80)
print("PHASE A: CLEANUP RECONCILIATION AUDIT")
print("=" * 80)

with open('ashdent-back/scratch/cleanup_execution_audit.json') as f:
    audit = json.load(f)

deletions = audit.get('deletions', [])
print(f"Total entries in cleanup_execution_audit.json: {len(deletions)}")

unique_colls_in_deletions = sorted(set(d['collection'] for d in deletions))
print(f"Unique collections in deletion entries: {len(unique_colls_in_deletions)}")
for c in unique_colls_in_deletions:
    cnt = sum(1 for d in deletions if d['collection'] == c)
    print(f"  {c:35}: {cnt} deletions listed")

print("\n" + "=" * 80)
print("INSPECTING EACH DELETION ENTRY AGAINST PRE-CLEANUP BACKUP & CURRENT TARGET")
print("=" * 80)

reconciliation_rows = []

for idx, entry in enumerate(deletions):
    c_name = entry['collection']
    doc_id = entry['id']
    reason = entry['reason']
    
    # Query in pre-cleanup backup to see if it existed
    q = {'_id': ObjectId(doc_id)} if ObjectId.is_valid(doc_id) else {'_id': doc_id}
    bak_doc = bak[c_name].find_one(q) if c_name in bak.list_collection_names() else None
    mig_doc = mig[c_name].find_one(q) if c_name in mig.list_collection_names() else None
    src_doc = src[c_name].find_one(q) if c_name in src.list_collection_names() else None
    
    existed_before = (bak_doc is not None)
    exists_in_current_mig = (mig_doc is not None)
    existed_in_prod = (src_doc is not None) # MUST BE FALSE
    
    # Check if it belonged to Arthur Dentist
    belonged_to_arthur = False
    if bak_doc:
        pt_ref = str(bak_doc.get('patient_id') or bak_doc.get('patient') or '')
        name_ref = str(bak_doc.get('name') or '')
        notes_ref = str(bak_doc.get('notes') or '')
        desc_ref = str(bak_doc.get('description') or '')
        if doc_id == '6aeef65ef054fbd01ad70dd3' or pt_ref == '6aeef65ef054fbd01ad70dd3' or 'Arthur' in name_ref or 'Arthur' in notes_ref or 'Arthur' in desc_ref or '2026-11-20' in str(doc_id):
            belonged_to_arthur = True
    elif 'slot' in doc_id:
        belonged_to_arthur = True # Arthur's appointment slot
        
    actually_deleted = existed_before and not exists_in_current_mig
    
    # Check current collection count in mig
    current_cnt = mig[c_name].count_documents({}) if c_name in mig.list_collection_names() else 0
    
    row = {
        'index': idx + 1,
        'collection': c_name,
        'document_id': doc_id,
        'reason': reason,
        'existed_before_cleanup': existed_before,
        'belonged_to_arthur': belonged_to_arthur,
        'exists_in_current_target': exists_in_current_mig,
        'existed_in_production': existed_in_prod,
        'actually_deleted': actually_deleted,
        'final_collection_count': current_cnt
    }
    reconciliation_rows.append(row)
    print(f"{idx+1:02d}. Coll: {c_name:30} | ID: {doc_id} | Existed: {existed_before} | Arthur: {belonged_to_arthur} | Deleted: {actually_deleted} | InProd: {existed_in_prod} | FinalCount: {current_cnt}")

with open('ashdent-back/scratch/phase_a_table.json', 'w') as f:
    json.dump(reconciliation_rows, f, indent=2)

print("\n" + "=" * 80)
print("VERIFYING FINAL DOCUMENT COUNTS ACROSS ALL TARGET COLLECTIONS")
print("=" * 80)

reported_counts = {
    'patients_treatmentplanitem': 123,
    'patients_billpayment': 36,
    'patients_billing': 44,
    'patients_patient': 25,
    'patients_appointment': 24,
    'patients_visit': 17,
    'patients_clinicalnotes': 9,
    'patients_treatmentplan': 112,
    'patients_prescription': 5,
    'patients_prescriptionitem': 7,
    'patients_estimate': 40
}

count_verification = []
for coll, expected in reported_counts.items():
    actual = mig[coll].count_documents({})
    match = (actual == expected)
    count_verification.append({
        'collection': coll,
        'expected': expected,
        'actual': actual,
        'match': match
    })
    print(f"[{'PASS' if match else 'FAIL'}] {coll:30}: Actual = {actual:3d}, Expected = {expected:3d}")

# Also check other affected collections
other_affected = [
    'patients_communicationlog',
    'patients_toothconditionrecord',
    'patients_emrchangelog',
    'patients_treatmentrecord',
    'patients_transaction',
    'patients_slot_lock'
]
print("\nOther affected collections counts in target:")
for coll in other_affected:
    cnt = mig[coll].count_documents({}) if coll in mig.list_collection_names() else 0
    bak_cnt = bak[coll].count_documents({}) if coll in bak.list_collection_names() else 0
    print(f"  {coll:30}: Target = {cnt:3d} (Pre-cleanup Backup = {bak_cnt:3d})")

# Check for any remaining references to Arthur Dentist (ObjectId '6aeef65ef054fbd01ad70dd3')
arthur_oid = ObjectId('6aeef65ef054fbd01ad70dd3')
dangling_refs = {}
for c in mig.list_collection_names():
    c_docs = list(mig[c].find({'$or': [{'patient_id': arthur_oid}, {'patient': arthur_oid}, {'patient_id': str(arthur_oid)}]}))
    if c_docs:
        dangling_refs[c] = len(c_docs)

print(f"\nDangling references to Arthur Dentist in target DB: {dangling_refs} (Must be empty)")

