import re

views_path = 'ashdent-back/patients/views.py'
with open(views_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add permissions imports
if 'from rest_framework.permissions import' not in content:
    content = "from rest_framework.permissions import IsAuthenticated, AllowAny\nfrom rest_framework_simplejwt.tokens import RefreshToken\n" + content

# 2. Patch get_user_doctor (around line 105)
old_doctor_fn = re.search(r'def get_user_doctor\(request\):.*?(?=\ndef log_audit)', content, re.DOTALL)
if old_doctor_fn:
    new_doctor_fn = '''def get_user_doctor(request):
    """Return the Doctor profile linked to the authenticated user, or None."""
    user = get_authenticated_user(request)
    if not user:
        return None
    from .security import get_staff_for_user
    staff = get_staff_for_user(user)
    if staff and staff.doctor_profile:
        return staff.doctor_profile
    if staff and staff.role == 'Doctor' and getattr(staff, 'doctor_profile_id', None):
        return Doctor.objects.filter(id=staff.doctor_profile_id).first()
    return None

'''
    content = content[:old_doctor_fn.start()] + new_doctor_fn + content[old_doctor_fn.end():]
    print("get_user_doctor patched.")
else:
    print("WARNING: old_doctor_fn not matched!")

# 3. Patch get_user_role
old_role_fn = re.search(r'def get_user_role\(request\):.*?(?=\ndef require_role)', content, re.DOTALL)
if old_role_fn:
    new_role_fn = '''def get_user_role(request):
    """Extract the role of the currently authenticated user from Staff profile."""
    user = get_authenticated_user(request)
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    if getattr(user, 'is_superuser', False):
        return 'Admin'
    from .security import get_staff_for_user
    staff = get_staff_for_user(user)
    if staff and staff.role:
        return staff.role
    return 'Staff'

'''
    content = content[:old_role_fn.start()] + new_role_fn + content[old_role_fn.end():]
    print("get_user_role patched.")
else:
    print("WARNING: old_role_fn not matched!")

# 4. Patch LoginView
old_login_block = re.search(r'class LoginView\(APIView\):.*?(?=\ndef check_username_exists)', content, re.DOTALL)
if old_login_block:
    new_login_block = '''class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        user = authenticate(username=username, password=password)
        if not user and username:
            try:
                user_obj = User.objects.filter(username__iexact=username).first()
                if user_obj:
                    from django.contrib.auth import authenticate as auth
                    user = auth(username=user_obj.username, password=password)
            except Exception:
                pass

        if user:
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)

            role = 'Admin'
            perms = []
            doctor_profile_id = None
            name = user.get_full_name() or user.username
            
            user_id_str = str(user.pk) if user.pk else str(user.id)
            try:
                from django.db import connections
                db = connections['default'].database
                u_doc = db['auth_user'].find_one({'username': user.username})
                if u_doc:
                    user_id_str = str(u_doc['_id'])
                    s_doc = db['patients_staff'].find_one({'user_id': u_doc['_id']})
                    if s_doc:
                        role = s_doc.get('role', 'Admin')
                        perms = s_doc.get('permissions', [])
                        if s_doc.get('doctor_profile_id'):
                            doctor_profile_id = str(s_doc.get('doctor_profile_id'))
                        name = s_doc.get('name', name)
            except Exception:
                pass
            
            if getattr(user, 'is_superuser', False) or role == 'Admin':
                perms = ['income-analytics', 'expense-manager', 'billing', 'pharmacy', 'stock', 'prescriptions', 'lab', 'users', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'follow-ups', 'pre-bookings', 'communication', 'tele-medicine', 'website-appointment', 'purchases', 'doctors', 'settings', 'pathology-lab', 'dental-lab']
                
            return Response({
                'id': user_id_str,
                'username': user.username,
                'role': role,
                'is_superuser': getattr(user, 'is_superuser', False),
                'permissions': perms,
                'doctor_profile_id': doctor_profile_id,
                'doctor_id': doctor_profile_id,
                'name': name,
                'access': access_token,
                'refresh': refresh_token,
                'access_token': access_token,
                'refresh_token': refresh_token
            })
        return Response({'error': 'Invalid credentials'}, status=401)

'''
    content = content[:old_login_block.start()] + new_login_block + content[old_login_block.end():]
    print("LoginView patched.")
else:
    print("WARNING: old_login_block not matched!")

# 5. Patch WebsiteAppointmentRequestListCreateView
old_web_block = re.search(r'class WebsiteAppointmentRequestListCreateView\(APIView\):.*?(?=\ndef post\(self, request\):)', content, re.DOTALL)
if old_web_block:
    new_web_block = '''class WebsiteAppointmentRequestListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
'''
    # We replace from class declaration to the start of get
    full_web_match = re.search(r'class WebsiteAppointmentRequestListCreateView\(APIView\):.*?def get\(self, request\):', content, re.DOTALL)
    if full_web_match:
        content = content[:full_web_match.start()] + new_web_block + content[full_web_match.end():]
        print("WebsiteAppointmentRequestListCreateView patched.")

# 6. Remove remaining empty authentication_classes and permission_classes overrides
# Exclude LoginView which has permission_classes = [AllowAny]
content = re.sub(r'(\n\s*authentication_classes\s*=\s*\[\s*\]\s*\n\s*permission_classes\s*=\s*\[\s*\]\s*)', '\n', content)

with open(views_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("views.py patched successfully!")

