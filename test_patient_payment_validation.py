import os
import sys
import requests
from datetime import date

API = "http://127.0.0.1:8000/api"

def run_tests():
    print("=" * 60)
    print("RUNNING PATIENT REGISTRATION PAYMENT VALIDATION TESTS")
    print("=" * 60)

    # 1. Amount = 0: No Payment Info -> Allowed (201)
    p0 = {
        "date": str(date.today()),
        "name": "Test ZeroFee Patient",
        "phone": "9998887760",
        "gender": "Male",
        "dob": "1995-01-01",
        "consultation_fee": 0,
        "treatments": [],
        "tax": 0,
        "paid_amount": 0,
        "payment_method": ""
    }
    r0 = requests.post(f"{API}/patient/create/", json=p0)
    print(f"Test 1 [Amount=0, No Payment] -> Expected 201, Got {r0.status_code}")
    assert r0.status_code == 201, f"Failed 1: {r0.text}"

    # 2. Amount > 0, Missing Payment Method -> Blocked (400)
    p1 = {
        "date": str(date.today()),
        "name": "Test Fee Patient 1",
        "phone": "9998887761",
        "gender": "Female",
        "dob": "1992-05-10",
        "consultation_fee": 500,
        "paid_amount": 0,
        "payment_method": ""
    }
    r1 = requests.post(f"{API}/patient/create/", json=p1)
    print(f"Test 2 [Amount>0, Empty Payment Method] -> Expected 400, Got {r1.status_code}")
    assert r1.status_code == 400, f"Failed 2: {r1.text}"

    # 3. Amount > 0, Cash, Amount Paid = 0 -> Blocked (400)
    p2 = {
        "date": str(date.today()),
        "name": "Test Fee Patient 2",
        "phone": "9998887762",
        "gender": "Male",
        "dob": "1990-03-15",
        "consultation_fee": 500,
        "paid_amount": 0,
        "payment_method": "Cash"
    }
    r2 = requests.post(f"{API}/patient/create/", json=p2)
    print(f"Test 3 [Amount>0, Cash, Paid=0] -> Expected 400, Got {r2.status_code}")
    assert r2.status_code == 400, f"Failed 3: {r2.text}"

    # 4. Amount > 0, Cash, Amount Paid > Payable -> Blocked (400)
    p3 = {
        "date": str(date.today()),
        "name": "Test Fee Patient 3",
        "phone": "9998887763",
        "gender": "Male",
        "dob": "1988-08-20",
        "consultation_fee": 500,
        "paid_amount": 700,
        "payment_method": "Cash"
    }
    r3 = requests.post(f"{API}/patient/create/", json=p3)
    print(f"Test 4 [Amount>0, Cash, Paid>Payable] -> Expected 400, Got {r3.status_code}")
    assert r3.status_code == 400, f"Failed 4: {r3.text}"

    # 5. Amount > 0, Cash, Valid Amount Paid -> Allowed (201)
    p4 = {
        "date": str(date.today()),
        "name": "Test Fee Patient 4",
        "phone": "9998887764",
        "gender": "Female",
        "dob": "1993-11-12",
        "consultation_fee": 500,
        "paid_amount": 500,
        "payment_method": "Cash"
    }
    r4 = requests.post(f"{API}/patient/create/", json=p4)
    print(f"Test 5 [Amount>0, Cash, Valid Paid] -> Expected 201, Got {r4.status_code}")
    assert r4.status_code == 201, f"Failed 5: {r4.text}"

    # 6. Amount > 0, UPI, Missing Transaction ID -> Blocked (400)
    p5 = {
        "date": str(date.today()),
        "name": "Test Fee Patient 5",
        "phone": "9998887765",
        "gender": "Male",
        "dob": "1994-02-14",
        "consultation_fee": 500,
        "payment_method": "UPI",
        "transaction_id": "",
        "transaction_date": str(date.today())
    }
    r5 = requests.post(f"{API}/patient/create/", json=p5)
    print(f"Test 6 [Amount>0, UPI, Missing Txn ID] -> Expected 400, Got {r5.status_code}")
    assert r5.status_code == 400, f"Failed 6: {r5.text}"

    # 7. Amount > 0, UPI, Missing Transaction Date -> Blocked (400)
    p6 = {
        "date": str(date.today()),
        "name": "Test Fee Patient 6",
        "phone": "9998887766",
        "gender": "Female",
        "dob": "1996-06-18",
        "consultation_fee": 500,
        "payment_method": "UPI",
        "transaction_id": "UPI-123456789",
        "transaction_date": ""
    }
    r6 = requests.post(f"{API}/patient/create/", json=p6)
    print(f"Test 7 [Amount>0, UPI, Missing Txn Date] -> Expected 400, Got {r6.status_code}")
    assert r6.status_code == 400, f"Failed 7: {r6.text}"

    # 8. Amount > 0, UPI, Valid Txn ID & Date -> Allowed (201)
    p7 = {
        "date": str(date.today()),
        "name": "Test Fee Patient 7",
        "phone": "9998887767",
        "gender": "Male",
        "dob": "1991-09-25",
        "consultation_fee": 500,
        "payment_method": "UPI",
        "transaction_id": "UPI-987654321",
        "transaction_date": str(date.today())
    }
    r7 = requests.post(f"{API}/patient/create/", json=p7)
    print(f"Test 8 [Amount>0, UPI, Valid Txn ID & Date] -> Expected 201, Got {r7.status_code}")
    assert r7.status_code == 201, f"Failed 8: {r7.text}"

    print("=" * 60)
    print("ALL PATIENT REGISTRATION PAYMENT VALIDATION TESTS PASSED!")
    print("=" * 60)

if __name__ == '__main__':
    run_tests()
