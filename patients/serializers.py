from rest_framework import serializers
from .models import (
    Company, Branch,
    Patient, Appointment, TreatmentMaster, Visit, TreatmentRecord, Payment, Prescription,
    PrescriptionItem, Doctor, DoctorSchedule, DoctorScheduleProposal, DoctorDateOverride,
    InAppNotification, Tooth, ClinicalNotes, ToothMaster, MedicineMaster, Billing, BillingItem,
    PatientGroup, Transaction, Supplier, PharmacyPurchase, PharmacyPurchaseItem, MedicineStock,
    SupplierLedger, TaxSetting, CommunicationTemplate, LabHeader, Laboratory, LabTestMaster,
    LabTestParameter, LabPackage, DentalLaboratory, DentalLabWork, WebsiteAppointmentRequest,
    Staff, PatientLabOrder, PatientImage, StaffLeaveConfig, StaffBenefit, StaffInsurance, InvestigationMaster, PatientInvestigation, InvestigationAttachment
)
from django_mongodb_backend.fields.auto import ObjectIdAutoField

serializers.ModelSerializer.serializer_field_mapping[ObjectIdAutoField] = serializers.CharField

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'

class BranchSerializer(serializers.ModelSerializer):
    company_name = serializers.ReadOnlyField(source='company.name')
    class Meta:
        model = Branch
        fields = '__all__'

class StaffLeaveConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffLeaveConfig
        fields = '__all__'
        read_only_fields = ['staff']

class StaffBenefitSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffBenefit
        fields = '__all__'
        read_only_fields = ['staff']

class StaffInsuranceSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffInsurance
        fields = '__all__'
        read_only_fields = ['staff']

class TreatmentMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentMaster
        fields = '__all__'

class PatientImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientImage
        fields = '__all__'

class StaffSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    leave_configs = StaffLeaveConfigSerializer(many=True, read_only=True)
    benefits = StaffBenefitSerializer(many=True, read_only=True)
    insurance_policies = StaffInsuranceSerializer(many=True, read_only=True)
    active_insurance = serializers.SerializerMethodField()

    class Meta:
        model = Staff
        fields = '__all__'

    def get_active_insurance(self, obj):
        active = obj.insurance_policies.filter(status='Active', is_enabled=True).first()
        if active:
            return StaffInsuranceSerializer(active).data
        latest = obj.insurance_policies.first()
        if latest:
            return StaffInsuranceSerializer(latest).data
        return None

class DoctorSerializer(serializers.ModelSerializer):
    company_name = serializers.ReadOnlyField(source='company.name')
    primary_branch_name = serializers.ReadOnlyField(source='primary_branch.name')

    class Meta:
        model = Doctor
        fields = '__all__'

class DoctorScheduleSerializer(serializers.ModelSerializer):
    doctor_name = serializers.ReadOnlyField(source='doctor.name')
    branch_name = serializers.ReadOnlyField(source='branch.name')
    company_name = serializers.ReadOnlyField(source='company.name')
    created_by_username = serializers.SerializerMethodField()
    approved_by_username = serializers.SerializerMethodField()

    class Meta:
        model = DoctorSchedule
        fields = '__all__'

    def get_created_by_username(self, obj):
        from .security import resolve_username_by_id
        return resolve_username_by_id(getattr(obj, 'created_by_id', None))

    def get_approved_by_username(self, obj):
        from .security import resolve_username_by_id
        return resolve_username_by_id(getattr(obj, 'approved_by_id', None))


class DoctorScheduleProposalSerializer(serializers.ModelSerializer):
    doctor_name = serializers.ReadOnlyField(source='doctor.name')
    branch_name = serializers.ReadOnlyField(source='branch.name')
    company_name = serializers.ReadOnlyField(source='company.name')
    submitted_by_username = serializers.SerializerMethodField()
    reviewed_by_username = serializers.SerializerMethodField()

    class Meta:
        model = DoctorScheduleProposal
        fields = '__all__'

    def get_submitted_by_username(self, obj):
        from .security import resolve_username_by_id
        return resolve_username_by_id(getattr(obj, 'submitted_by_id', None))

    def get_reviewed_by_username(self, obj):
        from .security import resolve_username_by_id
        return resolve_username_by_id(getattr(obj, 'reviewed_by_id', None))


class DoctorDateOverrideSerializer(serializers.ModelSerializer):
    doctor_name = serializers.ReadOnlyField(source='doctor.name')
    branch_name = serializers.ReadOnlyField(source='branch.name')
    company_name = serializers.ReadOnlyField(source='company.name')
    created_by_username = serializers.SerializerMethodField()
    approved_by_username = serializers.SerializerMethodField()

    class Meta:
        model = DoctorDateOverride
        fields = '__all__'

    def get_created_by_username(self, obj):
        from .security import resolve_username_by_id
        return resolve_username_by_id(getattr(obj, 'created_by_id', None))

    def get_approved_by_username(self, obj):
        from .security import resolve_username_by_id
        return resolve_username_by_id(getattr(obj, 'approved_by_id', None))


class InAppNotificationSerializer(serializers.ModelSerializer):
    recipient_username = serializers.SerializerMethodField()

    class Meta:
        model = InAppNotification
        fields = '__all__'

    def get_recipient_username(self, obj):
        from .security import resolve_username_by_id
        return resolve_username_by_id(getattr(obj, 'recipient_id', None))

class TreatmentRecordSerializer(serializers.ModelSerializer):
    treatment_name = serializers.ReadOnlyField(source='treatment.name')
    class Meta:
        model = TreatmentRecord
        fields = '__all__'

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'

class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = '__all__'

class PrescriptionSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    patient_name = serializers.ReadOnlyField(source='patient.name')
    doctor_name = serializers.ReadOnlyField(source='doctor.name')

    class Meta:
        model = Prescription
        fields = [
            'id', 'patient', 'patient_name', 'visit', 'clinical_note',
            'doctor', 'doctor_name', 'notes', 'status', 'created_by',
            'created_at', 'items'
        ]

    def get_items(self, obj):
        from .models import PrescriptionItem
        items = PrescriptionItem.objects.filter(prescription=obj)
        return PrescriptionItemSerializer(items, many=True).data

class ClinicalNotesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicalNotes
        fields = '__all__'

class ToothSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tooth
        fields = '__all__'

class ToothMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToothMaster
        fields = '__all__'

class PatientGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientGroup
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
    doctor_name = serializers.ReadOnlyField(source='doctor.name')

    class Meta:
        model = Billing
        fields = [
            'id', 'patient', 'patient_name', 'patient_phone',
            'visit', 'clinical_note', 'doctor', 'doctor_name',
            'bill_type', 'is_invoice', 'notes', 'created_by',
            'total_amount', 'paid_amount', 'cash_received', 'balance_returned', 'balance_amount',
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
    branch_name = serializers.ReadOnlyField(source='branch.name')
    company_name = serializers.ReadOnlyField(source='company.name')
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
            'company', 'company_name',
            'branch', 'branch_name',
            'date', 'time', 'time_formatted',
            'status', 'display_status',
            'rescheduled_to_date', 'rescheduled_to_time',
            'visit', 'clinical_notes',
            'is_virtual', 'meeting_link', 'telemedicine_notes'
        ]

    def get_time_formatted(self, obj):
        if obj.time:
            if isinstance(obj.time, str):
                try:
                    from datetime import datetime
                    t = datetime.strptime(obj.time[:5], "%H:%M").time()
                    return t.strftime("%I:%M %p")
                except Exception:
                    return obj.time
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
    patient_type_name = serializers.CharField(source='patient_type.name', read_only=True, default='')

    class Meta:
        model = Patient
        fields = [
            'id', 'name', 'phone', 'dob', 'age', 'gender', 'status', 'patient_type', 'patient_type_name', 'groups', 'group_ids', 'notes',
            'address', 'pincode',
            'created_at', 'total_balance', 'last_visit', 'consultation_fee', 'balance_adjustment', 'doctor'
        ]
        read_only_fields = ['total_balance', 'balance_adjustment', 'last_visit', 'groups', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.dob:
            from datetime import date
            today = date.today()
            birth_date = instance.dob
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            data['age'] = max(0, age)
        return data

    def validate_dob(self, value):
        if value:
            from datetime import date
            if value > date.today():
                raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate_age(self, value):
        if value is not None:
            if value < 0:
                raise serializers.ValidationError("Age cannot be negative.")
            if value > 150:
                raise serializers.ValidationError("Please enter a valid age (0 - 150).")
        return value

    def validate_pincode(self, value):
        if value:
            val_str = str(value).strip()
            import re
            if not re.match(r'^\d{6}$', val_str):
                raise serializers.ValidationError("Pincode must be a 6-digit numeric value.")
            return val_str
        return value

    def update(self, instance, validated_data):
        group_ids = validated_data.pop('group_ids', None)
        dob = validated_data.get('dob', instance.dob)
        if dob:
            from datetime import date
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            validated_data['age'] = max(0, age)
        instance = super().update(instance, validated_data)
        if group_ids is not None:
            instance.groups.set(group_ids)
        return instance

    def create(self, validated_data):
        group_ids = validated_data.pop('group_ids', None)
        dob = validated_data.get('dob')
        if dob:
            from datetime import date
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            validated_data['age'] = max(0, age)
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


class InvestigationMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestigationMaster
        fields = '__all__'


class InvestigationAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = InvestigationAttachment
        fields = ['id', 'investigation', 'file', 'file_url', 'file_name', 'file_type', 'file_size', 'file_data', 'uploaded_at']

    def get_file_url(self, obj):
        if obj.file:
            try:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.file.url)
                return obj.file.url
            except Exception:
                return ""
        return ""


class PatientInvestigationSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()
    doctor_name = serializers.ReadOnlyField(source='doctor.name')
    patient_name = serializers.ReadOnlyField(source='patient.name')
    master_name = serializers.ReadOnlyField(source='investigation_master.name')

    class Meta:
        model = PatientInvestigation
        fields = '__all__'

    def get_attachments(self, obj):
        try:
            return InvestigationAttachmentSerializer(obj.attachments.all(), many=True, context=self.context).data
        except Exception:
            return []
