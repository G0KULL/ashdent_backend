import sys, os, json
from pymongo import MongoClient
from bson import ObjectId

client = MongoClient('mongodb://localhost:27017/')
db = client['dental_clinic_db_migrated']

arthur_id = ObjectId('6aef1520a932d0e8baaf79d5')

print("=" * 80)
print(f"SAFELY PURGING SECOND SYNTHETIC ARTHUR DENTIST ({arthur_id})")
print("=" * 80)

# Verify existence
p = db['patients_patient'].find_one({'_id': arthur_id})
if not p:
    print("Patient not found or already purged!")
    sys.exit(0)

print(f"Target Patient: {p.get('name')} ({p.get('patient_id')})")

# Find linked plans, invoices, visits, appts
plan_ids = [d['_id'] for d in db['patients_treatmentplan'].find({'patient_id': arthur_id})]
bill_ids = [d['_id'] for d in db['patients_billing'].find({'patient_id': arthur_id})]
visit_ids = [d['_id'] for d in db['patients_visit'].find({'patient_id': arthur_id})]
appt_ids = [d['_id'] for d in db['patients_appointment'].find({'patient_id': arthur_id})]

# Delete linked child records
res_items = db['patients_treatmentplanitem'].delete_many({'plan_id': {'$in': plan_ids}})
res_plans = db['patients_treatmentplan'].delete_many({'_id': {'$in': plan_ids}})

res_pmts = db['patients_billpayment'].delete_many({'$or': [{'patient_id': arthur_id}, {'billing_id': {'$in': bill_ids}}]})
res_bitems = db['patients_billingitem'].delete_many({'billing_id': {'$in': bill_ids}})
res_bills = db['patients_billing'].delete_many({'_id': {'$in': bill_ids}})

res_notes = db['patients_clinicalnotes'].delete_many({'visit_id': {'$in': visit_ids}})
res_trecs = db['patients_treatmentrecord'].delete_many({'visit_id': {'$in': visit_ids}})
res_visits = db['patients_visit'].delete_many({'_id': {'$in': visit_ids}})

res_appts = db['patients_appointment'].delete_many({'_id': {'$in': appt_ids}})
res_tc = db['patients_toothconditionrecord'].delete_many({'patient_id': arthur_id})
res_rxitems = db['patients_prescriptionitem'].delete_many({'prescription__patient_id': arthur_id})
res_rx = db['patients_prescription'].delete_many({'patient_id': arthur_id})
res_estitems = db['patients_estimateitem'].delete_many({'estimate__patient_id': arthur_id})
res_est = db['patients_estimate'].delete_many({'patient_id': arthur_id})
res_logs = db['patients_communicationlog'].delete_many({'patient_id': arthur_id})
res_emrlogs = db['patients_emrchangelog'].delete_many({'patient_id': arthur_id})
res_txs = db['patients_transaction'].delete_many({'billing_id': {'$in': bill_ids}})

# Delete patient
res_pat = db['patients_patient'].delete_one({'_id': arthur_id})

print("\n--- Purge Results ---")
print(f"Patients deleted: {res_pat.deleted_count}")
print(f"Appointments deleted: {res_appts.deleted_count}")
print(f"Visits deleted: {res_visits.deleted_count}")
print(f"Clinical Notes deleted: {res_notes.deleted_count}")
print(f"Tooth Conditions deleted: {res_tc.deleted_count}")
print(f"Treatment Plans deleted: {res_plans.deleted_count}")
print(f"Treatment Plan Items deleted: {res_items.deleted_count}")
print(f"Treatment Records deleted: {res_trecs.deleted_count}")
print(f"Invoices deleted: {res_bills.deleted_count}")
print(f"Billing Items deleted: {res_bitems.deleted_count}")
print(f"Payments deleted: {res_pmts.deleted_count}")
print(f"Prescriptions deleted: {res_rx.deleted_count}")
print(f"Estimates deleted: {res_est.deleted_count}")

print("\n--- Final Verified Baseline Counts in dental_clinic_db_migrated ---")
print(f"Active Treatment Plan Items: {db['patients_treatmentplanitem'].count_documents({})}")
print(f"Bill Payments              : {db['patients_billpayment'].count_documents({})}")
print(f"Billing Invoices           : {db['patients_billing'].count_documents({})}")
print(f"Patients                   : {db['patients_patient'].count_documents({})}")
print(f"Appointments               : {db['patients_appointment'].count_documents({})}")
print(f"Visits                     : {db['patients_visit'].count_documents({})}")
print(f"Clinical Notes             : {db['patients_clinicalnotes'].count_documents({})}")
print(f"Treatment Plans            : {db['patients_treatmentplan'].count_documents({})}")
print(f"Prescriptions              : {db['patients_prescription'].count_documents({})}")
print(f"Estimates                  : {db['patients_estimate'].count_documents({})}")

