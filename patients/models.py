from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth.models import User

class Company(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

class Branch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, default="India")
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'code')

    def __str__(self):
        return f"{self.name} [{self.code}] - {self.company.name}"

class Doctor(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='doctors')
    primary_branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_doctors')
    assigned_branches = models.JSONField(default=list, blank=True)
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=20, default="#000000")
    phone = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    specialization = models.CharField(max_length=255, blank=True, null=True)
    qualification = models.CharField(max_length=255, blank=True, null=True)
    experience_years = models.IntegerField(default=0)
    availability = models.CharField(max_length=255, blank=True, null=True)
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    slot_duration = models.IntegerField(default=30) # in minutes (e.g. 15, 20, 30, 45, 60)

    def is_branch_assigned(self, branch):
        if not branch:
            return False
        b_id = str(getattr(branch, 'id', branch))
        if self.primary_branch_id and str(self.primary_branch_id) == b_id:
            return True
        return b_id in [str(x) for x in (self.assigned_branches or [])]

    def __str__(self):
        return self.name

class DoctorSchedule(models.Model):
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    STATUS_CHOICES = [
        ('APPROVED', 'Approved'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('REJECTED', 'Rejected'),
        ('WITHDRAWN', 'Withdrawn'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='doctor_schedules')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name='doctor_schedules')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration = models.IntegerField(default=30) # in minutes
    session_name = models.CharField(max_length=100, blank=True, default='Regular Session')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='APPROVED')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_schedules')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_schedules')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.doctor.name} - {self.get_day_of_week_display()} ({self.start_time} - {self.end_time})"


class DoctorScheduleProposal(models.Model):
    STATUS_CHOICES = [
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('WITHDRAWN', 'Withdrawn'),
    ]
    PROPOSAL_TYPES = [
        ('RECURRING_SCHEDULE', 'Recurring Weekly Schedule'),
        ('DATE_OVERRIDE', 'Date-Specific Change'),
        ('LEAVE', 'Doctor Leave / Blocked Period'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='schedule_proposals')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name='doctor_proposals')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='schedule_proposals')
    proposal_type = models.CharField(max_length=30, choices=PROPOSAL_TYPES, default='RECURRING_SCHEDULE')
    slot_duration = models.IntegerField(default=30)
    proposed_slots = models.JSONField(default=list, blank=True)
    # proposed_slots: [ { "day_of_week": 0, "start_time": "09:00", "end_time": "13:00", "session_name": "Morning" }, ... ]
    date_exceptions = models.JSONField(default=list, blank=True)
    # date_exceptions: [ { "date": "2026-11-05", "override_type": "LEAVE", "start_time": null, "end_time": null, "reason": "Conference", "leave_type": "Casual Leave" }, ... ]
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='PENDING_APPROVAL')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='submitted_proposals')
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_proposals')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Proposal for {self.doctor.name} - {self.proposal_type} [{self.status}]"


class DoctorDateOverride(models.Model):
    OVERRIDE_CHOICES = [
        ('AVAILABLE', 'Available (Working Day)'),
        ('UNAVAILABLE', 'Unavailable'),
        ('LEAVE', 'On Leave'),
        ('BLOCKED', 'Blocked Slot/Period'),
    ]
    STATUS_CHOICES = [
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('WITHDRAWN', 'Withdrawn'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='date_overrides')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='doctor_overrides')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='date_overrides')
    date = models.DateField()
    override_type = models.CharField(max_length=20, choices=OVERRIDE_CHOICES, default='UNAVAILABLE')
    start_time = models.TimeField(null=True, blank=True) # None indicates entire day
    end_time = models.TimeField(null=True, blank=True)
    slot_duration = models.IntegerField(default=30)
    reason = models.CharField(max_length=255, blank=True, default='')
    leave_type = models.CharField(max_length=100, blank=True, default='') # Links to StaffLeaveConfig types
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='APPROVED')
    proposal = models.ForeignKey(DoctorScheduleProposal, on_delete=models.SET_NULL, null=True, blank=True, related_name='date_overrides')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_date_overrides')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_date_overrides')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'start_time']

    def __str__(self):
        return f"{self.doctor.name} - {self.date} [{self.override_type}] ({self.status})"


class InAppNotification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, default='SYSTEM')
    is_read = models.BooleanField(default=False)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification to {self.recipient.username}: {self.title}"


import re

def normalize_phone(phone_str):
    if not phone_str:
        return ''
    digits = re.sub(r'\D', '', str(phone_str))
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits

def normalize_email(email_str):
    if not email_str:
        return ''
    return str(email_str).strip().lower()

class Staff(models.Model):
    ROLES = [
        ('Admin', 'Admin'),
        ('Doctor', 'Doctor'),
        ('Pharmacist', 'Pharmacist'),
        ('Receptionist', 'Receptionist'),
    ]
    STAFF_LEVEL_CHOICES = [
        ('Senior', 'Senior'),
        ('Junior', 'Junior'),
        ('Trainee', 'Trainee'),
        ('Intern', 'Intern'),
        ('Consultant', 'Consultant'),
        ('Other', 'Other'),
    ]
    staff_level = models.CharField(max_length=50, choices=STAFF_LEVEL_CHOICES, default='Junior', null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='staff_members')
    primary_branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_staff')
    accessible_branches = models.JSONField(default=list, blank=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile', null=True, blank=True)
    doctor_profile = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_account')
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=50, default='Staff')
    phone = models.CharField(max_length=20, null=True, blank=True, unique=True)
    email = models.CharField(max_length=255, null=True, blank=True, unique=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=10, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, default='Active')
    emergency_contact = models.CharField(max_length=100, null=True, blank=True)
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    incentive = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    permissions = models.JSONField(default=list, blank=True, null=True)
    additional_details = models.JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.email:
            norm_e = normalize_email(self.email)
            self.email = norm_e if norm_e else None
        else:
            self.email = None
            
        if self.phone:
            norm_p = normalize_phone(self.phone)
            self.phone = norm_p if norm_p else None
        else:
            self.phone = None
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.role})"

class PatientGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Patient(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='patients')
    registration_branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='registered_patients')
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15, blank=True, null=True)
    dob = models.DateField(null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    pincode = models.CharField(max_length=10, null=True, blank=True)
    status = models.CharField(max_length=10, default='Active')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, null=True, blank=True, related_name='patients')
    patient_type = models.ForeignKey('PatientTypeMaster', on_delete=models.SET_NULL, null=True, blank=True, related_name='patients')
    groups = models.ManyToManyField(PatientGroup, related_name='patients', blank=True)
    notes = models.TextField(null=True, blank=True)
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Cumulative administrative write-off / bad-debt adjustment (reduces displayed balance)
    balance_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def total_balance(self):
        """Net balance across both Billing and legacy Payment models. Returns 0 minimum.
        Excludes pharmacy-related bills as per 'no credit for medicines' rule.
        Subtracts balance_adjustment (waivers / manual corrections).
        """
        from .models import Billing, Payment
        
        # 1. Total Billed from clinical Billing records (excluding Pharmacy, Lab, and Cancelled)
        billings = Billing.objects.filter(patient=self, bill_type='Clinical').exclude(status='Cancelled').order_by('created_at')
        
        # Find if any bills carried forward a prior balance
        carry_forward_dates = []
        for b in billings:
            if b.items.filter(treatment__name='Outstanding balance (brought forward)').exists():
                carry_forward_dates.append(b.created_at)
                
        latest_carry_date = max(carry_forward_dates) if carry_forward_dates else None
        
        b_total = 0.0
        b_paid = 0.0
        for b in billings:
            if latest_carry_date and b.created_at < latest_carry_date:
                # Prior bill whose balance was carried forward into a newer bill.
                # Treat it as fully paid here to prevent double-counting.
                b_total += float(b.total_amount)
                b_paid += float(b.total_amount)
            else:
                b_total += float(b.total_amount)
                b_paid += float(b.paid_amount)
        
        # 2. Add legacy Payment records that are NOT accounted for in Billing
        # A Payment is "legacy/independent" if its visit has no related Billing record
        independent_payments = Payment.objects.filter(
            patient=self
        ).exclude(visit__billings__isnull=False).exclude(status='Cancelled')
        
        p_total = independent_payments.aggregate(total=Sum('total_amount'))['total'] or 0
        p_paid = independent_payments.aggregate(total=Sum('paid_amount'))['total'] or 0
        
        net = (b_total + float(p_total)) - (b_paid + float(p_paid))
        adj = float(self.balance_adjustment or 0)
        return max(0.0, max(0.0, net) - adj)

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('Scheduled', 'Scheduled'),
        ('Waiting', 'Waiting'),
        ('Engaged', 'Engaged'),
        ('Completed', 'Completed'),
        ('Missed', 'Missed'),
        ('Rescheduled', 'Rescheduled'),
        ('Follow-up', 'Follow-up'),
        ('Cancelled', 'Cancelled'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='appointments')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name='appointments')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Scheduled')
    rescheduled_to_date = models.DateField(null=True, blank=True)
    rescheduled_to_time = models.TimeField(null=True, blank=True)
    
    # Telemedicine fields
    is_virtual = models.BooleanField(default=False)
    meeting_link = models.CharField(max_length=500, blank=True, null=True)
    telemedicine_notes = models.TextField(blank=True, null=True)
    duration_minutes = models.IntegerField(default=30)

    def __str__(self):
        return f"{self.patient.name} - {self.date} ({self.status})"

class ToothMaster(models.Model):
    TYPE_CHOICES = [
        ('incisor', 'Incisor'),
        ('canine', 'Canine'),
        ('premolar', 'Premolar'),
        ('molar', 'Molar'),
    ]
    CATEGORY_CHOICES = [
        ('permanent', 'Permanent'),
        ('primary', 'Primary'),
    ]
    POSITION_CHOICES = [
        ('upper_right', 'Upper Right'),
        ('upper_left', 'Upper Left'),
        ('lower_left', 'Lower Left'),
        ('lower_right', 'Lower Right'),
    ]
    
    tooth_number = models.IntegerField(unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    position = models.CharField(max_length=20, choices=POSITION_CHOICES)

    def __str__(self):
        return f"{self.tooth_number} ({self.type})"

class Tooth(models.Model):
    # Keeping for legacy compatibility if needed, but renaming related fields
    number = models.IntegerField(unique=True)

    def __str__(self):
        return f"Tooth {self.number}"

class TreatmentMaster(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    fee_type = models.CharField(max_length=100, default='Treatment') # e.g., Consultation, X-Ray, Surgery
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.name

class DiagnosisMaster(models.Model):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=100, default='General')
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

class ExaminationMaster(models.Model):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=100, default='General')
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

class ToothConditionMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=50, default='#3b82f6')
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class Visit(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='visits')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='visit', null=True, blank=True)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Visit for {self.patient.name} on {self.created_at.date()}"

class DropdownMaster(models.Model):
    TYPES = [
        ('complaint', 'Complaint'),
        ('observation', 'Observation'),
        ('investigation', 'Investigation'),
        ('diagnosis', 'Diagnosis'),
        ('treatment', 'Treatment'),
        ('medical_history', 'Medical History'),
        ('payment_method', 'Payment Method'),
        ('document_type', 'Document Type'),
    ]
    type = models.CharField(max_length=50, choices=TYPES)
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.type}: {self.name}"

class CommunicationTemplate(models.Model):
    category = models.CharField(max_length=100)
    type = models.CharField(max_length=100)
    text = models.TextField()
    email_enabled = models.BooleanField(default=False)
    sms_enabled = models.BooleanField(default=True)
    whatsapp_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.category} - {self.type}"

class TaxSetting(models.Model):
    name = models.CharField(max_length=100, unique=True)
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

class ClinicalNotes(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='clinical_notes', null=True, blank=True)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='clinical_notes')
    selected_teeth = models.JSONField(default=list, blank=True)
    chart_conditions = models.JSONField(default=dict, blank=True)
    tooth_details = models.JSONField(default=dict, blank=True)
    vitals = models.JSONField(default=dict, blank=True)
    complaints = models.JSONField(default=list, blank=True)
    observations = models.JSONField(default=list, blank=True)
    investigations = models.JSONField(default=list, blank=True)
    diagnosis = models.JSONField(default=list, blank=True)
    medical_history = models.JSONField(default=list, blank=True)
    dental_history = models.JSONField(default=list, blank=True)
    allergies = models.JSONField(default=list, blank=True)
    ongoing_medications = models.JSONField(default=list, blank=True)
    chief_complaint = models.TextField(blank=True, null=True)
    patient_type = models.CharField(max_length=50, default='Adult')
    notes = models.TextField(blank=True, null=True)
    treatments = models.ManyToManyField(TreatmentMaster, blank=True, related_name='clinical_notes')
    treatment_plan = models.TextField(blank=True, null=True)
    follow_up_date = models.DateField(blank=True, null=True)
    follow_up_note = models.TextField(blank=True, null=True)
    follow_up_status = models.CharField(max_length=20, default='Pending') # Pending, Completed, Missed
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Clinical Notes for Appointment {self.appointment.id}"

class TreatmentRecord(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='treatment_records')
    treatment = models.ForeignKey(TreatmentMaster, on_delete=models.PROTECT)
    tooth_number = models.CharField(max_length=255, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2) # Copied from master
    fee_type = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, default='Completed')
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_records')

    def __str__(self):
        return f"{self.treatment.name} for Visit {self.visit.id}"

class PatientImage(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='images')
    visit = models.ForeignKey(Visit, on_delete=models.SET_NULL, null=True, blank=True, related_name='images')
    image = models.FileField(upload_to='patient_images/%Y/%m/', null=True, blank=True)
    file_name = models.CharField(max_length=255, blank=True, null=True)
    tooth_number = models.CharField(max_length=50, blank=True, null=True)
    image_data = models.TextField(blank=True, null=True) # Base64 fallback
    image_type = models.CharField(max_length=50, default='RVG') # RVG, Camera, Document
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.image_type} for {self.patient.name}"

class Payment(models.Model):
    # Keep Payment for simple backward compatibility if needed, but focus on Bill
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Partial', 'Partial'),
        ('Paid', 'Paid'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Card', 'Card'),
        ('UPI', 'UPI'),
        ('Cheque', 'Cheque'),
        ('Insurance', 'Insurance'),
        ('Online', 'Online'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='payments')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='payments')
    visit = models.OneToOneField(Visit, on_delete=models.CASCADE, related_name='payment')
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_received = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    balance_returned = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='Cash', blank=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    transaction_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.balance_amount = self.total_amount - self.paid_amount
        if self.paid_amount > self.total_amount and self.total_amount >= 0:
            self.status = 'Advance'
        elif self.paid_amount <= 0:
            self.status = 'Pending'
        elif self.paid_amount < self.total_amount:
            self.status = 'Partial'
        else:
            self.status = 'Paid'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment for {self.patient.name} - {self.total_amount}"

class Billing(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='billings')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='billings')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='billings')
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='billings', null=True, blank=True)
    clinical_note = models.ForeignKey(ClinicalNotes, on_delete=models.SET_NULL, null=True, blank=True)
    # Direct doctor FK for accurate revenue tracking (replaces visit→appointment→doctor chain)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='billings')
    BILL_TYPES = [
        ('Clinical', 'Clinical'),
        ('Pharmacy', 'Pharmacy'),
    ]
    bill_type = models.CharField(max_length=20, choices=BILL_TYPES, default='Clinical')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_received = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    balance_returned = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=50, default='Cash')
    status = models.CharField(max_length=20, default='Pending')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_invoice = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.balance_amount = self.total_amount - self.paid_amount
        if self.paid_amount > self.total_amount and self.total_amount >= 0:
            self.status = 'Advance'
        elif self.paid_amount <= 0:
            self.status = 'Pending'
        elif self.paid_amount < self.total_amount:
            self.status = 'Partial'
        else:
            self.status = 'Paid'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Billing #{self.id} for {self.patient.name}"

class BillingItem(models.Model):
    billing = models.ForeignKey(Billing, on_delete=models.CASCADE, related_name='items')
    treatment = models.ForeignKey(TreatmentMaster, on_delete=models.PROTECT)
    qty = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.treatment.name} (x{self.qty}) for Billing {self.billing.id}"


class Prescription(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='prescriptions')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='prescriptions')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='prescriptions', null=True, blank=True)
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='prescriptions', null=True, blank=True)
    clinical_note = models.ForeignKey(ClinicalNotes, on_delete=models.SET_NULL, null=True, blank=True)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True) # Global notes
    status = models.CharField(max_length=20, choices=[('PENDING', 'Pending'), ('BILLED', 'Billed')], default='PENDING')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Rx #{self.id} for {self.patient.name}"

class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='items')
    medicine_name = models.CharField(max_length=255)
    dosage = models.CharField(max_length=100, help_text="e.g. 1-0-1")
    duration = models.CharField(max_length=100, help_text="e.g. 5 days")
    notes = models.CharField(max_length=255, blank=True)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_billed = models.BooleanField(default=False)
    is_dispensed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.medicine_name} - {self.dosage}"

class MedicineMaster(models.Model):
    name = models.CharField(max_length=255)
    dosage = models.CharField(max_length=100, blank=True) # e.g. 500mg
    frequency = models.CharField(max_length=100, blank=True) # e.g. 1-0-1
    purchase_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sales_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=10)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class MedicinePurchase(models.Model):
    medicine = models.ForeignKey(MedicineMaster, on_delete=models.CASCADE, related_name='purchases')
    supplier = models.CharField(max_length=255, blank=True, null=True)
    quantity = models.IntegerField()
    purchase_rate = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateField(null=True, blank=True)
    currently_paying = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        if not self.total_amount:
            from decimal import Decimal
            self.total_amount = Decimal(str(self.purchase_rate)) * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Purchase: {self.medicine.name} (x{self.quantity}) from {self.supplier}"

class Supplier(models.Model):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    total_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class SupplierLedger(models.Model):
    ENTRY_TYPES = [
        ('Old Balance', 'Opening/Old Balance'),
        ('Payment', 'Payment Made'),
        ('Adjustment', 'Balance Adjustment'),
    ]
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='Old Balance')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.entry_type} - {self.amount} ({self.supplier.name})"

class PharmacyPurchase(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchases')
    invoice_no = models.CharField(max_length=100, blank=True, null=True)
    purchase_date = models.DateField(default=timezone.now)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Inv: {self.invoice_no} - {self.supplier.name}"

class PharmacyPurchaseItem(models.Model):
    purchase = models.ForeignKey(PharmacyPurchase, on_delete=models.CASCADE, related_name='items')
    medicine = models.ForeignKey(MedicineMaster, on_delete=models.CASCADE)
    batch_no = models.CharField(max_length=100)
    expiry_date = models.DateField()
    qty = models.IntegerField()
    free_qty = models.IntegerField(default=0)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.medicine.name} ({self.batch_no})"

class MedicineStock(models.Model):
    medicine = models.ForeignKey(MedicineMaster, on_delete=models.CASCADE, related_name='batches')
    batch_no = models.CharField(max_length=100)
    expiry_date = models.DateField()
    quantity = models.IntegerField(default=0)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('medicine', 'batch_no')

    def __str__(self):
        return f"{self.medicine.name} - Batch {self.batch_no} ({self.quantity})"

class PreBooking(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Booked', 'Booked'),
        ('Missed', 'Missed'),
    ]
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    expected_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.phone}"

class WebsiteAppointmentRequest(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    preferred_date = models.DateField()
    preferred_time = models.TimeField(null=True, blank=True)
    preferred_doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Request by {self.name} on {self.preferred_date} ({self.status})"

class CommunicationLog(models.Model):
    CHANNEL_CHOICES = [
        ('SMS', 'SMS'),
        ('WhatsApp', 'WhatsApp'),
        ('Both', 'Both'),
    ]
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='communication_logs')
    message = models.TextField()
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Msg to {self.patient.name} via {self.channel} on {self.sent_at.date()}"

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('Income', 'Income'),
        ('Expense', 'Expense'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='transactions')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=100) # e.g., Salary, Materials, Lab, Maintenance, Patient Payment
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    payment_method = models.CharField(max_length=50, default='Cash') # Cash, UPI, Card, Bank Transfer
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type}: {self.amount} ({self.category})"

class LabHeader(models.Model):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Laboratory(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class LabTestMaster(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True)
    category = models.CharField(max_length=100, default='General')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class LabTestParameter(models.Model):
    test = models.ForeignKey(LabTestMaster, on_delete=models.CASCADE, related_name='parameters')
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, blank=True)
    normal_range = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.name} for {self.test.name}"

class LabPackage(models.Model):
    name = models.CharField(max_length=255)
    tests = models.ManyToManyField(LabTestMaster, related_name='packages')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class DentalLaboratory(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class DentalLabWork(models.Model):
    name = models.CharField(max_length=255) # Work Name
    shade = models.CharField(max_length=100, blank=True)
    work_type = models.CharField(max_length=100, blank=True) # e.g. Veneers, Crown
    alloy_type = models.CharField(max_length=100, blank=True) # e.g. E-max, Zirconia
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    key = models.CharField(max_length=100, unique=True)
    color = models.CharField(max_length=20, default="#3b82f6")
    icon = models.CharField(max_length=50, default="Receipt")
    is_predefined = models.BooleanField(default=False)
    default_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Expense(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='expenses')
    branch_ref = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    title = models.CharField(max_length=255, default='Expense Entry')
    category = models.CharField(max_length=100) # Key or name of category
    category_ref = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    description = models.TextField(blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)
    paid_to = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.CharField(max_length=255, blank=True, null=True)
    payment_method = models.CharField(max_length=50, default='Cash')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    attachment_name = models.CharField(max_length=255, blank=True, null=True)
    attachment_data = models.TextField(blank=True, null=True) # Base64 or mock url
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(max_length=50, blank=True, null=True) # Weekly, Monthly, Yearly
    status = models.CharField(max_length=20, default='Paid') # Paid, Pending
    branch = models.CharField(max_length=100, default='Main Branch')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.amount} on {self.date}"

class DoctorSalary(models.Model):
    doctor = models.OneToOneField(Doctor, on_delete=models.CASCADE, related_name='salary_config')
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    incentive_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.doctor.name} - Config"

class DoctorSalaryRecord(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='salary_records')
    month = models.IntegerField()
    year = models.IntegerField()
    base_salary = models.DecimalField(max_digits=12, decimal_places=2)
    incentive = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    final_salary = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, default='Pending') # Pending, Paid
    payment_date = models.DateField(blank=True, null=True)
    payment_method = models.CharField(max_length=50, default='Bank Transfer')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.doctor.name} - {self.month}/{self.year} ({self.status})"

class DentalMaterial(models.Model):
    name = models.CharField(max_length=255, unique=True)
    quantity = models.IntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='materials')
    low_stock_threshold = models.IntegerField(default=5)
    last_purchased_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.name

class DentalMaterialPurchase(models.Model):
    material = models.ForeignKey(DentalMaterial, on_delete=models.CASCADE, related_name='purchases')
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.material.name} x {self.quantity} on {self.date}"

class AuditLog(models.Model):
    action = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} at {self.created_at}"


class ClinicProfile(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='clinic_profiles')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name='clinic_profiles')
    name = models.CharField(max_length=255, default="Clinic Name")
    specialization = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=500, blank=True, null=True)
    slogan = models.CharField(max_length=255, blank=True, null=True)
    locality = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=100, default="India")
    state = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    tax = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    default_language = models.CharField(max_length=50, default="English")
    default_currency = models.CharField(max_length=50, default="RS - ₹")
    
    def save(self, *args, **kwargs):
        if not self.pk and self.branch:
            existing = ClinicProfile.objects.filter(branch=self.branch).first()
            if existing:
                self.pk = existing.pk
        elif not self.pk and ClinicProfile.objects.exists():
            self.pk = ClinicProfile.objects.first().pk
        super(ClinicProfile, self).save(*args, **kwargs)

    @classmethod
    def load(cls, branch=None):
        if branch:
            obj = cls.objects.filter(branch=branch).first()
            if obj:
                return obj
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj

class ClinicTiming(models.Model):
    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]
    day = models.CharField(max_length=15, choices=DAY_CHOICES, unique=True)
    morning_start = models.TimeField(default='09:00:00')
    morning_end = models.TimeField(default='13:00:00')
    evening_start = models.TimeField(default='15:00:00')
    evening_end = models.TimeField(default='20:00:00')
    is_closed = models.BooleanField(default=False)

    def __str__(self):
        return self.day

class AutoNumbering(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='auto_numberings')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name='auto_numberings')
    patient_prefix = models.CharField(max_length=20, default="PT-")
    patient_start = models.IntegerField(default=1001)
    invoice_prefix = models.CharField(max_length=20, default="INV-")
    invoice_start = models.IntegerField(default=500)
    prescription_prefix = models.CharField(max_length=20, default="RX-")
    prescription_start = models.IntegerField(default=200)

    def save(self, *args, **kwargs):
        if not self.pk and self.branch:
            existing = AutoNumbering.objects.filter(branch=self.branch).first()
            if existing:
                self.pk = existing.pk
        elif not self.pk and AutoNumbering.objects.exists():
            self.pk = AutoNumbering.objects.first().pk
        super(AutoNumbering, self).save(*args, **kwargs)

    @classmethod
    def load(cls, branch=None):
        if branch:
            obj = cls.objects.filter(branch=branch).first()
            if obj:
                return obj
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj

class Salutation(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class PatientRequiredFields(models.Model):
    dob = models.BooleanField(default=True)
    gender = models.BooleanField(default=True)
    blood_group = models.BooleanField(default=False)
    phone = models.BooleanField(default=True)
    email = models.BooleanField(default=False)
    alt_contact = models.BooleanField(default=False)
    medical_history = models.BooleanField(default=True)
    patient_group = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.pk and PatientRequiredFields.objects.exists():
            self.pk = PatientRequiredFields.objects.first().pk
        super(PatientRequiredFields, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj


class PatientLabOrder(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='lab_orders')
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100) # Pathology, Dental Lab
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=50, default='Pending') # Pending, Completed
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} for {self.patient.name} ({self.status})"


# ─── NEW SETTINGS MODELS ────────────────────────────────────────────────────

class RoleDefaultPermissions(models.Model):
    """
    Stores the default module-level permissions for each role (Doctor, Receptionist, etc.).
    When a new staff member is created, these are copied to their profile.
    """
    ROLE_CHOICES = [
        ('Admin', 'Admin'),
        ('Doctor', 'Doctor'),
        ('Pharmacist', 'Pharmacist'),
        ('Receptionist', 'Receptionist'),
    ]
    role = models.CharField(max_length=50, unique=True)
    permissions = models.JSONField(default=list)

    def __str__(self):
        return f"Default permissions for {self.role}"

    @classmethod
    def get_or_create_defaults(cls):
        """Ensure all roles have a default permissions record."""
        defaults = {
            'Admin': ['dashboard', 'add-patients', 'appointments', 'today-patients',
                      'search-patient', 'follow-ups', 'pre-bookings', 'tele-medicine',
                      'website-appointment', 'communication', 'billing', 
                      'expense-manager', 'reports', 'pathology-lab', 'dental-lab',
                      'pharmacy', 'purchases', 'stock', 'prescriptions', 'users', 'doctors', 'settings'],
            'Doctor': ['dashboard', 'add-patients', 'appointments', 'today-patients',
                       'search-patient', 'follow-ups', 'pre-bookings', 'tele-medicine',
                       'website-appointment', 'communication', 'reports', 'prescriptions', 'doctor-slots', 'income'],
            'Pharmacist': ['dashboard', 'pharmacy', 'stock', 'purchases', 'prescriptions'],
            'Receptionist': ['dashboard', 'add-patients', 'appointments', 'today-patients',
                             'search-patient', 'follow-ups', 'pre-bookings', 'tele-medicine',
                             'website-appointment', 'billing', 'lab'],
        }
        records = {}
        for role, perms in defaults.items():
            obj, _ = cls.objects.get_or_create(role=role, defaults={'permissions': perms})
            records[role] = obj
        return records


class PharmacySettings(models.Model):
    """
    Singleton model for pharmacy-wide configuration.
    Changes here affect the Pharmacy module in real-time.
    """
    # Billing defaults
    default_payment_method = models.CharField(max_length=50, default='Cash')
    # Stock
    low_stock_threshold = models.IntegerField(default=10)
    # Dispensing
    require_prescription = models.BooleanField(default=False)
    allow_partial_dispensing = models.BooleanField(default=True)
    auto_deduct_stock_on_bill = models.BooleanField(default=True)
    # Receipt
    auto_print_receipt = models.BooleanField(default=False)
    # GST / Tax
    apply_gst = models.BooleanField(default=False)
    gst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        if not self.pk and PharmacySettings.objects.exists():
            self.pk = PharmacySettings.objects.first().pk
        super(PharmacySettings, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj

    def __str__(self):
        return "Pharmacy Settings"


class PrescriptionTemplate(models.Model):
    """
    Pre-built prescription templates doctors can load with one click.
    Each template contains a list of medicines with dosage/duration.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    items = models.JSONField(default=list)  # [{medicine_name, dosage, duration, qty, notes}]
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class DosageLabel(models.Model):
    """
    Custom dosage/frequency labels used in the prescription form dropdown.
    E.g.: 1-0-1, BD, TID, OD, SOS
    """
    label = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.label


from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=TreatmentRecord)
def auto_assign_patient_group(sender, instance, created, **kwargs):
    if not instance.visit or not instance.visit.patient or not instance.treatment:
        return
    
    patient = instance.visit.patient
    treatment_name = (instance.treatment.name or "").lower()
    fee_type = (instance.fee_type or "").lower()
    treatment_master_fee_type = (instance.treatment.fee_type or "").lower()

    # Ortho check
    if "ortho" in treatment_name or "ortho" in fee_type or "ortho" in treatment_master_fee_type:
        group, _ = PatientGroup.objects.get_or_create(
            name="Ortho",
            defaults={"description": "Automatically created Ortho communication group"}
        )
        if not patient.groups.filter(id=group.id).exists():
            patient.groups.add(group)
            
    # Implant check
    if "implant" in treatment_name or "implant" in fee_type or "implant" in treatment_master_fee_type:
        group, _ = PatientGroup.objects.get_or_create(
            name="Implant",
            defaults={"description": "Automatically created Implant communication group"}
        )
        if not patient.groups.filter(id=group.id).exists():
            patient.groups.add(group)


# ─── TOP-LEVEL MASTERS MODULE MODELS ────────────────────────────────────────

class PatientTypeMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class StaffLevelMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class DesignationMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class RoleMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    is_system_role = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PermissionMaster(models.Model):
    module_code = models.CharField(max_length=100, help_text="e.g. PATIENTS, BILLING, CLINICAL, MASTERS")
    permission_code = models.CharField(max_length=100, unique=True, help_text="e.g. PATIENTS_PROFILE, BILLING_INVOICES")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['module_code', 'permission_code']

    def __str__(self):
        return f"[{self.module_code}] {self.name}"


class RolePermission(models.Model):
    role = models.ForeignKey(RoleMaster, on_delete=models.CASCADE, related_name='role_permissions')
    permission = models.ForeignKey(PermissionMaster, on_delete=models.CASCADE, related_name='role_assignments')
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    can_approve = models.BooleanField(default=False)

    class Meta:
        unique_together = ('role', 'permission')

    def __str__(self):
        return f"{self.role.name} -> {self.permission.name}"


class StaffPermissionOverride(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='permission_overrides')
    permission = models.ForeignKey(PermissionMaster, on_delete=models.CASCADE)
    can_view = models.BooleanField(null=True, blank=True)
    can_create = models.BooleanField(null=True, blank=True)
    can_edit = models.BooleanField(null=True, blank=True)
    can_delete = models.BooleanField(null=True, blank=True)
    can_export = models.BooleanField(null=True, blank=True)
    can_approve = models.BooleanField(null=True, blank=True)

    class Meta:
        unique_together = ('staff', 'permission')

    def __str__(self):
        return f"Override for {self.staff.name} -> {self.permission.name}"


class DiscountMaster(models.Model):
    DISCOUNT_TYPES = [
        ('Percentage', 'Percentage'),
        ('Fixed Amount', 'Fixed Amount'),
    ]
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='Percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    applicable_module = models.CharField(max_length=50, default='ALL')
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField(null=True, blank=True)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class OfferPackage(models.Model):
    PACKAGE_TYPES = [
        ('Combo Treatment', 'Combo Treatment'),
        ('Seasonal Offer', 'Seasonal Offer'),
        ('Membership Plan', 'Membership Plan'),
        ('Patient Group Offer', 'Patient Group Offer'),
        ('Family Package', 'Family Package'),
    ]
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    package_type = models.CharField(max_length=50, choices=PACKAGE_TYPES, default='Combo Treatment')
    original_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    package_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_type = models.CharField(max_length=20, choices=[('Flat Amount', 'Flat Amount'), ('Percentage', 'Percentage')], default='Flat Amount')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField(null=True, blank=True)
    validity_days = models.IntegerField(default=365)
    max_redemptions = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.code}) - ₹{self.package_price}"


class OfferPackageItem(models.Model):
    ITEM_TYPES = [
        ('Treatment', 'Treatment'),
        ('Lab Test', 'Lab Test'),
        ('Medicine', 'Medicine'),
        ('Consultation', 'Consultation'),
    ]
    package = models.ForeignKey(OfferPackage, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(max_length=30, choices=ITEM_TYPES)
    treatment = models.ForeignKey(TreatmentMaster, on_delete=models.SET_NULL, null=True, blank=True)
    lab_test = models.ForeignKey(LabTestMaster, on_delete=models.SET_NULL, null=True, blank=True)
    medicine = models.ForeignKey(MedicineMaster, on_delete=models.SET_NULL, null=True, blank=True)
    custom_item_name = models.CharField(max_length=255, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    package_item_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.package.name} -> {self.item_type} (x{self.quantity})"


class PatientPackageSubscription(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('EXHAUSTED', 'Exhausted'),
        ('CANCELLED', 'Cancelled'),
    ]
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='package_subscriptions')
    group = models.ForeignKey(PatientGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='package_subscriptions')
    package = models.ForeignKey(OfferPackage, on_delete=models.PROTECT, related_name='subscriptions')
    purchase_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField()
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.patient.name} - {self.package.name} ({self.status})"


class PackageRedemption(models.Model):
    subscription = models.ForeignKey(PatientPackageSubscription, on_delete=models.CASCADE, related_name='redemptions')
    package_item = models.ForeignKey(OfferPackageItem, on_delete=models.CASCADE, related_name='redemptions')
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='package_redemptions')
    billing_item = models.ForeignKey(BillingItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='package_redemption')
    redeemed_quantity = models.IntegerField(default=1)
    redeemed_at = models.DateTimeField(default=timezone.now)
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Redeemed {self.redeemed_quantity}x {self.package_item} for {self.patient.name}"


class StaffLeaveConfig(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='leave_configs')
    leave_type = models.CharField(max_length=100) # e.g., Casual Leave, Paid Leave, Unpaid Leave
    annual_entitlement = models.IntegerField(default=12)
    is_paid = models.BooleanField(default=True)
    carry_forward = models.BooleanField(default=False)
    max_carry_forward = models.IntegerField(default=0)
    applicable_from = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['leave_type']

    def __str__(self):
        return f"{self.staff.name} - {self.leave_type} ({self.annual_entitlement} days)"


class StaffBenefit(models.Model):
    FREQUENCY_CHOICES = [
        ('Monthly', 'Monthly'),
        ('Annual', 'Annual'),
        ('One-time', 'One-time'),
    ]
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='benefits')
    benefit_name = models.CharField(max_length=150) # e.g., Health Benefit, Transport Benefit, Meal Benefit, Bonus
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    frequency = models.CharField(max_length=30, choices=FREQUENCY_CHOICES, default='Monthly')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.staff.name} - {self.benefit_name} (₹{self.amount})"


class StaffInsurance(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Expired', 'Expired'),
        ('Renewed', 'Renewed'),
        ('Cancelled', 'Cancelled'),
    ]
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='insurance_policies')
    is_enabled = models.BooleanField(default=True)
    provider = models.CharField(max_length=150, blank=True, null=True)
    policy_number = models.CharField(max_length=100, blank=True, null=True)
    policy_type = models.CharField(max_length=100, default='Health Insurance')
    coverage_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    employee_contribution = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    employer_contribution = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    start_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Active')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.staff.name} - {self.provider} ({self.policy_number})"



class InvestigationMaster(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='investigation_masters')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=100, default='Radiology / Imaging')
    description = models.TextField(blank=True, null=True)
    default_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PatientInvestigation(models.Model):
    STATUS_CHOICES = [
        ('Requested', 'Requested'),
        ('Result Pending', 'Result Pending'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='patient_investigations')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='patient_investigations')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='investigations')
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='investigations')
    visit = models.ForeignKey(Visit, on_delete=models.SET_NULL, null=True, blank=True, related_name='investigations')
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='investigations')
    investigation_master = models.ForeignKey(InvestigationMaster, on_delete=models.SET_NULL, null=True, blank=True, related_name='patient_investigations')

    investigation_name = models.CharField(max_length=255)
    investigation_date = models.DateField(default=timezone.now)
    reason = models.TextField(blank=True, null=True)
    findings = models.TextField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Requested')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-investigation_date', '-created_at']

    def __str__(self):
        return f"{self.investigation_name} - {self.patient.name} ({self.status})"


class InvestigationAttachment(models.Model):
    investigation = models.ForeignKey(PatientInvestigation, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='investigations/%Y/%m/', null=True, blank=True)
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100, blank=True, null=True)
    file_size = models.IntegerField(default=0)
    file_data = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file_name} ({self.investigation.investigation_name})"


class ToothConditionRecord(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='tooth_conditions')
    visit = models.ForeignKey(Visit, on_delete=models.SET_NULL, null=True, blank=True, related_name='tooth_conditions')
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='tooth_conditions')
    tooth_number = models.IntegerField()
    condition = models.JSONField(default=list, blank=True)
    surfaces = models.JSONField(default=list, blank=True)
    examination = models.JSONField(default=list, blank=True)
    diagnosis = models.JSONField(default=list, blank=True)
    treatments_suggested = models.JSONField(default=list, blank=True)
    mobility = models.CharField(max_length=50, blank=True, default='')
    pocket_depth = models.CharField(max_length=50, blank=True, default='')
    furcation = models.CharField(max_length=50, blank=True, default='')
    plaque_index = models.CharField(max_length=50, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['tooth_number']

    def __str__(self):
        return f'Tooth #{self.tooth_number} ({self.patient.name}): {self.condition}'


class TreatmentPlan(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Proposed', 'Proposed'),
        ('Accepted', 'Accepted'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='treatment_plans')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_plans')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='treatment_plans')
    visit = models.ForeignKey(Visit, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_plans')
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_plans')
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_plans')
    title = models.CharField(max_length=255, default='Comprehensive Dental Treatment Plan')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Proposed')
    total_estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} for {self.patient.name} [{self.status}]'


class TreatmentPlanItem(models.Model):
    PRIORITY_CHOICES = [
        ('Urgent', 'Urgent'),
        ('Routine', 'Routine'),
        ('Elective', 'Elective'),
    ]
    STATUS_CHOICES = [
        ('Proposed', 'Proposed'),
        ('Accepted', 'Accepted'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    plan = models.ForeignKey(TreatmentPlan, on_delete=models.CASCADE, related_name='items')
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_plan_items')
    tooth_number = models.CharField(max_length=50, blank=True, default='')
    surface = models.CharField(max_length=100, blank=True, default='All')
    diagnosis = models.CharField(max_length=255, blank=True, default='')
    procedure_name = models.CharField(max_length=255)
    treatment_master = models.ForeignKey(TreatmentMaster, null=True, blank=True, on_delete=models.SET_NULL, related_name='plan_items')
    priority = models.CharField(max_length=50, choices=PRIORITY_CHOICES, default='Routine')
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    estimated_visits = models.IntegerField(default=1)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Proposed')
    notes = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.procedure_name} (#{self.tooth_number}) - {self.status}'


class TreatmentSession(models.Model):
    STATUS_CHOICES = [
        ('Scheduled', 'Scheduled'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Incomplete', 'Incomplete'),
        ('Cancelled', 'Cancelled'),
    ]

    treatment_record = models.ForeignKey(TreatmentRecord, null=True, blank=True, on_delete=models.CASCADE, related_name='sessions')
    plan_item = models.ForeignKey(TreatmentPlanItem, null=True, blank=True, on_delete=models.SET_NULL, related_name='sessions')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='treatment_sessions')
    visit = models.ForeignKey(Visit, null=True, blank=True, on_delete=models.SET_NULL, related_name='treatment_sessions')
    doctor = models.ForeignKey(Doctor, null=True, blank=True, on_delete=models.SET_NULL, related_name='treatment_sessions')
    session_number = models.IntegerField(default=1)
    session_date = models.DateField(default=timezone.now)
    procedure_performed = models.CharField(max_length=255)
    clinical_notes = models.TextField(blank=True, default='')
    materials_used = models.TextField(blank=True, default='')
    next_session_plan = models.TextField(blank=True, default='')
    next_session_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Completed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['session_date', 'session_number']

    def __str__(self):
        return f'Session #{self.session_number}: {self.procedure_performed} ({self.patient.name})'


class EMRChangeLog(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='emr_audit_logs')
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100)
    action = models.CharField(max_length=50) # CREATE, UPDATE, DELETE
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    changes = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.action} on {self.entity_type} #{self.entity_id} at {self.timestamp}'
