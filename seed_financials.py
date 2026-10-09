import os
import django
import random
import datetime
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import Billing, Payment, Expense, Patient, ExpenseCategory, Doctor
from django.utils import timezone

def seed_financials():
    print("Starting financial data seed...")
    
    # 1. Ensure a general patient exists
    patient, _ = Patient.objects.get_or_create(phone='0000000000', defaults={'name': 'General Clinic Income'})
    doctors = list(Doctor.objects.all())
    
    # Ensure expense categories exist
    cat_keys = ['doctor_salary', 'consumables', 'maintenance', 'marketing', 'office_supplies', 'rent']
    cat_objs = []
    for k in cat_keys:
        c, _ = ExpenseCategory.objects.get_or_create(key=k, defaults={'name': k.replace('_', ' ').title()})
        cat_objs.append(c)

    # 2. Clear old dummy data
    print("Clearing old dummy data...")
    Billing.objects.filter(patient=patient).delete()
    Expense.objects.filter(title__startswith="Generated ").delete()

    # 3. Generate data for the past 6 months
    today = timezone.localtime().date()
    
    for i in range(180): # Past 180 days
        current_date = today - datetime.timedelta(days=i)
        
        # Determine number of transactions per day
        if i < 30:
            num_incomes = random.randint(10, 25)
            num_expenses = random.randint(2, 6)
        else:
            num_incomes = random.randint(1, 4)
            num_expenses = random.randint(0, 2)
        
        dt_obj = timezone.make_aware(datetime.datetime.combine(current_date, datetime.time(random.randint(9, 17), random.randint(0, 59))))
        
        # Generate Incomes (Billings/Payments)
        for _ in range(num_incomes):
            amount = Decimal(str(random.randint(500, 5000)))
            doc = random.choice(doctors) if doctors else None
            
            b = Billing.objects.create(
                patient=patient,
                doctor=doc,
                bill_type=random.choice(['Clinical', 'Pharmacy']),
                total_amount=amount,
                paid_amount=amount,
                balance_amount=Decimal('0.00'),
                status='Paid',
                payment_method=random.choice(['Cash', 'Card', 'UPI']),
                notes="Generated Income"
            )
            Billing.objects.filter(pk=b.pk).update(created_at=dt_obj)
            
        # Generate Expenses
        for _ in range(num_expenses):
            amount = Decimal(str(random.randint(200, 3000)))
            cat = random.choice(cat_objs)
            Expense.objects.create(
                title=f"Generated {cat.name} Expense",
                category=cat.key,
                category_ref=cat,
                amount=amount,
                date=current_date,
                payment_method=random.choice(['Cash', 'Bank Transfer']),
                status='Paid',
                notes="Generated Expense"
            )
            
    print("Financial data seed completed.")

if __name__ == '__main__':
    seed_financials()
