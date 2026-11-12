import os, sys, inspect, re
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
os.environ['DJANGO_DB_NAME'] = 'dental_clinic_db_migrated'
import django; django.setup()

from django.urls import get_resolver
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

resolver = get_resolver()

def extract_patterns(url_patterns, prefix=''):
    endpoints = []
    for pattern in url_patterns:
        if hasattr(pattern, 'url_patterns'):
            # Sub-resolver
            endpoints.extend(extract_patterns(pattern.url_patterns, prefix + str(pattern.pattern)))
        else:
            url = prefix + str(pattern.pattern)
            callback = pattern.callback
            endpoints.append((url, callback))
    return endpoints

all_endpoints = extract_patterns(resolver.url_patterns)
print(f"Total URL patterns discovered: {len(all_endpoints)}")

matrix = []

for url, callback in all_endpoints:
    # Filter to api/ endpoints
    if not url.startswith('api/'):
        continue
        
    view_func = callback
    view_class = getattr(callback, 'view_class', None)
    view_name = view_class.__name__ if view_class else getattr(view_func, '__name__', str(view_func))
    
    # Determine HTTP methods
    methods = []
    if view_class:
        if hasattr(view_class, 'http_method_names'):
            methods = [m.upper() for m in view_class.http_method_names if m.upper() in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']]
    elif hasattr(view_func, 'actions'):
        methods = [m.upper() for m in view_func.actions.keys()]
    else:
        methods = ['ANY']
        
    # Check permissions & authentication
    auth_classes = []
    perm_classes = []
    if view_class:
        auth_classes = [c.__name__ for c in getattr(view_class, 'authentication_classes', [])]
        perm_classes = [c.__name__ for c in getattr(view_class, 'permission_classes', [])]
        
    # Inspect source code of view class or function for tenant scoping
    src_code = ""
    try:
        if view_class:
            src_code = inspect.getsource(view_class)
        else:
            src_code = inspect.getsource(view_func)
    except Exception:
        src_code = ""
        
    company_scoped = ('get_request_scope' in src_code or 'company_id' in src_code or 'company=' in src_code or 'request.company' in src_code or 'has_company' in src_code)
    branch_scoped = ('branch_id' in src_code or 'branch=' in src_code or 'X-Branch-Id' in src_code or 'branch' in src_code)
    patient_validated = ('patient_id' in src_code or 'patient=' in src_code or 'patient' in src_code)
    role_restricted = ('IsAdminUser' in str(perm_classes) or 'role' in src_code or 'is_superuser' in src_code or 'is_staff' in src_code)
    
    # Read vs Write
    is_write = any(m in ['POST', 'PUT', 'PATCH', 'DELETE'] for m in methods) or 'def post' in src_code or 'def put' in src_code or 'def patch' in src_code or 'def delete' in src_code
    is_read = 'GET' in methods or 'def get' in src_code or 'def list' in src_code or 'def retrieve' in src_code
    
    auth_required = ('AllowAny' not in perm_classes) if perm_classes else False
    if 'login' in url or 'register' in url or 'token/refresh' in url:
        auth_required = False

    matrix.append({
        'url': '/' + url,
        'methods': methods,
        'view_name': view_name,
        'auth_required': auth_required,
        'permission_classes': perm_classes,
        'company_scoped': company_scoped,
        'branch_scoped': branch_scoped,
        'patient_validated': patient_validated,
        'role_restricted': role_restricted,
        'is_read': is_read,
        'is_write': is_write
    })

print(f"Total API endpoints analyzed: {len(matrix)}")
import json
with open('ashdent-back/scratch/audit5_endpoint_matrix.json', 'w') as f:
    json.dump(matrix, f, indent=2)

# Count security statistics
unauthenticated = [e for e in matrix if not e['auth_required']]
public_write = [e for e in matrix if not e['auth_required'] and e['is_write']]
unscoped_clinical_or_fin = [
    e for e in matrix 
    if any(k in e['url'] for k in ['patient', 'bill', 'payment', 'clinical', 'note', 'treatment', 'prescription', 'estimate'])
    and not e['company_scoped']
]

print(f"Unauthenticated endpoints count: {len(unauthenticated)}")
print(f"Public write endpoints: {[e['url'] for e in public_write]}")
print(f"Potentially unscoped clinical/financial endpoints count: {len(unscoped_clinical_or_fin)}")
for e in unscoped_clinical_or_fin:
    print(f"  Unscoped check: {e['url']} -> {e['view_name']}")

