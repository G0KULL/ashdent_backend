import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import (
    Company, Branch, Staff, Doctor, DoctorSchedule, DoctorScheduleProposal,
    DoctorDateOverride, Patient, Appointment, Visit, Billing, Payment,
    Transaction, Expense, Prescription, ClinicProfile, AutoNumbering
)

print("=" * 70)
print("ASHDENT HMS — IDEMPOTENT MULTI-BRANCH DATA BACKFILL SCRIPT")
print("=" * 70)

# 1. Company and Default Branch
company, c_created = Company.objects.get_or_create(
    code='ASHDENT',
    defaults={
        'name': 'AshDent Healthcare',
        'email': 'contact@ashdent.com',
        'phone': '9822001122',
        'is_active': True
    }
)
print(f"Company: {company.name} [{company.code}] (Created: {c_created})")

branch, b_created = Branch.objects.get_or_create(
    company=company,
    code='MAIN',
    defaults={
        'name': 'Main Branch',
        'phone': '9822001122',
        'city': 'Bangalore',
        'state': 'Karnataka',
        'country': 'India',
        'is_active': True
    }
)
print(f"Branch: {branch.name} [{branch.code}] (Created: {b_created})")

# 2. Staff Backfill
staff_count = 0
for st in Staff.objects.all():
    changed = False
    if not st.company_id:
        st.company = company
        changed = True
    if not st.primary_branch_id:
        st.primary_branch = branch
        changed = True
    if not st.accessible_branches:
        st.accessible_branches = [str(branch.id)]
        changed = True
    if changed:
        st.save()
        staff_count += 1
print(f"Staff updated: {staff_count} / {Staff.objects.count()}")

# 3. Doctor Backfill
doc_count = 0
for doc in Doctor.objects.all():
    changed = False
    if not doc.company_id:
        doc.company = company
        changed = True
    if not doc.primary_branch_id:
        doc.primary_branch = branch
        changed = True
    if not doc.assigned_branches:
        doc.assigned_branches = [str(branch.id)]
        changed = True
    if changed:
        doc.save()
        doc_count += 1
print(f"Doctors updated: {doc_count} / {Doctor.objects.count()}")

# 4. Schedules, Proposals, Overrides
sched_up = DoctorSchedule.objects.filter(company__isnull=True).update(company=company, branch=branch)
prop_up = DoctorScheduleProposal.objects.filter(company__isnull=True).update(company=company, branch=branch)
over_up = DoctorDateOverride.objects.filter(company__isnull=True).update(company=company, branch=branch)
print(f"Schedules backfilled: {sched_up}")
print(f"Proposals backfilled: {prop_up}")
print(f"Date Overrides backfilled: {over_up}")

# 5. Patients, Appointments, Visits
pat_up = Patient.objects.filter(company__isnull=True).update(company=company, registration_branch=branch)
appt_up = Appointment.objects.filter(company__isnull=True).update(company=company, branch=branch)
vis_up = Visit.objects.filter(company__isnull=True).update(company=company, branch=branch)
print(f"Patients backfilled: {pat_up}")
print(f"Appointments backfilled: {appt_up}")
print(f"Visits backfilled: {vis_up}")

# 6. Financials: Billing, Payment, Transaction, Expense
bill_up = Billing.objects.filter(company__isnull=True).update(company=company, branch=branch)
pay_up = Payment.objects.filter(company__isnull=True).update(company=company, branch=branch)
tx_up = Transaction.objects.filter(company__isnull=True).update(company=company, branch=branch)
exp_up = Expense.objects.filter(company__isnull=True).update(company=company, branch_ref=branch)
rx_up = Prescription.objects.filter(company__isnull=True).update(company=company, branch=branch)
print(f"Bills backfilled: {bill_up}")
print(f"Payments backfilled: {pay_up}")
print(f"Transactions backfilled: {tx_up}")
print(f"Expenses backfilled: {exp_up}")
print(f"Prescriptions backfilled: {rx_up}")

# 7. Clinic Profile & AutoNumbering
cp_up = ClinicProfile.objects.filter(company__isnull=True).update(company=company, branch=branch)
an_up = AutoNumbering.objects.filter(company__isnull=True).update(company=company, branch=branch)
print(f"Clinic Profile backfilled: {cp_up}")
print(f"AutoNumbering backfilled: {an_up}")

print("\n" + "=" * 70)
print("BACKFILL COMPLETED SUCCESSFULLY. VERIFYING ALL UNATTACHED RECORDS ARE ZERO:")
print("=" * 70)
print("Unscoped DoctorSchedules:", DoctorSchedule.objects.filter(company__isnull=True).count())
print("Unscoped Patients:", Patient.objects.filter(company__isnull=True).count())
print("Unscoped Appointments:", Appointment.objects.filter(company__isnull=True).count())
print("Unscoped Billings:", Billing.objects.filter(company__isnull=True).count())
print("Unscoped Payments:", Payment.objects.filter(company__isnull=True).count())
