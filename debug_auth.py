import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from patients.models import Staff, Company
from django.db import connections
from bson import ObjectId

db = connections['default'].database
db['auth_user'].delete_many({'username': 'admin_alpha_t'})
db['patients_staff'].delete_many({'name': 'Alpha Admin'})
db['patients_company'].delete_many({'name': 'Clinic Alpha'})

c = Company.objects.create(name="Clinic Alpha", code="ALPHA")
u = User.objects.create_user(username="admin_alpha_t", password="password123", email="admin_a_t@clinic.com")
s = Staff.objects.create(user_id=u.pk, name="Alpha Admin", role="Admin", is_super_admin=False, company=c)

str_user_id = str(u.pk)

u_doc = db['auth_user'].find_one({'_id': ObjectId(str_user_id)})
user = User.objects.filter(username=u_doc['username']).first() if u_doc else None

s_doc = db['patients_staff'].find_one({'user_id': u_doc['_id']})
if not s_doc:
    s_doc = db['patients_staff'].find_one({'user_id': str(u_doc['_id'])})
if not s_doc:
    s_doc = db['patients_staff'].find_one({'email': u_doc.get('email')})

staff = Staff.objects.filter(pk=str(s_doc['_id'])).first() if s_doc else None

print("user:", user, "is_superuser:", user.is_superuser if user else None)
print("staff:", staff, "is_super_admin:", staff.is_super_admin if staff else None, "role:", staff.role if staff else None)

db['auth_user'].delete_many({'username': 'admin_alpha_t'})
db['patients_staff'].delete_many({'name': 'Alpha Admin'})
db['patients_company'].delete_many({'name': 'Clinic Alpha'})
