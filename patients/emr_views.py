import io
import datetime
from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas

from .models import (
    Patient, Appointment, Visit, ClinicalNotes, TreatmentRecord, TreatmentMaster,
    Prescription, PrescriptionItem, PatientInvestigation, InvestigationAttachment,
    ClinicProfile, Company, Branch, Doctor,
    ToothConditionRecord, TreatmentPlan, TreatmentPlanItem, TreatmentSession, EMRChangeLog
)


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print exact 'Page X of Y' in footer.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        
        # Bottom rule
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(40, 36, 555, 36)
        
        # Left footer: Confidentiality notice
        self.drawString(40, 24, "CONFIDENTIAL - ASHDENT ELECTRONIC MEDICAL RECORD (EMR) - FOR CLINICAL USE ONLY")
        # Right footer: Page numbers
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(555, 24, page_str)
        self.restoreState()


class PatientToothConditionsView(APIView):
    """
    Retrieves or updates tooth conditions for a patient's odontogram chart.
    """
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        records = ToothConditionRecord.objects.filter(patient=patient, is_active=True).order_by('tooth_number')
        
        chart_dict = {}
        items = []
        for r in records:
            cond_data = {
                "tooth_number": r.tooth_number,
                "condition": r.condition or [],
                "surfaces": r.surfaces or [],
                "examination": r.examination or [],
                "diagnosis": r.diagnosis or [],
                "treatments_suggested": r.treatments_suggested or [],
                "mobility": r.mobility or "",
                "pocket_depth": r.pocket_depth or "",
                "furcation": r.furcation or "",
                "plaque_index": r.plaque_index or "",
                "notes": r.notes or "",
                "updated_at": r.updated_at.isoformat() if r.updated_at else None
            }
            chart_dict[str(r.tooth_number)] = cond_data
            items.append(cond_data)

        # Fallback to latest ClinicalNotes if no structured ToothConditionRecord yet exists
        if not chart_dict:
            latest_note = ClinicalNotes.objects.filter(appointment__patient=patient).order_by('-created_at').first()
            if latest_note and latest_note.chart_conditions:
                for t_num, cond in latest_note.chart_conditions.items():
                    c_list = cond if isinstance(cond, list) else [cond]
                    chart_dict[str(t_num)] = {
                        "tooth_number": int(t_num) if str(t_num).isdigit() else t_num,
                        "condition": c_list,
                        "surfaces": [],
                        "examination": [],
                        "diagnosis": [],
                        "treatments_suggested": []
                    }

        return Response({
            "patient_id": patient.id,
            "chart_conditions": chart_dict,
            "items": items
        })

    def post(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        teeth_data = request.data.get('teeth_data', {})
        appointment_id = request.data.get('appointment_id')
        visit_id = request.data.get('visit_id')

        appointment = Appointment.objects.filter(id=appointment_id).first() if appointment_id else None
        visit = Visit.objects.filter(id=visit_id).first() if visit_id else (appointment.visit if appointment and hasattr(appointment, 'visit') else None)

        saved_records = []
        # teeth_data can be { "13": { "condition": [...], "surfaces": [...] } } or { "13": "Decayed" }
        for t_str, data in teeth_data.items():
            try:
                t_num = int(t_str)
            except ValueError:
                continue

            cond = []
            surfaces = []
            exam = []
            diag = []
            tx_sugg = []
            mobility = ""
            pocket_depth = ""
            furcation = ""
            plaque_index = ""
            notes = ""

            if isinstance(data, dict):
                cond_val = data.get('condition', [])
                cond = cond_val if isinstance(cond_val, list) else ([cond_val] if cond_val else [])
                surf_val = data.get('surfaces', [])
                surfaces = surf_val if isinstance(surf_val, list) else ([surf_val] if surf_val else [])
                exam_val = data.get('examination', [])
                exam = exam_val if isinstance(exam_val, list) else ([exam_val] if exam_val else [])
                diag_val = data.get('diagnosis', [])
                diag = diag_val if isinstance(diag_val, list) else ([diag_val] if diag_val else [])
                tx_val = data.get('treatments_suggested', [])
                tx_sugg = tx_val if isinstance(tx_val, list) else ([tx_val] if tx_val else [])
                mobility = data.get('mobility', '')
                pocket_depth = data.get('pocket_depth', '')
                furcation = data.get('furcation', '')
                plaque_index = data.get('plaque_index', '')
                notes = data.get('notes', '')
            elif isinstance(data, list):
                cond = data
            elif isinstance(data, str) and data:
                cond = [data]

            record, _ = ToothConditionRecord.objects.update_or_create(
                patient=patient,
                tooth_number=t_num,
                defaults={
                    "visit": visit,
                    "appointment": appointment,
                    "condition": cond,
                    "surfaces": surfaces,
                    "examination": exam,
                    "diagnosis": diag,
                    "treatments_suggested": tx_sugg,
                    "mobility": mobility,
                    "pocket_depth": pocket_depth,
                    "furcation": furcation,
                    "plaque_index": plaque_index,
                    "notes": notes,
                    "is_active": True
                }
            )
            saved_records.append(record.tooth_number)

        # Also sync snapshot into ClinicalNotes if appointment provided
        if appointment:
            cn, _ = ClinicalNotes.objects.get_or_create(appointment=appointment)
            chart_snap = cn.chart_conditions or {}
            for t_str, data in teeth_data.items():
                if isinstance(data, dict):
                    chart_snap[str(t_str)] = data.get('condition', [])
                else:
                    chart_snap[str(t_str)] = data
            cn.chart_conditions = chart_snap
            cn.save()

        # Audit log
        EMRChangeLog.objects.create(
            patient=patient,
            entity_type="ToothConditionRecord",
            entity_id=f"batch-{patient.id}",
            action="UPDATE",
            changed_by=request.user if request.user.is_authenticated else None,
            changes={"updated_teeth": saved_records}
        )

        return Response({"message": f"Saved conditions for {len(saved_records)} teeth", "teeth": saved_records})


class TreatmentPlanListCreateView(APIView):
    """
    CRUD for Treatment Plans and their nested Plan Items.
    Permanent database persistence replacing browser localStorage.
    """
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        plans = TreatmentPlan.objects.filter(patient=patient).prefetch_related('items').order_by('-created_at')

        results = []
        for p in plans:
            items_data = []
            for item in p.items.all():
                items_data.append({
                    "id": item.id,
                    "tooth": item.tooth_number,
                    "tooth_number": item.tooth_number,
                    "surface": item.surface,
                    "surfaces": item.surface,
                    "diagnosis": item.diagnosis,
                    "procedure": item.procedure_name,
                    "procedure_name": item.procedure_name,
                    "treatment_master_id": item.treatment_master_id,
                    "priority": item.priority,
                    "cost": str(item.estimated_cost),
                    "estimated_cost": float(item.estimated_cost),
                    "discount": float(item.discount),
                    "finalAmount": str(item.final_cost),
                    "final_cost": float(item.final_cost),
                    "visits": item.estimated_visits,
                    "status": item.status,
                    "notes": item.notes,
                    "description": item.description,
                    "created_at": item.created_at.strftime('%Y-%m-%d')
                })

            results.append({
                "id": p.id,
                "title": p.title,
                "status": p.status,
                "total_estimated_cost": float(p.total_estimated_cost),
                "doctor_name": p.doctor.name if p.doctor else "Unassigned",
                "notes": p.notes,
                "created_at": p.created_at.strftime('%Y-%m-%d %H:%M'),
                "items": items_data
            })

        return Response(results)

    def post(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        data = request.data

        plan_id = data.get('plan_id')
        title = data.get('title', 'Comprehensive Dental Treatment Plan')
        plan_status = data.get('status', 'Proposed')
        notes = data.get('notes', '')
        items = data.get('items', [])
        doctor_id = data.get('doctor_id') or (patient.doctor_id if patient.doctor else None)
        doctor = Doctor.objects.filter(id=doctor_id).first() if doctor_id else None

        if plan_id:
            plan = get_object_or_404(TreatmentPlan, id=plan_id, patient=patient)
            plan.title = title
            plan.status = plan_status
            plan.notes = notes
            if doctor:
                plan.doctor = doctor
            plan.save()
        else:
            plan = TreatmentPlan.objects.create(
                patient=patient,
                doctor=doctor,
                company=patient.company,
                branch=patient.registration_branch,
                title=title,
                status=plan_status,
                notes=notes
            )

        # Clear existing items if full sync requested
        replace_items = data.get('replace_items', True)
        if replace_items:
            plan.items.all().delete()

        total_cost = Decimal('0.00')
        created_items = []
        for it in items:
            proc_name = it.get('procedure') or it.get('procedure_name') or 'Dental Procedure'
            tooth_num = str(it.get('tooth') or it.get('tooth_number') or '')
            surf = str(it.get('surface') or it.get('surfaces') or 'All')
            diag = str(it.get('diagnosis') or '')
            priority = it.get('priority') or 'Routine'
            
            raw_cost = it.get('cost') or it.get('estimated_cost') or 0
            try:
                est_cost = Decimal(str(raw_cost or 0))
            except Exception:
                est_cost = Decimal('0.00')

            raw_disc = it.get('discount') or 0
            try:
                disc = Decimal(str(raw_disc or 0))
            except Exception:
                disc = Decimal('0.00')

            raw_final = it.get('finalAmount') or it.get('final_cost') or (est_cost - disc)
            try:
                final_c = Decimal(str(raw_final or (est_cost - disc)))
            except Exception:
                final_c = max(Decimal('0.00'), est_cost - disc)

            visits_cnt = int(it.get('visits') or 1)
            item_status = it.get('status') or 'Proposed'
            it_notes = str(it.get('notes') or '')
            it_desc = str(it.get('description') or '')

            # Link treatment master if matching name
            tm = TreatmentMaster.objects.filter(name__iexact=proc_name).first()

            item_obj = TreatmentPlanItem.objects.create(
                plan=plan,
                tooth_number=tooth_num,
                surface=surf,
                diagnosis=diag,
                procedure_name=proc_name,
                treatment_master=tm,
                priority=priority,
                estimated_cost=est_cost,
                discount=disc,
                final_cost=final_c,
                estimated_visits=visits_cnt,
                status=item_status,
                notes=it_notes,
                description=it_desc
            )
            total_cost += final_c
            created_items.append(item_obj.id)

        plan.total_estimated_cost = total_cost
        plan.save()

        # Audit log
        EMRChangeLog.objects.create(
            patient=patient,
            entity_type="TreatmentPlan",
            entity_id=str(plan.id),
            action="UPDATE" if plan_id else "CREATE",
            changed_by=request.user if request.user.is_authenticated else None,
            changes={"items_count": len(created_items), "total_cost": str(total_cost)}
        )

        return Response({
            "message": "Treatment plan saved successfully",
            "plan_id": plan.id,
            "total_estimated_cost": float(total_cost),
            "items_count": len(created_items)
        }, status=status.HTTP_201_CREATED if not plan_id else status.HTTP_200_OK)


class TreatmentPlanItemUpdateView(APIView):
    """
    Updates a single TreatmentPlanItem's status or converts it into a performed TreatmentRecord.
    """
    def patch(self, request, item_id):
        item = get_object_or_404(TreatmentPlanItem, id=item_id)
        new_status = request.data.get('status')
        new_priority = request.data.get('priority')
        new_notes = request.data.get('notes')
        new_cost = request.data.get('cost') or request.data.get('final_cost')

        if new_status:
            item.status = new_status
        if new_priority:
            item.priority = new_priority
        if new_notes is not None:
            item.notes = new_notes
        if new_cost is not None:
            try:
                item.final_cost = Decimal(str(new_cost))
            except Exception:
                pass

        item.save()

        # Update parent plan total and status
        plan = item.plan
        all_items = plan.items.all()
        if all(i.status == 'Completed' for i in all_items):
            plan.status = 'Completed'
        elif any(i.status in ['In Progress', 'Completed'] for i in all_items):
            plan.status = 'In Progress'
        elif any(i.status == 'Accepted' for i in all_items):
            plan.status = 'Accepted'
        plan.save()

        return Response({"message": "Plan item updated", "id": item.id, "status": item.status})


class ConvertPlanItemToTreatmentRecordView(APIView):
    """
    Executes a recommended treatment item, creating an official TreatmentRecord.
    """
    def post(self, request, item_id):
        item = get_object_or_404(TreatmentPlanItem, id=item_id)
        plan = item.plan
        patient = plan.patient

        visit_id = request.data.get('visit_id')
        doctor_id = request.data.get('doctor_id') or (plan.doctor_id if plan.doctor else None)
        notes = request.data.get('notes', item.notes or '')
        tx_status = request.data.get('status', 'Completed')

        doctor = Doctor.objects.filter(id=doctor_id).first() if doctor_id else patient.doctor

        visit = None
        if visit_id:
            visit = Visit.objects.filter(id=visit_id).first()
        if not visit:
            latest_appt = Appointment.objects.filter(patient=patient).order_by('-date').first()
            if latest_appt and hasattr(latest_appt, 'visit'):
                visit = latest_appt.visit
            elif latest_appt:
                visit = Visit.objects.create(patient=patient, appointment=latest_appt, company=patient.company, branch=patient.registration_branch)
            else:
                appt = Appointment.objects.create(
                    patient=patient,
                    doctor=doctor,
                    date=timezone.now().date(),
                    time=timezone.now().time(),
                    status='Completed',
                    company=patient.company,
                    branch=patient.registration_branch
                )
                visit = Visit.objects.create(patient=patient, appointment=appt, company=patient.company, branch=patient.registration_branch)

        # Match or create TreatmentMaster
        tm = item.treatment_master
        if not tm:
            tm, _ = TreatmentMaster.objects.get_or_create(
                name=item.procedure_name,
                defaults={"price": item.final_cost or item.estimated_cost, "fee_type": "Treatment"}
            )

        tr = TreatmentRecord.objects.create(
            visit=visit,
            treatment=tm,
            tooth_number=item.tooth_number,
            price=item.final_cost or item.estimated_cost or tm.price,
            fee_type="Treatment",
            notes=notes,
            status=tx_status,
            doctor=doctor
        )

        item.status = tx_status
        item.save()

        # If it requires multiple sessions, initialize Session #1
        if item.estimated_visits > 1 or request.data.get('multi_session'):
            TreatmentSession.objects.create(
                treatment_record=tr,
                plan_item=item,
                patient=patient,
                visit=visit,
                doctor=doctor,
                session_number=1,
                session_date=timezone.now().date(),
                procedure_performed=f"Session 1: {item.procedure_name} initiated",
                clinical_notes=notes,
                status="Completed" if tx_status == "Completed" else "In Progress"
            )

        return Response({
            "message": "Converted to treatment record successfully",
            "treatment_record_id": tr.id,
            "status": tr.status
        }, status=status.HTTP_201_CREATED)


class TreatmentSessionListCreateView(APIView):
    """
    Manages multi-session tracking for treatments (e.g., RCT Session 1, Session 2, Obturation).
    """
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        sessions = TreatmentSession.objects.filter(patient=patient).select_related('doctor', 'treatment_record', 'plan_item').order_by('-session_date', '-session_number')

        results = []
        for s in sessions:
            results.append({
                "id": s.id,
                "treatment_record_id": s.treatment_record_id,
                "plan_item_id": s.plan_item_id,
                "tooth_number": s.treatment_record.tooth_number if s.treatment_record else (s.plan_item.tooth_number if s.plan_item else ""),
                "session_number": s.session_number,
                "session_date": s.session_date.strftime('%Y-%m-%d'),
                "doctor_name": s.doctor.name if s.doctor else "Unassigned",
                "procedure_performed": s.procedure_performed,
                "clinical_notes": s.clinical_notes,
                "materials_used": s.materials_used,
                "next_session_plan": s.next_session_plan,
                "next_session_date": s.next_session_date.strftime('%Y-%m-%d') if s.next_session_date else None,
                "status": s.status
            })
        return Response(results)

    def post(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)
        data = request.data

        tr_id = data.get('treatment_record_id')
        plan_item_id = data.get('plan_item_id')
        tr = TreatmentRecord.objects.filter(id=tr_id).first() if tr_id else None
        plan_item = TreatmentPlanItem.objects.filter(id=plan_item_id).first() if plan_item_id else None

        doctor_id = data.get('doctor_id') or (tr.doctor_id if tr else (patient.doctor_id if patient.doctor else None))
        doctor = Doctor.objects.filter(id=doctor_id).first() if doctor_id else None

        # Determine next session number
        existing_count = TreatmentSession.objects.filter(patient=patient, treatment_record=tr).count() if tr else 0
        session_num = int(data.get('session_number') or (existing_count + 1))

        session_date = data.get('session_date') or timezone.now().date()
        next_date = data.get('next_session_date') or None

        session = TreatmentSession.objects.create(
            treatment_record=tr,
            plan_item=plan_item,
            patient=patient,
            visit=tr.visit if tr else None,
            doctor=doctor,
            session_number=session_num,
            session_date=session_date,
            procedure_performed=data.get('procedure_performed', 'Clinical Treatment Session'),
            clinical_notes=data.get('clinical_notes', ''),
            materials_used=data.get('materials_used', ''),
            next_session_plan=data.get('next_session_plan', ''),
            next_session_date=next_date,
            status=data.get('status', 'Completed')
        )

        return Response({
            "message": "Treatment session recorded",
            "session_id": session.id,
            "session_number": session.session_number
        }, status=status.HTTP_201_CREATED)


class PatientEMRDetailView(APIView):
    """
    Unified full-spectrum EMR API returning all clinical dimensions:
    Demographics, Visits timeline, Clinical Notes, Tooth Conditions, Diagnoses,
    Recommended Treatment Plans, Performed Procedures, Multi-session logs,
    Prescriptions, Investigations, and Follow-ups.
    """
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)

        # 1. Patient Demographics & Profile
        patient_data = {
            "id": patient.id,
            "name": patient.name,
            "phone": patient.phone or "",
            "age": patient.age,
            "gender": patient.gender or "",
            "dob": patient.dob.strftime('%Y-%m-%d') if patient.dob else None,
            "address": patient.address or "",
            "pincode": patient.pincode or "",
            "status": patient.status,
            "registered_at": patient.created_at.strftime('%Y-%m-%d'),
            "primary_doctor": patient.doctor.name if patient.doctor else "Unassigned",
            "branch": patient.registration_branch.name if patient.registration_branch else "Main Clinic",
            "company": patient.company.name if patient.company else "AshDent Health"
        }

        # 2. Tooth Conditions (Active Chart Snapshot)
        tc_qs = ToothConditionRecord.objects.filter(patient=patient, is_active=True).order_by('tooth_number')
        tooth_conditions = []
        for tc in tc_qs:
            tooth_conditions.append({
                "tooth_number": tc.tooth_number,
                "condition": tc.condition or [],
                "surfaces": tc.surfaces or [],
                "examination": tc.examination or [],
                "diagnosis": tc.diagnosis or [],
                "treatments_suggested": tc.treatments_suggested or [],
                "mobility": tc.mobility or "",
                "pocket_depth": tc.pocket_depth or "",
                "notes": tc.notes or ""
            })

        # 3. Treatment Recommendations (Plans & Plan Items)
        plans_qs = TreatmentPlan.objects.filter(patient=patient).prefetch_related('items').order_by('-created_at')
        treatment_plans = []
        for p in plans_qs:
            p_items = []
            for it in p.items.all():
                p_items.append({
                    "id": it.id,
                    "tooth_number": it.tooth_number,
                    "surface": it.surface,
                    "diagnosis": it.diagnosis,
                    "procedure_name": it.procedure_name,
                    "priority": it.priority,
                    "estimated_cost": float(it.estimated_cost),
                    "final_cost": float(it.final_cost),
                    "estimated_visits": it.estimated_visits,
                    "status": it.status,
                    "notes": it.notes
                })
            treatment_plans.append({
                "id": p.id,
                "title": p.title,
                "status": p.status,
                "total_estimated_cost": float(p.total_estimated_cost),
                "created_at": p.created_at.strftime('%Y-%m-%d %H:%M'),
                "doctor": p.doctor.name if p.doctor else "Unassigned",
                "items": p_items
            })

        # 4. Executed Treatments
        records_qs = TreatmentRecord.objects.filter(visit__patient=patient).select_related('treatment', 'doctor', 'visit__appointment').order_by('-visit__created_at')
        performed_treatments = []
        for r in records_qs:
            performed_treatments.append({
                "id": r.id,
                "procedure_name": r.treatment.name if r.treatment else "Procedure",
                "tooth_number": r.tooth_number or "General",
                "price": float(r.price),
                "status": r.status,
                "doctor": r.doctor.name if r.doctor else "Doctor",
                "notes": r.notes or "",
                "date": r.visit.created_at.strftime('%Y-%m-%d') if r.visit else "Past Visit"
            })

        # 5. Multi-session Logs
        sessions_qs = TreatmentSession.objects.filter(patient=patient).select_related('doctor', 'treatment_record').order_by('-session_date')
        treatment_sessions = []
        for s in sessions_qs:
            treatment_sessions.append({
                "id": s.id,
                "session_number": s.session_number,
                "session_date": s.session_date.strftime('%Y-%m-%d'),
                "procedure_performed": s.procedure_performed,
                "tooth_number": s.treatment_record.tooth_number if s.treatment_record else "",
                "clinical_notes": s.clinical_notes,
                "materials_used": s.materials_used,
                "doctor": s.doctor.name if s.doctor else "Doctor",
                "status": s.status,
                "next_session_date": s.next_session_date.strftime('%Y-%m-%d') if s.next_session_date else None
            })

        # 6. Prescriptions
        rx_qs = Prescription.objects.filter(patient=patient).prefetch_related('items').order_by('-created_at')
        prescriptions = []
        for rx in rx_qs:
            meds = []
            for item in rx.items.all():
                meds.append({
                    "name": item.medicine_name,
                    "dosage": item.dosage,
                    "duration": item.duration,
                    "notes": item.notes or "",
                    "quantity": item.quantity
                })
            prescriptions.append({
                "id": rx.id,
                "date": rx.created_at.strftime('%Y-%m-%d'),
                "doctor": rx.doctor.name if rx.doctor else "Doctor",
                "status": rx.status,
                "notes": rx.notes or "",
                "items": meds
            })

        # 7. Investigations
        inv_qs = PatientInvestigation.objects.filter(patient=patient).prefetch_related('attachments').order_by('-investigation_date')
        investigations = []
        for inv in inv_qs:
            atts = []
            for att in inv.attachments.all():
                att_url = ""
                if att.file:
                    try:
                        att_url = request.build_absolute_uri(att.file.url)
                    except Exception:
                        att_url = str(att.file.url)
                atts.append({
                    "id": att.id,
                    "file_name": att.file_name,
                    "file_url": att_url,
                    "file_type": att.file_type or ""
                })
            investigations.append({
                "id": inv.id,
                "name": inv.investigation_name,
                "date": inv.investigation_date.strftime('%Y-%m-%d'),
                "doctor": inv.doctor.name if inv.doctor else "Doctor",
                "status": inv.status,
                "reason": inv.reason or "",
                "findings": inv.findings or "",
                "remarks": inv.remarks or "",
                "attachments": atts
            })

        # 8. Chronological Visit-by-Visit History
        appts = Appointment.objects.filter(patient=patient).order_by('-date')
        visits_timeline = []
        for appt in appts:
            cn = getattr(appt, 'clinical_notes', None)
            v = getattr(appt, 'visit', None)

            # Treatments for this visit
            v_treatments = []
            if v:
                for tr in v.treatment_records.all():
                    v_treatments.append({
                        "id": tr.id,
                        "procedure": tr.treatment.name if tr.treatment else "",
                        "tooth": tr.tooth_number,
                        "status": tr.status,
                        "doctor": tr.doctor.name if tr.doctor else ""
                    })

            # Prescriptions for this visit
            v_prescriptions = []
            if v:
                for rx in v.prescriptions.all():
                    v_prescriptions.append({
                        "id": rx.id,
                        "meds_count": rx.items.count(),
                        "items": [{"name": i.medicine_name, "dosage": i.dosage} for i in rx.items.all()]
                    })

            # Investigations for this appointment
            v_invs = []
            for inv in inv_qs.filter(appointment=appt):
                v_invs.append({
                    "id": inv.id,
                    "name": inv.investigation_name,
                    "status": inv.status,
                    "findings": inv.findings or ""
                })

            visits_timeline.append({
                "appointment_id": appt.id,
                "visit_id": v.id if v else None,
                "date": appt.date.strftime('%Y-%m-%d'),
                "time": appt.time.strftime('%I:%M %p') if appt.time else "",
                "doctor": appt.doctor.name if appt.doctor else "Doctor",
                "status": appt.status,
                "chief_complaint": cn.chief_complaint if cn else "",
                "complaints": cn.complaints if cn else [],
                "observations": cn.observations if cn else [],
                "diagnosis": cn.diagnosis if cn else [],
                "selected_teeth": cn.selected_teeth if cn else [],
                "notes": cn.notes if cn else "",
                "treatment_plan": cn.treatment_plan if cn else "",
                "follow_up_date": cn.follow_up_date.strftime('%Y-%m-%d') if (cn and cn.follow_up_date) else None,
                "follow_up_note": cn.follow_up_note if cn else "",
                "treatments": v_treatments,
                "prescriptions": v_prescriptions,
                "investigations": v_invs
            })

        # Aggregated Medical History / Allergies across patient records
        med_history = []
        allergies = []
        dental_history = []
        for appt in appts:
            cn = getattr(appt, 'clinical_notes', None)
            if cn:
                if cn.medical_history:
                    med_history.extend([m for m in cn.medical_history if m not in med_history])
                if cn.allergies:
                    allergies.extend([a for a in cn.allergies if a not in allergies])
                if cn.dental_history:
                    dental_history.extend([d for d in cn.dental_history if d not in dental_history])

        return Response({
            "patient": patient_data,
            "medical_alerts": {
                "allergies": allergies,
                "medical_history": med_history,
                "dental_history": dental_history
            },
            "tooth_conditions": tooth_conditions,
            "treatment_plans": treatment_plans,
            "performed_treatments": performed_treatments,
            "treatment_sessions": treatment_sessions,
            "prescriptions": prescriptions,
            "investigations": investigations,
            "visits_timeline": visits_timeline
        })


class EMRPDFReportView(APIView):
    """
    ReportLab PDF Generation:
    - Mode A (Lifetime EMR): /api/patients/<patient_id>/emr-report/pdf/
    - Mode B (Individual Visit EMR): /api/patients/<patient_id>/emr-report/pdf/?appointment_id=<id> or ?visit_id=<id>
    """
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, id=patient_id)

        appointment_id = request.query_params.get('appointment_id')
        visit_id = request.query_params.get('visit_id')

        is_visit_mode = bool(appointment_id or visit_id)
        target_appointment = None
        target_visit = None

        if appointment_id:
            target_appointment = Appointment.objects.filter(id=appointment_id, patient=patient).first()
            if target_appointment and hasattr(target_appointment, 'visit'):
                target_visit = target_appointment.visit
        elif visit_id:
            target_visit = Visit.objects.filter(id=visit_id, patient=patient).first()
            if target_visit:
                target_appointment = target_visit.appointment

        # Fetch Clinic Profile branding
        clinic = ClinicProfile.objects.first()
        clinic_name = clinic.name if clinic and clinic.name else "ASHDENT DENTAL SPECIALITY CENTRE"
        clinic_phone = clinic.phone or clinic.mobile if clinic else "+91 98765 43210"
        clinic_email = clinic.email if clinic else "contact@ashdent.clinic"
        clinic_address = clinic.address if clinic else "Healthcare Boulevard, Medical Plaza, Suite 400"
        clinic_slogan = clinic.slogan if clinic else "Advanced Digital Dental Care & Implantology"

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=45
        )

        styles = getSampleStyleSheet()

        # Custom typography styles
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=18,
            textColor=colors.HexColor('#0f172a'),
            alignment=TA_LEFT
        )
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#475569'),
            alignment=TA_LEFT
        )
        report_tag_style = ParagraphStyle(
            'ReportTag',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#1d4ed8'),
            alignment=TA_RIGHT
        )
        meta_right_style = ParagraphStyle(
            'MetaRight',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#64748b'),
            alignment=TA_RIGHT
        )
        section_heading = ParagraphStyle(
            'SectionHeading',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=13,
            textColor=colors.HexColor('#1e3a8a'),
            spaceBefore=8,
            spaceAfter=4
        )
        cell_bold = ParagraphStyle(
            'CellBold',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#0f172a')
        )
        cell_text = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#334155')
        )
        cell_subtext = ParagraphStyle(
            'CellSubtext',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=7,
            leading=9,
            textColor=colors.HexColor('#64748b')
        )

        story = []

        # --- 1. CLINIC HEADER ---
        report_type_title = "VISIT CONSULTATION RECORD" if is_visit_mode else "COMPLETE ELECTRONIC MEDICAL RECORD (EMR)"
        date_str = timezone.now().strftime('%d-%b-%Y %I:%M %p')

        header_data = [
            [
                Paragraph(f"<b>{clinic_name.upper()}</b><br/>{clinic_slogan}<br/>{clinic_address} | Tel: {clinic_phone}<br/>Email: {clinic_email}", subtitle_style),
                Paragraph(f"<b>{report_type_title}</b><br/>Generated: {date_str}<br/>Status: <b>VERIFIED RECORD</b><br/>Clinic ID: ASHDENT-EMR", meta_right_style)
            ]
        ]
        header_table = Table(header_data, colWidths=[330, 193])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563eb'), spaceBefore=2, spaceAfter=8))

        # --- 2. PATIENT DEMOGRAPHICS TABLE ---
        doctor_name = "Unassigned"
        if is_visit_mode and target_appointment and target_appointment.doctor:
            doctor_name = f"Dr. {target_appointment.doctor.name}"
        elif patient.doctor:
            doctor_name = f"Dr. {patient.doctor.name}"

        demo_data = [
            [
                Paragraph("<b>Patient Name:</b>", cell_bold),
                Paragraph(f"<b>{patient.name.upper()}</b>", cell_bold),
                Paragraph("<b>UHID / Patient ID:</b>", cell_bold),
                Paragraph(f"#{patient.id}", cell_bold)
            ],
            [
                Paragraph("<b>Age / Gender:</b>", cell_bold),
                Paragraph(f"{patient.age or '—'} Y / {patient.gender or '—'}", cell_text),
                Paragraph("<b>Contact Phone:</b>", cell_bold),
                Paragraph(str(patient.phone or '—'), cell_text)
            ],
            [
                Paragraph("<b>Primary Doctor:</b>", cell_bold),
                Paragraph(doctor_name, cell_text),
                Paragraph("<b>Reg. Branch:</b>", cell_bold),
                Paragraph(patient.registration_branch.name if patient.registration_branch else "Main Branch", cell_text)
            ]
        ]
        if is_visit_mode and target_appointment:
            demo_data.append([
                Paragraph("<b>Visit Date:</b>", cell_bold),
                Paragraph(target_appointment.date.strftime('%d-%b-%Y'), cell_bold),
                Paragraph("<b>Visit Status:</b>", cell_bold),
                Paragraph(target_appointment.status, cell_text)
            ])

        demo_table = Table(demo_data, colWidths=[95, 166, 105, 157])
        demo_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(demo_table)
        story.append(Spacer(1, 6))

        # --- 3. MEDICAL ALERTS & BACKGROUND ---
        # Collect allergies, medical history, dental history
        allergies_list = []
        med_history_list = []
        dental_history_list = []

        notes_qs = ClinicalNotes.objects.filter(appointment__patient=patient)
        if is_visit_mode and target_appointment:
            notes_qs = notes_qs.filter(appointment=target_appointment)

        for n in notes_qs:
            if n.allergies:
                allergies_list.extend([a for a in n.allergies if a not in allergies_list])
            if n.medical_history:
                med_history_list.extend([m for m in n.medical_history if m not in med_history_list])
            if n.dental_history:
                dental_history_list.extend([d for d in n.dental_history if d not in dental_history_list])

        alert_bg = '#fef2f2' if allergies_list else '#f8fafc'
        alert_box_data = [
            [
                Paragraph("<b>MEDICAL ALERTS & HISTORY</b>", cell_bold),
                Paragraph(f"<b>Allergies:</b> <font color='#b91c1c'>{', '.join(allergies_list) if allergies_list else 'No Known Drug Allergies (NKDA)'}</font><br/>"
                          f"<b>Medical Conditions:</b> {', '.join(med_history_list) if med_history_list else 'None Recorded'}<br/>"
                          f"<b>Dental History:</b> {', '.join(dental_history_list) if dental_history_list else 'None Recorded'}", cell_text)
            ]
        ]
        alert_table = Table(alert_box_data, colWidths=[130, 393])
        alert_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(alert_bg)),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#fca5a5' if allergies_list else '#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(alert_table)
        story.append(Spacer(1, 6))

        # --- 4. CONSULTATION & CLINICAL EXAMINATION ---
        story.append(Paragraph("1. CLINICAL EXAMINATION & COMPLAINTS", section_heading))
        exam_rows = [
            [
                Paragraph("<b>Date / Visit</b>", cell_bold),
                Paragraph("<b>Chief Complaints</b>", cell_bold),
                Paragraph("<b>Observations & Vitals</b>", cell_bold),
                Paragraph("<b>Diagnosis</b>", cell_bold)
            ]
        ]

        active_notes = notes_qs.order_by('-appointment__date')
        if not active_notes.exists():
            exam_rows.append([Paragraph("No examination notes recorded yet.", cell_subtext), "", "", ""])
        else:
            for n in active_notes:
                complaint_str = n.chief_complaint or (", ".join(n.complaints) if n.complaints else "Routine checkup")
                obs_str = ", ".join(n.observations) if n.observations else (n.notes or "No abnormalities noted")
                diag_str = ", ".join(n.diagnosis) if n.diagnosis else "Under investigation"
                exam_rows.append([
                    Paragraph(n.appointment.date.strftime('%d-%b-%Y') if n.appointment else "—", cell_text),
                    Paragraph(complaint_str, cell_text),
                    Paragraph(obs_str, cell_text),
                    Paragraph(f"<b>{diag_str}</b>", cell_bold)
                ])

        exam_table = Table(exam_rows, colWidths=[80, 140, 163, 140])
        exam_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(exam_table)
        story.append(Spacer(1, 6))

        # --- 5. DENTAL CHART & ODONTOGRAM FINDINGS ---
        story.append(Paragraph("2. DENTAL CHART & TOOTH-LEVEL FINDINGS", section_heading))
        chart_rows = [
            [
                Paragraph("<b>Tooth #</b>", cell_bold),
                Paragraph("<b>Tooth Condition(s)</b>", cell_bold),
                Paragraph("<b>Surfaces</b>", cell_bold),
                Paragraph("<b>Specific Diagnosis / Findings</b>", cell_bold),
                Paragraph("<b>Periodontal / Mobility</b>", cell_bold)
            ]
        ]

        t_records = ToothConditionRecord.objects.filter(patient=patient, is_active=True).order_by('tooth_number')
        if not t_records.exists():
            chart_rows.append([Paragraph("No individual tooth conditions recorded.", cell_subtext), "", "", "", ""])
        else:
            for trc in t_records:
                cond_str = ", ".join(trc.condition) if trc.condition else "Sound / Intact"
                surf_str = ", ".join(trc.surfaces) if trc.surfaces else "Whole Tooth"
                spec_diag = ", ".join(trc.diagnosis or trc.examination or trc.treatments_suggested) or "—"
                perio_str = f"Mobility: {trc.mobility or '0'}, Pocket: {trc.pocket_depth or 'Normal'}" if (trc.mobility or trc.pocket_depth) else "Healthy"

                chart_rows.append([
                    Paragraph(f"<b>#{trc.tooth_number}</b>", cell_bold),
                    Paragraph(cond_str, cell_text),
                    Paragraph(surf_str, cell_text),
                    Paragraph(spec_diag, cell_text),
                    Paragraph(perio_str, cell_text)
                ])

        chart_table = Table(chart_rows, colWidths=[55, 128, 90, 140, 110])
        chart_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(chart_table)
        story.append(Spacer(1, 6))

        # --- 6. RECOMMENDED TREATMENT PLANS ---
        story.append(Paragraph("3. RECOMMENDED TREATMENT PLANS (PROPOSED)", section_heading))
        plan_rows = [
            [
                Paragraph("<b>Tooth</b>", cell_bold),
                Paragraph("<b>Recommended Procedure</b>", cell_bold),
                Paragraph("<b>Priority</b>", cell_bold),
                Paragraph("<b>Visits</b>", cell_bold),
                Paragraph("<b>Est. Cost (INR)</b>", cell_bold),
                Paragraph("<b>Plan Status</b>", cell_bold)
            ]
        ]

        plans_qs = TreatmentPlan.objects.filter(patient=patient).prefetch_related('items').order_by('-created_at')
        has_items = False
        for p in plans_qs:
            for it in p.items.all():
                has_items = True
                plan_rows.append([
                    Paragraph(f"#{it.tooth_number}" if it.tooth_number else "Arch/Full", cell_bold),
                    Paragraph(f"<b>{it.procedure_name}</b>" + (f"<br/>{it.surface}" if it.surface and it.surface != 'All' else ""), cell_text),
                    Paragraph(it.priority, cell_text),
                    Paragraph(str(it.estimated_visits), cell_text),
                    Paragraph(f"Rs. {it.final_cost:,.2f}", cell_bold),
                    Paragraph(f"<b>{it.status}</b>", cell_bold)
                ])

        if not has_items:
            plan_rows.append([Paragraph("No treatment recommendations logged.", cell_subtext), "", "", "", "", ""])

        plan_table = Table(plan_rows, colWidths=[55, 188, 65, 45, 85, 85])
        plan_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(plan_table)
        story.append(Spacer(1, 6))

        # --- 7. TREATMENTS PERFORMED & CLINICAL EXECUTION ---
        story.append(Paragraph("4. TREATMENTS PERFORMED / PROCEDURES EXECUTED", section_heading))
        tx_rows = [
            [
                Paragraph("<b>Date</b>", cell_bold),
                Paragraph("<b>Tooth</b>", cell_bold),
                Paragraph("<b>Completed Procedure</b>", cell_bold),
                Paragraph("<b>Operating Doctor</b>", cell_bold),
                Paragraph("<b>Status</b>", cell_bold),
                Paragraph("<b>Clinical Notes / Remarks</b>", cell_bold)
            ]
        ]

        tx_qs = TreatmentRecord.objects.filter(visit__patient=patient).select_related('treatment', 'doctor', 'visit').order_by('-visit__created_at')
        if is_visit_mode and target_visit:
            tx_qs = tx_qs.filter(visit=target_visit)

        if not tx_qs.exists():
            tx_rows.append([Paragraph("No performed clinical procedures recorded.", cell_subtext), "", "", "", "", ""])
        else:
            for tr in tx_qs:
                tx_date = tr.visit.created_at.strftime('%d-%b-%Y') if tr.visit else "—"
                tx_rows.append([
                    Paragraph(tx_date, cell_text),
                    Paragraph(f"#{tr.tooth_number}" if tr.tooth_number else "Gen", cell_bold),
                    Paragraph(f"<b>{tr.treatment.name if tr.treatment else 'Procedure'}</b>", cell_bold),
                    Paragraph(f"Dr. {tr.doctor.name if tr.doctor else 'Attending'}", cell_text),
                    Paragraph(tr.status, cell_text),
                    Paragraph(tr.notes or "Completed uneventfully", cell_text)
                ])

        tx_table = Table(tx_rows, colWidths=[65, 45, 143, 90, 65, 115])
        tx_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(tx_table)
        story.append(Spacer(1, 6))

        # --- 8. MULTI-SESSION CLINICAL LOGS ---
        sess_qs = TreatmentSession.objects.filter(patient=patient).select_related('doctor', 'treatment_record').order_by('-session_date', '-session_number')
        if is_visit_mode and target_visit:
            sess_qs = sess_qs.filter(visit=target_visit)

        if sess_qs.exists():
            story.append(Paragraph("5. MULTI-SESSION PROCEDURE PROGRESS", section_heading))
            sess_rows = [
                [
                    Paragraph("<b>Session #</b>", cell_bold),
                    Paragraph("<b>Date</b>", cell_bold),
                    Paragraph("<b>Step / Procedure Performed</b>", cell_bold),
                    Paragraph("<b>Materials Used</b>", cell_bold),
                    Paragraph("<b>Next Step Planned</b>", cell_bold)
                ]
            ]
            for s in sess_qs:
                sess_rows.append([
                    Paragraph(f"Session {s.session_number}", cell_bold),
                    Paragraph(s.session_date.strftime('%d-%b-%Y'), cell_text),
                    Paragraph(f"<b>{s.procedure_performed}</b><br/>{s.clinical_notes}", cell_text),
                    Paragraph(s.materials_used or "Standard restorative", cell_text),
                    Paragraph(f"{s.next_session_plan or '—'}" + (f"<br/>(On: {s.next_session_date.strftime('%d-%b-%Y')})" if s.next_session_date else ""), cell_text)
                ])

            sess_table = Table(sess_rows, colWidths=[65, 65, 173, 110, 110])
            sess_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(sess_table)
            story.append(Spacer(1, 6))

        # --- 9. INVESTIGATIONS & RADIOLOGY ---
        inv_qs = PatientInvestigation.objects.filter(patient=patient).prefetch_related('attachments').order_by('-investigation_date')
        if is_visit_mode and target_appointment:
            inv_qs = inv_qs.filter(appointment=target_appointment)

        story.append(Paragraph("6. DIAGNOSTIC INVESTIGATIONS & RADIOLOGY", section_heading))
        inv_rows = [
            [
                Paragraph("<b>Date</b>", cell_bold),
                Paragraph("<b>Investigation Type</b>", cell_bold),
                Paragraph("<b>Indication / Reason</b>", cell_bold),
                Paragraph("<b>Findings & Impression</b>", cell_bold),
                Paragraph("<b>Status / Report</b>", cell_bold)
            ]
        ]
        if not inv_qs.exists():
            inv_rows.append([Paragraph("No radiology or lab investigations ordered.", cell_subtext), "", "", "", ""])
        else:
            for inv in inv_qs:
                att_names = ", ".join([a.file_name for a in inv.attachments.all()])
                report_str = f"<b>{inv.status}</b>" + (f"<br/>Files: {att_names}" if att_names else "")
                inv_rows.append([
                    Paragraph(inv.investigation_date.strftime('%d-%b-%Y'), cell_text),
                    Paragraph(f"<b>{inv.investigation_name}</b>", cell_bold),
                    Paragraph(inv.reason or "Clinical examination", cell_text),
                    Paragraph(inv.findings or "Normal radiographic findings", cell_text),
                    Paragraph(report_str, cell_text)
                ])

        inv_table = Table(inv_rows, colWidths=[65, 120, 110, 138, 90])
        inv_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(inv_table)
        story.append(Spacer(1, 6))

        # --- 10. PRESCRIPTIONS (Rx) ---
        rx_qs = Prescription.objects.filter(patient=patient).prefetch_related('items').order_by('-created_at')
        if is_visit_mode and target_visit:
            rx_qs = rx_qs.filter(visit=target_visit)

        story.append(Paragraph("7. MEDICATIONS PRESCRIBED (Rx)", section_heading))
        rx_rows = [
            [
                Paragraph("<b>Date</b>", cell_bold),
                Paragraph("<b>Medicine Name</b>", cell_bold),
                Paragraph("<b>Dosage (M-A-N)</b>", cell_bold),
                Paragraph("<b>Duration</b>", cell_bold),
                Paragraph("<b>Instructions / Special Notes</b>", cell_bold)
            ]
        ]

        has_rx_items = False
        for rx in rx_qs:
            rx_d = rx.created_at.strftime('%d-%b-%Y')
            for it in rx.items.all():
                has_rx_items = True
                rx_rows.append([
                    Paragraph(rx_d, cell_text),
                    Paragraph(f"<b>{it.medicine_name}</b>", cell_bold),
                    Paragraph(it.dosage, cell_text),
                    Paragraph(it.duration, cell_text),
                    Paragraph(it.notes or "Take after food with water", cell_text)
                ])

        if not has_rx_items:
            rx_rows.append([Paragraph("No medications prescribed.", cell_subtext), "", "", "", ""])

        rx_table = Table(rx_rows, colWidths=[65, 140, 95, 75, 148])
        rx_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(rx_table)
        story.append(Spacer(1, 6))

        # --- 11. FOLLOW-UP & ADVISORY INSTRUCTIONS ---
        latest_cn = active_notes.first()
        fu_date = latest_cn.follow_up_date.strftime('%d-%b-%Y') if (latest_cn and latest_cn.follow_up_date) else "As required / PRN"
        fu_note = latest_cn.follow_up_note if (latest_cn and latest_cn.follow_up_note) else "Maintain optimal oral hygiene. Brush twice daily and rinse with antiseptic mouthwash."

        advice_data = [
            [
                Paragraph("<b>FOLLOW-UP & POST-OP ADVICE</b>", cell_bold),
                Paragraph(f"<b>Next Scheduled Follow-up:</b> {fu_date}<br/>"
                          f"<b>Clinical Advice & Instructions:</b> {fu_note}", cell_text)
            ]
        ]
        advice_table = Table(advice_data, colWidths=[130, 393])
        advice_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(advice_table)
        story.append(Spacer(1, 14))

        # --- 12. SIGNATURE & ATTESTATION BLOCK ---
        sig_data = [
            [
                Paragraph("<b>PATIENT ACKNOWLEDGEMENT</b><br/><br/><br/>_______________________________<br/>Patient / Guardian Signature", cell_text),
                Paragraph(f"<b>TREATING DENTAL SURGEON</b><br/><br/><br/>_______________________________<br/><b>{doctor_name}</b><br/>B.D.S., M.D.S. (Dental Surgeon)<br/>Reg No: DENT-REG-ASHDENT", cell_text)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[260, 263])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(KeepTogether([sig_table]))

        # Build document with custom NumberedCanvas for dynamic page numbering
        doc.build(story, canvasmaker=NumberedCanvas)

        buffer.seek(0)
        filename = f"AshDent_EMR_{patient.id}_{'Visit' if is_visit_mode else 'Lifetime'}.pdf"
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
