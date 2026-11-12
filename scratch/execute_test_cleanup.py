import os, sys, json, pymongo
from bson import ObjectId

client = pymongo.MongoClient('mongodb://localhost:27017/')
src = client['dental_clinic_db']
mig = client['dental_clinic_db_migrated']

print("=" * 80)
print("BLOCKER 2: CONTROLLED SYNTHETIC TEST DATA CLEANUP")
print("Target Database: dental_clinic_db_migrated")
print("=" * 80)

# Safety check: confirm production database is not modified
prod_item_count = src['patients_treatmentplanitem'].count_documents({})
print(f"Safety check: dental_clinic_db patients_treatmentplanitem count = {prod_item_count} (must be 56,644)")
if prod_item_count != 56644:
    print("[ERROR] Production DB unexpected count! Aborting.")
    sys.exit(1)

# Pre-cleanup counts in target
pre_counts = {
    'patients_patient': mig['patients_patient'].count_documents({}),
    'patients_appointment': mig['patients_appointment'].count_documents({}),
    'patients_visit': mig['patients_visit'].count_documents({}),
    'patients_clinicalnotes': mig['patients_clinicalnotes'].count_documents({}),
    'patients_toothconditionrecord': mig['patients_toothconditionrecord'].count_documents({}),
    'patients_treatmentplan': mig['patients_treatmentplan'].count_documents({}),
    'patients_treatmentplanitem': mig['patients_treatmentplanitem'].count_documents({}),
    'patients_estimate': mig['patients_estimate'].count_documents({}),
    'patients_prescription': mig['patients_prescription'].count_documents({}),
    'patients_prescriptionitem': mig['patients_prescriptionitem'].count_documents({}),
    'patients_billing': mig['patients_billing'].count_documents({}),
    'patients_billpayment': mig['patients_billpayment'].count_documents({}),
    'patients_slot_lock': mig['patients_slot_lock'].count_documents({})
}

print("\nPre-cleanup target counts:")
for k, v in pre_counts.items():
    print(f"  {k:30}: {v}")

# Exact records to delete
arthur_id = ObjectId('6aeef65ef054fbd01ad70dd3')

deletion_log = []

def delete_by_id(coll_name, doc_id, reason):
    coll = mig[coll_name]
    query = {'_id': ObjectId(doc_id)} if ObjectId.is_valid(str(doc_id)) else {'_id': str(doc_id)}
    doc = coll.find_one(query)
    if doc:
        coll.delete_one(query)
        deletion_log.append({
            'collection': coll_name,
            'id': str(doc_id),
            'status': 'DELETED',
            'reason': reason
        })
        print(f"  [DELETED] {coll_name:30} | ID: {doc_id} | {reason}")
    else:
        deletion_log.append({
            'collection': coll_name,
            'id': str(doc_id),
            'status': 'NOT_FOUND',
            'reason': reason
        })
        print(f"  [NOT FOUND] {coll_name:30} | ID: {doc_id}")

print("\nExecuting record deletion for Arthur Dentist test suite...")

# Patient & appointment & encounter
delete_by_id('patients_patient', '6aeef65ef054fbd01ad70dd3', 'Arthur Dentist synthetic patient')
delete_by_id('patients_appointment', '6aeef65ef054fbd01ad70dd4', 'Arthur Dentist test appointment (2026-11-20)')
delete_by_id('patients_communicationlog', '6aeef65ef054fbd01ad70dd5', 'Arthur Dentist communication log')
delete_by_id('patients_visit', '6aeef65ef054fbd01ad70dd6', 'Arthur Dentist visit encounter')
delete_by_id('patients_clinicalnotes', '6aeef65ef054fbd01ad70dd7', 'Arthur Dentist clinical notes')
delete_by_id('patients_toothconditionrecord', '6aeef65ef054fbd01ad70dd8', 'Arthur Dentist tooth condition record (46)')
delete_by_id('patients_emrchangelog', '6aeef65ef054fbd01ad70dd9', 'Arthur Dentist emr change log 1')
delete_by_id('patients_emrchangelog', '6aeef65ff054fbd01ad70ddf', 'Arthur Dentist emr change log 2')

# Treatment plan & items
delete_by_id('patients_treatmentplan', '6aeef65ef054fbd01ad70ddc', 'Arthur Dentist treatment plan')
delete_by_id('patients_treatmentplanitem', '6aeef65ff054fbd01ad70ddd', 'Arthur Dentist treatment plan item 1 (Tooth 46 RCT)')
delete_by_id('patients_treatmentplanitem', '6aeef65ff054fbd01ad70dde', 'Arthur Dentist treatment plan item 2 (Tooth 46 Crown)')

# Estimate
delete_by_id('patients_estimate', '6aeef65ff054fbd01ad70de0', 'Arthur Dentist estimate')

# Prescription & items
delete_by_id('patients_prescription', '6aeef65ff054fbd01ad70de5', 'Arthur Dentist prescription')
delete_by_id('patients_prescriptionitem', '6aeef65ff054fbd01ad70de6', 'Arthur Dentist prescription item (Amoxicillin)')
delete_by_id('patients_prescriptionitem', '6aeef65ff054fbd01ad70de7', 'Arthur Dentist prescription item (Ketorolac)')

# Billing & payments
delete_by_id('patients_billing', '6aeef65ff054fbd01ad70de8', 'Arthur Dentist test billing invoice')
delete_by_id('patients_billpayment', '6aeef65ff054fbd01ad70deb', 'Arthur Dentist partial payment (RCP-BR_ALPHA_MAIN-1001)')
delete_by_id('patients_billpayment', '6aeef65ff054fbd01ad70ded', 'Arthur Dentist final payment (RCP-BR_ALPHA_MAIN-1002)')
delete_by_id('patients_transaction', '6aeef65ff054fbd01ad70dec', 'Arthur Dentist ledger transaction 1')
delete_by_id('patients_transaction', '6aeef65ff054fbd01ad70dee', 'Arthur Dentist ledger transaction 2')

# Slot lock
delete_by_id('patients_slot_lock', 'slot_6aeef65cf054fbd01ad70dc8_2026-11-20_10:00', 'Arthur Dentist appointment slot lock')

# Post-cleanup counts
post_counts = {
    'patients_patient': mig['patients_patient'].count_documents({}),
    'patients_appointment': mig['patients_appointment'].count_documents({}),
    'patients_visit': mig['patients_visit'].count_documents({}),
    'patients_clinicalnotes': mig['patients_clinicalnotes'].count_documents({}),
    'patients_toothconditionrecord': mig['patients_toothconditionrecord'].count_documents({}),
    'patients_treatmentplan': mig['patients_treatmentplan'].count_documents({}),
    'patients_treatmentplanitem': mig['patients_treatmentplanitem'].count_documents({}),
    'patients_estimate': mig['patients_estimate'].count_documents({}),
    'patients_prescription': mig['patients_prescription'].count_documents({}),
    'patients_prescriptionitem': mig['patients_prescriptionitem'].count_documents({}),
    'patients_billing': mig['patients_billing'].count_documents({}),
    'patients_billpayment': mig['patients_billpayment'].count_documents({}),
    'patients_slot_lock': mig['patients_slot_lock'].count_documents({})
}

print("\n" + "=" * 80)
print("POST-CLEANUP VALIDATION OF EXPECTED COUNTS:")
print("=" * 80)
expected_targets = {
    'patients_treatmentplanitem': 123,
    'patients_billpayment': 36,
    'patients_billing': 44
}

all_counts_valid = True
for k, exp in expected_targets.items():
    actual = post_counts[k]
    match = (actual == exp)
    print(f"[{'PASS' if match else 'FAIL'}] {k:30}: Actual = {actual}, Expected = {exp}")
    if not match:
        all_counts_valid = False

# Re-verify that 9 legacy payments remain untouched
legacy_bp_count = mig['patients_billpayment'].count_documents({'receipt_number': {'$regex': '^RCP-LEGACY'}})
print(f"[{'PASS' if legacy_bp_count == 9 else 'FAIL'}] Migrated legacy payments: {legacy_bp_count} (Expected 9)")

# Re-verify 83 price corrections
with open('ashdent-back/scratch/treatment_plan_deduplication_audit.json', 'r') as f:
    dedup_audit = json.load(f)
divergent = [g for g in dedup_audit if len(g.get('original_prices', [])) > 1]
prices_correct = True
for g in divergent:
    chosen_id = g.get('selected_item_id')
    doc = mig['patients_treatmentplanitem'].find_one({'_id': ObjectId(chosen_id)})
    if not doc or float(str(doc.get('estimated_cost', 0))) != 1500.0:
        prices_correct = False
        break
print(f"[{'PASS' if prices_correct else 'FAIL'}] All 83 composite filling price corrections intact: {prices_correct}")

# Save audit log
with open('ashdent-back/scratch/cleanup_execution_audit.json', 'w') as f:
    json.dump({
        'pre_counts': pre_counts,
        'post_counts': post_counts,
        'deletions': deletion_log,
        'all_counts_valid': all_counts_valid,
        'legacy_payments_intact': (legacy_bp_count == 9),
        'prices_intact': prices_correct
    }, f, indent=2)

print(f"\nCleanup execution audit saved to ashdent-back/scratch/cleanup_execution_audit.json")

