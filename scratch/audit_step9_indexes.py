import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections

db = connections['default'].database

print("Auditing Indexes and Data Integrity...")

cols = sorted(db.list_collection_names())
index_report = {}

# Analyze indexes per collection
for c in cols:
    col = db[c]
    idxs = []
    for idx in col.list_indexes():
        idxs.append({
            'name': idx.get('name'),
            'keys': list(idx.get('key', {}).items()),
            'unique': idx.get('unique', False)
        })
    index_report[c] = idxs

# Identify missing critical indexes on high-volume or tenant-scoped collections
critical_collections = [
    'patients_treatmentplanitem',
    'patients_treatmentplan',
    'patients_patient',
    'patients_appointment',
    'patients_billing',
    'patients_billingitem',
    'patients_billpayment',
    'patients_estimate',
    'patients_estimateitem',
    'patients_visit',
    'patients_staff',
    'patients_transaction'
]

index_recommendations = []

for c in critical_collections:
    col = db[c]
    existing_keys = [tuple(k[0] for k in idx['keys']) for idx in index_report[c]]
    
    # Check for plan_id index on patients_treatmentplanitem (56k documents!)
    if c == 'patients_treatmentplanitem':
        if ('plan_id',) not in existing_keys:
            index_recommendations.append({
                'collection': c,
                'recommended_index': [('plan_id', 1)],
                'reason': 'Critical: Collection holds 56,644 documents queried frequently by plan_id during EMR and Estimate loading.'
            })
            
    # Check for company & branch indexes
    sample = col.find_one()
    if sample:
        if 'company_id' in sample and ('company_id',) not in existing_keys and ('company_id', 'created_at') not in existing_keys:
            index_recommendations.append({
                'collection': c,
                'recommended_index': [('company_id', 1)],
                'reason': f'Multi-tenant scoping: Queries filter by company on {c}.'
            })
        if 'patient_id' in sample and ('patient_id',) not in existing_keys:
            index_recommendations.append({
                'collection': c,
                'recommended_index': [('patient_id', 1)],
                'reason': f'Patient EMR lookup: Queries filter by patient on {c}.'
            })

# Check orphaned items across child collections
orphans = {}

# 1. treatmentplanitem -> treatmentplan
valid_plan_ids = set(db['patients_treatmentplan'].distinct('_id'))
tpi_orphans = db['patients_treatmentplanitem'].count_documents({'plan_id': {'$nin': list(valid_plan_ids)}})
orphans['treatmentplanitem_to_plan'] = tpi_orphans

# 2. estimateitem -> estimate
valid_est_ids = set(db['patients_estimate'].distinct('_id'))
ei_orphans = db['patients_estimateitem'].count_documents({'estimate_id': {'$nin': list(valid_est_ids)}})
orphans['estimateitem_to_estimate'] = ei_orphans

# 3. billingitem -> billing
valid_bill_ids = set(db['patients_billing'].distinct('_id'))
bi_orphans = db['patients_billingitem'].count_documents({'billing_id': {'$nin': list(valid_bill_ids)}})
orphans['billingitem_to_billing'] = bi_orphans

# 4. billpayment -> billing
bp_orphans = db['patients_billpayment'].count_documents({'billing_id': {'$nin': list(valid_bill_ids)}})
orphans['billpayment_to_billing'] = bp_orphans

result = {
    'total_collections_audited': len(cols),
    'indexes_by_collection': index_report,
    'index_recommendations': index_recommendations,
    'orphaned_references': orphans
}

out_path = 'ashdent-back/scratch/step9_index_integrity_report.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2)

print("Index and integrity audit completed! Saved to", out_path)
print("Orphaned references summary:", orphans)
print(f"Total recommended indexes: {len(index_recommendations)}")

