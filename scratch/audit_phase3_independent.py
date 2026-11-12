import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
import django; django.setup()
from django.db import connections
from bson import ObjectId

client = connections['default'].database.client
prod_db = client['dental_clinic_db']
mig_db = client['dental_clinic_db_migrated']

print("=" * 80)
print("INDEPENDENT PRE-PRODUCTION AUDIT: ASHDENT PHASE 3")
print("Target: READ-ONLY FORENSIC COMPARISON & SCRIPT AUDIT")
print("=" * 80)

audit_report = {}

# ----------------------------------------------------------------------
# 1. COLLECTION COUNTS COMPARISON
# ----------------------------------------------------------------------
print("\n[SECTION 1: DATABASE COLLECTION INVENTORIES]")
prod_cols = sorted(prod_db.list_collection_names())
mig_cols = sorted(mig_db.list_collection_names())

audit_report['prod_collection_count'] = len(prod_cols)
audit_report['mig_collection_count'] = len(mig_cols)
audit_report['collections_in_mig_not_prod'] = [c for c in mig_cols if c not in prod_cols]
audit_report['collections_in_prod_not_mig'] = [c for c in prod_cols if c not in mig_cols]

print(f"Production collections count: {len(prod_cols)}")
print(f"Migrated collections count  : {len(mig_cols)}")
print(f"Collections added in migrated (archives): {audit_report['collections_in_mig_not_prod']}")
print(f"Collections dropped in migrated: {audit_report['collections_in_prod_not_mig']}")

# ----------------------------------------------------------------------
# 2. TREATMENT PLAN ITEM DEDUPLICATION AUDIT
# ----------------------------------------------------------------------
print("\n[SECTION 2: TREATMENT PLAN DEDUPLICATION DEEP-DIVE]")

prod_items = list(prod_db['patients_treatmentplanitem'].find())
mig_items = list(mig_db['patients_treatmentplanitem'].find())
raw_archived = list(mig_db['archived_treatmentplanitems_raw'].find())

audit_report['treatment_items'] = {
    'prod_count': len(prod_items),
    'raw_archived_count': len(raw_archived),
    'mig_active_count': len(mig_items),
}

print(f"Original items in prod          : {len(prod_items)}")
print(f"Archived raw items in mig       : {len(raw_archived)}")
print(f"Active deduplicated items in mig: {len(mig_items)}")

# Check duplicate grouping key collision forensics
# Key used in migration: (str(plan_id), str(tooth_number), str(procedure_name).strip().lower(), str(surface), str(status))
from collections import defaultdict
grouped_by_key = defaultdict(list)
for item in prod_items:
    k = (
        str(item.get('plan_id')),
        str(item.get('tooth_number', '')),
        str(item.get('procedure_name', '')).strip().lower(),
        str(item.get('surface', '')),
        str(item.get('status', ''))
    )
    grouped_by_key[k].append(item)

# Check field divergence within groups
field_divergences = {
    'differing_costs': 0,
    'differing_doctors': 0,
    'differing_diagnoses': 0,
    'differing_treatment_masters': 0,
    'differing_notes': 0
}
divergence_samples = []

for k, items in grouped_by_key.items():
    if len(items) > 1:
        costs = set(str(i.get('cost') or i.get('estimated_cost') or i.get('final_cost') or '') for i in items)
        docs = set(str(i.get('doctor_id') or i.get('doctor') or '') for i in items)
        diags = set(str(i.get('diagnosis') or '') for i in items)
        tms = set(str(i.get('treatment_master_id') or i.get('treatment_master') or '') for i in items)
        notes = set(str(i.get('notes') or '') for i in items)
        
        has_div = False
        div_desc = []
        if len(costs) > 1:
            field_divergences['differing_costs'] += 1
            has_div = True
            div_desc.append(f"costs: {costs}")
        if len(docs) > 1:
            field_divergences['differing_doctors'] += 1
            has_div = True
            div_desc.append(f"doctors: {docs}")
        if len(diags) > 1:
            field_divergences['differing_diagnoses'] += 1
            has_div = True
            div_desc.append(f"diagnoses: {diags}")
        if len(tms) > 1:
            field_divergences['differing_treatment_masters'] += 1
            has_div = True
            div_desc.append(f"treatment_masters: {tms}")
            
        if has_div and len(divergence_samples) < 5:
            divergence_samples.append({
                'key': [k[0][:8] + '...', k[1], k[2], k[3], k[4]],
                'count': len(items),
                'divergences': div_desc,
                'sample_ids': [str(items[0]['_id']), str(items[-1]['_id'])]
            })

audit_report['treatment_items']['field_divergences'] = field_divergences
audit_report['treatment_items']['divergence_samples'] = divergence_samples
print(f"Unique duplicate groups found: {len(grouped_by_key)}")
print(f"Field divergences within duplicate groups: {json.dumps(field_divergences, indent=2)}")

# Check foreign key linkage to treatment plans
mig_plan_ids = set(str(p['_id']) for p in mig_db['patients_treatmentplan'].find())
orphan_items = [str(i['_id']) for i in mig_items if str(i.get('plan_id')) not in mig_plan_ids]
audit_report['treatment_items']['orphan_plan_items_in_mig'] = len(orphan_items)
print(f"Orphan treatment plan items in migrated: {len(orphan_items)}")

# ----------------------------------------------------------------------
# 3. PAYMENT CONSOLIDATION AUDIT
# ----------------------------------------------------------------------
print("\n[SECTION 3: PAYMENT CONSOLIDATION FORENSICS]")

prod_leg_payments = list(prod_db['patients_payment'].find())
mig_leg_archive = list(mig_db['archived_legacy_payments'].find())
prod_bill_payments = list(prod_db['patients_billpayment'].find())
mig_bill_payments = list(mig_db['patients_billpayment'].find())

audit_report['payments'] = {
    'prod_legacy_payment_count': len(prod_leg_payments),
    'mig_legacy_archive_count': len(mig_leg_archive),
    'prod_billpayment_count': len(prod_bill_payments),
    'mig_billpayment_count': len(mig_bill_payments),
    'legacy_payment_details': []
}

print(f"Original legacy payments in prod     : {len(prod_leg_payments)}")
print(f"Archived legacy payments in mig      : {len(mig_leg_archive)}")
print(f"Original BillPayment records in prod : {len(prod_bill_payments)}")
print(f"Migrated BillPayment records in mig  : {len(mig_bill_payments)}")

# Detailed mapping of each legacy payment
for lp in prod_leg_payments:
    lp_id = str(lp['_id'])
    receipt_key = f"RCP-LEGACY-{lp_id[-6:].upper()}"
    matched_bp = mig_db['patients_billpayment'].find_one({'receipt_number': receipt_key})
    
    amt = float(str(lp.get('paid_amount') or lp.get('amount') or 0))
    p_detail = {
        'legacy_id': lp_id,
        'amount': amt,
        'payment_date': str(lp.get('created_at') or lp.get('payment_date')),
        'payment_method': lp.get('payment_method'),
        'patient_id': str(lp.get('patient_id') or ''),
        'visit_id': str(lp.get('visit_id') or ''),
        'matched_billpayment': {
            'id': str(matched_bp['_id']) if matched_bp else None,
            'receipt_number': matched_bp.get('receipt_number') if matched_bp else None,
            'billing_id': str(matched_bp.get('billing_id')) if matched_bp else None,
            'amount': float(str(matched_bp.get('amount'))) if matched_bp else None,
            'transaction_reference': matched_bp.get('transaction_reference') if matched_bp else None,
            'company_id': str(matched_bp.get('company_id')) if matched_bp else None,
            'branch_id': str(matched_bp.get('branch_id')) if matched_bp else None,
        } if matched_bp else None
    }
    audit_report['payments']['legacy_payment_details'].append(p_detail)

print(f"Successfully mapped {len([d for d in audit_report['payments']['legacy_payment_details'] if d['matched_billpayment']])} / {len(prod_leg_payments)} legacy payments to BillPayment")

# Check 27 original BillPayments were not mutated
orig_prod_bp_map = {str(b['_id']): b for b in prod_bill_payments}
mutated_original_bp = 0
for bp in mig_bill_payments:
    bid = str(bp['_id'])
    if bid in orig_prod_bp_map:
        orig = orig_prod_bp_map[bid]
        if (str(bp.get('receipt_number')) != str(orig.get('receipt_number')) or
            float(str(bp.get('amount', 0))) != float(str(orig.get('amount', 0))) or
            str(bp.get('billing_id')) != str(orig.get('billing_id'))):
            mutated_original_bp += 1

audit_report['payments']['mutated_original_billpayments'] = mutated_original_bp
print(f"Mutated original BillPayments count: {mutated_original_bp}")

# ----------------------------------------------------------------------
# 4. TENANT BACKFILL AUDIT
# ----------------------------------------------------------------------
print("\n[SECTION 4: TENANT BACKFILL VERIFICATION]")

tenant_audit = {}
patients_map = {str(p['_id']): p for p in prod_db['patients_patient'].find()}
branch_map = {str(b['_id']): b for b in prod_db['patients_branch'].find()}

for col_name in ['patients_billing', 'patients_visit', 'patients_prescription', 'patients_doctor']:
    prod_null_c = prod_db[col_name].count_documents({'company_id': None})
    mig_null_c = mig_db[col_name].count_documents({'company_id': None})
    
    # Check accuracy of backfilled company & branch relative to parent patient/branch
    mismatched_records = []
    for doc in mig_db[col_name].find():
        doc_id = str(doc['_id'])
        cid = str(doc.get('company_id') or '')
        bid = str(doc.get('branch_id') or doc.get('primary_branch_id') or '')
        
        # Branch to company validity check
        if bid and bid in branch_map:
            expected_cid = str(branch_map[bid].get('company_id') or '')
            if cid and expected_cid and cid != expected_cid:
                mismatched_records.append({
                    'id': doc_id,
                    'error': f"Branch belongs to company {expected_cid[:8]}... but record has {cid[:8]}..."
                })
        
        # Parent patient match check (for billing, visit, rx)
        pid = str(doc.get('patient_id') or '')
        if pid and pid in patients_map:
            p = patients_map[pid]
            p_cid = str(p.get('company_id') or '')
            if cid and p_cid and cid != p_cid:
                mismatched_records.append({
                    'id': doc_id,
                    'error': f"Patient belongs to company {p_cid[:8]}... but record has {cid[:8]}..."
                })
                
    tenant_audit[col_name] = {
        'prod_null_companies': prod_null_c,
        'mig_null_companies': mig_null_c,
        'mismatched_records_count': len(mismatched_records),
        'mismatched_samples': mismatched_records[:5]
    }
    print(f"Collection {col_name:25s}: Prod Null: {prod_null_c}, Mig Null: {mig_null_c}, Mismatches: {len(mismatched_records)}")

audit_report['tenant_backfill'] = tenant_audit

# ----------------------------------------------------------------------
# 5. ARCHIVE COMPLETENESS & HASH PARITY AUDIT
# ----------------------------------------------------------------------
print("\n[SECTION 5: ARCHIVE COMPLETENESS & PARITY]")
import hashlib

archive_audit = {}

# 5.1 archived_treatmentplanitems_raw
prod_item_ids = sorted(str(x['_id']) for x in prod_items)
arch_item_ids = sorted(str(x['_id']) for x in raw_archived)
p_hash = hashlib.sha256(json.dumps(prod_item_ids).encode()).hexdigest()
a_hash = hashlib.sha256(json.dumps(arch_item_ids).encode()).hexdigest()

archive_audit['archived_treatmentplanitems_raw'] = {
    'prod_ids_count': len(prod_item_ids),
    'arch_ids_count': len(arch_item_ids),
    'hash_match': p_hash == a_hash,
    'prod_hash': p_hash[:16],
    'arch_hash': a_hash[:16]
}
print(f"Treatment plan items archive ID parity: {p_hash == a_hash} ({p_hash[:16]}... == {a_hash[:16]}...)")

# 5.2 archived_legacy_payments
prod_pay_ids = sorted(str(x['_id']) for x in prod_leg_payments)
arch_pay_ids = sorted(str(x['_id']) for x in mig_leg_archive)
p_pay_hash = hashlib.sha256(json.dumps(prod_pay_ids).encode()).hexdigest()
a_pay_hash = hashlib.sha256(json.dumps(arch_pay_ids).encode()).hexdigest()

archive_audit['archived_legacy_payments'] = {
    'prod_ids_count': len(prod_pay_ids),
    'arch_ids_count': len(arch_pay_ids),
    'hash_match': p_pay_hash == a_pay_hash,
    'prod_hash': p_pay_hash[:16],
    'arch_hash': a_pay_hash[:16]
}
print(f"Legacy payments archive ID parity     : {p_pay_hash == a_pay_hash} ({p_pay_hash[:16]}... == {a_pay_hash[:16]}...)")

# 5.3 archived_clinicsubscription
prod_sub_count = prod_db['patients_clinicsubscription'].count_documents({})
arch_sub_count = mig_db['archived_clinicsubscription'].count_documents({})
archive_audit['archived_clinicsubscription'] = {
    'prod_count': prod_sub_count,
    'arch_count': arch_sub_count,
    'match': prod_sub_count == arch_sub_count
}
print(f"Clinic subscription archive parity    : {prod_sub_count == arch_sub_count} (count: {arch_sub_count})")

audit_report['archives'] = archive_audit

# Write full raw audit output to json
with open('ashdent-back/scratch/phase3_independent_audit_data.json', 'w', encoding='utf-8') as f:
    json.dump(audit_report, f, indent=2)

print("\n" + "=" * 80)
print("INDEPENDENT AUDIT DATA EXTRACTION COMPLETE!")
print("Saved raw audit extract to ashdent-back/scratch/phase3_independent_audit_data.json")
print("=" * 80)

