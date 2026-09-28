from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Count, Sum, Q
from django.db import models
from django.db.models.functions import TruncDate
from django.utils.dateparse import parse_date
from .models import (
    Appointment, Patient, ClinicalNotes, Billing, Transaction, 
    PharmacyPurchase, Prescription, MedicineStock, Expense,
    CommunicationLog, TreatmentRecord, PreBooking
)
from datetime import datetime, timedelta

class EHRReportView(APIView):
    def get(self, request, report_type):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        # Default to last 30 days if no dates provided
        if start_date_str:
            start_date = parse_date(start_date_str)
        else:
            start_date = datetime.now().date() - timedelta(days=30)
            
        if end_date_str:
            end_date = parse_date(end_date_str)
        else:
            end_date = datetime.now().date()

        # For exact date/datetime filtering logic
        inclusive_end = end_date + timedelta(days=1)
        
        data = []

        if report_type == 'appointment':
            qs = Appointment.objects.filter(date__gte=start_date, date__lte=end_date).select_related('patient', 'doctor').order_by('-date')
            for item in qs:
                data.append({
                    'date': item.date.strftime('%Y-%m-%d') if item.date else '',
                    'reference': item.patient.name if item.patient else 'Unknown',
                    'status': item.status or 'Unknown',
                    'details': f"Dr. {item.doctor.name if item.doctor else 'Unassigned'}",
                    'full_data': {
                        'Patient_Phone': item.patient.phone if item.patient else '',
                        'Doctor': item.doctor.name if item.doctor else '',
                        'Time': item.time.strftime('%I:%M %p') if item.time else 'Not Set'
                    }
                })

        elif report_type == 'patient':
            qs = Patient.objects.filter(created_at__gte=start_date, created_at__lt=inclusive_end).order_by('-created_at')
            for item in qs:
                data.append({
                    'date': item.created_at.strftime('%Y-%m-%d'),
                    'reference': item.name,
                    'status': item.status,
                    'details': f"Phone: {item.phone}, Age: {item.age or '-'}",
                    'full_data': {
                        'Phone': item.phone,
                        'Age': item.age,
                        'Gender': item.gender,
                        'Total_Balance_Due': item.total_balance
                    }
                })

        elif report_type == 'invoice':
            qs = Billing.objects.filter(created_at__gte=start_date, created_at__lt=inclusive_end, bill_type='Clinical').select_related('patient').order_by('-created_at')
            for item in qs:
                data.append({
                    'date': item.created_at.strftime('%Y-%m-%d'),
                    'reference': item.patient.name if item.patient else 'Unknown',
                    'status': item.status,
                    'details': f"Billed: {item.total_amount} | Paid: {item.paid_amount}",
                    'full_data': {
                        'Total_Amount': str(item.total_amount),
                        'Paid_Amount': str(item.paid_amount),
                        'Balance_Due': str(item.balance_amount),
                        'Payment_Method': item.payment_method,
                        'Notes': item.notes
                    }
                })

        elif report_type == 'receipt':
            qs = Transaction.objects.filter(date__gte=start_date, date__lte=end_date, type='Income').select_related('patient').order_by('-date')
            for item in qs:
                data.append({
                    'date': item.date.strftime('%Y-%m-%d'),
                    'reference': item.patient.name if item.patient else item.category,
                    'status': 'Income',
                    'details': f"Amount: {item.amount} ({item.payment_method})",
                    'full_data': {
                        'Amount': str(item.amount),
                        'Category': item.category,
                        'Payment_Method': item.payment_method,
                        'Notes': item.notes
                    }
                })

        elif report_type == 'pharmacy':
            qs = Billing.objects.filter(created_at__gte=start_date, created_at__lt=inclusive_end, bill_type='Pharmacy').prefetch_related('items__treatment').select_related('patient').order_by('-created_at')
            for item in qs:
                sold_items = ", ".join([f"{b_item.treatment.name} (x{b_item.qty})" for b_item in item.items.all()])
                data.append({
                    'date': item.created_at.strftime('%Y-%m-%d'),
                    'reference': item.patient.name if item.patient else 'Walk-in',
                    'status': item.status,
                    'details': f"Bill Amount: {item.total_amount}",
                    'full_data': {
                        'Total_Amount': str(item.total_amount),
                        'Items_Sold': sold_items or 'None',
                        'Paid_Amount': str(item.paid_amount),
                        'Balance_Due': str(item.balance_amount),
                        'Payment_Method': item.payment_method
                    }
                })

        elif report_type == 'prescription':
            qs = Prescription.objects.filter(created_at__gte=start_date, created_at__lt=inclusive_end).prefetch_related('items').select_related('patient', 'doctor').order_by('-created_at')
            for item in qs:
                medicines = ", ".join([f"{med.medicine_name} ({med.dosage})" for med in item.items.all()])
                data.append({
                    'date': item.created_at.strftime('%Y-%m-%d'),
                    'reference': item.patient.name if item.patient else 'Unknown',
                    'status': item.status,
                    'details': f"Dr. {item.doctor.name if item.doctor else 'Unknown'} | {len(item.items.all())} Meds",
                    'full_data': {
                        'Doctor': item.doctor.name if item.doctor else 'Unknown',
                        'Medicines': medicines or 'None',
                        'Status': item.status,
                        'Notes': item.notes
                    }
                })

        elif report_type == 'clinical_notes' or report_type == 'emr':
            qs = ClinicalNotes.objects.filter(created_at__gte=start_date, created_at__lt=inclusive_end).select_related('appointment__patient').order_by('-created_at')
            for item in qs:
                patient_name = item.appointment.patient.name if item.appointment and item.appointment.patient else 'Unknown'
                diag = ", ".join(item.diagnosis) if item.diagnosis else "No diagnosis"
                data.append({
                    'date': item.created_at.strftime('%Y-%m-%d') if item.created_at else '',
                    'reference': patient_name,
                    'status': 'Recorded',
                    'details': f"Diagnosis: {diag}",
                    'full_data': {
                        'Diagnosis': diag,
                        'Complaints': ", ".join(item.complaints) if item.complaints else '-',
                        'Observations': ", ".join(item.observations) if item.observations else '-',
                        'Treatment_Plan': item.treatment_plan
                    }
                })

        elif report_type == 'stock':
            qs = PharmacyPurchase.objects.filter(purchase_date__gte=start_date, purchase_date__lte=end_date).prefetch_related('items__medicine').select_related('supplier').order_by('-purchase_date')
            for item in qs:
                purchased_items = ", ".join([f"{p_item.medicine.name} (Qty: {p_item.qty})" for p_item in item.items.all()])
                data.append({
                    'date': item.purchase_date.strftime('%Y-%m-%d') if item.purchase_date else '',
                    'reference': item.supplier.name if item.supplier else 'Unknown Supplier',
                    'status': 'Purchased',
                    'details': f"Inv: {item.invoice_no} | Total: {item.grand_total}",
                    'full_data': {
                        'Invoice_No': item.invoice_no,
                        'Items': purchased_items or 'None',
                        'Subtotal': str(item.subtotal),
                        'Tax_Amount': str(item.tax_amount),
                        'Discount': str(item.discount_amount),
                        'Grand_Total': str(item.grand_total),
                        'Paid_Amount': str(item.paid_amount),
                        'Balance_Due': str(item.balance_due)
                    }
                })

        elif report_type == 'expense':
            qs = Expense.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')
            for item in qs:
                data.append({
                    'date': item.date.strftime('%Y-%m-%d') if item.date else '',
                    'reference': item.category or 'Unknown',
                    'status': item.status if item.status else 'Paid',
                    'details': f"{item.title} - Amount: {item.amount or 0}",
                    'full_data': {
                        'Title': item.title,
                        'Category': item.category,
                        'Paid_To': item.paid_to or 'N/A',
                        'Payment_Method': item.payment_method,
                        'Description': item.description,
                        'Amount': str(item.amount)
                    }
                })

        elif report_type == 'communication':
            qs = CommunicationLog.objects.filter(sent_at__gte=start_date, sent_at__lt=inclusive_end).select_related('patient').order_by('-sent_at')
            for item in qs:
                safe_msg = str(item.message or '')[:50]
                data.append({
                    'date': item.sent_at.strftime('%Y-%m-%d') if item.sent_at else '',
                    'reference': item.patient.name if item.patient else 'Unknown',
                    'status': item.channel or 'Unknown',
                    'details': f"Message: {safe_msg}...",
                    'full_data': {
                        'Channel': item.channel,
                        'Full_Message': item.message
                    }
                })

        elif report_type == 'treatments':
            qs = TreatmentRecord.objects.filter(visit__created_at__gte=start_date, visit__created_at__lt=inclusive_end).select_related('visit__patient', 'treatment').order_by('-visit__created_at')
            for item in qs:
                data.append({
                    'date': item.visit.created_at.strftime('%Y-%m-%d') if item.visit and item.visit.created_at else '',
                    'reference': item.visit.patient.name if item.visit and item.visit.patient else 'Unknown',
                    'status': 'Completed',
                    'details': f"Treatment: {item.treatment.name if item.treatment else 'Unknown'} (Price: {item.price or 0})",
                    'full_data': {
                        'Treatment_Name': item.treatment.name if item.treatment else '',
                        'Fee_Type': item.fee_type,
                        'Price': str(item.price),
                        'Notes': item.notes
                    }
                })
                
        elif report_type == 'pre_booking':
            qs = PreBooking.objects.filter(created_at__gte=start_date, created_at__lt=inclusive_end).order_by('-created_at')
            for item in qs:
                data.append({
                    'date': item.created_at.strftime('%Y-%m-%d') if item.created_at else '',
                    'reference': item.name or 'Unknown',
                    'status': item.status or 'Unknown',
                    'details': f"Expected: {item.expected_date or 'TBD'} | Phone: {item.phone or '-'}",
                    'full_data': {
                        'Phone': item.phone,
                        'Expected_Date': str(item.expected_date) if item.expected_date else '',
                        'Notes': item.notes
                    }
                })

        return Response({
            'report_type': report_type,
            'start_date': start_date,
            'end_date': end_date,
            'results': data
        })
