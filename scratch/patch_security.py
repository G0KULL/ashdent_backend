security_path = 'ashdent-back/patients/security.py'

with open(security_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace get_authenticated_user
old_get_authenticated_user = """def get_authenticated_user(request):
    \"\"\"
    Central user resolver for API requests.
    Checks:
    1. request.user if request.user.is_authenticated
    2. X-User-Id header (MongoDB ObjectId string, integer ID, or username)
    3. X-Username header
    \"\"\"
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
        
    return None"""

new_get_authenticated_user = """def get_authenticated_user(request):
    \"\"\"
    Central user resolver for API requests.
    Validates identity strictly via authenticated request.user or Bearer JWT token.
    Zero trust in client-supplied headers (X-User-Id, X-Username).
    \"\"\"
    if hasattr(request, 'user') and request.user and request.user.is_authenticated:
        return request.user

    # Attempt JWT authentication if request.user is not yet populated
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication
        auth_res = JWTAuthentication().authenticate(request)
        if auth_res is not None:
            user, token = auth_res
            request.user = user
            request.auth = token
            return user
    except Exception:
        pass

    return None"""

content = content.replace(old_get_authenticated_user.replace('\r\n', '\n'), new_get_authenticated_user)
content = content.replace(old_get_authenticated_user, new_get_authenticated_user)

# Update has_access_to_branch
old_branch_access = """    def has_access_to_branch(self, branch_id):
        if self.is_super or self.is_company_admin:
            return True
        if not branch_id:
            return True
        b_id = str(branch_id)
        if self.branch and str(self.branch.pk) == b_id:
            return True
        return b_id in [str(getattr(b, 'pk', b)) for b in self.accessible_branches]"""

new_branch_access = """    def has_access_to_branch(self, branch_id):
        if not branch_id:
            return True
        b_id = str(branch_id)
        from patients.models import Branch
        branch_obj = Branch.objects.filter(pk=b_id, is_active=True).first()
        if not branch_obj:
            return False

        # Strict company check: branch must belong to user's company (unless superuser)
        if not self.is_super:
            if not self.company or str(branch_obj.company_id) != str(self.company.id):
                return False

        if self.is_super or self.is_company_admin:
            return True

        if self.branch and str(self.branch.pk) == b_id:
            return True

        return b_id in [str(getattr(b, 'pk', b)) for b in self.accessible_branches]"""

content = content.replace(old_branch_access.replace('\r\n', '\n'), new_branch_access)
content = content.replace(old_branch_access, new_branch_access)

# Update accessible_ids in get_request_scope
old_scope_branches = """    # Determine accessible branches
    if is_company_admin:
        accessible_qs = Branch.objects.filter(company=company, is_active=True)
        accessible_ids = [str(b.id) for b in accessible_qs]
    else:
        accessible_ids = staff.accessible_branches if staff else []
        if staff and staff.primary_branch_id and str(staff.primary_branch_id) not in accessible_ids:
            accessible_ids.append(str(staff.primary_branch_id))"""

new_scope_branches = """    # Determine accessible branches belonging to this company
    if is_company_admin:
        accessible_qs = Branch.objects.filter(company=company, is_active=True)
        accessible_ids = [str(b.id) for b in accessible_qs]
    else:
        raw_branch_ids = staff.accessible_branches if staff else []
        if staff and staff.primary_branch_id and str(staff.primary_branch_id) not in raw_branch_ids:
            raw_branch_ids.append(str(staff.primary_branch_id))
        valid_branches = Branch.objects.filter(pk__in=raw_branch_ids, company=company, is_active=True)
        accessible_ids = [str(b.id) for b in valid_branches]"""

content = content.replace(old_scope_branches.replace('\r\n', '\n'), new_scope_branches)
content = content.replace(old_scope_branches, new_scope_branches)

with open(security_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("security.py patched successfully!")

