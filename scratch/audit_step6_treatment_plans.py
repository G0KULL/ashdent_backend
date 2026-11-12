import sys, os
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections
from collections import Counter
from bson import ObjectId

db = connections['default'].database
items_col = db['patients_treatmentplanitem']
plans_col = db['patients_treatmentplan']

total_items = items_col.count_documents({})
total_plans = plans_col.count_documents({})

print(f"Total treatment plans: {total_plans}")
print(f"Total treatment plan items: {total_items}")

# 1. Check distinct plan IDs in items
plan_ids_in_items = items_col.distinct('plan_id')
print(f"Distinct plan_id referenced in items: {len(plan_ids_in_items)}")

# 2. Check if all plan_ids in items exist in patients_treatmentplan
existing_plan_ids = set(plans_col.distinct('_id'))
orphaned_items = items_col.count_documents({'plan_id': {'$nin': list(existing_plan_ids)}})
print(f"Items with non-existent plan_id (orphaned): {orphaned_items}")

# 3. Top plans with most items
pipeline_top = [
    {'$group': {'_id': '$plan_id', 'count': {'$sum': 1}}},
    {'$sort': {'count': -1}},
    {'$limit': 15}
]
top_plans = list(items_col.aggregate(pipeline_top))
print("\nTop 15 Plans by item count:")
for tp in top_plans:
    plan_doc = plans_col.find_one({'_id': tp['_id']})
    patient_id = plan_doc.get('patient_id') if plan_doc else 'N/A'
    plan_title = plan_doc.get('title') if plan_doc else 'N/A'
    created_at = plan_doc.get('created_at') if plan_doc else 'N/A'
    print(f"  Plan ID: {tp['_id']} | Items: {tp['count']} | Patient: {patient_id} | Title: {plan_title} | Created: {created_at}")

# 4. Check duplicate items within the top plan
top_plan_id = top_plans[0]['_id']
print(f"\nAnalyzing top plan {top_plan_id} (count: {top_plans[0]['count']}):")
dup_pipeline = [
    {'$match': {'plan_id': top_plan_id}},
    {'$group': {
        '_id': {
            'tooth_number': '$tooth_number',
            'procedure_name': '$procedure_name',
            'surface': '$surface',
            'estimated_cost': '$estimated_cost',
            'status': '$status'
        },
        'count': {'$sum': 1},
        'min_created': {'$min': '$created_at'},
        'max_created': {'$max': '$created_at'}
    }},
    {'$sort': {'count': -1}},
    {'$limit': 10}
]
dups = list(items_col.aggregate(dup_pipeline))
for d in dups:
    print(f"  Tooth: {d['_id']['tooth_number']} | Proc: {d['_id']['procedure_name']} | Count: {d['count']} | MinDate: {d['min_created']} | MaxDate: {d['max_created']}")

# 5. Look at how items are created in code: check views.py or emr_views.py
print("\nCheck timestamp distribution of items:")
time_pipeline = [
    {'$group': {
        '_id': {
            'year': {'$year': '$created_at'},
            'month': {'$month': '$created_at'},
            'day': {'$dayOfMonth': '$created_at'},
            'hour': {'$hour': '$created_at'}
        },
        'count': {'$sum': 1}
    }},
    {'$sort': {'count': -1}},
    {'$limit': 10}
]
times = list(items_col.aggregate(time_pipeline))
for t in times:
    print(f"  Date: {t['_id']['year']}-{t['_id']['month']}-{t['_id']['day']} Hour: {t['_id']['hour']} -> {t['count']} items")


