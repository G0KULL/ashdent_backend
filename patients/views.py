import re
from collections import defaultdict
from rest_framework.views import APIView
from django.db import transaction, IntegrityError, connections
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login as django_login
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import models
from django.db.models import Q, Sum
from django.http import HttpResponse
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from .models import (
    Company, Branch,
    normalize_phone, normalize_email, Staff, Doctor, DoctorSchedule, DoctorScheduleProposal,
    DoctorDateOverride, InAppNotification, AuditLog, Patient, Appointment, TreatmentMaster,
    Visit, TreatmentRecord, Payment, Prescription, PrescriptionItem, Tooth, ClinicalNotes,
    ToothMaster, PreBooking, MedicineMaster, Billing, BillingItem, PatientGroup, CommunicationLog,
    Transaction, Supplier, MedicinePurchase, PharmacyPurchase, PharmacyPurchaseItem, MedicineStock,
    SupplierLedger, TaxSetting, CommunicationTemplate, LabHeader, Laboratory, LabTestMaster,
    LabTestParameter, LabPackage, DentalLaboratory, DentalLabWork, Expense, ExpenseCategory,
    PatientLabOrder, StaffLeaveConfig, StaffBenefit, StaffInsurance
)
from .serializers import (
    CompanySerializer, BranchSerializer,
    PatientSerializer, AppointmentSerializer, TreatmentMasterSerializer,
    VisitSerializer, TreatmentRecordSerializer, PaymentSerializer, PrescriptionSerializer,
    DoctorSerializer, DoctorScheduleSerializer, DoctorScheduleProposalSerializer,
    DoctorDateOverrideSerializer, InAppNotificationSerializer, ToothSerializer, ClinicalNotesSerializer,
    ToothMasterSerializer, MedicineMasterSerializer, BillingSerializer, BillingItemSerializer,
    PatientGroupSerializer, TransactionSerializer, SupplierSerializer, PharmacyPurchaseSerializer,
    MedicineStockSerializer, SupplierLedgerSerializer, TaxSettingSerializer, CommunicationTemplateSerializer,
    LabHeaderSerializer, LaboratorySerializer, LabTestMasterSerializer, LabTestParameterSerializer,
    LabPackageSerializer, DentalLaboratorySerializer, DentalLabWorkSerializer, StaffSerializer,
    PatientLabOrderSerializer, StaffLeaveConfigSerializer, StaffBenefitSerializer, StaffInsuranceSerializer
)
from .security import (
    get_authenticated_user, is_super_admin, is_application_admin,
    can_create_staff_role, can_modify_staff, get_user_for_staff, resolve_user_by_id,
    get_request_scope
)


def get_user_doctor(request):
    """Return the Doctor profile linked to the logged-in user, or None.

    Uses a direct PyMongo lookup because the Django ORM reverse
    OneToOneField lookup silently fails with MongoDB ObjectId PKs.
    Tries multiple strategies to resolve the user to a Doctor profile.
    """
    from django.db import connections
    from bson import ObjectId

    db = connections['default'].database
    user_id = request.headers.get('X-User-Id', '').strip()
    username = request.headers.get('X-Username', '').strip()

    u_doc = None

    # Strategy 1: Look up auth_user by MongoDB ObjectId
    if user_id:
        try:
            u_doc = db['auth_user'].find_one({'_id': ObjectId(user_id)})
        except Exception:
            pass

    # Strategy 2: Look up auth_user by integer numeric id field
    if not u_doc and user_id:
        try:
            u_doc = db['auth_user'].find_one({'id': int(user_id)})
        except Exception:
            pass

    # Strategy 3: Fallback lookup by username header
    if not u_doc and username:
        try:
            u_doc = db['auth_user'].find_one({'username': username})
        except Exception:
            pass

    if u_doc:
        try:
            s_doc = db['patients_staff'].find_one({'user_id': u_doc['_id']})
            if s_doc and s_doc.get('role') == 'Doctor' and s_doc.get('doctor_profile_id'):
                try:
                    return Doctor.objects.get(id=s_doc['doctor_profile_id'])
                except Doctor.DoesNotExist:
                    pass
        except Exception:
            pass

    return None

def log_audit(action, user=None):
    try:
        user_id = user.pk if user else None
        AuditLog.objects.create(action=action, user_id=user_id)
    except Exception as e:
        print("AuditLog error:", e)

def notify_user(user, title, message, notification_type='SYSTEM', data=None):
    if user:
        try:
            recipient_id = getattr(user, 'pk', user)
            InAppNotification.objects.create(
                recipient_id=recipient_id,
                title=title,
                message=message,
                notification_type=notification_type,
                data=data or {}
            )
        except Exception as e:
            print("Notification error:", e)

def notify_admins(title, message, notification_type='SYSTEM', data=None):
    from .security import get_user_for_staff
    from django.db import connections
    db = connections['default'].database
    admin_users = []
    for u_doc in db['auth_user'].find({'is_superuser': True}):
        u = User.objects.filter(username=u_doc['username']).first()
        if u:
            u.id = u_doc['_id']
            u.pk = u_doc['_id']
            admin_users.append(u)
    for s in Staff.objects.filter(role='Admin'):
        u = get_user_for_staff(s)
        if u and not any(str(existing.id) == str(u.id) for existing in admin_users):
            admin_users.append(u)
    for u in admin_users:
        notify_user(u, title, message, notification_type, data)

from .models import WebsiteAppointmentRequest
from .serializers import WebsiteAppointmentRequestSerializer
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from django.utils import timezone

def send_appointment_communication(appt, template_type="Confirmation"):
    try:
        template = CommunicationTemplate.objects.filter(category="Appointment", type=template_type).first()
        if not template:
            return
        
        # Replace placeholders
        msg = template.text.replace("{patient}", appt.patient.name)
        msg = msg.replace("{doctor}", appt.doctor.name if appt.doctor else "Doctor")
        msg = msg.replace("{date}", str(appt.date))
        msg = msg.replace("{time}", appt.time.strftime("%I:%M %p") if appt.time else "")
        msg = msg.replace("{clinic}", "Our Clinic")
        msg = msg.replace("{phone}", "Clinic Phone")
        msg = msg.replace("{procedure}", "Consultation")
        
        channels = []
        if template.sms_enabled:
            channels.append("SMS")
        if getattr(template, 'whatsapp_enabled', False):
            channels.append("WhatsApp")
        if getattr(template, 'email_enabled', False):
            channels.append("Email")
            
        for channel in channels:
            CommunicationLog.objects.create(
                patient=appt.patient,
                message=msg,
                channel=channel
            )
    except Exception as e:
        print("Error sending communication:", e)


# --- TEETH MASTER ---
class ToothMasterListView(APIView):
    def get(self, request):
        teeth = ToothMaster.objects.all().order_by('tooth_number')
        serializer = ToothMasterSerializer(teeth, many=True)
        return Response(serializer.data)

# --- PATIENT ---
class PatientCreateView(APIView):
    def post(self, request):
        phone = request.data.get('phone', '').strip()
        name  = request.data.get('name', '').strip()
        if not name:
            fn = request.data.get('firstName', '').strip()
            ln = request.data.get('lastName', '').strip()
            name = f"{fn} {ln}".strip()

        # --- BACKEND PAYMENT VALIDATION ---
        from decimal import Decimal
        consultation_fee_val = Decimal(str(request.data.get('consultation_fee', 0) or 0))
        if consultation_fee_val < Decimal('0.00'):
            return Response({
                'detail': 'Consultation fee cannot be negative.',
                'consultation_fee': 'Consultation fee cannot be negative.'
            }, status=status.HTTP_400_BAD_REQUEST)

        tax_rate_val = Decimal(str(request.data.get('tax', 0) or 0))
        if tax_rate_val < Decimal('0.00'):
            return Response({
                'detail': 'Tax rate cannot be negative.',
                'tax': 'Tax rate cannot be negative.'
            }, status=status.HTTP_400_BAD_REQUEST)

        treatments_raw = request.data.get('treatments', [])
        treatment_total_val = Decimal('0.00')
        for t_item in treatments_raw:
            if isinstance(t_item, dict):
                cost = t_item.get('cost')
                t_id = t_item.get('id')
            else:
                cost = None
                t_id = t_item
            if cost is not None and cost != '':
                cost_dec = Decimal(str(cost))
                if cost_dec < Decimal('0.00'):
                    return Response({
                        'detail': 'Treatment cost cannot be negative.',
                        'treatments': 'Treatment cost cannot be negative.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                treatment_total_val += cost_dec
            elif t_id:
                t_master = TreatmentMaster.objects.filter(id=t_id).first()
                if t_master:
                    treatment_total_val += Decimal(str(t_master.price))

        base_amount_val = consultation_fee_val + treatment_total_val
        payable_amount_val = base_amount_val + (base_amount_val * tax_rate_val / Decimal('100'))

        payment_method_val = str(request.data.get('payment_method', '') or '').strip()
        transaction_id_val = str(request.data.get('transaction_id', '') or '').strip()
        transaction_date_val = str(request.data.get('transaction_date', '') or '').strip()

        cash_received_val = Decimal('0.00')
        balance_returned_val = Decimal('0.00')
        actual_paid_val = Decimal('0.00')

        if payable_amount_val > Decimal('0.00'):
            if not payment_method_val:
                return Response({
                    'detail': 'Payment method is required when payable amount is greater than 0.',
                    'payment_method': 'Payment method is required.'
                }, status=status.HTTP_400_BAD_REQUEST)

            pm_lower = payment_method_val.lower()
            if pm_lower == 'cash':
                cash_rec_raw = request.data.get('cash_received')
                if cash_rec_raw is None or str(cash_rec_raw).strip() == '':
                    cash_rec_raw = request.data.get('paid_amount', 0)
                try:
                    cash_received_val = Decimal(str(cash_rec_raw or 0))
                except Exception:
                    return Response({
                        'detail': 'Invalid numeric value for Cash Received.',
                        'cash_received': 'Invalid numeric value for Cash Received.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if cash_received_val < Decimal('0.00'):
                    return Response({
                        'detail': 'Cash Received cannot be negative.',
                        'cash_received': 'Cash Received cannot be negative.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                if cash_received_val <= Decimal('0.00'):
                    return Response({
                        'detail': 'Cash Received must be greater than 0 for Cash payment.',
                        'cash_received': 'Cash Received must be greater than 0.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Authoritative calculation of amount applied and change to return
                if cash_received_val >= payable_amount_val:
                    actual_paid_val = payable_amount_val
                    balance_returned_val = cash_received_val - payable_amount_val
                else:
                    # Partial payment (supported by existing system)
                    actual_paid_val = cash_received_val
                    balance_returned_val = Decimal('0.00')
            else:
                paid_raw = request.data.get('paid_amount', 0)
                try:
                    paid_amount_val = Decimal(str(paid_raw or 0))
                except Exception:
                    return Response({
                        'detail': 'Invalid numeric value for Amount Paid.',
                        'paid_amount': 'Invalid numeric value for Amount Paid.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                if paid_amount_val < Decimal('0.00'):
                    return Response({
                        'detail': 'Amount Paid cannot be negative.',
                        'paid_amount': 'Amount Paid cannot be negative.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                if paid_amount_val <= Decimal('0.00'):
                    return Response({
                        'detail': f'Amount Paid must be greater than 0 for {payment_method_val} payment.',
                        'paid_amount': 'Amount Paid must be greater than 0.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                if paid_amount_val > payable_amount_val:
                    return Response({
                        'detail': f'Amount Paid (₹{paid_amount_val}) cannot exceed total payable amount (₹{payable_amount_val}).',
                        'paid_amount': 'Amount Paid cannot exceed total payable amount.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                if not transaction_id_val:
                    return Response({
                        'detail': 'Transaction ID is required for digital/non-cash payments.',
                        'transaction_id': 'Transaction ID is required.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                if not transaction_date_val:
                    return Response({
                        'detail': 'Transaction Date is required for digital/non-cash payments.',
                        'transaction_date': 'Transaction Date is required.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                actual_paid_val = paid_amount_val
                cash_received_val = Decimal('0.00')
                balance_returned_val = Decimal('0.00')
        else:
            actual_paid_val = Decimal('0.00')
            cash_received_val = Decimal('0.00')
            balance_returned_val = Decimal('0.00')

        scope = get_request_scope(request)
        # Match by BOTH phone AND name within the same company — same phone with a different name = different patient
        existing_patient = None
        if phone and name:
            match_qs = Patient.objects.filter(phone=phone, name=name)
            if scope.company and not scope.is_super:
                match_qs = match_qs.filter(company=scope.company)
            existing_patient = match_qs.first()

        if existing_patient:
            # Same person returning — just update mutable fields
            patient = existing_patient
            new_dob = request.data.get('dob')
            if new_dob:
                patient.dob = new_dob
            new_age = request.data.get('age')
            if new_age is not None and new_age != '':
                patient.age = new_age
            new_gender = request.data.get('gender')
            if new_gender:
                patient.gender = new_gender
            new_address = request.data.get('address')
            if new_address is not None:
                patient.address = new_address
            new_pincode = request.data.get('pincode')
            if new_pincode is not None:
                patient.pincode = new_pincode
            new_fee = request.data.get('consultation_fee')
            if new_fee is not None and str(new_fee).strip() != '':
                patient.consultation_fee = Decimal(str(new_fee))
            patient.save()
        else:
            # Different name or new phone — always create a brand-new patient record
            patient_data = {
                'name': name,
                'phone': phone,
                'dob': request.data.get('dob') or None,
                'age': request.data.get('age') if (request.data.get('age') is not None and request.data.get('age') != '') else None,
                'gender': request.data.get('gender'),
                'address': request.data.get('address'),
                'pincode': request.data.get('pincode'),
                'notes': request.data.get('notes'),
                'consultation_fee': request.data.get('consultation_fee', 0),
            }
            if scope.company:
                patient_data['company'] = str(scope.company.id)
            if scope.branch:
                patient_data['registration_branch'] = str(scope.branch.id)

            patient_serializer = PatientSerializer(data=patient_data)
            if not patient_serializer.is_valid():
                return Response(patient_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            patient = patient_serializer.save()

        # Assign Patient Type from Master
        patient_type_val = request.data.get('patient_type') or request.data.get('patient_type_id')
        if patient_type_val:
            from .models import PatientTypeMaster
            pt_obj = PatientTypeMaster.objects.filter(id=patient_type_val).first() or PatientTypeMaster.objects.filter(code__iexact=str(patient_type_val)).first() or PatientTypeMaster.objects.filter(name__iexact=str(patient_type_val)).first()
            if pt_obj:
                patient.patient_type = pt_obj
                patient.save()

        # Assign doctor
        doctor_id = request.data.get('doctor')
        doctor = None
        if doctor_id:
            try:
                doctor = Doctor.objects.filter(id=doctor_id).first()
            except Exception:
                pass

        if not doctor:
            logged_in_doctor = get_user_doctor(request)
            if logged_in_doctor:
                doctor = logged_in_doctor

        if doctor:
            patient.doctor = doctor
            patient.save()

        treatments = request.data.get('treatments', [])

        with transaction.atomic():
            if treatments or actual_paid_val > 0 or consultation_fee_val > Decimal('0.00') or payable_amount_val > Decimal('0.00'):
                appt_doc = doctor
                appt_time = request.data.get('time') or timezone.now().time()
                appt = Appointment.objects.create(
                    patient=patient,
                    doctor=appt_doc,
                    company=scope.company,
                    branch=scope.branch,
                    date=timezone.localtime(timezone.now()).date(),
                    time=appt_time,
                    status='Waiting'
                )

                visit = Visit.objects.create(patient=patient, appointment=appt, company=scope.company, branch=scope.branch)

                payment, _ = Payment.objects.get_or_create(visit=visit, defaults={'patient': patient, 'company': scope.company, 'branch': scope.branch})
                payment.payment_method = payment_method_val if payment_method_val else 'Cash'
                payment.doctor = doctor
                payment.company = scope.company
                payment.branch = scope.branch
                if transaction_id_val:
                    payment.transaction_id = transaction_id_val
                else:
                    payment.transaction_id = None
                if transaction_date_val:
                    payment.transaction_date = transaction_date_val
                else:
                    payment.transaction_date = None

                for t_item in treatments:
                    if isinstance(t_item, dict):
                        t_id = t_item.get('id')
                        cost = t_item.get('cost')
                        status_str = t_item.get('status', 'Pending')
                        notes_str = t_item.get('notes', '')
                        t_doc_id = t_item.get('doctor')
                    else:
                        t_id = t_item
                        cost = None
                        status_str = 'Pending'
                        notes_str = ''
                        t_doc_id = None
                    
                    t_master = TreatmentMaster.objects.filter(id=t_id).first()
                    if t_master:
                        cost_val = Decimal(str(cost)) if cost else t_master.price
                        TreatmentRecord.objects.create(
                            visit=visit,
                            treatment=t_master,
                            price=cost_val,
                            fee_type='Treatment',
                            status=status_str,
                            notes=notes_str,
                            doctor_id=t_doc_id if t_doc_id else (visit.appointment.doctor_id if (visit and visit.appointment) else None)
                        )

                payment.total_amount = payable_amount_val
                payment.paid_amount = actual_paid_val
                payment.cash_received = cash_received_val
                payment.balance_returned = balance_returned_val
                payment.save()

                # Add Prescription notes if any
                p_notes = request.data.get('prescription_notes')
                if p_notes:
                    Prescription.objects.create(visit=visit, notes=p_notes)

        # Send welcome/appointment communication
        send_appointment_communication(appt, template_type="Confirmation") if 'appt' in locals() else None

        return Response(PatientSerializer(patient).data, status=status.HTTP_201_CREATED)


class PatientByPhoneView(APIView):
    def get(self, request, phone):
        scope = get_request_scope(request)
        qs = Patient.objects.filter(phone=phone)
        if scope.company and not scope.is_super:
            qs = qs.filter(company=scope.company)
        patient = qs.first()
        if not patient:
            return Response({'detail': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PatientSerializer(patient)
        return Response(serializer.data)


class PatientSearchView(APIView):
    def get(self, request):
        scope = get_request_scope(request)
        query = request.query_params.get('q', '')
        date_filter = request.query_params.get('date', '')

        patients_qs = Patient.objects.all()
        if scope.company and not scope.is_super:
            patients_qs = patients_qs.filter(company=scope.company)

        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            patients_qs = patients_qs.filter(
                models.Q(doctor=doctor_profile) |
                models.Q(appointments__doctor=doctor_profile) |
                models.Q(billings__doctor=doctor_profile)
            ).distinct()

        if date_filter:
            patients_qs = patients_qs.filter(appointments__date=date_filter).distinct()

        patients = list(patients_qs.filter(
            models.Q(name__icontains=query) | models.Q(phone__icontains=query)
        ).order_by('name'))

        data = []
        for p in patients:
            net = float(p.total_balance)
            last_appt = p.appointments.order_by('-date').values('date', 'status').first()
            calculated_age = p.age
            if p.dob:
                from datetime import date
                today = date.today()
                calculated_age = max(0, today.year - p.dob.year - ((today.month, today.day) < (p.dob.month, p.dob.day)))
            data.append({
                'id': str(p.id),
                'name': p.name,
                'phone': p.phone or '',
                'dob': p.dob.strftime('%Y-%m-%d') if p.dob else '',
                'age': calculated_age,
                'gender': p.gender or '—',
                'address': p.address or '',
                'pincode': p.pincode or '',
                'status': p.status or 'Active',
                'total_balance': round(net, 2),
                'notes': p.notes or '',
                'created_at': p.created_at,
                'groups': [{'id': g.id, 'name': g.name} for g in p.groups.all()],
                'last_appointment': last_appt,
            })
        return Response(data)



class PatientProfileView(APIView):
    """Full patient profile with all related data."""
    def get(self, request, pk):
        scope = get_request_scope(request)
        patient = get_object_or_404(Patient, pk=pk)
        if not scope.is_super and scope.company and patient.company_id and str(patient.company_id) != str(scope.company.id):
            return Response({'error': 'Unauthorized: Patient belongs to another company.'}, status=status.HTTP_403_FORBIDDEN)

        today = timezone.localtime(timezone.now()).date()

        appointments = Appointment.objects.filter(patient=patient).order_by('-date', '-time')
        all_bills = Billing.objects.filter(patient=patient).order_by('-created_at')
        bills = all_bills.filter(is_invoice=True)
        clinical_bills = all_bills.exclude(bill_type='Pharmacy')
        prescriptions = Prescription.objects.filter(patient=patient).all().order_by('-created_at')

        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            appointments = appointments.filter(doctor=doctor_profile)
            all_bills = all_bills.filter(doctor=doctor_profile)
            bills = bills.filter(doctor=doctor_profile)
            clinical_bills = clinical_bills.filter(doctor=doctor_profile)
            prescriptions = prescriptions.filter(doctor=doctor_profile)

        return Response({
            'patient': PatientSerializer(patient).data,
            'appointments': AppointmentSerializer(appointments, many=True).data,
            'bills': BillingSerializer(bills, many=True).data,
            'payments': BillingSerializer(clinical_bills, many=True).data,  # Re-mapping for frontend compatibility
            'prescriptions': PrescriptionSerializer(prescriptions, many=True).data,
            'total_balance': str(patient.total_balance),
        })

    def patch(self, request, pk):
        patient = get_object_or_404(Patient, pk=pk)
        serializer = PatientSerializer(patient, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PatientBalanceWaiverView(APIView):
    """POST: increase balance_adjustment to waive part or all of the patient's displayed balance."""
    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
        if denied:
            return denied
        patient = get_object_or_404(Patient, pk=pk)
        current = Decimal(str(float(patient.total_balance)))
        if current <= 0:
            return Response({'error': 'No outstanding balance to waive.'}, status=400)
        raw_amt = request.data.get('amount')
        if raw_amt is None or str(raw_amt).strip() == '':
            amt = current
        else:
            amt = Decimal(str(raw_amt))
        if amt <= 0:
            return Response({'error': 'Amount must be positive.'}, status=400)
        if amt > current:
            amt = current
        prev_adj = Decimal(str(patient.balance_adjustment or 0))
        patient.balance_adjustment = prev_adj + amt
        patient.save()
        return Response({
            'status': 'ok',
            'waived': float(amt),
            'balance_adjustment': float(patient.balance_adjustment),
            'total_balance': float(patient.total_balance),
        })


class CreditPatientView(APIView):
    def get(self, request):
        from collections import defaultdict
        
        # Optimize by only fetching patients with outstanding balances in Billing/Payment
        active_bill_patient_ids = Billing.objects.filter(
            bill_type='Clinical', 
            balance_amount__gt=0
        ).exclude(status='Cancelled').values_list('patient_id', flat=True).distinct()
        
        active_pay_patient_ids = Payment.objects.filter(
            balance_amount__gt=0
        ).exclude(visit__billings__isnull=False).exclude(status='Cancelled').values_list('patient_id', flat=True).distinct()
        
        debtor_ids = list(set(active_bill_patient_ids) | set(active_pay_patient_ids))
        patients = Patient.objects.filter(id__in=debtor_ids)
        
        # Prefetch related billing and payment objects for these debtor patients to calculate balances in memory
        active_billings = Billing.objects.filter(
            patient_id__in=debtor_ids,
            bill_type='Clinical'
        ).exclude(status='Cancelled').order_by('created_at')
        
        active_payments = Payment.objects.filter(
            patient_id__in=debtor_ids
        ).exclude(visit__billings__isnull=False).exclude(status='Cancelled')
        
        # Fetch all BillingItem objects in one query to check for brought forward carry-overs
        billing_ids = [b.id for b in active_billings]
        billing_items = BillingItem.objects.filter(billing_id__in=billing_ids) if billing_ids else []
        
        # Mappings for O(1) in-memory lookups
        billings_by_patient = defaultdict(list)
        for b in active_billings:
            billings_by_patient[b.patient_id].append(b)
            
        items_by_billing = defaultdict(list)
        for item in billing_items:
            items_by_billing[item.billing_id].append(item)
            
        payments_by_patient = defaultdict(list)
        for p in active_payments:
            payments_by_patient[p.patient_id].append(p)
            
        data = []
        for p in patients:
            # Replicate Patient.total_balance logic in memory to eliminate N+1 queries
            patient_billings = billings_by_patient[p.id]
            carry_forward_dates = []
            for b in patient_billings:
                has_carry_forward = any(
                    item.treatment and item.treatment.name == 'Outstanding balance (brought forward)'
                    for item in items_by_billing[b.id]
                )
                if has_carry_forward:
                    carry_forward_dates.append(b.created_at)
                    
            latest_carry_date = max(carry_forward_dates) if carry_forward_dates else None
            
            b_total = 0.0
            b_paid = 0.0
            for b in patient_billings:
                if latest_carry_date and b.created_at < latest_carry_date:
                    b_total += float(b.total_amount)
                    b_paid += float(b.total_amount)
                else:
                    b_total += float(b.total_amount)
                    b_paid += float(b.paid_amount)
            
            patient_payments = payments_by_patient[p.id]
            p_total = sum(float(x.total_amount) for x in patient_payments)
            p_paid = sum(float(x.paid_amount) for x in patient_payments)
            
            net = (b_total + p_total) - (b_paid + p_paid)
            adj = float(p.balance_adjustment or 0)
            bal = max(0.0, max(0.0, net) - adj)
            
            if bal > 0:
                # Find latest transaction date in memory
                dates = [b.created_at for b in patient_billings] + [py.created_at for py in patient_payments]
                b_date = max(dates) if dates else None

                data.append({
                    'id': p.id,
                    'name': p.name,
                    'phone': p.phone or '',
                    'total_balance': round(bal, 2),
                    'last_payment_date': b_date
                })

        data.sort(key=lambda x: x['total_balance'], reverse=True)
        return Response(data)



class PaymentSearchView(APIView):
    def get(self, request):
        from collections import defaultdict
        
        q = request.query_params.get('q', '')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        credits_only = request.query_params.get('credits_only')
        patient_id = request.query_params.get('patient_id')

        bills = Billing.objects.filter(is_invoice=True)
        legacy_payments = Payment.objects.filter(patient__isnull=False).exclude(visit__billings__isnull=False).all()

        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            bills = bills.filter(doctor=doctor_profile)
            legacy_payments = legacy_payments.filter(visit__appointment__doctor=doctor_profile)

        if patient_id:
            bills = bills.filter(patient_id=patient_id)
            legacy_payments = legacy_payments.filter(patient_id=patient_id)

        if q:
            bills = bills.filter(Q(patient__name__icontains=q) | Q(patient__phone__icontains=q))
            legacy_payments = legacy_payments.filter(Q(patient__name__icontains=q) | Q(patient__phone__icontains=q))

        if start_date:
            dt_start = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            bills = bills.filter(created_at__gte=dt_start)
            legacy_payments = legacy_payments.filter(created_at__gte=dt_start)
        if end_date:
            dt_end = timezone.make_aware(datetime.combine(datetime.strptime(end_date, '%Y-%m-%d'), time.max))
            bills = bills.filter(created_at__lte=dt_end)
            legacy_payments = legacy_payments.filter(created_at__lte=dt_end)

        if credits_only == 'true':
            bills = bills.filter(balance_amount__gt=0).exclude(bill_type='Pharmacy')
            legacy_payments = legacy_payments.filter(balance_amount__gt=0)

        # Evaluate querysets to lists to avoid multiple DB execution trips
        bills_list = list(bills)
        legacy_payments_list = list(legacy_payments)

        # Collect unique foreign key IDs for bulk queries
        patient_ids = set()
        doctor_ids = set()
        visit_ids = set()
        appointment_ids = set()

        for b in bills_list:
            if b.patient_id:
                patient_ids.add(b.patient_id)
            if b.doctor_id:
                doctor_ids.add(b.doctor_id)

        for p in legacy_payments_list:
            if p.patient_id:
                patient_ids.add(p.patient_id)
            if p.visit_id:
                visit_ids.add(p.visit_id)

        # Bulk fetch related models
        patients_dict = {p.id: p for p in Patient.objects.filter(id__in=list(patient_ids))} if patient_ids else {}
        doctors_dict = {d.id: d for d in Doctor.objects.filter(id__in=list(doctor_ids))} if doctor_ids else {}

        # Fetch Visits, Appointments and their Doctors for legacy payments
        visits_dict = {}
        appointments_dict = {}
        if visit_ids:
            visits_dict = {v.id: v for v in Visit.objects.filter(id__in=list(visit_ids))}
            for v in visits_dict.values():
                if v.appointment_id:
                    appointment_ids.add(v.appointment_id)

        if appointment_ids:
            appointments_dict = {a.id: a for a in Appointment.objects.filter(id__in=list(appointment_ids))}
            # Gather any doctor IDs from appointments
            for a in appointments_dict.values():
                if a.doctor_id:
                    doctor_ids.add(a.doctor_id)
            # Re-fetch doctors to ensure appointment doctors are in doctors_dict
            doctors_dict = {d.id: d for d in Doctor.objects.filter(id__in=list(doctor_ids))}

        # Bulk fetch BillingItems and treatments for all bills
        bill_ids = [b.id for b in bills_list]
        billing_items_by_bill = defaultdict(list)
        if bill_ids:
            billing_items = BillingItem.objects.filter(billing_id__in=bill_ids)
            # Fetch all treatment objects referenced by these items
            treatment_ids = set(item.treatment_id for item in billing_items if item.treatment_id)
            treatments_dict = {t.id: t for t in TreatmentMaster.objects.filter(id__in=list(treatment_ids))} if treatment_ids else {}
            
            for item in billing_items:
                t = treatments_dict.get(item.treatment_id)
                billing_items_by_bill[item.billing_id].append({
                    "name": t.name if t else "Unknown",
                    "qty": item.qty,
                    "price": float(item.price) if item.price is not None else 0.0,
                    "fee_type": t.fee_type if t else "Default"
                })

        # Unified response
        results = []
        for b in bills_list:
            p = patients_dict.get(b.patient_id)
            d = doctors_dict.get(b.doctor_id)
            items = billing_items_by_bill.get(b.id, [])
            
            results.append({
                "id": str(b.id),
                "patient_id": str(b.patient_id) if b.patient_id else None,
                "created_at": b.created_at,
                "patient_name": p.name if p else "Unknown",
                "patient_phone": p.phone if p else "",
                "total_amount": float(b.total_amount) if b.total_amount is not None else 0.0,
                "paid_amount": float(b.paid_amount) if b.paid_amount is not None else 0.0,
                "balance_amount": float(b.balance_amount) if b.balance_amount is not None else 0.0,
                "payment_method": b.payment_method,
                "status": b.status,
                "type": "Billing",
                "items": items,
                "doctor_name": d.name if d else "",
                "notes": b.notes or "",
                "bill_type": b.bill_type,
            })
            
        for p in legacy_payments_list:
            pt = patients_dict.get(p.patient_id)
            doc_name = ""
            v = visits_dict.get(p.visit_id)
            if v and v.appointment_id:
                appt = appointments_dict.get(v.appointment_id)
                if appt and appt.doctor_id:
                    d = doctors_dict.get(appt.doctor_id)
                    if d:
                        doc_name = d.name
                        
            results.append({
                "id": str(p.id),
                "patient_id": str(p.patient_id) if p.patient_id else None,
                "created_at": p.created_at,
                "patient_name": pt.name if pt else "Unknown",
                "patient_phone": pt.phone if pt else "",
                "total_amount": float(p.total_amount) if p.total_amount is not None else 0.0,
                "paid_amount": float(p.paid_amount) if p.paid_amount is not None else 0.0,
                "balance_amount": float(p.balance_amount) if p.balance_amount is not None else 0.0,
                "payment_method": p.payment_method,
                "status": p.status,
                "type": "Payment",
                "items": [],
                "doctor_name": doc_name,
                "notes": "",
                "bill_type": "Clinical",
            })
        
        results.sort(key=lambda x: x['created_at'], reverse=True)
        return Response(results)


def acquire_slot_lock(doctor_id, appt_date, appt_time_str):
    """
    Acquires an atomic database reservation lock for (doctor_id, date, time) using MongoDB's unique _id guarantee.
    Guarantees 100% thread-safe concurrency without race conditions under parallel requests.
    """
    if not doctor_id or not appt_date or not appt_time_str:
        return True, None
    from django.db import connections
    from pymongo.errors import DuplicateKeyError
    db = connections['default'].database
    time_key = str(appt_time_str).strip()[:5]
    date_key = str(appt_date).strip()
    lock_id = f"slot_{doctor_id}_{date_key}_{time_key}"
    try:
        db['patients_slot_lock'].insert_one({
            '_id': lock_id,
            'doctor_id': str(doctor_id),
            'date': date_key,
            'time': time_key,
            'created_at': timezone.now()
        })
        return True, lock_id
    except DuplicateKeyError:
        return False, lock_id

def release_slot_lock(doctor_id, appt_date, appt_time_str):
    """
    Releases an atomic slot lock when an appointment is cancelled, rescheduled, or validation fails.
    """
    if not doctor_id or not appt_date or not appt_time_str:
        return
    from django.db import connections
    db = connections['default'].database
    time_key = str(appt_time_str).strip()[:5]
    date_key = str(appt_date).strip()
    lock_id = f"slot_{doctor_id}_{date_key}_{time_key}"
    db['patients_slot_lock'].delete_one({'_id': lock_id})


# --- APPOINTMENT ---
class AppointmentCreateView(APIView):
    def post(self, request):
        scope = get_request_scope(request)
        doc_id = request.data.get('doctor')
        appt_date_str = request.data.get('date')
        appt_time_str = request.data.get('time')

        branch_id = request.data.get('branch') or request.headers.get('X-Branch-Id') or (scope.branch.id if scope.branch else None)
        branch = Branch.objects.filter(pk=branch_id).first() if branch_id else (scope.branch or Branch.objects.first())

        doctor = None
        if doc_id:
            doctor = Doctor.objects.filter(id=doc_id).first()
            if not doctor:
                return Response({'error': 'Selected doctor does not exist.'}, status=400)

        # Doctor-to-branch authorization check
        if doctor and branch:
            if not doctor.is_branch_assigned(branch) and doctor.primary_branch:
                return Response({'error': f'Dr. {doctor.name} is not assigned to {branch.name}.'}, status=400)

        lock_acquired = False
        if doctor and appt_date_str and appt_time_str:
            try:
                target_date = datetime.strptime(str(appt_date_str), '%Y-%m-%d').date()
            except Exception:
                return Response({'error': 'Invalid date format (YYYY-MM-DD required).'}, status=400)

            raw_time = str(appt_time_str).strip()
            if len(raw_time.split(':')) == 2:
                raw_time += ':00'
            try:
                target_time = datetime.strptime(raw_time, '%H:%M:%S').time()
            except Exception:
                return Response({'error': 'Invalid time format.'}, status=400)

            # 1. Double Booking Check (Cross-Branch: Doctor cannot be booked in two places at once)
            existing_conflict = Appointment.objects.filter(
                doctor=doctor,
                date=target_date,
                time=target_time
            ).exclude(status__in=['Cancelled', 'Rescheduled'])
            if existing_conflict.exists():
                conflict_appt = existing_conflict.first()
                loc_info = f" at {conflict_appt.branch.name}" if conflict_appt.branch else ""
                return Response({
                    'error': f'Slot {raw_time[:5]} on {target_date} is already booked for Dr. {doctor.name}{loc_info}. Please select an available slot.'
                }, status=status.HTTP_409_CONFLICT)

            # Atomic database lock acquisition for true concurrency safety
            lock_acquired, lock_id = acquire_slot_lock(doctor.id, target_date, raw_time)
            if not lock_acquired:
                return Response({
                    'error': f'Slot {raw_time[:5]} on {target_date} is already booked for Dr. {doctor.name}. Please select an available slot.'
                }, status=status.HTTP_409_CONFLICT)

            # 2. Check Doctor Leave / Blocked Time
            overrides = DoctorDateOverride.objects.filter(
                doctor=doctor,
                date=target_date,
                is_active=True,
                status='APPROVED'
            )
            for ov in overrides:
                if ov.override_type in ['LEAVE', 'UNAVAILABLE'] and not ov.start_time:
                    reason_msg = f" (Reason: {ov.reason})" if ov.reason else ""
                    return Response({
                        'error': f'Dr. {doctor.name} is on leave/unavailable on {target_date}{reason_msg}. No appointments can be booked.'
                    }, status=400)
                elif ov.override_type in ['LEAVE', 'UNAVAILABLE', 'BLOCKED'] and ov.start_time and ov.end_time:
                    if ov.start_time <= target_time < ov.end_time:
                        return Response({
                            'error': f'Dr. {doctor.name} is blocked/unavailable between {ov.start_time} and {ov.end_time} on {target_date}.'
                        }, status=400)

            # 3. Check Active Approved Schedule for THIS branch
            avail_override = overrides.filter(override_type='AVAILABLE').first()
            day_of_week = target_date.weekday()
            if not avail_override:
                sched_filter = {
                    'doctor': doctor,
                    'day_of_week': day_of_week,
                    'is_active': True,
                    'status': 'APPROVED'
                }
                if branch:
                    sched_filter['branch'] = branch
                active_schedules = DoctorSchedule.objects.filter(**sched_filter)
                if not active_schedules.exists():
                    if lock_acquired: release_slot_lock(doctor.id, target_date, raw_time)
                    branch_name_str = f" at {branch.name}" if branch else ""
                    return Response({
                        'error': f'Dr. {doctor.name} has no approved active schedule{branch_name_str} on {target_date.strftime("%A")}s.'
                    }, status=400)

                within_session = False
                for s in active_schedules:
                    if s.start_time <= target_time < s.end_time:
                        within_session = True
                        break
                if not within_session:
                    if lock_acquired: release_slot_lock(doctor.id, target_date, raw_time)
                    return Response({
                        'error': f'Requested time {raw_time[:5]} is outside Dr. {doctor.name}\'s approved working hours on {target_date.strftime("%A")}.'
                    }, status=400)
            else:
                if avail_override.start_time and avail_override.end_time:
                    if not (avail_override.start_time <= target_time < avail_override.end_time):
                        if lock_acquired: release_slot_lock(doctor.id, target_date, raw_time)
                        return Response({
                            'error': f'Requested time is outside Dr. {doctor.name}\'s special working hours on {target_date}.'
                        }, status=400)

        data = request.data.copy()
        if branch:
            data['branch'] = str(branch.id)
            data['company'] = str(branch.company_id) if branch.company_id else None
        elif scope.company:
            data['company'] = str(scope.company.id)

        serializer = AppointmentSerializer(data=data)
        if serializer.is_valid():
            try:
                appt = serializer.save()
            except Exception as exc:
                if lock_acquired: release_slot_lock(doctor.id, target_date, raw_time)
                err_str = str(exc).lower()
                if 'duplicate' in err_str or 'e11000' in err_str:
                    doc_name = doctor.name if doctor else "Doctor"
                    time_label = raw_time[:5] if 'raw_time' in locals() else (appt_time_str or '')
                    date_label = str(target_date) if 'target_date' in locals() else (appt_date_str or '')
                    return Response({
                        'error': f'Slot {time_label} on {date_label} is already booked for Dr. {doc_name}. Please select an available slot.'
                    }, status=status.HTTP_409_CONFLICT)
                raise exc

            paid_amount = request.data.get('paid_amount', 0)
            payment_method = request.data.get('payment_method', 'Cash')

            # If a payment is recorded or it's a walk-in (Waiting), start a visit record
            if Decimal(str(paid_amount)) > 0 or appt.status == 'Waiting':
                visit = Visit.objects.create(patient=appt.patient, appointment=appt, company=branch.company if branch else None, branch=branch)
                payment, _ = Payment.objects.get_or_create(visit=visit, defaults={'patient': appt.patient, 'company': branch.company if branch else None, 'branch': branch})
                payment.paid_amount = Decimal(str(paid_amount))
                payment.payment_method = payment_method
                payment.company = branch.company if branch else None
                payment.branch = branch
                payment.save()

            # Trigger WhatsApp/SMS Notification
            send_appointment_communication(appt, template_type="Confirmation")

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        if lock_acquired: release_slot_lock(doctor.id, target_date, raw_time)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AppointmentByPatientView(APIView):
    def get(self, request, patient_id):
        appts = Appointment.objects.filter(patient_id=patient_id).order_by('-date', '-time')
        serializer = AppointmentSerializer(appts, many=True)
        return Response(serializer.data)


class TodayAppointmentListView(APIView):
    """Today's appointments — used by TodayPatients page and AppointmentStatus widget."""
    def get(self, request):
        scope = get_request_scope(request)
        today = timezone.localtime(timezone.now()).date()
        appts = Appointment.objects.filter(date=today).exclude(status__in=['Rescheduled', 'Cancelled']).order_by('time')

        if scope.company and not scope.is_super:
            appts = appts.filter(company=scope.company)

        branch_id = request.query_params.get('branch_id') or request.headers.get('X-Branch-Id')
        if branch_id and branch_id != 'all':
            appts = appts.filter(branch_id=branch_id)
        elif not scope.is_company_admin and scope.branch:
            appts = appts.filter(branch=scope.branch)

        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            # Strict: only show this doctor's own appointments, not unassigned ones
            appts = appts.filter(doctor=doctor_profile)

        serializer = AppointmentSerializer(appts, many=True)
        return Response(serializer.data)


class AllAppointmentListView(APIView):
    """All appointments with optional filters for the Appointments page."""
    def get(self, request):
        scope = get_request_scope(request)
        today = timezone.localtime(timezone.now()).date()
        status_filter = request.query_params.get('status', '')
        date_filter = request.query_params.get('date', '')
        q = request.query_params.get('q', '')

        appts = Appointment.objects.all().order_by('time', 'date')

        if scope.company and not scope.is_super:
            appts = appts.filter(company=scope.company)

        branch_id = request.query_params.get('branch_id') or request.headers.get('X-Branch-Id')
        if branch_id and branch_id != 'all':
            appts = appts.filter(branch_id=branch_id)
        elif not scope.is_company_admin and scope.branch:
            appts = appts.filter(branch=scope.branch)

        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            # Strict: only show this doctor's own appointments, not unassigned ones
            appts = appts.filter(doctor=doctor_profile)

        if q:
            appts = appts.filter(
                Q(patient__name__icontains=q) | Q(patient__phone__icontains=q)
            )

        if date_filter:
            is_today = (date_filter == str(today))

            if status_filter in ('', 'all'):
                # Show all appointments for the selected date
                appts = appts.filter(date=date_filter)
            elif status_filter == 'upcoming':
                appts = appts.filter(date=date_filter).exclude(status__in=['Cancelled', 'Completed', 'Missed'])
            elif status_filter == 'missed':
                appts = appts.filter(date=date_filter, status='Missed')
            elif status_filter == 'completed':
                appts = appts.filter(date=date_filter, status='Completed')
            elif status_filter == 'rescheduled':
                appts = appts.filter(date=date_filter, status='Rescheduled')
            elif status_filter == 'follow-up':
                appts = appts.filter(date=date_filter, status='Follow-up')
            elif status_filter == 'cancelled':
                appts = appts.filter(date=date_filter, status='Cancelled')
            else:
                appts = appts.filter(date=date_filter)
        else:
            # No date filter — legacy behaviour
            if status_filter == 'today':
                appts = appts.filter(date=today).exclude(status__in=['Rescheduled', 'Cancelled'])
            elif status_filter == 'upcoming':
                appts = appts.filter(date=today, status__in=['Scheduled', 'Follow-up'])
            elif status_filter == 'missed':
                appts = appts.filter(date__lt=today).exclude(status__in=['Completed', 'Rescheduled', 'Cancelled', 'Follow-up'])
            elif status_filter == 'completed':
                appts = appts.filter(status='Completed').exclude(date=today)
            elif status_filter == 'rescheduled':
                appts = appts.filter(status='Rescheduled').order_by('-rescheduled_to_date', '-rescheduled_to_time')
            elif status_filter == 'follow-up':
                appts = appts.filter(status='Follow-up').exclude(date=today)
            elif status_filter == 'cancelled':
                appts = appts.filter(status='Cancelled')
            elif status_filter == 'all':
                appts = appts.exclude(date=today)

        serializer = AppointmentSerializer(appts, many=True)
        return Response(serializer.data)


class AppointmentStatsView(APIView):
    def get(self, request):
        today = timezone.localtime(timezone.now()).date()
        today_appts = Appointment.objects.filter(date=today)
        
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            today_appts = today_appts.filter(doctor=doctor_profile)

        waiting_count  = today_appts.filter(status='Waiting').count()
        engaged_count  = today_appts.filter(status='Engaged').count()
        completed_count = today_appts.filter(status='Completed').count()
        
        # Comprehensive counts for tabs
        # Financial stats
        from django.db.models import Sum
        from decimal import Decimal
        
        # 1. Billing model totals
        b_qs = Billing.objects.all()
        if doctor_profile:
            b_qs = b_qs.filter(doctor=doctor_profile)
        
        b_sum = b_qs.aggregate(
            total=Sum('total_amount'),
            paid=Sum('paid_amount')
        )
        b_total = b_sum['total'] or Decimal('0.00')
        b_paid = b_sum['paid'] or Decimal('0.00')

        # 2. Legacy Payment model totals (only those not linked to a Billing record)
        p_qs = Payment.objects.exclude(visit__billings__isnull=False)
        if doctor_profile:
            p_qs = p_qs.filter(visit__appointment__doctor=doctor_profile)

        p_sum = p_qs.aggregate(
            total=Sum('total_amount'),
            paid=Sum('paid_amount')
        )
        p_total = p_sum['total'] or Decimal('0.00')
        p_paid = p_sum['paid'] or Decimal('0.00')

        overall_total = b_total + p_total
        overall_paid = b_paid + p_paid
        overall_debt = overall_total - overall_paid

        total_patients = Patient.objects.filter(appointments__doctor=doctor_profile).distinct().count() if doctor_profile else Patient.objects.count()
        total_appts = Appointment.objects.filter(doctor=doctor_profile).count() if doctor_profile else Appointment.objects.count()
        
        base_appts = Appointment.objects.filter(doctor=doctor_profile) if doctor_profile else Appointment.objects.all()

        from datetime import timedelta
        from django.db.models import Count

        # Weekly trend for last 7 days
        weekly_trend = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            day_appts = base_appts.filter(date=d).exclude(status__in=['Cancelled', 'Rescheduled'])
            appts_count = day_appts.count()
            patients_count = day_appts.values('patient').distinct().count()
            weekly_trend.append({
                "name": d.strftime('%a'),
                "patients": patients_count,
                "appointments": appts_count,
            })

        # Treatments by type (Top 4)
        from .models import TreatmentMaster
        treatment_qs = TreatmentMaster.objects.filter(billingitem__isnull=False)
        if doctor_profile:
            treatment_qs = treatment_qs.filter(billingitem__billing__doctor=doctor_profile)
        
        top_treatments = treatment_qs.annotate(count=Count('billingitem')).order_by('-count')[:4]
        
        colors = ['#3b82f6', '#10b981', '#f59e0b', '#6366f1']
        treatments_data = []
        for idx, t in enumerate(top_treatments):
            treatments_data.append({
                "name": t.name,
                "value": t.count,
                "color": colors[idx % len(colors)]
            })
        
        if not treatments_data:
            treatments_data = [
                {"name": "No data", "value": 1, "color": "#cbd5e1"}
            ]

        return Response({
            "total_patients":  total_patients,
            "total_appointments": total_appts,
            "today_total":     today_appts.exclude(status__in=['Rescheduled', 'Cancelled']).count(),
            "today_queue":     waiting_count + engaged_count + completed_count,
            "upcoming":        today_appts.filter(status__in=['Scheduled', 'Follow-up']).count(),
            "missed":          base_appts.filter(date__lt=today).exclude(status__in=['Completed', 'Rescheduled', 'Cancelled', 'Follow-up']).count(),
            "scheduled":       today_appts.filter(status='Scheduled').count(),
            "waiting":         waiting_count,
            "engaged":         engaged_count,
            "completed":       completed_count,
            "rescheduled":     base_appts.filter(status='Rescheduled').count(),
            "follow_up":       base_appts.filter(status='Follow-up').count(),
            "cancelled":       base_appts.filter(status='Cancelled').count(),
            "follow_up_expected_today": ClinicalNotes.objects.filter(appointment__doctor=doctor_profile, follow_up_date=today, follow_up_status='Pending').count() if doctor_profile else ClinicalNotes.objects.filter(follow_up_date=today, follow_up_status='Pending').count(),
            # Financials
            "total_revenue": float(overall_total),
            "total_collected": float(overall_paid),
            "total_debt": float(max(0, overall_debt)),
            "weekly_trend": weekly_trend,
            "treatments_by_type": treatments_data,
        })


class AppointmentStatusUpdateView(APIView):
    def patch(self, request, pk):
        appt = get_object_or_404(Appointment, pk=pk)
        scope = get_request_scope(request)
        if appt.branch_id and not scope.has_access_to_branch(appt.branch_id):
            return Response({'error': 'You do not have permission to modify appointments in this branch.'}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status', appt.status)
        new_date = request.data.get('date', appt.date)
        new_time = request.data.get('time', appt.time)
        new_doc_id = request.data.get('doctor')
        
        target_doctor = appt.doctor
        if new_doc_id is not None:
            if new_doc_id:
                target_doctor = Doctor.objects.filter(id=new_doc_id).first()
                if not target_doctor:
                    return Response({'error': 'Selected doctor does not exist.'}, status=400)
            else:
                target_doctor = None

        old_doc_id = appt.doctor_id
        old_date = appt.date
        old_time = appt.time

        # If date, time, or doctor is being updated and appointment is not cancelled
        if new_status not in ['Cancelled', 'Rescheduled'] and target_doctor and new_date and new_time:
            raw_time = str(new_time).strip()
            if len(raw_time.split(':')) == 2:
                raw_time += ':00'
            try:
                target_t = datetime.strptime(raw_time, '%H:%M:%S').time() if isinstance(raw_time, str) else new_time
            except Exception:
                target_t = new_time
            try:
                target_d = datetime.strptime(str(new_date), '%Y-%m-%d').date() if isinstance(new_date, str) else new_date
            except Exception:
                target_d = new_date

            # Double booking check (exclude current appointment)
            conflict = Appointment.objects.filter(
                doctor=target_doctor,
                date=target_d,
                time=target_t
            ).exclude(pk=appt.pk).exclude(status__in=['Cancelled', 'Rescheduled'])
            if conflict.exists():
                return Response({
                    'error': f'Slot {str(target_t)[:5]} on {target_d} is already booked for Dr. {target_doctor.name}.'
                }, status=status.HTTP_409_CONFLICT)

        # Handle atomic slot lock release / re-acquisition
        if new_status in ['Cancelled', 'Rescheduled']:
            release_slot_lock(old_doc_id, old_date, old_time)
        elif (target_doctor != appt.doctor or str(new_date) != str(appt.date) or str(new_time)[:5] != str(appt.time)[:5]):
            if target_doctor and new_date and new_time:
                locked, _ = acquire_slot_lock(target_doctor.id, new_date, new_time)
                if not locked:
                    return Response({
                        'error': f'Slot {str(new_time)[:5]} on {new_date} is already booked or reserved.'
                    }, status=status.HTTP_409_CONFLICT)
                release_slot_lock(old_doc_id, old_date, old_time)

        appt.status = new_status
        if 'date' in request.data and request.data['date']:
            appt.date = request.data['date']
        if 'time' in request.data and request.data['time']:
            appt.time = request.data['time']
        if 'rescheduled_to_date' in request.data:
            appt.rescheduled_to_date = request.data['rescheduled_to_date'] or None
        if 'rescheduled_to_time' in request.data:
            appt.rescheduled_to_time = request.data['rescheduled_to_time'] or None
        if new_doc_id is not None:
            appt.doctor = target_doctor

        appt.save()
        return Response(AppointmentSerializer(appt).data)


class MoveAppointmentToTodayView(APIView):
    """Move a future/past appointment to today and set status = Waiting.
       Automatically creates a Visit and Payment record for the appointment."""
    def post(self, request, pk):
        appt = get_object_or_404(Appointment, pk=pk)
        local_now = timezone.localtime(timezone.now())
        appt.date   = local_now.date()
        appt.time   = local_now.time()
        appt.status = 'Waiting'
        appt.save()

        # Ensure Visit exists
        visit, _ = Visit.objects.get_or_create(
            patient=appt.patient,
            appointment=appt,
        )
        # Ensure Payment exists
        Payment.objects.get_or_create(
            visit=visit,
            defaults={'patient': appt.patient}
        )
        return Response(AppointmentSerializer(appt).data)


class PatientBillCreateView(APIView):
    """Create a brand-new bill for a patient directly from the Bills page.
       Creates Visit + Billing + Payment in one shot."""
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
        if denied:
            return denied

        patient_id     = request.data.get('patient_id')
        total_amount_raw   = request.data.get('total_amount', 0)
        paid_amount_raw    = request.data.get('paid_amount', 0)
        payment_method = request.data.get('payment_method', 'Cash')
        doctor_id      = request.data.get('doctor_id')

        if not patient_id:
            return Response({'error': 'patient_id is required'}, status=400)

        try:
            total_amt = Decimal(str(total_amount_raw or 0))
            paid_amt = Decimal(str(paid_amount_raw or 0))
        except Exception:
            return Response({'error': 'Invalid numerical amount.'}, status=400)

        if total_amt < Decimal('0.00'):
            return Response({'error': 'Total amount cannot be negative.'}, status=400)
        if paid_amt < Decimal('0.00'):
            return Response({'error': 'Paid amount cannot be negative.'}, status=400)
        if total_amt > Decimal('0.00') and paid_amt > total_amt:
            return Response({'error': f'Paid amount (₹{paid_amt}) cannot exceed total bill amount (₹{total_amt}).'}, status=400)

        patient = get_object_or_404(Patient, pk=patient_id)
        doctor  = Doctor.objects.filter(id=doctor_id).first() if doctor_id else Doctor.objects.first()

        # Always create a fresh appointment + visit for each bill
        appt = Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            date=timezone.localtime(timezone.now()).date(),
            time=timezone.now().time(),
            status='Completed',
        )
        visit = Visit.objects.create(patient=patient, appointment=appt)
        
        billing = Billing.objects.create(
            patient=patient,
            visit=visit,
            doctor=doctor,
            total_amount=total_amt,
            paid_amount=paid_amt,
            payment_method=payment_method,
            bill_type='Clinical',
            is_invoice=True
        )

        payment = Payment.objects.create(
            patient=patient,
            visit=visit,
            doctor=doctor,
            total_amount=total_amt,
            paid_amount=paid_amt,
            payment_method=payment_method,
        )
        return Response(BillingSerializer(billing).data, status=201)


# --- VISIT ---
class VisitGetOrCreateView(APIView):
    def post(self, request):
        appointment_id = request.data.get('appointment_id')
        patient_id = request.data.get('patient_id')

        if str(appointment_id or '').strip().lower() in ['', 'null', 'undefined', 'new']:
            appointment_id = None
        if str(patient_id or '').strip().lower() in ['', 'null', 'undefined', 'new']:
            patient_id = None

        if appointment_id:
            appointment = Appointment.objects.filter(id=appointment_id).first()
            if appointment:
                patient = appointment.patient
                today = timezone.now().date()
                start_of_day = timezone.make_aware(datetime.combine(today, time.min))
                end_of_day = timezone.make_aware(datetime.combine(today, time.max))
                
                visit = Visit.objects.filter(
                    patient=patient,
                    appointment=appointment,
                    created_at__range=(start_of_day, end_of_day)
                ).first()

                if not visit:
                    visit = Visit.objects.create(patient=patient, appointment=appointment)
            elif patient_id:
                patient = get_object_or_404(Patient, id=patient_id)
                today = timezone.now().date()
                start_of_day = timezone.make_aware(datetime.combine(today, time.min))
                end_of_day = timezone.make_aware(datetime.combine(today, time.max))
                visit = Visit.objects.filter(
                    patient=patient,
                    appointment__isnull=True,
                    created_at__range=(start_of_day, end_of_day)
                ).first()
                if not visit:
                    visit = Visit.objects.create(patient=patient, appointment=None)
                appointment = None
            else:
                return Response({"error": "Appointment not found."}, status=404)
        elif patient_id:
            patient = get_object_or_404(Patient, id=patient_id)
            
            today = timezone.now().date()
            start_of_day = timezone.make_aware(datetime.combine(today, time.min))
            end_of_day = timezone.make_aware(datetime.combine(today, time.max))

            # Find an existing standalone visit for today
            visit = Visit.objects.filter(
                patient=patient,
                appointment__isnull=True,
                created_at__range=(start_of_day, end_of_day)
            ).first()
            
            if not visit:
                visit = Visit.objects.create(patient=patient, appointment=None)
            appointment = None
        else:
            return Response({"error": "appointment_id or patient_id is required"}, status=400)

        payment, _ = Payment.objects.get_or_create(visit=visit, defaults={'patient': patient})

        return Response({
            'visit_id': visit.id,
            'appointment_id': appointment.id if appointment else None,
            'payment_id': payment.id,
            'message': 'Visit and Appointment ready'
        }, status=200)


class TodayVisitListView(APIView):
    def get(self, request):
        today = timezone.localtime(timezone.now()).date()
        start_of_day = timezone.make_aware(datetime.combine(today, time.min))
        end_of_day = timezone.make_aware(datetime.combine(today, time.max))
        visits = Visit.objects.filter(created_at__range=(start_of_day, end_of_day)).order_by('-created_at')
        
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            visits = visits.filter(appointment__doctor=doctor_profile)
            
        serializer = VisitSerializer(visits, many=True)
        return Response(serializer.data)


class VisitDetailByAppointmentView(APIView):
    def get(self, request, appointment_id):
        visit = Visit.objects.filter(appointment_id=appointment_id).first()
        if not visit:
            return Response({"detail": "No visit found"}, status=404)
        serializer = VisitSerializer(visit)
        return Response(serializer.data)


# --- CLINICAL NOTES ---
class PatientClinicalHistoryView(APIView):
    def get(self, request, patient_id):
        patient = Patient.objects.filter(id=patient_id).first()
        if not patient:
            return Response({"detail": "Patient not found"}, status=404)
            
        appointments = Appointment.objects.filter(patient=patient).values_list('id', flat=True)
        notes = ClinicalNotes.objects.filter(appointment_id__in=appointments).order_by('-appointment__date')
        
        result = []
        for note in notes:
            # Fetch associated Visit for treatments and RVGs
            visit = Visit.objects.filter(appointment=note.appointment).first()
            
            treatments = []
            rvgs = []
            if visit:
                # Treatments
                records = TreatmentRecord.objects.filter(visit=visit)
                for rec in records:
                    treatments.append({
                        "id": rec.id,
                        "treatment": rec.treatment.name if rec.treatment else "",
                        "tooth_number": rec.tooth_number,
                        "status": rec.status,
                        "doctor": rec.doctor.name if rec.doctor else "Unknown",
                        "notes": rec.notes
                    })
                # RVGs
                images = PatientImage.objects.filter(visit=visit)
                for img in images:
                    rvgs.append({
                        "id": img.id,
                        "file_url": img.image.url if img.image else "",
                        "type": img.image_type,
                        "tooth": img.tooth_number
                    })

            result.append({
                "appointment_id": note.appointment.id,
                "date": note.appointment.date,
                "doctor": note.appointment.doctor.name if note.appointment.doctor else "Unknown",
                "chief_complaint": note.chief_complaint or (", ".join(note.complaints) if note.complaints else ""),
                "medical_history": note.medical_history or [],
                "dental_history": note.dental_history or [],
                "observations": note.observations or [],
                "diagnosis": note.diagnosis or [],
                "notes": note.notes or "",
                "treatment_plan": note.treatment_plan or "",
                "follow_up": note.follow_up_date,
                "treatments": treatments,
                "rvgs": rvgs
            })
            
        return Response(result)


class PatientTreatmentHistoryView(APIView):
    def get(self, request, patient_id):
        patient = Patient.objects.filter(id=patient_id).first()
        if not patient:
            return Response({"detail": "Patient not found"}, status=404)
            
        records = TreatmentRecord.objects.filter(visit__patient=patient).order_by('-visit__created_at')
        
        result = []
        for rec in records:
            # We can also get diagnosis from the associated ClinicalNotes
            clinical_note = ClinicalNotes.objects.filter(appointment=rec.visit.appointment).first()
            diagnosis = clinical_note.diagnosis if clinical_note and clinical_note.diagnosis else []
            
            rec_doc = rec.doctor or (rec.visit.appointment.doctor if (rec.visit and rec.visit.appointment) else None)
            result.append({
                "id": rec.id,
                "visit_id": rec.visit.id if rec.visit else None,
                "date": rec.visit.created_at.date() if rec.visit else None,
                "tooth_number": rec.tooth_number,
                "diagnosis": diagnosis,
                "treatment": rec.treatment.name if rec.treatment else "",
                "doctor": rec_doc.name if rec_doc else "Unassigned",
                "doctor_id": str(rec_doc.id) if rec_doc else None,
                "status": rec.status,
                "notes": rec.notes
            })
            
        return Response(result)

class ClinicalNotesDetailView(APIView):
    def get(self, request, appointment_id):
        appointment = Appointment.objects.filter(id=appointment_id).first()
        
        if not appointment:
            # Maybe it's a patient ID
            patient = Patient.objects.filter(id=appointment_id).first()
            if patient:
                appointment = Appointment.objects.filter(patient=patient).order_by('-date').first()
                
        if not appointment:
            return Response({"detail": "Appointment not found"}, status=404)
        notes = ClinicalNotes.objects.filter(appointment=appointment).first()
        
        patient_id = appointment.patient.id
        
        if not notes:
            return Response({
                "appointment": appointment.id,
                "patient": patient_id,
                "selected_teeth": [],
                "complaints": [],
                "observations": [],
                "investigations": [],
                "diagnosis": [],
                "medical_history": [],
                "notes": "",
                "treatment_plan": "",
            })

        return Response({
            "appointment": notes.appointment.id,
            "patient": patient_id,
            "selected_teeth": notes.selected_teeth or [],
            "complaints": notes.complaints or [],
            "observations": notes.observations or [],
            "investigations": notes.investigations or [],
            "diagnosis": notes.diagnosis or [],
            "medical_history": notes.medical_history or [],
            "dental_history": notes.dental_history or [],
            "allergies": notes.allergies or [],
            "ongoing_medications": notes.ongoing_medications or [],
            "chief_complaint": notes.chief_complaint or "",
            "patient_type": notes.patient_type or "Adult",
            "notes": notes.notes or "",
            "treatment_plan": notes.treatment_plan or "",
            "follow_up_date": notes.follow_up_date,
            "follow_up_note": notes.follow_up_note or "",
            "follow_up_status": notes.follow_up_status,
            "treatments": [t.id for t in notes.treatments.all()] if hasattr(notes, 'treatments') else []
        })


class ClinicalNotesSaveView(APIView):
    def post(self, request):
        appointment_id = request.data.get('appointment_id')
        patient_id = request.data.get('patient_id')
        doctor_id = request.data.get('doctor_id')
        
        if not appointment_id and not patient_id:
            return Response({"error": "appointment_id or patient_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        if appointment_id:
            appointment = get_object_or_404(Appointment, id=appointment_id)
            if doctor_id:
                doc_obj = Doctor.objects.filter(id=doctor_id).first()
                if doc_obj and appointment.doctor != doc_obj:
                    appointment.doctor = doc_obj
                    appointment.save()
        else:
            patient = get_object_or_404(Patient, id=patient_id)
            appointment = Appointment.objects.filter(
                patient=patient,
                date=timezone.now().date()
            ).first()
            if not appointment:
                doc_obj = Doctor.objects.filter(id=doctor_id).first() if doctor_id else Doctor.objects.first()
                appointment = Appointment.objects.create(
                    patient=patient,
                    doctor=doc_obj,
                    date=timezone.now().date(),
                    time=timezone.now().time(),
                    status='Completed'
                )
            elif doctor_id and not appointment.doctor:
                doc_obj = Doctor.objects.filter(id=doctor_id).first()
                if doc_obj:
                    appointment.doctor = doc_obj
                    appointment.save()

        old_follow_up_date = None
        try:
            existing_note = ClinicalNotes.objects.filter(appointment=appointment).first()
            if existing_note:
                old_follow_up_date = existing_note.follow_up_date
        except Exception:
            pass

        defaults = {
            'selected_teeth': request.data.get('selected_teeth', []),
            'complaints': request.data.get('complaints', []),
            'observations': request.data.get('observations', []),
            'investigations': request.data.get('investigations', []),
            'diagnosis': request.data.get('diagnosis', []),
            'medical_history': request.data.get('medical_history', []),
            'dental_history': request.data.get('dental_history', []),
            'allergies': request.data.get('allergies', []),
            'ongoing_medications': request.data.get('ongoing_medications', []),
            'chief_complaint': request.data.get('chief_complaint', ""),
            'patient_type': request.data.get('patient_type', "Adult"),
            'notes': request.data.get('notes', ""),
            'treatment_plan': request.data.get('treatment_plan', ""),
            'follow_up_date': request.data.get('follow_up_date') or None,
            'follow_up_note': request.data.get('follow_up_note', ""),
            'follow_up_status': request.data.get('follow_up_status', 'Pending')
        }

        notes, created = ClinicalNotes.objects.update_or_create(
            appointment=appointment,
            defaults=defaults
        )
        
        treatments = request.data.get('treatments', [])
        if treatments:
            notes.treatments.set(treatments)
        else:
            notes.treatments.clear()

        # Keep follow-up appointment in sync
        new_follow_up_date = defaults.get('follow_up_date')
        new_follow_up_status = defaults.get('follow_up_status', 'Pending')

        if new_follow_up_date and new_follow_up_status not in ['Completed', 'Missed']:
            appt = None
            if old_follow_up_date:
                appt = Appointment.objects.filter(
                    patient=appointment.patient,
                    date=old_follow_up_date,
                    status='Follow-up'
                ).first()
            
            if appt:
                appt.date = new_follow_up_date
                appt.doctor = appointment.doctor
                appt.save()
            else:
                Appointment.objects.get_or_create(
                    patient=appointment.patient,
                    date=new_follow_up_date,
                    status='Follow-up',
                    defaults={'doctor': appointment.doctor}
                )
        elif old_follow_up_date:
            appt = Appointment.objects.filter(
                patient=appointment.patient,
                date=old_follow_up_date,
                status='Follow-up'
            ).first()
            if appt:
                if new_follow_up_status in ['Completed', 'Missed']:
                    appt.status = new_follow_up_status
                    appt.save()
                else:
                    appt.delete()

        return Response({"message": "Saved successfully", "id": str(notes.id)})



# --- DROPDOWNS ---
class DropdownMasterListView(APIView):
    def get(self, request, type):
        from .models import DropdownMaster
        items = DropdownMaster.objects.filter(type=type).order_by('name')
        return Response([{"name": i.name} for i in items])

    def post(self, request, type):
        from .models import DropdownMaster
        name = request.data.get('name')
        if not name:
            return Response({"error": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)
        item, created = DropdownMaster.objects.get_or_create(type=type, name=name)
        return Response({"name": item.name}, status=status.HTTP_201_CREATED)

    def delete(self, request, type):
        from .models import DropdownMaster
        name = request.data.get('name')
        if not name:
            return Response({"error": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)
        item = DropdownMaster.objects.filter(type=type, name=name).first()
        if item:
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

class LabHeaderListView(APIView):
    def get(self, request):
        headers = LabHeader.objects.all()
        return Response(LabHeaderSerializer(headers, many=True).data)

    def post(self, request):
        serializer = LabHeaderSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LaboratoryListView(APIView):
    def get(self, request):
        labs = Laboratory.objects.all()
        return Response(LaboratorySerializer(labs, many=True).data)

    def post(self, request):
        serializer = LaboratorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LabTestMasterListView(APIView):
    def get(self, request):
        tests = LabTestMaster.objects.all()
        return Response(LabTestMasterSerializer(tests, many=True).data)

    def post(self, request):
        serializer = LabTestMasterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LabTestParameterView(APIView):
    def post(self, request):
        serializer = LabTestParameterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LabPackageListView(APIView):
    def get(self, request):
        packages = LabPackage.objects.all()
        return Response(LabPackageSerializer(packages, many=True).data)

    def post(self, request):
        serializer = LabPackageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# --- TREATMENT MASTER ---
class TreatmentMasterListView(APIView):
    def get(self, request):
        treatments = TreatmentMaster.objects.filter(is_active=True)
        serializer = TreatmentMasterSerializer(treatments, many=True)
        return Response(serializer.data)


class TreatmentMasterCreateView(APIView):
    def post(self, request):
        serializer = TreatmentMasterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TreatmentMasterUpdateView(APIView):
    def patch(self, request, pk):
        treatment = get_object_or_404(TreatmentMaster, pk=pk)
        serializer = TreatmentMasterSerializer(treatment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        treatment = get_object_or_404(TreatmentMaster, pk=pk)
        treatment.delete()
        return Response({'status': 'deleted'})



# --- TREATMENT RECORD ---
class TreatmentRecordAddView(APIView):
    def post(self, request):
        visit_id = request.data.get('visit')
        treatment_id = request.data.get('treatment')
        doctor_id = request.data.get('doctor_id')
        visit = get_object_or_404(Visit, id=visit_id)
        treatment_master = get_object_or_404(TreatmentMaster, id=treatment_id)
        doctor = Doctor.objects.filter(id=doctor_id).first() if doctor_id else None
        if not doctor and visit and visit.appointment and visit.appointment.doctor:
            doctor = visit.appointment.doctor
        tooth_number = request.data.get('tooth_number')
        record = TreatmentRecord.objects.create(
            visit=visit, treatment=treatment_master, price=treatment_master.price, doctor=doctor, tooth_number=tooth_number
        )
        try:
            payment = visit.payment
            payment.total_amount = Decimal(str(payment.total_amount)) + Decimal(str(record.price))
            payment.save()
        except Exception:
            pass
        return Response(TreatmentRecordSerializer(record).data, status=status.HTTP_201_CREATED)


class TreatmentRecordDeleteView(APIView):
    """Delete a treatment record, update linked billing, and restore pharmacy stock."""
    def delete(self, request, pk):
        from django.db import transaction as db_transaction
        record = get_object_or_404(TreatmentRecord, pk=pk)
        price = record.price
        visit = record.visit

        with db_transaction.atomic():
            # 1. Find and remove any matching BillingItem in this visit's billing
            linked_items = BillingItem.objects.filter(
                billing__visit=visit,
                treatment=record.treatment
            )
            for item in linked_items:
                # If pharmacy item, restore stock
                if item.treatment.name.startswith("Pharmacy: "):
                    med_name = item.treatment.name.replace("Pharmacy: ", "")
                    med = MedicineMaster.objects.filter(name__iexact=med_name).first()
                    if med:
                        med.stock_quantity += item.qty
                        med.save()
                billing = item.billing
                item.delete()
                # Recalculate billing total
                new_total = billing.items.aggregate(
                    total=Sum(models.F('price') * models.F('qty'))
                )['total'] or Decimal('0')
                billing.total_amount = new_total
                # Ensure paid_amount doesn't exceed new total
                if billing.paid_amount > new_total:
                    billing.paid_amount = new_total
                billing.balance_amount = billing.total_amount - billing.paid_amount
                # Update status
                if billing.paid_amount <= 0:
                    billing.status = 'Pending'
                elif billing.paid_amount < billing.total_amount:
                    billing.status = 'Partial'
                else:
                    billing.status = 'Paid'
                billing.save()

            # 2. Delete the treatment record itself
            record.delete()

        return Response({'status': 'deleted', 'message': 'Treatment removed and billing updated.'}, status=200)


# --- PAYMENT ---
class PaymentPayView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
        if denied:
            return denied

        record_type = request.data.get('type')
        try:
            amount_to_add = Decimal(str(request.data.get('amount', 0)))
        except Exception:
            return Response({'error': 'Invalid payment amount.'}, status=400)

        if amount_to_add <= Decimal('0.00'):
            return Response({'error': 'Payment amount must be greater than 0.'}, status=400)

        if record_type == 'Billing' or not record_type:
            bill = Billing.objects.filter(pk=pk).first()
            if bill:
                remaining_due = bill.total_amount - bill.paid_amount
                if bill.total_amount > Decimal('0.00') and amount_to_add > remaining_due:
                    return Response({'error': f'Payment amount (₹{amount_to_add}) exceeds remaining balance (₹{remaining_due}).'}, status=400)
                bill.paid_amount += amount_to_add
                if request.data.get('payment_method'):
                    bill.payment_method = request.data.get('payment_method')
                bill.save()
                return Response(BillingSerializer(bill).data)

        payment = get_object_or_404(Payment, pk=pk)
        remaining_due = payment.total_amount - payment.paid_amount
        if payment.total_amount > Decimal('0.00') and amount_to_add > remaining_due:
            return Response({'error': f'Payment amount (₹{amount_to_add}) exceeds remaining balance (₹{remaining_due}).'}, status=400)
        payment.paid_amount += amount_to_add
        if request.data.get('payment_method'):
            payment.payment_method = request.data.get('payment_method')
        payment.save()
        return Response(PaymentSerializer(payment).data)



# --- DOCTOR ---
class DoctorListView(APIView):
    def get(self, request):
        scope = get_request_scope(request)
        doctors = Doctor.objects.all()
        active_now = request.query_params.get('active_now')
        branch_id = request.query_params.get('branch_id') or request.headers.get('X-Branch-Id')

        if scope.company and not scope.is_super:
            doctors = doctors.filter(company=scope.company)

        if branch_id and branch_id != 'all':
            doctors = [d for d in doctors if d.is_branch_assigned(branch_id)]

        if active_now == 'true':
            from django.utils import timezone
            now = timezone.localtime()
            current_day = now.weekday()
            current_time = now.time()

            sched_filter = {
                'day_of_week': current_day,
                'start_time__lte': current_time,
                'end_time__gte': current_time,
                'is_active': True
            }
            if branch_id and branch_id != 'all':
                sched_filter['branch_id'] = branch_id

            active_doctor_ids = DoctorSchedule.objects.filter(**sched_filter).values_list('doctor_id', flat=True)
            doctors = doctors.filter(id__in=list(active_doctor_ids))

        serializer = DoctorSerializer(doctors, many=True)
        return Response(serializer.data)


class DoctorCreateView(APIView):
    def post(self, request):
        data = request.data
        username = data.get('username')
        password = data.get('password')
        
        try:
            with transaction.atomic():
                serializer = DoctorSerializer(data=data)
                if not serializer.is_valid():
                    return Response(serializer.errors, status=400)
                doctor = serializer.save()
                
                if username and password:
                    if User.objects.filter(username=username).exists():
                        raise Exception("Username already exists")
                    user = User.objects.create_user(username=username, password=password)
                    default_perms = ['add-patients', 'appointments', 'today-patients', 'search-patient', 'tele-medicine']
                    Staff.objects.create(
                        user=user, name=doctor.name, role='Doctor', phone=doctor.phone or '',
                        permissions=default_perms, doctor_profile=doctor
                    )
            return Response(DoctorSerializer(doctor).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

# --- FOLLOW-UPS ---
class FollowUpListView(APIView):
    def get(self, request):
        query = request.query_params.get('q', '')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status_filter = request.query_params.get('status', 'Pending')

        notes = ClinicalNotes.objects.filter(follow_up_date__isnull=False).all().order_by('follow_up_date')
        
        if status_filter and status_filter != 'all':
            notes = notes.filter(follow_up_status=status_filter)

        if start_date:
            notes = notes.filter(follow_up_date__gte=start_date)
        if end_date:
            notes = notes.filter(follow_up_date__lte=end_date)

        if query:
            notes = notes.filter(
                Q(appointment__patient__name__icontains=query) |
                Q(appointment__patient__phone__icontains=query) |
                Q(follow_up_note__icontains=query)
            )
            
        data = []
        for note in notes:
            if not note.appointment:
                continue
            patient = note.appointment.patient
            # Get latest treatments for context
            latest_treatments = []
            if hasattr(note.appointment, 'visit') and note.appointment.visit:
                latest_treatments = [tr.treatment.name for tr in note.appointment.visit.treatment_records.all()]
            
            data.append({
                "id": note.id,
                "patient_name": patient.name,
                "patient_phone": patient.phone,
                "patient_id": str(patient.id),
                "patient_balance": patient.total_balance,
                "patient_groups": [g.name for g in patient.groups.all()],
                "follow_up_date": note.follow_up_date,
                "follow_up_note": note.follow_up_note,
                "follow_up_status": note.follow_up_status,
                "appointment_id": str(note.appointment.id),
                "last_visit_date": note.appointment.date,
                "last_clinical_notes": note.notes or note.chief_complaint or "",
                "last_treatments": latest_treatments,
                "doctor": note.appointment.doctor.id if (note.appointment and note.appointment.doctor) else "",
                "doctor_name": note.appointment.doctor.name if (note.appointment and note.appointment.doctor) else "",
                "created_at": note.created_at
            })
        return Response(data)

class FollowUpUpdateView(APIView):
    def patch(self, request, pk):
        note = get_object_or_404(ClinicalNotes, pk=pk)
        old_follow_up_date = note.follow_up_date
        old_follow_up_status = note.follow_up_status

        # Update doctor if provided
        doctor = None
        if 'doctor' in request.data:
            doc_id = request.data['doctor']
            doctor = Doctor.objects.filter(id=doc_id).first() if doc_id else None
            if note.appointment:
                note.appointment.doctor = doctor
                note.appointment.save()

        if 'follow_up_date' in request.data:
            note.follow_up_date = request.data['follow_up_date']
        if 'follow_up_status' in request.data:
            note.follow_up_status = request.data['follow_up_status']
        if 'follow_up_note' in request.data:
            note.follow_up_note = request.data['follow_up_note']
        note.save()

        # Keep Appointment in sync!
        new_follow_up_date = note.follow_up_date
        new_follow_up_status = note.follow_up_status

        if new_follow_up_date and new_follow_up_status not in ['Completed', 'Missed']:
            appt = None
            if old_follow_up_date:
                appt = Appointment.objects.filter(
                    patient=note.appointment.patient,
                    date=old_follow_up_date,
                    status='Follow-up'
                ).first()
            
            if appt:
                appt.date = new_follow_up_date
                if 'doctor' in request.data:
                    appt.doctor = doctor
                appt.save()
            else:
                Appointment.objects.get_or_create(
                    patient=note.appointment.patient,
                    date=new_follow_up_date,
                    status='Follow-up',
                    defaults={'doctor': doctor or note.appointment.doctor}
                )
        elif old_follow_up_date:
            appt = Appointment.objects.filter(
                patient=note.appointment.patient,
                date=old_follow_up_date,
                status='Follow-up'
            ).first()
            if appt:
                if new_follow_up_status in ['Completed', 'Missed']:
                    appt.status = new_follow_up_status
                    appt.save()
                else:
                    appt.delete()

        return Response({
            "follow_up_date": note.follow_up_date,
            "follow_up_status": note.follow_up_status
        })

# --- PRE-BOOKINGS ---
class PreBookingListView(APIView):
    def get(self, request):
        status_filter = request.query_params.get('status', 'Pending')
        preds = PreBooking.objects.all().order_by('-created_at')
        if status_filter != 'all':
            preds = preds.filter(status=status_filter)
        
        data = []
        for p in preds:
            data.append({
                "id": str(p.id),
                "name": p.name,
                "phone": p.phone,
                "expected_date": p.expected_date,
                "status": p.status,
                "notes": p.notes,
                "created_at": p.created_at
            })
        return Response(data)

    def post(self, request):
        data = request.data
        pb = PreBooking.objects.create(
            name=data.get('name'),
            phone=data.get('phone'),
            expected_date=data.get('expected_date'),
            notes=data.get('notes', '')
        )
        return Response({"id": pb.id, "status": "success"})

class PreBookingBookView(APIView):
    def post(self, request, pk):
        pb = get_object_or_404(PreBooking, pk=pk)
        # 1. Create/Get Patient
        patient, created = Patient.objects.get_or_create(
            phone=pb.phone,
            defaults={'name': pb.name}
        )
        # 2. Create Appointment for expected date
        appt_date = pb.expected_date if pb.expected_date else timezone.localtime(timezone.now()).date()
        Appointment.objects.create(
            patient=patient,
            date=appt_date,
            status='Scheduled'
        )
        # 3. Mark PreBooking as Booked
        pb.status = 'Booked'
        pb.save()
        return Response({"status": "success", "patient_id": patient.id})

class PreBookingSyncMissedView(APIView):
    def post(self, request):
        from datetime import date
        # Mark past pending pre-bookings as Missed
        updated = PreBooking.objects.filter(
            expected_date__lt=timezone.localtime(timezone.now()).date(),
            status='Pending'
        ).update(status='Missed')
        
        # Also, mark any Follow-ups that are past their date and still 'Pending' as Missed
        updated_notes = ClinicalNotes.objects.filter(
            follow_up_date__lt=timezone.localtime(timezone.now()).date(),
            follow_up_status='Pending'
        ).update(follow_up_status='Missed')
        
        return Response({"updated_prebookings": updated, "updated_followups": updated_notes})

# --- PRESCRIPTIONS ---
class PrescriptionAddView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        data = request.data
        try:
            # Safely parse IDs
            visit_id = data.get('visit')
            patient_id = data.get('patient')
            note_id = data.get('clinical_note')
            doctor_id = data.get('doctor')
            
            # Convert to None if empty string or "null" string
            if str(visit_id or '').strip().lower() in ['', 'null', 'undefined', 'new']: visit_id = None
            if str(patient_id or '').strip().lower() in ['', 'null', 'undefined', 'new']: patient_id = None
            if str(note_id or '').strip().lower() in ['', 'null', 'undefined', 'new']: note_id = None
            if str(doctor_id or '').strip().lower() in ['', 'null', 'undefined', 'new']: doctor_id = None

            if not doctor_id:
                doc_profile = get_user_doctor(request)
                if doc_profile:
                    doctor_id = doc_profile.id

            notes = data.get('notes', '')
            items_data = data.get('items', [])

            prescription = Prescription.objects.create(
                visit_id=str(visit_id) if visit_id else None,
                patient_id=str(patient_id) if patient_id else None,
                clinical_note_id=str(note_id) if note_id else None,
                doctor_id=str(doctor_id) if doctor_id else None,
                notes=notes
            )
            
            for item in items_data:
                med_name = item.get('medicine_name') or item.get('name')
                if not med_name: continue
                
                qty = int(item.get('quantity') or 1)
                
                # Snapshot price from MedicineMaster if not supplied
                medicine_master = MedicineMaster.objects.filter(name__iexact=med_name).first()
                if medicine_master and getattr(medicine_master, 'is_active', True) is False:
                    return Response({"error": f"Medicine '{med_name}' is inactive/discontinued and cannot be prescribed."}, status=status.HTTP_400_BAD_REQUEST)
                u_price = Decimal(str(item.get('unit_price') or (medicine_master.sales_rate if medicine_master else 0)))
                
                # NOTE: Prescribing records the clinical prescription only.
                # Stock is deducted during pharmacy dispensing/billing (PharmacyBillView) via reduce_stock_batches.

                # Create Prescription Item
                PrescriptionItem.objects.create(
                    prescription=prescription,
                    medicine_name=med_name,
                    dosage=item.get('dosage', '1-0-1'),
                    duration=item.get('duration', '5 days'),
                    notes=item.get('notes', ''),
                    quantity=qty,
                    unit_price=u_price
                )

            return Response({"id": prescription.id, "status": "success"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PrescriptionListView(APIView):
    def get(self, request):
        from collections import defaultdict
        prescriptions = Prescription.objects.all().order_by('-created_at')
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            prescriptions = prescriptions.filter(doctor=doctor_profile)
        
        # Evaluate queryset to list
        rx_list = list(prescriptions)
        
        # Collect IDs
        patient_ids = set()
        doctor_ids = set()
        rx_ids = []
        for rx in rx_list:
            rx_ids.append(rx.id)
            if rx.patient_id:
                patient_ids.add(rx.patient_id)
            if rx.doctor_id:
                doctor_ids.add(rx.doctor_id)
                
        # Bulk query related models
        patients_dict = {p.id: p for p in Patient.objects.filter(id__in=list(patient_ids))} if patient_ids else {}
        doctors_dict = {d.id: d for d in Doctor.objects.filter(id__in=list(doctor_ids))} if doctor_ids else {}
        
        items_by_rx = defaultdict(list)
        if rx_ids:
            rx_items = PrescriptionItem.objects.filter(prescription_id__in=rx_ids)
            for item in rx_items:
                items_by_rx[item.prescription_id].append({
                    "id": item.id,
                    "prescription": item.prescription_id,
                    "medicine_name": item.medicine_name,
                    "dosage": item.dosage,
                    "duration": item.duration,
                    "notes": item.notes,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price) if item.unit_price is not None else 0.0,
                    "is_billed": item.is_billed,
                    "is_dispensed": item.is_dispensed
                })
                
        data = []
        for rx in rx_list:
            p = patients_dict.get(rx.patient_id)
            d = doctors_dict.get(rx.doctor_id)
            data.append({
                "id": rx.id,
                "patient": rx.patient_id,
                "patient_name": p.name if p else "Unknown",
                "patient_phone": p.phone if p else "",
                "doctor": rx.doctor_id,
                "doctor_name": d.name if d else "",
                "visit": rx.visit_id,
                "clinical_note": rx.clinical_note_id,
                "notes": rx.notes or "",
                "status": rx.status,
                "created_by": rx.created_by_id,
                "created_at": rx.created_at,
                "items": items_by_rx.get(rx.id, [])
            })
            
        return Response(data)

class MedicineMasterListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        meds = MedicineMaster.objects.all().order_by('name')

        # Active / Inactive filtering
        include_inactive = request.query_params.get('include_inactive')
        active_param = request.query_params.get('active')
        if active_param is not None:
            if active_param.lower() in ['true', '1']:
                meds = meds.filter(is_active=True)
            elif active_param.lower() in ['false', '0']:
                meds = meds.filter(is_active=False)
        elif not (include_inactive and include_inactive.lower() in ['true', '1']):
            meds = meds.filter(is_active=True)

        q = request.query_params.get('search') or request.query_params.get('q')
        if q:
            from django.db.models import Q
            meds = meds.filter(Q(name__icontains=q) | Q(dosage__icontains=q) | Q(frequency__icontains=q) | Q(notes__icontains=q))
        serializer = MedicineMasterSerializer(meds, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MedicineMasterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# --- BILLING ---
class CreateBillingView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist', 'Pharmacist'])
        if denied:
            return denied

        note_id = request.data.get('clinical_note_id')
        
        # 1. Flow for Clinical Notes Handover
        if note_id:
            treatment_ids = request.data.get('treatment_ids', [])
            note = get_object_or_404(ClinicalNotes, id=note_id)
            visit = Visit.objects.filter(appointment=note.appointment).first()
            
            # Find or create to prevent duplicate bills for the same clinical note
            billing = Billing.objects.filter(clinical_note=note, bill_type='Clinical').first()
            if not billing:
                billing = Billing.objects.create(
                    clinical_note=note,
                    bill_type='Clinical',
                    patient=note.appointment.patient,
                    visit=visit,
                    doctor=note.appointment.doctor,
                    is_invoice=False
                )
            else:
                billing.patient = note.appointment.patient
                billing.visit = visit
                billing.save()
            
            # Clear existing items if updating to avoid duplication (e.g. Root Canal showing twice)
            billing.items.all().delete()
                
            total = Decimal('0.00')
            for t_id in treatment_ids:
                t = get_object_or_404(TreatmentMaster, id=t_id)
                BillingItem.objects.create(
                    billing=billing,
                    treatment=t,
                    qty=1,
                    price=t.price
                )
                total += t.price
            billing.total_amount = total
            billing.paid_amount = total # Mark as fully paid
            billing.save()
            return Response({"billing_id": billing.id})
            
        # 2. Flow for Standalone/Advanced Creation (Direct from UI or Prescription)
        patient_id = request.data.get('patient')
        visit_id = request.data.get('visit_id') or request.data.get('visit')
        treatment_ids = request.data.get('treatment_ids', [])
        
        # --- Flow 3: visit_id + treatment_ids (from TreatmentModal) ---
        if visit_id and treatment_ids:
            visit = get_object_or_404(Visit, id=visit_id)
            patient = visit.patient
            paid_amount = Decimal(str(request.data.get('paid_amount', 0)))
            payment_method = request.data.get('payment_method', 'Cash')

            # USER REQUEST: "dont add that old one again" - disabling consolidation to ensure fresh bill per save/print
            doc_id = request.data.get('doctor_id')
            billing = Billing.objects.create(
                visit=visit,
                bill_type='Clinical',
                patient=patient,
                doctor_id=doc_id if doc_id else (visit.appointment.doctor.id if visit.appointment and visit.appointment.doctor else None),
                is_invoice=False
            )

            # Recalculate total for this new bill

            total = Decimal('0.00')
            for t_item in treatment_ids:
                if isinstance(t_item, dict):
                    t_id = t_item.get('id')
                    custom_price = t_item.get('price')
                    custom_name = t_item.get('name')
                else:
                    t_id = t_item
                    custom_price = None
                    custom_name = None

                if t_id:
                    t = get_object_or_404(TreatmentMaster, id=t_id)
                elif custom_name:
                    t, created = TreatmentMaster.objects.get_or_create(
                        name=custom_name,
                        defaults={'price': Decimal(str(custom_price or 0)), 'fee_type': 'Treatment'}
                    )
                else:
                    continue

                price_to_use = Decimal(str(custom_price)) if custom_price is not None and custom_price != '' else t.price
                
                t_doc = (visit.appointment.doctor if (visit and visit.appointment) else None)
                TreatmentRecord.objects.create(visit=visit, treatment=t, price=price_to_use, doctor=t_doc)
                total += price_to_use

            prior = Decimal('0')
            if request.data.get('include_prior_balance'):
                prior = Decimal(str(float(patient.total_balance)))
                if prior > 0:
                    # Mark previous Clinical bills as Paid so they are not double-counted (since their balance is now transferred to this new bill)
                    prior_bills = Billing.objects.filter(patient=patient, bill_type='Clinical').exclude(status='Cancelled')
                    for pb in prior_bills:
                        pb.paid_amount = pb.total_amount
                        pb.balance_amount = Decimal('0')
                        pb.status = 'Paid'
                        pb.save()

                    tpm, _ = TreatmentMaster.objects.get_or_create(
                        name='Outstanding balance (brought forward)',
                        defaults={'price': Decimal('0'), 'fee_type': 'Treatment'}
                    )
                    BillingItem.objects.create(billing=billing, treatment=tpm, qty=1, price=prior)
                    total += prior

            billing.total_amount = total
            requested_paid = Decimal(str(request.data.get('paid_amount', 0)))
            if total > 0:
                if requested_paid <= 0:
                    billing.paid_amount = total
                else:
                    billing.paid_amount = min(requested_paid, total)
            else:
                billing.paid_amount = max(Decimal('0'), requested_paid)
            billing.payment_method = payment_method
            billing.save()

            # Update or create Payment record for this visit
            if billing.paid_amount > 0:
                payment, _ = Payment.objects.update_or_create(
                    visit=visit,
                    defaults={
                        'patient': patient,
                        'total_amount': total,
                        'paid_amount': billing.paid_amount,
                        'payment_method': payment_method
                    }
                )

            return Response({
                "billing_id": billing.id,
                "total_amount": float(total),
                "paid_amount": float(billing.paid_amount),
                "balance": float(billing.balance_amount),
                "status": "success"
            })

        # --- Flow 2: patient + items (from Prescription/Advanced billing) ---
        if not patient_id:
            return Response({"error": "Either clinical_note_id, or visit_id+treatment_ids, or patient is required"}, status=400)
            
        patient = get_object_or_404(Patient, id=patient_id)
        
        # Ensure a visit exists for today if not provided
        if visit_id:
            visit = Visit.objects.filter(id=visit_id).first()
        else:
            today = timezone.localtime(timezone.now()).date()
            start_of_day = timezone.make_aware(datetime.combine(today, time.min))
            end_of_day = timezone.make_aware(datetime.combine(today, time.max))
            visit = Visit.objects.filter(patient=patient, created_at__range=(start_of_day, end_of_day)).first()
        
        if not visit:
            # Create a shell visit if none exists today
            req_doctor_id = request.data.get('doctor_id')
            doctor = Doctor.objects.filter(id=req_doctor_id).first() if req_doctor_id else Doctor.objects.first()
            appt = Appointment.objects.create(
                patient=patient, 
                doctor=doctor, 
                date=timezone.localtime(timezone.now()).date(), 
                time=timezone.now().time(), 
                status='Completed'
            )
            visit = Visit.objects.create(patient=patient, appointment=appt)

        # Consolidate into one row: find an existing unpaid bill of the SAME type
        # USER REQUEST: "dont add that old one again" - disabling consolidation to ensure fresh bill per save/print
        
        is_pharmacy = any(item.get('fee_type') == 'Pharmacy' for item in request.data.get('items', []))
        is_lab = any(item.get('fee_type') == 'Lab' or 'lab' in item.get('name', '').lower() for item in request.data.get('items', []))
        
        if is_pharmacy:
            bill_type = 'Pharmacy'
        elif is_lab:
            bill_type = 'Lab'
        else:
            bill_type = 'Clinical'
        
        items = list(request.data.get('items', []))
        prior_add = Decimal('0')
        if request.data.get('include_prior_balance') and bill_type == 'Clinical':
            prior_add = Decimal(str(float(patient.total_balance)))
            if prior_add > 0:
                # Mark previous Clinical bills as Paid so they are not double-counted (since their balance is now transferred to this new bill)
                prior_bills = Billing.objects.filter(patient=patient, bill_type='Clinical').exclude(status='Cancelled')
                for pb in prior_bills:
                    pb.paid_amount = pb.total_amount
                    pb.balance_amount = Decimal('0')
                    pb.status = 'Paid'
                    pb.save()

                items = [{
                    'name': 'Outstanding balance (brought forward)',
                    'quantity': 1,
                    'unit_price': float(prior_add),
                    'fee_type': 'Treatment',
                }] + items

        new_total = Decimal(str(request.data.get('total_amount', 0))) + prior_add
        if request.data.get('paid_amount') is not None and str(request.data.get('paid_amount')).strip() != '':
            new_paid = Decimal(str(request.data.get('paid_amount')))
        else:
            new_paid = new_total
        if new_total > 0:
            if new_paid > new_total:
                new_paid = new_total
            if new_paid < 0:
                new_paid = Decimal('0')
        else:
            if new_paid < 0:
                new_paid = Decimal('0')

        # Evaluate is_invoice based on treatment_ids or explicit is_draft flag
        is_draft = str(request.data.get('is_draft', '')).lower() in ['true', '1']
        is_invoice = False if request.data.get('treatment_ids') or is_draft else True

        billing = None
        if visit and bill_type == 'Clinical':
            billing = Billing.objects.filter(visit=visit, bill_type='Clinical', is_invoice=False).first()
            
        if billing:
            billing.total_amount += new_total
            billing.paid_amount += new_paid
            if request.data.get('payment_method'):
                billing.payment_method = request.data.get('payment_method')
            billing.is_invoice = is_invoice
            billing.save()
        else:
            billing = Billing.objects.create(
                patient=patient,
                visit=visit,
                bill_type=bill_type,
                total_amount=new_total,
                paid_amount=new_paid,
                payment_method=request.data.get('payment_method', 'Cash'),
                doctor=Doctor.objects.filter(id=request.data.get('doctor_id')).first() if request.data.get('doctor_id') else (
                    visit.appointment.doctor if visit and visit.appointment and visit.appointment.doctor else None
                ),
                is_invoice=is_invoice
            )
        
        for item in items:
            t_id = item.get('treatment')
            if t_id:
                t = get_object_or_404(TreatmentMaster, id=t_id)
            else:
                name = item.get('name', 'Lab Test/Custom')
                price = item.get('unit_price', 0)
                t, _ = TreatmentMaster.objects.get_or_create(name=name, defaults={'price': price, 'fee_type': 'Lab'})

            BillingItem.objects.create(
                billing=billing,
                treatment=t,
                qty=item.get('quantity', 1),
                price=item.get('unit_price', t.price)
            )
            t_doc = (visit.appointment.doctor if (visit and visit.appointment) else None)
            TreatmentRecord.objects.create(
                visit=visit,
                treatment=t,
                price=item.get('unit_price', t.price),
                notes=request.data.get('notes', 'Added via billing/prescription'),
                doctor=t_doc
            )
            
        billing.save() 
        
        if new_paid > 0:
            payment = Payment.objects.filter(visit=visit).first()
            if not payment:
                payment = Payment.objects.create(
                    visit=visit,
                    patient=patient,
                    total_amount=new_total,
                    paid_amount=new_total, # Mark as fully paid
                    payment_method=request.data.get('payment_method', 'Cash')
                )
            else:
                payment.total_amount = Decimal(str(payment.total_amount)) + new_total
                payment.paid_amount = Decimal(str(payment.paid_amount)) + new_paid
                payment.payment_method = request.data.get('payment_method', payment.payment_method)
                payment.save()
            
        return Response({"billing_id": billing.id, "status": "success"})

class BillingUpdateView(APIView):
    authentication_classes = []
    permission_classes = []

    def delete(self, request, pk):
        """Hard-delete a billing record."""
        denied = require_role(request, ['Admin', 'Doctor'])
        if denied:
            return denied
        bill = get_object_or_404(Billing, pk=pk)
        bill.delete()
        return Response({'status': 'deleted'}, status=204)

    def patch(self, request, pk):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
        if denied:
            return denied

        bill = get_object_or_404(Billing, pk=pk)
        data = request.data
        
        from django.db import transaction
        try:
            with transaction.atomic():
                # update basic fields with validation
                if 'total_amount' in data:
                    t_amt = Decimal(str(data['total_amount']))
                    if t_amt < Decimal('0.00'):
                        return Response({'error': 'Total amount cannot be negative.'}, status=400)
                    bill.total_amount = t_amt

                if 'paid_amount' in data:
                    p_amt = Decimal(str(data['paid_amount']))
                    if p_amt < Decimal('0.00'):
                        return Response({'error': 'Paid amount cannot be negative.'}, status=400)
                    if bill.total_amount > Decimal('0.00') and p_amt > bill.total_amount:
                        return Response({'error': f'Paid amount (₹{p_amt}) cannot exceed total bill amount (₹{bill.total_amount}).'}, status=400)
                    bill.paid_amount = p_amt

                if 'payment_method' in data: bill.payment_method = data['payment_method']
                if 'notes' in data: bill.notes = data['notes']
                if 'status' in data: bill.status = data['status']
                bill.save()
                
                incoming_items = data.get('items', [])
                
                for it_data in incoming_items:
                    it_id = it_data.get('id')
                    if it_id:
                        item = BillingItem.objects.filter(id=it_id, billing=bill).first()
                        if item:
                            old_qty = item.qty
                            new_qty = int(it_data.get('qty', old_qty))
                            
                            # Check if this is a pharmacy item
                            if item.treatment.name.startswith("Pharmacy: "):
                                med_name = item.treatment.name.replace("Pharmacy: ", "")
                                med = MedicineMaster.objects.filter(name__iexact=med_name).first()
                                if med:
                                    # Adjust stock
                                    diff = new_qty - old_qty
                                    if med.stock_quantity < diff:
                                        raise ValueError(f"Insufficient stock for '{med_name}'.")
                                    med.stock_quantity -= diff
                                    med.save()

                            item.qty = new_qty
                            item.price = Decimal(str(it_data.get('price', item.price)))
                            item.save()
                    else:
                        # new item added to existing bill
                        treatment_id = it_data.get('treatment')
                        qty = int(it_data.get('qty', 1))
                        price = Decimal(str(it_data.get('price', 0)))
                        
                        tm = TreatmentMaster.objects.get(id=treatment_id)
                        if tm.name.startswith("Pharmacy: "):
                            med_name = tm.name.replace("Pharmacy: ", "")
                            med = MedicineMaster.objects.filter(name__iexact=med_name).first()
                            if med:
                                if med.stock_quantity < qty:
                                    raise ValueError(f"Insufficient stock for '{med_name}'.")
                                med.stock_quantity -= qty
                                med.save()

                        BillingItem.objects.create(
                            billing=bill,
                            treatment=tm,
                            qty=qty,
                            price=price
                        )
                
                return Response({"status": "success", "bill_id": bill.id})
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        except Exception as e:
            return Response({'error': f'Update failed: {str(e)}'}, status=500)

class BillingListView(APIView):
    def get(self, request):
        from collections import defaultdict
        patient_id = request.query_params.get('patient_id')
        bill_type = request.query_params.get('bill_type')
        bills = Billing.objects.filter(is_invoice=True).order_by('-created_at')
        
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            bills = bills.filter(doctor=doctor_profile)
            
        if patient_id:
            bills = bills.filter(patient_id=patient_id)
            
        if bill_type:
            bills = bills.filter(bill_type=bill_type)
            
        # Optimize by converting to list and prefetching patients, billing items, and treatments
        bills_list = list(bills)
        
        patient_ids = set()
        bill_ids = []
        for b in bills_list:
            bill_ids.append(b.id)
            if b.patient_id:
                patient_ids.add(b.patient_id)
                
        patients_dict = {p.id: p for p in Patient.objects.filter(id__in=list(patient_ids))} if patient_ids else {}
        
        items_by_bill = defaultdict(list)
        if bill_ids:
            b_items = BillingItem.objects.filter(billing_id__in=bill_ids)
            # Fetch treatment names in bulk
            treatment_ids = set(item.treatment_id for item in b_items if item.treatment_id)
            treatments_dict = {t.id: t for t in TreatmentMaster.objects.filter(id__in=list(treatment_ids))} if treatment_ids else {}
            
            for item in b_items:
                t = treatments_dict.get(item.treatment_id)
                items_by_bill[item.billing_id].append({
                    "id": item.id,
                    "billing": item.billing_id,
                    "treatment": item.treatment_id,
                    "treatment_name": t.name if t else "Unknown",
                    "qty": item.qty,
                    "price": float(item.price) if item.price is not None else 0.0
                })
                
        data = []
        for b in bills_list:
            p = patients_dict.get(b.patient_id)
            data.append({
                "id": b.id,
                "patient": b.patient_id,
                "patient_name": p.name if p else "Unknown",
                "patient_phone": p.phone if p else "",
                "visit": b.visit_id,
                "clinical_note": b.clinical_note_id,
                "total_amount": float(b.total_amount) if b.total_amount is not None else 0.0,
                "paid_amount": float(b.paid_amount) if b.paid_amount is not None else 0.0,
                "balance_amount": float(b.balance_amount) if b.balance_amount is not None else 0.0,
                "payment_method": b.payment_method,
                "status": b.status,
                "created_at": b.created_at,
                "items": items_by_bill.get(b.id, [])
            })
            
        return Response(data)

class RecentPaymentsView(APIView):
    def get(self, request):
        bill_type = request.query_params.get('type')
        date_str = request.query_params.get('date')
        billings = Billing.objects.filter(is_invoice=True).order_by('-created_at')
        
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            billings = billings.filter(doctor=doctor_profile)
        
        if bill_type == 'Pharmacy':
            billings = billings.filter(bill_type='Pharmacy')
        elif bill_type == 'Clinical':
            billings = billings.exclude(bill_type='Pharmacy')
            
        if date_str:
            from datetime import datetime, time
            from django.utils import timezone
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                start_of_day = timezone.make_aware(datetime.combine(date_obj, time.min))
                end_of_day = timezone.make_aware(datetime.combine(date_obj, time.max))
                billings = billings.filter(created_at__range=(start_of_day, end_of_day))
            except ValueError:
                pass
            
        data = []
        for b in billings[:50]:
            data.append({
                'id': b.id,
                'created_at': b.created_at,
                'patient_name': b.patient.name,
                'patient_phone': b.patient.phone,
                'total_amount': b.total_amount,
                'payment_method': b.payment_method,
                'items': [{'id': i.id} for i in b.items.all()]
            })
        return Response(data)

# --- PDF UTILITIES ---
class LatestBillingPDFView(APIView):
    def get(self, request):
        patient_id = request.query_params.get('patient_id')
        if not patient_id:
            return Response({"error": "patient_id is required"}, status=400)
            
        bill = Billing.objects.filter(patient_id=patient_id, is_invoice=True).order_by('-created_at').first()
        if not bill:
            return Response({"error": "No bills found for this patient"}, status=404)
            
        # Redirect or reuse BillingPDFView logic
        view = BillingPDFView()
        return view.get(request, pk=bill.id)

class PrescriptionPDFView(APIView):
    def get(self, request, pk):
        rx = get_object_or_404(Prescription, pk=pk)
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header Clinic Details
        p.setFont("Helvetica-Bold", 18)
        p.drawString(50, height - 50, "SMILE DENTAL CLINIC")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 65, "123 Dental Street, Healthcare Plaza | Tel: +91 9876543210")
        p.drawString(50, height - 78, "Email: contact@smiledental.com | Web: www.smiledental.com")
        p.setStrokeColorRGB(0.2, 0.2, 0.8) # Blue line
        p.line(50, height - 85, 545, height - 85)

        # Patient & Rx Info Box
        p.setStrokeColorRGB(0.8, 0.8, 0.8)
        p.rect(50, height - 160, 495, 60)
        
        p.setFont("Helvetica-Bold", 11)
        p.drawString(60, height - 118, f"PATIENT NAME: {rx.patient.name.upper() if rx.patient else 'WALK-IN'}")
        p.setFont("Helvetica", 10)
        p.drawString(60, height - 132, f"Age/Gender: {rx.patient.age or '—'} Y / {rx.patient.gender or '—'}")
        p.drawString(60, height - 146, f"Patient ID: #{rx.patient.id if rx.patient else '—'}")
        
        p.drawString(380, height - 118, f"Date: {rx.created_at.strftime('%d %b %Y')}")
        p.drawString(380, height - 132, f"Time: {rx.created_at.strftime('%I:%M %p')}")

        y = height - 200
        
        # 1. MEDICINES Section
        if rx.items.exists():
            p.setFont("Helvetica-Bold", 14)
            p.setFillColorRGB(0.2, 0.4, 0.8)
            p.drawString(50, y, "MEDICINES")
            p.setFillColorRGB(0, 0, 0)
            y -= 25
            
            # Table Header
            p.setFont("Helvetica-Bold", 10)
            p.drawString(60, y, "Medicine Name")
            p.drawString(280, y, "Dosage (M-A-N)")
            p.drawString(420, y, "Duration")
            p.line(50, y-5, 545, y-5)
            y -= 20
            
            p.setFont("Helvetica", 10)
            for item in rx.items.all():
                if y < 100:
                    p.showPage()
                    y = height - 50
                p.drawString(60, y, item.medicine_name)
                p.drawString(280, y, item.dosage)
                p.drawString(420, y, item.duration)
                if item.notes:
                    y -= 12
                    p.setFont("Helvetica-Oblique", 9)
                    p.drawString(70, y, f"Note: {item.notes}")
                    p.setFont("Helvetica", 10)
                y -= 22
        
        # 2. TREATMENTS Section (from Billing)
        if rx.visit:
            from .models import Billing, BillingItem
            clinical_bill = Billing.objects.filter(visit=rx.visit, bill_type='Clinical').first()
            if clinical_bill and clinical_bill.items.exists():
                y -= 20
                p.setFont("Helvetica-Bold", 14)
                p.setFillColorRGB(0.2, 0.4, 0.8)
                p.drawString(50, y, "TREATMENTS")
                p.setFillColorRGB(0, 0, 0)
                y -= 20
                p.setFont("Helvetica", 10)
                for bi in clinical_bill.items.all():
                    p.drawString(60, y, f"• {bi.treatment.name} (Qty: {bi.qty})")
                    y -= 14

        # 3. LAB TESTS Section
        if rx.notes and "LAB TESTS:" in rx.notes:
            y -= 20
            p.setFont("Helvetica-Bold", 14)
            p.setFillColorRGB(0.2, 0.4, 0.8)
            p.drawString(50, y, "LAB TESTS")
            p.setFillColorRGB(0, 0, 0)
            y -= 20
            p.setFont("Helvetica", 10)
            
            lab_lines = rx.notes.replace("LAB TESTS:", "").strip().split('\n')
            for line in lab_lines:
                if line.strip():
                    p.drawString(60, y, line.strip())
                    y -= 14
        elif rx.notes:
            # General notes if they exist and aren't just lab tests
            y -= 20
            p.setFont("Helvetica-Bold", 12)
            p.drawString(50, y, "GENERAL NOTES / INSTRUCTIONS:")
            y -= 20
            p.setFont("Helvetica", 10)
            text_object = p.beginText(60, y)
            for line in rx.notes.split('\n'):
                # Line wrapping logic could go here, for now simple lines
                text_object.textLine(line)
                y -= 14
            p.drawText(text_object)

        # Footer / Signatures
        p.line(50, 100, 545, 100)
        p.setFont("Helvetica-Oblique", 9)
        p.drawString(50, 85, "Disclaimer: This prescription is generated electronically. Please consult your doctor for any severe reactions.")
        
        p.setFont("Helvetica-Bold", 11)
        p.drawString(420, 120, "Doctor's Signature")
        
        p.showPage()
        p.save()
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')


class BillingPDFView(APIView):
    def get(self, request, pk):
        bill = get_object_or_404(Billing, pk=pk)
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header Clinic Details
        p.setFont("Helvetica-Bold", 18)
        p.drawString(50, height - 50, "SMILE DENTAL CLINIC")
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 65, "123 Dental Street, Healthcare Plaza | Tel: +91 9876543210")
        p.drawString(50, height - 78, "INVOICE / RECEIPT")
        p.setStrokeColorRGB(0.2, 0.2, 0.8)
        p.line(50, height - 85, 545, height - 85)

        # Bill Meta Info
        p.setFont("Helvetica-Bold", 11)
        p.drawString(60, height - 110, f"BILL TO: {bill.patient.name.upper()}")
        p.setFont("Helvetica", 10)
        p.drawString(60, height - 124, f"Phone: {bill.patient.phone}")
        p.drawString(60, height - 138, f"Patient ID: #{bill.patient.id}")

        p.drawString(380, height - 110, f"Invoice #: INV-{str(bill.id).upper()[:8]}")
        p.drawString(380, height - 124, f"Date: {bill.created_at.strftime('%d %b %Y %I:%M %p')}")
        p.drawString(380, height - 138, f"Status: {bill.status.upper()}")

        y = height - 170

        # Items Table Header
        p.setFillColorRGB(0.95, 0.95, 0.95)
        p.rect(50, y-5, 495, 20, fill=1)
        p.setFillColorRGB(0, 0, 0)
        p.setFont("Helvetica-Bold", 10)
        p.drawString(60, y, "Treatment / Procedure")
        p.drawString(300, y, "Qty")
        p.drawString(380, y, "Unit Price")
        p.drawString(480, y, "Total")
        y -= 25

        p.setFont("Helvetica", 10)
        for item in bill.items.all():
            total_item = item.qty * item.price
            p.drawString(60, y, item.treatment.name)
            p.drawString(300, y, str(item.qty))
            p.drawString(380, y, f"₹{item.price:,.2f}")
            p.drawString(480, y, f"₹{total_item:,.2f}")
            y -= 20
        
        # Summary Section
        p.line(350, y, 545, y)
        y -= 20
        p.setFont("Helvetica", 11)
        p.drawString(350, y, "Current Bill Total:")
        p.drawString(480, y, f"₹{bill.total_amount:,.2f}")
        
        # Only show Previous Dues and Total Outstanding for CLINICAL bills
        if bill.bill_type == 'Clinical':
            # Calculate Previous Dues (Total Balance minus this bill's balance)
            total_bal = Decimal(str(bill.patient.total_balance))
            prev_dues = total_bal - bill.balance_amount
            
            if prev_dues > 0:
                y -= 18
                p.setFillColorRGB(0.5, 0.5, 0.5)
                p.drawString(350, y, "Previous Dues:")
                p.drawString(480, y, f"₹{prev_dues:,.2f}")
                p.setFillColorRGB(0, 0, 0)

            y -= 22
            p.setFont("Helvetica-Bold", 12)
            p.setFillColorRGB(0.2, 0.2, 0.8) # Blue for final total
            p.drawString(350, y, "Total Outstanding:")
            p.drawString(480, y, f"₹{total_bal:,.2f}")
            p.setFillColorRGB(0, 0, 0)
        else:
            # For Pharmacy and Lab, just show Paid status (no credit allowed)
            y -= 22
            p.setFont("Helvetica-Bold", 12)
            p.setFillColorRGB(0.1, 0.6, 0.1) # Green for paid
            p.drawString(350, y, "AMOUNT PAID:")
            p.drawString(480, y, f"₹{bill.paid_amount:,.2f}")
            p.setFillColorRGB(0, 0, 0)
        
        y -= 25
        p.line(350, y, 545, y)
        y -= 20
        p.setFont("Helvetica", 11)
        p.setFillColorRGB(0, 0.5, 0) # Green for paid
        p.drawString(350, y, "Amount Paid Now:")
        p.drawString(480, y, f"₹{bill.paid_amount:,.2f}")
        p.setFillColorRGB(0, 0, 0)

        if bill.payment_method and bill.payment_method.lower() == 'cash' and bill.cash_received and bill.cash_received > 0:
            y -= 18
            p.setFont("Helvetica", 10)
            p.drawString(350, y, "Cash Received:")
            p.drawString(480, y, f"₹{bill.cash_received:,.2f}")
            if bill.balance_returned and bill.balance_returned > 0:
                y -= 18
                p.drawString(350, y, "Balance Returned:")
                p.drawString(480, y, f"₹{bill.balance_returned:,.2f}")

        # Footer Notes
        y -= 60
        if y < 100:
            p.showPage()
            y = height - 50
            
        p.setFont("Helvetica-Bold", 10)
        p.drawString(50, y, "Payment Method: " + bill.payment_method)
        y -= 15
        p.setFont("Helvetica", 9)
        p.drawString(50, y, "Thank you for choosing Smile Dental Clinic!")
        p.drawString(50, y - 12, "For any inquiries, please contact our helpdesk.")

        p.showPage()
        p.save()
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')
class CommunicationLogView(APIView):
    def get(self, request):
        patient_id = request.query_params.get('patient_id')
        if patient_id:
            logs = CommunicationLog.objects.filter(patient_id=patient_id).order_by('-sent_at')
        else:
            logs = CommunicationLog.objects.all().order_by('-sent_at')
        
        # Simple serialization for now if no serializer exists
        data = [{
            "id": log.id,
            "patient_name": log.patient.name,
            "message": log.message,
            "channel": log.channel,
            "sent_at": log.sent_at
        } for log in logs]
        return Response(data)

    def post(self, request):
        patient_ids = request.data.get('patient_ids', [])
        message = request.data.get('message')
        channels = request.data.get('channels', []) # ['SMS', 'WhatsApp']
        
        if not patient_ids or not message:
            return Response({"error": "Patient IDs and message are required"}, status=400)
            
        channel_str = "Both" if len(channels) > 1 else channels[0] if channels else "SMS"
        
        for p_id in patient_ids:
            patient = get_object_or_404(Patient, id=p_id)
            CommunicationLog.objects.create(
                patient=patient,
                message=message,
                channel=channel_str
            )
            
        return Response({"status": "success", "count": len(patient_ids)})

class PatientGroupListView(APIView):
    def get(self, request):
        groups = PatientGroup.objects.all().order_by('name')
        serializer = PatientGroupSerializer(groups, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PatientGroupSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PatientGroupDetailView(APIView):
    def get(self, request, pk):
        group = get_object_or_404(PatientGroup, pk=pk)
        serializer = PatientGroupSerializer(group)
        return Response(serializer.data)

    def patch(self, request, pk):
        group = get_object_or_404(PatientGroup, pk=pk)
        serializer = PatientGroupSerializer(group, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        group = get_object_or_404(PatientGroup, pk=pk)
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class PatientBulkGroupUpdateView(APIView):
    def post(self, request):
        patient_ids = request.data.get('patient_ids', [])
        group_id = request.data.get('group_id')
        action = request.data.get('action', 'add') # add | remove

        if not group_id:
            return Response({"error": "group_id is required"}, status=400)
        
        group = get_object_or_404(PatientGroup, pk=group_id)
        patients = Patient.objects.filter(id__in=patient_ids)

        for p in patients:
            if action == 'add':
                p.groups.add(group)
            else:
                p.groups.remove(group)
        
        return Response({"status": "success", "count": patients.count()})

class PendingRemindersView(APIView):
    def get(self, request):
        from datetime import date, timedelta
        today = timezone.localtime(timezone.now()).date()
        tomorrow = today + timedelta(days=1)
        
        start_of_today = timezone.make_aware(datetime.combine(today, time.min))
        end_of_today = timezone.make_aware(datetime.combine(today, time.max))
        
        reminders = []
        
        from django.db.models import Q
        
        # 1. Birthdays Today
        birthday_patients = Patient.objects.filter(dob__month=today.month, dob__day=today.day)
        for p in birthday_patients:
            if not CommunicationLog.objects.filter(patient=p, sent_at__range=(start_of_today, end_of_today), message__icontains='Happy Birthday').exists():
                reminders.append({
                    "patient_id": p.id,
                    "patient_name": p.name,
                    "patient_phone": p.phone,
                    "type": "Birthday",
                    "message": f"Dear {p.name}, wishing you a very Happy Birthday from Dr. Navas and the entire dental team! Keep smiling!"
                })
            
        # 2. Follow-ups Tomorrow
        follow_ups = ClinicalNotes.objects.filter(follow_up_date=tomorrow, follow_up_status='Pending')
        for f in follow_ups:
            p = f.appointment.patient
            if not CommunicationLog.objects.filter(patient=p, sent_at__range=(start_of_today, end_of_today), message__icontains='follow-up check').exists():
                reminders.append({
                    "patient_id": p.id,
                    "patient_name": p.name,
                    "patient_phone": p.phone,
                    "type": "Follow-up",
                    "message": f"Hello {p.name}, this is a reminder for your follow-up check tomorrow. Please let us know if you have any severe pain."
                })
            
        # 3. Appointments / Reschedules Tomorrow
        appts = Appointment.objects.filter(
            Q(date=tomorrow, status='Scheduled') | 
            Q(rescheduled_to_date=tomorrow, status='Rescheduled')
        )
        processed_patient_ids = set()
        for a in appts:
            p = a.patient
            if p.id in processed_patient_ids:
                continue
                
            if not CommunicationLog.objects.filter(patient=p, sent_at__range=(start_of_today, end_of_today), message__icontains='appointment tomorrow').exists():
                is_resched = a.status == 'Rescheduled'
                appt_time = a.rescheduled_to_time if is_resched else a.time
                time_str = appt_time.strftime("%I:%M %p") if appt_time else "anytime"
                reminders.append({
                    "patient_id": p.id,
                    "patient_name": p.name,
                    "patient_phone": p.phone,
                    "type": "Appointment",
                    "message": f"Dear {p.name}, this is a reminder for your dental appointment tomorrow at {time_str}. Please arrive 10 mins early."
                })
                processed_patient_ids.add(p.id)
            
        return Response(reminders)


class AppointmentRemindersView(APIView):
    """Returns automated reminder list for a specific date.
    Includes: Follow-ups, Rescheduled, and Scheduled appointments for that date.
    Each entry shows whether a reminder was already sent today."""
    def get(self, request):
        from datetime import date as date_cls, datetime
        date_str = request.query_params.get('date', '')
        today = date_cls.today()
        start_of_today = timezone.make_aware(datetime.combine(today, time.min))
        end_of_today = timezone.make_aware(datetime.combine(today, time.max))

        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        else:
            # Default: show reminders for today
            target_date = today

        reminders = []
        processed_ids = set()

        # ── 1. Rescheduled appointments landing on target_date ─────────────────
        rescheduled_appts = Appointment.objects.filter(
            rescheduled_to_date=target_date,
            status='Rescheduled'
        ).all()

        for a in rescheduled_appts:
            p = a.patient
            if p.id in processed_ids:
                continue
            t = a.rescheduled_to_time
            time_str = t.strftime("%I:%M %p") if t else "your scheduled time"
            date_pretty = target_date.strftime("%d %b %Y")
            already_sent = CommunicationLog.objects.filter(
                patient=p,
                sent_at__range=(start_of_today, end_of_today),
                message__icontains='rescheduled appointment'
            ).exists()
            reminders.append({
                "patient_id": p.id,
                "patient_name": p.name,
                "patient_phone": p.phone,
                "type": "Rescheduled",
                "appointment_id": a.id,
                "date": str(target_date),
                "time": str(t or ''),
                "already_sent": already_sent,
                "message": (
                    f"Dear {p.name}, this is a reminder for your rescheduled dental appointment "
                    f"on {date_pretty} at {time_str}. Please arrive 10 minutes early. "
                    f"Call us if you need to reschedule."
                )
            })
            processed_ids.add(p.id)

        # ── 2. Follow-ups due on target_date (from ClinicalNotes) ──────────────
        follow_ups = ClinicalNotes.objects.filter(
            follow_up_date=target_date,
            follow_up_status='Pending'
        ).all()

        for f in follow_ups:
            p = f.appointment.patient
            if p.id in processed_ids:
                continue
            date_pretty = target_date.strftime("%d %b %Y")
            already_sent = CommunicationLog.objects.filter(
                patient=p,
                sent_at__range=(start_of_today, end_of_today),
                message__icontains='follow-up'
            ).exists()
            reminders.append({
                "patient_id": p.id,
                "patient_name": p.name,
                "patient_phone": p.phone,
                "type": "Follow-up",
                "appointment_id": f.appointment.id,
                "date": str(target_date),
                "time": "",
                "already_sent": already_sent,
                "message": (
                    f"Dear {p.name}, this is a reminder for your follow-up dental visit "
                    f"on {date_pretty}. "
                    f"{f.follow_up_note or 'Please let us know if you have any concerns.'}"
                )
            })
            processed_ids.add(p.id)

        # ── 3. Regular Scheduled / Follow-up appointments on target_date ────────
        scheduled_appts = Appointment.objects.filter(
            date=target_date,
            status__in=['Scheduled', 'Follow-up']
        ).all().exclude(patient_id__in=processed_ids)

        for a in scheduled_appts:
            p = a.patient
            if p.id in processed_ids:
                continue
            t = a.time
            time_str = t.strftime("%I:%M %p") if t else "your scheduled time"
            date_pretty = target_date.strftime("%d %b %Y")
            already_sent = CommunicationLog.objects.filter(
                patient=p,
                sent_at__range=(start_of_today, end_of_today),
                message__icontains='appointment'
            ).exists()
            reminders.append({
                "patient_id": p.id,
                "patient_name": p.name,
                "patient_phone": p.phone,
                "type": a.status,
                "appointment_id": a.id,
                "date": str(target_date),
                "time": str(t or ''),
                "already_sent": already_sent,
                "message": (
                    f"Dear {p.name}, this is a reminder for your dental appointment "
                    f"on {date_pretty} at {time_str}. Please arrive 10 minutes early."
                )
            })
            processed_ids.add(p.id)

        return Response(reminders)

# --- AUTH ---
class LoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        user = authenticate(username=username, password=password)
        if not user and username:
            try:
                user_obj = User.objects.filter(username__iexact=username).first()
                if user_obj:
                    from django.contrib.auth import authenticate as auth
                    user = auth(username=user_obj.username, password=password)
            except Exception:
                pass

        if user:
            role = 'Admin'
            perms = []
            doctor_profile_id = None
            name = user.get_full_name() or user.username
            
            user_id_str = str(user.pk) if user.pk else str(user.id)
            try:
                from django.db import connections
                db = connections['default'].database
                u_doc = db['auth_user'].find_one({'username': user.username})
                if u_doc:
                    user_id_str = str(u_doc['_id'])
                    s_doc = db['patients_staff'].find_one({'user_id': u_doc['_id']})
                    if s_doc:
                        role = s_doc.get('role', 'Admin')
                        perms = s_doc.get('permissions', [])
                        if s_doc.get('doctor_profile_id'):
                            doctor_profile_id = str(s_doc.get('doctor_profile_id'))
                        name = s_doc.get('name', name)
            except Exception:
                pass
            
            if getattr(user, 'is_superuser', False) or role == 'Admin':
                perms = ['income-analytics', 'expense-manager', 'billing', 'pharmacy', 'stock', 'prescriptions', 'lab', 'users', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'follow-ups', 'pre-bookings', 'communication', 'tele-medicine', 'website-appointment', 'purchases', 'doctors', 'settings', 'pathology-lab', 'dental-lab']
                
            return Response({
                'id': user_id_str,
                'username': user.username,
                'role': role,
                'is_superuser': getattr(user, 'is_superuser', False),
                'permissions': perms,
                'doctor_profile_id': doctor_profile_id,
                'doctor_id': doctor_profile_id,
                'name': name
            })
        return Response({'error': 'Invalid credentials'}, status=401)

def check_username_exists(username, exclude_user_id=None):
    if not username:
        return False
    db = connections['default'].database
    pattern = re.compile(f'^{re.escape(username.strip())}$', re.IGNORECASE)
    for u in db['auth_user'].find({'username': pattern}):
        if not exclude_user_id or str(u['_id']) != str(exclude_user_id):
            return True
    return False

def check_email_exists(email, exclude_staff_id=None, exclude_user_id=None):
    if not email:
        return False
    norm_e = normalize_email(email)
    if not norm_e:
        return False
    db = connections['default'].database
    # 1. Check Staff collection
    for s in Staff.objects.exclude(email__isnull=True).exclude(email=''):
        if exclude_staff_id and str(s.id) == str(exclude_staff_id):
            continue
        if s.email and normalize_email(s.email) == norm_e:
            return True
    # 2. Check auth_user collection
    pattern = re.compile(f'^{re.escape(norm_e)}$', re.IGNORECASE)
    for u in db['auth_user'].find({'email': pattern}):
        if not exclude_user_id or str(u['_id']) != str(exclude_user_id):
            return True
    return False

def check_phone_exists(phone, exclude_staff_id=None):
    if not phone:
        return False
    norm_p = normalize_phone(phone)
    if not norm_p:
        return False
    for s in Staff.objects.exclude(phone__isnull=True).exclude(phone=''):
        if exclude_staff_id and str(s.id) == str(exclude_staff_id):
            continue
        if s.phone and normalize_phone(s.phone) == norm_p:
            return True
    return False

class StaffCheckAvailabilityView(APIView):
    def get(self, request):
        req_user = get_authenticated_user(request)
        if not req_user:
            return Response({'detail': 'Authentication required.'}, status=401)
        if not is_application_admin(req_user):
            return Response({'detail': 'Administrative permission required.'}, status=403)

        username = request.query_params.get('username', '').strip().lower()
        email = request.query_params.get('email', '').strip().lower()
        phone = request.query_params.get('phone', '').strip()
        staff_id = request.query_params.get('staff_id', '').strip()

        user_id_to_exclude = None
        if staff_id:
            try:
                for s in Staff.objects.all():
                    if str(s.id) == str(staff_id) and s.user_id:
                        user_id_to_exclude = s.user_id
                        break
            except Exception:
                pass

        result = {}

        if username:
            if check_username_exists(username, exclude_user_id=user_id_to_exclude):
                result['username'] = {
                    'available': False,
                    'message': '✕ Username already exists. Please choose another username.'
                }
            else:
                result['username'] = {
                    'available': True,
                    'message': '✓ Username available'
                }

        if email:
            if check_email_exists(email, exclude_staff_id=staff_id, exclude_user_id=user_id_to_exclude):
                result['email'] = {
                    'available': False,
                    'message': '✕ Email address is already registered.'
                }
            else:
                result['email'] = {
                    'available': True,
                    'message': '✓ Email address available'
                }

        if phone:
            if check_phone_exists(phone, exclude_staff_id=staff_id):
                result['phone'] = {
                    'available': False,
                    'message': '✕ Phone number is already registered.'
                }
            else:
                result['phone'] = {
                    'available': True,
                    'message': '✓ Phone number available'
                }

        return Response(result)

class StaffCreateView(APIView):
    def post(self, request):
        data = request.data
        username = data.get('username', '').strip().lower()
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        role = data.get('role', 'Receptionist')

        req_user = get_authenticated_user(request)
        allowed, err_msg, err_status = can_create_staff_role(req_user, role)
        if not allowed:
            return Response({'detail': err_msg, 'error': err_msg}, status=err_status)

        name = data.get('name', '').strip()
        raw_phone = data.get('phone', '').strip()
        raw_email = data.get('email', '').strip().lower()
        
        phone = normalize_phone(raw_phone) if raw_phone else None
        email = normalize_email(raw_email) if raw_email else None
        
        gender = data.get('gender', '').strip()
        age = data.get('age') if data.get('age') not in [None, ''] else None
        dob = data.get('dob') if data.get('dob') not in [None, ''] else None
        blood_group = data.get('blood_group', '').strip()
        address = data.get('address', '').strip()
        status = data.get('status', 'Active').strip()
        emergency_contact = data.get('emergency_contact', '').strip()
        staff_level = data.get('staff_level', '').strip()
        permissions = data.get('permissions', [])
        base_salary = data.get('base_salary', 0)
        additional_details = data.get('additional_details', {})

        field_errors = {}
        if not name: field_errors['name'] = 'Full Name is required.'
        if not role: field_errors['role'] = 'Staff Role is required.'
        if not staff_level: field_errors['staff_level'] = 'Staff Level is required.'
        if not raw_phone or not phone: field_errors['phone'] = 'Phone Number is required.'
        if not gender: field_errors['gender'] = 'Gender is required.'
        if not dob: field_errors['dob'] = 'Date of Birth is required.'
        if age is None: field_errors['age'] = 'Age is required.'
        if not blood_group: field_errors['blood_group'] = 'Blood Group is required.'
        if not status: field_errors['status'] = 'Status is required.'
        if not address: field_errors['address'] = 'Residential Address is required.'
        if not username: field_errors['username'] = 'Username is required.'
        if not password: field_errors['password'] = 'Password is required.'
        if confirm_password is not None:
            if not confirm_password and password:
                field_errors['confirm_password'] = 'Please confirm your password.'
            elif password != confirm_password:
                field_errors['confirm_password'] = 'Passwords do not match.'

        # Validate Role-Specific Professional Information in backend
        add_det = additional_details or {}
        role_qual = str(add_det.get('qualification', '')).strip()
        role_spec = str(add_det.get('specialization', '')).strip()
        role_lic = str(add_det.get('license_no', '')).strip()
        role_council = str(add_det.get('registration_council', '')).strip()
        role_desig = str(add_det.get('designation', '')).strip()
        role_fee = add_det.get('consultation_fee')
        role_exp = add_det.get('experience_years')

        if role == 'Doctor':
            if not role_qual: field_errors['qualification'] = 'Qualification is required.'
            if not role_spec: field_errors['specialization'] = 'Specialization is required.'
            if not role_lic: field_errors['license_no'] = 'Dental Registration Number is required.'
            if not role_council: field_errors['registration_council'] = 'Registration Council is required.'
            if role_fee in [None, ''] or (isinstance(role_fee, str) and role_fee.strip() == ''):
                field_errors['consultation_fee'] = 'Consultation Fee is required.'
            else:
                try:
                    fee_val = float(role_fee)
                    if fee_val < 0:
                        field_errors['consultation_fee'] = 'Consultation Fee cannot be negative.'
                except (ValueError, TypeError):
                    field_errors['consultation_fee'] = 'Consultation Fee must be a valid number.'
        elif role == 'Receptionist':
            if not role_qual: field_errors['qualification'] = 'Highest Qualification is required.'
        elif role == 'Pharmacist':
            if not role_qual: field_errors['qualification'] = 'Qualification is required.'
            if not role_lic: field_errors['license_no'] = 'Pharmacy Registration Number is required.'
            if not role_council: field_errors['registration_council'] = 'Registration Council is required.'
        elif role in ['Dental Assistant', 'Assistant']:
            if not role_qual: field_errors['qualification'] = 'Qualification is required.'
        else:
            if not role_desig: field_errors['designation'] = 'Designation / Title is required.'

        # Validate Years of Experience (0 is valid, negative/decimal/empty are invalid)
        if role_exp in [None, ''] or (isinstance(role_exp, str) and role_exp.strip() == ''):
            field_errors['experience_years'] = 'Years of Experience is required.'
        else:
            try:
                exp_float = float(role_exp)
                if exp_float < 0:
                    field_errors['experience_years'] = 'Years of Experience cannot be negative.'
                elif not exp_float.is_integer():
                    field_errors['experience_years'] = 'Years of Experience must be a whole number.'
                else:
                    add_det['experience_years'] = int(exp_float)
                    additional_details['experience_years'] = int(exp_float)
            except (ValueError, TypeError):
                field_errors['experience_years'] = 'Years of Experience must be a valid number.'

        if field_errors:
            return Response({
                'success': False,
                'error': 'Please fill in all required fields.',
                'errors': field_errors
            }, status=400)

        # 1. Username uniqueness check
        if check_username_exists(username):
            return Response({
                'success': False,
                'error': 'Username already exists. Please choose another username.',
                'errors': {'username': 'Username already exists. Please choose another username.'}
            }, status=400)

        # 2. Phone uniqueness check
        if phone and check_phone_exists(phone):
            return Response({
                'success': False,
                'error': 'Phone number is already registered.',
                'errors': {'phone': 'This phone number is already registered.'}
            }, status=400)

        # 3. Email uniqueness check
        if email and check_email_exists(email):
            return Response({
                'success': False,
                'error': 'Email address is already registered.',
                'errors': {'email': 'This email is already registered.'}
            }, status=400)

        try:
            user = User.objects.create_user(username=username, password=password, first_name=name, email=email or '')
            
            doctor_profile = None
            if role == 'Doctor':
                spec = additional_details.get('specialization', 'General Dentist')
                qual = additional_details.get('qualification', '')
                fee = additional_details.get('consultation_fee', 500.00)
                exp = additional_details.get('experience_years', 0)
                doctor_profile = Doctor.objects.create(
                    name=name,
                    phone=raw_phone,
                    email=email or '',
                    specialization=spec,
                    qualification=qual,
                    consultation_fee=fee,
                    experience_years=exp
                )
                
            staff = Staff.objects.create(
                user=user,
                name=name,
                role=role,
                staff_level=staff_level,
                phone=phone,
                email=email,
                gender=gender,
                age=age,
                dob=dob,
                blood_group=blood_group,
                address=address,
                status=status,
                is_active=False if status == 'Inactive' else True,
                emergency_contact=emergency_contact,
                permissions=permissions,
                doctor_profile=doctor_profile,
                base_salary=base_salary,
                additional_details=additional_details
            )
            return Response({'success': True, 'id': staff.id, 'status': 'Staff created successfully'})
        except IntegrityError as e:
            err_str = str(e).lower()
            if 'email' in err_str or (email and check_email_exists(email)):
                return Response({'success': False, 'error': 'This email is already registered.', 'errors': {'email': 'This email is already registered.'}}, status=400)
            elif 'phone' in err_str or (phone and check_phone_exists(phone)):
                return Response({'success': False, 'error': 'This phone number is already registered.', 'errors': {'phone': 'This phone number is already registered.'}}, status=400)
            elif 'username' in err_str or (username and check_username_exists(username)):
                return Response({'success': False, 'error': 'This username is already taken.', 'errors': {'username': 'This username is already taken.'}}, status=400)
            return Response({'success': False, 'error': str(e), 'errors': {'non_field_errors': str(e)}}, status=400)
        except Exception as e:
            err_str = str(e).lower()
            if 'duplicate key' in err_str or 'e11000' in err_str:
                if 'email' in err_str or (email and check_email_exists(email)):
                    return Response({'success': False, 'error': 'This email is already registered.', 'errors': {'email': 'This email is already registered.'}}, status=400)
                elif 'phone' in err_str or (phone and check_phone_exists(phone)):
                    return Response({'success': False, 'error': 'This phone number is already registered.', 'errors': {'phone': 'This phone number is already registered.'}}, status=400)
                elif 'username' in err_str or (username and check_username_exists(username)):
                    return Response({'success': False, 'error': 'This username is already taken.', 'errors': {'username': 'This username is already taken.'}}, status=400)
            return Response({'success': False, 'error': str(e)}, status=400)

class StaffOnboardingView(APIView):
    def post(self, request):
        data = request.data
        
        basic_details = data.get('basic_details', {})
        employment = data.get('employment', {})
        role_submitted = employment.get('role', data.get('role', 'Receptionist'))

        req_user = get_authenticated_user(request)
        allowed, err_msg, err_status = can_create_staff_role(req_user, role_submitted)
        if not allowed:
            return Response({'detail': err_msg, 'error': err_msg}, status=err_status)
        login_data = data.get('login', {})
        benefits_data = data.get('benefits', [])
        leave_data = data.get('leave', data.get('leave_configs', []))
        insurance_data = data.get('insurance', {})
        permissions_data = data.get('permissions', [])

        if not basic_details and 'name' in data:
            basic_details = data
        if not employment and ('role' in data or 'staff_level' in data):
            employment = data
        if not login_data and ('username' in data or 'password' in data):
            login_data = data

        name = basic_details.get('name', '').strip()
        raw_phone = basic_details.get('phone', '').strip()
        raw_email = basic_details.get('email', '').strip().lower()
        gender = basic_details.get('gender', '').strip()
        dob = basic_details.get('dob') if basic_details.get('dob') not in [None, ''] else None
        age = basic_details.get('age') if basic_details.get('age') not in [None, ''] else None
        blood_group = basic_details.get('blood_group', '').strip()
        address = basic_details.get('address', '').strip()
        pincode = basic_details.get('pincode', '').strip()
        city = basic_details.get('city', '').strip()
        state = basic_details.get('state', '').strip()
        country = basic_details.get('country', '').strip()
        status = basic_details.get('status', 'Active').strip()
        emergency_contact = basic_details.get('emergency_contact', '').strip()

        role = employment.get('role', 'Receptionist').strip()
        staff_level = employment.get('staff_level', '').strip()
        joining_date = employment.get('joining_date') if employment.get('joining_date') not in [None, ''] else None
        base_salary = employment.get('base_salary', 0)
        additional_details = employment.get('additional_details', {}) or {}

        username = login_data.get('username', '').strip().lower()
        password = login_data.get('password', '')
        confirm_password = login_data.get('confirm_password')
        if confirm_password is None:
            confirm_password = data.get('confirm_password')

        phone = normalize_phone(raw_phone) if raw_phone else None
        email = normalize_email(raw_email) if raw_email else None

        field_errors = {}
        if not name: field_errors['name'] = 'Full Name is required.'
        if not role: field_errors['role'] = 'Staff Role is required.'
        if not staff_level: field_errors['staff_level'] = 'Staff Level is required.'
        if not raw_phone or not phone: field_errors['phone'] = 'Phone Number is required.'
        if not gender: field_errors['gender'] = 'Gender is required.'
        if not dob: field_errors['dob'] = 'Date of Birth is required.'
        if age is None: field_errors['age'] = 'Age is required.'
        if not blood_group: field_errors['blood_group'] = 'Blood Group is required.'
        if not status: field_errors['status'] = 'Status is required.'
        if not address: field_errors['address'] = 'Residential Address is required.'
        if not username: field_errors['username'] = 'Username is required.'
        if not password: field_errors['password'] = 'Password is required.'
        if confirm_password is not None:
            if not confirm_password and password:
                field_errors['confirm_password'] = 'Please confirm your password.'
            elif password != confirm_password:
                field_errors['confirm_password'] = 'Passwords do not match.'

        if pincode:
            if not re.match(r'^\d{6}$', pincode):
                field_errors['pincode'] = 'Pincode must be exactly 6 digits.'

        add_det = additional_details
        role_qual = str(add_det.get('qualification', '')).strip()
        role_spec = str(add_det.get('specialization', '')).strip()
        role_lic = str(add_det.get('license_no', '')).strip()
        role_council = str(add_det.get('registration_council', '')).strip()
        role_desig = str(add_det.get('designation', '')).strip()
        role_fee = add_det.get('consultation_fee')
        role_exp = add_det.get('experience_years')

        if role == 'Doctor':
            if not role_qual: field_errors['qualification'] = 'Qualification is required.'
            if not role_spec: field_errors['specialization'] = 'Specialization is required.'
            if not role_lic: field_errors['license_no'] = 'Dental Registration Number is required.'
            if not role_council: field_errors['registration_council'] = 'Registration Council is required.'
            if role_fee in [None, ''] or (isinstance(role_fee, str) and role_fee.strip() == ''):
                field_errors['consultation_fee'] = 'Consultation Fee is required.'
            else:
                try:
                    fee_val = float(role_fee)
                    if fee_val < 0:
                        field_errors['consultation_fee'] = 'Consultation Fee cannot be negative.'
                except (ValueError, TypeError):
                    field_errors['consultation_fee'] = 'Consultation Fee must be a valid number.'
        elif role == 'Receptionist':
            if not role_qual: field_errors['qualification'] = 'Highest Qualification is required.'
        elif role == 'Pharmacist':
            if not role_qual: field_errors['qualification'] = 'Qualification is required.'
            if not role_lic: field_errors['license_no'] = 'Pharmacy Registration Number is required.'
            if not role_council: field_errors['registration_council'] = 'Registration Council is required.'
        elif role in ['Dental Assistant', 'Assistant']:
            if not role_qual: field_errors['qualification'] = 'Qualification is required.'
        else:
            if not role_desig: field_errors['designation'] = 'Designation / Title is required.'

        if role_exp in [None, ''] or (isinstance(role_exp, str) and role_exp.strip() == ''):
            field_errors['experience_years'] = 'Years of Experience is required.'
        else:
            try:
                exp_float = float(role_exp)
                if exp_float < 0:
                    field_errors['experience_years'] = 'Years of Experience cannot be negative.'
                elif not exp_float.is_integer():
                    field_errors['experience_years'] = 'Years of Experience must be a whole number.'
                else:
                    add_det['experience_years'] = int(exp_float)
                    additional_details['experience_years'] = int(exp_float)
            except (ValueError, TypeError):
                field_errors['experience_years'] = 'Years of Experience must be a valid number.'

        if leave_data and isinstance(leave_data, list):
            for i, l_cfg in enumerate(leave_data):
                ent = l_cfg.get('annual_entitlement', 0)
                try:
                    if float(ent) < 0:
                        field_errors[f'leave_{i}_entitlement'] = 'Leave entitlement cannot be negative.'
                except (ValueError, TypeError):
                    field_errors[f'leave_{i}_entitlement'] = 'Invalid leave entitlement value.'

        if insurance_data and isinstance(insurance_data, dict):
            is_enabled = insurance_data.get('is_enabled', False)
            if is_enabled or insurance_data.get('provider'):
                cov = insurance_data.get('coverage_amount', 0)
                emp_contrib = insurance_data.get('employee_contribution', 0)
                empr_contrib = insurance_data.get('employer_contribution', 0)
                start_d = insurance_data.get('start_date')
                exp_d = insurance_data.get('expiry_date')
                try:
                    if float(cov) < 0: field_errors['coverage_amount'] = 'Coverage amount cannot be negative.'
                except (ValueError, TypeError): pass
                try:
                    if float(emp_contrib) < 0: field_errors['employee_contribution'] = 'Employee contribution cannot be negative.'
                except (ValueError, TypeError): pass
                try:
                    if float(empr_contrib) < 0: field_errors['employer_contribution'] = 'Employer contribution cannot be negative.'
                except (ValueError, TypeError): pass
                if start_d and exp_d and str(exp_d) < str(start_d):
                    field_errors['expiry_date'] = 'Expiry date cannot be before start date.'

        if field_errors:
            return Response({
                'success': False,
                'error': 'Please fix the validation errors.',
                'errors': field_errors
            }, status=400)

        if check_username_exists(username):
            return Response({'success': False, 'error': 'Username already exists.', 'errors': {'username': 'Username already exists.'}}, status=400)
        if phone and check_phone_exists(phone):
            return Response({'success': False, 'error': 'Phone number is already registered.', 'errors': {'phone': 'Phone number is already registered.'}}, status=400)
        if email and check_email_exists(email):
            return Response({'success': False, 'error': 'Email address is already registered.', 'errors': {'email': 'Email address is already registered.'}}, status=400)

        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, password=password, first_name=name, email=email or '')
                
                doctor_profile = None
                if role == 'Doctor':
                    spec = additional_details.get('specialization', 'General Dentist')
                    qual = additional_details.get('qualification', '')
                    fee = additional_details.get('consultation_fee', 500.00)
                    exp = additional_details.get('experience_years', 0)
                    doctor_profile = Doctor.objects.create(
                        name=name,
                        phone=raw_phone,
                        email=email or '',
                        specialization=spec,
                        qualification=qual,
                        consultation_fee=fee,
                        experience_years=exp
                    )

                full_add_det = dict(additional_details)
                if pincode: full_add_det['pincode'] = pincode
                if city: full_add_det['city'] = city
                if state: full_add_det['state'] = state
                if country: full_add_det['country'] = country
                if joining_date: full_add_det['joining_date'] = str(joining_date)

                staff = Staff.objects.create(
                    user=user,
                    name=name,
                    role=role,
                    staff_level=staff_level,
                    phone=phone,
                    email=email,
                    gender=gender,
                    age=age,
                    dob=dob,
                    blood_group=blood_group,
                    address=address,
                    status=status,
                    is_active=False if status == 'Inactive' else True,
                    emergency_contact=emergency_contact,
                    permissions=permissions_data,
                    doctor_profile=doctor_profile,
                    base_salary=base_salary,
                    additional_details=full_add_det
                )

                if leave_data and isinstance(leave_data, list):
                    for l_cfg in leave_data:
                        StaffLeaveConfig.objects.create(
                            staff=staff,
                            leave_type=l_cfg.get('leave_type', 'Casual Leave'),
                            annual_entitlement=l_cfg.get('annual_entitlement', 12),
                            is_paid=l_cfg.get('is_paid', True),
                            carry_forward=l_cfg.get('allow_carry_forward', l_cfg.get('carry_forward', True)),
                            max_carry_forward=l_cfg.get('max_carry_forward', 6),
                            applicable_from=l_cfg.get('applicable_from') or timezone.now(),
                            status=l_cfg.get('status', 'Active')
                        )

                if benefits_data and isinstance(benefits_data, list):
                    for b_cfg in benefits_data:
                        if b_cfg.get('benefit_name'):
                            StaffBenefit.objects.create(
                                staff=staff,
                                benefit_name=b_cfg.get('benefit_name'),
                                amount=b_cfg.get('amount', 0),
                                frequency=b_cfg.get('frequency', 'Monthly'),
                                notes=b_cfg.get('description', b_cfg.get('notes', '')),
                                is_active=True if b_cfg.get('status', 'Active') == 'Active' else False
                            )

                if insurance_data and isinstance(insurance_data, dict):
                    if insurance_data.get('is_enabled') or insurance_data.get('provider'):
                        StaffInsurance.objects.create(
                            staff=staff,
                            is_enabled=insurance_data.get('is_enabled', True),
                            provider=insurance_data.get('provider', ''),
                            policy_number=insurance_data.get('policy_number', ''),
                            policy_type=insurance_data.get('policy_type', 'Health Insurance'),
                            coverage_amount=insurance_data.get('coverage_amount', 0),
                            employee_contribution=insurance_data.get('employee_contribution', 0),
                            employer_contribution=insurance_data.get('employer_contribution', 0),
                            start_date=insurance_data.get('start_date') or None,
                            expiry_date=insurance_data.get('expiry_date') or None,
                            status=insurance_data.get('status', 'Active'),
                            notes=insurance_data.get('notes', '')
                        )

                return Response({'success': True, 'id': staff.id, 'status': 'Staff created successfully'}, status=201)

        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=400)


class StaffLeaveConfigManageView(APIView):
    def get(self, request, staff_id):
        req_user = get_authenticated_user(request)
        staff = get_object_or_404(Staff, pk=staff_id)
        allowed, err_msg, err_status = can_modify_staff(req_user, staff)
        if not allowed:
            return Response({'detail': err_msg}, status=err_status)
        leaves = StaffLeaveConfig.objects.filter(staff=staff)
        serializer = StaffLeaveConfigSerializer(leaves, many=True)
        return Response(serializer.data)

    def post(self, request, staff_id):
        req_user = get_authenticated_user(request)
        staff = get_object_or_404(Staff, pk=staff_id)
        allowed, err_msg, err_status = can_modify_staff(req_user, staff)
        if not allowed:
            return Response({'detail': err_msg}, status=err_status)
        data = request.data
        if isinstance(data, list):
            StaffLeaveConfig.objects.filter(staff=staff).delete()
            created = []
            for item in data:
                serializer = StaffLeaveConfigSerializer(data=item)
                if serializer.is_valid():
                    serializer.save(staff=staff)
                    created.append(serializer.data)
                else:
                    return Response(serializer.errors, status=400)
            return Response(created, status=201)
        else:
            serializer = StaffLeaveConfigSerializer(data=data)
            if serializer.is_valid():
                serializer.save(staff=staff)
                return Response(serializer.data, status=201)
            return Response(serializer.errors, status=400)


class StaffBenefitManageView(APIView):
    def get(self, request, staff_id):
        req_user = get_authenticated_user(request)
        staff = get_object_or_404(Staff, pk=staff_id)
        allowed, err_msg, err_status = can_modify_staff(req_user, staff)
        if not allowed:
            return Response({'detail': err_msg}, status=err_status)
        benefits = StaffBenefit.objects.filter(staff=staff)
        serializer = StaffBenefitSerializer(benefits, many=True)
        return Response(serializer.data)

    def post(self, request, staff_id):
        req_user = get_authenticated_user(request)
        staff = get_object_or_404(Staff, pk=staff_id)
        allowed, err_msg, err_status = can_modify_staff(req_user, staff)
        if not allowed:
            return Response({'detail': err_msg}, status=err_status)
        data = request.data
        if isinstance(data, list):
            StaffBenefit.objects.filter(staff=staff).delete()
            created = []
            for item in data:
                serializer = StaffBenefitSerializer(data=item)
                if serializer.is_valid():
                    serializer.save(staff=staff)
                    created.append(serializer.data)
            return Response(created, status=201)
        else:
            serializer = StaffBenefitSerializer(data=data)
            if serializer.is_valid():
                serializer.save(staff=staff)
                return Response(serializer.data, status=201)
            return Response(serializer.errors, status=400)


class StaffInsuranceManageView(APIView):
    def get(self, request, staff_id):
        req_user = get_authenticated_user(request)
        staff = get_object_or_404(Staff, pk=staff_id)
        allowed, err_msg, err_status = can_modify_staff(req_user, staff)
        if not allowed:
            return Response({'detail': err_msg}, status=err_status)
        insurance = StaffInsurance.objects.filter(staff=staff).order_by('-id')
        serializer = StaffInsuranceSerializer(insurance, many=True)
        return Response(serializer.data)

    def post(self, request, staff_id):
        req_user = get_authenticated_user(request)
        staff = get_object_or_404(Staff, pk=staff_id)
        allowed, err_msg, err_status = can_modify_staff(req_user, staff)
        if not allowed:
            return Response({'detail': err_msg}, status=err_status)
        data = dict(request.data)
        serializer = StaffInsuranceSerializer(data=data)
        if serializer.is_valid():
            serializer.save(staff=staff)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    def put(self, request, staff_id):
        req_user = get_authenticated_user(request)
        staff = get_object_or_404(Staff, pk=staff_id)
        allowed, err_msg, err_status = can_modify_staff(req_user, staff)
        if not allowed:
            return Response({'detail': err_msg}, status=err_status)
        insurance_id = request.data.get('id')
        if insurance_id:
            ins = get_object_or_404(StaffInsurance, pk=insurance_id, staff=staff)
            serializer = StaffInsuranceSerializer(ins, data=request.data, partial=True)
        else:
            ins = StaffInsurance.objects.filter(staff=staff).order_by('-id').first()
            if ins:
                serializer = StaffInsuranceSerializer(ins, data=request.data, partial=True)
            else:
                serializer = StaffInsuranceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(staff=staff)
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


class StaffListView(APIView):
    def get(self, request):
        req_user = get_authenticated_user(request)
        if not req_user:
            return Response({'detail': 'Authentication required.'}, status=401)
        if not is_application_admin(req_user):
            return Response({'detail': 'You do not have permission to view staff records.'}, status=403)
        staff = Staff.objects.all()
        data = []
        for s in staff:
            username = ''
            u = None
            if s.user_id:
                try:
                    u = User.objects.filter(pk=s.user_id).first()
                    if u:
                        username = u.username
                    else:
                        from django.db import connections
                        db = connections['default'].database
                        u_doc = db['auth_user'].find_one({'_id': s.user_id})
                        if u_doc: username = u_doc.get('username', '')
                except Exception:
                    pass
            data.append({
                'id': str(s.id),
                'name': s.name,
                'role': s.role,
                'staff_level': s.staff_level or 'Junior',
                'phone': s.phone or '',
                'email': s.email or (u.email if u else ''),
                'gender': s.gender or '',
                'age': s.age if s.age is not None else '',
                'dob': s.dob.strftime('%Y-%m-%d') if s.dob else '',
                'blood_group': s.blood_group or '',
                'address': s.address or '',
                'status': s.status or ('Active' if s.is_active else 'Inactive'),
                'is_active': s.is_active,
                'emergency_contact': s.emergency_contact or '',
                'username': username,
                'base_salary': s.base_salary,
                'incentive': s.incentive,
                'permissions': s.permissions or [],
                'additional_details': s.additional_details or {}
            })
        return Response(data)

class StaffUpdateView(APIView):
    def put(self, request, pk):
        try:
            staff = Staff.objects.get(pk=pk)
            data = request.data
            req_user = get_authenticated_user(request)
            allowed, err_msg, err_status = can_modify_staff(req_user, staff, new_role=data.get('role'))
            if not allowed:
                return Response({'detail': err_msg, 'error': err_msg}, status=err_status)

            name = data.get('name', '').strip()
            role = data.get('role', '').strip()
            staff_level = data.get('staff_level', '').strip()
            raw_phone = data.get('phone', '').strip()
            raw_email = data.get('email', '').strip().lower()
            gender = data.get('gender', '').strip()
            dob = data.get('dob') if data.get('dob') not in ['', None] else None
            age = data.get('age') if data.get('age') not in ['', None] else None
            blood_group = data.get('blood_group', '').strip()
            address = data.get('address', '').strip()
            status = data.get('status', '').strip()
            username = data.get('username', '').strip().lower()
            
            phone = normalize_phone(raw_phone) if raw_phone else None
            email = normalize_email(raw_email) if raw_email else None

            field_errors = {}
            if 'name' in data and not name: field_errors['name'] = 'Full Name is required.'
            if 'role' in data and not role: field_errors['role'] = 'Staff Role is required.'
            if 'staff_level' in data and not staff_level: field_errors['staff_level'] = 'Staff Level is required.'
            if 'phone' in data and (not raw_phone or not phone): field_errors['phone'] = 'Phone Number is required.'
            if 'gender' in data and not gender: field_errors['gender'] = 'Gender is required.'
            if 'dob' in data and not dob: field_errors['dob'] = 'Date of Birth is required.'
            if 'age' in data and age is None: field_errors['age'] = 'Age is required.'
            if 'blood_group' in data and not blood_group: field_errors['blood_group'] = 'Blood Group is required.'
            if 'status' in data and not status: field_errors['status'] = 'Status is required.'
            if 'address' in data and not address: field_errors['address'] = 'Residential Address is required.'
            if 'username' in data and not username: field_errors['username'] = 'Username is required.'

            if 'additional_details' in data:
                add_det = data.get('additional_details') or {}
                role_to_check = role or staff.role
                role_qual = str(add_det.get('qualification', '')).strip()
                role_spec = str(add_det.get('specialization', '')).strip()
                role_lic = str(add_det.get('license_no', '')).strip()
                role_council = str(add_det.get('registration_council', '')).strip()
                role_desig = str(add_det.get('designation', '')).strip()
                role_fee = add_det.get('consultation_fee')
                role_exp = add_det.get('experience_years')

                if role_to_check == 'Doctor':
                    if not role_qual: field_errors['qualification'] = 'Qualification is required.'
                    if not role_spec: field_errors['specialization'] = 'Specialization is required.'
                    if not role_lic: field_errors['license_no'] = 'Dental Registration Number is required.'
                    if not role_council: field_errors['registration_council'] = 'Registration Council is required.'
                    if role_fee in [None, ''] or (isinstance(role_fee, str) and role_fee.strip() == ''):
                        field_errors['consultation_fee'] = 'Consultation Fee is required.'
                    else:
                        try:
                            fee_val = float(role_fee)
                            if fee_val < 0:
                                field_errors['consultation_fee'] = 'Consultation Fee cannot be negative.'
                        except (ValueError, TypeError):
                            field_errors['consultation_fee'] = 'Consultation Fee must be a valid number.'
                elif role_to_check == 'Receptionist':
                    if not role_qual: field_errors['qualification'] = 'Highest Qualification is required.'
                elif role_to_check == 'Pharmacist':
                    if not role_qual: field_errors['qualification'] = 'Qualification is required.'
                    if not role_lic: field_errors['license_no'] = 'Pharmacy Registration Number is required.'
                    if not role_council: field_errors['registration_council'] = 'Registration Council is required.'
                elif role_to_check in ['Dental Assistant', 'Assistant']:
                    if not role_qual: field_errors['qualification'] = 'Qualification is required.'
                else:
                    if not role_desig: field_errors['designation'] = 'Designation / Title is required.'

                if role_exp in [None, ''] or (isinstance(role_exp, str) and role_exp.strip() == ''):
                    field_errors['experience_years'] = 'Years of Experience is required.'
                else:
                    try:
                        exp_float = float(role_exp)
                        if exp_float < 0:
                            field_errors['experience_years'] = 'Years of Experience cannot be negative.'
                        elif not exp_float.is_integer():
                            field_errors['experience_years'] = 'Years of Experience must be a whole number.'
                        else:
                            add_det['experience_years'] = int(exp_float)
                            data['additional_details'] = add_det
                    except (ValueError, TypeError):
                        field_errors['experience_years'] = 'Years of Experience must be a valid number.'

            if field_errors:
                return Response({
                    'success': False,
                    'error': 'Please fill in all required fields.',
                    'errors': field_errors
                }, status=400)

            if username and check_username_exists(username, exclude_user_id=staff.user_id):
                return Response({
                    'success': False,
                    'error': 'Username already exists. Please choose another username.',
                    'errors': {'username': 'This username is already taken.'}
                }, status=400)

            if phone and check_phone_exists(phone, exclude_staff_id=staff.id):
                return Response({
                    'success': False,
                    'error': 'Phone number is already registered to another staff member.',
                    'errors': {'phone': 'This phone number is already registered.'}
                }, status=400)

            if email and check_email_exists(email, exclude_staff_id=staff.id, exclude_user_id=staff.user_id):
                return Response({
                    'success': False,
                    'error': 'Email address is already registered to another staff member.',
                    'errors': {'email': 'This email is already registered.'}
                }, status=400)
            
            # Update User if username or password provided
            if staff.user_id:
                try:
                    db = connections['default'].database
                    update_fields = {}
                    if username: update_fields['username'] = username
                    if email: update_fields['email'] = email
                    if data.get('name'): update_fields['first_name'] = data.get('name')
                    if update_fields:
                        db['auth_user'].update_one({'_id': staff.user_id}, {'$set': update_fields})
                    password = data.get('password')
                    if password:
                        u = User.objects.get(pk=staff.user_id)
                        u.set_password(password)
                        u.save()
                except Exception:
                    pass
            
            # Update Staff record
            staff.name = data.get('name', staff.name)
            staff.phone = phone
            staff.email = email
            staff.gender = data.get('gender', staff.gender or '')
            staff.age = data.get('age') if 'age' in data and data.get('age') not in ['', None] else None
            staff.dob = data.get('dob') if 'dob' in data and data.get('dob') not in ['', None] else None
            staff.blood_group = data.get('blood_group', staff.blood_group or '')
            staff.address = data.get('address', staff.address or '')
            staff.status = data.get('status', staff.status or 'Active')
            staff.is_active = False if staff.status == 'Inactive' else True
            staff.emergency_contact = data.get('emergency_contact', staff.emergency_contact or '')

            if 'staff_level' in data:
                staff.staff_level = staff_level
            if 'base_salary' in data:
                staff.base_salary = data.get('base_salary')
            if 'incentive' in data:
                staff.incentive = data.get('incentive')
            if 'additional_details' in data:
                staff.additional_details = data.get('additional_details')
            
            # Handle role change
            old_role = staff.role
            new_role = data.get('role', staff.role)
            staff.role = new_role
            
            # If changing to Doctor, ensure doctor_profile exists
            if new_role == 'Doctor' and old_role != 'Doctor':
                if not staff.doctor_profile:
                    doctor_profile = Doctor.objects.create(name=staff.name, phone=raw_phone, email=email or '', specialization='General Dentist', consultation_fee=500.00)
                    staff.doctor_profile = doctor_profile

            # Update existing doctor profile name/phone/details if linked
            if staff.doctor_profile:
                d = staff.doctor_profile
                d.name = staff.name
                d.phone = staff.phone
                add_det = staff.additional_details or {}
                if 'specialization' in add_det: d.specialization = add_det['specialization']
                if 'qualification' in add_det: d.qualification = add_det['qualification']
                if 'consultation_fee' in add_det and add_det['consultation_fee'] not in [None, '']: d.consultation_fee = add_det['consultation_fee']
                if 'experience_years' in add_det and add_det['experience_years'] not in [None, '']: d.experience_years = int(add_det['experience_years'])
                d.save()

            # Sync with current month's Expense record
            if 'base_salary' in data or 'incentive' in data:
                from .models import Expense
                from datetime import datetime
                from django.utils import timezone
                
                current_month = datetime.now().strftime('%B %Y')
                expense = Expense.objects.filter(
                    category='doctor_salary',
                    paid_to=staff.name,
                    title__contains=current_month
                ).first()
                
                if expense:
                    expense.amount = (staff.base_salary or 0) + (staff.incentive or 0)
                    expense.notes = f"Month: {current_month} | Bonus: {staff.incentive}"
                    expense.description = staff.role
                    expense.save()
                else:
                    Expense.objects.create(
                        title=f'Salary - {current_month} - {staff.name}',
                        category='doctor_salary',
                        amount=(staff.base_salary or 0) + (staff.incentive or 0),
                        date=timezone.now().date(),
                        paid_to=staff.name,
                        description=staff.role,
                        notes=f"Month: {current_month} | Bonus: {staff.incentive}",
                        status='Pending'
                    )

            staff.save()
            return Response({'success': True, 'status': 'Staff updated successfully'})
        except Staff.DoesNotExist:
            return Response({'success': False, 'error': 'Staff member not found'}, status=404)
        except IntegrityError as e:
            err_str = str(e).lower()
            if 'email' in err_str:
                return Response({'success': False, 'error': 'This email is already registered.', 'errors': {'email': 'This email is already registered.'}}, status=400)
            elif 'phone' in err_str:
                return Response({'success': False, 'error': 'This phone number is already registered.', 'errors': {'phone': 'This phone number is already registered.'}}, status=400)
            elif 'username' in err_str:
                return Response({'success': False, 'error': 'This username is already taken.', 'errors': {'username': 'This username is already taken.'}}, status=400)
            return Response({'success': False, 'error': str(e), 'errors': {'non_field_errors': str(e)}}, status=400)
        except Exception as e:
            err_str = str(e).lower()
            if 'duplicate key' in err_str or 'e11000' in err_str:
                if 'email' in err_str or (email and check_email_exists(email, exclude_staff_id=pk, exclude_user_id=staff.user_id if 'staff' in locals() else None)):
                    return Response({'success': False, 'error': 'This email is already registered.', 'errors': {'email': 'This email is already registered.'}}, status=400)
                elif 'phone' in err_str or (phone and check_phone_exists(phone, exclude_staff_id=pk)):
                    return Response({'success': False, 'error': 'This phone number is already registered.', 'errors': {'phone': 'This phone number is already registered.'}}, status=400)
                elif 'username' in err_str or (username and check_username_exists(username, exclude_user_id=staff.user_id if 'staff' in locals() else None)):
                    return Response({'success': False, 'error': 'This username is already taken.', 'errors': {'username': 'This username is already taken.'}}, status=400)
            return Response({'success': False, 'error': str(e)}, status=400)

# ─── ROLE HELPER ──────────────────────────────────────────────────────────────
def get_user_role(request):
    """Extract the role of the currently logged-in user from Staff profile."""
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        if getattr(user, 'is_superuser', False):
            return 'Admin'
        from .security import get_staff_for_user
        staff = get_staff_for_user(user)
        if staff and staff.role:
            return staff.role
        return 'Staff'

    token_user_id = request.headers.get('X-User-Id')
    if token_user_id:
        try:
            from bson import ObjectId
            from django.db import connections
            db = connections['default'].database
            
            # 1. Find User document
            u_doc = None
            if ObjectId.is_valid(token_user_id):
                u_doc = db['auth_user'].find_one({'_id': ObjectId(token_user_id)})
            if not u_doc:
                u_doc = db['auth_user'].find_one({'username': token_user_id})
            
            if u_doc:
                # 2. Find Staff document
                s_doc = db['patients_staff'].find_one({'user_id': u_doc['_id']})
                if s_doc:
                    return s_doc.get('role', 'Admin')
                # If no staff record, but is superuser in user doc
                if u_doc.get('is_superuser'):
                    return 'Admin'
            
            # ORM Fallback (just in case)
            if ObjectId.is_valid(token_user_id):
                user = User.objects.filter(pk=token_user_id).first()
            else:
                user = User.objects.filter(username=token_user_id).first()
            
            if user:
                staff = Staff.objects.filter(user=user).first()
                return staff.role if staff else 'Admin'
                
        except Exception:
            pass
    return None

def require_role(request, allowed_roles):
    """Returns None if allowed, or a 403 Response if not."""
    role = get_user_role(request)
    if role is None:
        return Response({'error': 'Authentication required.'}, status=401)
    if role not in allowed_roles:
        return Response({'error': f'Access denied. Required roles: {allowed_roles}. Your role: {role}'}, status=403)
    return None

# ─── PHARMACY WORKFLOW ────────────────────────────────────────────────────────

class PharmacyQueueView(APIView):
    authentication_classes = []
    permission_classes = []
    """
    GET: Returns all PENDING prescriptions grouped by patient.
    Accessible to: Pharmacist, Admin, Doctor
    Receptionist gets read-only view (no prices).
    """
    def get(self, request):
        from collections import defaultdict
        role = get_user_role(request)
        show_prices = role in ['Pharmacist', 'Admin', 'Doctor']
        date_str = request.query_params.get('date', timezone.localtime(timezone.now()).date().isoformat())

        prescriptions = Prescription.objects.filter(
            status__in=['PENDING', 'BILLED']
        )

        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_of_day = timezone.make_aware(datetime.combine(target_date, time.min))
            end_of_day = timezone.make_aware(datetime.combine(target_date, time.max))
            prescriptions = prescriptions.filter(created_at__range=(start_of_day, end_of_day))

        # Evaluate querysets to lists to avoid multiple query runs
        prescriptions_list = list(prescriptions)

        # 2. Setup Direct Bills
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_of_day = timezone.make_aware(datetime.combine(target_date, time.min))
        end_of_day = timezone.make_aware(datetime.combine(target_date, time.max))
        
        direct_bills = Billing.objects.filter(
            created_at__range=(start_of_day, end_of_day),
            items__treatment__name__icontains='Pharmacy'
        ).exclude(notes__icontains='#').distinct()
        direct_bills_list = list(direct_bills)

        # Cache medicines to avoid querying database for every single item
        meds_cache = {m.name.lower(): m for m in MedicineMaster.objects.all()}

        # Collect unique patient IDs for bulk operations
        patient_ids = set()
        for rx in prescriptions_list:
            if rx.patient_id:
                patient_ids.add(rx.patient_id)
        for bill in direct_bills_list:
            if bill.patient_id:
                patient_ids.add(bill.patient_id)

        # Bulk fetch patients
        patients_dict = {p.id: p for p in Patient.objects.filter(id__in=list(patient_ids))} if patient_ids else {}

        # Prefetch related billing and payment objects for these patients to calculate balances in memory
        active_billings = Billing.objects.filter(
            patient_id__in=list(patient_ids),
            bill_type='Clinical'
        ).exclude(status='Cancelled').order_by('created_at') if patient_ids else []
        
        active_payments = Payment.objects.filter(
            patient_id__in=list(patient_ids)
        ).exclude(visit__billings__isnull=False).exclude(status='Cancelled') if patient_ids else []
        
        billing_ids = [b.id for b in active_billings]
        billing_items_cache = BillingItem.objects.filter(billing_id__in=billing_ids) if billing_ids else []
        
        billings_by_patient = defaultdict(list)
        for b in active_billings:
            billings_by_patient[b.patient_id].append(b)
            
        items_by_billing = defaultdict(list)
        for item in billing_items_cache:
            items_by_billing[item.billing_id].append(item)
            
        payments_by_patient = defaultdict(list)
        for p in active_payments:
            payments_by_patient[p.patient_id].append(p)

        def get_patient_balance_in_memory(p_id):
            p = patients_dict.get(p_id)
            if not p:
                return 0.0
            patient_billings = billings_by_patient[p.id]
            carry_forward_dates = []
            for b in patient_billings:
                has_carry_forward = any(
                    item.treatment and item.treatment.name == 'Outstanding balance (brought forward)'
                    for item in items_by_billing[b.id]
                )
                if has_carry_forward:
                    carry_forward_dates.append(b.created_at)
                    
            latest_carry_date = max(carry_forward_dates) if carry_forward_dates else None
            
            b_total = 0.0
            b_paid = 0.0
            for b in patient_billings:
                if latest_carry_date and b.created_at < latest_carry_date:
                    b_total += float(b.total_amount)
                    b_paid += float(b.total_amount)
                else:
                    b_total += float(b.total_amount)
                    b_paid += float(b.paid_amount)
            
            patient_payments = payments_by_patient[p.id]
            p_total = sum(float(x.total_amount) for x in patient_payments)
            p_paid = sum(float(x.paid_amount) for x in patient_payments)
            
            net = (b_total + p_total) - (b_paid + p_paid)
            adj = float(p.balance_adjustment or 0)
            return max(0.0, max(0.0, net) - adj)

        # Prefetch prescription items
        rx_ids = [rx.id for rx in prescriptions_list]
        items_by_rx = defaultdict(list)
        if rx_ids:
            rx_items = PrescriptionItem.objects.filter(prescription_id__in=rx_ids)
            for item in rx_items:
                items_by_rx[item.prescription_id].append(item)

        # Prefetch direct bill items and treatments
        direct_bill_ids = [b.id for b in direct_bills_list]
        direct_items_by_bill = defaultdict(list)
        direct_treatments_dict = {}
        if direct_bill_ids:
            direct_items = BillingItem.objects.filter(billing_id__in=direct_bill_ids)
            dt_ids = set(item.treatment_id for item in direct_items if item.treatment_id)
            direct_treatments_dict = {t.id: t for t in TreatmentMaster.objects.filter(id__in=list(dt_ids))} if dt_ids else {}
            for item in direct_items:
                direct_items_by_bill[item.billing_id].append(item)

        # Prefetch linked billings for prescriptions in bulk
        linked_bills = Billing.objects.filter(patient_id__in=list(patient_ids), notes__icontains='#') if patient_ids else []
        linked_bills_by_rx = {}
        for bill in linked_bills:
            notes = bill.notes or ''
            for rx in prescriptions_list:
                if f"#{rx.id}" in notes:
                    linked_bills_by_rx[rx.id] = bill
                    break

        queue = []
        
        # 1. Add Prescriptions
        for rx in prescriptions_list:
            items = []
            rx_items_list = items_by_rx.get(rx.id, [])
            for item in rx_items_list:
                med = meds_cache.get(item.medicine_name.lower())
                unit_price = float(med.sales_rate) if med else float(item.unit_price)
                total_price = unit_price * item.quantity

                item_data = {
                    'id': item.id,
                    'name': item.medicine_name,
                    'dosage': item.dosage,
                    'duration': item.duration,
                    'quantity': item.quantity,
                    'is_dispensed': item.is_dispensed,
                }
                if show_prices:
                    item_data['unit_price'] = unit_price
                    item_data['total_price'] = total_price
                items.append(item_data)

            linked_bill = linked_bills_by_rx.get(rx.id)
            p = patients_dict.get(rx.patient_id)

            queue.append({
                'type': 'PRESCRIPTION',
                'prescription_id': rx.id,
                'billing_id': linked_bill.id if linked_bill else None,
                'status': rx.status,
                'patient_id': rx.patient_id,
                'patient_name': p.name if p else 'Unknown',
                'patient_phone': p.phone if p else '',
                'patient_age': p.age if p else None,
                'patient_balance': get_patient_balance_in_memory(rx.patient_id),
                'date': rx.created_at.strftime('%d %b %Y %I:%M %p'),
                'items': items,
            })

        # 2. Add Direct Bills (Pharmacy only)
        for bill in direct_bills_list:
            items = []
            bi_items = direct_items_by_bill.get(bill.id, [])
            for bi in bi_items:
                t = direct_treatments_dict.get(bi.treatment_id)
                t_name = t.name.replace('Pharmacy: ', '') if t else 'Unknown'
                items.append({
                    'id': bi.id,
                    'name': t_name,
                    'quantity': bi.qty,
                    'unit_price': float(bi.price),
                    'total_price': float(bi.qty * bi.price)
                })
            
            p = patients_dict.get(bill.patient_id)
            queue.append({
                'type': 'DIRECT_BILL',
                'billing_id': bill.id,
                'status': 'BILLED',
                'patient_id': bill.patient_id,
                'patient_name': p.name if p else 'Unknown',
                'patient_phone': p.phone if p else '',
                'patient_balance': get_patient_balance_in_memory(bill.patient_id),
                'date': bill.created_at.strftime('%d %b %Y %I:%M %p'),
                'items': items,
                'total_amount': float(bill.total_amount)
            })

        queue.sort(key=lambda x: x['date'], reverse=True)
        return Response(queue)


class PharmacyBillView(APIView):
    authentication_classes = []
    permission_classes = []
    """
    POST: Generate a bill for a single prescription.
    - Only Pharmacist or Admin can do this.
    - Uses DB transaction to ensure stock + bill atomicity.
    - Prevents duplicate billing (prescription status = BILLED check).
    """
    def post(self, request):
        denied = require_role(request, ['Pharmacist', 'Admin', 'Doctor'])
        if denied:
            return denied

        from django.db import transaction
        from datetime import date

        def reduce_stock_batches(med, qty_to_reduce):
            """Reduces stock from batches based on FEFO (First Expiry First Out)"""
            batches = MedicineStock.objects.filter(medicine=med, quantity__gt=0).order_by('expiry_date')
            remaining = qty_to_reduce
            
            for b in batches:
                if remaining <= 0: break
                
                if b.quantity >= remaining:
                    b.quantity -= remaining
                    remaining = 0
                else:
                    remaining -= b.quantity
                    b.quantity = 0
                b.save()
            
            # Update master stock
            med.stock_quantity -= qty_to_reduce
            med.save()
            return remaining == 0


        from .models import PharmacySettings
        settings = PharmacySettings.load()

        prescription_id = request.data.get('prescription_id')
        payment_method = request.data.get('payment_method', 'Cash')

        if not prescription_id:
            return Response({'error': 'prescription_id is required.'}, status=400)

        try:
            rx = Prescription.objects.get(id=prescription_id)
        except Prescription.DoesNotExist:
            return Response({'error': 'Prescription not found.'}, status=404)

        # ── Prevent duplicate billing ──────────────────────────────────────────
        if rx.status == 'BILLED':
            return Response({'error': 'This prescription has already been billed.'}, status=400)

        try:
            with transaction.atomic():
                total_amount = Decimal('0.00')
                bill_items_data = []

                # Allow frontend to override items (quantity/price)
                override_items = request.data.get('items') # list of {name, quantity, unit_price}
                
                if override_items:
                    for o_item in override_items:
                        med_name = o_item.get('name')
                        qty = int(o_item.get('quantity', 0))
                        price = Decimal(str(o_item.get('unit_price', 0)))

                        med = MedicineMaster.objects.filter(name__iexact=med_name).first()
                        if med:
                            if med.stock_quantity < qty:
                                raise ValueError(f"Insufficient total stock for '{med_name}'.")
                            if settings.auto_deduct_stock_on_bill:
                                reduce_stock_batches(med, qty)
                        
                        total_amount += price * qty
                        bill_items_data.append({'name': med_name, 'qty': qty, 'price': price, 'med': med})
                else:
                    for item in rx.items.all():
                         med = MedicineMaster.objects.filter(name__iexact=item.medicine_name).first()
                         if med:
                             if med.stock_quantity < item.quantity:
                                 raise ValueError(f"Insufficient total stock for '{item.medicine_name}'.")
                             unit_price = med.sales_rate
                             if settings.auto_deduct_stock_on_bill:
                                 reduce_stock_batches(med, item.quantity)
                         else:
                             unit_price = item.unit_price
                         
                         total_amount += unit_price * item.quantity
                         bill_items_data.append({'name': item.medicine_name, 'qty': item.quantity, 'price': unit_price, 'med': med, 'item': item})

                if settings.apply_gst and settings.gst_percent > 0:
                    gst_amt = total_amount * (Decimal(str(settings.gst_percent)) / Decimal('100.00'))
                    total_amount += gst_amt

                # Create Billing Record
                billing = Billing.objects.create(
                    patient=rx.patient,
                    visit=rx.visit,
                    bill_type='Pharmacy',
                    total_amount=total_amount,
                    paid_amount=total_amount, # No credit for medicines - must be paid in full
                    payment_method=payment_method,
                    notes=f'Pharmacy bill for Prescription #{rx.id}'

                )

                for bd in bill_items_data:
                    # Get or create a TreatmentMaster entry for this medicine
                    tm, _ = TreatmentMaster.objects.get_or_create(
                        name=f"Pharmacy: {bd['name']}",
                        defaults={'price': bd['price'], 'fee_type': 'Pharmacy'}
                    )

                    BillingItem.objects.create(
                        billing=billing,
                        treatment=tm,
                        qty=bd['qty'],
                        price=bd['price']
                    )

                    # ── Mark original items as dispensed if they exist ────────────────
                    if 'item' in bd:
                        item = bd['item']
                        item.is_dispensed = True
                        item.unit_price = bd['price']
                        item.save()

                # ── Update prescription status → BILLED ───────────────────────
                rx.status = 'BILLED'
                rx.save()

                # ── Low stock alerts ──────────────────────────────────────────
                low_stock = []
                for bd in bill_items_data:
                    if bd['med'] and bd['med'].stock_quantity <= bd['med'].low_stock_threshold:
                        low_stock.append(f"{bd['med'].name} ({bd['med'].stock_quantity} left)")

                return Response({
                    'status': 'success',
                    'bill_id': billing.id,
                    'total_amount': float(total_amount),
                    'low_stock_alerts': low_stock,
                    'message': f'Bill #{billing.id} generated successfully.'
                })

        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        except Exception as e:
            return Response({'error': f'Billing failed: {str(e)}'}, status=500)


# DispenseMedicineView kept as alias for URL backward compatibility
DispenseMedicineView = PharmacyBillView

class DirectBillView(APIView):
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        denied = require_role(request, ['Pharmacist', 'Admin', 'Doctor'])
        if denied:
            return denied

        from django.db import transaction
        from datetime import date
        from .models import Patient, Visit, Appointment, Billing, BillingItem, TreatmentMaster, MedicineMaster, MedicineStock
        from decimal import Decimal

        def reduce_stock_batches(med, qty_to_reduce):
            batches = MedicineStock.objects.filter(medicine=med, quantity__gt=0).order_by('expiry_date')
            remaining = qty_to_reduce
            
            for b in batches:
                if remaining <= 0: break
                
                if b.quantity >= remaining:
                    b.quantity -= remaining
                    remaining = 0
                else:
                    remaining -= b.quantity
                    b.quantity = 0
                b.save()
            
            med.stock_quantity -= qty_to_reduce
            med.save()
            return remaining == 0

        from .models import PharmacySettings
        settings = PharmacySettings.load()
        if settings.require_prescription:
            return Response({'error': 'Direct billing is disabled because prescriptions are required by the pharmacy settings.'}, status=400)

        patient_id = request.data.get('patient_id')
        payment_method = request.data.get('payment_method', 'Cash')
        items = request.data.get('items', [])

        if not patient_id or not items:
            return Response({'error': 'patient_id and items are required.'}, status=400)

        try:
            patient = Patient.objects.get(id=patient_id)
        except Patient.DoesNotExist:
            return Response({'error': 'Patient not found.'}, status=404)

        try:
            with transaction.atomic():
                total_amount = Decimal('0.00')
                bill_items_data = []

                for item in items:
                    med_id = item.get('medicine_id')
                    qty = int(item.get('quantity', 0))
                    price = Decimal(str(item.get('unit_price', 0)))

                    med = MedicineMaster.objects.get(id=med_id)
                    if med.stock_quantity < qty:
                        raise ValueError(f"Insufficient total stock for '{med.name}'.")
                    if settings.auto_deduct_stock_on_bill:
                        reduce_stock_batches(med, qty)
                    
                    total_amount += price * qty
                    bill_items_data.append({'name': med.name, 'qty': qty, 'price': price, 'med': med})

                if settings.apply_gst and settings.gst_percent > 0:
                    gst_amt = total_amount * (Decimal(str(settings.gst_percent)) / Decimal('100.00'))
                    total_amount += gst_amt

                from django.utils import timezone
                appt = Appointment.objects.create(
                    patient=patient,
                    date=timezone.localtime(timezone.now()).date(),
                    time=timezone.now().time(),
                    status='Completed',
                    notes='Direct Pharmacy Sale'
                )
                visit = Visit.objects.create(patient=patient, appointment=appt, notes='Direct Pharmacy Sale')

                billing = Billing.objects.create(
                    patient=patient,
                    visit=visit,
                    bill_type='Pharmacy',
                    total_amount=total_amount,
                    paid_amount=total_amount, 
                    payment_method=payment_method,
                    notes='Direct Pharmacy POS Sale'
                )

                for bd in bill_items_data:
                    tm, _ = TreatmentMaster.objects.get_or_create(
                        name=f"Pharmacy: {bd['name']}",
                        defaults={'price': bd['price'], 'fee_type': 'Pharmacy'}
                    )
                    BillingItem.objects.create(
                        billing=billing,
                        treatment=tm,
                        qty=bd['qty'],
                        price=bd['price']
                    )

                low_stock = []
                for bd in bill_items_data:
                    if bd['med'].stock_quantity <= bd['med'].low_stock_threshold:
                        low_stock.append(f"{bd['med'].name} ({bd['med'].stock_quantity} left)")

                return Response({
                    'status': 'success',
                    'bill_id': billing.id,
                    'total_amount': float(total_amount),
                    'low_stock_alerts': low_stock,
                    'message': f'Direct Bill #{billing.id} generated successfully.'
                })

        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        except Exception as e:
            return Response({'error': f'Billing failed: {str(e)}'}, status=500)

# PrescriptionQueueView — the real queue implementation used by both
# Pharmacist (with prices) and Receptionist (without prices)
PrescriptionQueueView = PharmacyQueueView

class StockManageView(APIView):
    authentication_classes = []
    permission_classes = []
    """
    GET: List all medicines with stock info.
    POST: Add new medicine.
    PATCH: Update stock/rates for a medicine.
    Only Pharmacist and Admin can POST/PATCH.
    """
    def get(self, request):
        medicines = MedicineMaster.objects.all().order_by('name')
        serializer = MedicineMasterSerializer(medicines, many=True)
        # Add is_low_stock calculated field manually if not in serializer
        data = serializer.data
        for item, m in zip(data, medicines):
            item['is_low_stock'] = m.stock_quantity <= m.low_stock_threshold
        return Response(data)

    def post(self, request):
        denied = require_role(request, ['Pharmacist', 'Admin'])
        if denied:
            return denied

        name = request.data.get('name', '').strip()
        if not name:
            return Response({'error': 'Medicine name is required.'}, status=400)

        try:
            med, created = MedicineMaster.objects.get_or_create(name__iexact=name, defaults={'name': name})
            
            # Use a helper to safely parse numbers
            def parse_num(val, default):
                if val is None or str(val).strip() == '': return default
                try: return float(val)
                except: return default

            def parse_int(val, default):
                if val is None or str(val).strip() == '': return default
                try: return int(float(val))
                except: return default

            med.purchase_rate = parse_num(request.data.get('purchase_rate'), med.purchase_rate)
            med.sales_rate = parse_num(request.data.get('sales_rate'), med.sales_rate)
            med.stock_quantity = parse_int(request.data.get('stock_quantity'), med.stock_quantity)
            med.low_stock_threshold = parse_int(request.data.get('low_stock_threshold'), med.low_stock_threshold)
            if 'dosage' in request.data:
                med.dosage = str(request.data.get('dosage') or '').strip()
            if 'frequency' in request.data:
                med.frequency = str(request.data.get('frequency') or '').strip()
            if 'notes' in request.data:
                med.notes = str(request.data.get('notes') or '').strip()
            if 'is_active' in request.data:
                med.is_active = bool(request.data.get('is_active'))
            med.save()

            return Response({
                'id': med.id,
                'name': med.name,
                'dosage': med.dosage,
                'frequency': med.frequency,
                'stock_quantity': med.stock_quantity,
                'is_active': med.is_active,
                'created': created,
            })
        except Exception as e:
            return Response({'error': f'Failed to save medicine: {str(e)}'}, status=500)

    def patch(self, request, pk):
        denied = require_role(request, ['Pharmacist', 'Admin'])
        if denied:
            return denied

        try:
            med = MedicineMaster.objects.get(id=pk)
            
            def parse_num(val, default):
                if val is None or str(val).strip() == '': return default
                try: return float(val)
                except: return default

            def parse_int(val, default):
                if val is None or str(val).strip() == '': return default
                try: return int(float(val))
                except: return default

            if 'purchase_rate' in request.data:
                med.purchase_rate = parse_num(request.data['purchase_rate'], med.purchase_rate)
            if 'sales_rate' in request.data:
                med.sales_rate = parse_num(request.data['sales_rate'], med.sales_rate)
            if 'stock_quantity' in request.data:
                med.stock_quantity = parse_int(request.data['stock_quantity'], med.stock_quantity)
            if 'low_stock_threshold' in request.data:
                med.low_stock_threshold = parse_int(request.data['low_stock_threshold'], med.low_stock_threshold)
            if 'dosage' in request.data:
                med.dosage = str(request.data.get('dosage') or '').strip()
            if 'frequency' in request.data:
                med.frequency = str(request.data.get('frequency') or '').strip()
            if 'notes' in request.data:
                med.notes = str(request.data.get('notes') or '').strip()
            if 'is_active' in request.data:
                med.is_active = bool(request.data['is_active'])
            med.save()

            return Response({'status': 'updated', 'id': med.id})
        except MedicineMaster.DoesNotExist:
            return Response({'error': 'Medicine not found.'}, status=404)
        except Exception as e:
            return Response({'error': f'Update failed: {str(e)}'}, status=500)

    def delete(self, request, pk):
        denied = require_role(request, ['Pharmacist', 'Admin'])
        if denied:
            return denied
        try:
            med = MedicineMaster.objects.get(id=pk)
            med.delete()
            return Response({'status': 'deleted'})
        except MedicineMaster.DoesNotExist:
            return Response({'error': 'Medicine not found.'}, status=404)
        except Exception as e:
            return Response({'error': f'Delete failed: {str(e)}'}, status=500)


class MedicinePurchaseView(APIView):
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        denied = require_role(request, ['Pharmacist', 'Admin'])
        if denied: return denied

        med_name = request.data.get('medicine_name', '').strip()
        supplier = request.data.get('supplier', '').strip()
        quantity = int(request.data.get('quantity', 0))
        purchase_rate = Decimal(str(request.data.get('purchase_rate', 0)))
        sales_rate = Decimal(str(request.data.get('sales_rate', 0)))
        
        # New parameters
        expiry_date_str = request.data.get('expiry_date')
        currently_paying_val = request.data.get('currently_paying')
        add_to_pending = request.data.get('add_to_pending_expenses', False)

        if not med_name or quantity <= 0:
            return Response({'error': 'Medicine name and positive quantity required.'}, status=400)

        from django.db import transaction
        try:
            with transaction.atomic():
                med, created = MedicineMaster.objects.get_or_create(
                    name__iexact=med_name,
                    defaults={'name': med_name, 'purchase_rate': purchase_rate, 'sales_rate': sales_rate}
                )
                
                # Update stock and rates
                med.stock_quantity += quantity
                med.purchase_rate = purchase_rate
                if sales_rate > 0:
                    med.sales_rate = sales_rate
                med.save()

                from django.utils.dateparse import parse_date
                exp_date = parse_date(expiry_date_str) if expiry_date_str else None

                # Compute costs
                total_cost = purchase_rate * quantity
                currently_paying = Decimal(str(currently_paying_val)) if currently_paying_val is not None else total_cost
                balance = total_cost - currently_paying

                # Record purchase history
                purchase = MedicinePurchase.objects.create(
                    medicine=med,
                    supplier=supplier,
                    quantity=quantity,
                    purchase_rate=purchase_rate,
                    expiry_date=exp_date,
                    currently_paying=currently_paying,
                    balance=balance
                )

                # Optional: Update/create batch in MedicineStock
                if exp_date:
                    from django.utils import timezone
                    batch_no = f"B-{timezone.now().strftime('%Y%m%d')}"
                    from .models import MedicineStock
                    MedicineStock.objects.create(
                        medicine=med,
                        batch_no=batch_no,
                        expiry_date=exp_date,
                        quantity=quantity,
                        purchase_price=purchase_rate,
                        mrp=sales_rate
                    )

                cat_obj = ExpenseCategory.objects.filter(key='pharmacy_purchase').first()
                expense_date = timezone.localtime(purchase.date).date() if purchase.date else datetime.date.today()
                
                # Paid Expense (if currently paying > 0)
                if currently_paying > 0:
                    Expense.objects.create(
                        title=f"Medicine Purchase - {med.name}",
                        category='pharmacy_purchase',
                        category_ref=cat_obj,
                        description=f"Purchased x{quantity} units of {med.name} from {supplier or 'Unknown Supplier'} at ₹{purchase_rate}/unit. Paid portion.",
                        amount=currently_paying,
                        date=expense_date,
                        paid_to=supplier or 'Unknown Supplier',
                        payment_method='Cash',
                        status='Paid',
                        notes=f"Linked to Medicine Purchase Log #{purchase.id}"
                    )
                
                # Pending Balance Expense
                if balance > 0:
                    Expense.objects.create(
                        title=f"Pending Balance - Medicine Purchase - {med.name}",
                        category='pharmacy_purchase',
                        category_ref=cat_obj,
                        description=f"Outstanding balance for stock purchase of x{quantity} units of {med.name} from {supplier or 'Unknown Supplier'}.",
                        amount=balance,
                        date=expense_date,
                        paid_to=supplier or 'Unknown Supplier',
                        payment_method='Cash',
                        status='Pending',
                        notes=f"Outstanding balance linked to Purchase Log #{purchase.id}"
                    )

                return Response({
                    'status': 'success',
                    'medicine': med.name,
                    'new_stock': med.stock_quantity,
                    'purchase_id': purchase.id
                })
        except Exception as e:
            return Response({'error': str(e)}, status=500)

class MedicinePurchaseHistoryView(APIView):
    def get(self, request):
        view_type = request.query_params.get('view', 'items')
        data = []
        
        from datetime import date, datetime, time
        if view_type == 'invoice':
            adv_purchases = PharmacyPurchase.objects.all()
            for p in adv_purchases:
                p_date = p.purchase_date
                if isinstance(p_date, date):
                    p_date = datetime.combine(p_date, time.min)
                
                data.append({
                    'id': f"p-{p.id}",
                    'date': p_date,
                    'medicine_name': 'Bulk Advanced Purchase',
                    'supplier': p.supplier.name if p.supplier else '--',
                    'invoice_no': p.invoice_no,
                    'total_amount': p.grand_total,
                    'paid_amount': p.paid_amount,
                    'payment_method': 'Bank Transfer'
                })
                
            purchases = MedicinePurchase.objects.all()
            for p in purchases:
                data.append({
                    'id': f"m-{p.id}",
                    'date': p.date,
                    'medicine_name': p.medicine.name if p.medicine else 'Unknown',
                    'supplier': p.supplier,
                    'invoice_no': '--',
                    'total_amount': p.total_amount,
                    'paid_amount': p.total_amount,
                    'payment_method': 'Cash'
                })
                
            data.sort(key=lambda x: x['date'], reverse=True)
            return Response(data)

        # 1. Get simple purchases
        purchases = MedicinePurchase.objects.all()
        for p in purchases:
            data.append({
                'id': f"m-{p.id}",
                'date': p.date, # This is a DateTimeField
                'medicine_name': p.medicine.name,
                'supplier': p.supplier,
                'quantity': p.quantity,
                'purchase_rate': p.purchase_rate,
                'sales_rate': p.medicine.sales_rate if (p.medicine and p.medicine.sales_rate) else 0.0,
                'total_amount': p.total_amount,
                'expiry_date': p.expiry_date.strftime('%Y-%m-%d') if p.expiry_date else '',
                'currently_paying': float(p.currently_paying) if p.currently_paying is not None else float(p.total_amount),
                'balance': float(p.balance) if p.balance is not None else 0.0
            })
            
        # 2. Get advanced purchases (from PharmacyPurchaseItem)
        adv_items = PharmacyPurchaseItem.objects.all()
        for item in adv_items:
            # Convert date to datetime for consistent sorting if needed
            p_date = item.purchase.purchase_date
            if isinstance(p_date, date):
                from datetime import datetime, time
                p_date = datetime.combine(p_date, time.min)

            # Proportional calculation for advanced purchases
            grand_total = float(item.purchase.grand_total)
            item_amount = float(item.amount)
            paid_amount = float(item.purchase.paid_amount)
            balance_due = float(item.purchase.balance_due)
            
            proportional_paid = (item_amount / grand_total) * paid_amount if grand_total > 0 else 0.0
            proportional_balance = (item_amount / grand_total) * balance_due if grand_total > 0 else 0.0

            data.append({
                'id': f"p-{item.id}",
                'date': p_date,
                'medicine_name': item.medicine.name,
                'supplier': item.purchase.supplier.name,
                'quantity': item.qty,
                'purchase_rate': item.purchase_price,
                'sales_rate': item.mrp,
                'total_amount': item.amount,
                'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else '',
                'currently_paying': round(proportional_paid, 2),
                'balance': round(proportional_balance, 2)
            })
            
        # Sort by date (descending)
        data.sort(key=lambda x: x['date'], reverse=True)
        return Response(data)
# --- ACCOUNTS / TRANSACTIONS ---
class TransactionListView(APIView):
    def get(self, request):
        type_filter = request.query_params.get('type')
        category_filter = request.query_params.get('category')
        doctor_filter = request.query_params.get('doctor')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        queryset = Transaction.objects.all().order_by('-date', '-created_at')

        if type_filter:
            queryset = queryset.filter(type=type_filter)
        if category_filter:
            queryset = queryset.filter(category=category_filter)
        if doctor_filter:
            queryset = queryset.filter(doctor_id=doctor_filter)
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        serializer = TransactionSerializer(queryset, many=True)
        return Response(serializer.data)

class TransactionCreateView(APIView):
    def post(self, request):
        serializer = TransactionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AccountSummaryView(APIView):
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        doctor_id = request.query_params.get('doctor')

        queryset = Transaction.objects.all()
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        if doctor_id:
            queryset = queryset.filter(doctor_id=doctor_id)

        income = queryset.filter(type='Income').aggregate(total=Sum('amount'))['total'] or 0
        expense = queryset.filter(type='Expense').aggregate(total=Sum('amount'))['total'] or 0

        # Calculate profit
        profit = float(income) - float(expense)

        # Category Breakdown
        categories = queryset.values('type', 'category').annotate(total=Sum('amount')).order_by('-total')

        return Response({
            "total_income": float(income),
            "total_expense": float(expense),
            "net_profit": profit,
            "category_breakdown": categories
        })
# --- PHARMACY PURCHASE & STOCK ---
class SupplierListView(APIView):
    def get(self, request):
        suppliers = Supplier.objects.all().order_by('name')
        return Response(SupplierSerializer(suppliers, many=True).data)
    
    @transaction.atomic
    def post(self, request):
        data = request.data.copy()
        opening_balance = data.pop('opening_balance', 0)
        
        serializer = SupplierSerializer(data=data)
        if serializer.is_valid():
            supplier = serializer.save()
            if float(opening_balance) != 0:
                SupplierLedger.objects.create(
                    supplier=supplier,
                    entry_type='Old Balance',
                    amount=Decimal(str(opening_balance)),
                    notes='Opening Balance'
                )
                supplier.total_balance = Decimal(str(opening_balance))
                supplier.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SupplierDetailView(APIView):
    def delete(self, request, pk):
        supplier = get_object_or_404(Supplier, pk=pk)
        supplier.delete()
        return Response({'status': 'deleted'})

class PharmacyPurchaseCreateView(APIView):
    @transaction.atomic
    def post(self, request):
        data = request.data
        items_data = data.pop('items', [])
        
        # 1. Create Purchase Header
        serializer = PharmacyPurchaseSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        purchase = serializer.save()
        
        # 3. Update Supplier Balance
        supplier = purchase.supplier
        supplier.total_balance += purchase.balance_due
        supplier.save()
        
        # 4. Process Items and Update Stock
        for item in items_data:
            medicine = get_object_or_404(MedicineMaster, id=item['medicine'])
            
            # Create Purchase Item
            PharmacyPurchaseItem.objects.create(
                purchase=purchase,
                medicine=medicine,
                batch_no=item['batch_no'],
                expiry_date=item['expiry_date'],
                qty=item['qty'],
                free_qty=item.get('free_qty', 0),
                purchase_price=item['purchase_price'],
                mrp=item['mrp'],
                tax_percent=item.get('tax_percent', 0),
                discount_percent=item.get('discount_percent', 0),
                amount=item['amount']
            )
            
            # Update/Create Stock entry
            stock, created = MedicineStock.objects.get_or_create(
                medicine=medicine,
                batch_no=item['batch_no'],
                defaults={
                    'expiry_date': item['expiry_date'],
                    'purchase_price': item['purchase_price'],
                    'mrp': item['mrp']
                }
            )
            
            total_qty = int(item['qty']) + int(item.get('free_qty', 0))
            stock.quantity += total_qty
            stock.save()
            
            # Update MedicineMaster total stock and rates
            medicine.stock_quantity += total_qty
            medicine.purchase_rate = item['purchase_price']
            if item.get('mrp'):
                medicine.sales_rate = item['mrp']
            medicine.save()

        # Create corresponding Expense
        import datetime
        cat_obj = ExpenseCategory.objects.filter(key='pharmacy_purchase').first()
        Expense.objects.create(
            title=f"Pharmacy Purchase - Inv #{purchase.invoice_no or purchase.id}",
            category='pharmacy_purchase',
            category_ref=cat_obj,
            description=f"Purchased medicines from supplier {supplier.name}. Grand Total: ₹{purchase.grand_total}, Paid: ₹{purchase.paid_amount}, Balance: ₹{purchase.balance_due}.",
            amount=purchase.grand_total,
            date=purchase.purchase_date or datetime.date.today(),
            paid_to=supplier.name,
            payment_method=data.get('payment_method', 'Cash'),
            status='Paid' if purchase.balance_due == 0 else 'Pending',
            notes=f"Linked to Pharmacy Purchase Log #{purchase.id}"
        )
            
        return Response(PharmacyPurchaseSerializer(purchase).data, status=status.HTTP_201_CREATED)

class MedicineStockListView(APIView):
    def get(self, request):
        stocks = MedicineStock.objects.all().order_by('expiry_date')
        return Response(MedicineStockSerializer(stocks, many=True).data)

class SupplierLedgerView(APIView):
    def get(self, request, supplier_id):
        ledger = SupplierLedger.objects.filter(supplier_id=supplier_id).order_by('-created_at')
        return Response(SupplierLedgerSerializer(ledger, many=True).data)

    @transaction.atomic
    def post(self, request, supplier_id):
        supplier = get_object_or_404(Supplier, id=supplier_id)
        data = request.data.copy()
        data['supplier'] = supplier.id
        
        serializer = SupplierLedgerSerializer(data=data)
        if serializer.is_valid():
            entry = serializer.save()
            # Update supplier balance
            # Old Balance and Adjustment increase balance, Payment decreases it
            if entry.entry_type in ['Old Balance', 'Adjustment']:
                supplier.total_balance += entry.amount
            elif entry.entry_type == 'Payment':
                supplier.total_balance -= entry.amount
            supplier.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SupplierLedgerDeleteView(APIView):
    @transaction.atomic
    def delete(self, request, pk):
        entry = get_object_or_404(SupplierLedger, pk=pk)
        supplier = entry.supplier
        
        # Reverse the balance update
        if entry.entry_type in ['Old Balance', 'Adjustment']:
            supplier.total_balance -= entry.amount
        elif entry.entry_type == 'Payment':
            supplier.total_balance += entry.amount
        
        supplier.save()
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class PharmacyPurchaseDeleteView(APIView):
    @transaction.atomic
    def delete(self, request, pk):
        purchase = get_object_or_404(PharmacyPurchase, pk=pk)
        supplier = purchase.supplier
        # Subtract the balance that was added to supplier's debt
        supplier.total_balance -= purchase.balance_due
        supplier.save()
        # Delete linked Expense
        Expense.objects.filter(notes=f"Linked to Pharmacy Purchase Log #{purchase.id}").delete()
        purchase.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class MedicinePurchaseDeleteView(APIView):
    def delete(self, request, pk):
        purchase = get_object_or_404(MedicinePurchase, pk=pk)
        # Delete linked Expense
        Expense.objects.filter(notes=f"Linked to Medicine Purchase Log #{purchase.id}").delete()
        purchase.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# --- TAX & COMMUNICATION ---
class TaxSettingListView(APIView):
    def get(self, request):
        taxes = TaxSetting.objects.all().order_by('name')
        return Response(TaxSettingSerializer(taxes, many=True).data)
    
    def post(self, request):
        serializer = TaxSettingSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TaxSettingDetailView(APIView):
    def delete(self, request, pk):
        tax = get_object_or_404(TaxSetting, pk=pk)
        tax.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class CommunicationTemplateListView(APIView):
    def get(self, request):
        if not CommunicationTemplate.objects.exists():
            default_templates = [
                {"category": "Appointment", "type": "Confirmation", "text": "Dear [Name], your dental appointment is confirmed for today. Please arrive 10 mins early. Thank you!"},
                {"category": "Follow-up", "type": "Reminder", "text": "Dear [Name], this is a gentle reminder regarding your follow-up appointment. Please let us know if you need to reschedule."},
                {"category": "Billing", "type": "Payment Receipt", "text": "Dear [Name], we have received your payment for your recent dental procedure. Thank you for choosing our clinic!"},
                {"category": "Greeting", "type": "Welcome", "text": "Welcome [Name]! We are excited to assist you with your dental care and help you maintain a healthy smile."},
                {"category": "Greeting", "type": "Birthday Wish", "text": "Happy Birthday [Name]! 🎂 Wishing you a wonderful day filled with joy and smiles from all of us at the dental clinic!"},
                {"category": "Appointment", "type": "Missed Appointment", "text": "Dear [Name], we noticed you missed your scheduled appointment today. Please call us to reschedule at your convenience."},
                {"category": "Clinical", "type": "Post-Op Care", "text": "Dear [Name], please take your prescribed medications on time and avoid hard or hot foods today. Take rest and feel free to reach out if you have any discomfort."},
                {"category": "Reminder", "type": "Routine Dental Checkup", "text": "Dear [Name], it has been 6 months since your last dental checkup! Regular cleanings protect your teeth. Book your slot today."}
            ]
            for t in default_templates:
                CommunicationTemplate.objects.create(**t)
        templates = CommunicationTemplate.objects.all().order_by('category', 'type')
        return Response(CommunicationTemplateSerializer(templates, many=True).data)

    def post(self, request):
        serializer = CommunicationTemplateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CommunicationTemplateDetailView(APIView):
    def patch(self, request, pk):
        template = get_object_or_404(CommunicationTemplate, pk=pk)
        serializer = CommunicationTemplateSerializer(template, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        template = get_object_or_404(CommunicationTemplate, pk=pk)
        template.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# --- DENTAL LAB SETTINGS ---
class DentalLaboratoryListView(APIView):
    def get(self, request):
        labs = DentalLaboratory.objects.all().order_by('name')
        return Response(DentalLaboratorySerializer(labs, many=True).data)

    def post(self, request):
        serializer = DentalLaboratorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DentalLaboratoryDetailView(APIView):
    def patch(self, request, pk):
        lab = get_object_or_404(DentalLaboratory, pk=pk)
        serializer = DentalLaboratorySerializer(lab, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        lab = get_object_or_404(DentalLaboratory, pk=pk)
        lab.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class DentalLabWorkListView(APIView):
    def get(self, request):
        work = DentalLabWork.objects.all().order_by('name')
        return Response(DentalLabWorkSerializer(work, many=True).data)

    def post(self, request):
        serializer = DentalLabWorkSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DentalLabWorkDetailView(APIView):
    def patch(self, request, pk):
        work = get_object_or_404(DentalLabWork, pk=pk)
        serializer = DentalLabWorkSerializer(work, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        work = get_object_or_404(DentalLabWork, pk=pk)
        work.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class WebsiteAppointmentRequestListCreateView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        status_filter = request.query_params.get('status', 'Pending')
        if status_filter == 'all':
            requests = WebsiteAppointmentRequest.objects.all().order_by('-created_at')
        else:
            requests = WebsiteAppointmentRequest.objects.filter(status=status_filter).order_by('-created_at')
        serializer = WebsiteAppointmentRequestSerializer(requests, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = WebsiteAppointmentRequestSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class WebsiteAppointmentRequestActionView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        req = get_object_or_404(WebsiteAppointmentRequest, pk=pk)
        action = request.data.get('action')

        if action == 'approve':
            denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
            if denied:
                return denied
            
            with transaction.atomic():
                # Check if patient exists by phone number
                phone = req.phone
                patient = Patient.objects.filter(phone=phone).first()
                if not patient:
                    patient = Patient.objects.create(
                        name=req.name,
                        phone=req.phone,
                        status='Active'
                    )
                
                # Create the real scheduled appointment
                appt = Appointment.objects.create(
                    patient=patient,
                    doctor=req.preferred_doctor,
                    date=req.preferred_date,
                    time=req.preferred_time,
                    status='Scheduled'
                )
                
                # Mark request as Approved
                req.status = 'Approved'
                req.notes = request.data.get('notes', req.notes)
                req.save()

                # Trigger WhatsApp/SMS Notification
                send_appointment_communication(appt, template_type="Confirmation")

            return Response({
                'status': 'Approved',
                'patient_id': str(patient.id),
                'appointment_id': str(appt.id)
            })

        elif action == 'reject':
            denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
            if denied:
                return denied

            req.status = 'Rejected'
            req.notes = request.data.get('notes', '')
            req.save()
            return Response({'status': 'Rejected'})

        elif action == 'reschedule':
            denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
            if denied:
                return denied

            new_date = request.data.get('date')
            new_time = request.data.get('time')
            doctor_id = request.data.get('doctor_id')

            if not new_date:
                return Response({'error': 'date is required'}, status=400)

            req.preferred_date = new_date
            if new_time:
                req.preferred_time = new_time
            if doctor_id:
                req.preferred_doctor = get_object_or_404(Doctor, pk=doctor_id)
            req.notes = request.data.get('notes', req.notes)
            req.save()
            return Response({'status': 'Rescheduled'})

        else:
            return Response({'error': 'Invalid action'}, status=400)

class DoctorScheduleListView(APIView):
    def get(self, request):
        scope = get_request_scope(request)
        doctor_profile = get_user_doctor(request)
        branch_id = request.query_params.get('branch_id')
        doctor_id = request.query_params.get('doctor_id')

        schedules = DoctorSchedule.objects.filter(is_active=True, status='APPROVED')
        if scope.company and not scope.is_super:
            schedules = schedules.filter(company=scope.company)

        if doctor_profile:
            schedules = schedules.filter(doctor=doctor_profile)
        elif doctor_id:
            schedules = schedules.filter(doctor_id=doctor_id)

        if branch_id:
            schedules = schedules.filter(branch_id=branch_id)
        elif not scope.is_company_admin and scope.branch:
            schedules = schedules.filter(branch=scope.branch)

        serializer = DoctorScheduleSerializer(schedules, many=True)
        return Response(serializer.data)

    def post(self, request):
        scope = get_request_scope(request)
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        doctor_profile = get_user_doctor(request)

        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        data = request.data.copy()
        if doctor_profile and not is_admin:
            data['doctor'] = doctor_profile.id

        target_doctor_id = data.get('doctor') or (doctor_profile.id if doctor_profile else None)
        target_doctor = Doctor.objects.filter(id=target_doctor_id).first()
        if not target_doctor:
            return Response({'error': 'Doctor is required.'}, status=400)

        target_branch_id = data.get('branch') or request.headers.get('X-Branch-Id') or (scope.branch.id if scope.branch else None)
        target_branch = Branch.objects.filter(pk=target_branch_id).first() if target_branch_id else (target_doctor.primary_branch or Branch.objects.first())

        if not is_admin:
            # DOCTOR CANNOT DIRECTLY ACTIVATE SCHEDULE. CREATE PROPOSAL INSTEAD:
            slot_entry = {
                'day_of_week': int(data.get('day_of_week', 0)),
                'start_time': str(data.get('start_time', '09:00')),
                'end_time': str(data.get('end_time', '17:00')),
                'session_name': data.get('session_name', 'Requested Session')
            }
            proposal = DoctorScheduleProposal.objects.create(
                doctor=target_doctor,
                company=target_branch.company if target_branch else target_doctor.company,
                branch=target_branch,
                proposal_type='RECURRING_SCHEDULE',
                slot_duration=int(data.get('slot_duration', target_doctor.slot_duration or 30)),
                proposed_slots=[slot_entry],
                status='PENDING_APPROVAL',
                submitted_by=req_user,
                notes=data.get('notes', 'Submitted via schedule management')
            )
            notify_admins(
                title="New Schedule Proposal",
                message=f"Dr. {target_doctor.name} submitted a new schedule proposal for approval at {target_branch.name if target_branch else 'Clinic'}.",
                notification_type='SCHEDULE_PROPOSAL',
                data={'proposal_id': str(proposal.id), 'doctor_id': str(target_doctor.id)}
            )
            log_audit(f"Doctor {target_doctor.name} submitted schedule proposal #{proposal.id} for {target_branch.name if target_branch else 'Clinic'}", user=req_user)
            return Response({
                'status': 'PENDING_APPROVAL',
                'proposal_id': str(proposal.id),
                'message': 'Schedule proposal submitted for administrator approval. Live schedule will update upon approval.'
            }, status=status.HTTP_202_ACCEPTED)

        # ADMIN CREATES ACTIVE APPROVED SCHEDULE DIRECTLY
        data['status'] = 'APPROVED'
        data['is_active'] = True
        if target_branch:
            data['branch'] = str(target_branch.id)
            data['company'] = str(target_branch.company_id) if target_branch.company_id else None

        serializer = DoctorScheduleSerializer(data=data)
        if serializer.is_valid():
            sched = serializer.save(created_by=req_user, approved_by=req_user, status='APPROVED', is_active=True)
            log_audit(f"Admin {req_user.username if req_user else 'Admin'} directly created schedule for Dr. {target_doctor.name} at {target_branch.name if target_branch else 'Clinic'}", user=req_user)
            return Response(DoctorScheduleSerializer(sched).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DoctorScheduleUpdateView(APIView):
    def put(self, request, pk):
        schedule = get_object_or_404(DoctorSchedule, pk=pk)
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        if not is_admin:
            return Response({
                'error': 'Doctors cannot directly modify active schedules. Please submit a schedule proposal for administrator approval.'
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = DoctorScheduleSerializer(schedule, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_audit(f"Admin {req_user.username if req_user else 'Admin'} updated schedule #{pk}", user=req_user)
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        schedule = get_object_or_404(DoctorSchedule, pk=pk)
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        if not is_admin:
            return Response({
                'error': 'Doctors cannot directly delete active schedules. Please submit a schedule proposal for administrator approval.'
            }, status=status.HTTP_403_FORBIDDEN)

        doc_name = schedule.doctor.name if schedule.doctor else "Doctor"
        schedule.delete()
        log_audit(f"Admin {req_user.username if req_user else 'Admin'} deleted schedule #{pk} for Dr. {doc_name}", user=req_user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffPermissionsUpdateView(APIView):
    def patch(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk)
        req_user = get_authenticated_user(request)
        allowed, err_msg, err_status = can_modify_staff(req_user, staff)
        if not allowed:
            return Response({'detail': err_msg, 'error': err_msg}, status=err_status)
        perms = request.data.get('permissions')
        if perms is not None:
            staff.permissions = perms
            staff.save()
            return Response(StaffSerializer(staff).data)
        return Response({'error': 'No permissions provided'}, status=400)

class GlobalLabOrderListView(APIView):
    def get(self, request):
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        date_param = request.query_params.get('date')

        orders = PatientLabOrder.objects.all()

        if date_param:
            orders = orders.filter(date=date_param)
        if month and year:
            orders = orders.filter(date__year=year, date__month=month)

        orders = orders.order_by('-date', '-created_at')
        
        # Serialize the orders, but we also want patient name. Let's serialize the basic data.
        data = []
        for order in orders:
            data.append({
                'id': str(order.id),
                'date': order.date,
                'test_name': order.test_name,
                'patient_name': order.patient.name,
                'patient_id': str(order.patient.id),
                'status': order.status if hasattr(order, 'status') else 'Ordered',
                'notes': order.notes
            })
            
        return Response(data)

# --- PATIENT LAB ORDERS ---
class PatientLabOrderListView(APIView):
    def get(self, request, patient_id):
        orders = PatientLabOrder.objects.filter(patient_id=patient_id).order_by('-date', '-created_at')
        return Response(PatientLabOrderSerializer(orders, many=True).data)

    def post(self, request, patient_id):
        patient = get_object_or_404(Patient, pk=patient_id)
        data = request.data.copy()
        data['patient'] = patient.id
        serializer = PatientLabOrderSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PatientLabOrderDeleteView(APIView):
    def delete(self, request, pk):
        order = get_object_or_404(PatientLabOrder, pk=pk)
        order.delete()
        return Response({"status": "deleted"}, status=status.HTTP_204_NO_CONTENT)

class RecentPatientsView(APIView):
    def get(self, request):
        patients = Patient.objects.order_by('-created_at')[:3]
        serializer = PatientSerializer(patients, many=True)
        return Response(serializer.data)


# =====================================================================
# DOCTOR SLOT SCHEDULING, PROPOSALS, AVAILABILITY & ADMIN APPROVAL
# =====================================================================

class DoctorAvailableSlotsView(APIView):
    """
    Computes valid, bookable candidate slots for a doctor on a specific date and branch.
    Factors in:
    - Active, approved branch schedules (DoctorSchedule with status='APPROVED', is_active=True, branch=target_branch)
    - Slot duration (doctor or schedule slot_duration, default 30 mins)
    - Date-specific overrides & approved leaves (DoctorDateOverride)
    - Cross-branch booking conflicts: checks existing appointments across ALL branches on target_date
    - Partial-day blocked time periods
    """
    def get(self, request, doctor_id):
        doctor = get_object_or_404(Doctor, pk=doctor_id)
        scope = get_request_scope(request)
        date_str = request.query_params.get('date')
        if not date_str:
            target_date = timezone.localtime(timezone.now()).date()
        else:
            try:
                target_date = datetime.strptime(str(date_str).strip(), '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': 'Invalid date format (YYYY-MM-DD required)'}, status=400)

        # Resolve branch context
        branch_id = request.query_params.get('branch_id') or request.headers.get('X-Branch-Id')
        target_branch = None
        if branch_id:
            target_branch = Branch.objects.filter(pk=branch_id).first()
        if not target_branch:
            target_branch = doctor.primary_branch or (Branch.objects.filter(pk=doctor.assigned_branches[0]).first() if doctor.assigned_branches else None) or (scope.branch if scope.branch else Branch.objects.first())

        # Verify doctor is authorized for target branch
        if target_branch:
            if not doctor.is_branch_assigned(target_branch) and doctor.primary_branch:
                return Response({
                    'error': f'Dr. {doctor.name} is not assigned to {target_branch.name}.',
                    'doctor_id': str(doctor.id),
                    'branch_id': str(target_branch.id) if target_branch else None,
                    'branch_name': target_branch.name if target_branch else None,
                    'slots': []
                }, status=400)

        day_of_week = target_date.weekday() # 0 = Monday, ..., 6 = Sunday
        duration = doctor.slot_duration or 30

        # 1. Inspect date-specific overrides / leaves (approved & active)
        overrides = DoctorDateOverride.objects.filter(
            doctor=doctor,
            date=target_date,
            is_active=True,
            status='APPROVED'
        )

        full_day_leave = False
        leave_reason = None
        blocked_windows = []
        custom_sessions = []

        for ov in overrides:
            if ov.override_type in ['LEAVE', 'UNAVAILABLE'] and not ov.start_time:
                full_day_leave = True
                leave_reason = ov.reason or ov.leave_type or 'Doctor on leave / unavailable'
                break
            elif ov.override_type in ['LEAVE', 'UNAVAILABLE', 'BLOCKED'] and ov.start_time and ov.end_time:
                blocked_windows.append((ov.start_time, ov.end_time))
            elif ov.override_type == 'AVAILABLE' and ov.start_time and ov.end_time:
                custom_sessions.append({
                    'start_time': ov.start_time,
                    'end_time': ov.end_time,
                    'session_name': ov.reason or 'Special Hours',
                    'slot_duration': ov.slot_duration or duration
                })

        if full_day_leave:
            return Response({
                'doctor_id': str(doctor.id),
                'doctor_name': doctor.name,
                'branch_id': str(target_branch.id) if target_branch else None,
                'branch_name': target_branch.name if target_branch else None,
                'date': str(target_date),
                'day_name': target_date.strftime('%A'),
                'slot_duration': duration,
                'is_on_leave': True,
                'leave_reason': leave_reason,
                'slots': []
            })

        sessions = []
        if custom_sessions:
            sessions = custom_sessions
        else:
            sched_filter = {
                'doctor': doctor,
                'day_of_week': day_of_week,
                'is_active': True,
                'status': 'APPROVED'
            }
            if target_branch:
                sched_filter['branch'] = target_branch
            schedules = DoctorSchedule.objects.filter(**sched_filter).order_by('start_time')
            for s in schedules:
                sessions.append({
                    'start_time': s.start_time,
                    'end_time': s.end_time,
                    'session_name': s.session_name or 'Regular Session',
                    'slot_duration': s.slot_duration or duration
                })

        # 2. Fetch existing active booked appointments for this doctor on target_date ACROSS ALL BRANCHES
        booked_appts = Appointment.objects.filter(
            doctor=doctor,
            date=target_date
        ).exclude(status__in=['Cancelled', 'Rescheduled'])

        booked_map = {}
        for b in booked_appts:
            if b.time:
                is_other = bool(target_branch and b.branch_id and str(b.branch_id) != str(target_branch.id))
                booked_map[b.time.strftime('%H:%M')] = {
                    'appointment_id': str(b.id),
                    'status': b.status,
                    'branch_id': str(b.branch_id) if b.branch_id else None,
                    'branch_name': b.branch.name if b.branch else '',
                    'is_other_branch': is_other,
                    'patient_name': b.patient.name if b.patient else 'Booked'
                }

        candidate_slots = []
        for sess in sessions:
            sess_dur = sess.get('slot_duration') or duration
            cur_dt = datetime.combine(target_date, sess['start_time'])
            end_dt = datetime.combine(target_date, sess['end_time'])

            while cur_dt + timedelta(minutes=sess_dur) <= end_dt:
                slot_start_t = cur_dt.time()
                slot_end_t = (cur_dt + timedelta(minutes=sess_dur)).time()
                slot_key = slot_start_t.strftime('%H:%M')

                # Check if slot overlaps with partial-day blocked windows
                is_blocked = False
                for b_start, b_end in blocked_windows:
                    if not (slot_end_t <= b_start or slot_start_t >= b_end):
                        is_blocked = True
                        break

                if is_blocked:
                    candidate_slots.append({
                        'time': slot_key,
                        'end_time': slot_end_t.strftime('%H:%M'),
                        'is_available': False,
                        'is_blocked': True,
                        'session_name': sess.get('session_name', 'Session'),
                        'status': 'Blocked'
                    })
                elif slot_key in booked_map:
                    slot_info = booked_map[slot_key]
                    display_status = f"Booked at {slot_info['branch_name']}" if slot_info.get('is_other_branch') and slot_info.get('branch_name') else slot_info['status']
                    candidate_slots.append({
                        'time': slot_key,
                        'end_time': slot_end_t.strftime('%H:%M'),
                        'is_available': False,
                        'is_blocked': False,
                        'session_name': sess.get('session_name', 'Session'),
                        'status': display_status,
                        'appointment_id': slot_info['appointment_id'],
                        'is_other_branch': slot_info.get('is_other_branch', False)
                    })
                else:
                    candidate_slots.append({
                        'time': slot_key,
                        'end_time': slot_end_t.strftime('%H:%M'),
                        'is_available': True,
                        'is_blocked': False,
                        'session_name': sess.get('session_name', 'Session'),
                        'status': 'Available'
                    })

                cur_dt += timedelta(minutes=sess_dur)

        return Response({
            'doctor_id': str(doctor.id),
            'doctor_name': doctor.name,
            'branch_id': str(target_branch.id) if target_branch else None,
            'branch_name': target_branch.name if target_branch else None,
            'date': str(target_date),
            'day_name': target_date.strftime('%A'),
            'slot_duration': duration,
            'is_on_leave': False,
            'leave_reason': None,
            'slots': candidate_slots
        })


class DoctorScheduleProposalListView(APIView):
    """
    List and create schedule proposals.
    - Doctor: views own proposals, creates pending proposals for approval.
    - Admin: views all proposals with filters (doctor_id, status).
    """
    def get(self, request):
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        doctor_profile = get_user_doctor(request)

        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        scope = get_request_scope(request)
        if not is_admin and doctor_profile:
            proposals = DoctorScheduleProposal.objects.filter(doctor=doctor_profile)
        elif not is_admin and req_user:
            proposals = DoctorScheduleProposal.objects.filter(submitted_by=req_user)
        else:
            proposals = DoctorScheduleProposal.objects.all()
            if scope.company and not scope.is_super:
                proposals = proposals.filter(company=scope.company)
            doctor_id = request.query_params.get('doctor_id')
            branch_id = request.query_params.get('branch_id')
            status_param = request.query_params.get('status')
            if doctor_id:
                proposals = proposals.filter(doctor_id=doctor_id)
            if branch_id:
                proposals = proposals.filter(branch_id=branch_id)
            if status_param:
                proposals = proposals.filter(status=status_param)

        serializer = DoctorScheduleProposalSerializer(proposals, many=True)
        return Response(serializer.data)

    def post(self, request):
        scope = get_request_scope(request)
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        doctor_profile = get_user_doctor(request)

        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        data = request.data.copy()
        target_doctor_id = data.get('doctor') or (doctor_profile.id if doctor_profile else None)
        target_doctor = Doctor.objects.filter(id=target_doctor_id).first()
        if not target_doctor:
            return Response({'error': 'Doctor is required for schedule proposal.'}, status=400)

        # Enforce that doctors can only propose for their own profile
        if not is_admin and doctor_profile and str(doctor_profile.id) != str(target_doctor.id):
            return Response({'error': 'You can only submit proposals for your own schedule.'}, status=403)

        target_branch_id = data.get('branch') or request.headers.get('X-Branch-Id') or (scope.branch.id if scope.branch else None)
        target_branch = Branch.objects.filter(pk=target_branch_id).first() if target_branch_id else (target_doctor.primary_branch or Branch.objects.first())

        proposed_slots = data.get('proposed_slots', [])
        slot_duration = int(data.get('slot_duration', target_doctor.slot_duration or 30))
        date_exceptions = data.get('date_exceptions', [])
        proposal_type = data.get('proposal_type', 'RECURRING_SCHEDULE')
        notes = data.get('notes', '')

        # Validate proposed slots structure and time logic
        if proposed_slots:
            from collections import defaultdict
            day_sessions = defaultdict(list)
            for idx, s in enumerate(proposed_slots):
                day = s.get('day_of_week')
                start_t = s.get('start_time')
                end_t = s.get('end_time')
                if day is None or not start_t or not end_t:
                    return Response({'error': f'Slot #{idx+1} is missing required fields (day_of_week, start_time, end_time).'}, status=400)
                try:
                    st_val = datetime.strptime(start_t[:5], '%H:%M').time()
                    et_val = datetime.strptime(end_t[:5], '%H:%M').time()
                except ValueError:
                    return Response({'error': f'Slot #{idx+1} has invalid time format.'}, status=400)
                if st_val >= et_val:
                    return Response({'error': f'Slot #{idx+1} start time ({start_t}) must be before end time ({end_t}).'}, status=400)
                day_sessions[day].append((st_val, et_val))

            # Overlap check within each day
            for day, sessions in day_sessions.items():
                sorted_sess = sorted(sessions, key=lambda x: x[0])
                for i in range(len(sorted_sess) - 1):
                    if sorted_sess[i][1] > sorted_sess[i+1][0]:
                        return Response({'error': f'Overlapping sessions detected on day {day}. Each session must be non-overlapping.'}, status=400)

        # Create proposal in PENDING_APPROVAL status with branch & company
        proposal = DoctorScheduleProposal.objects.create(
            doctor=target_doctor,
            company=target_branch.company if target_branch else target_doctor.company,
            branch=target_branch,
            proposal_type=proposal_type,
            slot_duration=slot_duration,
            proposed_slots=proposed_slots,
            date_exceptions=date_exceptions,
            status='PENDING_APPROVAL',
            submitted_by=req_user,
            notes=notes
        )

        # Notify Administrators
        notify_admins(
            title="New Schedule Proposal",
            message=f"Dr. {target_doctor.name} submitted a proposed schedule for approval at {target_branch.name if target_branch else 'Clinic'}.",
            notification_type='SCHEDULE_PROPOSAL',
            data={'proposal_id': str(proposal.id), 'doctor_id': str(target_doctor.id)}
        )

        log_audit(f"Doctor {target_doctor.name} submitted schedule proposal #{proposal.id} for {target_branch.name if target_branch else 'Clinic'}", user=req_user)
        return Response(DoctorScheduleProposalSerializer(proposal).data, status=status.HTTP_201_CREATED)


class DoctorScheduleProposalDetailView(APIView):
    def get(self, request, pk):
        proposal = get_object_or_404(DoctorScheduleProposal, pk=pk)
        # Fetch current active schedule for comparison
        active_schedules = DoctorSchedule.objects.filter(doctor=proposal.doctor, branch=proposal.branch, is_active=True, status='APPROVED')
        active_serializer = DoctorScheduleSerializer(active_schedules, many=True)
        prop_serializer = DoctorScheduleProposalSerializer(proposal)
        return Response({
            'proposal': prop_serializer.data,
            'active_schedule': active_serializer.data
        })


class DoctorScheduleProposalApproveView(APIView):
    """
    Administrator approval endpoint.
    - Strictly blocks self-approval.
    - Safely replaces active schedules with proposed slots for THIS branch upon approval.
    - Leaves active schedules for other branches intact.
    - Creates date overrides if date exceptions are proposed.
    - Notifies the doctor and records audit log.
    """
    def post(self, request, pk):
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        if not is_admin:
            return Response({'error': 'Administrative privileges required to approve schedule proposals.'}, status=status.HTTP_403_FORBIDDEN)

        proposal = get_object_or_404(DoctorScheduleProposal, pk=pk)

        # Prevent Self-Approval
        if req_user and proposal.submitted_by_id and str(req_user.id) == str(proposal.submitted_by_id):
            return Response({'error': 'You cannot approve your own schedule proposal.'}, status=status.HTTP_403_FORBIDDEN)

        if proposal.status != 'PENDING_APPROVAL':
            return Response({'error': f'Proposal is already {proposal.status} and cannot be approved.'}, status=400)

        with transaction.atomic():
            # If proposal contains recurring slots, safely replace active schedule FOR THIS BRANCH
            if proposal.proposed_slots:
                # Deactivate previous active schedule for this branch
                if proposal.branch:
                    DoctorSchedule.objects.filter(doctor=proposal.doctor, branch=proposal.branch).update(is_active=False)
                else:
                    DoctorSchedule.objects.filter(doctor=proposal.doctor).update(is_active=False)

                submitter_user = resolve_user_by_id(proposal.submitted_by_id)

                # Create new active DoctorSchedule records with company and branch
                for slot in proposal.proposed_slots:
                    DoctorSchedule.objects.create(
                        doctor=proposal.doctor,
                        company=proposal.company or (proposal.branch.company if proposal.branch else proposal.doctor.company),
                        branch=proposal.branch,
                        day_of_week=int(slot['day_of_week']),
                        start_time=slot['start_time'],
                        end_time=slot['end_time'],
                        slot_duration=proposal.slot_duration,
                        session_name=slot.get('session_name', 'Regular Session'),
                        status='APPROVED',
                        is_active=True,
                        created_by_id=proposal.submitted_by_id,
                        approved_by_id=req_user.pk if req_user else None
                    )

                # Update Doctor's default slot duration
                proposal.doctor.slot_duration = proposal.slot_duration
                proposal.doctor.save()

            # If proposal contains date exceptions/leaves
            if proposal.date_exceptions:
                for exc in proposal.date_exceptions:
                    DoctorDateOverride.objects.create(
                        doctor=proposal.doctor,
                        date=exc['date'],
                        override_type=exc.get('override_type', 'LEAVE'),
                        start_time=exc.get('start_time'),
                        end_time=exc.get('end_time'),
                        slot_duration=proposal.slot_duration,
                        reason=exc.get('reason', ''),
                        leave_type=exc.get('leave_type', ''),
                        status='APPROVED',
                        proposal=proposal,
                        created_by=submitter_user,
                        approved_by=req_user,
                        is_active=True
                    )

            proposal.status = 'APPROVED'
            proposal.reviewed_by_id = req_user.pk if req_user else None
            proposal.reviewed_at = timezone.now()
            proposal.rejection_reason = None
            proposal.save()

        # In-App Notification to Submitter Doctor
        submitter_user = resolve_user_by_id(proposal.submitted_by_id)
        if submitter_user:
            notify_user(
                user=submitter_user,
                title="Schedule Proposal Approved",
                message=f"Your schedule proposal for Dr. {proposal.doctor.name} has been approved and is now active.",
                notification_type='PROPOSAL_APPROVED',
                data={'proposal_id': str(proposal.id)}
            )

        log_audit(f"Schedule proposal #{proposal.id} for Dr. {proposal.doctor.name} APPROVED by {req_user.username if req_user else 'Admin'}", user=req_user)
        return Response(DoctorScheduleProposalSerializer(proposal).data)


class DoctorScheduleProposalRejectView(APIView):
    """
    Administrator rejection endpoint.
    - Strictly blocks self-review.
    - Requires rejection reason.
    - Leaves active schedule untouched.
    """
    def post(self, request, pk):
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        if not is_admin:
            return Response({'error': 'Administrative privileges required to reject schedule proposals.'}, status=status.HTTP_403_FORBIDDEN)

        proposal = get_object_or_404(DoctorScheduleProposal, pk=pk)

        # Prevent Self-Rejection as reviewer
        if req_user and proposal.submitted_by_id and str(req_user.id) == str(proposal.submitted_by_id):
            return Response({'error': 'You cannot act as reviewer on your own proposal.'}, status=status.HTTP_403_FORBIDDEN)

        if proposal.status != 'PENDING_APPROVAL':
            return Response({'error': f'Proposal is already {proposal.status}.'}, status=400)

        rejection_reason = request.data.get('rejection_reason', '').strip()
        if not rejection_reason:
            return Response({'error': 'A rejection reason is required.'}, status=400)

        proposal.status = 'REJECTED'
        proposal.rejection_reason = rejection_reason
        proposal.reviewed_by = req_user
        proposal.reviewed_at = timezone.now()
        proposal.save()

        # In-App Notification to Doctor
        submitter_user = resolve_user_by_id(proposal.submitted_by_id)
        if submitter_user:
            notify_user(
                user=submitter_user,
                title="Schedule Proposal Rejected",
                message=f"Your schedule proposal was rejected. Reason: {rejection_reason}",
                notification_type='PROPOSAL_REJECTED',
                data={'proposal_id': str(proposal.id), 'reason': rejection_reason}
            )

        log_audit(f"Schedule proposal #{proposal.id} for Dr. {proposal.doctor.name} REJECTED by {req_user.username if req_user else 'Admin'}. Reason: {rejection_reason}", user=req_user)
        return Response(DoctorScheduleProposalSerializer(proposal).data)


class DoctorScheduleProposalWithdrawView(APIView):
    """
    Allows a doctor (or admin) to withdraw a pending schedule proposal before review.
    """
    def post(self, request, pk):
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        doctor_profile = get_user_doctor(request)
        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        proposal = get_object_or_404(DoctorScheduleProposal, pk=pk)

        # Only submitter or admin can withdraw
        is_submitter = (req_user and proposal.submitted_by_id and str(req_user.id) == str(proposal.submitted_by_id))
        is_own_doctor = (doctor_profile and str(doctor_profile.id) == str(proposal.doctor_id))

        if not (is_admin or is_submitter or is_own_doctor):
            return Response({'error': 'You are not authorized to withdraw this proposal.'}, status=status.HTTP_403_FORBIDDEN)

        if proposal.status != 'PENDING_APPROVAL':
            return Response({'error': f'Only pending proposals can be withdrawn (current status: {proposal.status}).'}, status=400)

        proposal.status = 'WITHDRAWN'
        proposal.save()

        log_audit(f"Schedule proposal #{proposal.id} WITHDRAWN by {req_user.username if req_user else 'User'}", user=req_user)
        return Response(DoctorScheduleProposalSerializer(proposal).data)


class DoctorScheduleProposalConflictsView(APIView):
    """
    Pre-approval inspection: Scans upcoming booked appointments for conflicts with proposed schedule.
    """
    def get(self, request, pk):
        proposal = get_object_or_404(DoctorScheduleProposal, pk=pk)
        today = timezone.localtime(timezone.now()).date()

        # Find upcoming appointments
        upcoming = Appointment.objects.filter(
            doctor=proposal.doctor,
            date__gte=today
        ).exclude(status__in=['Cancelled', 'Rescheduled']).order_by('date', 'time')

        # Check which upcoming appointments conflict
        conflicts = []
        proposed_slots_by_day = defaultdict(list)
        for s in proposal.proposed_slots:
            try:
                st = datetime.strptime(s['start_time'][:5], '%H:%M').time()
                et = datetime.strptime(s['end_time'][:5], '%H:%M').time()
                proposed_slots_by_day[int(s['day_of_week'])].append((st, et))
            except Exception:
                pass

        # Check date exceptions (e.g. leave dates)
        leave_dates = set()
        for exc in proposal.date_exceptions:
            if exc.get('override_type') in ['LEAVE', 'UNAVAILABLE']:
                leave_dates.add(str(exc.get('date')))

        for appt in upcoming:
            date_str = str(appt.date)
            day_of_week = appt.date.weekday()

            if date_str in leave_dates:
                conflicts.append({
                    'appointment_id': str(appt.id),
                    'patient_name': appt.patient.name if appt.patient else 'Unknown',
                    'date': date_str,
                    'time': appt.time.strftime('%H:%M') if appt.time else '',
                    'conflict_type': 'LEAVE_CONFLICT',
                    'reason': f'Appointment booked on proposed leave date ({date_str})'
                })
            elif proposal.proposed_slots:
                # Check if doctor practices on that day in proposed schedule
                if day_of_week not in proposed_slots_by_day:
                    conflicts.append({
                        'appointment_id': str(appt.id),
                        'patient_name': appt.patient.name if appt.patient else 'Unknown',
                        'date': date_str,
                        'time': appt.time.strftime('%H:%M') if appt.time else '',
                        'conflict_type': 'DAY_REMOVED',
                        'reason': f'Doctor has no proposed sessions on {appt.date.strftime("%A")}s'
                    })
                elif appt.time:
                    # Check if appointment time falls inside any proposed session
                    inside = any(st <= appt.time < et for st, et in proposed_slots_by_day[day_of_week])
                    if not inside:
                        conflicts.append({
                            'appointment_id': str(appt.id),
                            'patient_name': appt.patient.name if appt.patient else 'Unknown',
                            'date': date_str,
                            'time': appt.time.strftime('%H:%M'),
                            'conflict_type': 'HOURS_MISMATCH',
                            'reason': f'Appointment time ({appt.time.strftime("%H:%M")}) falls outside proposed working hours'
                        })

        return Response({
            'proposal_id': str(proposal.id),
            'doctor_name': proposal.doctor.name,
            'has_conflicts': len(conflicts) > 0,
            'conflict_count': len(conflicts),
            'conflicts': conflicts
        })


class DoctorScheduleDirectManageView(APIView):
    """
    Direct schedule management for Administrators and Super Admins.
    - Applies same strict backend validation as proposals.
    - Activates immediately without second approval.
    - Fully records the actual administrator in created_by and approved_by.
    - Never misrepresents direct change as a doctor proposal.
    - Doctors receive 403 Forbidden.
    """
    def post(self, request):
        req_user = get_authenticated_user(request)
        scope = get_request_scope(request)
        user_role = get_user_role(request)
        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        if not is_admin:
            return Response({'error': 'Administrative privileges required for direct schedule management.'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        doctor_id = data.get('doctor')
        doctor = get_object_or_404(Doctor, pk=doctor_id)

        branch_id = data.get('branch') or request.headers.get('X-Branch-Id') or (scope.branch.id if scope.branch else None)
        target_branch = Branch.objects.filter(pk=branch_id).first() if branch_id else (doctor.primary_branch or Branch.objects.first())

        slots = data.get('slots', [])
        slot_duration = int(data.get('slot_duration', doctor.slot_duration or 30))

        # Validate sessions
        day_sessions = defaultdict(list)
        for idx, s in enumerate(slots):
            day = s.get('day_of_week')
            st_str = s.get('start_time')
            et_str = s.get('end_time')
            if day is None or not st_str or not et_str:
                return Response({'error': f'Slot #{idx+1} is missing required fields.'}, status=400)
            try:
                st = datetime.strptime(st_str[:5], '%H:%M').time()
                et = datetime.strptime(et_str[:5], '%H:%M').time()
            except ValueError:
                return Response({'error': f'Slot #{idx+1} has invalid time format.'}, status=400)
            if st >= et:
                return Response({'error': f'Slot #{idx+1} start time must be before end time.'}, status=400)
            day_sessions[day].append((st, et))

        # Check for overlap within each day
        for day, sess_list in day_sessions.items():
            sorted_s = sorted(sess_list, key=lambda x: x[0])
            for i in range(len(sorted_s) - 1):
                if sorted_s[i][1] > sorted_s[i+1][0]:
                    return Response({'error': f'Overlapping sessions detected on day {day}.'}, status=400)

        with transaction.atomic():
            # Deactivate current active schedule for THIS branch
            if target_branch:
                DoctorSchedule.objects.filter(doctor=doctor, branch=target_branch).update(is_active=False)
            else:
                DoctorSchedule.objects.filter(doctor=doctor).update(is_active=False)

            created_records = []
            for s in slots:
                rec = DoctorSchedule.objects.create(
                    doctor=doctor,
                    company=target_branch.company if target_branch else doctor.company,
                    branch=target_branch,
                    day_of_week=int(s['day_of_week']),
                    start_time=s['start_time'],
                    end_time=s['end_time'],
                    slot_duration=slot_duration,
                    session_name=s.get('session_name', 'Regular Session'),
                    status='APPROVED',
                    is_active=True,
                    created_by_id=req_user.pk if req_user else None,
                    approved_by_id=req_user.pk if req_user else None
                )
                created_records.append(rec)

            doctor.slot_duration = slot_duration
            doctor.save()

        # Notify doctor
        doctor_staff = Staff.objects.filter(doctor_profile=doctor).first()
        doc_user = get_user_for_staff(doctor_staff) if doctor_staff else None
        if doc_user:
            notify_user(
                user=doc_user,
                title="Schedule Updated",
                message=f"Administrator {req_user.username if req_user else 'Admin'} directly updated your active working hours.",
                notification_type='SCHEDULE_UPDATE',
                data={'doctor_id': str(doctor.id)}
            )

        log_audit(f"Administrator {req_user.username if req_user else 'Admin'} directly updated schedule for Dr. {doctor.name}", user=req_user)
        return Response(DoctorScheduleSerializer(created_records, many=True).data, status=status.HTTP_200_OK)


class DoctorDateOverrideListCreateView(APIView):
    """
    Manage date-specific overrides, leaves, and blocked periods.
    """
    def get(self, request):
        doctor_id = request.query_params.get('doctor_id')
        overrides = DoctorDateOverride.objects.filter(is_active=True)
        if doctor_id:
            overrides = overrides.filter(doctor_id=doctor_id)
        serializer = DoctorDateOverrideSerializer(overrides, many=True)
        return Response(serializer.data)

    def post(self, request):
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        doctor_profile = get_user_doctor(request)
        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        data = request.data.copy()
        target_doctor_id = data.get('doctor') or (doctor_profile.id if doctor_profile else None)
        target_doctor = get_object_or_404(Doctor, pk=target_doctor_id)

        # Date validation
        try:
            target_date = datetime.strptime(str(data.get('date')), '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format (YYYY-MM-DD required)'}, status=400)

        override_type = data.get('override_type', 'UNAVAILABLE')
        start_time = data.get('start_time') or None
        end_time = data.get('end_time') or None
        reason = data.get('reason', '')
        leave_type = data.get('leave_type', '')

        # If Admin, directly approved. If Doctor, pending approval.
        initial_status = 'APPROVED' if is_admin else 'PENDING_APPROVAL'

        override = DoctorDateOverride.objects.create(
            doctor=target_doctor,
            date=target_date,
            override_type=override_type,
            start_time=start_time,
            end_time=end_time,
            slot_duration=int(data.get('slot_duration', target_doctor.slot_duration or 30)),
            reason=reason,
            leave_type=leave_type,
            status=initial_status,
            created_by=req_user,
            approved_by=req_user if is_admin else None,
            is_active=True
        )

        if not is_admin:
            notify_admins(
                title="Doctor Leave/Override Request",
                message=f"Dr. {target_doctor.name} submitted a request for {override_type} on {target_date}.",
                notification_type='LEAVE_REQUEST',
                data={'override_id': str(override.id)}
            )

        log_audit(f"Date override ({override_type}) created for Dr. {target_doctor.name} on {target_date} [{initial_status}]", user=req_user)
        return Response(DoctorDateOverrideSerializer(override).data, status=status.HTTP_201_CREATED)


class DoctorDateOverrideActionView(APIView):
    """
    Approve or reject a doctor's date override / leave request.
    """
    def post(self, request, pk):
        req_user = get_authenticated_user(request)
        user_role = get_user_role(request)
        is_admin = is_application_admin(req_user) or is_super_admin(req_user) or (user_role and user_role.lower() == 'admin')

        if not is_admin:
            return Response({'error': 'Administrative privileges required.'}, status=status.HTTP_403_FORBIDDEN)

        override = get_object_or_404(DoctorDateOverride, pk=pk)

        # Prevent Self-Approval
        if req_user and override.created_by_id and str(req_user.id) == str(override.created_by_id):
            return Response({'error': 'You cannot approve your own leave/override request.'}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get('action') # 'approve' or 'reject'
        if action == 'approve':
            override.status = 'APPROVED'
            override.approved_by = req_user
            override.save()

            creator = resolve_user_by_id(override.created_by_id)
            if creator:
                notify_user(
                    user=creator,
                    title="Leave/Override Approved",
                    message=f"Your {override.override_type} request for {override.date} has been approved.",
                    notification_type='LEAVE_APPROVED',
                    data={'override_id': str(override.id)}
                )
            log_audit(f"Date override #{override.id} for Dr. {override.doctor.name} APPROVED by {req_user.username if req_user else 'Admin'}", user=req_user)
            return Response(DoctorDateOverrideSerializer(override).data)

        elif action == 'reject':
            rejection_reason = request.data.get('rejection_reason', '')
            override.status = 'REJECTED'
            override.save()

            creator = resolve_user_by_id(override.created_by_id)
            if creator:
                notify_user(
                    user=creator,
                    title="Leave/Override Rejected",
                    message=f"Your {override.override_type} request for {override.date} was rejected. Reason: {rejection_reason}",
                    notification_type='LEAVE_REJECTED',
                    data={'override_id': str(override.id), 'reason': rejection_reason}
                )
            log_audit(f"Date override #{override.id} for Dr. {override.doctor.name} REJECTED by {req_user.username if req_user else 'Admin'}", user=req_user)
            return Response(DoctorDateOverrideSerializer(override).data)
        else:
            return Response({'error': 'Invalid action. Must be approve or reject.'}, status=400)


# =====================================================================
# IN-APP NOTIFICATIONS
# =====================================================================

class InAppNotificationListView(APIView):
    """
    Get notifications and unread count for current user.
    """
    def get(self, request):
        req_user = get_authenticated_user(request)
        if not req_user:
            return Response({'unread_count': 0, 'notifications': []})

        notifications = InAppNotification.objects.filter(recipient=req_user)[:50]
        unread_count = InAppNotification.objects.filter(recipient=req_user, is_read=False).count()
        serializer = InAppNotificationSerializer(notifications, many=True)
        return Response({
            'unread_count': unread_count,
            'notifications': serializer.data
        })


class InAppNotificationReadView(APIView):
    """
    Mark single notification as read.
    """
    def post(self, request, pk):
        req_user = get_authenticated_user(request)
        if not req_user:
            return Response({'error': 'Authentication required'}, status=401)
        notif = get_object_or_404(InAppNotification, pk=pk, recipient=req_user)
        notif.is_read = True
        notif.save()
        return Response({'status': 'read'})


class InAppNotificationMarkAllReadView(APIView):
    """
    Mark all notifications for current user as read.
    """
    def post(self, request):
        req_user = get_authenticated_user(request)
        if not req_user:
            return Response({'error': 'Authentication required'}, status=401)
        InAppNotification.objects.filter(recipient=req_user, is_read=False).update(is_read=True)
        return Response({'status': 'all_read'})


# =====================================================================
# MULTI-COMPANY & MULTI-BRANCH MANAGEMENT
# =====================================================================

class CompanyListView(APIView):
    """
    List and create Companies.
    - Superadmin: can view all companies, create new companies.
    - Company Admin / Staff: can view only their own company.
    """
    def get(self, request):
        scope = get_request_scope(request)
        if not scope.is_authenticated:
            companies = Company.objects.filter(is_active=True)
            return Response(CompanySerializer(companies, many=True).data)

        if scope.is_super:
            companies = Company.objects.all().order_by('name')
        elif scope.company:
            companies = Company.objects.filter(id=scope.company.id)
        else:
            companies = Company.objects.filter(is_active=True)

        return Response(CompanySerializer(companies, many=True).data)

    def post(self, request):
        scope = get_request_scope(request)
        if not scope.is_super:
            return Response({'error': 'Platform administrator (Superadmin) required to create new companies.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = CompanySerializer(data=request.data)
        if serializer.is_valid():
            company = serializer.save()
            # Also create default 'Main Branch' for new company
            Branch.objects.create(
                company=company,
                name="Main Branch",
                code=f"{company.code or 'CMP'}-BR1",
                is_main=True,
                is_active=True
            )
            return Response(CompanySerializer(company).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CompanyDetailView(APIView):
    def get(self, request, pk):
        scope = get_request_scope(request)
        company = get_object_or_404(Company, pk=pk)
        if not scope.is_super and (not scope.company or str(scope.company.id) != str(company.id)):
            return Response({'error': 'Unauthorized to view this company.'}, status=status.HTTP_403_FORBIDDEN)
        return Response(CompanySerializer(company).data)

    def put(self, request, pk):
        scope = get_request_scope(request)
        company = get_object_or_404(Company, pk=pk)
        if not (scope.is_super or (scope.is_company_admin and str(scope.company.id) == str(company.id))):
            return Response({'error': 'Unauthorized to edit this company.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = CompanySerializer(company, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BranchListView(APIView):
    """
    List and create branches.
    - Superadmin: can view all branches across companies, or filter by ?company_id=...
    - Company Admin: can view all branches for their company.
    - Ordinary Staff / Doctor: can view branches they are assigned/accessible to.
    """
    def get(self, request):
        scope = get_request_scope(request)
        company_id = request.query_params.get('company_id')

        if scope.is_super:
            branches = Branch.objects.filter(is_active=True)
            if company_id:
                branches = branches.filter(company_id=company_id)
        elif scope.is_company_admin and scope.company:
            branches = Branch.objects.filter(company=scope.company, is_active=True)
        elif scope.company:
            if scope.accessible_branches:
                branches = Branch.objects.filter(company=scope.company, id__in=scope.accessible_branches, is_active=True)
            elif scope.branch:
                branches = Branch.objects.filter(id=scope.branch.id, is_active=True)
            else:
                branches = Branch.objects.filter(company=scope.company, is_active=True)
        else:
            branches = Branch.objects.filter(is_active=True)

        return Response(BranchSerializer(branches.order_by('name'), many=True).data)

    def post(self, request):
        scope = get_request_scope(request)
        if not (scope.is_super or scope.is_company_admin):
            return Response({'error': 'Administrator privileges required to create branches.'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()
        if not scope.is_super and scope.company:
            data['company'] = str(scope.company.id)

        serializer = BranchSerializer(data=data)
        if serializer.is_valid():
            branch = serializer.save()
            return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BranchDetailView(APIView):
    def get(self, request, pk):
        scope = get_request_scope(request)
        branch = get_object_or_404(Branch, pk=pk)
        if not scope.is_super and scope.company and str(branch.company_id) != str(scope.company.id):
            return Response({'error': 'Unauthorized to view this branch.'}, status=status.HTTP_403_FORBIDDEN)
        return Response(BranchSerializer(branch).data)

    def put(self, request, pk):
        scope = get_request_scope(request)
        branch = get_object_or_404(Branch, pk=pk)
        if not (scope.is_super or (scope.is_company_admin and str(branch.company_id) == str(scope.company.id))):
            return Response({'error': 'Unauthorized to edit this branch.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = BranchSerializer(branch, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


