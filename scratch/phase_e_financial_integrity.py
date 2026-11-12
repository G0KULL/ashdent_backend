import sys, os, json
from pymongo import MongoClient
from bson import ObjectId

client = MongoClient('mongodb://localhost:27017/')
prod_db = client['dental_clinic_db']
mig_db = client['dental_clinic_db_migrated']

print("=" * 80)
print("PHASE E: FINANCIAL INTEGRITY AUDIT")
print("=" * 80)

def to_float(val):
    if val is None:
        return 0.0
    return float(str(val))

# 1. Inspect 9 Legacy Payments in migrated DB
print("\n--- 1. Inspecting 9 Legacy Payments in Migrated DB ---")
legacy_payments_col = mig_db['patients_billpayment']
legacy_payments = list(legacy_payments_col.find({'receipt_number': {'$regex': r'^RCP-LEGACY'}}))
print(f"Found {len(legacy_payments)} RCP-LEGACY payments in patients_billpayment")

total_legacy_amount = sum(to_float(p.get('amount', 0)) for p in legacy_payments)
print(f"Total Legacy Payment Amount: {total_legacy_amount:.2f}")

legacy_invoice_ids = set()
for p in legacy_payments:
    b_id = str(p.get('billing_id'))
    legacy_invoice_ids.add(b_id)
    print(f"  Receipt: {p.get('receipt_number')}, Amount: {p.get('amount')}, Method: {p.get('payment_method')}, Billing ID: {b_id}, Date: {p.get('payment_date')}")

print(f"Unique Invoices linked to legacy payments: {len(legacy_invoice_ids)}")
legacy_invoices = list(mig_db['patients_billing'].find({'_id': {'$in': [ObjectId(bid) if ObjectId.is_valid(bid) else bid for bid in legacy_invoice_ids]}}))
for inv in legacy_invoices:
    print(f"  Linked Invoice: ID={inv.get('_id')}, Bill#={inv.get('bill_number')}, Patient={inv.get('patient_name')}, Total={inv.get('total_amount')}, Paid={inv.get('paid_amount')}, Balance={inv.get('balance_amount')}")

# Check archived_legacy_payments collection
archived_payments_col = mig_db['archived_legacy_payments']
archived_count = archived_payments_col.count_documents({})
print(f"Dedicated Archive 'archived_legacy_payments' count: {archived_count}")

# Check if double-counted
payment_receipts = [p.get('receipt_number') for p in legacy_payments]
duplicate_receipts = set([x for x in payment_receipts if payment_receipts.count(x) > 1])
print(f"Duplicate receipt numbers among legacy payments: {duplicate_receipts if duplicate_receipts else 'None (0 duplicates)'}")

# 2. Document the 4 historical test invoices
print("\n--- 2. Inspecting 4 Historical Test Invoices ---")
target_invoices = [
    ('BILL-f9a1ae', '6ae9782499ca57772af9a1ae'),
    ('BILL-f9a1b7', '6ae9782499ca57772af9a1b7'),
    ('BILL-fb4690', '6ae97840f3a0d81af3fb4690'),
    ('BILL-fb4698', '6ae97840f3a0d81af3fb4698')
]
invoice_results = []

for label, doc_id in target_invoices:
    oid = ObjectId(doc_id)
    prod_inv = prod_db['patients_billing'].find_one({'_id': oid})
    mig_inv = mig_db['patients_billing'].find_one({'_id': oid})
    
    prod_payments = list(prod_db['patients_billpayment'].find({'billing_id': oid})) if prod_inv else []
    mig_payments = list(mig_db['patients_billpayment'].find({'billing_id': oid})) if mig_inv else []
    
    prod_payment_sum = sum(to_float(p.get('amount', 0)) for p in prod_payments)
    mig_payment_sum = sum(to_float(p.get('amount', 0)) for p in mig_payments)
    
    inv_data = {
        'label': label,
        'doc_id': doc_id,
        'exists_in_prod': bool(prod_inv),
        'exists_in_mig': bool(mig_inv),
        'prod_total': to_float(prod_inv.get('total_amount', 0)) if prod_inv else None,
        'prod_paid_field': to_float(prod_inv.get('paid_amount', 0)) if prod_inv else None,
        'prod_balance_field': to_float(prod_inv.get('balance_amount', 0)) if prod_inv else None,
        'prod_payment_sum': prod_payment_sum,
        'prod_payment_count': len(prod_payments),
        'mig_total': to_float(mig_inv.get('total_amount', 0)) if mig_inv else None,
        'mig_paid_field': to_float(mig_inv.get('paid_amount', 0)) if mig_inv else None,
        'mig_balance_field': to_float(mig_inv.get('balance_amount', 0)) if mig_inv else None,
        'mig_payment_sum': mig_payment_sum,
        'mig_payment_count': len(mig_payments),
    }
    invoice_results.append(inv_data)
    print(f"Invoice: {label} (ID: {doc_id})")
    print(f"  Prod: Exists={inv_data['exists_in_prod']}, Total={inv_data['prod_total']}, PaidField={inv_data['prod_paid_field']}, BalField={inv_data['prod_balance_field']}, PaymentSum={inv_data['prod_payment_sum']} ({inv_data['prod_payment_count']} pmts)")
    print(f"  Mig : Exists={inv_data['exists_in_mig']}, Total={inv_data['mig_total']}, PaidField={inv_data['mig_paid_field']}, BalField={inv_data['mig_balance_field']}, PaymentSum={inv_data['mig_payment_sum']} ({inv_data['mig_payment_count']} pmts)")

# 3. Trace 83 Composite Filling Tooth 36 groups
print("\n--- 3. Tracing Composite Filling Tooth 36 Groups ---")
pipeline_prod = [
    {'$match': {'procedure_name': 'Composite Filling', 'tooth_number': '36'}},
    {'$group': {'_id': '$plan_id', 'count': {'$sum': 1}}},
    {'$match': {'count': {'$gt': 1}}}
]
duplicate_plans_prod = list(prod_db['patients_treatmentplanitem'].aggregate(pipeline_prod))
print(f"Prod Plans with duplicate (>1) Composite Filling Tooth 36: {len(duplicate_plans_prod)}")

pipeline_all_groups = [
    {'$match': {'procedure_name': 'Composite Filling', 'tooth_number': '36'}},
    {'$group': {'_id': {'plan_id': '$plan_id', 'tooth': '$tooth_number', 'procedure': '$procedure_name'}, 'count': {'$sum': 1}}}
]
all_groups_prod = list(prod_db['patients_treatmentplanitem'].aggregate(pipeline_all_groups))
print(f"Total distinct (plan, tooth, procedure) groups in production: {len(all_groups_prod)}")

raw_col = mig_db['archived_treatmentplanitems_raw']
raw_count = raw_col.count_documents({'procedure_name': 'Composite Filling', 'tooth_number': '36'})
print(f"Archived raw items (Tooth 36 + Composite Filling): {raw_count}")

active_items_col = mig_db['patients_treatmentplanitem']
active_comp_36 = active_items_col.count_documents({'procedure_name': 'Composite Filling', 'tooth_number': '36'})
print(f"Active retained items (Tooth 36 + Composite Filling): {active_comp_36}")


output_data = {
    'legacy_payments_count': len(legacy_payments),
    'legacy_payments_total_amount': total_legacy_amount,
    'legacy_invoices_count': len(legacy_invoice_ids),
    'archived_legacy_payments_count': archived_count,
    'invoices_audit': invoice_results,
    'duplicate_plans_prod_count': len(duplicate_plans_prod),
    'distinct_groups_prod_count': len(all_groups_prod),
    'raw_archived_comp_36_count': raw_count,
    'active_comp_36_count': active_comp_36
}

with open('ashdent-back/scratch/phase_e_financial_report.json', 'w') as f:
    json.dump(output_data, f, indent=2)

print("\nPhase E Financial Integrity Audit completed successfully.")
