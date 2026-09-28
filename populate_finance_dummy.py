import os
import django
import datetime
from decimal import Decimal
import random
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import (
    Patient, Doctor, Billing, BillingItem, TreatmentMaster,
    MedicineMaster, Supplier, PharmacyPurchase, PharmacyPurchaseItem,
    Expense, ExpenseCategory, DoctorSalary, DoctorSalaryRecord, Payment,
    Visit, Appointment
)

def populate_dummy_data():
    print("Starting finance and expense dummy data generation...")

    # 1. Ensure Doctors exist
    doctors = []
    doc_names = [('Dr. Navas Kp', '#3b82f6'), ('Dr. Smith', '#ef4444'), ('Dr. Sarah Jenkins', '#8b5cf6')]
    for name, col in doc_names:
        doc, created = Doctor.objects.get_or_create(name=name, defaults={'color': col, 'consultation_fee': Decimal('500.00')})
        doctors.append(doc)

    # 2. Ensure Patients exist
    patients = []
    pat_details = [
        ('Arjun Menon', '9876543210'),
        ('Priya Menon', '9123456789'),
        ('Rahul Krishna', '9988776655'),
        ('Sneha Nair', '9876123450'),
        ('Amit Sharma', '9123888888')
    ]
    for name, phone in pat_details:
        pat, created = Patient.objects.get_or_create(phone=phone, defaults={'name': name, 'age': random.randint(20, 60), 'gender': random.choice(['Male', 'Female'])})
        patients.append(pat)

    # 3. Ensure Suppliers exist
    suppliers = []
    sup_details = [
        ('PharmaCorp Distributors', '9991112222', 'Mumbai, India'),
        ('MedTech Supplies', '9993334444', 'Bangalore, India'),
        ('DentalKart Supply Co', '9995556666', 'Delhi, India')
    ]
    for name, phone, addr in sup_details:
        sup, created = Supplier.objects.get_or_create(name=name, defaults={'phone': phone, 'address': addr})
        suppliers.append(sup)

    # 4. Ensure Treatment Masters exist
    treatments = []
    treat_details = [
        ('Consultation', Decimal('500.00'), 'Consultation'),
        ('Root Canal Treatment (RCT)', Decimal('4500.00'), 'Treatment'),
        ('Scaling & Polishing', Decimal('1500.00'), 'Treatment'),
        ('Composite Filling', Decimal('1200.00'), 'Treatment'),
        ('Zirconia Crown', Decimal('12000.00'), 'Treatment'),
        ('Dental Implant', Decimal('35000.00'), 'Treatment')
    ]
    for name, price, fee_type in treat_details:
        tm, created = TreatmentMaster.objects.get_or_create(name=name, defaults={'price': price, 'fee_type': fee_type})
        treatments.append(tm)

    # 5. Ensure Medicine Masters exist
    medicines = []
    med_details = [
        ('Paracetamol 650mg', Decimal('12.00'), Decimal('30.00'), 100),
        ('Amoxicillin 500mg', Decimal('45.00'), Decimal('120.00'), 80),
        ('Ibuprofen 400mg', Decimal('15.00'), Decimal('40.00'), 150),
        ('Clindamycin 300mg', Decimal('70.00'), Decimal('180.00'), 50),
        ('Sensodyne Toothpaste', Decimal('80.00'), Decimal('150.00'), 40)
    ]
    for name, p_rate, s_rate, qty in med_details:
        # Also ensure TreatmentMaster entry exists for Pharmacy billing: e.g. "Pharmacy: <Medicine Name>"
        TreatmentMaster.objects.get_or_create(name=f"Pharmacy: {name}", defaults={'price': s_rate, 'fee_type': 'Pharmacy'})
        med, created = MedicineMaster.objects.get_or_create(name=name, defaults={'purchase_rate': p_rate, 'sales_rate': s_rate, 'stock_quantity': qty, 'low_stock_threshold': 10})
        medicines.append(med)

    # 6. Generate Dummy Income (Clinical and Pharmacy Billings & Payments) for May 2026
    print("Generating Billing and Payment records...")
    payment_methods = ['Cash', 'UPI', 'Card']
    
    # Current Month up to today
    today = datetime.date.today()
    start_date = today.replace(day=1)
    end_date = today
    delta = end_date - start_date

    # Let's seed 30-40 clinical and pharmacy bills
    for i in range(delta.days + 1):
        day = start_date + datetime.timedelta(days=i)
        
        # 1-3 clinical bills per day
        for _ in range(random.randint(1, 3)):
            pat = random.choice(patients)
            doc = random.choice(doctors)
            
            # Select random treatments
            selected_tms = random.sample(treatments, k=random.randint(1, 2))
            total_amt = sum(tm.price for tm in selected_tms)
            
            # payment method & paid amount
            pm = random.choice(payment_methods)
            paid_ratio = random.choice([1.0, 1.0, 1.0, 0.5, 0.0]) # usually paid in full
            paid_amt = Decimal(str(round(total_amt * Decimal(str(paid_ratio)), 2)))
            
            # Create Appointment
            appt_time = datetime.time(random.randint(9, 17), random.choice([0, 30]))
            appt = Appointment.objects.create(
                patient=pat,
                doctor=doc,
                date=day,
                time=appt_time,
                status='Completed'
            )
            
            # Create Visit
            visit = Visit.objects.create(patient=pat, appointment=appt)
            visit.created_at = timezone.make_aware(datetime.datetime.combine(day, appt_time))
            visit.save()

            # Create Billing
            bill = Billing.objects.create(
                patient=pat,
                visit=visit,
                doctor=doc,
                bill_type='Clinical',
                total_amount=total_amt,
                paid_amount=paid_amt,
                payment_method=pm,
                notes="Consultation and treatment billing"
            )
            bill.created_at = timezone.make_aware(datetime.datetime.combine(day, appt_time))
            bill.save()
            
            # Billing items
            for tm in selected_tms:
                BillingItem.objects.create(billing=bill, treatment=tm, qty=1, price=tm.price)

            # Create legacy Payment if paid_amount > 0 to match system calculations
            if paid_amt > 0:
                payment = Payment.objects.create(
                    patient=pat,
                    visit=visit,
                    total_amount=total_amt,
                    paid_amount=paid_amt,
                    payment_method=pm
                )
                payment.created_at = timezone.make_aware(datetime.datetime.combine(day, appt_time))
                payment.save()

        # 1 pharmacy bill every 1-2 days
        if random.choice([True, False, True]):
            pat = random.choice(patients)
            selected_meds = random.sample(medicines, k=random.randint(1, 3))
            total_amt = Decimal('0.00')
            pm = random.choice(payment_methods)
            
            # Create shell Appointment and Visit for Pharmacy bill
            appt = Appointment.objects.create(
                patient=pat,
                doctor=random.choice(doctors),
                date=day,
                time=datetime.time(11, 0),
                status='Completed'
            )
            visit = Visit.objects.create(patient=pat, appointment=appt)
            visit.created_at = timezone.make_aware(datetime.datetime.combine(day, datetime.time(11, 0)))
            visit.save()
            
            bill = Billing.objects.create(
                patient=pat,
                visit=visit,
                bill_type='Pharmacy',
                payment_method=pm
            )
            bill.created_at = timezone.make_aware(datetime.datetime.combine(day, datetime.time(11, 30)))
            
            for med in selected_meds:
                qty = random.randint(1, 3)
                tm_pharm = TreatmentMaster.objects.get(name=f"Pharmacy: {med.name}")
                price = med.sales_rate
                BillingItem.objects.create(billing=bill, treatment=tm_pharm, qty=qty, price=price)
                total_amt += price * qty
                
            bill.total_amount = total_amt
            bill.paid_amount = total_amt # Pharmacy must be paid in full
            bill.save()

    # 7. Generate Pharmacy Purchases (Stock Purchases) for May 2026
    print("Generating Pharmacy Purchase records...")
    for i in range(5):
        sup = random.choice(suppliers)
        purchase_date = start_date + datetime.timedelta(days=random.randint(1, 20))
        
        # Create advanced PharmacyPurchase
        invoice_no = f"INV-PH-{random.randint(1000, 9999)}"
        purchase = PharmacyPurchase.objects.create(
            supplier=sup,
            invoice_no=invoice_no,
            purchase_date=purchase_date,
            notes="Bulk pharmacy inventory purchase"
        )
        
        subtotal = Decimal('0.00')
        selected_meds = random.sample(medicines, k=random.randint(2, 4))
        for med in selected_meds:
            qty = random.randint(10, 30)
            p_price = med.purchase_rate
            mrp = med.sales_rate
            amount = p_price * qty
            PharmacyPurchaseItem.objects.create(
                purchase=purchase,
                medicine=med,
                batch_no=f"B-{random.randint(100, 999)}",
                expiry_date=purchase_date + datetime.timedelta(days=random.randint(300, 700)),
                qty=qty,
                purchase_price=p_price,
                mrp=mrp,
                amount=amount
            )
            subtotal += amount
            
        purchase.subtotal = subtotal
        purchase.grand_total = subtotal
        purchase.paid_amount = subtotal # fully paid
        purchase.save()

    # 8. Generate General Expenses for May 2026
    print("Generating General Expense records...")
    expense_categories = [
        ('consumables', 'Dental Consumables Box Purchase', 'consumables', Decimal('4500.00'), 'Paid_To_DentStore'),
        ('marketing', 'Facebook Ad Campaign May', 'marketing', Decimal('12000.00'), 'SocialMediaAgency'),
        ('rent_electricity', 'Clinic Office Rent May 2026', 'rent_electricity', Decimal('40000.00'), 'Landlord Inc'),
        ('rent_electricity', 'Electricity Bill May 2026', 'rent_electricity', Decimal('7800.00'), 'State Power Corp'),
        ('water_bill', 'Water Supply Bill May 2026', 'water_bill', Decimal('1200.00'), 'Municipal Corporation'),
        ('internet_software', 'HMS Software subscription', 'internet_software', Decimal('3500.00'), 'DoctoSmart SaaS'),
        ('biomedical_waste', 'Biomedical Waste Disposal May', 'biomedical_waste', Decimal('2200.00'), 'EcoSafe Biohazard'),
        ('maintenance', 'AC Service & Repair', 'maintenance', Decimal('4800.00'), 'Cooling Experts')
    ]
    
    for key, title, cat, amount, paid_to in expense_categories:
        exp_date = start_date + datetime.timedelta(days=random.randint(2, 22))
        Expense.objects.create(
            title=title,
            category=cat,
            description=f"Overhead cost for {title}",
            amount=amount,
            date=exp_date,
            paid_to=paid_to,
            payment_method=random.choice(payment_methods),
            status='Paid'
        )

    # 9. Generate Salaries & Incentives (Doctor Salary & Staff Salary)
    print("Generating Salary records...")
    # Seed Doctor Salary Configs and paid records for current month
    for doc in doctors:
        sal_config, _ = DoctorSalary.objects.get_or_create(
            doctor=doc,
            defaults={'base_salary': Decimal('35000.00'), 'incentive_percent': Decimal('10.00')}
        )
        
        # Calculate final salary for May 2026
        base = sal_config.base_salary
        inc = Decimal('3500.00') # incentive
        bonus = Decimal('2000.00')
        ded = Decimal('500.00')
        final = base + inc + bonus - ded
        
        record = DoctorSalaryRecord.objects.create(
            doctor=doc,
            month=today.month,
            year=today.year,
            base_salary=base,
            incentive=inc,
            bonus=bonus,
            deductions=ded,
            final_salary=final,
            status='Paid',
            payment_date=today,
            payment_method='Bank Transfer',
            notes=f"{today.strftime('%B %Y')} salary processed"
        )
        
        # Create an expense under 'doctor_salary' to link
        Expense.objects.create(
            title=f"Doctor Salary - {doc.name}",
            category='doctor_salary',
            description=f"Salary payment for Dr. {doc.name} ({today.strftime('%B %Y')})",
            amount=final,
            date=today,
            paid_to=doc.name,
            payment_method='Bank Transfer',
            status='Paid',
            notes=f"Linked to record #{record.id}"
        )

    # Add 2 Staff Salary records directly as Expense entries under category 'salary_incentives'
    staff_salaries = [
        ('Staff Salary - John Doe (Receptionist)', Decimal('25000.00'), 'John Doe'),
        ('Staff Salary - Sneha Nair (Clinic Assistant)', Decimal('18000.00'), 'Sneha Nair')
    ]
    for title, amount, paid_to in staff_salaries:
        Expense.objects.create(
            title=title,
            category='salary_incentives',
            description=f"Monthly staff salary ({today.strftime('%B %Y')})",
            amount=amount,
            date=today,
            paid_to=paid_to,
            payment_method='Bank Transfer',
            status='Paid'
        )

    print("Dummy data generated successfully!")

if __name__ == '__main__':
    populate_dummy_data()
