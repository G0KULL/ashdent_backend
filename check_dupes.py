import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import Expense

expenses = Expense.objects.all().order_by('-id')[:20]
print(f"Total expenses: {Expense.objects.count()}")
for e in expenses:
    print(e.id, e.title, e.amount, e.date, e.category)

