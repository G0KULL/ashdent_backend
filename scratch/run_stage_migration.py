import sys, os, time, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections
from bson import ObjectId, Decimal128
from decimal import Decimal
from collections import defaultdict
import datetime

client = connections['default'].database.client
db = client['dental_clinic_db_migrated']

print("=" * 70)
print("ASHDENT PHASE 3.1: RE-EXECUTING SAFE MIGRATION & RESTRUCTURING")
print("Target Database: dental_clinic_db_migrated (ISOLATED)")
print("=" * 70)

start_time = time.time()
audit_log = {
    'started_at': datetime.datetime.now().isoformat(),
    'actions': [],
    'warnings': [],
    'errors': [],
    'exceptions_report': []
}

def log_action(name, details):
    entry = {'name': name, 'timestamp': datetime.datetime.now().isoformat(), 'details': details}
    audit_log['actions'].append(entry)
    print(f"[ACTION] {name}: {details}")

# -------------------------------------------------------------
# STEP 2.1: CREATE ARCHIVE SNAPSHOTS FOR RETIRED / RAW COLLECTIONS
# -------------------------------------------------------------
print("\n--- STEP 2.1: CREATING ARCHIVE SNAPSHOTS ---")

# 1. Archive raw treatment plan items
raw_items_count = db['patients_treatmentplanitem'].count_documents({})
raw_items = list(db['patients_treatmentplanitem'].find())
db['archived_treatmentplanitems_raw'].drop()
if raw_items:
    db['archived_treatmentplanitems_raw'].insert_many(raw_items)
log_action("archive_raw_treatment_plan_items", f"Archived {len(raw_items)} items to archived_treatmentplanitems_raw")

# 2. Archive legacy payments
legacy_pay_count = db['patients_payment'].count_documents({})
raw_payments = list(db['patients_payment'].find())
db['archived_legacy_payments'].drop()
if raw_payments:
    db['archived_legacy_payments'].insert_many(raw_payments)
log_action("archive_legacy_payments", f"Archived {len(raw_payments)} records to archived_legacy_payments")

# 3. Retire patients_clinicsubscription
sub_count = db['patients_clinicsubscription'].count_documents({})
subs = list(db['patients_clinicsubscription'].find())
db['archived_clinicsubscription'].drop()
if subs:
    db['archived_clinicsubscription'].insert_many(subs)
db['patients_clinicsubscription'].drop()
log_action("retire_clinicsubscription", f"Archived {sub_count} doc to archived_clinicsubscription and dropped patients_clinicsubscription")

# 4. Retire empty junction patients_patient_groups
pg_count = db['patients_patient_groups'].count_documents({})
db['patients_patient_groups'].drop()
log_action("retire_patient_groups_junction", f"Dropped empty unused junction collection patients_patient_groups (count: {pg_count})")

# -------------------------------------------------------------
# STEP 2.2: DEDUPLICATE patients_treatmentplanitem WITH PRICE VETTING
# -------------------------------------------------------------
print("\n--- STEP 2.2: DEDUPLICATING TREATMENT PLAN ITEMS (PRICE-VETTED) ---")

cursor = db['patients_treatmentplanitem'].find().sort([('created_at', 1), ('_id', 1)])
groups = defaultdict(list)

for item in cursor:
    plan_id = str(item.get('plan_id'))
    tooth_number = str(item.get('tooth_number', ''))
    procedure_name = str(item.get('procedure_name', '')).strip().lower()
    surface = str(item.get('surface', ''))
    status = str(item.get('status', ''))
    
    key = (plan_id, tooth_number, procedure_name, surface, status)
    groups[key].append(item)

unique_items = []
duplicate_count = 0
dedup_audit = []

for key, items in groups.items():
    if len(items) == 1:
        unique_items.append(items[0])
        continue
    
    duplicate_count += (len(items) - 1)
    
    # 1. Check if authorized doctor price override exists with audit metadata
    override_item = next((it for it in items if it.get('price_override_reason') or it.get('price_modified_by_id')), None)
    
    # Check if there is price divergence in this group
    costs = set(str(it.get('estimated_cost')) for it in items)
    
    if override_item:
        selected_item = override_item
        reason = "Preserved authorized doctor price override with audit metadata"
    elif len(costs) > 1:
        # 2. Look up catalogue price from TreatmentMaster
        tm_id = items[0].get('treatment_master_id')
        tm = db['patients_treatmentmaster'].find_one({'_id': tm_id}) if tm_id else None
        cat_price = str(tm.get('price')) if tm else None
        
        # 3. Look for item whose estimated_cost matches standard catalogue price / snapshot
        std_price_item = None
        for it in items:
            est_cost_str = str(it.get('estimated_cost'))
            snap_str = str(it.get('standard_price_snapshot'))
            if (cat_price and est_cost_str == cat_price) or (snap_str and est_cost_str == snap_str):
                std_price_item = it
                break
                
        if std_price_item:
            selected_item = std_price_item
            reason = f"Selected catalogue standard price {cat_price or std_price_item.get('standard_price_snapshot')} (suppressed runaway insertion error {costs - {str(selected_item.get('estimated_cost'))}})"
        else:
            selected_item = items[0]
            reason = "Retained earliest record (no catalogue price match established)"
    else:
        selected_item = items[0]
        reason = "Identical duplicate group, retained earliest record"
        
    unique_items.append(selected_item)
    
    # Record audit log for groups with duplicates or price divergence
    dedup_audit.append({
        'plan_id': key[0],
        'tooth_number': key[1],
        'procedure_name': key[2],
        'surface': key[3],
        'status': key[4],
        'total_original_items': len(items),
        'original_prices': list(costs),
        'selected_item_id': str(selected_item['_id']),
        'selected_price': str(selected_item.get('estimated_cost')),
        'standard_price_snapshot': str(selected_item.get('standard_price_snapshot')),
        'reason': reason
    })

# Replace active collection with vetted unique items
db['patients_treatmentplanitem'].drop()
if unique_items:
    db['patients_treatmentplanitem'].insert_many(unique_items)

# Recalculate total_estimated_cost on affected patients_treatmentplan
plan_totals = defaultdict(Decimal)
for it in unique_items:
    pid = it.get('plan_id')
    cost_val = Decimal(str(it.get('final_cost') or it.get('estimated_cost') or 0))
    plan_totals[pid] += cost_val

for pid, tot in plan_totals.items():
    db['patients_treatmentplan'].update_one(
        {'_id': pid},
        {'$set': {'total_estimated_cost': Decimal128(str(tot))}}
    )

with open('ashdent-back/scratch/treatment_plan_deduplication_audit.json', 'w', encoding='utf-8') as f:
    json.dump(dedup_audit, f, indent=2)

log_action("deduplicate_treatment_plan_items", {
    "original_count": raw_items_count,
    "unique_preserved": len(unique_items),
    "duplicates_archived": duplicate_count,
    "divergent_groups_corrected": len([a for a in dedup_audit if len(a['original_prices']) > 1])
})

# -------------------------------------------------------------
# STEP 2.3: BACKFILL HISTORICAL RECORDS
# -------------------------------------------------------------
print("\n--- STEP 2.3: BACKFILLING HISTORICAL COMPANY & BRANCH POINTERS ---")

default_company = db['patients_company'].find_one({'is_active': True})
default_company_id = default_company['_id'] if default_company else None
default_branch = db['patients_branch'].find_one({'company_id': default_company_id, 'is_active': True})
default_branch_id = default_branch['_id'] if default_branch else None

patients_map = {str(p['_id']): p for p in db['patients_patient'].find()}

# 1. Backfill patients_billing
bills_updated = 0
for b in db['patients_billing'].find({'company_id': None}):
    pid = str(b.get('patient_id'))
    p = patients_map.get(pid)
    c_id = p.get('company_id') if p else default_company_id
    b_id = p.get('registration_branch_id') if p else default_branch_id
    db['patients_billing'].update_one(
        {'_id': b['_id']},
        {'$set': {'company_id': c_id, 'branch_id': b_id}}
    )
    bills_updated += 1
log_action("backfill_billing_tenants", f"Backfilled company/branch on {bills_updated} historical billing records")

# 2. Backfill patients_visit
visits_updated = 0
for v in db['patients_visit'].find({'company_id': None}):
    pid = str(v.get('patient_id'))
    p = patients_map.get(pid)
    c_id = p.get('company_id') if p else default_company_id
    b_id = p.get('registration_branch_id') if p else default_branch_id
    db['patients_visit'].update_one(
        {'_id': v['_id']},
        {'$set': {'company_id': c_id, 'branch_id': b_id}}
    )
    visits_updated += 1
log_action("backfill_visit_tenants", f"Backfilled company/branch on {visits_updated} historical visit records")

# 3. Backfill patients_prescription
rx_updated = 0
for rx in db['patients_prescription'].find({'company_id': None}):
    pid = str(rx.get('patient_id'))
    p = patients_map.get(pid)
    c_id = p.get('company_id') if p else default_company_id
    b_id = p.get('registration_branch_id') if p else default_branch_id
    db['patients_prescription'].update_one(
        {'_id': rx['_id']},
        {'$set': {'company_id': c_id, 'branch_id': b_id}}
    )
    rx_updated += 1
log_action("backfill_prescription_tenants", f"Backfilled company/branch on {rx_updated} historical prescription records")

# 4. Backfill patients_doctor
docs_updated = 0
for d in db['patients_doctor'].find({'company_id': None}):
    db['patients_doctor'].update_one(
        {'_id': d['_id']},
        {'$set': {'company_id': default_company_id, 'primary_branch_id': default_branch_id}}
    )
    docs_updated += 1
log_action("backfill_doctor_tenants", f"Backfilled company/branch on {docs_updated} historical doctor profiles")

# -------------------------------------------------------------
# STEP 2.4: CONSOLIDATE LEGACY PAYMENTS WITH ZERO CROSS-PATIENT LEAK
# -------------------------------------------------------------
print("\n--- STEP 2.4: CONSOLIDATING LEGACY PAYMENTS (ZERO CROSS-PATIENT LEAK) ---")

existing_bp_receipts = set(db['patients_billpayment'].distinct('receipt_number'))
legacy_merged = 0
consultation_bills_created = 0

for lp in db['patients_payment'].find():
    pid = lp.get('patient_id')
    vid = lp.get('visit_id')
    raw_amount = lp.get('paid_amount') or lp.get('amount') or 0
    amount = Decimal128(str(raw_amount))
    
    # 1. Retrieve & validate exact patient
    patient = db['patients_patient'].find_one({'_id': pid}) if pid else None
    if not patient:
        audit_log['exceptions_report'].append({
            'payment_id': str(lp['_id']),
            'error': f"Orphan payment: patient {pid} not found in database."
        })
        continue
        
    p_company_id = patient.get('company_id') or default_company_id
    p_branch_id = patient.get('registration_branch_id') or default_branch_id
    
    # 2. Retrieve & validate exact visit
    visit = db['patients_visit'].find_one({'_id': vid}) if vid else None
    if visit and str(visit.get('patient_id')) != str(pid):
        audit_log['exceptions_report'].append({
            'payment_id': str(lp['_id']),
            'error': f"Cross-patient mismatch: visit {vid} belongs to patient {visit.get('patient_id')}, not {pid}."
        })
        continue
        
    # 3. Search for legitimate existing consultation/visit bill strictly for THIS patient
    bill = None
    if vid:
        bill = db['patients_billing'].find_one({'visit_id': vid, 'patient_id': pid})
    if not bill and pid:
        bill = db['patients_billing'].find_one({'patient_id': pid, 'bill_type': 'Consultation'})
        
    # 4. If no bill exists, create a dedicated Consultation bill for this exact patient
    if not bill:
        new_inv_num = f"INV-LEGACY-{str(lp['_id'])[-6:].upper()}"
        existing_bill = db['patients_billing'].find_one({'invoice_number': new_inv_num})
        if existing_bill:
            bill = existing_bill
        else:
            bill = {
                '_id': ObjectId(),
                'invoice_number': new_inv_num,
                'bill_type': 'Consultation',
                'patient_id': pid,
                'visit_id': vid,
                'company_id': p_company_id,
                'branch_id': p_branch_id,
                'doctor_id': lp.get('doctor_id') or (visit.get('doctor_id') if visit else None) or patient.get('doctor_id'),
                'subtotal': amount,
                'discount_total': Decimal128('0.00'),
                'tax_total': Decimal128('0.00'),
                'total_amount': amount,
                'paid_amount': amount,
                'cash_received': amount,
                'balance_returned': Decimal128('0.00'),
                'balance_amount': Decimal128('0.00'),
                'payment_method': lp.get('payment_method') or 'Cash',
                'status': 'Paid',
                'is_invoice': True,
                'notes': f"Auto-generated consultation invoice for legacy payment {lp['_id']}",
                'created_at': lp.get('created_at') or lp.get('payment_date') or datetime.datetime.now(),
            }
            db['patients_billing'].insert_one(bill)
            consultation_bills_created += 1
            
    # 5. Insert traceable BillPayment
    receipt_num = f"RCP-LEGACY-{str(lp['_id'])[-6:].upper()}"
    if receipt_num not in existing_bp_receipts:
        new_bp = {
            'billing_id': bill['_id'],
            'patient_id': pid,
            'company_id': bill.get('company_id') or p_company_id,
            'branch_id': bill.get('branch_id') or p_branch_id,
            'amount': amount,
            'payment_method': lp.get('payment_method') or 'Cash',
            'payment_type': 'DIRECT',
            'receipt_number': receipt_num,
            'transaction_reference': str(lp['_id']),
            'notes': f"Consolidated from legacy visit payment record {lp['_id']}",
            'created_at': lp.get('created_at') or lp.get('payment_date') or datetime.datetime.now(),
            'updated_at': datetime.datetime.now()
        }
        db['patients_billpayment'].insert_one(new_bp)
        existing_bp_receipts.add(receipt_num)
        legacy_merged += 1

log_action("consolidate_legacy_payments", {
    "total_legacy_payments_processed": len(raw_payments),
    "consultation_bills_created": consultation_bills_created,
    "billpayments_created": legacy_merged,
    "exceptions_count": len(audit_log['exceptions_report'])
})

# -------------------------------------------------------------
# STEP 2.5: CREATE PERFORMANCE INDEXES
# -------------------------------------------------------------
print("\n--- STEP 2.5: CREATING PERFORMANCE INDEXES ---")

db['patients_treatmentplanitem'].create_index([('plan_id', 1)], name='treatmentplanitem_plan_id_idx')
db['patients_billing'].create_index([('company_id', 1), ('created_at', -1)], name='billing_company_created_idx')
db['patients_appointment'].create_index([('doctor_id', 1), ('date', 1), ('time', 1)], name='appointment_doc_datetime_idx')
db['patients_patient'].create_index([('company_id', 1), ('phone', 1)], name='patient_company_phone_idx')
log_action("create_indexes", "Verified 4 performance indexes on target database")

elapsed = time.time() - start_time
audit_log['completed_at'] = datetime.datetime.now().isoformat()
audit_log['elapsed_seconds'] = elapsed

with open('ashdent-back/scratch/migration_execution_audit.json', 'w', encoding='utf-8') as f:
    json.dump(audit_log, f, indent=2)

print("\n" + "=" * 70)
print(f"STAGE 2 MIGRATION COMPLETED IN {elapsed:.2f} SECONDS!")
print("Full audit written to ashdent-back/scratch/migration_execution_audit.json")
print("=" * 70)
