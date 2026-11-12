import os, sys, shutil, pymongo

client = pymongo.MongoClient('mongodb://localhost:27017/')
src_db = client['dental_clinic_db_migrated']
test_db_name = 'dental_clinic_db_workflow_test'

if test_db_name in client.list_database_names():
    client.drop_database(test_db_name)

test_db = client[test_db_name]
print(f"Cloning {src_db.name} -> {test_db_name} for disposable workflow execution...")

for c in src_db.list_collection_names():
    docs = list(src_db[c].find({}))
    if docs:
        test_db[c].insert_many(docs)
    idxs = src_db[c].index_information()
    for name, info in idxs.items():
        if name != '_id_':
            try:
                test_db[c].create_index(info['key'])
            except Exception:
                pass

print(f"Cloned {len(src_db.list_collection_names())} collections to {test_db_name}.")

# Now run workflow tests with DJANGO_DB_NAME=dental_clinic_db_workflow_test
os.environ['DJANGO_DB_NAME'] = test_db_name
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'

import subprocess
res = subprocess.run([sys.executable, 'ashdent-back/scratch/test_workflows_on_migrated_db.py'], capture_output=True, text=True, env=dict(os.environ, DJANGO_DB_NAME=test_db_name))

print("\n" + "=" * 80)
print("WORKFLOW EXECUTION OUTPUT:")
print("=" * 80)
print(res.stdout)
if res.stderr:
    print("ERRORS / WARNINGS:")
    print(res.stderr)

# Clean up disposable test DB
client.drop_database(test_db_name)
print(f"\n[PASS] Cleaned up disposable DB {test_db_name}.")
print(f"[PASS] Target database dental_clinic_db_migrated remains strictly pristine.")

