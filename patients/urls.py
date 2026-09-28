from django.urls import path
from .views import (
    PatientCreateView, PatientByPhoneView, PatientSearchView, PatientProfileView,
    RecentPatientsView,
    PatientBalanceWaiverView,
    AppointmentCreateView, AppointmentByPatientView,
    TodayAppointmentListView, AllAppointmentListView,
    AppointmentStatsView, AppointmentStatusUpdateView,
    MoveAppointmentToTodayView, PatientBillCreateView,
    VisitGetOrCreateView, TodayVisitListView, VisitDetailByAppointmentView,
    ClinicalNotesDetailView, ClinicalNotesSaveView, PatientClinicalHistoryView, PatientTreatmentHistoryView,
    DropdownMasterListView,
    TreatmentMasterListView, TreatmentMasterCreateView, TreatmentMasterUpdateView,
    TreatmentRecordAddView, PaymentPayView,
    DoctorListView, DoctorCreateView, DoctorScheduleListView, DoctorScheduleUpdateView,
    ToothMasterListView, CreditPatientView, PaymentSearchView,
    FollowUpListView, FollowUpUpdateView,
    PreBookingListView, PreBookingBookView, PreBookingSyncMissedView,
    PrescriptionAddView, MedicineMasterListView, PrescriptionListView,
    CreateBillingView, BillingListView, BillingUpdateView,
    PrescriptionPDFView, BillingPDFView, LatestBillingPDFView,
    CommunicationLogView, PatientGroupListView, PatientGroupDetailView, PatientBulkGroupUpdateView,
    PendingRemindersView, AppointmentRemindersView,
    LoginView, StaffCreateView, StaffOnboardView, StaffListView, StaffDetailView, StaffUpdateView, StaffToggleStatusView, StaffPermissionsUpdateView,
    CompanyListCreateView, AuditLogListView,
    PharmacyQueueView, DispenseMedicineView, DirectBillView,
    PharmacyBillView, StockManageView, PrescriptionQueueView, MedicinePurchaseView,
    RecentPaymentsView, TransactionListView, TransactionCreateView, AccountSummaryView,
    SupplierListView, SupplierDetailView, PharmacyPurchaseCreateView, MedicineStockListView, MedicinePurchaseHistoryView,
    SupplierLedgerView, SupplierLedgerDeleteView, PharmacyPurchaseDeleteView, MedicinePurchaseDeleteView,
    TaxSettingListView, TaxSettingDetailView,
    CommunicationTemplateListView, CommunicationTemplateDetailView,
    LabHeaderListView, LaboratoryListView, LabTestMasterListView, LabTestParameterView, LabPackageListView,
    DentalLaboratoryListView, DentalLaboratoryDetailView, DentalLabWorkListView, DentalLabWorkDetailView,
    WebsiteAppointmentRequestListCreateView, WebsiteAppointmentRequestActionView,
    PatientLabOrderListView, PatientLabOrderDeleteView,
    GlobalLabOrderListView,
)
from .patient_image_views import PatientImageListView, PatientImageDetailView
from .finance_views import (
    FinanceDashboardView, ExpenseCategoryAPIView, ExpenseAPIView, TransactionSummaryAPIView,
    ExpenseBulkDeleteAPIView, DoctorSalaryAPIView, DentalMaterialAPIView,
    PharmacyDashboardAPIView, GenerateSalariesAPIView, TotalExpenseSummaryView
)
from .report_views import EHRReportView
from .settings_views import (
    ClinicProfileAPIView, ClinicTimingListCreateAPIView, ClinicTimingUpdateAPIView,
    AutoNumberingAPIView, SalutationListCreateAPIView, SalutationDeleteAPIView,
    PatientRequiredFieldsAPIView,
    RoleDefaultPermissionsListView, RoleDefaultPermissionsDetailView,
    PharmacySettingsAPIView,
    PrescriptionTemplateListCreateView, PrescriptionTemplateDetailView,
    DosageLabelListView,
)

urlpatterns = [
    # PHARMACY WORKFLOW (Pharmacist + Admin only for billing/stock)
    path('pharmacy/dashboard/', PharmacyDashboardAPIView.as_view()),
    path('pharmacy/queue/', PharmacyQueueView.as_view()),
    path('pharmacy/bill/', PharmacyBillView.as_view()),
    path('pharmacy/direct-bill/', DirectBillView.as_view()),
    path('pharmacy/dispense/', DispenseMedicineView.as_view()),
    path('pharmacy/prescriptions/', PrescriptionQueueView.as_view()),
    # STOCK MANAGEMENT
    path('stock/', StockManageView.as_view()),
    path('stock/purchase/', MedicinePurchaseView.as_view()),
    path('stock/purchase/history/', MedicinePurchaseHistoryView.as_view()),
    path('stock/purchase/advanced/', PharmacyPurchaseCreateView.as_view()),
    path('stock/<str:pk>/', StockManageView.as_view()),

    # PATIENT
    path('patient/create/', PatientCreateView.as_view()),
    path('patient/search/', PatientSearchView.as_view()),
    path('patients/recent/', RecentPatientsView.as_view()),
    path('patient/by-phone/<str:phone>/', PatientByPhoneView.as_view()),
    path('patient/<str:pk>/profile/', PatientProfileView.as_view()),
    path('patient/<str:pk>/balance/waiver/', PatientBalanceWaiverView.as_view()),
    path('patient/<int:patient_id>/lab-orders/', PatientLabOrderListView.as_view()),
    path('lab-orders/', GlobalLabOrderListView.as_view()),
    path('lab-orders/<int:pk>/', PatientLabOrderDeleteView.as_view()),

    # APPOINTMENT
    path('appointment/create/', AppointmentCreateView.as_view()),
    path('appointment/patient/<str:patient_id>/', AppointmentByPatientView.as_view()),
    path('appointments/today/', TodayAppointmentListView.as_view()),
    path('appointments/all/', AllAppointmentListView.as_view()),
    path('appointments/stats/', AppointmentStatsView.as_view()),
    path('appointments/<str:pk>/status/', AppointmentStatusUpdateView.as_view()),
    path('appointments/<str:pk>/move-to-today/', MoveAppointmentToTodayView.as_view()),
    path('bill/create/', PatientBillCreateView.as_view()),

    # VISIT
    path('visit/create/', VisitGetOrCreateView.as_view()),
    path('visit/get-or-create/', VisitGetOrCreateView.as_view()),
    path('visit/appointment/<str:appointment_id>/', VisitDetailByAppointmentView.as_view()),
    path('visits/today/', TodayVisitListView.as_view()),

    # CLINICAL NOTES
    path('clinical-notes/create/', ClinicalNotesSaveView.as_view()),
    path('clinical-notes/save/', ClinicalNotesSaveView.as_view()),
    path('clinical-notes/<str:appointment_id>/', ClinicalNotesDetailView.as_view()),
    path('patient/<str:patient_id>/clinical-history/', PatientClinicalHistoryView.as_view()),
    path('patient/<str:patient_id>/treatment-history/', PatientTreatmentHistoryView.as_view()),

    # DROPDOWNS
    path('dropdowns/<str:type>/', DropdownMasterListView.as_view()),

    # TREATMENT MASTER
    path('treatment-master/list/', TreatmentMasterListView.as_view()),
    path('treatment-master/create/', TreatmentMasterCreateView.as_view()),
    path('treatment-master/update/<str:pk>/', TreatmentMasterUpdateView.as_view()),

    # TREATMENT RECORD
    path('treatment-record/create/', TreatmentRecordAddView.as_view(), name='treatment-record-create'),
    path('treatment-record/add/', TreatmentRecordAddView.as_view()),

    # PAYMENT
    path('payment/pay/<str:pk>/', PaymentPayView.as_view()),
    path('payments/search/', PaymentSearchView.as_view(), name='payment-search'),
    path('payments/recent/', RecentPaymentsView.as_view(), name='payment-recent'),
    path('billing/search/', PaymentSearchView.as_view(), name='billing-search-alias'),

    # CREDITS
    path('credits/', CreditPatientView.as_view(), name='credits'),

    # DOCTOR
    path('doctors/', DoctorListView.as_view()),
    path('doctor/create/', DoctorCreateView.as_view()),
    path('doctor-schedules/', DoctorScheduleListView.as_view()),
    path('doctor-schedules/<str:pk>/', DoctorScheduleUpdateView.as_view()),

    path('teeth/', ToothMasterListView.as_view()),
    path('teeth/select/', ClinicalNotesSaveView.as_view()),

    path('patient-images/', PatientImageListView.as_view()),
    path('patient-images/<str:pk>/', PatientImageDetailView.as_view()),

    # FOLLOW-UPS
    path('follow-ups/', FollowUpListView.as_view()),
    path('follow-ups/update/<str:pk>/', FollowUpUpdateView.as_view()),
    # PRE-BOOKINGS
    path('pre-bookings/', PreBookingListView.as_view()),
    path('pre-bookings/book/<str:pk>/', PreBookingBookView.as_view()),
    path('pre-bookings/sync-missed/', PreBookingSyncMissedView.as_view()),
    # PRESCRIPTIONS
    path('prescription/add/', PrescriptionAddView.as_view()),
    path('prescription/list/', PrescriptionListView.as_view()),
    path('medicine-master/list/', MedicineMasterListView.as_view()),
    # BILLS
    path('bill/create-advanced/', CreateBillingView.as_view()),
    path('bill/list/', BillingListView.as_view()),
    path('create-billing/', CreateBillingView.as_view()),
    path('billing/latest/', LatestBillingPDFView.as_view()),
    path('billing/<str:pk>/update/', BillingUpdateView.as_view()),
    path('billing/<str:pk>/pdf/', BillingPDFView.as_view()),
    path('prescription/<str:pk>/pdf/', PrescriptionPDFView.as_view()),
    path('communication-logs/', CommunicationLogView.as_view()),
    path('patient-groups/', PatientGroupListView.as_view()),
    path('patient-groups/<str:pk>/', PatientGroupDetailView.as_view()),
    path('patients/bulk-group-update/', PatientBulkGroupUpdateView.as_view()),
    path('reminders/pending/', PendingRemindersView.as_view()),
    path('appointments/reminders/', AppointmentRemindersView.as_view()),
    # AUTH & MULTI-TENANT STAFF MANAGEMENT
    path('login/', LoginView.as_view()),
    path('companies/', CompanyListCreateView.as_view()),
    path('staff/onboard/', StaffOnboardView.as_view()),
    path('staff/create/', StaffCreateView.as_view()),
    path('staff/list/', StaffListView.as_view()),
    path('staff/<str:pk>/', StaffDetailView.as_view()),
    path('staff/<str:pk>/update/', StaffUpdateView.as_view()),
    path('staff/<str:pk>/toggle-status/', StaffToggleStatusView.as_view()),
    path('staff/<str:pk>/permissions/', StaffPermissionsUpdateView.as_view()),
    path('audit-logs/', AuditLogListView.as_view()),
    # ACCOUNTS / TRANSACTIONS
    path('transactions/', TransactionListView.as_view()),
    path('transactions/create/', TransactionCreateView.as_view()),
    path('accounts/summary/', AccountSummaryView.as_view()),

    # PHARMACY PURCHASE & STOCK
    path('pharmacy/suppliers/', SupplierListView.as_view()),
    path('pharmacy/suppliers/<str:pk>/', SupplierDetailView.as_view()),
    path('pharmacy/purchase/create/', PharmacyPurchaseCreateView.as_view()),
    path('pharmacy/stock/batches/', MedicineStockListView.as_view()),
    path('pharmacy/suppliers/<str:supplier_id>/ledger/', SupplierLedgerView.as_view()),
    path('pharmacy/ledger/<str:pk>/delete/', SupplierLedgerDeleteView.as_view()),
    path('pharmacy/purchase/<str:pk>/delete/', PharmacyPurchaseDeleteView.as_view()),
    path('stock/purchase/<str:pk>/delete/', MedicinePurchaseDeleteView.as_view()),
    path('reports/<str:report_type>/', EHRReportView.as_view()),

    # GENERAL SETTINGS
    path('settings/taxes/', TaxSettingListView.as_view()),
    path('settings/taxes/<str:pk>/', TaxSettingDetailView.as_view()),
    path('settings/communication-templates/', CommunicationTemplateListView.as_view()),
    path('settings/communication-templates/<str:pk>/', CommunicationTemplateDetailView.as_view()),

    # PATHOLOGY LAB SETTINGS
    path('settings/lab-headers/', LabHeaderListView.as_view()),
    path('settings/laboratories/', LaboratoryListView.as_view()),
    path('settings/lab-tests/', LabTestMasterListView.as_view()),
    path('settings/lab-parameters/', LabTestParameterView.as_view()),
    path('settings/lab-packages/', LabPackageListView.as_view()),
    
    # CLINIC PROFILE SETTINGS
    path('settings/clinic-profile/', ClinicProfileAPIView.as_view()),
    path('settings/clinic-timing/', ClinicTimingListCreateAPIView.as_view()),
    path('settings/clinic-timing/<str:pk>/', ClinicTimingUpdateAPIView.as_view()),
    path('settings/auto-numbering/', AutoNumberingAPIView.as_view()),
    path('settings/salutations/', SalutationListCreateAPIView.as_view()),
    path('settings/salutations/<str:pk>/', SalutationDeleteAPIView.as_view()),
    path('settings/patient-required-fields/', PatientRequiredFieldsAPIView.as_view()),

    # ROLE DEFAULT PERMISSIONS
    path('settings/role-defaults/', RoleDefaultPermissionsListView.as_view()),
    path('settings/role-defaults/<str:role>/', RoleDefaultPermissionsDetailView.as_view()),

    # PHARMACY SETTINGS
    path('settings/pharmacy/', PharmacySettingsAPIView.as_view()),

    # PRESCRIPTION TEMPLATES
    path('settings/prescription-templates/', PrescriptionTemplateListCreateView.as_view()),
    path('settings/prescription-templates/<str:pk>/', PrescriptionTemplateDetailView.as_view()),

    # DOSAGE LABELS
    path('settings/dosage-labels/', DosageLabelListView.as_view()),

    # DENTAL LAB SETTINGS
    path('settings/dental-laboratories/', DentalLaboratoryListView.as_view()),
    path('settings/dental-laboratories/<str:pk>/', DentalLaboratoryDetailView.as_view()),
    path('settings/dental-lab-work/', DentalLabWorkListView.as_view()),
    path('settings/dental-lab-work/<str:pk>/', DentalLabWorkDetailView.as_view()),
    
    # FINANCE DASHBOARD & EXPENSE MANAGEMENT SYSTEM APIs
    path('finance/dashboard/', FinanceDashboardView.as_view()),
    path('finance/categories/', ExpenseCategoryAPIView.as_view()),
    path('finance/categories/<str:pk>/', ExpenseCategoryAPIView.as_view()),
    path('finance/expenses/', ExpenseAPIView.as_view()),
    path('finance/expenses/bulk-delete/', ExpenseBulkDeleteAPIView.as_view()),
    path('finance/expenses/<str:pk>/', ExpenseAPIView.as_view()),
    path('finance/transaction-summary/', TransactionSummaryAPIView.as_view()),
    path('finance/salaries/', DoctorSalaryAPIView.as_view()),
    path('finance/generate-salaries/', GenerateSalariesAPIView.as_view()),
    path('finance/salaries/<str:pk>/', DoctorSalaryAPIView.as_view()),
    path('finance/materials/', DentalMaterialAPIView.as_view()),
    path('finance/total-expenses/', TotalExpenseSummaryView.as_view()),
    
    # WEBSITE APPOINTMENT REQUESTS
    path('website-appointments/', WebsiteAppointmentRequestListCreateView.as_view()),
    path('website-appointments/<str:pk>/action/', WebsiteAppointmentRequestActionView.as_view()),
]
