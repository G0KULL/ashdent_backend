import sys, os, hashlib, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections

client = connections['default'].database.client
src_db = client['dental_clinic_db']
tgt_db = client['dental_clinic_db_migrated']

print("=" * 80)
print("PHASE 3.1: POST-MIGRATION DATA INTEGRITY & AUDIT VERIFICATION")
print("Comparing Source [dental_clinic_db] vs Target [dental_clinic_db_migrated]")
print("=" * 80)

results = {
    "checks_passed": 0,
    "checks_failed": 0,
    "details": []
}

def record_check(name, passed, message):
    status = "PASS" if passed else "FAIL"
    if passed:
        results["checks_passed"] += 1
    else:
        results["checks_failed"] += 1
    results["details"].append({"name": name, "status": status, "message": message})
    print(f"[{status}] {name}: {message}")

# 1. Verify Production DB was NOT modified
src_item_count = src_db['patients_treatmentplanitem'].count_documents({})
record_check(
    "production_db_isolation",
    src_item_count == 56644,
    f"Source DB untouched: patients_treatmentplanitem count is {src_item_count}"
)

# 2. Check Document Counts on Core Clinical Collections
core_collections = [
    'patients_patient',
    'patients_appointment',
    'patients_visit',
    'patients_clinicalnotes',
    'patients_treatmentplan',
    'patients_prescription',
    'patients_prescriptionitem',
    'patients_company',
    'patients_branch',
    'patients_doctor',
    'patients_staff'
]

for col in core_collections:
    s_cnt = src_db[col].count_documents({})
    t_cnt = tgt_db[col].count_documents({})
    record_check(
        f"count_equality_{col}",
        s_cnt == t_cnt,
        f"Source: {s_cnt}, Target: {t_cnt}"
    )

# 3. Deduplication and Archive Verification
raw_archived = tgt_db['archived_treatmentplanitems_raw'].count_documents({})
deduped_items = tgt_db['patients_treatmentplanitem'].count_documents({})
record_check(
    "archive_raw_treatment_plan_items",
    raw_archived == 56644,
    f"Archived raw items count: {raw_archived} (expected 56644)"
)
record_check(
    "deduplicated_treatment_plan_items",
    deduped_items == 123,
    f"Deduplicated treatment plan items: {deduped_items} (expected 123)"
)

# 4. Check SHA-256 Checksum on Patients
s_patients = list(src_db['patients_patient'].find({}, {'_id': 1, 'name': 1, 'phone': 1}).sort('_id', 1))
t_patients = list(tgt_db['patients_patient'].find({}, {'_id': 1, 'name': 1, 'phone': 1}).sort('_id', 1))
s_hash = hashlib.sha256(json.dumps([[str(p['_id']), str(p.get('name')), str(p.get('phone'))] for p in s_patients], sort_keys=True).encode()).hexdigest()
t_hash = hashlib.sha256(json.dumps([[str(p['_id']), str(p.get('name')), str(p.get('phone'))] for p in t_patients], sort_keys=True).encode()).hexdigest()
record_check(
    "patient_data_sha256_integrity",
    s_hash == t_hash,
    f"Patient hash match: {s_hash[:16]}... == {t_hash[:16]}..."
)

# 5. Check Correction 2: Divergent Pricing Fixed to Standard Catalogue (₹1,500)
sample_div_item = tgt_db['patients_treatmentplanitem'].find_one({
    'tooth_number': '36',
    'procedure_name': 'Composite Filling'
})
record_check(
    "vetted_standard_price_composite_filling",
    sample_div_item and str(sample_div_item.get('estimated_cost')) == '1500',
    f"Retained price for tooth 36 composite filling is {sample_div_item.get('estimated_cost') if sample_div_item else None} (catalogue standard: 1500)"
)

# 6. Check Zero Null Company IDs in Migrated Collections
collections_to_check_tenancy = [
    'patients_billing',
    'patients_visit',
    'patients_prescription',
    'patients_doctor',
    'patients_patient',
    'patients_appointment'
]
for col in collections_to_check_tenancy:
    null_companies = tgt_db[col].count_documents({'company_id': None})
    null_branches = tgt_db[col].count_documents({'branch_id': None}) if col not in ['patients_doctor', 'patients_patient'] else 0
    record_check(
        f"tenant_isolation_null_check_{col}",
        null_companies == 0 and null_branches == 0,
        f"Null company_id: {null_companies}, Null branch_id: {null_branches}"
    )

# 7. Check Correction 1: Legacy Payment Consolidation (Zero Cross-Patient Linkage)
orig_bp = src_db['patients_billpayment'].count_documents({})
mig_bp = tgt_db['patients_billpayment'].count_documents({})
archived_lp = tgt_db['archived_legacy_payments'].count_documents({})
record_check(
    "legacy_payment_consolidation_count",
    mig_bp == orig_bp + archived_lp and archived_lp == 9,
    f"Original BillPayments: {orig_bp}, Migrated: {mig_bp} (Consolidated +{archived_lp} legacy payments)"
)

# Check zero cross-patient attribution in bill payments
cross_patient_mismatches = 0
for bp in tgt_db['patients_billpayment'].find({'receipt_number': {'$regex': '^RCP-LEGACY-'}}):
    b = tgt_db['patients_billing'].find_one({'_id': bp['billing_id']})
    if not b or str(b.get('patient_id')) != str(bp.get('patient_id')):
        cross_patient_mismatches += 1

record_check(
    "zero_cross_patient_payment_attribution",
    cross_patient_mismatches == 0,
    f"Cross-patient payment mismatches: {cross_patient_mismatches} (must be 0)"
)

# Check zero cross-company attribution in bill payments
cross_comp_mismatches = 0
for bp in tgt_db['patients_billpayment'].find({'receipt_number': {'$regex': '^RCP-LEGACY-'}}):
    b = tgt_db['patients_billing'].find_one({'_id': bp['billing_id']})
    if not b or str(b.get('company_id')) != str(bp.get('company_id')):
        cross_comp_mismatches += 1

record_check(
    "zero_cross_company_payment_attribution",
    cross_comp_mismatches == 0,
    f"Cross-company payment mismatches: {cross_comp_mismatches} (must be 0)"
)

# 8. Check Referential Integrity (Orphan checks)
# 8a: Every treatment plan item points to an existing treatment plan
all_plan_ids = set(tgt_db['patients_treatmentplan'].distinct('_id'))
orphan_plan_items = 0
for item in tgt_db['patients_treatmentplanitem'].find():
    pid = item.get('plan_id')
    if pid not in all_plan_ids and str(pid) not in [str(x) for x in all_plan_ids]:
        orphan_plan_items += 1
record_check(
    "referential_integrity_treatment_plan_items",
    orphan_plan_items == 0,
    f"Orphan treatment plan items: {orphan_plan_items}"
)

# 8b: Every billing record points to an existing patient
all_patient_ids = set(tgt_db['patients_patient'].distinct('_id'))
orphan_bills = 0
for bill in tgt_db['patients_billing'].find():
    pid = bill.get('patient_id')
    if pid not in all_patient_ids and str(pid) not in [str(x) for x in all_patient_ids]:
        orphan_bills += 1
record_check(
    "referential_integrity_billing_patients",
    orphan_bills == 0,
    f"Orphan billing records: {orphan_bills}"
)

# 8c: Every appointment points to an existing patient and doctor
all_doc_ids = set(tgt_db['patients_doctor'].distinct('_id'))
orphan_appts = 0
for appt in tgt_db['patients_appointment'].find():
    pid = appt.get('patient_id')
    did = appt.get('doctor_id')
    p_ok = pid in all_patient_ids or str(pid) in [str(x) for x in all_patient_ids]
    d_ok = did in all_doc_ids or str(did) in [str(x) for x in all_doc_ids]
    if not (p_ok and d_ok):
        orphan_appts += 1
record_check(
    "referential_integrity_appointments",
    orphan_appts == 0,
    f"Orphan appointment records: {orphan_appts}"
)

# 9. Verify Indexes on Migrated DB
indexes_to_verify = [
    ('patients_treatmentplanitem', 'treatmentplanitem_plan_id_idx'),
    ('patients_billing', 'billing_company_created_idx'),
    ('patients_appointment', 'appointment_doc_datetime_idx'),
    ('patients_patient', 'patient_company_phone_idx')
]
for col_name, idx_name in indexes_to_verify:
    existing_idxs = tgt_db[col_name].index_information()
    record_check(
        f"index_verified_{idx_name}",
        idx_name in existing_idxs,
        f"Index {idx_name} on {col_name}: {list(existing_idxs.get(idx_name, {}).get('key', []))}"
    )

print("\n" + "=" * 80)
print(f"VERIFICATION COMPLETE: {results['checks_passed']} PASSED, {results['checks_failed']} FAILED")
print("=" * 80)

with open('ashdent-back/scratch/post_migration_verification_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)
