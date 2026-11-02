from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import Patient, Treatment, Prescription, Invoice, InvoiceItem
from decimal import Decimal
import json

def patient_detail(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    return render(request, 'patient_management/patient_detail.html', {'patient': patient})

def treatment_list(request, patient_id):
    treatments = Treatment.objects.filter(patient_id=patient_id).order_by('-created_at')
    return render(request, 'patient_management/partials/treatment_list.html', {'treatments': treatments})

def add_treatment(request, patient_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            total_amount = (Decimal(data['price']) * int(data['quantity'])) - Decimal(data.get('discount', 0)) + Decimal(data.get('tax', 0))
            Treatment.objects.create(
                patient_id=patient_id,
                treatment_name=data['treatment_name'],
                teeth=data.get('teeth', ''),
                quantity=data['quantity'],
                price=data['price'],
                discount=data.get('discount', 0),
                tax=data.get('tax', 0),
                total_amount=total_amount
            )
            return JsonResponse({'status': 'success', 'message': 'Treatment saved successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

def prescription_list(request, patient_id):
    prescriptions = Prescription.objects.filter(patient_id=patient_id).order_by('-created_at')
    return render(request, 'patient_management/partials/prescription_list.html', {'prescriptions': prescriptions})

def add_prescription(request, patient_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            Prescription.objects.create(
                patient_id=patient_id,
                drug_name=data['drug_name'],
                dosage=data['dosage'],
                frequency=data['frequency'],
                duration=data['duration'],
                instructions=data.get('instructions', ''),
                notes=data.get('notes', '')
            )
            return JsonResponse({'status': 'success', 'message': 'Prescription saved successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

def unbilled_treatments(request, patient_id):
    # Get treatments not linked to any InvoiceItem
    treatments = Treatment.objects.filter(patient_id=patient_id, invoiceitem__isnull=True).values('id', 'treatment_name', 'quantity', 'total_amount')
    return JsonResponse({'treatments': list(treatments)})

def invoice_list(request, patient_id):
    invoices = Invoice.objects.filter(patient_id=patient_id).order_by('-created_at')
    return render(request, 'patient_management/partials/invoice_list.html', {'invoices': invoices})

def add_invoice(request, patient_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            treatment_ids = data.get('treatment_ids', [])
            subtotal = Decimal(data.get('subtotal', 0))
            tax = Decimal(data.get('tax', 0))
            discount = Decimal(data.get('discount', 0))
            total = subtotal + tax - discount

            invoice = Invoice.objects.create(
                patient_id=patient_id,
                subtotal=subtotal,
                tax=tax,
                discount=discount,
                total=total
            )
            for tid in treatment_ids:
                treatment = Treatment.objects.get(id=tid)
                InvoiceItem.objects.create(invoice=invoice, treatment=treatment, price=treatment.total_amount)
            return JsonResponse({'status': 'success', 'message': 'Invoice generated successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)
