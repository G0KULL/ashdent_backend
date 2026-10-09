import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from patients.models import (
    Patient, Appointment, Visit, ClinicalNotes, Billing, BillingItem, 
    Prescription, PrescriptionItem, CommunicationLog, MedicinePurchase, 
    TreatmentRecord, Payment, Expense, DoctorSalaryRecord, DentalMaterialPurchase,
    PharmacyPurchase, PharmacyPurchaseItem, SupplierLedger, WebsiteAppointmentRequest, AuditLog
)

def reset_data():
    print("Deleting all clinical and financial data...")
    
    # Financial data
    BillingItem.objects.all().delete()
    Billing.objects.all().delete()
    Payment.objects.all().delete()
    MedicinePurchase.objects.all().delete()
    Expense.objects.all().delete()
    DoctorSalaryRecord.objects.all().delete()
    DentalMaterialPurchase.objects.all().delete()
    PharmacyPurchase.objects.all().delete()
    PharmacyPurchaseItem.objects.all().delete()
    SupplierLedger.objects.all().delete()
    
    # Clinical data
    PrescriptionItem.objects.all().delete()
    Prescription.objects.all().delete()
    TreatmentRecord.objects.all().delete()
    ClinicalNotes.objects.all().delete()
    
    # Visit and Appointments
    Visit.objects.all().delete()
    Appointment.objects.all().delete()
    WebsiteAppointmentRequest.objects.all().delete()
    
    # Logs
    CommunicationLog.objects.all().delete()
    AuditLog.objects.all().delete()
    
    # Patients
    Patient.objects.all().delete()
    
    print("Database reset successfully! Masters (Doctors, Medicines, Treatments, Users) are preserved.")

if __name__ == "__main__":
    reset_data()
