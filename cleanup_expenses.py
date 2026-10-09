import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import Expense

all_expenses = Expense.objects.all().order_by('id')
seen = set()
duplicates = []

for e in all_expenses:
    key = (e.title, e.amount, e.date)
    if key in seen:
        duplicates.append(e.id)
    else:
        seen.add(key)

if duplicates:
    Expense.objects.filter(id__in=duplicates).delete()
    print(f"Deleted {len(duplicates)} duplicate expenses.")
else:
    print("No duplicates found.")
