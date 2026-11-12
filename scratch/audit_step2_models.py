import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.apps import apps
from django.db import connections

db = connections['default'].database
existing_mongo_cols = set(db.list_collection_names())

models = apps.get_models()
model_mappings = []
model_tables = set()

for m in models:
    table = m._meta.db_table
    model_tables.add(table)
    app_label = m._meta.app_label
    model_name = m.__name__
    
    # Analyze fields
    field_names = [f.name for f in m._meta.get_fields()]
    
    # Primary key format
    pk_field = m._meta.pk
    pk_info = {
        'name': pk_field.name if pk_field else 'id',
        'type': type(pk_field).__name__ if pk_field else 'Unknown'
    }
    
    # Relationships
    rel_company = 'company' in field_names or 'company_id' in field_names
    rel_branch = any(k in field_names for k in ['branch', 'branch_id', 'primary_branch', 'registration_branch'])
    rel_patient = any(k in field_names for k in ['patient', 'patient_id'])
    rel_appointment = any(k in field_names for k in ['appointment', 'appointment_id'])
    rel_visit = any(k in field_names for k in ['visit', 'visit_id'])
    rel_doctor = any(k in field_names for k in ['doctor', 'doctor_id', 'doctor_profile'])
    
    timestamps = [f for f in field_names if any(t in f.lower() for t in ['created', 'updated', 'timestamp', 'date_joined'])]
    
    # Related models
    related_models = []
    for f in m._meta.get_fields():
        if f.is_relation and getattr(f, 'related_model', None):
            rm = f.related_model
            related_models.append(f"{f.name} -> {rm.__name__} ({rm._meta.db_table})")
            
    doc_count = db[table].count_documents({}) if table in existing_mongo_cols else 0
    
    model_mappings.append({
        'app_label': app_label,
        'model_name': model_name,
        'collection_name': table,
        'exists_in_mongo': table in existing_mongo_cols,
        'mongo_doc_count': doc_count,
        'pk_info': pk_info,
        'relationships': {
            'company': rel_company,
            'branch': rel_branch,
            'patient': rel_patient,
            'appointment': rel_appointment,
            'visit': rel_visit,
            'doctor': rel_doctor
        },
        'timestamps': timestamps,
        'related_models': related_models
    })

# Identify discrepancies
unmodeled_cols = sorted(list(existing_mongo_cols - model_tables))
models_without_cols = [m['model_name'] for m in model_mappings if not m['exists_in_mongo']]

result = {
    'total_models': len(model_mappings),
    'models': model_mappings,
    'unmodeled_collections': unmodeled_cols,
    'models_without_collections': models_without_cols
}

out_path = 'ashdent-back/scratch/step2_model_mappings.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2)

print(f"Model mapping completed! Total models: {len(model_mappings)}")
print(f"Unmodeled collections ({len(unmodeled_cols)}): {unmodeled_cols}")
print(f"Models without collections ({len(models_without_cols)}): {models_without_cols}")

