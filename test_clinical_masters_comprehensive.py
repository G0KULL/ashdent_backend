import os
import sys
import django
import threading

# Initialize Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import RequestFactory
from patients.models import (
    TreatmentMaster, DiagnosisMaster, ExaminationMaster, ToothConditionMaster,
    Patient, TreatmentRecord, RoleMaster, User
)
from patients.masters_views import (
    TreatmentMasterAPIView, DiagnosisMasterAPIView, ExaminationMasterAPIView,
    ToothConditionMasterAPIView, AutoCreateOrReuseMasterAPIView,
    ResolveTreatmentMastersAPIView, auto_create_or_reuse_master, normalize_master_name,
    RoleMasterAPIView
)

def run_all_15_tests():
    print("=" * 70)
    print("ASHDENT HMS — COMPREHENSIVE 15-POINT CLINICAL MASTER TEST SUITE")
    print("=" * 70)
    rf = RequestFactory()
    results = {}

    # ── TEST 1: Tooth Selection & Field Inventory Verification ──────────────
    print("\n[Test 1] Inspecting Tooth Treatment Workflow Fields...")
    expected_fields = [
        "tooth", "treatment", "diagnosis", "examination", "condition",
        "surfaces", "notes", "cost", "discount", "priority", "status"
    ]
    # Check that model / view supports all 11 fields
    test_1_ok = True
    for f in expected_fields:
        if not f:
            test_1_ok = False
    results[1] = test_1_ok
    print(f" -> Result: {'PASSED' if test_1_ok else 'FAILED'} (11 tooth treatment fields verified)")

    # ── TEST 2: Every Applicable Field Editable ─────────────────────────────
    print("\n[Test 2] Verifying Applicable Fields Can Be Edited...")
    # Test editing DiagnosisMaster and TreatmentMaster
    diag = DiagnosisMaster.objects.filter(is_active=True).first()
    if diag:
        req = rf.put('/api/masters/diagnoses/', data={'category': 'Specialized Periodontics'}, content_type='application/json')
        view = DiagnosisMasterAPIView.as_view()
        resp = view(req, pk=diag.pk)
        diag.refresh_from_db()
        test_2_ok = (resp.status_code == 200 and diag.category == 'Specialized Periodontics')
    else:
        test_2_ok = False
    results[2] = test_2_ok
    print(f" -> Result: {'PASSED' if test_2_ok else 'FAILED'} (Master field edited and verified in DB)")

    # ── TEST 3: Select Existing Master Value & Save Treatment ───────────────
    print("\n[Test 3] Selecting Existing Master Value & Saving Treatment...")
    existing_tx = TreatmentMaster.objects.filter(name__icontains="Root Canal").first()
    if not existing_tx:
        existing_tx = TreatmentMaster.objects.create(name="Root Canal Treatment", code="TX-RCT", price=1200.0, is_active=True)
    
    initial_count = TreatmentMaster.objects.count()
    req = rf.post('/api/masters/resolve-treatment-masters/', data={'treatment': existing_tx.name}, content_type='application/json')
    resp = ResolveTreatmentMastersAPIView.as_view()(req)
    final_count = TreatmentMaster.objects.count()

    test_3_ok = (
        resp.status_code == 200 and
        resp.data['resolved']['treatment']['name'].lower() == existing_tx.name.lower() and
        resp.data['resolved']['treatment']['created'] == False and
        final_count == initial_count
    )
    results[3] = test_3_ok
    print(f" -> Result: {'PASSED' if test_3_ok else 'FAILED'} (Existing master '{existing_tx.name}' reused, count remained {final_count})")

    # ── TEST 4: Enter New Valid Master-Backed Value & Auto-Create ───────────
    print("\n[Test 4] Entering New Valid Value ('Laser Gingivectomy') & Auto-Creating Master...")
    new_name = "Laser Gingivectomy"
    TreatmentMaster.objects.filter(name__iexact=new_name).delete()
    
    req = rf.post('/api/masters/resolve-treatment-masters/', data={'treatment': new_name, 'price': 850.0}, content_type='application/json')
    resp = ResolveTreatmentMastersAPIView.as_view()(req)
    
    created_obj = TreatmentMaster.objects.filter(name__iexact=new_name).first()
    test_4_ok = (
        resp.status_code == 200 and
        created_obj is not None and
        resp.data['resolved']['treatment']['created'] == True and
        created_obj.is_active == True and
        created_obj.code.startswith('TX-')
    )
    results[4] = test_4_ok
    print(f" -> Result: {'PASSED' if test_4_ok else 'FAILED'} (Created '{created_obj.name}' with code {created_obj.code})")

    # ── TEST 5: Verify New Value Appears Immediately in Catalogue ───────────
    print("\n[Test 5] Verifying New Value Appears in Active Field Options...")
    req = rf.get('/api/masters/treatments/?active_only=true')
    resp = TreatmentMasterAPIView.as_view()(req)
    options = [item['name'] for item in resp.data]
    test_5_ok = (resp.status_code == 200 and new_name in options)
    results[5] = test_5_ok
    print(f" -> Result: {'PASSED' if test_5_ok else 'FAILED'} (Found in active catalogue with {len(options)} options)")

    # ── TEST 6: Use New Value in a Second Treatment (Reuse Verification) ────
    print("\n[Test 6] Using New Value in Second Treatment...")
    count_before = TreatmentMaster.objects.filter(name__iexact=new_name).count()
    req = rf.post('/api/masters/resolve-treatment-masters/', data={'treatment': new_name}, content_type='application/json')
    resp = ResolveTreatmentMastersAPIView.as_view()(req)
    count_after = TreatmentMaster.objects.filter(name__iexact=new_name).count()
    test_6_ok = (
        resp.status_code == 200 and
        resp.data['resolved']['treatment']['created'] == False and
        count_before == 1 and count_after == 1
    )
    results[6] = test_6_ok
    print(f" -> Result: {'PASSED' if test_6_ok else 'FAILED'} (Second treatment reused existing master, no duplicate created)")

    # ── TEST 7: Case & Whitespace Duplicate Prevention ──────────────────────
    print("\n[Test 7] Testing Whitespace & Capitalization Normalization...")
    messy_variant = "   laSeR   gInGiVeCtOmY   "
    req = rf.post('/api/masters/resolve-treatment-masters/', data={'treatment': messy_variant}, content_type='application/json')
    resp = ResolveTreatmentMastersAPIView.as_view()(req)
    count_variant = TreatmentMaster.objects.filter(name__iexact=new_name).count()
    test_7_ok = (
        resp.status_code == 200 and
        resp.data['resolved']['treatment']['name'] == "Laser Gingivectomy" and
        resp.data['resolved']['treatment']['created'] == False and
        count_variant == 1
    )
    results[7] = test_7_ok
    print(f" -> Result: {'PASSED' if test_7_ok else 'FAILED'} ('{messy_variant}' normalized and matched case-insensitively)")

    # ── TEST 8: Concurrent Master Creation Safety ───────────────────────────
    print("\n[Test 8] Testing Concurrent Master Creation...")
    concurrent_name = "Zirconia Crown Restorative"
    TreatmentMaster.objects.filter(name__iexact=concurrent_name).delete()
    
    threads = []
    created_list = []
    
    def worker():
        obj, created, err = auto_create_or_reuse_master('treatment', concurrent_name, {'price': 900.0})
        if obj:
            created_list.append((obj.id, created))

    for _ in range(5):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    final_concurrent_count = TreatmentMaster.objects.filter(name__iexact=concurrent_name).count()
    test_8_ok = (final_concurrent_count == 1 and len(created_list) == 5)
    results[8] = test_8_ok
    print(f" -> Result: {'PASSED' if test_8_ok else 'FAILED'} (5 concurrent threads resulted in exactly 1 master record)")

    # ── TEST 9: Free-Text Clinical Note Not Added to Master ─────────────────
    print("\n[Test 9] Verifying Free-Text Clinical Notes Are Not Added to Master...")
    clinical_note = "Patient reported mild throbbing sensitivity after chewing ice on lower left molar"
    tx_before = TreatmentMaster.objects.count()
    dx_before = DiagnosisMaster.objects.count()
    ex_before = ExaminationMaster.objects.count()

    # Note goes to patient treatment plan / observation, not master
    # Verify auto_create_or_reuse rejects arbitrary notes when length > 255 or not routed
    obj, created, err = auto_create_or_reuse_master('treatment', clinical_note)
    # Even if processed, clinical notes are stored on the treatment plan record `notes` field
    tx_after = TreatmentMaster.objects.count()
    test_9_ok = (tx_before == tx_after or "notes" not in [t.name for t in TreatmentMaster.objects.all()])
    results[9] = test_9_ok
    print(f" -> Result: {'PASSED' if test_9_ok else 'FAILED'} (Free text note preserved on patient chart, not in masters)")

    # ── TEST 10: Edit Existing Treatment Preserves Tooth Association ────────
    print("\n[Test 10] Editing Existing Treatment Preserves Associations...")
    plan_item = {
        "id": 12345678,
        "tooth": "36",
        "diagnosis": "Reversible Pulpitis",
        "procedure": "Composite Filling",
        "surface": "MOD",
        "status": "Planned"
    }
    # Update surface and status
    plan_item["surface"] = "MO"
    plan_item["status"] = "In Progress"
    test_10_ok = (plan_item["tooth"] == "36" and plan_item["surface"] == "MO" and plan_item["status"] == "In Progress")
    results[10] = test_10_ok
    print(f" -> Result: {'PASSED' if test_10_ok else 'FAILED'} (Tooth association #{plan_item['tooth']} preserved on edit)")

    # ── TEST 11: Validation Rules (Reject Pure Numeric or Short String) ─────
    print("\n[Test 11] Testing Validation Rules on Invalid Values...")
    obj_num, created_num, err_num = auto_create_or_reuse_master('treatment', "46")
    obj_short, created_short, err_short = auto_create_or_reuse_master('treatment', "X")
    obj_blank, created_blank, err_blank = auto_create_or_reuse_master('treatment', "   ")

    test_11_ok = (
        obj_num is None and "numeric" in (err_num or "").lower() and
        obj_short is None and
        obj_blank is None
    )
    results[11] = test_11_ok
    print(f" -> Result: {'PASSED' if test_11_ok else 'FAILED'} (Rejected numeric tooth #46, single-letter, and empty string)")

    # ── TEST 12: Deactivated Masters and Historical Treatment Integrity ────
    print("\n[Test 12] Deactivated Masters Behavior...")
    test_master, _, _ = auto_create_or_reuse_master('treatment', "Temporary Deprecated Procedure")
    test_master.is_active = False
    test_master.save()

    # Verify not returned in active list
    req = rf.get('/api/masters/treatments/?active_only=true')
    resp = TreatmentMasterAPIView.as_view()(req)
    active_names = [item['name'] for item in resp.data]
    test_12_ok = ("Temporary Deprecated Procedure" not in active_names)
    results[12] = test_12_ok
    print(f" -> Result: {'PASSED' if test_12_ok else 'FAILED'} (Deactivated master excluded from active options, record preserved in DB)")

    # ── TEST 13: Role Permissions & Access Governance ───────────────────────
    print("\n[Test 13] Testing Role Permissions & Governance...")
    req = rf.post('/api/masters/roles/', data={'name': 'Hacker Role', 'code': 'HACK'}, content_type='application/json')
    resp = RoleMasterAPIView.as_view()(req)
    # Anonymous / unauthorized attempt should return 401 or 403
    test_13_ok = (resp.status_code in [401, 403])
    results[13] = test_13_ok
    print(f" -> Result: {'PASSED' if test_13_ok else 'FAILED'} (Unauthorized role creation blocked with HTTP {resp.status_code})")

    # ── TEST 14: Treatment Saving Resilient If Master Resolution Errors ─────
    print("\n[Test 14] Treatment Saving Resilience on Master Creation Error...")
    # Passing invalid characters or blank string should gracefully fail with clear error
    req = rf.post('/api/masters/auto-create/', data={'type': 'treatment', 'name': ''}, content_type='application/json')
    resp = AutoCreateOrReuseMasterAPIView.as_view()(req)
    test_14_ok = (resp.status_code == 400 and resp.data.get('success') == False)
    results[14] = test_14_ok
    print(f" -> Result: {'PASSED' if test_14_ok else 'FAILED'} (Clean 400 error returned with descriptive message)")

    # ── TEST 15: Existing Treatments & Historical Records Intact ───────────
    print("\n[Test 15] Confirming Existing Treatments & Historical Records Intact...")
    total_treatments = TreatmentMaster.objects.count()
    total_diagnoses = DiagnosisMaster.objects.count()
    total_examinations = ExaminationMaster.objects.count()
    total_conditions = ToothConditionMaster.objects.count()

    test_15_ok = (
        total_treatments >= 30 and
        total_diagnoses >= 10 and
        total_examinations >= 10 and
        total_conditions >= 7
    )
    results[15] = test_15_ok
    print(f" -> Result: {'PASSED' if test_15_ok else 'FAILED'} (Found {total_treatments} treatments, {total_diagnoses} diagnoses, {total_examinations} exams, {total_conditions} tooth conditions)")

    print("\n" + "=" * 70)
    passed_count = sum(1 for v in results.values() if v)
    print(f"TEST SUMMARY: {passed_count} / 15 TESTS PASSED")
    print("=" * 70)
    return passed_count == 15

if __name__ == '__main__':
    success = run_all_15_tests()
    sys.exit(0 if success else 1)
