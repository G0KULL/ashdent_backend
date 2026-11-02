import os
import sys
import django

sys.path.append(r'c:\Users\gokul\Downloads\dental software\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth.models import User

print("=== VERIFYING WEBINAR DEMO DATASET VIA API ===")
client = APIClient()
user = User.objects.first()
client.force_authenticate(user=user)

# 1. Dashboard / Today Appointments
res1 = client.get('/api/appointments/today/')
assert res1.status_code == 200, f"Failed today appts: {res1.status_code}"
print(f"[OK] Today Appointments Endpoint: Returned {len(res1.data)} appointments for today.")

# 2. Patient Search
res2 = client.get('/api/patient/search/')
assert res2.status_code == 200, f"Failed patient search: {res2.status_code}"
print(f"[OK] Patient Search Endpoint: Returned {len(res2.data)} patients.")

# 3. Billing List
res3 = client.get('/api/bill/list/')
assert res3.status_code == 200, f"Failed bill list: {res3.status_code}"
print(f"[OK] Billing List Endpoint: Returned {len(res3.data)} clinical bills.")

# 4. EHR Reports - Invoices
res4 = client.get('/api/reports/invoice/')
assert res4.status_code == 200, f"Failed report invoice: {res4.status_code}"
print(f"[OK] Invoice Report Endpoint: Returned {len(res4.data['results'])} report entries.")

print("\n=== ALL WEBINAR API ENDPOINTS VERIFIED PERFECTLY! ===")
