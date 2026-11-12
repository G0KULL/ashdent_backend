import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections

db = connections['default'].database

print("Auditing Finance Collections and Data Flows...")

est_col = db['patients_estimate']
est_items_col = db['patients_estimateitem']
billing_col = db['patients_billing']
bill_items_col = db['patients_billingitem']
bill_pay_col = db['patients_billpayment']
legacy_pay_col = db['patients_payment']
trans_col = db['patients_transaction']

# 1. Total counts
f_counts = {
    'estimates': est_col.count_documents({}),
    'estimate_items': est_items_col.count_documents({}),
    'billings': billing_col.count_documents({}),
    'billing_items': bill_items_col.count_documents({}),
    'bill_payments': bill_pay_col.count_documents({}),
    'legacy_payments': legacy_pay_col.count_documents({}),
    'transactions': trans_col.count_documents({})
}

# 2. Check overlap between Billing, Payment, BillPayment, and Transaction
bills = list(billing_col.find())
bill_ids = set(billing_col.distinct('_id'))
bill_payments = list(bill_pay_col.find())
legacy_payments = list(legacy_pay_col.find())
transactions = list(trans_col.find())

# Bill payment links
bp_linked_to_bill = sum(1 for bp in bill_payments if bp.get('billing_id') in bill_ids)

# Legacy payments: check how they link
lp_with_visit = sum(1 for lp in legacy_payments if lp.get('visit_id'))
lp_with_patient = sum(1 for lp in legacy_payments if lp.get('patient_id'))

# Transactions: check references
tx_with_bill = sum(1 for tx in transactions if tx.get('bill_id') or tx.get('billing_id'))
tx_with_patient = sum(1 for tx in transactions if tx.get('patient_id'))
tx_types = list(trans_col.aggregate([{'$group': {'_id': '$type', 'count': {'$sum': 1}}}]))

# Check invoice numbering uniqueness and format
invoice_numbers = [b.get('invoice_number') for b in bills if b.get('invoice_number')]
unique_inv = len(set(invoice_numbers))
inv_duplicates = len(invoice_numbers) - unique_inv

# Check estimates converted to bills
converted_estimates = est_col.count_documents({'status': 'CONVERTED'})
accepted_estimates = est_col.count_documents({'status': 'ACCEPTED'})
pending_estimates = est_col.count_documents({'status': 'DRAFT'})

# Check bill payment totals vs billing paid_amount
bill_discrepancies = []
for b in bills:
    b_id = b['_id']
    b_total = float(str(b.get('total_amount', 0) or 0))
    b_paid = float(str(b.get('paid_amount', 0) or 0))
    
    # Sum of BillPayments for this bill
    bps = list(bill_pay_col.find({'billing_id': b_id}))
    bp_sum = sum(float(str(p.get('amount', 0) or 0)) for p in bps)
    
    if abs(b_paid - bp_sum) > 0.01 and bps:
        bill_discrepancies.append({
            'bill_id': str(b_id),
            'invoice_number': b.get('invoice_number'),
            'bill_paid_recorded': b_paid,
            'bill_payments_sum': bp_sum
        })

finance_report = {
    'counts': f_counts,
    'estimates': {
        'total': len(list(est_col.find())),
        'converted': converted_estimates,
        'accepted': accepted_estimates,
        'draft_or_other': pending_estimates
    },
    'billings': {
        'total': len(bills),
        'invoices': billing_col.count_documents({'is_invoice': True}),
        'pharmacy_bills': billing_col.count_documents({'bill_type': 'Pharmacy'}),
        'clinical_bills': billing_col.count_documents({'bill_type': 'Clinical'}),
        'invoice_number_duplicates': inv_duplicates
    },
    'bill_payments': {
        'total': len(bill_payments),
        'linked_to_valid_bill': bp_linked_to_bill
    },
    'legacy_payments': {
        'total': len(legacy_payments),
        'with_visit': lp_with_visit,
        'with_patient': lp_with_patient
    },
    'transactions': {
        'total': len(transactions),
        'types': tx_types,
        'with_patient': tx_with_patient
    },
    'reconciliation_discrepancies': bill_discrepancies
}

out_path = 'ashdent-back/scratch/step7_finance_report.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(finance_report, f, indent=2)

print("Finance Audit complete! Saved to", out_path)
print(json.dumps(finance_report, indent=2))

