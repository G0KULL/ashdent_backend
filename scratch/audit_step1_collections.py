import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections
from bson import ObjectId
import datetime
from decimal import Decimal

db = connections['default'].database

def serialize(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)

def redact_value(field_name, val):
    fn = field_name.lower()
    if any(k in fn for k in ['name', 'first_name', 'last_name']) and not any(k in fn for k in ['company', 'branch', 'procedure', 'treatment', 'medicine']):
        return "REDACTED_NAME"
    if any(k in fn for k in ['phone', 'mobile']):
        return "REDACTED_PHONE"
    if any(k in fn for k in ['email']):
        return "redacted@example.com"
    if any(k in fn for k in ['address']):
        return "REDACTED_ADDRESS"
    if any(k in fn for k in ['password']):
        return "REDACTED_HASH"
    return val

FRAMEWORK_COLS = {
    'auth_permission', 'auth_user', 'django_content_type', 'django_migrations'
}

cols = sorted(db.list_collection_names())
inventory = {}

for col_name in cols:
    col = db[col_name]
    count = col.count_documents({})
    
    # Indexes
    indexes = []
    for idx in col.list_indexes():
        indexes.append({
            'name': idx.get('name'),
            'key': list(idx.get('key', {}).items()),
            'unique': idx.get('unique', False)
        })
        
    # Analyze fields across sample of documents (up to 100 docs)
    field_stats = {}
    sample_docs = list(col.find().limit(100))
    
    for doc in sample_docs:
        for k, v in doc.items():
            if k not in field_stats:
                field_stats[k] = {'types': set(), 'null_count': 0, 'present_count': 0}
            field_stats[k]['present_count'] += 1
            if v is None:
                field_stats[k]['null_count'] += 1
                field_stats[k]['types'].add('NoneType')
            else:
                field_stats[k]['types'].add(type(v).__name__)
                
    # Prepare redacted sample document
    sample_doc = col.find_one()
    redacted_sample = {}
    if sample_doc:
        for k, v in sample_doc.items():
            redacted_sample[k] = redact_value(k, serialize(v))
            
    is_framework = col_name in FRAMEWORK_COLS
    
    fields_list = []
    for k, v in field_stats.items():
        types_str = "/".join(sorted(list(v['types'])))
        sample_total = len(sample_docs)
        is_optional = (v['present_count'] < sample_total) or (v['null_count'] > 0)
        fields_list.append({
            'field': k,
            'types': types_str,
            'optional': is_optional,
            'null_count_in_sample': v['null_count'],
            'missing_count_in_sample': sample_total - v['present_count']
        })
        
    inventory[col_name] = {
        'collection_name': col_name,
        'document_count': count,
        'is_framework': is_framework,
        'indexes': indexes,
        'fields': fields_list,
        'sample_document': redacted_sample
    }

out_path = 'ashdent-back/scratch/step1_collection_inventory.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(inventory, f, indent=2)

print(f"Collection inventory completed for {len(inventory)} collections! Saved to {out_path}")

