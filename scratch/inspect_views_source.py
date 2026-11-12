import sys, os, inspect
sys.path.insert(0, 'ashdent-back')
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
import django; django.setup()

from patients import views, billing_views

target_views = [
    ('BillingListView', views.BillingListView),
    ('PatientEMRDetailView', views.PatientEMRDetailView),
    ('PatientToothConditionsView', views.PatientToothConditionsView),
    ('PatientTreatmentHistoryView', views.PatientTreatmentHistoryView),
    ('RecentPaymentsView', views.RecentPaymentsView),
    ('PrescriptionListView', views.PrescriptionListView),
    ('AppointmentByPatientView', views.AppointmentByPatientView),
    ('PatientUnbilledTreatmentsView', views.PatientUnbilledTreatmentsView),
    ('RecentPatientsView', views.RecentPatientsView),
    ('BillPaymentCreateView', billing_views.BillPaymentCreateView),
    ('PatientImageListView', views.PatientImageListView),
    ('PatientInvestigationDetailView', views.PatientInvestigationDetailView),
    ('TreatmentPlanItemUpdateView', views.TreatmentPlanItemUpdateView),
    ('PaymentSearchView', views.PaymentSearchView)
]

for name, cls in target_views:
    lines, start_line = inspect.getsourcelines(cls)
    fpath = inspect.getsourcefile(cls)
    print(f"=== {name} ({os.path.basename(fpath)}: lines {start_line}-{start_line + len(lines)}) ===")
    print(''.join(lines[:12]))
    print("...")

