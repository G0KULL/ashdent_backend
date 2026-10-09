from rest_framework.views import APIView
from django.db import transaction
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
from .models import Staff, Doctor, DoctorSchedule, Patient, Appointment, TreatmentMaster, Visit, TreatmentRecord, Payment, Prescription, PrescriptionItem, Tooth, ClinicalNotes, ToothMaster, PreBooking, MedicineMaster, Billing, BillingItem, PatientGroup, CommunicationLog, Transaction, Supplier, MedicinePurchase, PharmacyPurchase, PharmacyPurchaseItem, MedicineStock, SupplierLedger, TaxSetting, CommunicationTemplate, LabHeader, Laboratory, LabTestMaster, LabTestParameter, LabPackage, DentalLaboratory, DentalLabWork, Expense, ExpenseCategory, PatientLabOrder, Company, AuditLog
from .serializers import (
    PatientSerializer, AppointmentSerializer, TreatmentMasterSerializer,
    VisitSerializer, TreatmentRecordSerializer, PaymentSerializer, PrescriptionSerializer,
    DoctorSerializer, DoctorScheduleSerializer, ToothSerializer, ClinicalNotesSerializer, ToothMasterSerializer, MedicineMasterSerializer, BillingSerializer, BillingItemSerializer, PatientGroupSerializer, TransactionSerializer, SupplierSerializer, PharmacyPurchaseSerializer, MedicineStockSerializer, SupplierLedgerSerializer, TaxSettingSerializer, CommunicationTemplateSerializer, LabHeaderSerializer, LaboratorySerializer, LabTestMasterSerializer, LabTestParameterSerializer, LabPackageSerializer,
    DentalLaboratorySerializer, DentalLabWorkSerializer, StaffSerializer, PatientLabOrderSerializer, CompanySerializer, AuditLogSerializer
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

from .models import WebsiteAppointmentRequest
from .serializers import WebsiteAppointmentRequestSerializer
from datetime import date, datetime, time
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

        # Match by BOTH phone AND name — same phone with a different name = different patient
        existing_patient = None
        if phone and name:
            existing_patient = Patient.objects.filter(phone=phone, name=name).first()

        if existing_patient:
            # Same person returning — just update mutable fields
            patient = existing_patient
            new_age = request.data.get('age')
            if new_age:
                patient.age = new_age
            new_gender = request.data.get('gender')
            if new_gender:
                patient.gender = new_gender
            new_fee = request.data.get('consultation_fee', 0)
            if new_fee:
                patient.consultation_fee = new_fee
            patient.save()
        else:
            # Different name or new phone — always create a brand-new patient record
            patient_data = {
                'name': name,
                'phone': phone,
                'age': request.data.get('age'),
                'gender': request.data.get('gender'),
                'consultation_fee': request.data.get('consultation_fee', 0),
            }
            patient_serializer = PatientSerializer(data=patient_data)
            if not patient_serializer.is_valid():
                return Response(patient_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            patient = patient_serializer.save()


        # Assign doctor: use explicitly provided doctor_id, or fall back to the
        # logged-in user's own doctor profile so that doctor-created patients
        # always appear in their own patient list.
        doctor_id = request.data.get('doctor')
        doctor = None
        if doctor_id:
            try:
                doctor = Doctor.objects.filter(id=doctor_id).first()
            except Exception:
                pass

        # Auto-assign the logged-in doctor if none was explicitly provided
        if not doctor:
            logged_in_doctor = get_user_doctor(request)
            if logged_in_doctor:
                doctor = logged_in_doctor

        if doctor:
            patient.doctor = doctor
            patient.save()

        treatments = request.data.get('treatments', [])
        paid_amount = request.data.get('paid_amount', 0)
        payment_method = request.data.get('payment_method', 'Cash')

        if treatments or Decimal(str(paid_amount)) > 0 or Decimal(str(patient.consultation_fee)) > 0:
            # Use already-resolved doctor; don't fall back to Doctor.objects.first()
            appt_doc = doctor

            # Create Appointment as Waiting so they appear in doctor queue immediately
            appt_time = request.data.get('time') or timezone.now().time()
            appt = Appointment.objects.create(
                patient=patient,
                doctor=appt_doc,
                date=timezone.localtime(timezone.now()).date(),
                time=appt_time,
                status='Waiting'
            )

            # Create Visit
            visit = Visit.objects.create(patient=patient, appointment=appt)

            # Create Payment
            payment, _ = Payment.objects.get_or_create(visit=visit, defaults={'patient': patient})
            payment.payment_method = payment_method

            # Add Consultation Fee to payment
            if Decimal(str(patient.consultation_fee)) > 0:
                payment.total_amount = Decimal(str(payment.total_amount)) + Decimal(str(patient.consultation_fee))

            # Add Treatments
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
                        doctor_id=t_doc_id if t_doc_id else None
                    )
                    payment.total_amount = Decimal(str(payment.total_amount)) + cost_val

            # Record Paid Amount
            if Decimal(str(paid_amount)) > 0:
                payment.paid_amount = Decimal(str(paid_amount))

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
        patient = Patient.objects.filter(phone=phone).first()
        if not patient:
            return Response({'detail': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PatientSerializer(patient)
        return Response(serializer.data)


class PatientSearchView(APIView):
    def get(self, request):
        query = request.query_params.get('q', '')
        date_filter = request.query_params.get('date', '')
        
        patients_qs = Patient.objects.all()
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            # Only show patients directly assigned to this doctor, who have had
            # an appointment with this doctor, or who have a billing from this doctor.
            # NOTE: We intentionally exclude appointments__doctor__isnull=True so that
            # unassigned/walk-in appointments are NOT leaked to every doctor's list.
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
            data.append({
                'id': str(p.id),
                'name': p.name,
                'phone': p.phone or '',
                'age': p.age,
                'gender': p.gender or '—',
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
        patient = get_object_or_404(Patient, pk=pk)
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


# --- APPOINTMENT ---
class AppointmentCreateView(APIView):
    def post(self, request):
        serializer = AppointmentSerializer(data=request.data)
        if serializer.is_valid():
            appt = serializer.save()
            
            paid_amount = request.data.get('paid_amount', 0)
            payment_method = request.data.get('payment_method', 'Cash')
            
            # If a payment is recorded or it's a walk-in (Waiting), start a visit record
            if Decimal(str(paid_amount)) > 0 or appt.status == 'Waiting':
                visit = Visit.objects.create(patient=appt.patient, appointment=appt)
                payment, _ = Payment.objects.get_or_create(visit=visit, defaults={'patient': appt.patient})
                payment.paid_amount = Decimal(str(paid_amount))
                payment.payment_method = payment_method
                payment.save()
                
            # Trigger WhatsApp/SMS Notification
            send_appointment_communication(appt, template_type="Confirmation")
                
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AppointmentByPatientView(APIView):
    def get(self, request, patient_id):
        appts = Appointment.objects.filter(patient_id=patient_id).order_by('-date', '-time')
        serializer = AppointmentSerializer(appts, many=True)
        return Response(serializer.data)


class TodayAppointmentListView(APIView):
    """Today's appointments — used by TodayPatients page and AppointmentStatus widget."""
    def get(self, request):
        today = timezone.localtime(timezone.now()).date()
        appts = Appointment.objects.filter(date=today).exclude(status__in=['Rescheduled', 'Cancelled']).order_by('time')
        
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            # Strict: only show this doctor's own appointments, not unassigned ones
            appts = appts.filter(doctor=doctor_profile)
            
        serializer = AppointmentSerializer(appts, many=True)
        return Response(serializer.data)


class AllAppointmentListView(APIView):
    """All appointments with optional filters for the Appointments page."""
    def get(self, request):
        today = timezone.localtime(timezone.now()).date()
        status_filter = request.query_params.get('status', '')
        date_filter = request.query_params.get('date', '')
        q = request.query_params.get('q', '')

        appts = Appointment.objects.all().order_by('time', 'date')
        
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
        appt.status = request.data.get('status', appt.status)
        # Save the rescheduled target date/time if provided
        if 'rescheduled_to_date' in request.data:
            appt.rescheduled_to_date = request.data['rescheduled_to_date'] or None
        if 'rescheduled_to_time' in request.data:
            appt.rescheduled_to_time = request.data['rescheduled_to_time'] or None
        if 'doctor' in request.data:
            doc_id = request.data['doctor']
            if doc_id:
                appt.doctor = Doctor.objects.filter(id=doc_id).first()
            else:
                appt.doctor = None
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
       Creates Visit + Payment in one shot."""
    def post(self, request):
        patient_id     = request.data.get('patient_id')
        total_amount   = request.data.get('total_amount', 0)
        paid_amount    = request.data.get('paid_amount', 0)
        payment_method = request.data.get('payment_method', 'Cash')
        doctor_id      = request.data.get('doctor_id')

        if not patient_id:
            return Response({'error': 'patient_id is required'}, status=400)

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
        payment = Payment.objects.create(
            patient=patient,
            visit=visit,
            total_amount=Decimal(str(total_amount)),
            paid_amount=Decimal(str(paid_amount)),
            payment_method=payment_method,
        )
        return Response(PaymentSerializer(payment).data, status=201)


# --- VISIT ---
class VisitGetOrCreateView(APIView):
    def post(self, request):
        appointment_id = request.data.get('appointment_id')
        patient_id = request.data.get('patient_id')

        if appointment_id:
            appointment = get_object_or_404(Appointment, id=appointment_id)
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
            
            result.append({
                "id": rec.id,
                "visit_id": rec.visit.id,
                "date": rec.visit.created_at.date() if rec.visit else None,
                "tooth_number": rec.tooth_number,
                "diagnosis": diagnosis,
                "treatment": rec.treatment.name if rec.treatment else "",
                "doctor": rec.doctor.name if rec.doctor else "Unknown",
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
        
        if not appointment_id and not patient_id:
            return Response({"error": "appointment_id or patient_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        if appointment_id:
            appointment = get_object_or_404(Appointment, id=appointment_id)
        else:
            patient = get_object_or_404(Patient, id=patient_id)
            appointment = Appointment.objects.filter(
                patient=patient,
                date=timezone.now().date()
            ).first()
            if not appointment:
                doctor = Doctor.objects.first()
                appointment = Appointment.objects.create(
                    patient=patient,
                    doctor=doctor,
                    date=timezone.now().date(),
                    time=timezone.now().time(),
                    status='Completed'
                )

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
    def post(self, request, pk):
        record_type = request.data.get('type')
        
        if record_type == 'Billing':
            bill = get_object_or_404(Billing, pk=pk)
            amount_to_add = Decimal(str(request.data.get('amount', 0)))
            payment_method = request.data.get('payment_method', bill.payment_method)
            if amount_to_add > 0:
                bill.paid_amount += amount_to_add
                bill.payment_method = payment_method
                bill.save()
            return Response(BillingSerializer(bill).data)

        elif record_type == 'Payment':
            payment = get_object_or_404(Payment, pk=pk)
            amount_to_add = Decimal(str(request.data.get('amount', 0)))
            if amount_to_add > 0:
                payment.paid_amount += amount_to_add
                payment.payment_method = request.data.get('payment_method', payment.payment_method)
                payment.save()
            return Response(PaymentSerializer(payment).data)

        else:
            # Fallback if type not provided
            bill = Billing.objects.filter(pk=pk).first()
            if bill:
                amount_to_add = Decimal(str(request.data.get('amount', 0)))
                payment_method = request.data.get('payment_method', bill.payment_method)
                if amount_to_add > 0:
                    bill.paid_amount += amount_to_add
                    bill.payment_method = payment_method
                    bill.save()
                return Response(BillingSerializer(bill).data)

            payment = get_object_or_404(Payment, pk=pk)
            amount_to_add = Decimal(str(request.data.get('amount', 0)))
            if amount_to_add > 0:
                payment.paid_amount += amount_to_add
                payment.payment_method = request.data.get('payment_method', payment.payment_method)
                payment.save()
            return Response(PaymentSerializer(payment).data)



# --- DOCTOR ---
class DoctorListView(APIView):
    def get(self, request):
        doctors = Doctor.objects.all()
        active_now = request.query_params.get('active_now')

        if active_now == 'true':
            from django.utils import timezone
            now = timezone.localtime()
            current_day = now.weekday()
            current_time = now.time()

            # Find doctors who have an active schedule right now
            active_doctor_ids = DoctorSchedule.objects.filter(
                day_of_week=current_day,
                start_time__lte=current_time,
                end_time__gte=current_time,
                is_active=True
            ).values_list('doctor_id', flat=True)

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
    def post(self, request):
        data = request.data
        try:
            # Safely parse IDs
            visit_id = data.get('visit')
            patient_id = data.get('patient')
            note_id = data.get('clinical_note')
            
            # Convert to None if empty string or "null" string
            if visit_id == "" or visit_id == "null": visit_id = None
            if patient_id == "" or patient_id == "null": patient_id = None
            if note_id == "" or note_id == "null" or note_id == "new": note_id = None

            notes = data.get('notes', '')
            items_data = data.get('items', [])

            # USER REQUEST: "dont add that old one again" - disabling consolidation to ensure fresh prescription per save
            prescription = Prescription.objects.create(
                visit_id=str(visit_id) if visit_id else None,
                patient_id=str(patient_id) if patient_id else None,
                clinical_note_id=str(note_id) if note_id else None,
                notes=notes
            )
            
            for item in items_data:
                med_name = item.get('medicine_name') or item.get('name')
                if not med_name: continue
                
                qty = int(item.get('quantity') or 1)
                
                # 1. Deduct from Stock
                medicine_master = MedicineMaster.objects.filter(name__iexact=med_name).first()
                u_price = Decimal(str(item.get('unit_price') or (medicine_master.sales_rate if medicine_master else 0)))
                
                if medicine_master:
                    medicine_master.stock_quantity -= qty
                    medicine_master.save()

                # 2. Create Prescription Item
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
    def get(self, request):
        meds = MedicineMaster.objects.all().order_by('name')
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
    def post(self, request):
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
                
                BillingItem.objects.create(billing=billing, treatment=t, qty=1, price=price_to_use)
                TreatmentRecord.objects.create(visit=visit, treatment=t, price=price_to_use)
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
            TreatmentRecord.objects.create(
                visit=visit,
                treatment=t,
                price=item.get('unit_price', t.price),
                notes=request.data.get('notes', 'Added via billing/prescription')
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
    def delete(self, request, pk):
        """Hard-delete a billing record."""
        bill = get_object_or_404(Billing, pk=pk)
        bill.delete()
        return Response({'status': 'deleted'}, status=204)

    def patch(self, request, pk):
        bill = get_object_or_404(Billing, pk=pk)
        data = request.data
        
        from django.db import transaction
        try:
            with transaction.atomic():
                # update basic fields
                if 'status' in data: bill.status = data['status']
                if 'total_amount' in data: bill.total_amount = data['total_amount']
                if 'paid_amount' in data: bill.paid_amount = data['paid_amount']
                if 'balance_amount' in data: bill.balance_amount = data['balance_amount']
                if 'payment_method' in data: bill.payment_method = data['payment_method']
                if 'notes' in data: bill.notes = data['notes']
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
# --- AUTH & MULTI-COMPANY STAFF ONBOARDING ---
def get_caller_info(request):
    user_id = (
        request.headers.get('X-User-Id') or 
        request.headers.get('X-USER-ID') or 
        request.META.get('HTTP_X_USER_ID') or 
        request.META.get('X-User-Id') or 
        (isinstance(request.data, dict) and request.data.get('auth_user_id')) or 
        request.query_params.get('auth_user_id')
    )
    user = None
    staff = None
    if user_id:
        try:
            from bson import ObjectId
            from django.db import connections
            db = connections['default'].database
            u_doc = None
            if isinstance(user_id, str) and len(user_id) == 24:
                try:
                    u_doc = db['auth_user'].find_one({'_id': ObjectId(user_id)})
                except Exception: pass
            if not u_doc:
                u_doc = db['auth_user'].find_one({'_id': user_id})
            if not u_doc and isinstance(user_id, str):
                u_doc = db['auth_user'].find_one({'username': user_id})
            
            if u_doc:
                username_val = u_doc.get('username')
                user_obj_id = u_doc['_id']
                if username_val:
                    user = User.objects.filter(username=username_val).first()
                
                s_doc = db['patients_staff'].find_one({'user_id': user_obj_id})
                if not s_doc:
                    s_doc = db['patients_staff'].find_one({'user_id': str(user_obj_id)})
                if not s_doc and u_doc.get('email'):
                    s_doc = db['patients_staff'].find_one({'email': u_doc.get('email')})

                if s_doc:
                    staff = Staff.objects.filter(pk=str(s_doc['_id'])).first()
                    if not staff:
                        staff = Staff.objects.filter(pk=s_doc['_id']).first()
        except Exception:
            pass

    if not user and getattr(request, 'user', None) and request.user.is_authenticated:
        user = request.user
        if user and not staff:
            staff = Staff.objects.filter(user=user).first()
            if not staff and user.email:
                staff = Staff.objects.filter(email=user.email).first()

    is_super = False
    if user and user.is_superuser:
        is_super = True
    elif staff and staff.is_super_admin:
        is_super = True
    return user, staff, is_super


class CompanyListCreateView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        user, staff, is_super = get_caller_info(request)
        if is_super:
            companies = Company.objects.all().order_by('name')
        elif staff and staff.company:
            companies = Company.objects.filter(pk=staff.company.pk)
        else:
            companies = Company.objects.all().order_by('name')
        return Response(CompanySerializer(companies, many=True).data)

    def post(self, request):
        user, staff, is_super = get_caller_info(request)
        if not is_super:
            return Response({'error': 'Only Super Admin can create companies.'}, status=403)
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip()
        if not name:
            return Response({'error': 'Company name is required.'}, status=400)
        if Company.objects.filter(name__iexact=name).exists():
            return Response({'error': 'Company name already exists.'}, status=400)
        company = Company.objects.create(
            name=name,
            code=code or None,
            address=request.data.get('address', ''),
            email=request.data.get('email', ''),
            phone=request.data.get('phone', ''),
        )
        AuditLog.objects.create(
            user_id=user.pk if (user and hasattr(user, 'pk') and user.pk) else None,
            action='Company Created',
            target_type='Company',
            target_id=str(company.id),
            company=company,
            details={'company_name': company.name}
        )
        return Response(CompanySerializer(company).data, status=201)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        user = authenticate(username=username, password=password)
        if not user:
            try:
                user_obj = User.objects.get(username__iexact=username)
                from django.contrib.auth import authenticate as auth
                user = auth(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass

        if user:
            staff = getattr(user, 'staff_profile', None)
            if not staff:
                staff = Staff.objects.filter(user=user).first()

            if staff and not staff.is_active:
                return Response({'detail': 'Your account is inactive. Please contact your administrator.'}, status=403)
            if not user.is_active:
                return Response({'detail': 'Your account is disabled.'}, status=403)

            role = 'Admin'
            doctor_id = None
            company_id = None
            company_name = ''
            is_super_admin = False
            name = user.get_full_name() or user.username
            employee_id = ''

            if staff:
                role = staff.role
                name = staff.name
                employee_id = staff.employee_id or ''
                is_super_admin = staff.is_super_admin
                if staff.company:
                    company_id = str(staff.company.id)
                    company_name = staff.company.name
                if staff.doctor_profile:
                    doctor_id = str(staff.doctor_profile.id)
            elif user.is_superuser:
                role = 'Admin'
                is_super_admin = True

            return Response({
                'id': str(user.pk),
                'username': user.username,
                'name': name,
                'role': role,
                'doctor_id': doctor_id,
                'company_id': company_id,
                'company_name': company_name,
                'is_super_admin': is_super_admin,
                'employee_id': employee_id,
                'permissions': staff.permissions if staff else [],
                'status': 'success'
            })
        return Response({'detail': 'Invalid username or password'}, status=401)


class StaffOnboardView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        data = request.data
        user, caller_staff, is_super = get_caller_info(request)

        # Authorization Checks
        if not is_super:
            if not caller_staff or caller_staff.role != 'Admin':
                return Response({'error': 'Unauthorized: Only Admins can access staff onboarding.'}, status=403)

        target_company = None
        if is_super:
            company_id = data.get('company_id') or data.get('company')
            if company_id:
                target_company = Company.objects.filter(pk=company_id).first()
            if not target_company:
                target_company = Company.objects.first()
                if not target_company:
                    target_company = Company.objects.create(name="Main Dental Clinic", code="MAIN")
        else:
            # Company Admin MUST be restricted to their own company
            if not caller_staff.company:
                target_company = Company.objects.first()
                if not target_company:
                    target_company = Company.objects.create(name="Main Dental Clinic", code="MAIN")
                caller_staff.company = target_company
                caller_staff.save()
            target_company = caller_staff.company

        # Reject attempts by Company Admin to create Super Admin
        requested_is_super = data.get('is_super_admin', False)
        requested_role = data.get('role', 'Doctor')
        if not is_super:
            if requested_is_super or requested_role == 'Super Admin':
                return Response({'error': 'Company Admin cannot create Super Admin accounts.'}, status=403)

        # Required Fields Validation
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        name = data.get('name') or f"{first_name} {last_name}".strip()
        email = data.get('email', '').strip().lower()
        mobile = data.get('phone') or data.get('mobile_number', '').strip()
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        employee_id = data.get('employee_id', '').strip()
        registration_number = data.get('registration_number', '').strip()

        if not first_name and not name:
            return Response({'error': 'First name is required.'}, status=400)
        if not mobile:
            return Response({'error': 'Mobile number is required.'}, status=400)
        if not email:
            return Response({'error': 'Email address is required.'}, status=400)
        if not username:
            return Response({'error': 'Username is required.'}, status=400)
        if not password:
            return Response({'error': 'Password is required.'}, status=400)
        if confirm_password and password != confirm_password:
            return Response({'error': 'Passwords do not match.'}, status=400)

        # Unique Constraints Check
        if User.objects.filter(username__iexact=username).exists():
            return Response({'error': f"The username '{username}' is already taken. Please choose another."}, status=400)
        if email and (User.objects.filter(email__iexact=email).exists() or Staff.objects.filter(email__iexact=email).exists()):
            return Response({'error': f"The email '{email}' is already registered."}, status=400)
        if employee_id and Staff.objects.filter(company=target_company, employee_id__iexact=employee_id).exists():
            return Response({'error': f"Employee ID '{employee_id}' already exists in this company."}, status=400)
        if registration_number and Staff.objects.filter(registration_number__iexact=registration_number).exists():
            return Response({'error': f"Registration number '{registration_number}' is already registered to another staff member."}, status=400)

        # Default Role Permissions Mapping
        role_permissions_map = {
            'Doctor': ['dashboard', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'follow-ups', 'pre-bookings', 'tele-medicine', 'communication', 'reports', 'prescriptions', 'doctor-slots', 'income'],
            'Dental Assistant': ['dashboard', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'follow-ups', 'pre-bookings', 'material-purchases'],
            'Pharmacist': ['dashboard', 'pharmacy', 'purchases', 'material-purchases', 'stock', 'prescriptions'],
            'Accountant': ['dashboard', 'billing', 'transactions', 'reports', 'material-purchases'],
            'Admin': ['dashboard', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'follow-ups', 'pre-bookings', 'tele-medicine', 'website-appointment', 'communication', 'billing', 'transactions', 'reports', 'pathology-lab', 'dental-lab', 'pharmacy', 'purchases', 'material-purchases', 'stock', 'prescriptions', 'users', 'doctors', 'settings'],
            'Receptionist': ['dashboard', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'follow-ups', 'pre-bookings', 'material-purchases', 'billing']
        }

        permissions = data.get('permissions') or role_permissions_map.get(requested_role, ['dashboard'])

        try:
            with transaction.atomic():
                new_user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=email,
                    first_name=first_name,
                    last_name=last_name
                )

                doctor_profile = None
                if requested_role == 'Doctor':
                    doctor_profile = Doctor.objects.create(
                        company=target_company,
                        name=f"Dr. {name}" if not name.startswith('Dr.') else name,
                        phone=mobile,
                        email=email,
                        specialization=data.get('specialization', 'General Dentistry'),
                        qualification=data.get('qualification', ''),
                        experience_years=int(data.get('years_of_experience') or 0),
                        consultation_fee=float(data.get('consultation_fee') or 500.00),
                        followup_fee=float(data.get('followup_fee') or 0.00),
                        employee_id=employee_id,
                        registration_number=registration_number,
                        medical_council=data.get('medical_council', ''),
                        bio=data.get('bio', '')
                    )

                new_staff = Staff.objects.create(
                    user_id=new_user.pk,
                    company=target_company,
                    is_super_admin=True if (is_super and requested_is_super) else False,
                    doctor_profile=doctor_profile,
                    name=name,
                    first_name=first_name,
                    last_name=last_name,
                    role=requested_role,
                    phone=mobile,
                    email=email,
                    gender=data.get('gender', ''),
                    dob=data.get('dob') or None,
                    profile_photo=data.get('profile_photo', ''),
                    address=data.get('address', ''),
                    city=data.get('city', ''),
                    state=data.get('state', ''),
                    country=data.get('country', 'India'),
                    pincode=data.get('pincode', ''),
                    employee_id=employee_id,
                    qualification=data.get('qualification', ''),
                    specialization=data.get('specialization', ''),
                    registration_number=registration_number,
                    medical_council=data.get('medical_council', ''),
                    years_of_experience=int(data.get('years_of_experience') or 0),
                    joining_date=data.get('joining_date') or None,
                    consultation_fee=float(data.get('consultation_fee') or 0.00),
                    followup_fee=float(data.get('followup_fee') or 0.00),
                    working_days=data.get('working_days', []),
                    working_hours=data.get('working_hours', ''),
                    break_time=data.get('break_time', ''),
                    appointment_duration=int(data.get('appointment_duration') or 30),
                    bio=data.get('bio', ''),
                    department=data.get('department', ''),
                    emergency_contact=data.get('emergency_contact', ''),
                    assigned_doctor_ids=data.get('assigned_doctor_ids', []),
                    base_salary=float(data.get('base_salary') or 0.00),
                    incentive=float(data.get('incentive') or 0.00),
                    permissions=permissions,
                    is_active=data.get('is_active', True)
                )

                AuditLog.objects.create(
                    user_id=user.pk if (user and hasattr(user, 'pk') and user.pk) else None,
                    action='Staff Onboarded',
                    target_type='Staff',
                    target_id=str(new_staff.id),
                    company=target_company,
                    details={
                        'staff_name': new_staff.name,
                        'role': new_staff.role,
                        'employee_id': new_staff.employee_id,
                        'company_name': target_company.name
                    }
                )

                serialized = StaffSerializer(new_staff).data
                return Response({
                    'status': 'success',
                    'message': 'Staff account created successfully.',
                    'staff': serialized
                }, status=201)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


# Keep StaffCreateView as alias to StaffOnboardView for backwards compatibility
StaffCreateView = StaffOnboardView


class StaffListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        user, caller_staff, is_super = get_caller_info(request)
        queryset = Staff.objects.all()

        # Company Isolation:
        # Company Admin sees ONLY their company's staff
        if not is_super:
            if caller_staff and caller_staff.company_id:
                queryset = queryset.filter(company_id=caller_staff.company_id)
            else:
                queryset = queryset.none()
        else:
            comp_param = request.query_params.get('company_id') or request.query_params.get('company')
            if comp_param:
                queryset = queryset.filter(company_id=comp_param)

        role_param = request.query_params.get('role')
        if role_param and role_param != 'All':
            queryset = queryset.filter(role=role_param)

        status_param = request.query_params.get('status')
        if status_param == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_param == 'inactive':
            queryset = queryset.filter(is_active=False)

        search_param = request.query_params.get('search')
        if search_param:
            queryset = queryset.filter(
                Q(name__icontains=search_param) |
                Q(email__icontains=search_param) |
                Q(phone__icontains=search_param) |
                Q(employee_id__icontains=search_param) |
                Q(role__icontains=search_param)
            )

        serializer = StaffSerializer(queryset.order_by('-created_at'), many=True)
        return Response(serializer.data)


class StaffDetailView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, pk):
        user, caller_staff, is_super = get_caller_info(request)
        staff = get_object_or_404(Staff, pk=pk)

        if not is_super and caller_staff and caller_staff.company:
            if staff.company and staff.company != caller_staff.company:
                return Response({'error': 'Access denied: Staff belongs to another company.'}, status=403)

        return Response(StaffSerializer(staff).data)


class StaffUpdateView(APIView):
    authentication_classes = []
    permission_classes = []

    def put(self, request, pk):
        user, caller_staff, is_super = get_caller_info(request)
        staff = get_object_or_404(Staff, pk=pk)
        data = request.data

        # Company Isolation Check
        if not is_super and caller_staff and caller_staff.company:
            if staff.company and staff.company != caller_staff.company:
                return Response({'error': 'Cannot modify staff member of another company.'}, status=403)

        # Company Immutability Check for Company Admin
        if ('company_id' in data or 'company' in data) and not is_super:
            req_comp_id = str(data.get('company_id') or data.get('company'))
            cur_comp_id = str(staff.company.id) if staff.company else ''
            if req_comp_id != cur_comp_id:
                return Response({'error': 'Company Admin cannot move staff to another company.'}, status=403)

        if is_super and ('company_id' in data or 'company' in data):
            comp_id = data.get('company_id') or data.get('company')
            new_comp = Company.objects.filter(pk=comp_id).first()
            if new_comp:
                staff.company = new_comp
                if staff.doctor_profile:
                    staff.doctor_profile.company = new_comp
                    staff.doctor_profile.save()

        # Update User credentials/info
        u = None
        try:
            if staff.user_id:
                u = User.objects.filter(pk=staff.user_id).first()
        except Exception:
            pass
        if not u:
            try:
                u = getattr(staff, 'user', None)
            except Exception:
                u = None

        if u:
            username = data.get('username', '').strip().lower()
            if username and username != u.username:
                if User.objects.filter(username__iexact=username).exclude(pk=u.pk).exists():
                    return Response({'error': f"The username '{username}' is already taken."}, status=400)
                u.username = username
            if data.get('password'):
                u.set_password(data.get('password'))
            if data.get('email'):
                u.email = data.get('email')
            if data.get('first_name'):
                u.first_name = data.get('first_name')
            if data.get('last_name'):
                u.last_name = data.get('last_name')
            u.save()

        # Update Staff attributes
        fields_to_update = [
            'name', 'first_name', 'last_name', 'phone', 'email', 'gender', 'dob',
            'address', 'city', 'state', 'country', 'pincode', 'employee_id',
            'qualification', 'specialization', 'registration_number', 'medical_council',
            'years_of_experience', 'joining_date', 'consultation_fee', 'followup_fee',
            'working_days', 'working_hours', 'break_time', 'appointment_duration',
            'bio', 'department', 'emergency_contact', 'assigned_doctor_ids',
            'base_salary', 'incentive', 'permissions', 'role'
        ]
        for f in fields_to_update:
            if f in data:
                setattr(staff, f, data.get(f))

        staff.save()

        if staff.doctor_profile:
            d = staff.doctor_profile
            d.name = f"Dr. {staff.name}" if not staff.name.startswith('Dr.') else staff.name
            d.phone = staff.phone
            d.email = staff.email
            d.specialization = staff.specialization
            d.qualification = staff.qualification
            d.consultation_fee = staff.consultation_fee
            d.followup_fee = staff.followup_fee
            d.employee_id = staff.employee_id
            d.registration_number = staff.registration_number
            d.save()

        AuditLog.objects.create(
            user_id=user.pk if (user and hasattr(user, 'pk') and user.pk) else None,
            action='Staff Updated',
            target_type='Staff',
            target_id=str(staff.id),
            company=staff.company,
            details={'staff_name': staff.name, 'role': staff.role}
        )

        return Response({'status': 'success', 'staff': StaffSerializer(staff).data})


class StaffToggleStatusView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        user, caller_staff, is_super = get_caller_info(request)
        staff = get_object_or_404(Staff, pk=pk)

        if not is_super and caller_staff and caller_staff.company:
            if staff.company and staff.company != caller_staff.company:
                return Response({'error': 'Cannot change status of staff member in another company.'}, status=403)

        staff.is_active = not staff.is_active
        staff.save()

        u = None
        try:
            if staff.user_id:
                u = User.objects.filter(pk=staff.user_id).first()
        except Exception:
            pass
        if u:
            u.is_active = staff.is_active
            u.save()

        AuditLog.objects.create(
            user_id=user.pk if (user and hasattr(user, 'pk') and user.pk) else None,
            action='Staff Status Changed',
            target_type='Staff',
            target_id=str(staff.id),
            company=staff.company,
            details={'staff_name': staff.name, 'is_active': staff.is_active}
        )

        return Response({
            'id': str(staff.id),
            'is_active': staff.is_active,
            'message': f"Staff account is now {'Active' if staff.is_active else 'Inactive'}."
        })


class AuditLogListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        user, caller_staff, is_super = get_caller_info(request)
        logs = AuditLog.objects.all().order_by('-timestamp')
        if not is_super and caller_staff and caller_staff.company:
            logs = logs.filter(company=caller_staff.company)
        return Response(AuditLogSerializer(logs[:100], many=True).data)

# ─── ROLE HELPER ──────────────────────────────────────────────────────────────
def get_user_role(request):
    """Extract the role of the currently logged-in user from Staff profile."""
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
            med.save()

            return Response({
                'id': med.id,
                'name': med.name,
                'stock_quantity': med.stock_quantity,
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
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            schedules = DoctorSchedule.objects.filter(doctor=doctor_profile)
        else:
            doctor_id = request.query_params.get('doctor_id')
            if doctor_id:
                schedules = DoctorSchedule.objects.filter(doctor_id=doctor_id)
            else:
                schedules = DoctorSchedule.objects.all()
        serializer = DoctorScheduleSerializer(schedules, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        doctor_profile = get_user_doctor(request)
        if doctor_profile:
            data['doctor'] = doctor_profile.id
            
        serializer = DoctorScheduleSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DoctorScheduleUpdateView(APIView):
    def put(self, request, pk):
        schedule = get_object_or_404(DoctorSchedule, pk=pk)
        doctor_profile = get_user_doctor(request)
        if doctor_profile and schedule.doctor != doctor_profile:
            return Response({'error': 'Unauthorized'}, status=403)
        serializer = DoctorScheduleSerializer(schedule, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        schedule = get_object_or_404(DoctorSchedule, pk=pk)
        doctor_profile = get_user_doctor(request)
        if doctor_profile and schedule.doctor != doctor_profile:
            return Response({'error': 'Unauthorized'}, status=403)
        schedule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class StaffListView(APIView):
    def get(self, request):
        staff = Staff.objects.all()
        serializer = StaffSerializer(staff, many=True)
        return Response(serializer.data)

class StaffCreateView(APIView):
    def post(self, request):
        data = request.data
        username = data.get('username')
        password = data.get('password')
        name = data.get('name')
        role = data.get('role', 'Staff')
        phone = data.get('phone', '')
        base_salary = data.get('base_salary', 0)

        if not username or not password:
            return Response({'error': 'Username and password required'}, status=400)
        
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists'}, status=400)
            
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, password=password)
                
                # Default permissions based on role
                default_permissions = []
                if role == 'Pharmacist':
                    default_permissions = ['pharmacy', 'stock', 'purchases']
                elif role == 'Receptionist':
                    default_permissions = ['add-patients', 'appointments', 'today-patients', 'search-patient']
                elif role == 'Doctor':
                    default_permissions = ['add-patients', 'appointments', 'today-patients', 'search-patient', 'tele-medicine']
                    
                staff = Staff.objects.create(
                    user=user, name=name, role=role, phone=phone,
                    permissions=default_permissions,
                    base_salary=base_salary
                )
                
                if role == 'Doctor':
                    doctor = Doctor.objects.create(name=name, phone=phone)
                    staff.doctor_profile = doctor
                    staff.save()
                    
            serializer = StaffSerializer(staff)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

class StaffPermissionsUpdateView(APIView):
    def patch(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk)
        perms = request.data.get('permissions')
        if perms is not None:
            staff.permissions = perms
            staff.save()
            return Response(StaffSerializer(staff).data)
        return Response({'error': 'No permissions provided'}, status=400)

class LoginView(APIView):
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
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
            
            # If admin, give all permissions
            if getattr(user, 'is_superuser', False) or role == 'Admin':
                perms = ['income-analytics', 'expense-manager', 'billing', 'pharmacy', 'stock', 'prescriptions', 'lab', 'users', 'add-patients', 'appointments', 'today-patients', 'search-patient', 'follow-ups', 'pre-bookings', 'communication', 'tele-medicine', 'website-appointment', 'purchases', 'doctors', 'settings', 'pathology-lab', 'dental-lab']
                
            return Response({
                'id': user_id_str,
                'username': user.username,
                'role': role,
                'permissions': perms,
                'doctor_profile_id': doctor_profile_id,
                'name': name
            })
        return Response({'error': 'Invalid credentials'}, status=401)
        

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
