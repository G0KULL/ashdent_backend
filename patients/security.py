from django.contrib.auth.models import User
from patients.models import Staff

def get_authenticated_user(request):
    """
    Central user resolver for API requests.
    Checks:
    1. request.user if request.user.is_authenticated
    2. X-User-Id header (MongoDB ObjectId string, integer ID, or username)
    3. X-Username header
    """
    if hasattr(request, 'user') and request.user and request.user.is_authenticated:
        return request.user
        
    user_id = request.headers.get('X-User-Id', '').strip()
    username = request.headers.get('X-Username', '').strip()
    
    if not user_id and not username:
        return None
        
    from django.db import connections
    from bson import ObjectId
    
    db = connections['default'].database
    u_doc = None
    
    if user_id:
        if ObjectId.is_valid(user_id):
            u_doc = db['auth_user'].find_one({'_id': ObjectId(user_id)})
        if not u_doc:
            try:
                u_doc = db['auth_user'].find_one({'id': int(user_id)})
            except (ValueError, TypeError):
                pass
        if not u_doc:
            u_doc = db['auth_user'].find_one({'username': user_id})
            
    if not u_doc and username:
        u_doc = db['auth_user'].find_one({'username': username})
        
    if u_doc:
        user_obj = User.objects.filter(pk=u_doc['_id']).first()
        if not user_obj:
            user_obj = User.objects.filter(username=u_doc.get('username')).first()
        if user_obj and (user_obj.id is None or user_obj.pk is None):
            user_obj.id = u_doc['_id']
            user_obj.pk = u_doc['_id']
        return user_obj
        
    return None

def get_user_for_staff(staff_obj):
    if not staff_obj or not getattr(staff_obj, 'user_id', None):
        return None
    from bson import ObjectId
    from django.db import connections
    db = connections['default'].database
    uid_str = str(staff_obj.user_id)
    u_doc = None
    if ObjectId.is_valid(uid_str):
        u_doc = db['auth_user'].find_one({'_id': ObjectId(uid_str)})
    if not u_doc:
        try:
            u_doc = db['auth_user'].find_one({'id': int(uid_str)})
        except (ValueError, TypeError):
            pass
    if not u_doc:
        u_doc = db['auth_user'].find_one({'username': uid_str})
    if u_doc:
        u = User.objects.filter(username=u_doc.get('username')).first()
        if u:
            u.id = u_doc['_id']
            u.pk = u_doc['_id']
            return u
    return None

def resolve_user_by_id(user_id):
    if not user_id:
        return None
    from bson import ObjectId
    from django.db import connections
    db = connections['default'].database
    uid_str = str(user_id)
    u_doc = None
    if ObjectId.is_valid(uid_str):
        u_doc = db['auth_user'].find_one({'_id': ObjectId(uid_str)})
    if not u_doc:
        try:
            u_doc = db['auth_user'].find_one({'id': int(uid_str)})
        except (ValueError, TypeError):
            pass
    if not u_doc:
        u_doc = db['auth_user'].find_one({'username': uid_str})
    if u_doc:
        u = User.objects.filter(username=u_doc.get('username')).first()
        if u:
            u.id = u_doc['_id']
            u.pk = u_doc['_id']
            return u
    return None

def resolve_username_by_id(user_id):
    if not user_id:
        return None
    from bson import ObjectId
    from django.db import connections
    db = connections['default'].database
    uid_str = str(user_id)
    u_doc = None
    if ObjectId.is_valid(uid_str):
        u_doc = db['auth_user'].find_one({'_id': ObjectId(uid_str)}, {'username': 1})
    if not u_doc:
        try:
            u_doc = db['auth_user'].find_one({'id': int(uid_str)}, {'username': 1})
        except (ValueError, TypeError):
            pass
    if not u_doc:
        u_doc = db['auth_user'].find_one({'username': uid_str}, {'username': 1})
    if u_doc:
        return u_doc.get('username')
    return None

def is_super_admin(user):
    """
    Returns True if user is a Django Superuser (is_superuser=True).
    """
    if not user:
        return False
    return getattr(user, 'is_superuser', False) is True

def is_application_admin(user):
    """
    Returns True if user is an Application Admin (is_superuser=False and staff.role=='Admin')
    or a Super Admin (is_superuser=True).
    """
    if not user:
        return False
    if getattr(user, 'is_superuser', False):
        return True

    try:
        from django.db import connections
        db = connections['default'].database
        u_doc = db['auth_user'].find_one({'username': user.username})
        if u_doc:
            s_doc = db['patients_staff'].find_one({'user_id': u_doc['_id']})
            if s_doc:
                return (s_doc.get('role') or '').strip().lower() == 'admin'
    except Exception:
        pass

    staff = Staff.objects.filter(user_id=user.pk).first()
    return bool(staff and (staff.role or '').strip().lower() == 'admin')

def is_ordinary_staff(user):
    """
    Returns True if user is an authenticated user who is NOT a Super Admin and NOT an Application Admin.
    """
    if not user:
        return False
    return not is_super_admin(user) and not is_application_admin(user)

def can_create_staff_role(requesting_user, target_role):
    """
    Backend policy for staff creation:
    - Anonymous / Unauthenticated -> Denied (401)
    - Ordinary Staff -> Denied (403)
    - Application Admin -> Allowed ONLY for ordinary staff roles:
      ['Doctor', 'Pharmacist', 'Receptionist', 'Accountant', 'Dental Assistant', 'Assistant']
      CANNOT create 'Admin' or 'Super Admin'.
    - Super Admin -> Allowed to create 'Admin' or ordinary staff roles.
    """
    if not requesting_user:
        return False, "Authentication required to manage staff accounts.", 401
        
    target_role_clean = (target_role or '').strip()
    
    if is_super_admin(requesting_user):
        if target_role_clean.lower() in ['super admin', 'superuser']:
            return False, "Super Admin accounts must be managed via Django CLI or Django Admin panel.", 403
        return True, None, 200
        
    if is_application_admin(requesting_user):
        if target_role_clean.lower() in ['admin', 'super admin', 'superuser']:
            return False, "Application Admins are not permitted to create other Admin or Super Admin accounts.", 403
        allowed_ordinary = ['doctor', 'pharmacist', 'receptionist', 'accountant', 'dental assistant', 'assistant']
        if target_role_clean.lower() not in allowed_ordinary:
            return False, f"Application Admins can only create ordinary staff roles ({', '.join(r.capitalize() for r in allowed_ordinary)}).", 403
        return True, None, 200
        
    return False, "You do not have administrative privileges to create staff accounts.", 403

def can_modify_staff(requesting_user, target_staff, new_role=None, is_delete=False):
    """
    Backend policy for modifying staff accounts:
    - Anonymous / Unauthenticated -> Denied (401)
    - Ordinary Staff -> Denied (403)
    - Super Admin -> Can edit/delete any staff account and change any role.
    - Application Admin ->
      - CANNOT edit/delete another Admin.
      - CANNOT edit/delete self to change own role or delete self.
      - CANNOT change any staff's role to 'Admin' or 'Super Admin'.
      - CAN edit ordinary staff.
    """
    if not requesting_user:
        return False, "Authentication required to manage staff accounts.", 401
        
    if is_super_admin(requesting_user):
        return True, None, 200
        
    if not is_application_admin(requesting_user):
        return False, "You do not have administrative permissions to modify staff records.", 403
        
    requester_staff_id = None
    try:
        from django.db import connections
        db = connections['default'].database
        u_doc = db['auth_user'].find_one({'username': requesting_user.username})
        if u_doc:
            s_doc = db['patients_staff'].find_one({'user_id': u_doc['_id']})
            if s_doc:
                requester_staff_id = str(s_doc['_id'])
    except Exception:
        pass
        
    if not requester_staff_id:
        st = Staff.objects.filter(user_id=requesting_user.pk).first()
        if st:
            requester_staff_id = str(st.id)

    target_role = (target_staff.role or '') if target_staff else ''
    if target_role.strip().lower() == 'admin':
        return False, "Only Super Admin can modify or delete Admin accounts.", 403
        
    if target_staff and requester_staff_id and str(target_staff.id) == str(requester_staff_id):
        if new_role and new_role.strip().lower() != target_role.strip().lower():
            return False, "You cannot modify your own administrative role.", 403
        if is_delete:
            return False, "You cannot delete your own administrative account.", 403
            
    if new_role and new_role.strip().lower() in ['admin', 'super admin', 'superuser']:
        return False, "Only Super Admin can assign the Admin role.", 403
        
    return True, None, 200

def get_staff_for_user(user):
    """
    Safely retrieves the Staff record for a User, accounting for MongoDB ObjectId types.
    """
    if not user:
        return None

    from django.db import connections
    from bson import ObjectId
    db = connections['default'].database

    u_id = getattr(user, 'pk', None)
    if (not u_id or str(u_id) == 'None') and hasattr(user, 'username') and user.username:
        u_doc = db['auth_user'].find_one({'username': user.username})
        if u_doc:
            u_id = u_doc['_id']

    if not u_id or str(u_id) == 'None':
        return None

    queries = [{'user_id': u_id}, {'user_id': str(u_id)}]
    if ObjectId.is_valid(str(u_id)):
        queries.append({'user_id': ObjectId(str(u_id))})

    try:
        s_doc = db['patients_staff'].find_one({'$or': queries})
        if s_doc:
            return Staff.objects.filter(id=str(s_doc['_id'])).first()
    except Exception:
        pass

    return None

class RequestScope:
    def __init__(self, user=None, staff=None, company=None, branch=None, is_super=False, is_company_admin=False, is_branch_admin=False, accessible_branches=None):
        self.user = user
        self.staff = staff
        self.company = company
        self.branch = branch
        self.is_super = is_super
        self.is_company_admin = is_company_admin
        self.is_branch_admin = is_branch_admin
        self.accessible_branches = accessible_branches or []

    @property
    def is_authenticated(self):
        return self.user is not None

    def has_access_to_branch(self, branch_id):
        if self.is_super or self.is_company_admin:
            return True
        if not branch_id:
            return True
        b_id = str(branch_id)
        if self.branch and str(self.branch.pk) == b_id:
            return True
        return b_id in [str(getattr(b, 'pk', b)) for b in self.accessible_branches]

def get_request_scope(request):
    """
    Resolves the authenticated user, their company, and active branch context.
    Strictly prevents client-side tenant or branch spoofing.
    """
    from patients.models import Company, Branch
    user = get_authenticated_user(request)
    if not user:
        return RequestScope()

    is_super = is_super_admin(user)
    staff = get_staff_for_user(user)

    # 1. Super Admin scope: Can select any company / branch, or defaults to first active
    if is_super:
        company_header = request.headers.get('X-Company-Id') or request.query_params.get('company_id')
        branch_header = request.headers.get('X-Branch-Id') or request.query_params.get('branch_id')
        company = None
        branch = None

        if company_header:
            company = Company.objects.filter(pk=company_header, is_active=True).first()
        if not company:
            company = Company.objects.filter(is_active=True).first()

        if branch_header and company:
            branch = Branch.objects.filter(pk=branch_header, company=company, is_active=True).first()
        if not branch and company:
            branch = Branch.objects.filter(company=company, is_active=True).first()

        accessible_ids = [str(b.id) for b in Branch.objects.filter(company=company, is_active=True)] if company else []
        return RequestScope(
            user=user,
            staff=staff,
            company=company,
            branch=branch,
            is_super=True,
            is_company_admin=True,
            is_branch_admin=True,
            accessible_branches=accessible_ids
        )

    # 2. Ordinary Staff / Company Admin scope: Company strictly bound to staff.company
    if not staff or not staff.company:
        default_company = Company.objects.filter(is_active=True).first()
        default_branch = Branch.objects.filter(company=default_company, is_active=True).first() if default_company else None
        if staff and default_company and not staff.company:
            staff.company = default_company
            staff.primary_branch = default_branch
            staff.accessible_branches = [str(default_branch.id)] if default_branch else []
            staff.save()
        company = staff.company if staff else default_company
    else:
        company = staff.company

    user_role = (staff.role or '').strip().lower() if staff else ''
    is_company_admin = (user_role == 'admin')

    # Determine accessible branches
    if is_company_admin:
        accessible_qs = Branch.objects.filter(company=company, is_active=True)
        accessible_ids = [str(b.id) for b in accessible_qs]
    else:
        accessible_ids = staff.accessible_branches if staff else []
        if staff and staff.primary_branch_id and str(staff.primary_branch_id) not in accessible_ids:
            accessible_ids.append(str(staff.primary_branch_id))

    # Resolve active branch from header/param, validating authorization
    branch_header = request.headers.get('X-Branch-Id') or request.query_params.get('branch_id')
    branch = None
    if branch_header and str(branch_header) in accessible_ids:
        branch = Branch.objects.filter(pk=branch_header, company=company, is_active=True).first()

    if not branch and staff and staff.primary_branch:
        branch = staff.primary_branch

    if not branch and accessible_ids:
        branch = Branch.objects.filter(pk=accessible_ids[0], company=company, is_active=True).first()

    if not branch and company:
        branch = Branch.objects.filter(company=company, is_active=True).first()

    return RequestScope(
        user=user,
        staff=staff,
        company=company,
        branch=branch,
        is_super=False,
        is_company_admin=is_company_admin,
        is_branch_admin=is_company_admin or (user_role in ['branch admin', 'manager']),
        accessible_branches=accessible_ids
    )


