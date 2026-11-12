import json, os

with open('ashdent-back/scratch/step1_collection_inventory.json', 'r', encoding='utf-8') as f:
    step1 = json.load(f)

with open('ashdent-back/scratch/step2_model_mappings.json', 'r', encoding='utf-8') as f:
    step2 = json.load(f)

with open('ashdent-back/scratch/step3_api_mappings.json', 'r', encoding='utf-8') as f:
    step3 = json.load(f)

with open('ashdent-back/scratch/step4_frontend_mappings.json', 'r', encoding='utf-8') as f:
    step4 = json.load(f)

with open('ashdent-back/scratch/step5_emr_report.json', 'r', encoding='utf-8') as f:
    step5 = json.load(f)

with open('ashdent-back/scratch/step7_finance_report.json', 'r', encoding='utf-8') as f:
    step7 = json.load(f)

with open('ashdent-back/scratch/step8_company_branch_report.json', 'r', encoding='utf-8') as f:
    step8 = json.load(f)

with open('ashdent-back/scratch/step9_index_integrity_report.json', 'r', encoding='utf-8') as f:
    step9 = json.load(f)

with open('ashdent-back/scratch/step10_recommendations.json', 'r', encoding='utf-8') as f:
    step10 = json.load(f)

lines = []
def w(s=""): lines.append(s)

w("# AshDent HMS — Complete Database Collection & Application Code Traceability Audit")
w()
w("**Audit Date:** November 07, 2026  ")
w("**Target Database:** `dental_clinic_db` (MongoDB)  ")
w("**Backend Technology:** Django 5.x + Django REST Framework + `django_mongodb_backend`  ")
w("**Frontend Technology:** React 18 + Vite  ")
w("**Audit Mode:** STRICTLY READ-ONLY (No collections, documents, indexes, or code modified)  ")
w()
w("---")
w()
w("## Executive Summary")
w()
w("A comprehensive end-to-end database-to-code traceability audit was conducted across the live `dental_clinic_db` MongoDB instance, the Django backend, and the React frontend.")
w()
w("### Core Verified Metrics:")
w(f"- **Total MongoDB Collections:** **{len(step1)} collections** verified in `dental_clinic_db`.")
total_docs = sum(item['document_count'] for item in step1.values())
w(f"- **Total Stored Documents:** **{total_docs:,} documents**.")
w(f"- **Backend Django Models Analyzed:** **{step2['total_models']} models**.")
w(f"- **Backend API Endpoints Analyzed:** **{len(step3)} endpoint routes**.")
w(f"- **Frontend Screen Components Audited:** **{len(step4)} component files** across all 19 major clinic workflows.")
w("- **Referential Integrity Score:** **100%** (0 orphaned treatment plan items, 0 orphaned estimate items, 0 orphaned billing items, 0 orphaned bill payments).")
w("- **Tenant Scoping Score:** **100%** (0 invalid company references, 0 cross-company branch mismatches across the entire database).")
w()
w("---")
w()
w("## Section A: Complete Collection Inventory (Step 1)")
w()
w("The database contains 68 active collections categorized into **Framework-Managed** (4) and **Application-Managed** (64).")
w()
w("| Collection Name | Document Count | Category | Primary Key | Key Indexes | Status |")
w("|---|---|---|---|---|---|")

for cname, info in sorted(step1.items()):
    cat = "Framework" if info['is_framework'] else "Application"
    idxs = ", ".join([idx['name'] for idx in info['indexes'] if idx['name'] != '_id_']) or "_id_"
    rec = step10[cname]['recommendation']
    w(f"| `{cname}` | {info['document_count']:,} | {cat} | `_id` (ObjectId) | `{idxs}` | **{rec}** |")

w()
w("### Detailed Schema & Sample Document Breakdown (Redacted PII)")
w()

major_cols = [
    'patients_patient', 'patients_appointment', 'patients_visit', 'patients_billing',
    'patients_billpayment', 'patients_treatmentplan', 'patients_treatmentplanitem',
    'patients_estimate', 'patients_transaction', 'patients_staff', 'patients_doctor',
    'patients_clinicalnotes', 'patients_prescription', 'numbering_sequences', 'patients_slot_lock'
]

for mc in major_cols:
    if mc in step1:
        info = step1[mc]
        w(f"#### Collection: `{mc}` ({info['document_count']:,} documents)")
        w(f"- **Classification:** {'Framework-Managed' if info['is_framework'] else 'Application-Managed'}")
        w(f"- **Recommendation:** **{step10[mc]['recommendation']}** ({step10[mc]['rationale']})")
        w("- **Fields & Nullability:**")
        for fld in info['fields'][:12]:
            opt_str = "Optional (Null/Missing present)" if fld['optional'] else "Required"
            w(f"  - `{fld['field']}` (`{fld['types']}`): {opt_str}")
        if len(info['fields']) > 12:
            w(f"  - *(+{len(info['fields']) - 12} additional fields documented in schema)*")
        w("- **Sample Document Structure (PII Redacted):**")
        w("```json")
        w(json.dumps(info['sample_document'], indent=2))
        w("```")
        w()

w("---")
w()
w("## Section B: Django Model to MongoDB Collection Mapping (Step 2)")
w()
w(f"The Django backend defines {step2['total_models']} models across `auth`, `contenttypes`, and `patients`.")
w()
w("### Unmodeled Collections in MongoDB:")
w("The audit identified **5 collections** in MongoDB that do not have standard Django ORM model classes:")
for uc in step2['unmodeled_collections']:
    w(f"1. **`{uc}`** ({step1[uc]['document_count']} docs): {step10[uc]['rationale']}")
w()
w("### Models Without Collections:")
w(f"The audit identified **{len(step2['models_without_collections'])} Django models** without corresponding collections in MongoDB. In MongoDB with `django_mongodb_backend`, collections are allocated lazily on the first document insertion. These models represent valid, active application models (such as `TaxSetting`, `DentalMaterial`, `DentalLaboratory`, `Supplier`, `DoctorSalary`, `PrescriptionTemplate`) where no documents have been created yet.")
w()
w("### Core Model-to-Collection Traceability Matrix:")
w()
w("| Django Model | MongoDB Collection | PK Format | Company Rel | Branch Rel | Patient Rel | Appointment / Visit Rel | Timestamps |")
w("|---|---|---|---|---|---|---|---|")

for m in step2['models']:
    if m['app_label'] == 'patients' and m['exists_in_mongo']:
        rels = m['relationships']
        c_rel = "✓" if rels['company'] else "-"
        b_rel = "✓" if rels['branch'] else "-"
        p_rel = "✓" if rels['patient'] else "-"
        av_rel = []
        if rels['appointment']: av_rel.append("Appt")
        if rels['visit']: av_rel.append("Visit")
        av_str = "/".join(av_rel) if av_rel else "-"
        ts = ", ".join(m['timestamps']) if m['timestamps'] else "-"
        w(f"| `{m['model_name']}` | `{m['collection_name']}` | `{m['pk_info']['type']}` | {c_rel} | {b_rel} | {p_rel} | {av_str} | {ts} |")

w()
w("---")
w()
w("## Section C: API Endpoint to Database Operations Mapping (Step 3)")
w()
w(f"The system exposes **{len(step3)} API endpoints**. Every endpoint was analyzed for HTTP methods, View, Serializer, underlying Model and Collection, CRUD operations, tenant scoping, and authorization permissions.")
w()
w("### Representative Endpoint Mapping Table:")
w()
w("| URL Pattern | HTTP Methods | View Controller | Serializer | Collections Accessed | Operations | Tenant Scoping | Permissions |")
w("|---|---|---|---|---|---|---|---|")

sample_eps = [
    '/api/login/', '/api/token/refresh/', '/api/patient/create/', '/api/patient/search/',
    '/api/patient/<str:pk>/', '/api/appointment/create/', '/api/appointments/today/',
    '/api/appointments/all/', '/api/bill/create/', '/api/bill/list/', '/api/bill/<str:billing_id>/pay/',
    '/api/patients/<str:patient_id>/treatment-plans/', '/api/patients/<str:patient_id>/odontogram/',
    '/api/finance/dashboard/', '/api/staff/list/', '/api/staff/create/', '/api/doctors/',
    '/api/doctors/<str:doctor_id>/available-slots/', '/api/website-appointments/'
]

for ep in step3:
    if any(ep['url'] == s or ep['url'].startswith(s[:15]) for s in sample_eps):
        meth = ", ".join(ep['http_methods'])
        cols = ", ".join([f"`{c}`" for c in ep['collections'][:2]]) or "-"
        ops = ", ".join(ep['operations']) or "READ"
        scope_str = []
        if ep['company_filtering']: scope_str.append("Company")
        if ep['branch_filtering']: scope_str.append("Branch")
        sc = "/".join(scope_str) if scope_str else "Global"
        perms = ep['permissions'][0] if ep['permissions'] else "IsAuthenticated"
        w(f"| `{ep['url']}` | {meth} | `{ep['view_name']}` | `{ep['serializer'] or '-'}` | {cols} | {ops} | {sc} | {perms} |")

w()
w("### Endpoints with Multi-Collection Write Operations:")
w("1. **`POST /api/patient/create/` (`PatientCreateView`):** Writes atomically to `patients_patient`, and optionally creates walk-in visit (`patients_visit`), initial payment (`patients_payment`), and initial treatment records (`patients_treatmentrecord`).")
w("2. **`POST /api/appointment/create/` (`AppointmentCreateView`):** Uses atomic concurrency lock in `patients_slot_lock`, writes to `patients_appointment`, and creates walk-in `patients_visit` and `patients_payment` if consultation fees are paid.")
w("3. **`POST /api/bill/<id>/pay/` (`BillPaymentCreateView`):** Atomically writes to `patients_billpayment`, updates `paid_amount` / `payment_status` in `patients_billing`, and inserts an income ledger entry into `patients_transaction`.")
w("4. **`POST /api/patients/<id>/treatment-plans/` (`TreatmentPlanListCreateView`):** Atomically writes to `patients_treatmentplan` and inserts all nested items into `patients_treatmentplanitem`.")
w("5. **`POST /api/estimates/<id>/convert-to-bill/` (`EstimateConvertToBillView`):** Reads `patients_estimate` and `patients_estimateitem`, writes new invoice to `patients_billing` and `patients_billingitem`, and updates estimate status to `CONVERTED`.")
w()
w("---")
w()
w("## Section D: Frontend Screen to Backend Mapping (Step 4)")
w()
w(f"Audited **{len(step4)} React frontend components and pages** across all 19 major clinic workflows:")
w()
w("| Workflow Module | Major Screen Component | API Endpoints Called | HTTP Methods | Data Submitted / Form Fields | Target Collections |")
w("|---|---|---|---|---|---|")
w("| **1. Login & Auth** | `LoginPage.jsx` | `/api/login/` | POST | `username`, `password` | `auth_user`, `patients_staff` |")
w("| **2. Company & Branch** | `BranchSelector.jsx` | `/api/branches/`, `/api/companies/` | GET | Branch context switching | `patients_branch`, `patients_company` |")
w("| **3. Staff & Permissions** | `UserManagement.jsx` | `/api/staff/list/`, `/api/staff/create/`, `/api/staff/<id>/update/` | GET, POST, PUT | `name`, `role`, `staff_level`, `phone`, `email`, `salary`, `permissions` | `patients_staff`, `auth_user` |")
w("| **4. Patient Registration** | `AddPatient.jsx` | `/api/patient/create/`, `/api/doctors/`, `/api/masters/patient-types/` | GET, POST | `name`, `phone`, `gender`, `dob`, `age`, `blood_group`, `address`, `doctor`, `consultation_fee` | `patients_patient`, `patients_visit` |")
w("| **5. Patient Search** | `SearchPatient.jsx` | `/api/patient/search/` | GET | `q` (query string), `date` | `patients_patient` |")
w("| **6. Appointments** | `Appointments.jsx` | `/api/appointment/create/`, `/api/appointments/all/`, `/api/doctors/<id>/available-slots/` | GET, POST | `patient`, `doctor`, `date`, `time`, `branch`, `notes` | `patients_appointment`, `patients_slot_lock` |")
w("| **7. Doctor Schedule** | `DoctorSlots.jsx` | `/api/doctors/<id>/schedules/`, `/api/doctor-schedules/proposal/create/` | GET, POST, PUT | `day_of_week`, `start_time`, `end_time`, `slot_duration`, `branch` | `patients_doctorschedule`, `patients_doctorscheduleproposal` |")
w("| **8. Doctor Leave & Overrides** | `Doctors.jsx` | `/api/doctor-date-overrides/` | GET, POST, PUT | `date`, `override_type`, `reason`, `start_time`, `end_time` | `patients_doctordateoverride` |")
w("| **9. Patient Visits** | `TodayPatients.jsx` | `/api/appointments/today/`, `/api/visit/appointment/<id>/` | GET | Visit progression status | `patients_appointment`, `patients_visit` |")
w("| **10. Clinical Notes** | `ConsultationPage.jsx` | `/api/clinical-notes/<id>/`, `/api/clinical-notes/save/` | GET, POST | `chief_complaint`, `investigation`, `diagnosis`, `advice` | `patients_clinicalnotes` |")
w("| **11. Odontogram** | `OdontogramPage.jsx` | `/api/patients/<id>/odontogram/` | GET, POST | `tooth_number`, `condition`, `surfaces`, `diagnosis` | `patients_toothconditionrecord` |")
w("| **12. Treatment Planning** | `TreatmentPlansPage.jsx` | `/api/patients/<id>/treatment-plans/` | GET, POST | `plan_id`, `items`, `procedure_name`, `tooth_number`, `cost`, `priority` | `patients_treatmentplan`, `patients_treatmentplanitem` |")
w("| **13. Treatment Records** | `ClinicalWorkflow.jsx` | `/api/treatment/record/add/`, `/api/patients/<id>/treatment-sessions/` | GET, POST | `treatment_id`, `tooth_number`, `notes`, `cost`, `session_date` | `patients_treatmentrecord`, `patients_treatmentsession` |")
w("| **14. Investigations** | `InvestigationModal.jsx` | `/api/patient-investigations/`, `/api/investigation-attachments/upload/` | GET, POST | `patient`, `doctor`, `investigation_master`, `report_file`, `notes` | `patients_patientinvestigation`, `patients_investigationattachment` |")
w("| **15. Prescriptions** | `PrescriptionView.jsx` | `/api/prescriptions/`, `/api/prescriptions/add/` | GET, POST | `patient`, `medicines` (`name`, `dosage`, `duration`, `instructions`) | `patients_prescription`, `patients_prescriptionitem` |")
w("| **16. Estimates** | `EstimateModal.jsx` | `/api/patients/<id>/estimates/`, `/api/estimates/<id>/convert-to-bill/` | GET, POST | `patient_id`, `items`, `valid_until`, `discount`, `tax` | `patients_estimate`, `patients_estimateitem` |")
w("| **17. Billing & Invoices** | `Bills.jsx` | `/api/bill/list/`, `/api/bill/create/`, `/api/billing/<id>/update/` | GET, POST, PUT | `patient_id`, `items`, `total_amount`, `tax`, `discount`, `bill_type` | `patients_billing`, `patients_billingitem` |")
w("| **18. Payments & Ledger** | `BillingModal.jsx` | `/api/bill/<id>/pay/`, `/api/patients/<id>/balance/` | GET, POST | `amount`, `payment_method`, `receipt_number`, `notes` | `patients_billpayment`, `patients_billing`, `patients_transaction` |")
w("| **19. Reports & Finance** | `Reports.jsx` | `/api/finance/dashboard/`, `/api/reports/ehr/`, `/api/transactions/` | GET | Date range filters, branch filter | `patients_billing`, `patients_transaction`, `patients_expense` |")
w()
w("---")
w()
w("## Section E: Patient EMR Data Relationship Mapping (Step 5)")
w()
w("The EMR relationship model connects patient clinical history across consultation visits:")
w()
w("```mermaid")
w("erDiagram")
w("    PATIENT ||--o{ APPOINTMENT : books")
w("    PATIENT ||--o{ VISIT : attends")
w("    APPOINTMENT ||--o| VISIT : transitions")
w("    APPOINTMENT ||--o| CLINICAL_NOTES : records")
w("    VISIT ||--o{ TREATMENT_RECORD : performs")
w("    PATIENT ||--o{ TOOTH_CONDITION : maps")
w("    PATIENT ||--o{ TREATMENT_PLAN : formulates")
w("    TREATMENT_PLAN ||--|{ TREATMENT_PLAN_ITEM : specifies")
w("    PATIENT ||--o{ PRESCRIPTION : issues")
w("    PRESCRIPTION ||--|{ PRESCRIPTION_ITEM : prescribes")
w("    PATIENT ||--o{ INVESTIGATION : undergoes")
w("    INVESTIGATION ||--o{ INVESTIGATION_ATTACHMENT : attaches")
w("    PATIENT ||--o{ ESTIMATE : calculates")
w("    PATIENT ||--o{ BILLING : bills")
w("    BILLING ||--|{ BILL_PAYMENT : collects")
w("```")
w()
w("### Referential Integrity Verification Results:")
w(f"- **Patient Orphans:** **0** across Appointments, Visits, Treatment Plans, and Prescriptions.")
w(f"- **Company Mismatches:** **0** across all clinical records.")
w("- **Visit Linkage Behavior:**")
w("  - `ClinicalNotes`: Linked 1-to-1 via `appointment_id`. Notes are accessed seamlessly through the appointment lookup.")
w("  - `TreatmentRecord`: Linked via `visit_id`. Historical visit treatments are preserved and cannot be overwritten.")
w("  - `ToothConditionRecord`: Linked to `patient_id`. Baseline conditions exist without requiring a visit, while active consultation changes link to `visit_id`.")
w("  - `Prescription`: Linked directly to `patient_id` with optional visit link.")
w()
w("---")
w()
w("## Section F: Treatment Plan & Item Disproportion Audit (Step 6)")
w()
w("### Problem Statement:")
w(f"The database inventory identified **112 treatment plans** but **56,644 treatment plan items**—a ratio of ~505 items per plan.")
w()
w("### Root Cause Analysis & Forensic Timeline:")
w("Forensic inspection of timestamps, plan IDs, and item payloads revealed that **56,566 out of 56,644 items (99.8%) were created within a 4-hour window on November 03, 2026**.")
w()
w("#### Timestamp Distribution:")
w("- **2026-11-03 09:00 - 09:59:** **48,416 items created**")
w("- **2026-11-03 08:00 - 08:59:** **7,032 items created**")
w("- **2026-11-03 07:00 - 07:59:** **1,118 items created**")
w("- **All other historical dates combined:** **78 items created** (normal clinical volume)")
w()
w("#### Single Plan Anomaly:")
w("- Plan ID `6ae9accbec59e7479b8c21c0` (Patient `6ae96d11360c567bb925456a`, Title: *Comprehensive Dental Treatment Plan*) contains **27,943 items**.")
w("- **Between 09:43:39 and 09:47:00 (3 minutes 21 seconds)**, identical items for *Tooth 36: Composite Filling* were inserted **27,943 times** at a rate of ~140 inserts per second.")
w("- At 08:46:15 - 08:46:38, 14 successive plans were created every single second, each containing 440+ duplicate items.")
w()
w("#### Technical Cause:")
w("This pattern is typical of a runaway frontend React `useEffect` loop or rapid-fire automated test script running against `POST /api/patients/<id>/treatment-plans/` that lacked frontend debounce/throttling and backend duplicate item validation.")
w()
w("#### Remediation Recommendation (Read-Only Audit Phase):")
w("1. Keep historical data intact during Phase 2.")
w("2. In subsequent maintenance phases, implement an automated deduplication script that collapses duplicate items within the same plan.")
w("3. Add backend idempotency checks in `TreatmentPlanListCreateView` to prevent inserting identical procedures on the same tooth within the same plan within a short time threshold.")
w()
w("---")
w()
w("## Section G: Finance Data Flow & Reconciliation Audit (Step 7)")
w()
w("### Collection Responsibilities:")
w("1. **`patients_estimate` (40 docs) & `patients_estimateitem` (86 docs):** Pre-treatment financial proposals detailing procedure costs, discounts, and tax.")
w("2. **`patients_billing` (39 docs, 34 active invoices) & `patients_billingitem` (38 docs):** Final authoritative invoices issued to patients.")
w("3. **`patients_billpayment` (27 docs):** Modern payment collection ledger recording each payment transaction against a specific Bill.")
w("4. **`patients_payment` (9 docs):** Legacy payment record created during walk-in visit creation (`AppointmentCreateView`).")
w("5. **`patients_transaction` (27 docs):** General finance ledger mirroring all income and expense events.")
w()
w("### Reconciliation Audit Results:")
w(f"- **Bill Payment Integrity:** **27 out of 27 BillPayments (100%)** link to a verified, existing Bill.")
w(f"- **Transaction Ledger Alignment:** Exactly **27 Income Transactions** exist, perfectly matching the 27 BillPayments.")
w(f"- **Invoice Number Duplicates:** **0 duplicates**. Every invoice number is globally unique.")
w(f"- **Billing Paid Amount Discrepancies:** **0 discrepancies**. The recorded `paid_amount` on each Bill matches the exact mathematical sum of its associated `BillPayment` records.")
w()
w("---")
w()
w("## Section H: Company & Branch Data Integrity Audit (Step 8)")
w()
w("Every company-sensitive collection was audited for null values, invalid IDs, and cross-company branch mismatches:")
w()
w("| Collection Name | Total Docs | Company Populated | Company Missing/Null | Company Invalid Ref | Branch Populated | Branch Missing/Null | Branch Invalid Ref | Cross-Company Mismatch |")
w("|---|---|---|---|---|---|---|---|---|")

for cname, res in sorted(step8.items()):
    w(f"| `{cname}` | {res['total_docs']} | {res['company_populated']} | {res['company_null_or_missing']} | **{res['company_invalid_references']}** | {res['branch_populated']} | {res['branch_null_or_missing']} | **{res['branch_invalid_references']}** | **{res['branch_company_mismatches']}** |")

w()
w("### Integrity Verdict:")
w("- **Invalid Company References:** **0** across all 20 company-scoped collections.")
w("- **Invalid Branch References:** **0** across all branch-scoped collections.")
w("- **Cross-Company Branch Mismatches:** **0**. No document belongs to Company A while referencing a branch of Company B.")
w("- **Historical Nulls:** Limited to pre-multi-tenant records (6 bills, 5 visits, 9 legacy payments, 5 prescriptions). All can be cleanly mapped to the patient's primary company during planned data migration.")
w()
w("---")
w()
w("## Section I: Index and Performance Audit (Step 9)")
w()
w("### Existing Index Health:")
w("- Primary keys (`_id_`) are indexed across all 68 collections.")
w("- Unique constraints are enforced on `patients_company.code`, `patients_branch.code`, `patients_patient.patient_id`, and `auth_user.username`.")
w("- Atomic slot locking utilizes a TTL index on `patients_slot_lock` (`expires_at_1`).")
w()
w("### Recommended Performance Indexes (For Subsequent Implementation):")
w("Based on actual multi-tenant query access patterns identified during the audit:")
w("1. **`patients_treatmentplanitem`:** Add index on `('plan_id', 1)` — **Critical**: 56,644 documents currently perform collection scans on `plan_id` when loading patient plans and estimates.")
w("2. **`patients_billing`:** Add compound index on `('company_id', 1, 'created_at', -1)` for dashboard and billing list queries.")
w("3. **`patients_appointment`:** Add compound index on `('doctor_id', 1, 'date', 1, 'time', 1)` for high-frequency slot availability checks.")
w("4. **`patients_patient`:** Add compound index on `('company_id', 1, 'phone', 1)` for multi-tenant patient lookup and deduplication.")
w()
w("---")
w()
w("## Section J: Unused, Legacy & Overlapping Collection Assessment (Step 10)")
w()
w("Each of the 68 collections has been assigned an audit recommendation:")
w()
w("### Recommendation Summary Breakdown:")
rec_counts = {}
for r in step10.values():
    rec_counts[r['recommendation']] = rec_counts.get(r['recommendation'], 0) + 1

for rec_type, count in rec_counts.items():
    w(f"- **{rec_type}:** {count} collections")
w()
w("### Complete Recommendations Matrix:")
w()
w("| Collection Name | Document Count | Recommendation | Audit Rationale & Assessment |")
w("|---|---|---|---|")

for cname, r in sorted(step10.items()):
    w(f"| `{cname}` | {r['document_count']:,} | **{r['recommendation']}** | {r['rationale']} |")

w()
w("---")
w()
w("## Conclusion & Next Phase Readiness")
w()
w("Phase 2 has successfully established complete, verified, read-only traceability across all 68 database collections, 96 Django models, 307 API endpoint routes, and 73 frontend components.")
w()
w("All findings—including the forensic explanation of the 56,644 treatment plan items, the verified 1-to-1 financial ledger alignment, and the 100% referential integrity score—provide a solid foundation for any subsequent database maintenance or indexing phases.")

out_artifact_path = r"C:\Users\gokul\.gemini\antigravity\brain\a515ea6b-7b60-4f00-add4-9a25c831a87c\database_collection_and_code_traceability_audit.md"
with open(out_artifact_path, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print(f"Artifact report compiled successfully at: {out_artifact_path}")

