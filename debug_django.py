import json
from django.test import RequestFactory
from django.db import connections
from patients.models import Staff, Doctor
from patients.finance_views import FinanceDashboardView
from bson import ObjectId

# Create a request factory
factory = RequestFactory()

db = connections['default'].database

# Find a staff member whose role is Doctor and has a user link
staff_cursor = db['patients_staff'].find({'role': 'Doctor', 'user_id': {'$ne': None}})
for staff_doc in staff_cursor:
    user_id = staff_doc.get('user_id')
    user_doc = db['auth_user'].find_one({'_id': ObjectId(user_id)})
    if user_doc:
        print(f"Testing for doctor: {staff_doc.get('name')} (User: {user_doc.get('username')}, ID: {user_id})")
        
        # Create request with doctor headers
        req = factory.get('/api/finance/dashboard/?filter_type=monthly')
        req.META['HTTP_X_USER_ID'] = str(user_id)
        req.META['HTTP_X_USERNAME'] = str(user_doc.get('username'))
        
        # Call view
        view = FinanceDashboardView.as_view()
        response = view(req)
        
        print("Response Status:", response.status_code)
        if response.status_code == 200:
            data = response.data
            print("KEYS:", list(data.keys()))
            print("MONTHLY INCOME TOTAL FOR DOCTOR:", data['monthlyIncome']['total'])
            print("DOCTOR REVENUE ENTRIES:")
            for doc in data['doctorRevenue']:
                print(doc)
            print("DETAILED LEDGER SAMPLE:")
            for ledger in data['detailedIncome'][:3]:
                print(ledger)
        else:
            print("Error response:", response.data)
        break
else:
    print("No doctor with a valid auth_user link was found in MongoDB database.")
