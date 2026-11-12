import pymongo
from bson import ObjectId

mig = pymongo.MongoClient('mongodb://localhost:27017/')['dental_clinic_db_migrated']
aid = ObjectId('6aeef65ef054fbd01ad70dd3')

print("--- Inspecting Arthur Dentist and related test entities ---")
arthur = mig['patients_patient'].find_one({'_id': aid})
print("Patient:", arthur)

for c in sorted(mig.list_collection_names()):
    docs = list(mig[c].find({'$or': [{'patient_id': aid}, {'patient': aid}, {'patient_id': str(aid)}]}))
    if docs:
        print(f"\nCollection {c} ({len(docs)} docs):")
        for d in docs:
            print(f"  _id: {d.get('_id')}, type/title: {d.get('title') or d.get('procedure_name') or d.get('bill_type') or d.get('receipt_number') or d.get('status')}")

# Also check treatment plan items for the plan
if arthur:
    plans = list(mig['patients_treatmentplan'].find({'patient_id': aid}))
    for p in plans:
        pid = p['_id']
        items = list(mig['patients_treatmentplanitem'].find({'plan_id': pid}))
        print(f"\nTreatmentPlanItems for plan {pid} ({len(items)} items):")
        for it in items:
            print(f"  _id: {it.get('_id')}, tooth: {it.get('tooth_number')}, procedure: {it.get('procedure_name')}")

# Also check slot locks
locks = list(mig['patients_slot_lock'].find({}))
print(f"\nSlot locks in DB ({len(locks)} total):")
for sl in locks:
    print(f"  _id: {sl.get('_id')}, slot: {sl.get('slot_time')}, doc: {sl.get('doctor_id')}")

# Also check prescription items
rx_list = list(mig['patients_prescription'].find({'patient_id': aid}))
for rx in rx_list:
    rx_items = list(mig['patients_prescriptionitem'].find({'prescription_id': rx['_id']}))
    print(f"\nPrescriptionItems for rx {rx['_id']} ({len(rx_items)} items):")
    for rxi in rx_items:
        print(f"  _id: {rxi.get('_id')}, med: {rxi.get('medicine_name')}")

