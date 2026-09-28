from rest_framework import serializers
from .models import Patient, Appointment, TreatmentMaster, Visit, TreatmentRecord, Payment, Prescription, PrescriptionItem, Doctor, DoctorSchedule, Tooth, ClinicalNotes, ToothMaster, MedicineMaster, Billing, BillingItem, PatientGroup, Transaction, Supplier, PharmacyPurchase, PharmacyPurchaseItem, MedicineStock, SupplierLedger, TaxSetting, CommunicationTemplate, LabHeader, Laboratory, LabTestMaster, LabTestParameter, LabPackage, DentalLaboratory, DentalLabWork, WebsiteAppointmentRequest, Staff, PatientLabOrder, PatientImage, Company, AuditLog
from django_mongodb_backend.fields.auto import ObjectIdAutoField

serializers.ModelSerializer.serializer_field_mapping[ObjectIdAutoField] = serializers.CharField


class ToothMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToothMaster
        fields = '__all__'

class PatientGroupSerializer(serializers.ModelSerializer):
    patient_count = serializers.IntegerField(source='patients.count', read_only=True)
    class Meta:
        model = PatientGroup
        fields = ['id', 'name', 'description', 'created_at', 'patient_count']

class ToothSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tooth
        fields = '__all__'

class TreatmentMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentMaster
        fields = '__all__'

class ClinicalNotesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicalNotes
        fields = [
            'id', 'appointment', 'selected_teeth', 'complaints', 'observations', 'investigations', 
            'diagnosis', 'medical_history', 'dental_history', 'allergies', 'ongoing_medications', 
            'chief_complaint', 'patient_type', 'notes', 'treatments', 'treatment_plan', 
            'follow_up_date', 'follow_up_note', 'follow_up_status', 'created_at'
        ]

class TreatmentRecordSerializer(serializers.ModelSerializer):
    treatment_name = serializers.CharField(source='treatment.name', read_only=True)
    class Meta:
        model = TreatmentRecord
        fields = ['id', 'visit', 'treatment', 'treatment_name', 'tooth_number', 'price']

class PatientImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientImage
        fields = '__all__'

class PaymentSerializer(serializers.ModelSerializer):
    patient_name = serializers.ReadOnlyField(source='patient.name')
    patient_phone = serializers.ReadOnlyField(source='patient.phone')

    class Meta:
        model = Payment
        fields = [
            'id', 'patient', 'patient_name', 'patient_phone',
            'visit', 'total_amount', 'paid_amount', 'balance_amount',
            'payment_method', 'status', 'created_at'
        ]
        read_only_fields = ['balance_amount', 'status']

class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = ['id', 'prescription', 'medicine_name', 'dosage', 'duration', 'notes', 'quantity', 'unit_price', 'is_billed', 'is_dispensed']

class PrescriptionSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    patient_name = serializers.ReadOnlyField(source='patient.name')
    patient_phone = serializers.ReadOnlyField(source='patient.phone')
    doctor_name = serializers.ReadOnlyField(source='doctor.name')

    class Meta:
        model = Prescription
        fields = '__all__'

    def get_items(self, obj):
        from .models import PrescriptionItem
        items = PrescriptionItem.objects.filter(prescription=obj)
        return PrescriptionItemSerializer(items, many=True).data


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'

class DoctorSerializer(serializers.ModelSerializer):
    company_name = serializers.ReadOnlyField(source='company.name')
    class Meta:
        model = Doctor
        fields = '__all__'

class StaffSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    company_name = serializers.ReadOnlyField(source='company.name')
    doctor_name = serializers.ReadOnlyField(source='doctor_profile.name')

    class Meta:
        model = Staff
        fields = '__all__'

class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    company_name = serializers.ReadOnlyField(source='company.name')

    class Meta:
        model = AuditLog
        fields = '__all__'

class DoctorScheduleSerializer(serializers.ModelSerializer):
    doctor_name = serializers.ReadOnlyField(source='doctor.name')
    class Meta:
        model = DoctorSchedule
        fields = '__all__'

class VisitSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    patient_phone = serializers.CharField(source='patient.phone', read_only=True)
    # Use SerializerMethodField for all reverse relations - MongoDB ObjectId compat
    treatment_records = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    prescriptions = serializers.SerializerMethodField()
    clinical_notes = serializers.SerializerMethodField()

    class Meta:
        model = Visit
        fields = [
            'id', 'patient', 'patient_name', 'patient_phone',
            'appointment', 'created_at',
            'treatment_records', 'payment', 'prescriptions', 'clinical_notes'
        ]

    def get_treatment_records(self, obj):
        from .models import TreatmentRecord
        records = TreatmentRecord.objects.filter(visit=obj)
        return TreatmentRecordSerializer(records, many=True).data

    def get_payment(self, obj):
        from .models import Payment
        pay = Payment.objects.filter(visit=obj).first()
        return PaymentSerializer(pay).data if pay else None

    def get_prescriptions(self, obj):
        from .models import Prescription
        rxs = Prescription.objects.filter(visit=obj)
        return PrescriptionSerializer(rxs, many=True).data

    def get_clinical_notes(self, obj):
        from .models import ClinicalNotes
        if obj.appointment_id:
            notes = ClinicalNotes.objects.filter(appointment_id=obj.appointment_id).first()
            return ClinicalNotesSerializer(notes).data if notes else None
        return None


class MedicineMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineMaster
        fields = '__all__'

class BillingItemSerializer(serializers.ModelSerializer):
    treatment_name = serializers.ReadOnlyField(source='treatment.name')
    class Meta:
        model = BillingItem
        fields = ['id', 'billing', 'treatment', 'treatment_name', 'qty', 'price']

class BillingSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    patient_name = serializers.ReadOnlyField(source='patient.name')
    patient_phone = serializers.ReadOnlyField(source='patient.phone')

    class Meta:
        model = Billing
        fields = [
            'id', 'patient', 'patient_name', 'patient_phone',
            'visit', 'clinical_note',
            'total_amount', 'paid_amount', 'balance_amount',
            'payment_method', 'status', 'created_at', 'items'
        ]

    def get_items(self, obj):
        from .models import BillingItem
        items = BillingItem.objects.filter(billing=obj)
        return BillingItemSerializer(items, many=True).data


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.ReadOnlyField(source='patient.name')
    patient_phone = serializers.ReadOnlyField(source='patient.phone')
    patient_balance = serializers.ReadOnlyField(source='patient.total_balance')
    doctor_name = serializers.ReadOnlyField(source='doctor.name')
    doctor_color = serializers.ReadOnlyField(source='doctor.color')
    time_formatted = serializers.SerializerMethodField()
    # Use SerializerMethodField instead of direct relation for MongoDB ObjectId compatibility
    visit = serializers.SerializerMethodField()
    clinical_notes = serializers.SerializerMethodField()
    display_status = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'patient', 'patient_name', 'patient_phone', 'patient_balance',
            'doctor', 'doctor_name', 'doctor_color',
            'date', 'time', 'time_formatted',
            'status', 'display_status',
            'rescheduled_to_date', 'rescheduled_to_time',
            'visit', 'clinical_notes',
            'is_virtual', 'meeting_link', 'telemedicine_notes'
        ]

    def get_time_formatted(self, obj):
        if obj.time:
            return obj.time.strftime("%I:%M %p")
        return "--:--"

    def get_visit(self, obj):
        """Manually fetch visit to avoid MongoDB reverse relation issues."""
        from .models import Visit
        try:
            visit = Visit.objects.filter(appointment=obj).first()
            if visit:
                return VisitSerializer(visit).data
        except Exception:
            pass
        return None

    def get_clinical_notes(self, obj):
        """Manually fetch clinical notes to avoid MongoDB reverse relation issues."""
        from .models import ClinicalNotes
        try:
            notes = ClinicalNotes.objects.filter(appointment=obj).first()
            if notes:
                return ClinicalNotesSerializer(notes).data
        except Exception:
            pass
        return None

    def get_display_status(self, obj):
        """User-facing status label for the Appointments page."""
        from datetime import date
        today = date.today()
        # Always honour these explicit statuses regardless of date
        if obj.status in ('Completed', 'Missed', 'Rescheduled', 'Cancelled', 'Follow-up'):
            return obj.status
        if obj.date > today and obj.status == 'Scheduled':
            return 'Upcoming'
        if obj.date == today:
            return obj.status  # Scheduled / Waiting / Engaged
        if obj.date < today and obj.status not in ('Completed', 'Rescheduled', 'Cancelled', 'Follow-up'):
            return 'Missed'
        return obj.status

class PatientSerializer(serializers.ModelSerializer):
    total_balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    last_visit = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    group_ids = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)

    class Meta:
        model = Patient
        fields = [
            'id', 'name', 'phone', 'dob', 'age', 'gender', 'status', 'groups', 'group_ids', 'notes',
            'created_at', 'total_balance', 'last_visit', 'consultation_fee', 'balance_adjustment', 'doctor'
        ]
        read_only_fields = ['total_balance', 'balance_adjustment', 'last_visit', 'groups', 'created_at']

    def update(self, instance, validated_data):
        group_ids = validated_data.pop('group_ids', None)
        instance = super().update(instance, validated_data)
        if group_ids is not None:
            instance.groups.set(group_ids)
        return instance

    def create(self, validated_data):
        group_ids = validated_data.pop('group_ids', None)
        instance = super().create(validated_data)
        if group_ids is not None:
            instance.groups.set(group_ids)
        return instance

    def get_groups(self, obj):
        try:
            return PatientGroupSerializer(obj.groups.all(), many=True).data
        except Exception:
            return []

    def get_last_visit(self, obj):
        last_visit = obj.visits.order_by('-created_at').first()
        if last_visit:
            return VisitSerializer(last_visit).data
        return None
class TransactionSerializer(serializers.ModelSerializer):
    patient_name = serializers.ReadOnlyField(source='patient.name')
    doctor_name = serializers.ReadOnlyField(source='doctor.name')

    class Meta:
        model = Transaction
        fields = '__all__'

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'contact_person', 'phone', 'email', 'address', 'total_balance']

class MedicineStockSerializer(serializers.ModelSerializer):
    medicine_name = serializers.ReadOnlyField(source='medicine.name')
    class Meta:
        model = MedicineStock
        fields = '__all__'

class PharmacyPurchaseItemSerializer(serializers.ModelSerializer):
    medicine_name = serializers.ReadOnlyField(source='medicine.name')
    class Meta:
        model = PharmacyPurchaseItem
        fields = '__all__'

class PharmacyPurchaseSerializer(serializers.ModelSerializer):
    items = PharmacyPurchaseItemSerializer(many=True, read_only=True)
    supplier_name = serializers.ReadOnlyField(source='supplier.name')
    class Meta:
        model = PharmacyPurchase
        fields = '__all__'
class SupplierLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierLedger
        fields = '__all__'

class TaxSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxSetting
        fields = '__all__'

class CommunicationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationTemplate
        fields = '__all__'

class LabHeaderSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabHeader
        fields = '__all__'

class LaboratorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Laboratory
        fields = '__all__'

class LabTestParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTestParameter
        fields = '__all__'

class LabTestMasterSerializer(serializers.ModelSerializer):
    parameters = serializers.SerializerMethodField()
    class Meta:
        model = LabTestMaster
        fields = '__all__'

    def get_parameters(self, obj):
        try:
            return LabTestParameterSerializer(obj.parameters.all(), many=True).data
        except Exception:
            return []

class LabPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabPackage
        fields = '__all__'

class DentalLaboratorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DentalLaboratory
        fields = '__all__'

class DentalLabWorkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DentalLabWork
        fields = '__all__'

class WebsiteAppointmentRequestSerializer(serializers.ModelSerializer):
    doctor_name = serializers.ReadOnlyField(source='preferred_doctor.name')
    class Meta:
        model = WebsiteAppointmentRequest
        fields = '__all__'

class PatientLabOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientLabOrder
        fields = '__all__'
