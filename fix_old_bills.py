import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from patients.models import Billing

drafts = Billing.objects.filter(bill_type='Clinical', paid_amount=0).filter(notes__exact='')
count = 0
for d in drafts:
    d.is_invoice = False
    d.save()
    count += 1

drafts_null = Billing.objects.filter(bill_type='Clinical', paid_amount=0, notes__isnull=True)
for d in drafts_null:
    d.is_invoice = False
    d.save()
    count += 1

print(f"Updated {count} old draft bills.")
