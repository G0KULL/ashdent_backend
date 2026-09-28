from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.utils import timezone
import datetime
from decimal import Decimal
from .models import (
    Billing, Payment, Appointment, Visit, Doctor, 
    Expense, MedicineMaster, BillingItem, TreatmentMaster, Patient, Supplier,
    ExpenseCategory, DoctorSalary, DoctorSalaryRecord, DentalMaterial, DentalMaterialPurchase, AuditLog, PharmacyPurchase, MedicinePurchase,
    TreatmentRecord
)
from calendar import month_abbr
from .views import get_user_doctor

def seed_default_categories():
    default_cats = [
        ('Consumables (Gloves, Glass, Suction)', 'consumables', '#f43f5e', 'ShieldAlert'),
        ('Dental Materials', 'dental_materials', '#ec4899', 'Activity'),
        ('Dental Lab', 'dental_lab', '#8b5cf6', 'FlaskConical'),
        ('Doctors Salary', 'doctor_salary', '#4f46e5', 'UserCheck'),
        ('Salary & Incentives', 'salary_incentives', '#3b82f6', 'Users'),
        ('Marketing, Advertising & Sponsorship', 'marketing', '#06b6d4', 'Megaphone'),
        ('Rent & Electricity Bill', 'rent_electricity', '#f59e0b', 'Home'),
        ('Waste Disposal & Biomedical Waste', 'biomedical_waste', '#ef4444', 'Trash2'),
        ('Maintenance', 'maintenance', '#6b7280', 'Wrench'),
        ('Pharmacy Purchase', 'pharmacy_purchase', '#10b981', 'PlusSquare'),
        ('Equipment Purchase', 'equipment_purchase', '#14b8a6', 'Cpu'),
        ('Equipment Repair', 'equipment_repair', '#f97316', 'Hammer'),
        ('Internet & Software', 'internet_software', '#3b82f6', 'Globe'),
        ('Water Bill', 'water_bill', '#0ea5e9', 'Droplet'),
        ('Taxes', 'taxes', '#ef4444', 'Percent'),
        ('Miscellaneous', 'other', '#6b7280', 'HelpCircle')
    ]
    for name, key, color, icon in default_cats:
        ExpenseCategory.objects.get_or_create(
            key=key,
            defaults={'name': name, 'color': color, 'icon': icon, 'is_predefined': True}
        )

class FinanceDashboardView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        filter_type = request.query_params.get('filter_type', 'monthly') # 'today', 'yesterday', 'custom', 'monthly'
        
        today = timezone.localtime().date()
        
        # Default start and end dates
        start_date = today
        end_date = today
        
        month = int(request.query_params.get('month', today.month))
        year = int(request.query_params.get('year', today.year))
        
        if filter_type == 'today':
            start_date = today
            end_date = today
        elif filter_type == 'yesterday':
            start_date = today - datetime.timedelta(days=1)
            end_date = today - datetime.timedelta(days=1)
        elif filter_type == 'custom':
            start_str = request.query_params.get('start_date')
            end_str = request.query_params.get('end_date')
            from django.utils.dateparse import parse_date
            if start_str:
                start_date = parse_date(start_str) or today
            if end_str:
                end_date = parse_date(end_str) or today
        else: # 'monthly'
            import calendar
            num_days = calendar.monthrange(year, month)[1]
            start_date = datetime.date(year, month, 1)
            end_date = datetime.date(year, month, num_days)

        start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

        doctor_profile = get_user_doctor(request)

        # 1. Daily Income (Today) for the today card split
        today_start = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
        today_end = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))
        
        daily_income = {'total': 0.0, 'cash': 0.0, 'upi': 0.0, 'card': 0.0}
        today_bills = Billing.objects.filter(created_at__range=(today_start, today_end), is_invoice=True)
        if doctor_profile:
            today_bills = today_bills.filter(doctor=doctor_profile)

        for b in today_bills:
            amt = float(b.paid_amount)
            pm = b.payment_method.lower()
            daily_income['total'] += amt
            if 'cash' in pm: daily_income['cash'] += amt
            elif 'upi' in pm: daily_income['upi'] += amt
            elif 'card' in pm: daily_income['card'] += amt

        today_payments = Payment.objects.filter(created_at__range=(today_start, today_end)).exclude(visit__billings__isnull=False)
        if doctor_profile:
            today_payments = today_payments.filter(visit__appointment__doctor=doctor_profile)

        for p in today_payments:
            amt = float(p.paid_amount)
            pm = p.payment_method.lower()
            daily_income['total'] += amt
            if 'cash' in pm: daily_income['cash'] += amt
            elif 'upi' in pm: daily_income['upi'] += amt
            elif 'card' in pm: daily_income['card'] += amt

        # 2. Main Selected Date Range / Monthly Income
        month_bills = Billing.objects.filter(created_at__range=(start_dt, end_dt), is_invoice=True)
        if doctor_profile:
            month_bills = month_bills.filter(doctor=doctor_profile)

        month_payments = Payment.objects.filter(created_at__range=(start_dt, end_dt)).exclude(visit__billings__isnull=False)
        if doctor_profile:
            month_payments = month_payments.filter(visit__appointment__doctor=doctor_profile)

        from collections import defaultdict
        
        # Evaluate to lists
        month_bills_list = list(month_bills)
        month_payments_list = list(month_payments)

        # Collect unique foreign key IDs for bulk queries
        patient_ids = set()
        doctor_ids = set()
        visit_ids = set()
        appointment_ids = set()

        for b in month_bills_list:
            if b.patient_id:
                patient_ids.add(b.patient_id)
            if b.doctor_id:
                doctor_ids.add(b.doctor_id)

        for p in month_payments_list:
            if p.patient_id:
                patient_ids.add(p.patient_id)
            if p.visit_id:
                visit_ids.add(p.visit_id)

        # Bulk fetch related models
        patients_dict = {pt.id: pt for pt in Patient.objects.filter(id__in=list(patient_ids))} if patient_ids else {}
        doctors_dict = {d.id: d for d in Doctor.objects.filter(id__in=list(doctor_ids))} if doctor_ids else {}

        # Fetch Visits, Appointments and their Doctors for legacy payments
        visits_dict = {}
        appointments_dict = {}
        visit_has_treatments = set()
        if visit_ids:
            visits_dict = {v.id: v for v in Visit.objects.filter(id__in=list(visit_ids))}
            for v in visits_dict.values():
                if v.appointment_id:
                    appointment_ids.add(v.appointment_id)
            
            treatment_visits = TreatmentRecord.objects.filter(visit_id__in=list(visit_ids)).values_list('visit_id', flat=True)
            visit_has_treatments = set(treatment_visits)

        if appointment_ids:
            appointments_dict = {a.id: a for a in Appointment.objects.filter(id__in=list(appointment_ids))}
            # Gather any doctor IDs from appointments
            for a in appointments_dict.values():
                if a.doctor_id:
                    doctor_ids.add(a.doctor_id)
            # Re-fetch doctors to ensure appointment doctors are in doctors_dict
            doctors_dict = {d.id: d for d in Doctor.objects.filter(id__in=list(doctor_ids))}

        # Bulk fetch BillingItems and treatments for all month bills
        bill_ids = [b.id for b in month_bills_list]
        billing_items_by_bill = defaultdict(list)
        if bill_ids:
            billing_items = BillingItem.objects.filter(billing_id__in=bill_ids)
            treatment_ids = set(item.treatment_id for item in billing_items if item.treatment_id)
            treatments_dict = {t.id: t for t in TreatmentMaster.objects.filter(id__in=list(treatment_ids))} if treatment_ids else {}
            
            for item in billing_items:
                billing_items_by_bill[item.billing_id].append(item)

        summary_totals = {
            'total': 0.0,
            'consultation': 0.0,
            'treatment': 0.0,
            'pharmacy': 0.0,
            'other': 0.0,
            'cash': 0.0,
            'upi': 0.0,
            'card': 0.0
        }

        # Initialize daily map for trend
        daily_inc_map = {}
        delta = end_date - start_date
        max_days = min(delta.days, 366)
        
        for i in range(max_days + 1):
            day = start_date + datetime.timedelta(days=i)
            date_key = day.strftime('%Y-%m-%d')
            daily_inc_map[date_key] = {
                'total': 0.0, 'cash': 0.0, 'upi': 0.0, 'card': 0.0,
                'consultation': 0.0, 'treatment': 0.0, 'pharmacy': 0.0, 'other': 0.0
            }

        # Process bills
        for b in month_bills_list:
            amt = float(b.paid_amount)
            if amt <= 0:
                continue
            pm = b.payment_method.lower()
            
            b_consultation = 0.0
            b_treatment = 0.0
            b_pharmacy = 0.0
            b_other = 0.0
            
            if b.bill_type == 'Pharmacy':
                b_pharmacy = amt
            else:
                items = billing_items_by_bill.get(b.id, [])
                if not items:
                    if 'consult' in (b.notes or '').lower():
                        b_consultation = amt
                    elif b.patient_id and patients_dict.get(b.patient_id) and patients_dict.get(b.patient_id).name == 'General Clinic Income':
                        b_other = amt
                    else:
                        b_treatment = amt
                else:
                    total_item_val = sum(float(item.price * item.qty) for item in items)
                    ratio = amt / total_item_val if total_item_val > 0 else 1.0
                    for item in items:
                        item_amt = float(item.price * item.qty) * ratio
                        t = treatments_dict.get(item.treatment_id) if treatments_dict else None
                        fee_type = t.fee_type.lower() if (t and t.fee_type) else ''
                        t_name = t.name.lower() if (t and t.name) else ''
                        if 'consult' in fee_type or 'consultation' in t_name:
                            b_consultation += item_amt
                        else:
                            b_treatment += item_amt
            
            summary_totals['total'] += amt
            summary_totals['consultation'] += b_consultation
            summary_totals['treatment'] += b_treatment
            summary_totals['pharmacy'] += b_pharmacy
            summary_totals['other'] += b_other
            
            if 'cash' in pm: summary_totals['cash'] += amt
            elif 'upi' in pm: summary_totals['upi'] += amt
            elif 'card' in pm: summary_totals['card'] += amt
            
            day_str = timezone.localtime(b.created_at).strftime('%Y-%m-%d')
            if day_str in daily_inc_map:
                daily_inc_map[day_str]['total'] += amt
                daily_inc_map[day_str]['consultation'] += b_consultation
                daily_inc_map[day_str]['treatment'] += b_treatment
                daily_inc_map[day_str]['pharmacy'] += b_pharmacy
                daily_inc_map[day_str]['other'] += b_other
                if 'cash' in pm: daily_inc_map[day_str]['cash'] += amt
                elif 'upi' in pm: daily_inc_map[day_str]['upi'] += amt
                elif 'card' in pm: daily_inc_map[day_str]['card'] += amt

        # Process payments
        for p in month_payments_list:
            amt = float(p.paid_amount)
            if amt <= 0:
                continue
            pm = p.payment_method.lower()
            
            p_consultation = 0.0
            p_treatment = 0.0
            
            v = visits_dict.get(p.visit_id)
            appt = appointments_dict.get(v.appointment_id) if v else None
            doc = doctors_dict.get(appt.doctor_id) if appt else None
            doc_fee = float(doc.consultation_fee) if doc else 0.0
            
            pt = patients_dict.get(p.patient_id)
            pt_fee = float(pt.consultation_fee) if pt and pt.consultation_fee else 0.0
            
            if v and v.id not in visit_has_treatments:
                p_consultation = amt
            elif (pt_fee > 0 and abs(amt - pt_fee) < 1.0) or (doc_fee > 0 and abs(amt - doc_fee) < 1.0):
                p_consultation = amt
            else:
                p_treatment = amt
                
            summary_totals['total'] += amt
            summary_totals['consultation'] += p_consultation
            summary_totals['treatment'] += p_treatment
            
            if 'cash' in pm: summary_totals['cash'] += amt
            elif 'upi' in pm: summary_totals['upi'] += amt
            elif 'card' in pm: summary_totals['card'] += amt
            
            day_str = timezone.localtime(p.created_at).strftime('%Y-%m-%d')
            if day_str in daily_inc_map:
                daily_inc_map[day_str]['total'] += amt
                daily_inc_map[day_str]['consultation'] += p_consultation
                daily_inc_map[day_str]['treatment'] += p_treatment
                if 'cash' in pm: daily_inc_map[day_str]['cash'] += amt
                elif 'upi' in pm: daily_inc_map[day_str]['upi'] += amt
                elif 'card' in pm: daily_inc_map[day_str]['card'] += amt

        # Formulate Day-by-Day Income Trend
        day_by_day_income = []
        for d, data in daily_inc_map.items():
            day_by_day_income.append({
                'date': d,
                'total': data['total'],
                'cash': data['cash'],
                'upi': data['upi'],
                'card': data['card'],
                'consultation': data['consultation'],
                'treatment': data['treatment'],
                'pharmacy': data['pharmacy'],
                'other': data['other']
            })
        day_by_day_income.sort(key=lambda x: x['date'])

        # Week-wise breakdown for the selected range
        week_wise = {'Week 1': 0.0, 'Week 2': 0.0, 'Week 3': 0.0, 'Week 4': 0.0, 'Week 5+': 0.0}
        for d_key, val in daily_inc_map.items():
            day_num = int(d_key.split('-')[2])
            if day_num <= 7:
                week_wise['Week 1'] += val['total']
            elif day_num <= 14:
                week_wise['Week 2'] += val['total']
            elif day_num <= 21:
                week_wise['Week 3'] += val['total']
            elif day_num <= 28:
                week_wise['Week 4'] += val['total']
            else:
                week_wise['Week 5+'] += val['total']
        
        week_wise_breakdown = [{'week': k, 'total': v} for k, v in week_wise.items()]

        month_income = {
            'total': summary_totals['total'],
            'cash': summary_totals['cash'],
            'upi': summary_totals['upi'],
            'card': summary_totals['card'],
            'consultation': summary_totals['consultation'],
            'treatment': summary_totals['treatment'],
            'pharmacy': summary_totals['pharmacy'],
            'other': summary_totals['other'],
            'day_by_day': day_by_day_income,
            'week_wise': week_wise_breakdown
        }

        # 3. Detailed Income ledger
        detailed_income = []
        for b in month_bills_list:
            amt = float(b.paid_amount)
            if amt <= 0:
                continue
            
            items = billing_items_by_bill.get(b.id, [])
            if b.bill_type == 'Pharmacy':
                service_type = 'Pharmacy'
            else:
                has_consult = False
                has_treat = False
                for item in items:
                    t = treatments_dict.get(item.treatment_id) if treatments_dict else None
                    fee_type = t.fee_type.lower() if (t and t.fee_type) else ''
                    t_name = t.name.lower() if (t and t.name) else ''
                    if 'consult' in fee_type or 'consultation' in t_name:
                        has_consult = True
                    else:
                        has_treat = True
                
                if has_consult and has_treat:
                    service_type = 'Consultation & Treatment'
                elif has_consult:
                    service_type = 'Consultation'
                else:
                    service_type = 'Treatment'
                    
            items_list = items[:3]
            items_desc = ", ".join([treatments_dict.get(item.treatment_id).name for item in items_list if treatments_dict.get(item.treatment_id)])
            if len(items) > 3:
                items_desc += "..."
            
            p_obj = patients_dict.get(b.patient_id)
            detailed_income.append({
                'id': f"bill_{b.id}",
                'date': timezone.localtime(b.created_at).strftime('%Y-%m-%d'),
                'patient_name': p_obj.name if p_obj else 'Walk-in',
                'service_type': service_type,
                'type': f"Billing ({b.bill_type})",
                'amount': amt,
                'payment_method': b.payment_method or 'Cash',
                'description': items_desc or b.notes or f"{b.bill_type} billing record"
            })
            
        for p in month_payments_list:
            amt = float(p.paid_amount)
            if amt <= 0:
                continue
            
            v = visits_dict.get(p.visit_id)
            appt = appointments_dict.get(v.appointment_id) if v else None
            doc = doctors_dict.get(appt.doctor_id) if appt else None
            doc_name = doc.name if doc else ''
            doc_fee = float(doc.consultation_fee) if doc else 0.0
            
            pt_obj = patients_dict.get(p.patient_id)
            pt_fee = float(pt_obj.consultation_fee) if pt_obj and pt_obj.consultation_fee else 0.0
            
            if v and v.id not in visit_has_treatments:
                service_type = 'Consultation'
            elif (pt_fee > 0 and abs(amt - pt_fee) < 1.0) or (doc_fee > 0 and abs(amt - doc_fee) < 1.0):
                service_type = 'Consultation'
            else:
                service_type = 'Treatment'
                
            desc = "Direct Payment"
            if doc_name:
                desc += f" (Dr. {doc_name})"
                
            pt_obj = patients_dict.get(p.patient_id)
            detailed_income.append({
                'id': f"payment_{p.id}",
                'date': timezone.localtime(p.created_at).strftime('%Y-%m-%d'),
                'patient_name': pt_obj.name if pt_obj else 'Walk-in',
                'service_type': service_type,
                'type': 'Direct Payment',
                'amount': amt,
                'payment_method': p.payment_method or 'Cash',
                'description': desc
            })
        detailed_income.sort(key=lambda x: x['date'], reverse=True)

        # 4. Doctor Revenue — uses billing.doctor FK directly for accuracy
        doctor_revenue_map = {}
        doctors = Doctor.objects.all()
        for doc in doctors:
            doctor_revenue_map[str(doc.id)] = {
                'doctor_id': doc.id,
                'doctor_name': doc.name,
                'consultation_revenue': 0.0,
                'treatment_revenue': 0.0,
                'total_earnings': 0.0,
                'total_patients': set(),   # will convert to count later
                'total_treatments': 0,
            }
        
        doctor_revenue_map['unassigned'] = {
            'doctor_id': None,
            'doctor_name': 'Unassigned / General',
            'consultation_revenue': 0.0,
            'treatment_revenue': 0.0,
            'total_earnings': 0.0,
            'total_patients': set(),
            'total_treatments': 0,
        }

        clinical_bills = [b for b in month_bills_list if b.bill_type == 'Clinical']
        for b in clinical_bills:
            amt = float(b.paid_amount)
            if amt <= 0:
                continue
            
            # Use direct billing.doctor if set, else fall back to visit→appointment→doctor
            doc_id = 'unassigned'
            if b.doctor_id:
                doc_id = str(b.doctor_id)
            else:
                v = visits_dict.get(b.visit_id)
                appt = appointments_dict.get(v.appointment_id) if v else None
                if appt and appt.doctor_id:
                    doc_id = str(appt.doctor_id)
                
            if doc_id not in doctor_revenue_map:
                doc_id = 'unassigned'
            
            # Track unique patients and treatment count
            doctor_revenue_map[doc_id]['total_patients'].add(b.patient_id)
            
            items = billing_items_by_bill.get(b.id, [])
            doctor_revenue_map[doc_id]['total_treatments'] += len(items) if items else 1
            
            if not items:
                if 'consult' in (b.notes or '').lower():
                    doctor_revenue_map[doc_id]['consultation_revenue'] += amt
                else:
                    doctor_revenue_map[doc_id]['treatment_revenue'] += amt
            else:
                total_item_val = sum(float(item.price * item.qty) for item in items)
                ratio = amt / total_item_val if total_item_val > 0 else 1.0
                for item in items:
                    item_amt = float(item.price * item.qty) * ratio
                    t = treatments_dict.get(item.treatment_id) if treatments_dict else None
                    fee_type = t.fee_type.lower() if (t and t.fee_type) else ''
                    t_name = t.name.lower() if (t and t.name) else ''
                    if 'consult' in fee_type or 'consultation' in t_name:
                        doctor_revenue_map[doc_id]['consultation_revenue'] += item_amt
                    else:
                        doctor_revenue_map[doc_id]['treatment_revenue'] += item_amt
                        
        for p in month_payments_list:
            amt = float(p.paid_amount)
            if amt <= 0:
                continue
                
            doc_id = 'unassigned'
            doc_fee = 0.0
            v = visits_dict.get(p.visit_id)
            appt = appointments_dict.get(v.appointment_id) if v else None
            doc = doctors_dict.get(appt.doctor_id) if appt else None
            if doc:
                doc_id = str(doc.id)
                doc_fee = float(doc.consultation_fee)
                
            if doc_id not in doctor_revenue_map:
                doc_id = 'unassigned'
            
            doctor_revenue_map[doc_id]['total_patients'].add(p.patient_id)
            doctor_revenue_map[doc_id]['total_treatments'] += 1
                
            if v and v.id not in visit_has_treatments:
                doctor_revenue_map[doc_id]['consultation_revenue'] += amt
            elif (pt_fee > 0 and abs(amt - pt_fee) < 1.0) or (doc_fee > 0 and abs(amt - doc_fee) < 1.0):
                doctor_revenue_map[doc_id]['consultation_revenue'] += amt
            else:
                doctor_revenue_map[doc_id]['treatment_revenue'] += amt

        doctor_revenue = []
        total_clinic_revenue = summary_totals['total']
        for d_id, dr_data in doctor_revenue_map.items():
            dr_data['total_earnings'] = dr_data['consultation_revenue'] + dr_data['treatment_revenue']
            dr_data['total_patients'] = len(dr_data['total_patients'])  # convert set to count
            if dr_data['total_earnings'] > 0:
                dr_data['contribution_pct'] = round(
                    (dr_data['total_earnings'] / total_clinic_revenue * 100) if total_clinic_revenue > 0 else 0, 1
                )
                doctor_revenue.append(dr_data)
        doctor_revenue.sort(key=lambda x: x['total_earnings'], reverse=True)

        # 5. Pharmacy Sales
        # Calculate pharmacy purchases (expenses) in the selected range
        adv_purchases_total = PharmacyPurchase.objects.filter(
            purchase_date__range=(start_date, end_date)
        ).aggregate(total=Sum('grand_total'))['total'] or 0
        
        simple_purchases_total = MedicinePurchase.objects.filter(
            date__range=(start_dt, end_dt)
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        total_pharmacy_expenses = float(adv_purchases_total) + float(simple_purchases_total)

        pharmacy_sales = {
            'total_sales': 0.0,
            'total_cost': 0.0,  # Legacy COGS
            'total_expenses': total_pharmacy_expenses, # Actual spent
            'total_profit': 0.0,
            'items': [],
            'day_by_day': [],
            'transactions': []
        }
        ph_bills = [b for b in month_bills_list if b.bill_type == 'Pharmacy']
        meds_summary = {}
        daily_pharm = {}
        
        # Initialize daily_pharm for all days in selected range
        for i in range(max_days + 1):
            day = start_date + datetime.timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            daily_pharm[day_str] = {'sales': 0.0, 'expenses': 0.0, 'cost': 0.0}

        # Fetch medicine master for pharmacy items in bulk
        med_names_to_fetch = set()
        billing_items_for_ph_bills = {}
        
        ph_bill_ids = [b.id for b in ph_bills]
        if ph_bill_ids:
            ph_items = BillingItem.objects.filter(billing_id__in=ph_bill_ids)
            # Find treatments and map items
            t_ids = set(item.treatment_id for item in ph_items if item.treatment_id)
            t_dict = {t.id: t for t in TreatmentMaster.objects.filter(id__in=list(t_ids))} if t_ids else {}
            
            for item in ph_items:
                t = t_dict.get(item.treatment_id)
                if t:
                    med_name = t.name.replace('Pharmacy: ', '').strip()
                    med_names_to_fetch.add(med_name.lower())
                
                if item.billing_id not in billing_items_for_ph_bills:
                    billing_items_for_ph_bills[item.billing_id] = []
                billing_items_for_ph_bills[item.billing_id].append((item, t))

        meds_dict = {m.name.lower(): m for m in MedicineMaster.objects.filter(name__in=list(med_names_to_fetch))} if med_names_to_fetch else {}

        for b in ph_bills:
            amt = float(b.paid_amount)
            pharmacy_sales['total_sales'] += amt
            day_str = timezone.localtime(b.created_at).strftime('%Y-%m-%d')
            if day_str not in daily_pharm:
                daily_pharm[day_str] = {'sales': 0.0, 'expenses': 0.0, 'cost': 0.0}
            
            bill_cost = 0.0
            daily_pharm[day_str]['sales'] += amt

            items_and_treats = billing_items_for_ph_bills.get(b.id, [])
            total_item_val = sum(float(item.price * item.qty) for item, _ in items_and_treats)
            ratio = amt / total_item_val if total_item_val > 0 else 1.0

            for item, t in items_and_treats:
                if not t:
                    continue
                med_name = t.name.replace('Pharmacy: ', '').strip()
                med = meds_dict.get(med_name.lower())
                purchase_rate = float(med.purchase_rate) if med else 0.0
                
                if med_name not in meds_summary:
                    meds_summary[med_name] = {'qty': 0, 'sale_price': 0.0, 'cost_per_unit': purchase_rate}
                
                sale_price = float(item.price * item.qty) * ratio
                cost = purchase_rate * item.qty
                profit = sale_price - cost
                bill_cost += cost

                meds_summary[med_name]['qty'] += item.qty
                meds_summary[med_name]['sale_price'] += sale_price
                
                p_obj = patients_dict.get(b.patient_id)
                pharmacy_sales['transactions'].append({
                    'date': b.created_at.strftime('%d %b %Y'),
                    'patient_name': p_obj.name if p_obj else 'Walk-in',
                    'medicine': med_name,
                    'qty': item.qty,
                    'sale_price': sale_price,
                    'profit': profit
                })
            daily_pharm[day_str]['cost'] += bill_cost

        # Populate daily purchases (expenses) in daily_pharm
        for pp in PharmacyPurchase.objects.filter(purchase_date__range=(start_date, end_date)):
            day_str = pp.purchase_date.strftime('%Y-%m-%d')
            if day_str in daily_pharm:
                daily_pharm[day_str]['expenses'] += float(pp.grand_total)
                
        for mp in MedicinePurchase.objects.filter(date__range=(start_dt, end_dt)):
            day_str = timezone.localtime(mp.date).strftime('%Y-%m-%d')
            if day_str in daily_pharm:
                daily_pharm[day_str]['expenses'] += float(mp.total_amount)
                
        for name, data in meds_summary.items():
            cost = data['qty'] * data['cost_per_unit']
            profit = data['sale_price'] - cost
            pharmacy_sales['total_cost'] += cost
            pharmacy_sales['items'].append({
                'name': name,
                'qty': data['qty'],
                'sale_price': data['sale_price'],
                'cost': cost,
                'profit': profit
            })
        pharmacy_sales['items'].sort(key=lambda x: x['profit'], reverse=True)
        
        # Profit represents Sales - Stock Purchases (Expenses) as requested
        pharmacy_sales['total_profit'] = pharmacy_sales['total_sales'] - total_pharmacy_expenses
        
        for d, data in daily_pharm.items():
            if data['sales'] > 0 or data['expenses'] > 0:
                pharmacy_sales['day_by_day'].append({
                    'date': d,
                    'sales': data['sales'],
                    'expenses': data['expenses'],
                    'profit': data['sales'] - data['expenses']
                })
        pharmacy_sales['day_by_day'].sort(key=lambda x: x['date'])

        # 6. Expenses
        seed_default_categories()
        all_cats = ExpenseCategory.objects.all()
        expenses_summary = {c.key: 0.0 for c in all_cats}
        if 'other' not in expenses_summary:
            expenses_summary['other'] = 0.0

        # Let Expense table handle pharmacy_purchase
        # expenses_summary['pharmacy_purchase'] = total_pharmacy_expenses

        month_expenses = Expense.objects.filter(date__range=(start_date, end_date)).order_by('-date', '-created_at')
        detailed_expenses = []
        
        daily_exp_map = {}
        for i in range(max_days + 1):
            day = start_date + datetime.timedelta(days=i)
            date_key = day.strftime('%Y-%m-%d')
            daily_exp_map[date_key] = 0.0
            
        for e in month_expenses:
            amt = float(e.amount)
            cat = (e.category or '').lower()
            
            # Let Expense table populate it
            pass

            if cat in expenses_summary:
                expenses_summary[cat] += amt
            else:
                expenses_summary['other'] += amt
                
            day_str = e.date.strftime('%Y-%m-%d')
            if day_str not in daily_exp_map:
                daily_exp_map[day_str] = 0.0
            daily_exp_map[day_str] += amt

        # Pharmacy purchases are already in month_expenses since they create Expense records.
            
        for e in month_expenses:
            amt = float(e.amount)
            detailed_expenses.append({
                'id': e.id,
                'title': e.title,
                'category': e.category,
                'description': e.description or '',
                'amount': amt,
                'date': e.date.strftime('%Y-%m-%d'),
                'paid_to': e.paid_to or '',
                'payment_method': e.payment_method or 'Cash',
                'notes': e.notes or '',
                'attachment_name': e.attachment_name or '',
                'attachment_data': e.attachment_data or '',
                'is_recurring': e.is_recurring,
                'recurring_frequency': e.recurring_frequency or '',
                'status': e.status,
                'branch': e.branch
            })

        day_by_day_expense = []
        for d, amt in daily_exp_map.items():
            day_by_day_expense.append({
                'date': d,
                'amount': amt
            })
        day_by_day_expense.sort(key=lambda x: x['date'])

        # 7. Monthly Stats - Optimized using in-memory year metrics to prevent 48 DB trips
        bills_by_month = defaultdict(float)
        for b in Billing.objects.filter(created_at__year=year).only('created_at', 'paid_amount'):
            bills_by_month[b.created_at.month] += float(b.paid_amount or 0)
            
        payments_by_month = defaultdict(float)
        for p in Payment.objects.filter(created_at__year=year).exclude(visit__billings__isnull=False).only('created_at', 'paid_amount'):
            payments_by_month[p.created_at.month] += float(p.paid_amount or 0)
            
        adv_by_month = defaultdict(float)
        for pp in PharmacyPurchase.objects.filter(purchase_date__year=year).only('purchase_date', 'grand_total'):
            adv_by_month[pp.purchase_date.month] += float(pp.grand_total or 0)
            
        simple_by_month = defaultdict(float)
        for mp in MedicinePurchase.objects.filter(date__year=year).only('date', 'total_amount'):
            simple_by_month[mp.date.month] += float(mp.total_amount or 0)
            
        expenses_by_month = defaultdict(float)
        for e in Expense.objects.filter(date__year=year).only('date', 'amount'):
            expenses_by_month[e.date.month] += float(e.amount or 0)

        monthly_stats = []
        for m in range(1, 13):
            inc = bills_by_month[m] + payments_by_month[m]
            exp = expenses_by_month[m]

            
            monthly_stats.append({
                'month': list(month_abbr)[m],
                'year': year,
                'income': inc,
                'expense': exp,
                'profit': inc - exp
            })

        return Response({
            'dailyIncome': daily_income,
            'monthlyIncome': month_income,
            'detailedIncome': detailed_income,
            'doctorRevenue': doctor_revenue,
            'pharmacySales': pharmacy_sales,
            'expenses': expenses_summary,
            'detailedExpenses': detailed_expenses,
            'dayByDayExpense': day_by_day_expense,
            'monthlyStats': monthly_stats,
            'categories': [
                {
                    'id': c.id,
                    'name': c.name,
                    'key': c.key,
                    'color': c.color,
                    'icon': c.icon,
                    'is_predefined': c.is_predefined
                } for c in all_cats
            ],
            'pendingPayments': float(Billing.objects.filter(status='Pending').aggregate(total=Sum('balance_amount'))['total'] or 0.00) if hasattr(Billing, 'status') else 0.00,
            'notes': []
        })

    def post(self, request):
        tx_type = request.data.get('type', 'expense') # 'expense' or 'income'
        
        if tx_type == 'income':
            amount = request.data.get('amount')
            payment_method = request.data.get('payment_method', 'Cash')
            description = request.data.get('description', '')
            date_str = request.data.get('date')
            patient_name = request.data.get('patient_name', 'General Clinic Income')
            
            if not amount:
                return Response({'error': 'Amount is required.'}, status=400)
                
            try:
                from django.utils.dateparse import parse_date
                from django.utils import timezone
                import datetime
                import random
                
                patient = Patient.objects.filter(phone='0000000000').first()
                if not patient:
                    patient = Patient.objects.create(name='General Clinic Income', phone='0000000000')
                
                # Overwrite patient name if specified to be custom
                if patient_name and patient_name != 'General Clinic Income':
                    existing = Patient.objects.filter(name=patient_name).first()
                    if existing:
                        patient = existing
                    else:
                        dummy_phone = f"99{random.randint(10000000, 99999999)}"
                        patient = Patient.objects.create(name=patient_name, phone=dummy_phone)
                
                dt_obj = timezone.now()
                if date_str:
                    parsed = parse_date(date_str)
                    if parsed:
                        dt_obj = timezone.make_aware(datetime.datetime.combine(parsed, timezone.localtime().time()))
                
                billing = Billing.objects.create(
                    patient=patient,
                    bill_type='Clinical',
                    total_amount=Decimal(str(amount)),
                    paid_amount=Decimal(str(amount)),
                    payment_method=payment_method if payment_method else 'Cash',
                    notes=description if description else 'Manual Income Entry'
                )
                
                doctor_id = request.data.get('doctor_id')
                if doctor_id:
                    try:
                        doc = Doctor.objects.filter(id=doctor_id).first()
                        if doc:
                            billing.doctor = doc
                    except Exception:
                        pass
                        
                Billing.objects.filter(pk=billing.pk).update(created_at=dt_obj)
                billing.refresh_from_db()
                
                return Response({
                    'status': 'success',
                    'income': {
                        'id': f"bill_{billing.id}",
                        'patient_name': patient.name,
                        'amount': float(billing.paid_amount),
                        'payment_method': billing.payment_method,
                        'description': billing.notes,
                        'date': billing.created_at.strftime('%Y-%m-%d')
                    }
                })
            except Exception as e:
                return Response({'error': str(e)}, status=400)
        else:
            category = request.data.get('category')
            description = request.data.get('description', '')
            amount = request.data.get('amount')
            date_str = request.data.get('date')
            
            if not category or not amount:
                return Response({'error': 'Category and amount are required.'}, status=400)
                
            try:
                expense = Expense.objects.create(
                    category=category,
                    description=description,
                    amount=Decimal(str(amount)),
                    date=date_str if date_str else datetime.date.today()
                )
                return Response({
                    'status': 'success',
                    'expense': {
                        'id': expense.id,
                        'category': expense.category,
                        'description': expense.description,
                        'amount': float(expense.amount),
                        'date': expense.date.strftime('%Y-%m-%d')
                    }
                })
            except Exception as e:
                return Response({'error': str(e)}, status=400)

    def delete(self, request):
        id_str = request.query_params.get('id')
        if not id_str:
            return Response({'error': 'ID is required.'}, status=400)
        try:
            if str(id_str).startswith('bill_'):
                real_id = str(id_str).replace('bill_', '')
                try:
                    real_id = int(real_id)
                except ValueError:
                    pass
                Billing.objects.filter(id=real_id).delete()
            elif str(id_str).startswith('payment_'):
                real_id = str(id_str).replace('payment_', '')
                try:
                    real_id = int(real_id)
                except ValueError:
                    pass
                Payment.objects.filter(id=real_id).delete()
            else:
                # Fallback to Expense delete
                Expense.objects.filter(id=id_str).delete()
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)


class ExpenseCategoryAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        seed_default_categories()
        cats = ExpenseCategory.objects.all().order_by('-is_predefined', 'name')
        return Response([
            {
                'id': c.id,
                'name': c.name,
                'key': c.key,
                'color': c.color,
                'icon': c.icon,
                'is_predefined': c.is_predefined,
                'default_amount': c.default_amount
            } for c in cats
        ])

    def post(self, request):
        name = request.data.get('name')
        color = request.data.get('color', '#3b82f6')
        icon = request.data.get('icon', 'Receipt')
        if not name:
            return Response({'error': 'Name is required'}, status=400)
        
        key = name.lower().replace(' ', '_').replace('&', 'and')
        # Check if already exists
        if ExpenseCategory.objects.filter(Q(name__iexact=name) | Q(key=key)).exists():
            return Response({'error': 'Category already exists'}, status=400)
            
        cat = ExpenseCategory.objects.create(
            name=name,
            key=key,
            color=color,
            icon=icon,
            is_predefined=False,
            default_amount=request.data.get('default_amount', 0.00)
        )
        return Response({'status': 'success', 'id': cat.id, 'name': cat.name, 'key': cat.key, 'default_amount': cat.default_amount})

    def put(self, request, pk):
        try:
            cat = ExpenseCategory.objects.get(pk=pk)
        except ExpenseCategory.DoesNotExist:
            return Response({'error': 'Category not found'}, status=404)
            
        if cat.is_predefined and ('name' in request.data or 'color' in request.data or 'icon' in request.data):
            # Predefined categories can only update default_amount
            if set(request.data.keys()) - {'default_amount'} != set():
                pass # Allow it to slide or just ignore other fields
            
        if not cat.is_predefined:
            name = request.data.get('name')
            if name:
                cat.name = name
                cat.key = name.lower().replace(' ', '_').replace('&', 'and')
            cat.color = request.data.get('color', cat.color)
            cat.icon = request.data.get('icon', cat.icon)
            
        if 'default_amount' in request.data:
            cat.default_amount = request.data.get('default_amount', cat.default_amount)
            
        cat.save()
        return Response({'status': 'success'})

    def delete(self, request, pk):
        try:
            cat = ExpenseCategory.objects.get(pk=pk)
        except ExpenseCategory.DoesNotExist:
            return Response({'error': 'Category not found'}, status=404)
            
        if cat.is_predefined:
            return Response({'error': 'Predefined categories cannot be deleted'}, status=400)
            
        cat.delete()
        return Response({'status': 'success'})


class ExpenseAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        q = request.query_params.get('q', '')
        category = request.query_params.get('category', '')
        payment_method = request.query_params.get('payment_method', '')
        status_filter = request.query_params.get('status', '')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        qs = Expense.objects.all().order_by('-date', '-created_at')

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(paid_to__icontains=q))
        if category:
            qs = qs.filter(category=category)
        if payment_method:
            qs = qs.filter(payment_method__iexact=payment_method)
        if status_filter:
            qs = qs.filter(status__iexact=status_filter)
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)

        data = []
        for e in qs:
            data.append({
                'id': e.id,
                'title': e.title,
                'category': e.category,
                'amount': float(e.amount),
                'date': e.date.strftime('%Y-%m-%d'),
                'paid_to': e.paid_to or '',
                'payment_method': e.payment_method,
                'vendor': e.vendor or '',
                'transaction_id': e.transaction_id or '',
                'notes': e.notes or '',
                'description': e.description or '',
                'attachment_name': e.attachment_name or '',
                'attachment_data': e.attachment_data or '',
                'is_recurring': e.is_recurring,
                'recurring_frequency': e.recurring_frequency or '',
                'status': e.status,
                'branch': e.branch
            })
        return Response(data)

    def post(self, request):
        title = request.data.get('title')
        category = request.data.get('category')
        amount = request.data.get('amount')
        date_str = request.data.get('date')
        
        if not title or not category or amount is None:
            return Response({'error': 'Title, category, and amount are required.'}, status=400)
            
        try:
            amt = Decimal(str(amount))
            if amt <= 0:
                return Response({'error': 'Amount must be positive.'}, status=400)
        except Exception:
            return Response({'error': 'Invalid amount.'}, status=400)

        category_ref = None
        cat_obj = ExpenseCategory.objects.filter(key=category).first()
        if cat_obj:
            category_ref = cat_obj
            
        expense = Expense.objects.create(
            title=title,
            category=category,
            category_ref=category_ref,
            description=request.data.get('description', ''),
            amount=amt,
            date=date_str if date_str else datetime.date.today(),
            paid_to=request.data.get('paid_to', ''),
            vendor=request.data.get('vendor', ''),
            transaction_id=request.data.get('transaction_id', ''),
            payment_method=request.data.get('payment_method', 'Cash'),
            notes=request.data.get('notes', ''),
            attachment_name=request.data.get('attachment_name', ''),
            attachment_data=request.data.get('attachment_data', ''),
            is_recurring=request.data.get('is_recurring', False),
            recurring_frequency=request.data.get('recurring_frequency', ''),
            status=request.data.get('status', 'Paid'),
            branch=request.data.get('branch', 'Main Branch')
        )
        
        AuditLog.objects.create(action=f"Created Expense: {title} (₹{amount})")
        return Response({'status': 'success', 'id': expense.id})

    def put(self, request, pk):
        try:
            expense = Expense.objects.get(pk=pk)
        except Expense.DoesNotExist:
            return Response({'error': 'Expense not found.'}, status=404)
            
        amount = request.data.get('amount')
        if amount is not None:
            try:
                amt = Decimal(str(amount))
                if amt <= 0:
                    return Response({'error': 'Amount must be positive.'}, status=400)
                expense.amount = amt
            except Exception:
                return Response({'error': 'Invalid amount.'}, status=400)

        expense.title = request.data.get('title', expense.title)
        expense.category = request.data.get('category', expense.category)
        
        cat_obj = ExpenseCategory.objects.filter(key=expense.category).first()
        if cat_obj:
            expense.category_ref = cat_obj

        expense.description = request.data.get('description', expense.description)
        if 'date' in request.data:
            expense.date = request.data['date']
        expense.paid_to = request.data.get('paid_to', expense.paid_to)
        expense.vendor = request.data.get('vendor', expense.vendor)
        expense.transaction_id = request.data.get('transaction_id', expense.transaction_id)
        expense.payment_method = request.data.get('payment_method', expense.payment_method)
        expense.notes = request.data.get('notes', expense.notes)
        expense.attachment_name = request.data.get('attachment_name', expense.attachment_name)
        expense.attachment_data = request.data.get('attachment_data', expense.attachment_data)
        expense.is_recurring = request.data.get('is_recurring', expense.is_recurring)
        expense.recurring_frequency = request.data.get('recurring_frequency', expense.recurring_frequency)
        expense.status = request.data.get('status', expense.status)
        expense.branch = request.data.get('branch', expense.branch)
        expense.save()

        AuditLog.objects.create(action=f"Updated Expense: {expense.title} (₹{expense.amount})")
        return Response({'status': 'success'})

    def delete(self, request, pk):
        try:
            expense = Expense.objects.get(pk=pk)
            title = expense.title
            amt = expense.amount
            expense.delete()
            AuditLog.objects.create(action=f"Deleted Expense: {title} (₹{amt})")
            return Response({'status': 'success'})
        except Expense.DoesNotExist:
            return Response({'error': 'Expense not found.'}, status=404)


class ExpenseBulkDeleteAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No IDs provided.'}, status=400)
            
        deleted_count = Expense.objects.filter(id__in=ids).delete()[0]
        AuditLog.objects.create(action=f"Bulk Deleted {deleted_count} expenses.")
        return Response({'status': 'success', 'deleted': deleted_count})


class DoctorSalaryAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        doctors = Doctor.objects.all()
        configs = []
        for doc in doctors:
            salary_config, created = DoctorSalary.objects.get_or_create(
                doctor=doc,
                defaults={'base_salary': Decimal('30000.00'), 'incentive_percent': Decimal('10.00')}
            )
            configs.append({
                'doctor_id': doc.id,
                'doctor_name': doc.name,
                'base_salary': float(salary_config.base_salary),
                'incentive_percent': float(salary_config.incentive_percent)
            })
            
        records = DoctorSalaryRecord.objects.all().order_by('-year', '-month', '-created_at')
        records_data = [{
            'id': r.id,
            'doctor_id': r.doctor.id,
            'doctor_name': r.doctor.name,
            'month': r.month,
            'year': r.year,
            'base_salary': float(r.base_salary),
            'incentive': float(r.incentive),
            'bonus': float(r.bonus),
            'deductions': float(r.deductions),
            'final_salary': float(r.final_salary),
            'status': r.status,
            'payment_date': r.payment_date.strftime('%Y-%m-%d') if r.payment_date else '',
            'payment_method': r.payment_method,
            'notes': r.notes or ''
        } for r in records]

        return Response({
            'configs': configs,
            'records': records_data
        })

    def post(self, request):
        action = request.data.get('action')
        if action == 'save_config':
            doctor_id = request.data.get('doctor_id')
            base_salary = request.data.get('base_salary', 0)
            incentive_percent = request.data.get('incentive_percent', 0)
            
            try:
                doc = Doctor.objects.get(pk=doctor_id)
            except Doctor.DoesNotExist:
                return Response({'error': 'Doctor not found'}, status=404)
                
            salary_config, _ = DoctorSalary.objects.get_or_create(doctor=doc)
            salary_config.base_salary = Decimal(str(base_salary))
            salary_config.incentive_percent = Decimal(str(incentive_percent))
            salary_config.save()
            
            AuditLog.objects.create(action=f"Saved Salary Config for Dr. {doc.name}")
            return Response({'status': 'success'})
            
        elif action == 'pay_salary':
            doctor_id = request.data.get('doctor_id')
            month = int(request.data.get('month', 1))
            year = int(request.data.get('year', 2026))
            base_salary = Decimal(str(request.data.get('base_salary', 0)))
            incentive = Decimal(str(request.data.get('incentive', 0)))
            bonus = Decimal(str(request.data.get('bonus', 0)))
            deductions = Decimal(str(request.data.get('deductions', 0)))
            final_salary = Decimal(str(request.data.get('final_salary', 0)))
            status = request.data.get('status', 'Pending')
            payment_method = request.data.get('payment_method', 'Bank Transfer')
            notes = request.data.get('notes', '')

            is_staff = False
            try:
                doc = Doctor.objects.get(pk=doctor_id)
            except Doctor.DoesNotExist:
                # Check if it's a Staff member
                try:
                    from patients.models import Staff
                    doc = Staff.objects.get(pk=doctor_id)
                    is_staff = True
                except:
                    return Response({'error': 'Doctor/Staff not found'}, status=404)

            record_id = None
            if not is_staff:
                existing = DoctorSalaryRecord.objects.filter(doctor=doc, month=month, year=year).first()
                if existing:
                    return Response({'error': f"Salary record already exists for Dr. {doc.name} in {month}/{year}"}, status=400)

                record = DoctorSalaryRecord.objects.create(
                    doctor=doc,
                    month=month,
                    year=year,
                    base_salary=base_salary,
                    incentive=incentive,
                    bonus=bonus,
                    deductions=deductions,
                    final_salary=final_salary,
                    status=status,
                    payment_date=datetime.date.today() if status == 'Paid' else None,
                    payment_method=payment_method,
                    notes=notes
                )
                record_id = record.id

            if status == 'Paid':
                cat_key = 'salary_incentives' if is_staff else 'doctor_salary'
                title_prefix = 'Staff Salary' if is_staff else 'Doctor Salary'
                doc_title = getattr(doc, 'name', 'Staff')
                if not is_staff:
                    doc_title = f"Dr. {doc.name}"

                cat_obj = ExpenseCategory.objects.filter(key=cat_key).first()
                Expense.objects.create(
                    title=f"{title_prefix} - {doc_title}",
                    category=cat_key,
                    category_ref=cat_obj,
                    description=f"Salary paid to {doc_title} for {month}/{year}. Base: ₹{base_salary}, Inc: ₹{incentive}, Bonus: ₹{bonus}, Ded: ₹{deductions}",
                    amount=final_salary,
                    date=datetime.date.today(),
                    paid_to=doc_title,
                    payment_method=payment_method,
                    status='Paid',
                    notes=notes
                )
                
            AuditLog.objects.create(action=f"Processed Salary Record for {getattr(doc, 'name', 'Staff')} - ₹{final_salary} ({status})")
            return Response({'status': 'success', 'record_id': record_id})
            
        return Response({'error': 'Invalid action'}, status=400)

    def delete(self, request, pk):
        try:
            record = DoctorSalaryRecord.objects.get(pk=pk)
            doc_name = record.doctor.name
            month = record.month
            year = record.year
            record.delete()
            AuditLog.objects.create(action=f"Deleted Salary Record for Dr. {doc_name} for {month}/{year}")
            return Response({'status': 'success'})
        except DoctorSalaryRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)


class DentalMaterialAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        materials = DentalMaterial.objects.all().order_by('name')
        materials_data = [{
            'id': m.id,
            'name': m.name,
            'quantity': m.quantity,
            'unit_price': float(m.unit_price),
            'supplier_id': m.supplier.id if m.supplier else None,
            'supplier_name': m.supplier.name if m.supplier else '',
            'low_stock_threshold': m.low_stock_threshold,
            'last_purchased_date': m.last_purchased_date.strftime('%Y-%m-%d') if m.last_purchased_date else ''
        } for m in materials]

        suppliers = Supplier.objects.all().order_by('name')
        suppliers_data = [{
            'id': s.id,
            'name': s.name
        } for s in suppliers]

        purchases = DentalMaterialPurchase.objects.all().order_by('-date', '-created_at')
        purchases_data = [{
            'id': p.id,
            'material_id': p.material.id,
            'material_name': p.material.name,
            'quantity': p.quantity,
            'unit_price': float(p.unit_price),
            'total_price': float(p.total_price),
            'supplier_name': p.supplier.name if p.supplier else '',
            'date': p.date.strftime('%Y-%m-%d')
        } for p in purchases]

        return Response({
            'materials': materials_data,
            'suppliers': suppliers_data,
            'purchases': purchases_data
        })

    def post(self, request):
        action = request.data.get('action')
        if action == 'add_material':
            name = request.data.get('name')
            quantity = int(request.data.get('quantity', 0))
            unit_price = Decimal(str(request.data.get('unit_price', 0)))
            supplier_id = request.data.get('supplier_id')
            low_stock_threshold = int(request.data.get('low_stock_threshold', 5))

            if not name:
                return Response({'error': 'Name is required'}, status=400)
                
            supplier = None
            if supplier_id:
                supplier = Supplier.objects.filter(pk=supplier_id).first()

            material, created = DentalMaterial.objects.get_or_create(
                name=name,
                defaults={
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'supplier': supplier,
                    'low_stock_threshold': low_stock_threshold
                }
            )
            if not created:
                return Response({'error': 'Material already exists'}, status=400)
                
            AuditLog.objects.create(action=f"Added Dental Material Stock Config: {name}")
            return Response({'status': 'success'})

        elif action == 'purchase':
            material_id = request.data.get('material_id')
            quantity = int(request.data.get('quantity', 1))
            unit_price = Decimal(str(request.data.get('unit_price', 0)))
            supplier_id = request.data.get('supplier_id')
            date_str = request.data.get('date')

            try:
                material = DentalMaterial.objects.get(pk=material_id)
            except DentalMaterial.DoesNotExist:
                return Response({'error': 'Material not found'}, status=404)

            supplier = None
            if supplier_id:
                supplier = Supplier.objects.filter(pk=supplier_id).first()

            total_price = unit_price * quantity
            purchase_date = date_str if date_str else datetime.date.today()

            purchase = DentalMaterialPurchase.objects.create(
                material=material,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price,
                supplier=supplier,
                date=purchase_date
            )

            material.quantity += quantity
            material.unit_price = unit_price
            material.last_purchased_date = purchase_date
            if supplier:
                material.supplier = supplier
            material.save()

            cat_key = 'dental_materials'
            lower_name = material.name.lower()
            if 'glove' in lower_name or 'mask' in lower_name or 'syringe' in lower_name or 'cotton' in lower_name or 'consumable' in lower_name:
                cat_key = 'consumables'

            cat_obj = ExpenseCategory.objects.filter(key=cat_key).first()
            Expense.objects.create(
                title=f"Inventory Purchase - {material.name}",
                category=cat_key,
                category_ref=cat_obj,
                description=f"Purchased x{quantity} units of {material.name} from {supplier.name if supplier else 'General Supplier'} at ₹{unit_price}/unit.",
                amount=total_price,
                date=purchase_date,
                paid_to=supplier.name if supplier else 'Cash Supplier',
                payment_method='Cash',
                status='Paid',
                notes=f"Linked to Material Purchase Log #{purchase.id}"
            )

            AuditLog.objects.create(action=f"Logged Material Purchase for {material.name} (x{quantity}) - ₹{total_price}")
            return Response({'status': 'success'})

        return Response({'error': 'Invalid action'}, status=400)


class PharmacyDashboardAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        today = timezone.localtime().date()
        preset = request.query_params.get('preset', 'today') # today, weekly, monthly, custom
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        if preset == 'today':
            start_date = today
            end_date = today
        elif preset == 'weekly':
            start_date = today - datetime.timedelta(days=6)
            end_date = today
        elif preset == 'monthly':
            start_date = datetime.date(today.year, today.month, 1)
            import calendar
            num_days = calendar.monthrange(today.year, today.month)[1]
            end_date = datetime.date(today.year, today.month, num_days)
        elif preset == 'custom' or (start_str and end_str):
            from django.utils.dateparse import parse_date
            start_date = parse_date(start_str) if start_str else today
            end_date = parse_date(end_str) if end_str else today
        else:
            start_date = today
            end_date = today

        start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

        # Query all pharmacy bills in the range
        bills = Billing.objects.filter(bill_type='Pharmacy', created_at__range=(start_dt, end_dt)).order_by('created_at')

        # Build day-by-day map
        daily_data = {}
        delta = end_date - start_date
        max_days = min(delta.days, 366)
        
        for i in range(max_days + 1):
            day = start_date + datetime.timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            daily_data[day_str] = {
                'date': day.strftime('%d-%b-%Y'),
                'invoice_count': 0,
                'sales': 0.0,
                'purchase_cost': 0.0,
                'profit': 0.0
            }

        # Evaluate bills to list
        bills_list = list(bills)
        
        # Today stats (always calculated for cards)
        today_start = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
        today_end = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))
        today_bills = Billing.objects.filter(bill_type='Pharmacy', created_at__range=(today_start, today_end))
        today_bills_list = list(today_bills)
        
        from collections import defaultdict
        
        # Collect referenced medicine names and billing items in bulk
        all_bill_ids = [b.id for b in bills_list] + [b.id for b in today_bills_list]
        billing_items_by_bill = defaultdict(list)
        treatments_dict = {}
        med_names = set()
        
        if all_bill_ids:
            billing_items = BillingItem.objects.filter(billing_id__in=all_bill_ids)
            t_ids = set(item.treatment_id for item in billing_items if item.treatment_id)
            treatments_dict = {t.id: t for t in TreatmentMaster.objects.filter(id__in=list(t_ids))} if t_ids else {}
            
            for item in billing_items:
                billing_items_by_bill[item.billing_id].append(item)
                t = treatments_dict.get(item.treatment_id)
                if t:
                    med_name = t.name.replace('Pharmacy: ', '').strip()
                    med_names.add(med_name.lower())
                    
        meds_dict = {m.name.lower(): m for m in MedicineMaster.objects.filter(name__in=list(med_names))} if med_names else {}
        
        today_sales = 0.0
        today_purchase_cost = 0.0
        
        for b in today_bills_list:
            amt = float(b.paid_amount)
            today_sales += amt
            bill_cost = 0.0
            items = billing_items_by_bill.get(b.id, [])
            for item in items:
                t = treatments_dict.get(item.treatment_id)
                if not t:
                    continue
                med_name = t.name.replace('Pharmacy: ', '').strip()
                med = meds_dict.get(med_name.lower())
                purchase_rate = float(med.purchase_rate) if med else 0.0
                bill_cost += purchase_rate * item.qty
            today_purchase_cost += bill_cost

        # Selected range processing
        for b in bills_list:
            day_str = timezone.localtime(b.created_at).strftime('%Y-%m-%d')
            if day_str not in daily_data:
                daily_data[day_str] = {
                    'date': timezone.localtime(b.created_at).strftime('%d-%b-%Y'),
                    'invoice_count': 0,
                    'sales': 0.0,
                    'purchase_cost': 0.0,
                    'profit': 0.0
                }
            
            amt = float(b.paid_amount)
            daily_data[day_str]['invoice_count'] += 1
            daily_data[day_str]['sales'] += amt
            
            bill_cost = 0.0
            items = billing_items_by_bill.get(b.id, [])
            for item in items:
                t = treatments_dict.get(item.treatment_id)
                if not t:
                    continue
                med_name = t.name.replace('Pharmacy: ', '').strip()
                med = meds_dict.get(med_name.lower())
                purchase_rate = float(med.purchase_rate) if med else 0.0
                bill_cost += purchase_rate * item.qty
            daily_data[day_str]['purchase_cost'] += bill_cost

        # Calculate profit and convert map to a list
        for d_key in daily_data:
            daily_data[d_key]['profit'] = daily_data[d_key]['sales'] - daily_data[d_key]['purchase_cost']

        daily_list = list(daily_data.values())
        # Sort in reverse chronological order
        daily_list.sort(key=lambda x: datetime.datetime.strptime(x['date'], '%d-%b-%Y'), reverse=True)

        return Response({
            'today_sales': today_sales,
            'today_purchase_cost': today_purchase_cost,
            'today_profit': today_sales - today_purchase_cost,
            'daily_report': daily_list
        })

class GenerateSalariesAPIView(APIView):
    def post(self, request):
        from .models import Staff, Expense
        from datetime import datetime
        from django.utils import timezone
        from decimal import Decimal
        
        current_month = datetime.now().strftime('%B %Y')
        current_date = timezone.now().date()
        
        active_staff = Staff.objects.filter(is_active=True, base_salary__gt=0)
        generated_count = 0
        
        for staff in active_staff:
            # Check if salary expense already exists for this staff this month
            exists = Expense.objects.filter(
                category='doctor_salary',
                paid_to=staff.name,
                title__contains=current_month
            ).exists()

            if not exists:
                Expense.objects.create(
                    title=f'Salary - {current_month} - {staff.name}',
                    category='doctor_salary',
                    amount=staff.base_salary + staff.incentive,
                    date=current_date,
                    paid_to=staff.name,
                    description=staff.role,
                    notes=f"Month: {current_month} | Bonus: {staff.incentive}",
                    status='Pending'
                )
                generated_count += 1
                
        return Response({'status': 'success', 'generated_count': generated_count})


class TotalExpenseSummaryView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        today = timezone.localtime().date()
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        if month and year:
            try:
                month = int(month)
                year = int(year)
            except ValueError:
                month = today.month
                year = today.year
            import calendar
            num_days = calendar.monthrange(year, month)[1]
            start_date = datetime.date(year, month, 1)
            end_date = datetime.date(year, month, num_days)
        elif start_str and end_str:
            from django.utils.dateparse import parse_date
            start_date = parse_date(start_str) or today
            end_date = parse_date(end_str) or today
        else:
            start_date = today
            end_date = today

        start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

        # Calculate pharmacy purchases (expenses) in the selected range
        adv_purchases_total = PharmacyPurchase.objects.filter(
            purchase_date__range=(start_date, end_date)
        ).aggregate(total=Sum('grand_total'))['total'] or 0
        
        simple_purchases_total = MedicinePurchase.objects.filter(
            date__range=(start_dt, end_dt)
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        total_pharmacy_expenses = float(adv_purchases_total) + float(simple_purchases_total)

        seed_default_categories()
        all_cats = ExpenseCategory.objects.all()
        expenses_summary = {c.key: 0.0 for c in all_cats}
        if 'other' not in expenses_summary:
            expenses_summary['other'] = 0.0

        # Inject actual pharmacy purchases into regular expenses category 'pharmacy_purchase'
        expenses_summary['pharmacy_purchase'] = total_pharmacy_expenses

        month_expenses = Expense.objects.filter(date__range=(start_date, end_date))
        
        delta = end_date - start_date
        max_days = min(delta.days, 366)
        daily_exp_map = {}
        for i in range(max_days + 1):
            day = start_date + datetime.timedelta(days=i)
            date_key = day.strftime('%Y-%m-%d')
            daily_exp_map[date_key] = 0.0

        for e in month_expenses:
            amt = float(e.amount)
            cat = (e.category or '').lower()
            
            # Avoid double counting since pharmacy purchases are manually added above/below
            if cat == 'pharmacy_purchase':
                continue
                
            if cat in expenses_summary:
                expenses_summary[cat] += amt
            else:
                expenses_summary['other'] += amt
                
            day_str = e.date.strftime('%Y-%m-%d')
            if day_str in daily_exp_map:
                daily_exp_map[day_str] += amt

        # Add advanced purchases to daily expense map for overall clinic trend
        for pp in PharmacyPurchase.objects.filter(purchase_date__range=(start_date, end_date)):
            day_str = pp.purchase_date.strftime('%Y-%m-%d')
            if day_str in daily_exp_map:
                daily_exp_map[day_str] += float(pp.grand_total)
                
        # Add simple purchases to daily expense map for overall clinic trend
        for mp in MedicinePurchase.objects.filter(date__range=(start_dt, end_dt)):
            day_str = timezone.localtime(mp.date).strftime('%Y-%m-%d')
            if day_str in daily_exp_map:
                daily_exp_map[day_str] += float(mp.total_amount)

        day_by_day_expense = []
        for d, amt in daily_exp_map.items():
            day_by_day_expense.append({
                'date': d,
                'amount': amt
            })
        day_by_day_expense.sort(key=lambda x: x['date'])

        grand_total = sum(expenses_summary.values())

        # Construct the response payload matching DashboardFinanceWidgets expectations
        response_data = {
            'grand_total': grand_total,
            'daily_trend': day_by_day_expense,
        }
        # Include category key-values in the same dictionary so UI can read expenses[cat]
        for cat_key, total in expenses_summary.items():
            response_data[cat_key] = total

        return Response(response_data)


class TransactionSummaryAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        today = datetime.date.today()
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        if start_str and end_str:
            from django.utils.dateparse import parse_date
            start_date = parse_date(start_str) or today
            end_date = parse_date(end_str) or today
        else:
            start_date = today
            end_date = today

        start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

        # Total Patients (based on appointments)
        from patients.models import Appointment, Payment, Billing
        patient_count = Appointment.objects.filter(date__range=(start_date, end_date)).values('patient').distinct().count()

        # Payments Breakdown
        bills = Billing.objects.filter(is_invoice=True, created_at__range=(start_dt, end_dt))
        legacy_payments = Payment.objects.filter(patient__isnull=False, created_at__range=(start_dt, end_dt)).exclude(visit__billings__isnull=False)

        cash_total = 0.0
        upi_total = 0.0
        card_total = 0.0
        other_total = 0.0
        total_revenue = 0.0

        for b in bills:
            amt = float(b.paid_amount) if b.paid_amount is not None else 0.0
            pm = (b.payment_method or '').lower()
            if pm == 'cash': cash_total += amt
            elif pm == 'upi': upi_total += amt
            elif pm == 'card': card_total += amt
            else: other_total += amt
            total_revenue += amt

        for p in legacy_payments:
            amt = float(p.paid_amount) if p.paid_amount is not None else 0.0
            pm = (p.payment_method or '').lower()
            if pm == 'cash': cash_total += amt
            elif pm == 'upi': upi_total += amt
            elif pm == 'card': card_total += amt
            else: other_total += amt
            total_revenue += amt

        # Expenses
        expenses = Expense.objects.filter(date__range=(start_date, end_date))
        total_expenses = sum(float(e.amount) for e in expenses)

        # Net Income
        net_income = total_revenue - total_expenses

        return Response({
            'patients': patient_count,
            'payments': {
                'cash': cash_total,
                'upi': upi_total,
                'card': card_total,
                'other': other_total,
                'total': total_revenue
            },
            'expenses': {
                'total': total_expenses
            },
            'total_revenue': total_revenue,
            'net_income': net_income
        })
