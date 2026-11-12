import os, sys, datetime, json, pymongo
from bson import ObjectId

client = pymongo.MongoClient('mongodb://localhost:27017/')

# Create disposable test databases for simulation
sim_cutover_db = 'dental_clinic_db_sim_cutover'
sim_baseline_db = 'dental_clinic_db_sim_baseline'

for db_name in [sim_cutover_db, sim_baseline_db]:
    if db_name in client.list_database_names():
        client.drop_database(db_name)

# Clone migrated DB into both disposable simulation databases
mig = client['dental_clinic_db_migrated']
db_cutover = client[sim_cutover_db]
db_baseline = client[sim_baseline_db]

print(f"Cloning {mig.name} -> {sim_cutover_db} and {sim_baseline_db}...")
for c in mig.list_collection_names():
    docs = list(mig[c].find({}))
    if docs:
        db_cutover[c].insert_many([dict(d) for d in docs])
        db_baseline[c].insert_many([dict(d) for d in docs])

print("Simulation databases prepared.")

# Record cutover timestamp
cutover_time = datetime.datetime.now()

print("\n" + "=" * 80)
print("SIMULATING 15 OPERATIONAL LIVE TRANSACTIONS IN CUTOVER DB")
print(f"Cutover Timestamp: {cutover_time.isoformat()}")
print("=" * 80)

sim_log = []

# 1. New patient registration
p_id = ObjectId()
db_cutover['patients_patient'].insert_one({
    '_id': p_id,
    'name': 'Delta Test Patient',
    'phone': '9111122222',
    'created_at': datetime.datetime.now()
})
sim_log.append(('1. New patient registration', 'patients_patient', p_id, 'INSERT'))

# 2. New appointment
appt_id = ObjectId()
db_cutover['patients_appointment'].insert_one({
    '_id': appt_id,
    'patient_id': p_id,
    'date': '2026-11-25',
    'time': '11:00',
    'status': 'Booked',
    'created_at': datetime.datetime.now()
})
sim_log.append(('2. New appointment', 'patients_appointment', appt_id, 'INSERT'))

# 3. Updated clinical note (on an existing patient/appt)
existing_note = db_cutover['patients_clinicalnotes'].find_one({})
note_id = existing_note['_id'] if existing_note else None
if note_id:
    # Notice: ClinicalNotes has NO updated_at field in schema!
    db_cutover['patients_clinicalnotes'].update_one(
        {'_id': note_id},
        {'$set': {'notes': 'UPDATED LIVE NOTES POST-CUTOVER'}}
    )
sim_log.append(('3. Updated clinical note', 'patients_clinicalnotes', note_id, 'UPDATE (No updated_at)'))

# 4. Updated tooth condition
existing_tc = db_cutover['patients_toothconditionrecord'].find_one({})
tc_id = existing_tc['_id'] if existing_tc else None
if tc_id:
    db_cutover['patients_toothconditionrecord'].update_one(
        {'_id': tc_id},
        {'$set': {'condition': ['Caries Restored'], 'updated_at': datetime.datetime.now()}}
    )
sim_log.append(('4. Updated tooth condition', 'patients_toothconditionrecord', tc_id, 'UPDATE (Has updated_at)'))

# 5. New treatment plan and items
plan_id = ObjectId()
db_cutover['patients_treatmentplan'].insert_one({
    '_id': plan_id,
    'patient_id': p_id,
    'title': 'Delta Restorative Plan',
    'total_estimated_cost': 4500.0,
    'created_at': datetime.datetime.now(),
    'updated_at': datetime.datetime.now()
})
tpi_id = ObjectId()
db_cutover['patients_treatmentplanitem'].insert_one({
    '_id': tpi_id,
    'plan_id': plan_id,
    'tooth_number': 14,
    'procedure_name': 'Crown',
    'estimated_cost': 4500.0,
    'created_at': datetime.datetime.now(),
    'updated_at': datetime.datetime.now()
})
sim_log.append(('5. New treatment plan & item', 'patients_treatmentplan', plan_id, 'INSERT'))

# 6. New investigation and attachment
inv_id = ObjectId()
db_cutover['patients_patientinvestigation'].insert_one({
    '_id': inv_id,
    'patient_id': p_id,
    'status': 'Completed',
    'created_at': datetime.datetime.now(),
    'updated_at': datetime.datetime.now()
})
att_id = ObjectId()
db_cutover['patients_investigationattachment'].insert_one({
    '_id': att_id,
    'investigation_id': inv_id,
    'file_name': 'delta_xray.png'
    # Notice: NO created_at / updated_at in model!
})
sim_log.append(('6. New investigation & attachment', 'patients_patientinvestigation', inv_id, 'INSERT'))

# 7. New prescription and items
rx_id = ObjectId()
db_cutover['patients_prescription'].insert_one({
    '_id': rx_id,
    'patient_id': p_id,
    'created_at': datetime.datetime.now()
})
rxi_id = ObjectId()
db_cutover['patients_prescriptionitem'].insert_one({
    '_id': rxi_id,
    'prescription_id': rx_id,
    'medicine_name': 'Paracetamol'
    # Notice: NO created_at / updated_at in model!
})
sim_log.append(('7. New prescription & items', 'patients_prescription', rx_id, 'INSERT'))

# 8. New estimate
est_id = ObjectId()
db_cutover['patients_estimate'].insert_one({
    '_id': est_id,
    'patient_id': p_id,
    'total_amount': 4500.0,
    'created_at': datetime.datetime.now(),
    'updated_at': datetime.datetime.now()
})
sim_log.append(('8. New estimate', 'patients_estimate', est_id, 'INSERT'))

# 9. New invoice
bill_id = ObjectId()
db_cutover['patients_billing'].insert_one({
    '_id': bill_id,
    'patient_id': p_id,
    'total_amount': 5000.0,
    'paid_amount': 0.0,
    'balance_amount': 5000.0,
    'status': 'Pending',
    'created_at': datetime.datetime.now()
})
sim_log.append(('9. New invoice', 'patients_billing', bill_id, 'INSERT'))

# 10. Partial payment
bp1_id = ObjectId()
db_cutover['patients_billpayment'].insert_one({
    '_id': bp1_id,
    'billing_id': bill_id,
    'patient_id': p_id,
    'amount': 2000.0,
    'receipt_number': 'RCP-DELTA-01',
    'created_at': datetime.datetime.now()
})
db_cutover['patients_billing'].update_one(
    {'_id': bill_id},
    {'$set': {'paid_amount': 2000.0, 'balance_amount': 3000.0, 'status': 'Partial'}} # NO updated_at!
)
sim_log.append(('10. Partial payment', 'patients_billpayment', bp1_id, 'INSERT + Billing UPDATE'))

# 11. Full payment
bp2_id = ObjectId()
db_cutover['patients_billpayment'].insert_one({
    '_id': bp2_id,
    'billing_id': bill_id,
    'patient_id': p_id,
    'amount': 3000.0,
    'receipt_number': 'RCP-DELTA-02',
    'created_at': datetime.datetime.now()
})
db_cutover['patients_billing'].update_one(
    {'_id': bill_id},
    {'$set': {'paid_amount': 5000.0, 'balance_amount': 0.0, 'status': 'Paid'}} # NO updated_at!
)
sim_log.append(('11. Full payment', 'patients_billpayment', bp2_id, 'INSERT + Billing UPDATE'))

# 12. Payment reversal
rev_bp = db_cutover['patients_billpayment'].find_one({'_id': bp2_id})
db_cutover['patients_billpayment'].update_one(
    {'_id': bp2_id},
    {'$set': {'payment_type': 'Refund', 'notes': 'Reversed payment'}} # NO updated_at on BillPayment!
)
sim_log.append(('12. Payment update/reversal', 'patients_billpayment', bp2_id, 'UPDATE (No updated_at)'))

# 13. Deleted appointment (Hard delete of existing appointment)
existing_appt = db_cutover['patients_appointment'].find_one({'_id': {'$ne': appt_id}})
del_appt_id = existing_appt['_id'] if existing_appt else None
if del_appt_id:
    db_cutover['patients_appointment'].delete_one({'_id': del_appt_id})
sim_log.append(('13. Deleted appointment', 'patients_appointment', del_appt_id, 'DELETE (Hard Delete)'))

# 14. Deleted or soft-deleted clinical record
existing_visit = db_cutover['patients_visit'].find_one({})
del_visit_id = existing_visit['_id'] if existing_visit else None
if del_visit_id:
    db_cutover['patients_visit'].delete_one({'_id': del_visit_id})
sim_log.append(('14. Deleted clinical record', 'patients_visit', del_visit_id, 'DELETE (Hard Delete)'))

# 15. Updated invoice or receipt sequence
seq_doc = db_cutover['patients_autonumbersequence'].find_one({'prefix': 'receipt'}) if 'patients_autonumbersequence' in db_cutover.list_collection_names() else None
if seq_doc:
    db_cutover['patients_autonumbersequence'].update_one(
        {'_id': seq_doc['_id']},
        {'$inc': {'last_number': 2}}
    )
    sim_log.append(('15. Updated receipt sequence', 'patients_autonumbersequence', seq_doc['_id'], 'UPDATE'))
else:
    sim_log.append(('15. Updated receipt sequence', 'patients_autonumbersequence', None, 'SKIPPED (No sequence coll)'))

print(f"Total simulated operations: {len(sim_log)}")

# Now run DeltaReconciliationEngine against sim_cutover_db and sim_baseline_db!
sys.path.insert(0, os.path.abspath('ashdent-back'))
from scratch.rollback_delta_reconciliation import DeltaReconciliationEngine

engine = DeltaReconciliationEngine(sim_cutover_db, sim_baseline_db, cutover_time)
deltas, detected_count = engine.scan_deltas()

print("\n" + "=" * 80)
print(f"DELTA SCANNER DETECTION RESULTS (Timestamp >= {cutover_time.isoformat()}):")
print("=" * 80)
print(f"Total detected documents: {detected_count}")
for c, recs in deltas.items():
    print(f"  {c:35}: {len(recs)} detected")

# Check which of the 15 simulated changes were detected vs missed
detection_results = []
for label, coll, doc_id, op in sim_log:
    detected = False
    if doc_id and coll in deltas:
        detected = any(str(r['_id']) == str(doc_id) for r in deltas[coll])
    detection_results.append({
        'operation': label,
        'collection': coll,
        'doc_id': str(doc_id) if doc_id else 'N/A',
        'type': op,
        'detected_by_timestamp_query': detected
    })
    print(f"[{'DETECTED' if detected else 'MISSED  '}] {label:35} | Type: {op:24} | ID: {doc_id}")

with open('ashdent-back/scratch/rollback_15_test_results.json', 'w') as f:
    json.dump({
        'cutover_time': cutover_time.isoformat(),
        'detected_count': detected_count,
        'simulated_operations': detection_results
    }, f, indent=2)

# Clean up simulation DBs
client.drop_database(sim_cutover_db)
client.drop_database(sim_baseline_db)
print("\nSimulation databases cleanly dropped.")

