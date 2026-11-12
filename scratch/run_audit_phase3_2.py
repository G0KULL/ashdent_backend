import os, sys, json, pymongo
from bson import ObjectId
from decimal import Decimal
import datetime

client = pymongo.MongoClient('mongodb://localhost:27017/')
src = client['dental_clinic_db']
mig = client['dental_clinic_db_migrated']

output_data = {}

# ==============================================================================
# AUDIT 1: Database Configuration and Cutover inspection
# ==============================================================================
# We will inspect core/settings.py, cutover_to_production.py, background workers, etc.
# Check settings:
settings_path = 'ashdent-back/core/settings.py'
with open(settings_path, 'r', encoding='utf-8') as f:
    settings_code = f.read()

has_env_db_name = "os.getenv('DJANGO_DB_NAME'" in settings_code or 'os.environ.get("DJANGO_DB_NAME"' in settings_code or 'os.environ.get(\'DJANGO_DB_NAME\'' in settings_code or 'os.getenv("DJANGO_DB_NAME"' in settings_code

# Check cutover_to_production.py
cutover_path = 'ashdent-back/scratch/cutover_to_production.py'
with open(cutover_path, 'r', encoding='utf-8') as f:
    cutover_code = f.read()

has_confirm_env = 'CONFIRM_CUTOVER' in cutover_code
has_drop_collection = '.drop()' in cutover_code or 'drop_collection' in cutover_code
has_dry_run = '--dry-run' in cutover_code
has_backup_step = 'backup' in cutover_code.lower()

output_data['audit1'] = {
    'settings_has_env_db_name': has_env_db_name,
    'cutover_has_confirm_env': has_confirm_env,
    'cutover_has_drop_collection': has_drop_collection,
    'cutover_has_dry_run': has_dry_run,
    'cutover_has_backup_step': has_backup_step,
}

# ==============================================================================
# AUDIT 2: Nine Legacy Payments Reconciliation
# ==============================================================================
src_payments = list(src['patients_payment'].find({}))
audit2_rows = []

for p in src_payments:
    orig_id = str(p.get('_id'))
    pt_id = str(p.get('patient_id') or p.get('patient'))
    amt = float(str(p.get('paid_amount') or p.get('total_amount') or p.get('amount') or 0))
    dt = str(p.get('payment_date') or p.get('created_at'))
    orig_comp = str(p.get('company_id')) if p.get('company_id') else None
    orig_branch = str(p.get('branch_id')) if p.get('branch_id') else None
    method = p.get('payment_method')
    
    # Matching BillPayment in mig
    bp = mig['patients_billpayment'].find_one({
        '$or': [
            {'receipt_number': f"RCP-LEGACY-{orig_id[-6:].upper()}"},
            {'receipt_number': f"RCP-LEGACY-{orig_id[-8:].upper()}"},
            {'notes': {'$regex': orig_id}},
            {'transaction_id': f"TXN-LEGACY-{orig_id[-6:].upper()}"},
            {'transaction_id': f"TXN-LEGACY-{orig_id[-8:].upper()}"}
        ]
    })
    
    bp_id = str(bp['_id']) if bp else None
    rcp_no = bp.get('receipt_number') if bp else None
    billing_id = str(bp.get('billing_id')) if bp and bp.get('billing_id') else None
    bp_amt = float(str(bp.get('amount', 0))) if bp else None
    bp_comp = str(bp.get('company_id')) if bp else None
    bp_branch = str(bp.get('branch_id')) if bp else None
    
    # Bill in mig
    bill = mig['patients_billing'].find_one({'_id': ObjectId(billing_id)}) if billing_id else None
    bill_inv = bill.get('invoice_number') if bill else None
    bill_pt = str(bill.get('patient_id')) if bill else None
    bill_comp = str(bill.get('company_id')) if bill else None
    bill_branch = str(bill.get('branch_id')) if bill else None
    bill_tot = float(str(bill.get('total_amount', 0))) if bill else None
    bill_bal = float(str(bill.get('balance_amount', 0))) if bill else None
    bill_status = bill.get('status') if bill else None
    
    # Patient info
    pt = mig['patients_patient'].find_one({'_id': ObjectId(pt_id)}) if pt_id else None
    pt_name = pt.get('name') if pt else 'Unknown'
    pt_comp = str(pt.get('company_id')) if pt else None
    pt_branch = str(pt.get('branch_id') or pt.get('registration_branch_id')) if pt else None

    # Verification criteria
    pt_match = (pt_id == bill_pt)
    comp_match = (bill_comp == pt_comp or (not pt_comp and bill_comp is not None))
    bal_zero_or_valid = (bill_bal == 0.0) if bill and bill.get('bill_type') == 'Consultation' else (bill_bal is not None)
    
    audit2_rows.append({
        'orig_payment_id': orig_id,
        'patient_id': pt_id,
        'patient_name': pt_name,
        'amount': amt,
        'payment_date': dt,
        'payment_method': method,
        'patient_company_id': pt_comp,
        'patient_branch_id': pt_branch,
        'migrated_bill_id': billing_id,
        'migrated_bill_number': bill_inv or f"BILL-{billing_id[-6:]}",
        'bill_patient_id': bill_pt,
        'bill_company_id': bill_comp,
        'bill_branch_id': bill_branch,
        'migrated_billpayment_id': bp_id,
        'receipt_number': rcp_no,
        'bill_total_amount': bill_tot,
        'bill_balance_amount': bill_bal,
        'bill_status': bill_status,
        'patient_match': pt_match,
        'company_match': comp_match,
        'balance_valid': bal_zero_or_valid
    })

output_data['audit2'] = audit2_rows

# ==============================================================================
# AUDIT 3: Eighty-Three Group Treatment Price Audit
# ==============================================================================
with open('ashdent-back/scratch/treatment_plan_deduplication_audit.json', 'r') as f:
    dedup_audit = json.load(f)

# Identify divergent vs identical
identical_groups = [g for g in dedup_audit if len(g.get('original_prices', [])) == 1]
divergent_groups = [g for g in dedup_audit if len(g.get('original_prices', [])) > 1]

print(f"Total deduplication groups: {len(dedup_audit)}")
print(f"Identical groups: {len(identical_groups)}")
print(f"Divergent groups: {len(divergent_groups)}")

audit3_summary = {
    'total_groups': len(dedup_audit),
    'identical_groups_count': len(identical_groups),
    'divergent_groups_count': len(divergent_groups),
    'divergent_groups': []
}

exceptions = []
for idx, g in enumerate(divergent_groups):
    pid = g.get('plan_id')
    tooth = g.get('tooth_number')
    proc = g.get('procedure_name')
    orig_prices = g.get('original_prices', [])
    chosen_id = g.get('selected_item_id')
    chosen_price = float(str(g.get('selected_price', 0)))
    reason = g.get('reason')
    
    # Check actual doc in mig
    doc = mig['patients_treatmentplanitem'].find_one({'_id': ObjectId(chosen_id)})
    actual_cost = float(str(doc.get('estimated_cost', 0))) if doc else None
    snap = doc.get('standard_price_snapshot') if doc else None
    override_reason = doc.get('price_override_reason') if doc else None
    override_by = doc.get('price_modified_by_id') if doc else None
    
    # Check parent plan
    plan = mig['patients_treatmentplan'].find_one({'_id': ObjectId(pid)}) if pid else None
    plan_pt_id = str(plan.get('patient_id')) if plan else None
    plan_total = float(str(plan.get('total_estimated_cost', 0))) if plan else None
    
    # Exception check: procedure was composite filling, expected 1500.0
    if proc.lower() == 'composite filling' and actual_cost != 1500.0:
        exceptions.append({
            'group_idx': idx,
            'plan_id': pid,
            'actual_cost': actual_cost,
            'reason': 'Unexpected cost for composite filling'
        })
        
    audit3_summary['divergent_groups'].append({
        'group_index': idx + 1,
        'plan_id': pid,
        'patient_id': plan_pt_id,
        'tooth': tooth,
        'procedure': proc,
        'duplicate_count': g.get('total_original_items'),
        'original_prices': orig_prices,
        'selected_item_id': chosen_id,
        'selected_price': chosen_price,
        'actual_db_price': actual_cost,
        'standard_price_snapshot': str(snap),
        'override_reason': override_reason,
        'override_by': str(override_by) if override_by else None,
        'decision_reason': reason,
        'parent_plan_total': plan_total
    })

audit3_summary['exceptions_count'] = len(exceptions)
audit3_summary['exceptions'] = exceptions
output_data['audit3'] = audit3_summary

# Check if any bills or payments reference these plans
affected_pids = [ObjectId(g['plan_id']) for g in divergent_groups]
linked_bills = list(mig['patients_billing'].find({'treatment_plan_id': {'$in': affected_pids}}))
audit3_summary['linked_bills_count'] = len(linked_bills)

# ==============================================================================
# AUDIT 4: Test Data Identification
# ==============================================================================
# In pre-test migration:
# Active items were 123. Now:
current_active_items = mig['patients_treatmentplanitem'].count_documents({})
# BillPayment records were 36. Now:
current_bp_count = mig['patients_billpayment'].count_documents({})

# Let's inspect test items created by Arthur Dentist workflow
arthur = mig['patients_patient'].find_one({'name': {'$regex': 'Arthur Dentist', '$options': 'i'}})
arthur_id = arthur['_id'] if arthur else None

test_inventory = []
if arthur_id:
    # Patient
    test_inventory.append({
        'collection': 'patients_patient',
        'id': str(arthur_id),
        'name': arthur.get('name'),
        'created_at': str(arthur.get('created_at')),
        'disposition': 'Purge before production'
    })
    
    # Appointments
    for a in mig['patients_appointment'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_appointment',
            'id': str(a['_id']),
            'summary': f"Appt on {a.get('date')} at {a.get('time')}",
            'created_at': str(a.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Visits
    for v in mig['patients_visit'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_visit',
            'id': str(v['_id']),
            'summary': f"Visit type {v.get('visit_type')}",
            'created_at': str(v.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Clinical notes
    for cn in mig['patients_clinicalnotes'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_clinicalnotes',
            'id': str(cn['_id']),
            'summary': f"Notes: {cn.get('chief_complaint')}",
            'created_at': str(cn.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Tooth conditions
    for tc in mig['patients_toothcondition'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_toothcondition',
            'id': str(tc['_id']),
            'summary': f"Tooth {tc.get('tooth_number')}: {tc.get('condition')}",
            'created_at': str(tc.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Treatment plans
    for tp in mig['patients_treatmentplan'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_treatmentplan',
            'id': str(tp['_id']),
            'summary': f"Plan {tp.get('title')}, total {tp.get('total_estimated_cost')}",
            'created_at': str(tp.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Treatment plan items
    for tpi in mig['patients_treatmentplanitem'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_treatmentplanitem',
            'id': str(tpi['_id']),
            'summary': f"Item Tooth {tpi.get('tooth_number')} - {tpi.get('procedure_name')}, cost {tpi.get('estimated_cost')}",
            'created_at': str(tpi.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Estimates
    for est in mig['patients_estimate'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_estimate',
            'id': str(est['_id']),
            'summary': f"Estimate {est.get('estimate_number')}, total {est.get('total_amount')}",
            'created_at': str(est.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Treatment records
    for tr in mig['patients_treatmentrecord'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_treatmentrecord',
            'id': str(tr['_id']),
            'summary': f"Treatment record Tooth {tr.get('tooth_number')} - {tr.get('procedure_name')}",
            'created_at': str(tr.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Prescriptions
    for pr in mig['patients_prescription'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_prescription',
            'id': str(pr['_id']),
            'summary': f"Prescription {pr.get('prescription_number')}",
            'created_at': str(pr.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Prescription items
    for pri in mig['patients_prescriptionitem'].find({}):
        # Check if linked to test prescription
        test_presc_ids = [ObjectId(item['id']) for item in test_inventory if item['collection'] == 'patients_prescription']
        if pri.get('prescription_id') in test_presc_ids:
            test_inventory.append({
                'collection': 'patients_prescriptionitem',
                'id': str(pri['_id']),
                'summary': f"Medicine: {pri.get('medicine_name')}",
                'created_at': str(pri.get('created_at')),
                'disposition': 'Purge before production'
            })
            
    # Billings
    for bi in mig['patients_billing'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_billing',
            'id': str(bi['_id']),
            'summary': f"Bill {bi.get('invoice_number')}, total {bi.get('total_amount')}, status {bi.get('status')}",
            'created_at': str(bi.get('created_at')),
            'disposition': 'Purge before production'
        })
        
    # Bill payments
    for bp in mig['patients_billpayment'].find({'patient_id': arthur_id}):
        test_inventory.append({
            'collection': 'patients_billpayment',
            'id': str(bp['_id']),
            'summary': f"Payment Rcp {bp.get('receipt_number')}, amount {bp.get('amount')}",
            'created_at': str(bp.get('created_at')),
            'disposition': 'Purge before production'
        })

# Also check test companies COMP_ALPHA, COMP_BETA and their branches/users
for comp in mig['patients_company'].find({'code': {'$in': ['COMP_ALPHA', 'COMP_BETA']}}):
    test_inventory.append({
        'collection': 'patients_company',
        'id': str(comp['_id']),
        'summary': f"Company {comp.get('name')} ({comp.get('code')})",
        'created_at': str(comp.get('created_at')),
        'disposition': 'Retain or purge based on tenant policy'
    })

# Slot locks created during testing
for sl in mig['patients_slot_lock'].find({}):
    test_inventory.append({
        'collection': 'patients_slot_lock',
        'id': str(sl['_id']),
        'summary': f"Slot lock on {sl.get('slot_time')}",
        'created_at': str(sl.get('locked_at')),
        'disposition': 'Purge before production'
    })

output_data['audit4'] = {
    'pre_test_active_items': 123,
    'current_active_items': current_active_items,
    'test_added_items': current_active_items - 123,
    'pre_test_bill_payments': 36,
    'current_bill_payments': current_bp_count,
    'test_added_bill_payments': current_bp_count - 36,
    'test_records_inventory': test_inventory
}

# ==============================================================================
# AUDIT 7: Financial Reconciliation
# ==============================================================================
bills = list(mig['patients_billing'].find({}))
fin_reconciliation = []
fin_mismatches = []

for b in bills:
    b_id = str(b['_id'])
    b_no = b.get('invoice_number') or f"BILL-{b_id[-6:]}"
    tot = float(str(b.get('total_amount', 0)))
    bal = float(str(b.get('balance_amount', 0)))
    status = b.get('status')
    
    # payments
    payments = list(mig['patients_billpayment'].find({'billing_id': b['_id']}))
    paid_sum = sum(float(str(p.get('amount', 0))) for p in payments)
    calc_bal = round(tot - paid_sum, 2)
    bal_match = abs(bal - calc_bal) < 0.01
    
    item = {
        'bill_id': b_id,
        'invoice_number': b_no,
        'bill_type': b.get('bill_type'),
        'total_amount': tot,
        'recorded_balance': bal,
        'payments_count': len(payments),
        'paid_sum': paid_sum,
        'calculated_balance': calc_bal,
        'balance_match': bal_match,
        'status': status
    }
    fin_reconciliation.append(item)
    if not bal_match:
        fin_mismatches.append(item)

output_data['audit7'] = {
    'total_bills_audited': len(bills),
    'mismatches_count': len(fin_mismatches),
    'mismatches': fin_mismatches,
    'sample_bills': fin_reconciliation[:10]
}

with open('ashdent-back/scratch/audit_phase3_2_output.json', 'w') as f:
    json.dump(output_data, f, indent=2)

print("\nAudit Phase 3.2 data aggregation successfully finished.")
print(f"Audit 1 settings OK: {output_data['audit1']['settings_has_env_db_name']}")
print(f"Audit 2 reconciled rows: {len(output_data['audit2'])}")
print(f"Audit 3 divergent groups: {len(output_data['audit3']['divergent_groups'])}, exceptions: {output_data['audit3']['exceptions_count']}")
print(f"Audit 4 test items reconciled: {output_data['audit4']['test_added_items']} items, {output_data['audit4']['test_added_bill_payments']} payments")
print(f"Audit 7 financial bills audited: {output_data['audit7']['total_bills_audited']}, mismatches: {output_data['audit7']['mismatches_count']}")

