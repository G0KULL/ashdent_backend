import os
import django
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import PharmacyPurchase, MedicinePurchase, Expense, ExpenseCategory

def sync_expenses():
    # Ensure category exists
    cat, _ = ExpenseCategory.objects.get_or_create(
        key='pharmacy_purchase',
        defaults={'name': 'Pharmacy Purchase', 'color': '#10b981', 'icon': 'Pill'}
    )
    
    added = 0
    # Sync Advanced Purchases
    for p in PharmacyPurchase.objects.all():
        if not Expense.objects.filter(category='pharmacy_purchase', date=p.purchase_date, amount=p.paid_amount).exists():
            Expense.objects.create(
                title=f"Pharmacy Purchase - Inv #{p.invoice_no or p.id}",
                category='pharmacy_purchase',
                category_ref=cat,
                amount=p.paid_amount,
                date=p.purchase_date,
                status='Paid',
                payment_method='Bank Transfer'
            )
            added += 1

    # Sync Simple Purchases
    for p in MedicinePurchase.objects.all():
        if not Expense.objects.filter(category='pharmacy_purchase', date__date=p.date.date(), amount=p.total_amount).exists():
            Expense.objects.create(
                title=f"Medicine Purchase - {p.medicine.name}",
                category='pharmacy_purchase',
                category_ref=cat,
                amount=p.total_amount,
                date=p.date.date(),
                status='Paid',
                payment_method='Cash'
            )
            added += 1

    print(f"Synced {added} missing pharmacy expenses to the Expense table.")

if __name__ == '__main__':
    sync_expenses()
