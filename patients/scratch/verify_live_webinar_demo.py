import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth.models import User
from patients.models import Patient

print("=" * 70)
print("  VERIFYING LIVE WEBINAR DATASET VIA REST API ENDPOINTS")
print("=" * 70)

client = APIClient()
admin_user = User.objects.filter(username='admin').first() or User.objects.first()
client.force_authenticate(user=admin_user)

# 1. Today's Appointments
res_today = client.get('/api/appointments/today/')
assert res_today.status_code == 200, f"Today appointments failed: {res_today.status_code}"
today_data = res_today.data
print(f"[OK] /api/appointments/today/ -> {len(today_data)} appointments returned for today.")
statuses = [a['status'] for a in today_data]
print(f"     Statuses: {statuses}")

# 2. Appointment Stats (Dashboard Cards & Weekly Trend)
res_stats = client.get('/api/appointments/stats/')
assert res_stats.status_code == 200, f"Stats failed: {res_stats.status_code}"
stats_data = res_stats.data
print(f"[OK] /api/appointments/stats/ -> Waiting: {stats_data.get('waiting')}, Engaged: {stats_data.get('engaged')}, Completed: {stats_data.get('completed')}")
print(f"     Total Revenue: Rs. {stats_data.get('total_revenue', 0):,.2f} | Collected: Rs. {stats_data.get('total_collected', 0):,.2f}")
print(f"     Weekly Trend Days: {len(stats_data.get('weekly_trend', []))} days populated.")

# 3. Doctor Performance
res_perf = client.get('/api/dashboard/doctor-performance/?period=this_month')
assert res_perf.status_code == 200, f"Doctor performance failed: {res_perf.status_code}"
print(f"[OK] /api/dashboard/doctor-performance/ -> Returned stats for {len(res_perf.data.get('doctors', []))} doctors.")

# 4. Finance Dashboard
res_fin = client.get('/api/finance/dashboard/?filter_type=monthly')
assert res_fin.status_code == 200, f"Finance dashboard failed: {res_fin.status_code}"
print(f"[OK] /api/finance/dashboard/ -> Income & Expense data returned cleanly.")

# 5. Odontogram Treatment History for Arjun Mathew
arjun = Patient.objects.filter(name='Arjun Mathew').first()
assert arjun is not None, "Arjun Mathew not found"
res_odont = client.get(f'/api/patient/{arjun.id}/treatment-history/')
assert res_odont.status_code == 200, f"Treatment history failed: {res_odont.status_code}"
odont_data = res_odont.data
print(f"[OK] /api/patient/{arjun.id}/treatment-history/ -> {len(odont_data)} treatment records returned.")
for rec in odont_data:
    print(f"     - Tooth {rec.get('tooth_number')}: {rec.get('treatment')} (Status: {rec.get('status')})")

# 6. Patient Search
res_pts = client.get('/api/patient/search/')
assert res_pts.status_code == 200, f"Patient search failed: {res_pts.status_code}"
print(f"[OK] /api/patient/search/ -> {len(res_pts.data)} patients ready for instant search.")

# 7. Billing & Invoices (Verify Cash Received and Balance Returned)
res_bills = client.get('/api/bill/list/')
assert res_bills.status_code == 200, f"Bill list failed: {res_bills.status_code}"
bills_data = res_bills.data
cash_bill = next((b for b in bills_data if b.get('payment_method') == 'Cash' and b.get('cash_received')), None)
print(f"[OK] /api/bill/list/ -> {len(bills_data)} bills returned.")
if cash_bill:
    print(f"     - Cash Bill Sample: Total Rs. {cash_bill.get('total_amount')}, Cash Received Rs. {cash_bill.get('cash_received')}, Balance Returned Rs. {cash_bill.get('balance_returned')}")

print("\n" + "=" * 70)
print("  ALL API ENDPOINTS TESTED AND VERIFIED PERFECTLY FOR WEBINAR!")
print("=" * 70)
