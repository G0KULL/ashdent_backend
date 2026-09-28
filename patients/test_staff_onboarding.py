import unittest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from patients.models import Company, Staff, Doctor, AuditLog
from django.db import connections

class StaffOnboardingSecurityTestCase(unittest.TestCase):
    def clean_db(self):
        try:
            db = connections['default'].database
            db['patients_staff'].delete_many({})
            db['patients_doctor'].delete_many({})
            db['auth_user'].delete_many({})
            db['patients_company'].delete_many({})
            db['patients_auditlog'].delete_many({})
        except Exception:
            pass

    def setUp(self):
        self.client = APIClient()
        self.clean_db()

        # Companies
        self.company_a = Company.objects.create(name="Clinic Alpha", code="ALPHA")
        self.company_b = Company.objects.create(name="Clinic Beta", code="BETA")

        # Super Admin User
        self.super_user = User.objects.create_superuser(username="superadmin_t", password="password123", email="super_t@clinic.com")
        self.super_staff = Staff.objects.create(
            user_id=self.super_user.pk,
            name="Super Admin",
            role="Admin",
            is_super_admin=True,
            company=self.company_a
        )

        # Company Admin User (Company A)
        self.admin_a_user = User.objects.create_user(username="admin_alpha_t", password="password123", email="admin_a_t@clinic.com")
        self.admin_a_staff = Staff.objects.create(
            user_id=self.admin_a_user.pk,
            name="Alpha Admin",
            role="Admin",
            is_super_admin=False,
            company=self.company_a
        )

        # Normal Staff User (Doctor in Company A)
        self.doctor_a_user = User.objects.create_user(username="dr_alpha_t", password="password123", email="doc_a_t@clinic.com")
        self.doctor_a_staff = Staff.objects.create(
            user_id=self.doctor_a_user.pk,
            name="Dr. Alpha",
            role="Doctor",
            company=self.company_a
        )

        # Staff in Company B
        self.staff_b_user = User.objects.create_user(username="staff_beta_t", password="password123", email="beta_t@clinic.com")
        self.staff_b = Staff.objects.create(
            user_id=self.staff_b_user.pk,
            name="Beta Staff",
            role="Pharmacist",
            company=self.company_b
        )

    def tearDown(self):
        self.clean_db()

    def test_1_company_admin_can_create_staff_for_own_company(self):
        payload = {
            "first_name": "Doctor",
            "last_name": "One",
            "role": "Doctor",
            "email": "doc1@alpha.com",
            "phone": "9876543210",
            "username": "doc_one",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "specialization": "Orthodontics",
            "consultation_fee": 600
        }
        res = self.client.post('/api/staff/onboard/', payload, HTTP_X_USER_ID=str(self.admin_a_user.pk), format='json')
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        u = User.objects.get(username='doc_one')
        created_staff = Staff.objects.get(user_id=u.pk)
        self.assertEqual(str(created_staff.company_id), str(self.company_a.pk))
        self.assertEqual(created_staff.role, 'Doctor')

    def test_2_company_admin_cannot_create_staff_for_another_company(self):
        payload = {
            "first_name": "Infiltrator",
            "last_name": "Staff",
            "role": "Accountant",
            "email": "infilt@beta.com",
            "phone": "9876543211",
            "username": "infiltrator",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "company_id": str(self.company_b.pk)
        }
        res = self.client.post('/api/staff/onboard/', payload, HTTP_X_USER_ID=str(self.admin_a_user.pk), format='json')
        self.assertEqual(res.status_code, 201)
        u = User.objects.get(username='infiltrator')
        created_staff = Staff.objects.get(user_id=u.pk)
        self.assertEqual(str(created_staff.company_id), str(self.company_a.pk))

    def test_3_company_admin_cannot_create_super_admin(self):
        payload = {
            "first_name": "Fake",
            "last_name": "Super",
            "role": "Super Admin",
            "is_super_admin": True,
            "email": "fakesuper@alpha.com",
            "phone": "9876543212",
            "username": "fakesuper",
            "password": "Password123!",
            "confirm_password": "Password123!"
        }
        res = self.client.post('/api/staff/onboard/', payload, HTTP_X_USER_ID=str(self.admin_a_user.pk), format='json')
        self.assertEqual(res.status_code, 403)

    def test_4_company_admin_cannot_modify_another_company_staff(self):
        res = self.client.put(f'/api/staff/{self.staff_b.pk}/update/', {'name': 'Hacked Name'}, HTTP_X_USER_ID=str(self.admin_a_user.pk), format='json')
        self.assertEqual(res.status_code, 403)

    def test_5_company_admin_cannot_list_another_company_staff(self):
        res = self.client.get('/api/staff/list/', HTTP_X_USER_ID=str(self.admin_a_user.pk))
        self.assertEqual(res.status_code, 200)
        staff_ids = [str(s['id']) for s in res.json()]
        self.assertNotIn(str(self.staff_b.pk), staff_ids)

    def test_6_company_admin_cannot_access_another_company_staff_profile(self):
        res = self.client.get(f'/api/staff/{self.staff_b.pk}/', HTTP_X_USER_ID=str(self.admin_a_user.pk))
        self.assertEqual(res.status_code, 403)

    def test_7_super_admin_can_create_staff_for_authorized_company(self):
        payload = {
            "first_name": "Beta",
            "last_name": "Accountant",
            "role": "Accountant",
            "email": "acc@beta.com",
            "phone": "9876543215",
            "username": "beta_acc",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "company_id": str(self.company_b.pk)
        }
        res = self.client.post('/api/staff/onboard/', payload, HTTP_X_USER_ID=str(self.super_user.pk), format='json')
        self.assertEqual(res.status_code, 201)
        u = User.objects.get(username='beta_acc')
        created_staff = Staff.objects.get(user_id=u.pk)
        self.assertEqual(str(created_staff.company_id), str(self.company_b.pk))

    def test_8_role_assignment_and_permissions(self):
        roles_to_test = [
            ("Doctor", "doc_user", "doc@test.com"),
            ("Dental Assistant", "assistant_user", "ass@test.com"),
            ("Pharmacist", "pharm_user", "pharm@test.com"),
            ("Accountant", "acc_user", "acc@test.com"),
            ("Admin", "admin_user", "adm@test.com")
        ]
        for role, username, email in roles_to_test:
            payload = {
                "first_name": role,
                "last_name": "User",
                "role": role,
                "email": email,
                "phone": "9998887776",
                "username": username,
                "password": "Password123!",
                "confirm_password": "Password123!"
            }
            res = self.client.post('/api/staff/onboard/', payload, HTTP_X_USER_ID=str(self.super_user.pk), format='json')
            self.assertEqual(res.status_code, 201)
            u = User.objects.get(username=username)
            st = Staff.objects.get(user_id=u.pk)
            self.assertEqual(st.role, role)
            self.assertTrue(len(st.permissions) > 0)

    def test_13_inactive_staff_cannot_login(self):
        self.doctor_a_staff.is_active = False
        self.doctor_a_staff.save()
        res = self.client.post('/api/login/', {'username': 'dr_alpha_t', 'password': 'password123'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_14_duplicate_email_rejected(self):
        payload = {
            "first_name": "Dup",
            "last_name": "Email",
            "role": "Doctor",
            "email": "doc_a_t@clinic.com",
            "phone": "9876543299",
            "username": "dup_email_user",
            "password": "Password123!",
            "confirm_password": "Password123!"
        }
        res = self.client.post('/api/staff/onboard/', payload, HTTP_X_USER_ID=str(self.super_user.pk), format='json')
        self.assertEqual(res.status_code, 400)

    def test_15_duplicate_username_rejected(self):
        payload = {
            "first_name": "Dup",
            "last_name": "User",
            "role": "Doctor",
            "email": "newunique@clinic.com",
            "phone": "9876543299",
            "username": "dr_alpha_t",
            "password": "Password123!",
            "confirm_password": "Password123!"
        }
        res = self.client.post('/api/staff/onboard/', payload, HTTP_X_USER_ID=str(self.super_user.pk), format='json')
        self.assertEqual(res.status_code, 400)

    def test_18_unauthorized_users_cannot_access_onboarding(self):
        payload = {
            "first_name": "Hacker",
            "last_name": "User",
            "role": "Admin",
            "email": "hacker@clinic.com",
            "phone": "9876543299",
            "username": "hacker",
            "password": "Password123!",
            "confirm_password": "Password123!"
        }
        res = self.client.post('/api/staff/onboard/', payload, HTTP_X_USER_ID=str(self.doctor_a_user.pk), format='json')
        self.assertEqual(res.status_code, 403)
