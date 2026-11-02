import os
import sys
import django
from decimal import Decimal

# Setup Django environment
sys.path.append(r'c:\Users\gokul\Downloads\dental software\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from rest_framework.test import APIClient
from patients.models import Patient, Doctor, Billing, Payment, Visit, Appointment

print("=== STARTING COMPREHENSIVE BILLING AUDIT & REGRESSION TEST ===")
from django.contrib.auth.models import User
from patients.models import Staff

admin_user = User.objects.first()
if not admin_user:
    admin_user = User.objects.create_user('testadmin', 'admin@test.com', 'adminpass')

if not admin_user.pk:
    admin_user.save()

staff = Staff.objects.filter(user_id=admin_user.id).first()
if not staff:
    staff = Staff.objects.create(user=admin_user, name='Test Admin', role='Admin', is_active=True)

client = APIClient()
client.force_authenticate(user=admin_user)
print(f"Authenticated as Admin User: {admin_user.username}")

doctor = Doctor.objects.first()
if not doctor:
    doctor = Doctor.objects.create(name="Dr. Test", consultation_fee=500.00)

# -------------------------------------------------------------
# TEST 1: Zero-Amount Patient Registration
# -------------------------------------------------------------
print("\n--- TEST 1: Zero-Amount Patient Registration ---")
zero_payload = {
    'date': '2026-10-06',
    'firstName': 'ZeroFee',
    'lastName': 'Patient',
    'mobile': '9900011122',
    'dob': '1995-05-15',
    'gender': 'Female',
    'doctor': doctor.id,
    'consultation_fee': 0,
    'tax': 0,
    'paid_amount': 0,
    'payment_method': 'Cash',
    'treatments': []
}
res1 = client.post('/api/patient/create/', zero_payload, format='json')
assert res1.status_code == 201, f"Expected 201 for Rs.0 registration, got {res1.status_code}: {res1.data}"
patient1_id = res1.data['id']
print(f"SUCCESS: Rs.0 registration created patient ID {patient1_id} without payment errors.")

# -------------------------------------------------------------
# TEST 2: Cash Patient Registration with Valid Payment
# -------------------------------------------------------------
print("\n--- TEST 2: Cash Patient Registration (Rs.500 Fee, Rs.300 Paid) ---")
cash_payload = {
    'date': '2026-10-06',
    'firstName': 'CashTest',
    'lastName': 'User',
    'mobile': '9900011123',
    'dob': '1990-01-01',
    'gender': 'Male',
    'doctor': doctor.id,
    'consultation_fee': 500,
    'tax': 0,
    'paid_amount': 300,
    'payment_method': 'Cash',
    'treatments': []
}
res2 = client.post('/api/patient/create/', cash_payload, format='json')
assert res2.status_code == 201, f"Expected 201 for valid Cash payment, got {res2.status_code}: {res2.data}"
patient2_id = res2.data['id']
p2 = Patient.objects.get(id=patient2_id)
assert p2.total_balance == 200.0, f"Expected total balance 200.0, got {p2.total_balance}"
print(f"SUCCESS: Cash registration created patient ID {patient2_id} with due = Rs.200.0.")

# -------------------------------------------------------------
# TEST 3: Digital Payment without Transaction ID (Should be Rejected)
# -------------------------------------------------------------
print("\n--- TEST 3: Digital Payment without Transaction ID ---")
upi_invalid_payload = {
    'date': '2026-10-06',
    'firstName': 'UPIFail',
    'lastName': 'User',
    'mobile': '9900011124',
    'dob': '1992-03-10',
    'gender': 'Female',
    'doctor': doctor.id,
    'consultation_fee': 500,
    'tax': 0,
    'paid_amount': 500,
    'payment_method': 'UPI',
    'transaction_id': '', # Missing!
    'transaction_date': '2026-10-06',
}
res3 = client.post('/api/patient/create/', upi_invalid_payload, format='json')
assert res3.status_code == 400, f"Expected 400 rejection for missing transaction_id, got {res3.status_code}"
print("SUCCESS: Digital payment without transaction ID was rejected server-side.")

# -------------------------------------------------------------
# TEST 4: Digital Payment with Valid Transaction ID
# -------------------------------------------------------------
print("\n--- TEST 4: Valid Digital Payment (UPI) ---")
upi_valid_payload = {
    'date': '2026-10-06',
    'firstName': 'UPIPass',
    'lastName': 'User',
    'mobile': '9900011125',
    'dob': '1992-03-10',
    'gender': 'Female',
    'doctor': doctor.id,
    'consultation_fee': 500,
    'tax': 0,
    'paid_amount': 500,
    'payment_method': 'UPI',
    'transaction_id': 'UPI987654321',
    'transaction_date': '2026-10-06',
}
res4 = client.post('/api/patient/create/', upi_valid_payload, format='json')
assert res4.status_code == 201, f"Expected 201 for valid UPI payment, got {res4.status_code}: {res4.data}"
print("SUCCESS: Valid UPI payment accepted server-side.")

# -------------------------------------------------------------
# TEST 5: Negative Financial Values Rejection
# -------------------------------------------------------------
print("\n--- TEST 5: Rejection of Negative Financial Values ---")
neg_payload = {
    'date': '2026-10-06',
    'firstName': 'NegVal',
    'lastName': 'User',
    'mobile': '9900011126',
    'dob': '1992-03-10',
    'gender': 'Male',
    'doctor': doctor.id,
    'consultation_fee': -100, # Invalid negative fee!
    'payment_method': 'Cash',
    'paid_amount': 50
}
res5 = client.post('/api/patient/create/', neg_payload, format='json')
assert res5.status_code == 400, f"Expected 400 rejection for negative consultation fee, got {res5.status_code}"
print("SUCCESS: Negative consultation fee rejected server-side.")

# -------------------------------------------------------------
# TEST 6: Paid Amount > Payable Amount Rejection
# -------------------------------------------------------------
print("\n--- TEST 6: Rejection of Paid Amount > Payable Amount ---")
overpay_payload = {
    'date': '2026-10-06',
    'firstName': 'Overpay',
    'lastName': 'User',
    'mobile': '9900011127',
    'dob': '1992-03-10',
    'gender': 'Male',
    'doctor': doctor.id,
    'consultation_fee': 300,
    'payment_method': 'Cash',
    'paid_amount': 500 # Paid > Fee!
}
res6 = client.post('/api/patient/create/', overpay_payload, format='json')
assert res6.status_code == 400, f"Expected 400 rejection for overpayment, got {res6.status_code}"
print("SUCCESS: Paid amount > Payable amount rejected server-side.")

# -------------------------------------------------------------
# TEST 7: Standalone Bill Creation & Update Validation
# -------------------------------------------------------------
print("\n--- TEST 7: Standalone Bill Creation & Overpayment Protection ---")
res7 = client.post('/api/bill/create/', {
    'patient_id': patient1_id,
    'doctor_id': doctor.id,
    'total_amount': 1000,
    'paid_amount': 400,
    'payment_method': 'Cash'
}, format='json')
assert res7.status_code in [200, 201], f"Expected 200/201 for bill creation, got {res7.status_code}: {res7.data}"
bill_id = res7.data['id']

# Attempt to add payment exceeding remaining due (due = 600, attempting to add 800)
res_pay_exceed = client.post(f'/api/payment/pay/{bill_id}/', {
    'type': 'Billing',
    'amount': 800,
    'payment_method': 'Cash'
}, format='json')
assert res_pay_exceed.status_code == 400, f"Expected 400 rejection for payment exceeding remaining due, got {res_pay_exceed.status_code}"
print("SUCCESS: Payment exceeding remaining due was rejected server-side.")

# Add valid partial payment of 600 to complete bill
res_pay_valid = client.post(f'/api/payment/pay/{bill_id}/', {
    'type': 'Billing',
    'amount': 600,
    'payment_method': 'Cash'
}, format='json')
assert res_pay_valid.status_code == 200, f"Expected 200 for valid payment add, got {res_pay_valid.status_code}: {res_pay_valid.data}"
assert res_pay_valid.data['status'] == 'Paid', f"Expected bill status Paid, got {res_pay_valid.data['status']}"
print("SUCCESS: Valid payment add transitioned bill to Paid status.")

print("\n=== ALL BILLING AUDIT & REGRESSION TESTS PASSED CLEANLY! ===")
