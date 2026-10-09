import os
import django
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import Expense, PharmacyPurchase, ExpenseCategory

print("=== BEFORE CLEANUP ===")
old = list(Expense.objects.filter(category='pharmacy_purchase').values('id','title','amount','date'))
print(f"Total pharmacy_purchase expense records: {len(old)}")
total_before = sum(float(x['amount']) for x in old)
print(f"Total amount (pharmacy_purchase in Expense): {total_before}")

# Step 1: DELETE all existing pharmacy_purchase records from Expense table (clean slate)
deleted = Expense.objects.filter(category='pharmacy_purchase').delete()
print(f"\nDeleted {deleted[0]} old pharmacy_purchase expense records.")

# Step 2: Ensure category exists
cat, _ = ExpenseCategory.objects.get_or_create(
    key='pharmacy_purchase',
    defaults={'name': 'Pharmacy Purchase', 'color': '#10b981', 'icon': 'Pill'}
)

# Step 3: Re-create from PharmacyPurchase using grand_total (actual purchase cost)
all_pp = PharmacyPurchase.objects.all().order_by('purchase_date')
created = 0
grand_total_sum = 0
for p in all_pp:
    inv = p.invoice_no.strip() if p.invoice_no else ''
    inv_display = inv if inv else str(p.id)[:20]
    supplier_name = p.supplier.name if p.supplier else 'Supplier'
    amount = float(p.grand_total)
    grand_total_sum += amount
    
    Expense.objects.create(
        title=f"Pharmacy Purchase - {inv_display}",
        category='pharmacy_purchase',
        category_ref=cat,
        amount=p.grand_total,
        date=p.purchase_date,
        paid_to=supplier_name,
        status='Paid' if float(p.balance_due) <= 0 else 'Partial',
        payment_method='Bank Transfer',
        notes=f"Invoice: {inv_display} | Paid: Rs.{p.paid_amount} | Balance Due: Rs.{p.balance_due} | Items: {p.items.count()}"
    )
    created += 1
    print(f"  Created: {inv_display} | Rs.{amount} | {p.purchase_date}")

print(f"\nCreated {created} pharmacy_purchase expense records.")
print(f"Total pharmacy grand_total sum: Rs.{grand_total_sum}")

# Step 4: Verify totals
print("\n=== FINAL EXPENSE TOTALS (June 2026) ===")
from django.db.models import Sum

cats = Expense.objects.filter(date__year=2026, date__month=6).values('category').annotate(t=Sum('amount'))
grand = 0
for c in cats:
    val = float(c['t'])
    grand += val
    print(f"  {c['category']}: Rs.{val:,.0f}")
print(f"\nGRAND TOTAL in Expense table (June 2026): Rs.{grand:,.0f}")
