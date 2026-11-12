import io
from decimal import Decimal
from datetime import datetime, date, timedelta
from bson import ObjectId

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.models import User

from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
from rest_framework import status

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from patients.models import (
    Company, Branch, Doctor, Patient, Appointment, Visit,
    TreatmentMaster, TreatmentPlan, TreatmentPlanItem, TreatmentRecord,
    Billing, BillingItem, BillPayment, Transaction,
    Estimate, EstimateItem, AutoNumbering
)
from patients.security import get_request_scope, get_authenticated_user


def require_role(request, allowed_roles):
    """Enforces role-based permissions based on active staff session."""
    from patients.views import get_user_role
    role = get_user_role(request)
    if role is None:
        return Response({'error': 'Authentication required.'}, status=401)
    if role not in allowed_roles:
        return Response({'error': f'Access denied. Required roles: {allowed_roles}. Your role: {role}'}, status=403)
    return None


def get_clinic_branding(company, branch):
    """Returns dynamic clinic header details for PDFs based on Company and Branch."""
    c_name = company.name if company else "AshDent Dental Healthcare"
    b_name = branch.name if branch else "Main Branch"
    addr_parts = []
    if branch and branch.address:
        addr_parts.append(branch.address)
    if branch and branch.city:
        addr_parts.append(branch.city)
    if branch and branch.state:
        addr_parts.append(branch.state)
    if branch and branch.zip_code:
        addr_parts.append(f"Pincode: {branch.zip_code}")
    address_str = ", ".join(addr_parts) if addr_parts else "Healthcare Plaza, Main Road"

    phone = (branch.phone if branch and branch.phone else (company.phone if company and company.phone else "+91 98765 43210"))
    email = (branch.email if branch and branch.email else (company.email if company and company.email else "billing@ashdent.com"))

    return {
        "title": f"{c_name} — {b_name}".upper(),
        "address": address_str,
        "contact": f"Tel: {phone} | Email: {email}"
    }


class EstimateListCreateView(APIView):
    """
    List estimates for a patient or create a new formal Estimate.
    Company and Branch scoped.
    """
    def get(self, request, patient_id=None):
        pid = patient_id or request.query_params.get('patient_id')
        if not pid:
            return Response({'error': 'patient_id required'}, status=status.HTTP_400_BAD_REQUEST)
        patient = get_object_or_404(Patient, id=pid)
        scope = get_request_scope(request)

        estimates = Estimate.objects.filter(patient=patient).prefetch_related('items', 'revisions').order_by('-created_at')
        if not scope.is_super and scope.company:
            estimates = estimates.filter(company=scope.company)

        res = []
        for est in estimates:
            items_data = []
            for it in est.items.all():
                items_data.append({
                    "id": it.id,
                    "plan_item_id": it.plan_item_id,
                    "treatment_master_id": it.treatment_master_id,
                    "tooth_number": it.tooth_number,
                    "surface": it.surface,
                    "procedure_name": it.procedure_name,
                    "quantity": it.quantity,
                    "billed_quantity": it.billed_quantity,
                    "remaining_quantity": max(0, it.quantity - it.billed_quantity),
                    "standard_price": float(it.standard_price),
                    "unit_price": float(it.unit_price),
                    "discount": float(it.discount),
                    "total_amount": float(it.total_amount),
                    "status": it.status,
                    "notes": it.notes
                })

            res.append({
                "id": est.id,
                "estimate_number": est.estimate_number,
                "version": est.version,
                "parent_estimate_id": est.parent_estimate_id,
                "status": est.status,
                "doctor": est.doctor.name if est.doctor else "Doctor not assigned",
                "doctor_id": est.doctor_id,
                "treatment_plan_id": est.treatment_plan_id,
                "subtotal": float(est.subtotal),
                "discount": float(est.discount),
                "tax": float(est.tax),
                "grand_total": float(est.grand_total),
                "valid_until": est.valid_until.strftime('%Y-%m-%d') if est.valid_until else None,
                "notes": est.notes,
                "terms": est.terms,
                "created_at": est.created_at.strftime('%Y-%m-%d %H:%M'),
                "created_by": est.created_by.username if est.created_by else None,
                "items": items_data
            })

        return Response(res)

    def post(self, request, patient_id=None):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
        if denied:
            return denied

        pid = patient_id or request.data.get('patient_id')
        if not pid:
            return Response({'error': 'patient_id required in request'}, status=status.HTTP_400_BAD_REQUEST)
        patient = get_object_or_404(Patient, id=pid)
        scope = get_request_scope(request)
        company = scope.company or patient.company
        branch = scope.branch or patient.registration_branch
        data = request.data

        # Doctor resolution
        doc_id = data.get('doctor_id')
        doctor = Doctor.objects.filter(id=doc_id).first() if doc_id else patient.doctor
        if not doctor:
            latest_appt = Appointment.objects.filter(patient=patient).order_by('-date', '-time').first()
            if latest_appt and latest_appt.doctor:
                doctor = latest_appt.doctor

        # Optional treatment plan link
        plan_id = data.get('treatment_plan_id')
        plan = TreatmentPlan.objects.filter(id=plan_id, patient=patient).first() if plan_id else None

        # Validity date (default 30 days)
        valid_until_raw = data.get('valid_until')
        if valid_until_raw:
            try:
                valid_until = datetime.strptime(str(valid_until_raw)[:10], '%Y-%m-%d').date()
            except Exception:
                valid_until = timezone.now().date() + timedelta(days=30)
        else:
            valid_until = timezone.now().date() + timedelta(days=30)

        # Generate atomic sequence number
        est_number = AutoNumbering.get_next_sequence('estimate', branch=branch, company=company)

        # Tax & general discount
        tax_pct = Decimal(str(data.get('tax_percent') or data.get('tax_rate') or 0))
        overall_disc = Decimal(str(data.get('discount') or data.get('discount_amount') or 0))
        notes = data.get('notes', '')
        terms = data.get('terms', 'Estimate valid for 30 days from date of issue. Prices subject to clinical changes during treatment.')

        items_in = data.get('items', [])
        if not items_in and plan:
            # Auto-populate from plan if items not specified
            items_in = []
            for pi in plan.items.all():
                items_in.append({
                    "plan_item_id": pi.id,
                    "tooth_number": pi.tooth_number,
                    "surface": pi.surface,
                    "procedure_name": pi.procedure_name,
                    "treatment_master_id": pi.treatment_master_id,
                    "quantity": 1,
                    "standard_price": pi.standard_price_snapshot or pi.estimated_cost,
                    "unit_price": pi.final_cost or pi.estimated_cost,
                    "discount": pi.discount or 0
                })

        with transaction.atomic():
            estimate = Estimate.objects.create(
                company=company,
                branch=branch,
                patient=patient,
                doctor=doctor,
                treatment_plan=plan,
                estimate_number=est_number,
                version=1,
                status=data.get('status', 'Draft'),
                valid_until=valid_until,
                notes=notes,
                terms=terms,
                created_by=request.user if (hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False) and getattr(request.user, 'pk', None)) else None
            )

            subtotal = Decimal('0.00')
            item_disc_total = Decimal('0.00')

            seen_items = set()
            for it in items_in:
                proc_name = str(it.get('procedure_name') or it.get('procedure') or 'Treatment Procedure').strip()
                tooth_num = str(it.get('tooth_number') or it.get('tooth') or '').strip()
                surf = str(it.get('surface') or 'All').strip()

                dedup_key = (tooth_num, proc_name.lower(), surf.lower())
                if dedup_key in seen_items:
                    continue
                seen_items.add(dedup_key)

                # Link or find treatment master
                tm_id = it.get('treatment_master_id')
                tm = TreatmentMaster.objects.filter(id=tm_id).first() if tm_id else TreatmentMaster.objects.filter(name__iexact=proc_name).first()

                try:
                    qty = max(1, int(it.get('quantity') or it.get('qty') or 1))
                except Exception:
                    qty = 1

                try:
                    std_price = Decimal(str(it.get('standard_price') or (tm.price if tm else 0)))
                except Exception:
                    std_price = Decimal('0.00')

                try:
                    u_price = Decimal(str(it.get('unit_price') or it.get('cost') or std_price))
                except Exception:
                    u_price = std_price

                try:
                    disc = Decimal(str(it.get('discount') or 0))
                except Exception:
                    disc = Decimal('0.00')

                line_total = max(Decimal('0.00'), (u_price * qty) - disc)

                # Link plan item if passed
                pi_id = it.get('plan_item_id') or it.get('id')
                plan_item = TreatmentPlanItem.objects.filter(id=pi_id).first() if pi_id else None

                EstimateItem.objects.create(
                    estimate=estimate,
                    plan_item=plan_item,
                    treatment_master=tm,
                    tooth_number=tooth_num,
                    surface=surf,
                    procedure_name=proc_name,
                    quantity=qty,
                    billed_quantity=0,
                    standard_price=std_price,
                    unit_price=u_price,
                    discount=disc,
                    total_amount=line_total,
                    status='Pending',
                    notes=str(it.get('notes') or '')
                )

                subtotal += (u_price * qty)
                item_disc_total += disc

            total_disc = item_disc_total + overall_disc
            taxable = max(Decimal('0.00'), subtotal - total_disc)
            tax_amt = (taxable * (tax_pct / Decimal('100.00'))) if tax_pct > 0 else Decimal('0.00')
            grand_total = max(Decimal('0.00'), taxable + tax_amt)

            estimate.subtotal = subtotal
            estimate.discount = total_disc
            estimate.tax = tax_amt
            estimate.grand_total = grand_total
            estimate.save()

        return Response({
            "message": "Estimate created successfully",
            "id": estimate.id,
            "estimate_number": estimate.estimate_number,
            "version": estimate.version,
            "subtotal": float(estimate.subtotal),
            "discount_amount": float(estimate.discount),
            "tax_amount": float(estimate.tax),
            "grand_total": float(estimate.grand_total),
            "total_amount": float(estimate.grand_total),
            "status": estimate.status,
            "items": list(estimate.items.values('id', 'procedure_name', 'quantity', 'total_amount'))
        }, status=status.HTTP_201_CREATED)


class EstimateDetailUpdateView(APIView):
    """
    Get estimate details, update status (Accept, Reject), or create an authorized Revision.
    """
    def get(self, request, estimate_id):
        estimate = get_object_or_404(Estimate, id=estimate_id)
        scope = get_request_scope(request)
        if scope.company and estimate.company and estimate.company != scope.company:
            return Response({"error": "Estimate not found."}, status=404)
        items_data = []
        for it in estimate.items.all():
            items_data.append({
                "id": it.id,
                "plan_item_id": it.plan_item_id,
                "treatment_master_id": it.treatment_master_id,
                "tooth_number": it.tooth_number,
                "surface": it.surface,
                "procedure_name": it.procedure_name,
                "quantity": it.quantity,
                "billed_quantity": it.billed_quantity,
                "remaining_quantity": max(0, it.quantity - it.billed_quantity),
                "standard_price": float(it.standard_price),
                "unit_price": float(it.unit_price),
                "discount": float(it.discount),
                "total_amount": float(it.total_amount),
                "status": it.status,
                "notes": it.notes
            })

        return Response({
            "id": estimate.id,
            "estimate_number": estimate.estimate_number,
            "version": estimate.version,
            "parent_estimate_id": estimate.parent_estimate_id,
            "status": estimate.status,
            "patient_id": estimate.patient_id,
            "patient_name": estimate.patient.name,
            "doctor": estimate.doctor.name if estimate.doctor else "Doctor not assigned",
            "doctor_id": estimate.doctor_id,
            "treatment_plan_id": estimate.treatment_plan_id,
            "subtotal": float(estimate.subtotal),
            "discount": float(estimate.discount),
            "tax": float(estimate.tax),
            "grand_total": float(estimate.grand_total),
            "valid_until": estimate.valid_until.strftime('%Y-%m-%d') if estimate.valid_until else None,
            "notes": estimate.notes,
            "terms": estimate.terms,
            "created_at": estimate.created_at.strftime('%Y-%m-%d %H:%M'),
            "items": items_data
        })

    def post(self, request, estimate_id):
        return self.patch(request, estimate_id)

    def patch(self, request, estimate_id):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
        if denied:
            return denied

        estimate = get_object_or_404(Estimate, id=estimate_id)
        scope = get_request_scope(request)
        if scope.company and estimate.company and estimate.company != scope.company:
            return Response({"error": "Estimate not found."}, status=404)
        data = request.data
        raw_user = get_authenticated_user(request) or (request.user if hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False) else None)
        user = raw_user if (raw_user and getattr(raw_user, 'pk', None)) else None

        # 1. Action: Status change (Accept, Reject, Expire, Cancel)
        new_status = data.get('status')
        if new_status and new_status != estimate.status:
            allowed_statuses = ['Draft', 'Sent', 'Accepted', 'Rejected', 'Expired', 'Converted', 'Partially Converted', 'Cancelled']
            if new_status not in allowed_statuses:
                return Response({"error": f"Invalid status: {new_status}"}, status=400)

            estimate.status = new_status
            estimate.status_updated_by = user
            estimate.status_updated_at = timezone.now()
            if data.get('notes'):
                estimate.notes = f"{estimate.notes}\n[{timezone.now().strftime('%Y-%m-%d')}]: Status changed to {new_status}"
            estimate.save()
            return Response({"message": f"Estimate status updated to {new_status}", "status": estimate.status})

        # 2. Action: Create an authorized revision (Preserve historical version)
        if data.get('create_revision') or data.get('action') == 'revise':
            with transaction.atomic():
                rev_num = f"{estimate.estimate_number}-R{estimate.version + 1}"
                new_version = estimate.version + 1
                revised_items = data.get('items', [])

                rev_estimate = Estimate.objects.create(
                    company=estimate.company,
                    branch=estimate.branch,
                    patient=estimate.patient,
                    doctor=estimate.doctor,
                    treatment_plan=estimate.treatment_plan,
                    estimate_number=rev_num,
                    version=new_version,
                    parent_estimate=estimate,
                    status='Draft',
                    valid_until=estimate.valid_until,
                    notes=data.get('notes', f"Revision of {estimate.estimate_number}"),
                    terms=estimate.terms,
                    created_by=user if (user and getattr(user, 'pk', None)) else None
                )

                subtotal = Decimal('0.00')
                disc_total = Decimal('0.00')

                for it in revised_items:
                    proc_name = it.get('procedure_name') or 'Procedure'
                    tooth_num = str(it.get('tooth_number') or '')
                    surf = str(it.get('surface') or 'All')
                    qty = int(it.get('quantity') or 1)
                    u_price = Decimal(str(it.get('unit_price') or 0))
                    disc = Decimal(str(it.get('discount') or 0))
                    std_price = Decimal(str(it.get('standard_price') or u_price))
                    line_tot = max(Decimal('0.00'), (u_price * qty) - disc)

                    EstimateItem.objects.create(
                        estimate=rev_estimate,
                        plan_item_id=it.get('plan_item_id'),
                        treatment_master_id=it.get('treatment_master_id'),
                        tooth_number=tooth_num,
                        surface=surf,
                        procedure_name=proc_name,
                        quantity=qty,
                        billed_quantity=0,
                        standard_price=std_price,
                        unit_price=u_price,
                        discount=disc,
                        total_amount=line_tot,
                        status='Pending'
                    )
                    subtotal += (u_price * qty)
                    disc_total += disc

                rev_estimate.subtotal = subtotal
                rev_estimate.discount = disc_total
                rev_estimate.grand_total = max(Decimal('0.00'), subtotal - disc_total)
                rev_estimate.save()

                return Response({
                    "message": "Revised estimate created",
                    "id": rev_estimate.id,
                    "estimate_number": rev_estimate.estimate_number,
                    "new_estimate_id": rev_estimate.id,
                    "new_estimate_number": rev_estimate.estimate_number,
                    "version": rev_estimate.version
                }, status=status.HTTP_201_CREATED)

        return Response({"message": "No changes applied"})


class EstimatePDFView(APIView):
    """
    Generates an official Estimate / Quotation PDF with dynamic company & branch branding.
    """
    def get(self, request, estimate_id):
        estimate = get_object_or_404(Estimate, id=estimate_id)
        branding = get_clinic_branding(estimate.company, estimate.branch)

        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header Clinic Details (Dynamic, never hardcoded)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, branding["title"])
        p.setFont("Helvetica", 9)
        p.setFillColorRGB(0.3, 0.3, 0.3)
        p.drawString(50, height - 65, branding["address"])
        p.drawString(50, height - 78, branding["contact"])

        p.setFont("Helvetica-Bold", 11)
        p.setFillColorRGB(0.06, 0.72, 0.5) # Brand Teal
        p.drawString(420, height - 50, "TREATMENT ESTIMATE")
        p.setFont("Helvetica", 9)
        p.setFillColorRGB(0.2, 0.2, 0.2)
        p.drawString(420, height - 65, f"Est #: {estimate.estimate_number}")
        p.drawString(420, height - 78, f"Date: {estimate.created_at.strftime('%d %b %Y')}")
        p.drawString(420, height - 91, f"Status: {estimate.status.upper()}")

        p.setStrokeColorRGB(0.85, 0.85, 0.85)
        p.line(50, height - 102, 545, height - 102)

        # Patient & Doctor Info
        p.setFont("Helvetica-Bold", 10)
        p.setFillColorRGB(0.1, 0.1, 0.1)
        p.drawString(50, height - 120, f"PATIENT: {estimate.patient.name.upper()}")
        p.setFont("Helvetica", 9)
        p.setFillColorRGB(0.3, 0.3, 0.3)
        p.drawString(50, height - 134, f"Phone: {estimate.patient.phone or 'N/A'} | ID: #{estimate.patient.id}")
        p.drawString(50, height - 148, f"Age/Gender: {estimate.patient.age or 'N/A'} yrs / {estimate.patient.gender or 'N/A'}")

        p.setFont("Helvetica-Bold", 10)
        p.setFillColorRGB(0.1, 0.1, 0.1)
        doc_name = estimate.doctor.name if estimate.doctor else "Doctor not assigned"
        p.drawString(320, height - 120, f"TREATING DOCTOR: Dr. {doc_name}")
        p.setFont("Helvetica", 9)
        p.setFillColorRGB(0.3, 0.3, 0.3)
        valid_date_str = estimate.valid_until.strftime('%d %b %Y') if estimate.valid_until else "30 days from issue"
        p.drawString(320, height - 134, f"Estimate Valid Until: {valid_date_str}")

        # Items Table Header
        y = height - 180
        p.setFillColorRGB(0.96, 0.97, 0.98)
        p.rect(50, y - 5, 495, 20, fill=1, stroke=0)
        p.setFillColorRGB(0.1, 0.1, 0.1)
        p.setFont("Helvetica-Bold", 9)
        p.drawString(55, y, "#")
        p.drawString(75, y, "Tooth")
        p.drawString(120, y, "Procedure / Treatment")
        p.drawString(320, y, "Qty")
        p.drawString(350, y, "Std Rate")
        p.drawString(410, y, "Est Rate")
        p.drawString(480, y, "Total (Rs. )")

        p.setFont("Helvetica", 9)
        p.setFillColorRGB(0.2, 0.2, 0.2)
        y -= 20

        idx = 1
        for it in estimate.items.all():
            tooth_display = f"#{it.tooth_number}" if it.tooth_number else "General"
            p.drawString(55, y, str(idx))
            p.drawString(75, y, tooth_display)
            p.drawString(120, y, it.procedure_name[:32])
            p.drawString(325, y, str(it.quantity))
            p.drawString(350, y, f"Rs. {float(it.standard_price):.2f}")
            p.drawString(410, y, f"Rs. {float(it.unit_price):.2f}")
            p.drawString(480, y, f"Rs. {float(it.total_amount):.2f}")
            y -= 18
            idx += 1
            if y < 160:
                p.showPage()
                y = height - 60

        # Totals Section
        y -= 10
        p.setStrokeColorRGB(0.85, 0.85, 0.85)
        p.line(320, y + 5, 545, y + 5)

        p.setFont("Helvetica", 9)
        p.drawString(350, y - 10, "Subtotal:")
        p.drawRightString(545, y - 10, f"Rs. {float(estimate.subtotal):.2f}")

        p.drawString(350, y - 24, "Total Discount:")
        p.drawRightString(545, y - 24, f"- Rs. {float(estimate.discount):.2f}")

        p.drawString(350, y - 38, "Applicable Tax:")
        p.drawRightString(545, y - 38, f"+ Rs. {float(estimate.tax):.2f}")

        p.setFont("Helvetica-Bold", 11)
        p.drawString(350, y - 56, "Grand Total:")
        p.drawRightString(545, y - 56, f"Rs. {float(estimate.grand_total):.2f}")

        # Terms & Disclaimer
        p.setFont("Helvetica-Bold", 8)
        p.setFillColorRGB(0.4, 0.4, 0.4)
        p.drawString(50, 90, "TERMS & CONDITIONS:")
        p.setFont("Helvetica", 8)
        p.drawString(50, 78, estimate.terms[:110])
        p.drawString(50, 68, "Actual clinical procedures may vary depending on patient anatomy and clinical findings.")

        # Doctor Signature Line
        p.setStrokeColorRGB(0.7, 0.7, 0.7)
        p.line(400, 75, 540, 75)
        p.setFont("Helvetica", 8)
        p.drawRightString(535, 62, "Doctor's Signature")

        p.showPage()
        p.save()
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Estimate_{estimate.estimate_number}.pdf"'
        return response


class EstimateConvertToBillView(APIView):
    """
    STAGED FINAL BILLING:
    Converts accepted Estimate items into a final Billing invoice.
    Prevents duplicate billing, links completed TreatmentRecords,
    and assigns a sequential branch invoice number.
    """
    def post(self, request, estimate_id):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
        if denied:
            return denied

        estimate = get_object_or_404(Estimate, id=estimate_id)
        scope = get_request_scope(request)
        if scope.company and estimate.company and estimate.company != scope.company:
            return Response({"error": "Estimate not found."}, status=404)
        patient = estimate.patient
        company = scope.company or estimate.company or patient.company
        branch = scope.branch or estimate.branch or patient.registration_branch
        data = request.data

        selected_items = data.get('items', [])
        if not selected_items:
            return Response({"error": "No treatment items selected for billing."}, status=400)

        # Payment options on bill generation
        initial_paid_raw = data.get('paid_amount', 0)
        try:
            initial_paid = Decimal(str(initial_paid_raw or 0))
        except Exception:
            initial_paid = Decimal('0.00')

        payment_method = data.get('payment_method', 'Cash')

        with transaction.atomic():
            # 1. Generate sequential invoice number
            inv_number = AutoNumbering.get_next_sequence('invoice', branch=branch, company=company)

            # 2. Create the Billing Header
            billing = Billing.objects.create(
                company=company,
                branch=branch,
                patient=patient,
                doctor=estimate.doctor,
                estimate=estimate,
                invoice_number=inv_number,
                bill_type='Clinical',
                is_invoice=True,
                payment_method=payment_method,
                notes=data.get('notes', f"Billed from Estimate #{estimate.estimate_number}")
            )

            total_bill = Decimal('0.00')
            subtotal_bill = Decimal('0.00')
            disc_bill = Decimal('0.00')

            # 3. Process each selected estimate item
            for sel in selected_items:
                est_item_id = sel.get('estimate_item_id') or sel.get('id')
                est_item = EstimateItem.objects.filter(id=est_item_id, estimate=estimate).first()
                if not est_item:
                    continue

                # Quantity validation for staged billing
                requested_qty = int(sel.get('quantity') or 1)
                remaining_qty = est_item.quantity - est_item.billed_quantity
                if remaining_qty <= 0:
                    return Response({"error": f"Item '{est_item.procedure_name}' is already fully billed."}, status=400)

                qty_to_bill = min(requested_qty, remaining_qty)
                unit_price = Decimal(str(sel.get('unit_price') or est_item.unit_price))
                item_disc = Decimal(str(sel.get('discount') or 0))
                line_total = max(Decimal('0.00'), (unit_price * qty_to_bill) - item_disc)

                # Link to existing TreatmentRecord if provided (NO duplicate creation)
                tr_id = sel.get('treatment_record_id')
                tr = TreatmentRecord.objects.filter(id=tr_id).first() if tr_id else None

                # Resolve treatment master or fallback
                tm = est_item.treatment_master
                if not tm and est_item.procedure_name:
                    tm = TreatmentMaster.objects.filter(name__iexact=est_item.procedure_name).first()

                BillingItem.objects.create(
                    billing=billing,
                    estimate_item=est_item,
                    treatment=tm,
                    treatment_record=tr,
                    tooth_number=est_item.tooth_number,
                    qty=qty_to_bill,
                    price=unit_price,
                    standard_price_snapshot=est_item.standard_price,
                    discount=item_disc,
                    price_override_reason=sel.get('price_override_reason')
                )

                # Update staged progress on EstimateItem
                est_item.billed_quantity += qty_to_bill
                if est_item.billed_quantity >= est_item.quantity:
                    est_item.status = 'Billed'
                else:
                    est_item.status = 'Partially Billed'
                est_item.save()

                subtotal_bill += (unit_price * qty_to_bill)
                disc_bill += item_disc
                total_bill += line_total

            # Update parent Estimate status
            all_est_items = estimate.items.all()
            if all(i.status == 'Billed' for i in all_est_items):
                estimate.status = 'Converted'
            else:
                estimate.status = 'Partially Converted'
            estimate.save()

            # Finalize billing amounts
            billing.subtotal = subtotal_bill
            billing.discount_total = disc_bill
            billing.total_amount = total_bill
            billing.paid_amount = min(initial_paid, total_bill) if total_bill > 0 else initial_paid
            billing.balance_amount = max(Decimal('0.00'), total_bill - billing.paid_amount)
            billing.save()

            # Record initial payment ledger receipt if paid > 0
            if billing.paid_amount > 0:
                rcp_number = AutoNumbering.get_next_sequence('receipt', branch=branch, company=company)
                BillPayment.objects.create(
                    billing=billing,
                    patient=patient,
                    company=company,
                    branch=branch,
                    receipt_number=rcp_number,
                    amount=billing.paid_amount,
                    payment_method=payment_method,
                    transaction_reference=data.get('transaction_reference', ''),
                    payment_type='Payment',
                    notes="Payment on invoice generation",
                    received_by=request.user if (hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False) and getattr(request.user, 'pk', None)) else None
                )

                # Financial transaction log
                Transaction.objects.create(
                    company=company,
                    branch=branch,
                    type='Income',
                    amount=billing.paid_amount,
                    category='Patient Payment',
                    patient=patient,
                    doctor=estimate.doctor,
                    payment_method=payment_method,
                    notes=f"Receipt {rcp_number} for Invoice {inv_number}"
                )

        return Response({
            "message": "Final bill generated successfully",
            "bill_id": billing.id,
            "billing_id": billing.id,
            "invoice_number": billing.invoice_number,
            "total_amount": float(billing.total_amount),
            "paid_amount": float(billing.paid_amount),
            "balance_amount": float(billing.balance_amount),
            "estimate_status": estimate.status
        }, status=status.HTTP_201_CREATED)


class BillPaymentCreateView(APIView):
    """
    Records an auditable payment or advance adjustment against a Bill.
    Generates an official receipt and updates the billing ledger.
    """
    def get(self, request, billing_id=None, bill_id=None, *args, **kwargs):
        scope = get_request_scope(request)
        if not scope.is_authenticated:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

        bid = billing_id or bill_id or kwargs.get('billing_id') or kwargs.get('bill_id')
        billing = get_object_or_404(Billing, id=bid)

        if not scope.is_super:
            if not scope.company or (billing.company_id and billing.company_id != scope.company.id):
                return Response({"detail": "You do not have permission to view payments for this invoice."}, status=status.HTTP_403_FORBIDDEN)
            if scope.branch and not scope.is_company_admin:
                if billing.branch_id and not scope.has_access_to_branch(billing.branch_id):
                    return Response({"detail": "You do not have permission to access records for this branch."}, status=status.HTTP_403_FORBIDDEN)

        payments = BillPayment.objects.filter(billing=billing).order_by('-created_at')
        res = []
        for p in payments:
            res.append({
                "id": p.id,
                "receipt_number": p.receipt_number,
                "amount": float(p.amount),
                "payment_method": p.payment_method,
                "payment_type": p.payment_type,
                "transaction_reference": p.transaction_reference,
                "notes": p.notes,
                "created_at": p.created_at.strftime('%Y-%m-%d %H:%M')
            })
        return Response(res)

    def post(self, request, billing_id=None, bill_id=None, *args, **kwargs):
        denied = require_role(request, ['Admin', 'Doctor', 'Receptionist'])
        if denied:
            return denied

        scope = get_request_scope(request)
        if not scope.is_authenticated:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

        bid = billing_id or bill_id or kwargs.get('billing_id') or kwargs.get('bill_id')
        billing = get_object_or_404(Billing, id=bid)

        if not scope.is_super:
            if not scope.company or (billing.company_id and billing.company_id != scope.company.id):
                return Response({"detail": "You do not have permission to record payments for this invoice."}, status=status.HTTP_403_FORBIDDEN)
            if scope.branch and not scope.is_company_admin:
                if billing.branch_id and not scope.has_access_to_branch(billing.branch_id):
                    return Response({"detail": "You do not have permission to access records for this branch."}, status=status.HTTP_403_FORBIDDEN)

        company = scope.company or billing.company
        branch = scope.branch or billing.branch
        data = request.data

        try:
            amount = Decimal(str(data.get('amount') or 0))
        except Exception:
            return Response({"error": "Invalid payment amount"}, status=400)

        if amount <= Decimal('0.00'):
            return Response({"error": "Payment amount must be greater than zero."}, status=400)

        payment_method = data.get('payment_method', 'Cash')
        payment_type = data.get('payment_type', 'Payment') # Payment, Advance, Refund
        tx_ref = data.get('transaction_reference', '')
        notes = data.get('notes', '')

        with transaction.atomic():
            rcp_number = AutoNumbering.get_next_sequence('receipt', branch=branch, company=company)
            payment_record = BillPayment.objects.create(
                billing=billing,
                patient=billing.patient,
                company=company,
                branch=branch,
                receipt_number=rcp_number,
                amount=amount,
                payment_method=payment_method,
                transaction_reference=tx_ref,
                payment_type=payment_type,
                notes=notes,
                received_by=request.user if (hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False) and getattr(request.user, 'pk', None)) else None
            )

            # Update bill balance
            if payment_type == 'Refund':
                billing.paid_amount = max(Decimal('0.00'), billing.paid_amount - amount)
            else:
                billing.paid_amount += amount

            billing.balance_amount = max(Decimal('0.00'), billing.total_amount - billing.paid_amount)
            if billing.paid_amount >= billing.total_amount:
                billing.status = 'Paid'
            elif billing.paid_amount > Decimal('0.00'):
                billing.status = 'Partial'
            else:
                billing.status = 'Pending'
            billing.save()

            # Record in general finance ledger
            Transaction.objects.create(
                company=company,
                branch=branch,
                type='Expense' if payment_type == 'Refund' else 'Income',
                amount=amount,
                category='Patient Payment',
                patient=billing.patient,
                doctor=billing.doctor,
                payment_method=payment_method,
                notes=f"Receipt {rcp_number} for Invoice {billing.invoice_number or billing.id}"
            )

        return Response({
            "message": "Payment recorded successfully",
            "payment_id": payment_record.id,
            "receipt_number": payment_record.receipt_number,
            "amount": float(payment_record.amount),
            "total_paid": float(billing.paid_amount),
            "remaining_balance": float(billing.balance_amount),
            "bill_status": billing.status,
            "bill": {
                "id": billing.id,
                "paid_amount": float(billing.paid_amount),
                "balance_amount": float(billing.balance_amount),
                "status": billing.status
            }
        }, status=status.HTTP_201_CREATED)


class BillReceiptPDFView(APIView):
    """
    Generates an official Payment Receipt PDF for an individual transaction.
    """
    def get(self, request, receipt_id=None, payment_id=None, *args, **kwargs):
        rid = receipt_id or payment_id or kwargs.get('receipt_id') or kwargs.get('payment_id')
        receipt = get_object_or_404(BillPayment, id=rid)
        branding = get_clinic_branding(receipt.company, receipt.branch)

        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Header Clinic Details
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, branding["title"])
        p.setFont("Helvetica", 9)
        p.setFillColorRGB(0.3, 0.3, 0.3)
        p.drawString(50, height - 65, branding["address"])
        p.drawString(50, height - 78, branding["contact"])

        p.setFont("Helvetica-Bold", 12)
        p.setFillColorRGB(0.06, 0.72, 0.5)
        p.drawString(420, height - 50, "PAYMENT RECEIPT")
        p.setFont("Helvetica", 9)
        p.setFillColorRGB(0.2, 0.2, 0.2)
        p.drawString(420, height - 65, f"Receipt #: {receipt.receipt_number}")
        p.drawString(420, height - 78, f"Date: {receipt.created_at.strftime('%d %b %Y %I:%M %p')}")

        p.setStrokeColorRGB(0.85, 0.85, 0.85)
        p.line(50, height - 90, 545, height - 90)

        # Receipt Body
        p.setFont("Helvetica-Bold", 10)
        p.drawString(60, height - 115, f"Received With Thanks From: {receipt.patient.name.upper()}")
        p.setFont("Helvetica", 9)
        p.drawString(60, height - 130, f"Patient Phone: {receipt.patient.phone or 'N/A'} | ID: #{receipt.patient.id}")
        p.drawString(60, height - 145, f"Invoice Number: {receipt.billing.invoice_number or ('INV-' + str(receipt.billing.id)[:8])}")

        p.setFillColorRGB(0.96, 0.97, 0.98)
        p.rect(60, height - 215, 475, 55, fill=1, stroke=0)
        p.setFillColorRGB(0.1, 0.1, 0.1)

        p.setFont("Helvetica", 10)
        p.drawString(75, height - 180, "Amount Received:")
        p.setFont("Helvetica-Bold", 14)
        p.setFillColorRGB(0.06, 0.72, 0.5)
        p.drawString(220, height - 180, f"Rs. {float(receipt.amount):.2f}")

        p.setFont("Helvetica", 9)
        p.setFillColorRGB(0.3, 0.3, 0.3)
        p.drawString(75, height - 200, f"Mode: {receipt.payment_method}  |  Ref/Txn ID: {receipt.transaction_reference or 'N/A'}")

        # Ledger Balance Box
        p.setFont("Helvetica", 9)
        p.drawString(75, height - 240, f"Bill Total: Rs. {float(receipt.billing.total_amount):.2f}")
        p.drawString(220, height - 240, f"Total Paid To Date: Rs. {float(receipt.billing.paid_amount):.2f}")
        p.drawString(380, height - 240, f"Remaining Balance: Rs. {float(receipt.billing.balance_amount):.2f}")

        # Authorized Signature
        p.setStrokeColorRGB(0.7, 0.7, 0.7)
        p.line(390, height - 320, 530, height - 320)
        p.drawRightString(525, height - 335, "Authorized Signatory")

        p.showPage()
        p.save()
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Receipt_{receipt.receipt_number}.pdf"'
        return response


class PatientUnbilledTreatmentsView(APIView):
    """
    Returns unbilled treatment items for a patient (both accepted EstimateItems and completed TreatmentRecords).
    Used for 1-click staged billing.
    """
    def get(self, request, patient_id):
        scope = get_request_scope(request)
        if not scope.is_authenticated:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

        patient = get_object_or_404(Patient, id=patient_id)

        if not scope.is_super:
            if not scope.company or (patient.company_id and patient.company_id != scope.company.id):
                return Response({"detail": "You do not have permission to view unbilled treatments for this patient."}, status=status.HTTP_403_FORBIDDEN)
            if scope.branch and not scope.is_company_admin:
                if patient.registration_branch_id and not scope.has_access_to_branch(patient.registration_branch_id):
                    return Response({"detail": "You do not have permission to access records for this branch."}, status=status.HTTP_403_FORBIDDEN)

        # 1. Accepted Estimate Items with unbilled quantity
        est_items_qs = EstimateItem.objects.filter(
            estimate__patient=patient,
            estimate__status__in=['Accepted', 'Partially Converted']
        ).exclude(status='Billed')

        estimate_candidates = []
        for it in est_items_qs:
            rem = max(0, it.quantity - it.billed_quantity)
            if rem > 0:
                estimate_candidates.append({
                    "estimate_id": it.estimate_id,
                    "estimate_number": it.estimate.estimate_number,
                    "estimate_item_id": it.id,
                    "tooth_number": it.tooth_number,
                    "procedure_name": it.procedure_name,
                    "total_quantity": it.quantity,
                    "billed_quantity": it.billed_quantity,
                    "remaining_quantity": rem,
                    "unit_price": float(it.unit_price),
                    "standard_price": float(it.standard_price),
                    "discount": float(it.discount),
                    "total_amount": float(it.total_amount)
                })

        # 2. Executed Treatment Records not yet billed
        billed_tr_ids = set(BillingItem.objects.filter(billing__patient=patient).exclude(treatment_record__isnull=True).values_list('treatment_record_id', flat=True))
        records_qs = TreatmentRecord.objects.filter(visit__patient=patient, status='Completed').exclude(id__in=billed_tr_ids).order_by('-visit__created_at')

        record_candidates = []
        for r in records_qs:
            record_candidates.append({
                "treatment_record_id": r.id,
                "tooth_number": r.tooth_number or "General",
                "procedure_name": r.treatment.name if r.treatment else "Procedure",
                "price": float(r.price),
                "quantity": r.quantity,
                "date": r.visit.created_at.strftime('%Y-%m-%d') if r.visit else "Past Visit",
                "doctor": r.doctor.name if r.doctor else "Doctor not assigned"
            })

        return Response({
            "estimate_items": estimate_candidates,
            "treatment_records": record_candidates
        })
