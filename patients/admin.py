from django.contrib import admin
from .models import Staff, MedicineMaster, Prescription, PrescriptionItem, Billing, BillingItem, TreatmentMaster, Patient, LabHeader, Laboratory, LabTestMaster, LabTestParameter

@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'user')

@admin.register(MedicineMaster)
class MedicineMasterAdmin(admin.ModelAdmin):
    list_display = ('name', 'stock_quantity', 'purchase_rate', 'sales_rate', 'low_stock_threshold')
    search_fields = ('name',)

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'gender', 'age')
    search_fields = ('name', 'phone')

admin.site.register(Prescription)
admin.site.register(PrescriptionItem)
admin.site.register(Billing)
admin.site.register(BillingItem)
admin.site.register(TreatmentMaster)
admin.site.register(LabHeader)
admin.site.register(Laboratory)
admin.site.register(LabTestMaster)
admin.site.register(LabTestParameter)
