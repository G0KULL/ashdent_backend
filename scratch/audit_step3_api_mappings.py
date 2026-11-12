import sys, os, json, inspect
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.urls import get_resolver
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

resolver = get_resolver()

def extract_endpoints(patterns, prefix=''):
    endpoints = []
    for p in patterns:
        if hasattr(p, 'url_patterns'):
            new_prefix = prefix + str(p.pattern)
            endpoints.extend(extract_endpoints(p.url_patterns, new_prefix))
        elif hasattr(p, 'callback') and p.callback:
            url = prefix + str(p.pattern)
            view_func = p.callback
            view_cls = getattr(view_func, 'view_class', None) or getattr(view_func, 'cls', None)
            endpoints.append({
                'url': '/' + url.lstrip('/'),
                'view_name': view_cls.__name__ if view_cls else view_func.__name__,
                'view_cls': view_cls,
                'view_func': view_func
            })
    return endpoints

raw_endpoints = extract_endpoints(resolver.url_patterns)
print(f"Extracted {len(raw_endpoints)} raw endpoint routes.")

# Detailed analysis for each endpoint
api_mappings = []

for ep in raw_endpoints:
    url = ep['url']
    view_cls = ep['view_cls']
    view_name = ep['view_name']
    
    methods = []
    serializer_name = None
    model_names = []
    collections = []
    operations = []
    company_filter = False
    branch_filter = False
    patient_rel = False
    appt_visit_rel = False
    perm_classes = []
    
    if view_cls:
        # Check standard methods
        for m in ['get', 'post', 'put', 'patch', 'delete']:
            if hasattr(view_cls, m):
                methods.append(m.upper())
                
        # Inspect source code of view
        try:
            source = inspect.getsource(view_cls)
            
            # Identify serializer
            import re
            ser_match = re.search(r'([A-Za-z0-9_]+Serializer)', source)
            if ser_match:
                serializer_name = ser_match.group(1)
                
            # Identify models
            from django.apps import apps
            all_models = {m.__name__: m for m in apps.get_models()}
            for mname, mobj in all_models.items():
                if f'{mname}.objects' in source or f'{mname}(' in source:
                    model_names.append(mname)
                    collections.append(mobj._meta.db_table)
                    
            # Operations
            if any(k in source for k in ['.create(', '.save(', 'serializer.save()', 'create_user(']):
                operations.append('CREATE')
            if any(k in source for k in ['.all(', '.filter(', '.get(', '.first()', '.count(']):
                operations.append('READ')
            if any(k in source for k in ['.update(', '.save()', 'partial=True']):
                operations.append('UPDATE')
            if any(k in source for k in ['.delete()']):
                operations.append('DELETE')
                
            # Scoping & filtering
            if 'scope.company' in source or 'company=' in source or 'company_id=' in source:
                company_filter = True
            if 'branch' in source or 'branch_id' in source or 'has_access_to_branch' in source:
                branch_filter = True
            if 'patient' in source or 'patient_id' in source:
                patient_rel = True
            if 'appointment' in source or 'visit' in source:
                appt_visit_rel = True
                
            # Permissions
            p_classes = getattr(view_cls, 'permission_classes', None)
            if p_classes:
                perm_classes = [c.__name__ for c in p_classes]
            else:
                perm_classes = ['IsAuthenticated (Global Default)']
                
        except Exception:
            pass

    api_mappings.append({
        'url': url,
        'http_methods': methods if methods else ['ALL'],
        'view_name': view_name,
        'serializer': serializer_name,
        'models': sorted(list(set(model_names))),
        'collections': sorted(list(set(collections))),
        'operations': sorted(list(set(operations))),
        'company_filtering': company_filter,
        'branch_filtering': branch_filter,
        'patient_relationship': patient_rel,
        'appointment_visit_relationship': appt_visit_rel,
        'permissions': perm_classes
    })

out_path = 'ashdent-back/scratch/step3_api_mappings.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(api_mappings, f, indent=2)

print(f"API mapping complete! Analyzed {len(api_mappings)} endpoints. Saved to {out_path}")

