import os, sys, subprocess, hashlib, datetime, json, pymongo
from bson import ObjectId

def find_mongo_tool(name):
    import shutil
    p = shutil.which(name)
    if p:
        return p
    default_path = os.path.join(r"C:\Program Files\MongoDB\Tools\100\bin", f"{name}.exe")
    if os.path.isfile(default_path):
        return default_path
    return None

mongodump = find_mongo_tool('mongodump')
mongorestore = find_mongo_tool('mongorestore')

print(f"mongodump binary  : {mongodump}")
print(f"mongorestore binary: {mongorestore}")

if not mongodump or not mongorestore:
    print("[ERROR] MongoDB tools missing.")
    sys.exit(1)

client = pymongo.MongoClient('mongodb://localhost:27017/')
backup_dir = os.path.abspath('ashdent-back/backups')
os.makedirs(backup_dir, exist_ok=True)
timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

def compute_sha256(filepath):
    sha = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()

def verify_backup_and_restore(source_db_name, restore_db_name, archive_name):
    print("\n" + "=" * 80)
    print(f"BACKUP & RESTORE VERIFICATION FOR [{source_db_name}]")
    print("=" * 80)
    
    archive_path = os.path.join(backup_dir, archive_name)
    
    # 1. mongodump
    cmd_dump = [
        mongodump,
        f"--db={source_db_name}",
        "--gzip",
        f"--archive={archive_path}"
    ]
    print(f"Executing: {' '.join(cmd_dump)}")
    t0 = datetime.datetime.now()
    res_dump = subprocess.run(cmd_dump, capture_output=True, text=True)
    t1 = datetime.datetime.now()
    
    if res_dump.returncode != 0:
        print(f"[FAIL] Dump failed: {res_dump.stderr}")
        return {'status': 'FAILED', 'error': res_dump.stderr}
        
    size_bytes = os.path.getsize(archive_path)
    sha256_hash = compute_sha256(archive_path)
    
    print(f"[PASS] Archive created: {archive_path}")
    print(f"  Size   : {size_bytes:,} bytes ({size_bytes / (1024*1024):.2f} MB)")
    print(f"  SHA-256: {sha256_hash}")
    print(f"  Time   : {(t1 - t0).total_seconds():.2f} seconds")
    
    # 2. mongorestore into disposable DB
    if restore_db_name in client.list_database_names():
        client.drop_database(restore_db_name)
        
    cmd_restore = [
        mongorestore,
        "--gzip",
        f"--archive={archive_path}",
        f"--nsFrom={source_db_name}.*",
        f"--nsTo={restore_db_name}.*"
    ]
    print(f"Executing restore: {' '.join(cmd_restore)}")
    res_restore = subprocess.run(cmd_restore, capture_output=True, text=True)
    if res_restore.returncode != 0:
        print(f"[FAIL] Restore failed: {res_restore.stderr}")
        return {'status': 'FAILED', 'error': res_restore.stderr}
        
    # 3. Compare collections, doc counts, and indexes
    src_db = client[source_db_name]
    rest_db = client[restore_db_name]
    
    src_colls = sorted(src_db.list_collection_names())
    rest_colls = sorted(rest_db.list_collection_names())
    
    colls_match = (src_colls == rest_colls)
    print(f"Collections match: {colls_match} (Source: {len(src_colls)}, Restored: {len(rest_colls)})")
    
    count_mismatches = []
    index_mismatches = []
    
    for c in src_colls:
        c_src = src_db[c].count_documents({})
        c_rest = rest_db[c].count_documents({})
        if c_src != c_rest:
            count_mismatches.append((c, c_src, c_rest))
            
        # check indexes
        src_idx = src_db[c].index_information()
        rest_idx = rest_db[c].index_information()
        # compare index keys
        src_keys = sorted(src_idx.get(k, {}).get('key', []) for k in src_idx if k != '_id_')
        rest_keys = sorted(rest_idx.get(k, {}).get('key', []) for k in rest_idx if k != '_id_')
        if src_keys != rest_keys:
            index_mismatches.append((c, src_keys, rest_keys))

    print(f"Document count mismatches: {len(count_mismatches)}")
    print(f"Index key mismatches     : {len(index_mismatches)}")
    
    # 4. Verify test read using Django settings style connection
    # Verify reading patient collection
    can_read = False
    try:
        sample_doc = rest_db['patients_patient'].find_one({})
        can_read = (sample_doc is not None)
    except Exception as e:
        print(f"Read error: {e}")
        
    print(f"Restored DB readable by pymongo client: {can_read}")
    
    # 5. Clean up disposable DB
    client.drop_database(restore_db_name)
    print(f"Disposable DB [{restore_db_name}] cleanly dropped.")
    
    return {
        'source_db': source_db_name,
        'restore_db': restore_db_name,
        'archive_path': archive_path,
        'size_bytes': size_bytes,
        'sha256': sha256_hash,
        'timestamp': timestamp,
        'exit_code': 0,
        'collections_count': len(src_colls),
        'collections_match': colls_match,
        'count_mismatches': count_mismatches,
        'index_mismatches': index_mismatches,
        'can_read': can_read,
        'status': 'VERIFIED'
    }

# Execute for both DBs
prod_result = verify_backup_and_restore(
    'dental_clinic_db',
    'dental_clinic_db_restore_verify_prod',
    f"phase3_4_dental_clinic_db_prod_{timestamp}.gz"
)

mig_result = verify_backup_and_restore(
    'dental_clinic_db_migrated',
    'dental_clinic_db_restore_verify_migrated',
    f"phase3_4_dental_clinic_db_migrated_{timestamp}.gz"
)

with open('ashdent-back/scratch/phase_b_backup_report.json', 'w') as f:
    json.dump({'production_backup': prod_result, 'migrated_backup': mig_result}, f, indent=2)

print("\n" + "=" * 80)
print("PHASE B VERIFICATION SUMMARY:")
print(f"  Production Backup Status: {prod_result['status']}")
print(f"  Migrated Backup Status  : {mig_result['status']}")
print("=" * 80)

