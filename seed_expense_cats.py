import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import ExpenseCategory

categories = [
    "AC Chiller Bills",
    "Clinic Maintenance",
    "Consumables",
    "Dental Supplies",
    "Electricity Bill",
    "Equipment Services",
    "Insurance",
    "Internet Bill",
    "Laboratory Bills",
    "Licensing, Permits, Compliance",
    "Marketing Expenses",
    "Miscellaneous Expenses",
    "Mobile Phone Recharges",
    "Office Supplies",
    "Patient Refunds",
    "Pharmacy Inventory",
    "Postage & Courier",
    "Printing & Stationery",
    "Professional Fees",
    "Rent/Lease",
    "Repairs & Maintenance",
    "Salary/Wages",
    "Software Subscriptions",
    "Taxes",
    "Training & Development",
    "Travel Expenses",
    "Water & Utilities",
    "Website/Hosting"
]

def seed_categories():
    for name in categories:
        key = name.lower().replace(" ", "_").replace("&", "and").replace(",", "").replace("/", "_")
        ExpenseCategory.objects.get_or_create(
            key=key,
            defaults={
                'name': name,
                'color': '#3b82f6',
                'icon': 'Receipt',
                'is_predefined': True
            }
        )
    print("Expense categories seeded successfully!")

if __name__ == "__main__":
    seed_categories()
