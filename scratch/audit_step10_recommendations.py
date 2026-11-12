import json

with open('ashdent-back/scratch/step1_collection_inventory.json', 'r') as f:
    step1 = json.load(f)

with open('ashdent-back/scratch/step2_model_mappings.json', 'r') as f:
    step2 = json.load(f)

recommendations = {}

for col_name, info in step1.items():
    count = info['document_count']
    is_fw = info['is_framework']
    
    if is_fw or col_name in ['django_migrations', 'django_content_type', 'auth_permission', 'auth_user']:
        rec = 'FRAMEWORK REQUIRED'
        rationale = 'Essential Django framework collection for auth, content types, and migrations.'
    elif col_name == 'patients_treatmentplanitem':
        rec = 'RETAIN AND FIX'
        rationale = 'Core EMR collection holding 56,644 items. Suffers from runaway duplicates (27k+ duplicate items in a single plan from Nov 3 runaway loop). Requires deduplication script and unique index.'
    elif col_name == 'patients_payment':
        rec = 'POTENTIAL MERGE'
        rationale = 'Legacy payment record created during walk-in visit creation (9 docs). Overlaps with patients_billpayment (27 docs) and patients_transaction (27 docs).'
    elif col_name == 'patients_patient_groups':
        rec = 'POTENTIAL RETIREMENT'
        rationale = 'Empty unmodeled collection (0 docs). AshDent uses patients_patientgroup (1 doc) with an embedded members list rather than a separate junction table.'
    elif col_name == 'patients_clinicsubscription':
        rec = 'POTENTIAL RETIREMENT'
        rationale = 'Single record (1 doc) from early single-tenant setup. Unused in multi-tenant AshDent architecture.'
    elif col_name == 'numbering_sequences':
        rec = 'RETAIN'
        rationale = 'Raw PyMongo atomic counter collection used by AutoNumbering.get_next_sequence for branch/company invoice and estimate sequencing.'
    elif col_name == 'patients_slot_lock':
        rec = 'RETAIN'
        rationale = 'Raw PyMongo atomic lock collection with TTL index used by acquire_slot_lock and release_slot_lock for appointment slot concurrency control.'
    elif col_name in ['patients_prebooking', 'patients_doctordateoverride', 'patients_patientlaborder', 'patients_expense', 'patients_patientimage', 'patients_staffbenefit', 'patients_staffinsurance']:
        rec = 'RETAIN'
        rationale = f'Active domain model ({col_name}) currently having 0 records. Collection and APIs are active and functional when users utilize this module.'
    elif col_name in ['patients_billing', 'patients_visit', 'patients_prescription']:
        rec = 'RETAIN AND FIX'
        rationale = f'Core collection ({col_name}). Contains a few historical documents missing company_id/branch_id from before multi-tenant scoping was introduced.'
    else:
        rec = 'RETAIN'
        rationale = f'Actively used application collection ({col_name}) with {count} documents, correctly structured and referenced.'

    recommendations[col_name] = {
        'collection_name': col_name,
        'document_count': count,
        'recommendation': rec,
        'rationale': rationale
    }

out_path = 'ashdent-back/scratch/step10_recommendations.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(recommendations, f, indent=2)

print(f"Assigned recommendations for all {len(recommendations)} collections!")
summary_counts = {}
for r in recommendations.values():
    rc = r['recommendation']
    summary_counts[rc] = summary_counts.get(rc, 0) + 1
print("Summary:", summary_counts)

