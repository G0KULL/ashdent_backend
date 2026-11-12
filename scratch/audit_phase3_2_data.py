import os, sys, json, pymongo
from bson import ObjectId

client = pymongo.MongoClient('mongodb://localhost:27017/')
src = client['dental_clinic_db']
mig = client['dental_clinic_db_migrated']

print("=" * 80)
print("AUDIT 2: LEGACY PAYMENT 9-ROW INSPECTION")
print("=" * 80)

src_payments = list(src['patients_payment'].find({}))
print(f"Total payments in src['patients_payment']: {len(src_payments)}")

audit2_rows = []
for p in src_payments:
    orig_id = str(p.get('_id'))
    pt_id = str(p.get('patient_id') or p.get('patient'))
    amt = float(str(p.get('amount', 0)))
    dt = str(p.get('payment_date') or p.get('created_at'))
    method = p.get('payment_method')
    
    # In mig_db, find the matching BillPayment
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
    
    # Look up the bill in mig['patients_billing']
    bill = None
    if billing_id:
        try:
            bill = mig['patients_billing'].find_one({'_id': ObjectId(billing_id)})
        except Exception:
            bill = mig['patients_billing'].find_one({'_id': billing_id})
            
    bill_no = bill.get('bill_number') if bill else None
    bill_pt = str(bill.get('patient_id')) if bill else None
    bill_comp = str(bill.get('company_id')) if bill else None
    bill_branch = str(bill.get('branch_id')) if bill else None
    bill_tot = float(str(bill.get('total_amount', 0))) if bill else None
    bill_bal = float(str(bill.get('balance_amount', 0))) if bill else None
    bill_status = bill.get('status') if bill else None
    
    # Look up patient company/branch
    pt = mig['patients_patient'].find_one({'_id': ObjectId(pt_id)}) if pt_id else None
    pt_comp = str(pt.get('company_id')) if pt else None
    pt_branch = str(pt.get('branch_id') or pt.get('registration_branch_id')) if pt else None
    pt_name = pt.get('name') if pt else 'Unknown'

    row = {
        'orig_payment_id': orig_id,
        'patient_id': pt_id,
        'patient_name': pt_name,
        'amount': amt,
        'bp_amount': bp_amt,
        'payment_date': dt,
        'patient_company_id': pt_comp,
        'patient_branch_id': pt_branch,
        'migrated_bill_id': billing_id,
        'migrated_bill_number': bill_no,
        'bill_patient_id': bill_pt,
        'bill_company_id': bill_comp,
        'bill_branch_id': bill_branch,
        'migrated_billpayment_id': bp_id,
        'receipt_number': rcp_no,
        'bill_total_amount': bill_tot,
        'bill_balance_amount': bill_bal,
        'bill_status': bill_status,
        'pt_match': (pt_id == bill_pt),
        'comp_match': (pt_comp == bill_comp or not pt_comp)
    }
    audit2_rows.append(row)
    print(f"Payment {orig_id}: OrigAmt {amt}, BPAmt {bp_amt}, Pt '{pt_name}' ({pt_id}) -> Bill '{bill_no}' ({billing_id}), BP {bp_id}, Rcp {rcp_no}, PtMatch: {row['pt_match']}, CompMatch: {row['comp_match']}")

with open('ashdent-back/scratch/audit2_legacy_payments.json', 'w') as f:
    json.dump(audit2_rows, f, indent=2)

print("\n" + "=" * 80)
print("AUDIT 3: 83 DIVERGENT GROUPS AUDIT")
print("=" * 80)
with open('ashdent-back/scratch/treatment_plan_deduplication_audit.json', 'r') as f:
    dedup_audit = json.load(f)

# dedup_audit is a list of groups
print(f"Total groups audited in json: {len(dedup_audit)}")
print(f"Sample divergent group:\n{json.dumps(dedup_audit[0] if dedup_audit else {}, indent=2)}")

# Let's inspect all groups
retained_prices = []
all_catalogue_standard = []
recalculated_plan_totals = []
exceptions = []

for idx, g in enumerate(dedup_audit):
    chosen_id = g.get('selected_item_id')
    doc = mig['patients_treatmentplanitem'].find_one({'_id': ObjectId(chosen_id)})
    if doc:
        price = float(str(doc.get('estimated_cost', 0)))
        retained_prices.append(price)
        snap = float(str(doc.get('standard_price_snapshot', 0)))
        if price != 1500.0:
            exceptions.append({'index': idx, 'group': g, 'actual_price': price})
    else:
        retained_prices.append(None)
        exceptions.append({'index': idx, 'group': g, 'error': 'Not found in mig'})

print(f"Retained prices set: {set(retained_prices)}")
print(f"Exceptions found: {len(exceptions)}")

# Check parent plans
plan_totals_before_after = []
unique_plan_ids = set(g.get('plan_id') for g in dedup_audit if g.get('plan_id'))
print(f"Unique parent treatment plans across 83 groups: {len(unique_plan_ids)}")
for pid in unique_plan_ids:
    plan_doc = mig['patients_treatmentplan'].find_one({'_id': ObjectId(pid)})
    if plan_doc:
        tot = float(str(plan_doc.get('total_estimated_cost', 0)))
        # sum active items
        active_items = list(mig['patients_treatmentplanitem'].find({'plan_id': ObjectId(pid)}))
        item_sum = sum(float(str(it.get('estimated_cost', 0))) for it in active_items)
        plan_totals_before_after.append({
            'plan_id': pid,
            'plan_total': tot,
            'active_items_count': len(active_items),
            'items_sum': item_sum,
            'match': abs(tot - item_sum) < 0.01
        })

print(f"Plan totals checked: {len(plan_totals_before_after)}, All match item sums: {all(p['match'] for p in plan_totals_before_after)}")

# Check if any bill or payment was affected
bills_linked = list(mig['patients_billing'].find({'treatment_plan_id': {'$in': [ObjectId(p) for p in unique_plan_ids]}}))
print(f"Bills linked to these 83 treatment plans: {len(bills_linked)}")

print("\n" + "=" * 80)
print("AUDIT 7: FINANCIAL RECONCILIATION")
print("=" * 80)
bills = list(mig['patients_billing'].find({}))
print(f"Total bills in mig: {len(bills)}")

fin_audit = []
for b in bills:
    b_id = str(b['_id'])
    b_no = b.get('bill_number')
    tot = float(str(b.get('total_amount', 0)))
    bal = float(str(b.get('balance_amount', 0)))
    status = b.get('status')
    
    payments = list(mig['patients_billpayment'].find({'billing_id': b['_id']}))
    paid_sum = sum(float(str(p.get('amount', 0))) for p in payments)
    
    calc_bal = round(tot - paid_sum, 2)
    bal_match = abs(bal - calc_bal) < 0.01
    
    fin_audit.append({
        'bill_id': b_id,
        'bill_number': b_no,
        'total_amount': tot,
        'balance_amount': bal,
        'payments_count': len(payments),
        'paid_sum': paid_sum,
        'calculated_balance': calc_bal,
        'balance_match': bal_match,
        'status': status
    })

mismatches = [b for b in fin_audit if not b['balance_match']]
print(f"Total bills: {len(fin_audit)}, Mismatches: {len(mismatches)}")
if mismatches:
    for m in mismatches:
        print(f"  Mismatch in Bill {m['bill_number']}: Total={m['total_amount']}, PaidSum={m['paid_sum']}, DB Bal={m['balance_amount']}, CalcBal={m['calculated_balance']}")

with open('ashdent-back/scratch/audit7_fin_reconciliation.json', 'w') as f:
    json.dump(fin_audit, f, indent=2)

print("Inspection completed.")
