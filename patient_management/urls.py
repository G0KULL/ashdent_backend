from django.urls import path
from . import views

app_name = 'patient_management'

urlpatterns = [
    path('patient/<int:patient_id>/', views.patient_detail, name='patient_detail'),
    path('patient/<int:patient_id>/treatments/', views.treatment_list, name='treatment_list'),
    path('patient/<int:patient_id>/add_treatment/', views.add_treatment, name='add_treatment'),
    path('patient/<int:patient_id>/prescriptions/', views.prescription_list, name='prescription_list'),
    path('patient/<int:patient_id>/add_prescription/', views.add_prescription, name='add_prescription'),
    path('patient/<int:patient_id>/invoices/', views.invoice_list, name='invoice_list'),
    path('patient/<int:patient_id>/add_invoice/', views.add_invoice, name='add_invoice'),
    path('patient/<int:patient_id>/unbilled_treatments/', views.unbilled_treatments, name='unbilled_treatments'),
]
