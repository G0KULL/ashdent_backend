import os, sys, subprocess, hashlib, datetime, pymongo

def find_mongo_tool(name):
    # Check PATH
    import shutil
    p = shutil.which(name)
    if p:
        return p
    # Check default Windows path
    default_path = os.path.join(r"C:\Program Files\MongoDB\Tools\100\bin", f"{name}.exe")
    if os.path.isfile(default_path):
        return default_path
    return None

mongodump_bin = find_mongo_tool('mongodump')
mongorestore_bin = find_mongo_tool('mongorestore')

print(f"mongodump binary  : {mongodump_bin}")
print(f"mongorestore binary: {mongorestore_bin}")

if not mongodump_bin or not mongorestore_bin:
    print("[ERROR] MongoDB Database Tools (mongodump/mongorestore) not found! Aborting.")
    sys.exit(1)

os.makedirs('ashdent-back/backups', exist_ok=True)
timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup_archive = os.path.abspath(f"ashdent-back/backups/dental_clinic_db_backup_{timestamp}.gz")
restore_test_db = "dental_clinic_db_restore_test"

print("\n" + "=" * 80)
print("STAGE 1: EXECUTING PHYSICAL MONGODUMP BACKUP")
print(f"Source Database: dental_clinic_db")
print(f"Archive Output : {backup_archive}")
print("=" * 80)

cmd_dump = [
    mongodump_bin,
    "--db=dental_clinic_db",
    "--gzip",
    f"--archive={backup_archive}"
]

res_dump = subprocess.run(cmd_dump, capture_output=True, text=True)
print(f"Exit code: {res_dump.returncode}")
if res_dump.returncode != 0:
    print(f"[FAILED] mongodump failed: {res_dump.stderr}")
    sys.exit(1)

if not os.path.isfile(backup_archive) or os.path.getsize(backup_archive) == 0:
    print(f"[FAILED] Backup archive missing or empty: {backup_archive}")
    sys.exit(1)

file_size = os.path.getsize(backup_archive)

# Compute SHA-256
sha256 = hashlib.sha256()
with open(backup_archive, 'rb') as f:
    while chunk := f.read(65536):
        sha256.update(chunk)
archive_hash = sha256.hexdigest()

print(f"[PASS] Physical backup archive created successfully!")
print(f"  Size   : {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
print(f"  SHA-256: {archive_hash}")

print("\n" + "=" * 80)
print(f"STAGE 2: RESTORE VALIDATION ON DISPOSABLE DATABASE [{restore_test_db}]")
print("=" * 80)

client = pymongo.MongoClient('mongodb://localhost:27017/')
if restore_test_db in client.list_database_names():
    client.drop_database(restore_test_db)

cmd_restore = [
    mongorestore_bin,
    "--gzip",
    f"--archive={backup_archive}",
    f"--nsFrom=dental_clinic_db.*",
    f"--nsTo={restore_test_db}.*"
]

res_restore = subprocess.run(cmd_restore, capture_output=True, text=True)
print(f"Exit code: {res_restore.returncode}")
if res_restore.returncode != 0:
    print(f"[FAILED] mongorestore failed: {res_restore.stderr}")
    sys.exit(1)

src_db = client['dental_clinic_db']
test_db = client[restore_test_db]

src_colls = sorted(src_db.list_collection_names())
test_colls = sorted(test_db.list_collection_names())

print(f"Source DB collections : {len(src_colls)}")
print(f"Restored DB collections: {len(test_colls)}")

mismatches = []
for c in src_colls:
    c_src = src_db[c].count_documents({})
    c_tgt = test_db[c].count_documents({})
    if c_src != c_tgt:
        mismatches.append((c, c_src, c_tgt))

print(f"Collections checked: {len(src_colls)}, Count mismatches: {len(mismatches)}")
if mismatches:
    print(f"[FAIL] Count mismatches: {mismatches}")
    sys.exit(1)
else:
    print("[PASS] 100% Document count and collection parity verified between dental_clinic_db and restore test DB!")

# Clean up disposable test database
client.drop_database(restore_test_db)
print(f"[PASS] Disposable restore test DB [{restore_test_db}] cleanly dropped after verification.")

print("\n" + "=" * 80)
print("BLOCKER 3: PHYSICAL BACKUP & RESTORE VERIFICATION COMPLETE")
print("=" * 80)

