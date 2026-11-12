import sys, os, json
sys.path.insert(0, os.path.abspath('ashdent-back'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django; django.setup()
from django.db import connections
from bson import ObjectId

db = connections['default'].database

print("Auditing Company and Branch References across all collections...")

valid_companies = {str(c['_id']): c for c in db['patients_company'].find()}
valid_branches = {str(b['_id']): b for b in db['patients_branch'].find()}

cols = sorted(db.list_collection_names())

audit_results = {}

for col_name in cols:
    col = db[col_name]
    total_docs = col.count_documents({})
    if total_docs == 0:
        continue
        
    sample = col.find_one()
    has_company_field = any('company' in k for k in sample.keys())
    has_branch_field = any('branch' in k for k in sample.keys())
    
    if not has_company_field and not has_branch_field:
        continue
        
    company_field_name = next((k for k in ['company_id', 'company'] if k in sample.keys()), None)
    branch_field_name = next((k for k in ['branch_id', 'primary_branch_id', 'registration_branch_id', 'branch'] if k in sample.keys()), None)
    
    # Audit company
    comp_populated = 0
    comp_null_or_missing = 0
    comp_invalid = 0
    
    # Audit branch
    branch_populated = 0
    branch_null_or_missing = 0
    branch_invalid = 0
    branch_company_mismatches = 0
    
    for doc in col.find():
        # Company check
        c_val = doc.get(company_field_name) if company_field_name else None
        if c_val is not None and str(c_val) not in ['', 'None']:
            comp_populated += 1
            if str(c_val) not in valid_companies:
                comp_invalid += 1
        else:
            comp_null_or_missing += 1
            
        # Branch check
        b_val = doc.get(branch_field_name) if branch_field_name else None
        if b_val is not None and str(b_val) not in ['', 'None']:
            branch_populated += 1
            if str(b_val) not in valid_branches:
                branch_invalid += 1
            else:
                # Check cross-company mismatch
                b_obj = valid_branches[str(b_val)]
                b_comp = str(b_obj.get('company_id'))
                if c_val and str(c_val) in valid_companies:
                    if b_comp != str(c_val):
                        branch_company_mismatches += 1
        else:
            branch_null_or_missing += 1
            
    audit_results[col_name] = {
        'total_docs': total_docs,
        'company_field': company_field_name,
        'company_populated': comp_populated,
        'company_null_or_missing': comp_null_or_missing,
        'company_invalid_references': comp_invalid,
        'branch_field': branch_field_name,
        'branch_populated': branch_populated,
        'branch_null_or_missing': branch_null_or_missing,
        'branch_invalid_references': branch_invalid,
        'branch_company_mismatches': branch_company_mismatches
    }

out_path = 'ashdent-back/scratch/step8_company_branch_report.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(audit_results, f, indent=2)

print("Step 8 Audit complete! Saved to", out_path)
for k, v in audit_results.items():
    print(f"{k} (total: {v['total_docs']}) -> Comp: {v['company_populated']}/{v['total_docs']} (inv: {v['company_invalid_references']}), Branch: {v['branch_populated']}/{v['total_docs']} (inv: {v['branch_invalid_references']}, mismatch: {v['branch_company_mismatches']})")

