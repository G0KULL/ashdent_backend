import sys, os, time, hashlib
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections

source_client = connections['default'].database.client
source_db = source_client['dental_clinic_db']
target_db = source_client['dental_clinic_db_migrated']

print("=" * 60)
print("STAGE 1: CLONING PRODUCTION DATABASE TO TEST DATABASE")
print("Source: dental_clinic_db")
print("Target: dental_clinic_db_migrated")
print("=" * 60)

start_time = time.time()

# 1. Clean up target test database if exists
if 'dental_clinic_db_migrated' in source_client.list_database_names():
    print("Dropping existing dental_clinic_db_migrated to ensure clean baseline...")
    source_client.drop_database('dental_clinic_db_migrated')

# 2. Iterate through all collections
source_cols = sorted(source_db.list_collection_names())
print(f"\nCloning {len(source_cols)} collections...")

total_source_docs = 0
total_target_docs = 0

for i, col_name in enumerate(source_cols, 1):
    src_col = source_db[col_name]
    tgt_col = target_db[col_name]
    
    doc_count = src_col.count_documents({})
    total_source_docs += doc_count
    
    # Batch copy documents in chunks of 5000
    if doc_count > 0:
        cursor = src_col.find({}, batch_size=5000)
        batch = []
        for doc in cursor:
            batch.append(doc)
            if len(batch) >= 5000:
                tgt_col.insert_many(batch, ordered=False)
                batch = []
        if batch:
            tgt_col.insert_many(batch, ordered=False)
            
    # Copy indexes (excluding _id_)
    src_indexes = list(src_col.list_indexes())
    for idx in src_indexes:
        if idx.get('name') != '_id_':
            keys = list(idx['key'].items())
            opts = {}
            if idx.get('unique'):
                opts['unique'] = True
            if 'expireAfterSeconds' in idx:
                opts['expireAfterSeconds'] = idx['expireAfterSeconds']
            if 'name' in idx:
                opts['name'] = idx['name']
            try:
                tgt_col.create_index(keys, **opts)
            except Exception as e:
                print(f"  Note: index {idx.get('name')} on {col_name}: {e}")
                
    tgt_count = tgt_col.count_documents({})
    total_target_docs += tgt_count
    assert doc_count == tgt_count, f"Count mismatch in {col_name}: src={doc_count}, tgt={tgt_count}"
    
    if i % 10 == 0 or i == len(source_cols):
        print(f"  [{i}/{len(source_cols)}] Cloned {col_name}: {tgt_count:,} docs")

elapsed = time.time() - start_time
print("\n" + "=" * 60)
print("STAGE 1 COMPLETED SUCCESSFULLY!")
print(f"Total Collections Cloned: {len(source_cols)}")
print(f"Total Source Docs: {total_source_docs:,}")
print(f"Total Cloned Docs: {total_target_docs:,}")
print(f"Time Taken: {elapsed:.2f} seconds")

# Compute Baseline Checksum on Patient IDs and Invoices
patient_ids = sorted([str(p['_id']) for p in target_db['patients_patient'].find({}, {'_id': 1})])
patient_hash = hashlib.sha256("".join(patient_ids).encode()).hexdigest()
invoice_nums = sorted([str(b.get('invoice_number', '')) for b in target_db['patients_billing'].find({}, {'invoice_number': 1})])
invoice_hash = hashlib.sha256("".join(invoice_nums).encode()).hexdigest()

print(f"Patient IDs Hash: {patient_hash}")
print(f"Invoice Numbers Hash: {invoice_hash}")
print("=" * 60)

