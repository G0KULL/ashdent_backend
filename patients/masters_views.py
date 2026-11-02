import re
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import (
    PatientTypeMaster, StaffLevelMaster, DesignationMaster, RoleMaster,
    PermissionMaster, RolePermission, StaffPermissionOverride, DiscountMaster,
    OfferPackage, OfferPackageItem, PatientPackageSubscription, PackageRedemption,
    Patient, Staff, BillingItem,
    TreatmentMaster, DiagnosisMaster, ExaminationMaster, ToothConditionMaster, DropdownMaster
)

from .security import get_authenticated_user, is_super_admin, is_application_admin


# ─── HELPER: PERMISSION CHECKER ──────────────────────────────────────────────

def evaluate_staff_permission(staff, permission_code, action='view'):
    """
    Centralized Permission Evaluation Engine (Phase 6):
    Staff Override exists? -> Use Staff Override
    No Staff Override? -> Use Role Permission
    No Permission? -> Denied (False)
    """
    if not staff or not permission_code:
        return False
        
    # Admin override
    if staff.role and staff.role.lower() == 'admin':
        return True

    perm = PermissionMaster.objects.filter(permission_code=permission_code).first()
    if not perm:
        return True # Fallback for non-master system actions

    # 1. Check Staff Specific Override
    override = StaffPermissionOverride.objects.filter(staff=staff, permission=perm).first()
    if override:
        action_val = getattr(override, f"can_{action}", None)
        if action_val is not None:
            return action_val

    # 2. Check Role Permission
    role_obj = RoleMaster.objects.filter(name__iexact=staff.role).first() or RoleMaster.objects.filter(code__iexact=staff.role).first()
    if role_obj:
        role_perm = RolePermission.objects.filter(role=role_obj, permission=perm).first()
        if role_perm:
            return getattr(role_perm, f"can_{action}", False)

    return False


# ─── 1. PATIENT TYPE MASTER API ───────────────────────────────────────────────

class PatientTypeMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(PatientTypeMaster, pk=pk)
            return Response({
                "id": obj.id, "name": obj.name, "code": obj.code,
                "description": obj.description, "is_active": obj.is_active,
                "display_order": obj.display_order
            })
        
        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        qs = PatientTypeMaster.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
            
        data = [{
            "id": item.id, "name": item.name, "code": item.code,
            "description": item.description, "is_active": item.is_active,
            "display_order": item.display_order
        } for item in qs]
        return Response(data)

    def post(self, request):
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip().upper()
        description = request.data.get('description', '').strip()
        display_order = request.data.get('display_order', 0)

        if not name or not code:
            return Response({"success": False, "error": "Name and Code are required."}, status=status.HTTP_400_BAD_REQUEST)

        if PatientTypeMaster.objects.filter(code=code).exists():
            return Response({"success": False, "error": f"Patient Type with code '{code}' already exists."}, status=status.HTTP_400_BAD_REQUEST)

        obj = PatientTypeMaster.objects.create(
            name=name, code=code, description=description, display_order=display_order, is_active=True
        )
        return Response({"success": True, "message": "Patient Type created", "id": obj.id}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(PatientTypeMaster, pk=pk)
        obj.name = request.data.get('name', obj.name).strip()
        obj.description = request.data.get('description', obj.description)
        obj.display_order = request.data.get('display_order', obj.display_order)
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Patient Type updated"})

    def delete(self, request, pk):
        obj = get_object_or_404(PatientTypeMaster, pk=pk)
        obj.is_active = False
        obj.save()
        return Response({"success": True, "message": "Patient Type deactivated"})


# ─── 2. STAFF LEVEL MASTER API ────────────────────────────────────────────────

class StaffLevelMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(StaffLevelMaster, pk=pk)
            return Response({
                "id": obj.id, "name": obj.name, "code": obj.code,
                "description": obj.description, "is_active": obj.is_active,
                "display_order": obj.display_order
            })
            
        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        qs = StaffLevelMaster.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
            
        data = [{
            "id": item.id, "name": item.name, "code": item.code,
            "description": item.description, "is_active": item.is_active,
            "display_order": item.display_order
        } for item in qs]
        return Response(data)

    def post(self, request):
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip().upper()
        description = request.data.get('description', '').strip()
        display_order = request.data.get('display_order', 0)

        if not name or not code:
            return Response({"success": False, "error": "Name and Code are required."}, status=status.HTTP_400_BAD_REQUEST)

        if StaffLevelMaster.objects.filter(code=code).exists():
            return Response({"success": False, "error": f"Staff Level code '{code}' already exists."}, status=status.HTTP_400_BAD_REQUEST)

        obj = StaffLevelMaster.objects.create(
            name=name, code=code, description=description, display_order=display_order, is_active=True
        )
        return Response({"success": True, "message": "Staff Level created", "id": obj.id}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(StaffLevelMaster, pk=pk)
        obj.name = request.data.get('name', obj.name).strip()
        obj.description = request.data.get('description', obj.description)
        obj.display_order = request.data.get('display_order', obj.display_order)
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Staff Level updated"})

    def delete(self, request, pk):
        obj = get_object_or_404(StaffLevelMaster, pk=pk)
        obj.is_active = False
        obj.save()
        return Response({"success": True, "message": "Staff Level deactivated"})


# ─── 3. DESIGNATION MASTER API ────────────────────────────────────────────────

class DesignationMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(DesignationMaster, pk=pk)
            return Response({
                "id": obj.id, "name": obj.name, "code": obj.code,
                "description": obj.description, "is_active": obj.is_active,
                "display_order": obj.display_order
            })
            
        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        qs = DesignationMaster.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
            
        data = [{
            "id": item.id, "name": item.name, "code": item.code,
            "description": item.description, "is_active": item.is_active,
            "display_order": item.display_order
        } for item in qs]
        return Response(data)

    def post(self, request):
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip().upper()
        description = request.data.get('description', '').strip()
        display_order = request.data.get('display_order', 0)

        if not name or not code:
            return Response({"success": False, "error": "Name and Code are required."}, status=status.HTTP_400_BAD_REQUEST)

        if DesignationMaster.objects.filter(code=code).exists():
            return Response({"success": False, "error": f"Designation code '{code}' already exists."}, status=status.HTTP_400_BAD_REQUEST)

        obj = DesignationMaster.objects.create(
            name=name, code=code, description=description, display_order=display_order, is_active=True
        )
        return Response({"success": True, "message": "Designation created", "id": obj.id}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(DesignationMaster, pk=pk)
        obj.name = request.data.get('name', obj.name).strip()
        obj.description = request.data.get('description', obj.description)
        obj.display_order = request.data.get('display_order', obj.display_order)
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Designation updated"})

    def delete(self, request, pk):
        obj = get_object_or_404(DesignationMaster, pk=pk)
        obj.is_active = False
        obj.save()
        return Response({"success": True, "message": "Designation deactivated"})


# ─── 4. ROLE MASTER & PERMISSION MATRIX API ───────────────────────────────────

class RoleMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(RoleMaster, pk=pk)
            perms = RolePermission.objects.filter(role=obj)
            return Response({
                "id": obj.id, "name": obj.name, "code": obj.code,
                "description": obj.description, "is_system_role": obj.is_system_role,
                "is_active": obj.is_active,
                "permissions": [{
                    "permission_id": p.permission.id,
                    "permission_code": p.permission.permission_code,
                    "permission_name": p.permission.name,
                    "can_view": p.can_view, "can_create": p.can_create,
                    "can_edit": p.can_edit, "can_delete": p.can_delete,
                    "can_export": p.can_export, "can_approve": p.can_approve
                } for p in perms]
            })
            
        qs = RoleMaster.objects.all()
        data = []
        for item in qs:
            perms = RolePermission.objects.filter(role=item)
            data.append({
                "id": item.id, "name": item.name, "code": item.code,
                "description": item.description, "is_system_role": item.is_system_role,
                "is_active": item.is_active,
                "permissions": [{
                    "permission_code": p.permission.permission_code,
                    "can_view": p.can_view, "can_create": p.can_create,
                    "can_edit": p.can_edit, "can_delete": p.can_delete,
                    "can_export": p.can_export, "can_approve": p.can_approve
                } for p in perms]
            })
        return Response(data)

    def post(self, request):
        req_user = get_authenticated_user(request)
        if not req_user:
            return Response({"success": False, "error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        if not is_application_admin(req_user):
            return Response({"success": False, "error": "Only Super Admin can create or modify system role definitions."}, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip().upper()
        description = request.data.get('description', '').strip()

        if not name or not code:
            return Response({"success": False, "error": "Name and Code are required."}, status=status.HTTP_400_BAD_REQUEST)

        if RoleMaster.objects.filter(code=code).exists():
            return Response({"success": False, "error": f"Role code '{code}' already exists."}, status=status.HTTP_400_BAD_REQUEST)

        obj = RoleMaster.objects.create(
            name=name, code=code, description=description, is_system_role=False, is_active=True
        )

        permissions_data = request.data.get('permissions', [])
        for p_data in permissions_data:
            p_code = p_data.get('permission_code')
            perm_obj = PermissionMaster.objects.filter(permission_code=p_code).first()
            if perm_obj:
                RolePermission.objects.update_or_create(
                    role=obj, permission=perm_obj,
                    defaults={
                        "can_view": bool(p_data.get('can_view', False)),
                        "can_create": bool(p_data.get('can_create', False)),
                        "can_edit": bool(p_data.get('can_edit', False)),
                        "can_delete": bool(p_data.get('can_delete', False)),
                        "can_export": bool(p_data.get('can_export', False)),
                        "can_approve": bool(p_data.get('can_approve', False)),
                    }
                )
        return Response({"success": True, "message": "Role created successfully", "id": obj.id}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        req_user = get_authenticated_user(request)
        if not req_user:
            return Response({"success": False, "error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        if not is_application_admin(req_user):
            return Response({"success": False, "error": "Only Super Admin can create or modify system role definitions."}, status=status.HTTP_403_FORBIDDEN)

        obj = get_object_or_404(RoleMaster, pk=pk)
        obj.name = request.data.get('name', obj.name).strip()
        obj.description = request.data.get('description', obj.description)
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()

        permissions_data = request.data.get('permissions', [])
        for p_data in permissions_data:
            p_code = p_data.get('permission_code')
            perm_obj = PermissionMaster.objects.filter(permission_code=p_code).first()
            if perm_obj:
                RolePermission.objects.update_or_create(
                    role=obj, permission=perm_obj,
                    defaults={
                        "can_view": bool(p_data.get('can_view', False)),
                        "can_create": bool(p_data.get('can_create', False)),
                        "can_edit": bool(p_data.get('can_edit', False)),
                        "can_delete": bool(p_data.get('can_delete', False)),
                        "can_export": bool(p_data.get('can_export', False)),
                        "can_approve": bool(p_data.get('can_approve', False)),
                    }
                )

        return Response({"success": True, "message": "Role updated successfully"})

    def delete(self, request, pk):
        obj = get_object_or_404(RoleMaster, pk=pk)
        if obj.is_system_role:
            return Response({"success": False, "error": "System roles cannot be deleted."}, status=status.HTTP_400_BAD_REQUEST)
        obj.is_active = False
        obj.save()
        return Response({"success": True, "message": "Role deactivated"})


class PermissionMasterAPIView(APIView):
    def get(self, request):
        qs = PermissionMaster.objects.all()
        data = [{
            "id": p.id, "module_code": p.module_code,
            "permission_code": p.permission_code, "name": p.name,
            "description": p.description
        } for p in qs]
        return Response(data)


# ─── 5. DISCOUNT MASTER API ───────────────────────────────────────────────────

class DiscountMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(DiscountMaster, pk=pk)
            return Response({
                "id": obj.id, "name": obj.name, "code": obj.code,
                "description": obj.description, "discount_type": obj.discount_type,
                "discount_value": float(obj.discount_value), "applicable_module": obj.applicable_module,
                "valid_from": str(obj.valid_from) if obj.valid_from else None,
                "valid_to": str(obj.valid_to) if obj.valid_to else None,
                "max_discount": float(obj.max_discount) if obj.max_discount else None,
                "is_active": obj.is_active
            })
            
        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        qs = DiscountMaster.objects.all()
        if active_only:
            today = timezone.now().date()
            qs = qs.filter(is_active=True, valid_from__lte=today)
            
        data = [{
            "id": item.id, "name": item.name, "code": item.code,
            "description": item.description, "discount_type": item.discount_type,
            "discount_value": float(item.discount_value), "applicable_module": item.applicable_module,
            "valid_from": str(item.valid_from) if item.valid_from else None,
            "valid_to": str(item.valid_to) if item.valid_to else None,
            "max_discount": float(item.max_discount) if item.max_discount else None,
            "is_active": item.is_active
        } for item in qs]
        return Response(data)

    def post(self, request):
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip().upper()
        discount_type = request.data.get('discount_type', 'Percentage')
        discount_value = request.data.get('discount_value', 0)
        valid_from = request.data.get('valid_from') or timezone.now().date()
        valid_to = request.data.get('valid_to') if request.data.get('valid_to') not in ['', None] else None

        if not name or not code or discount_value is None:
            return Response({"success": False, "error": "Name, Code, and Discount Value are required."}, status=status.HTTP_400_BAD_REQUEST)

        if DiscountMaster.objects.filter(code=code).exists():
            return Response({"success": False, "error": f"Discount code '{code}' already exists."}, status=status.HTTP_400_BAD_REQUEST)

        if valid_to and str(valid_to) < str(valid_from):
            return Response({"success": False, "error": "Valid To date cannot be earlier than Valid From date."}, status=status.HTTP_400_BAD_REQUEST)

        obj = DiscountMaster.objects.create(
            name=name, code=code, description=request.data.get('description', ''),
            discount_type=discount_type, discount_value=discount_value,
            applicable_module=request.data.get('applicable_module', 'ALL'),
            valid_from=valid_from, valid_to=valid_to,
            max_discount=request.data.get('max_discount') if request.data.get('max_discount') not in ['', None] else None,
            is_active=True
        )
        return Response({"success": True, "message": "Discount created", "id": obj.id}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(DiscountMaster, pk=pk)
        obj.name = request.data.get('name', obj.name).strip()
        obj.discount_type = request.data.get('discount_type', obj.discount_type)
        obj.discount_value = request.data.get('discount_value', obj.discount_value)
        obj.applicable_module = request.data.get('applicable_module', obj.applicable_module)
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Discount updated"})

    def delete(self, request, pk):
        obj = get_object_or_404(DiscountMaster, pk=pk)
        obj.is_active = False
        obj.save()
        return Response({"success": True, "message": "Discount deactivated"})


# ─── 6. OFFER PACKAGES API ────────────────────────────────────────────────────

class OfferPackageAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(OfferPackage, pk=pk)
            items = OfferPackageItem.objects.filter(package=obj)
            return Response({
                "id": obj.id, "name": obj.name, "code": obj.code,
                "description": obj.description, "package_type": obj.package_type,
                "original_price": float(obj.original_price), "package_price": float(obj.package_price),
                "discount_type": obj.discount_type, "discount_value": float(obj.discount_value),
                "valid_from": str(obj.valid_from) if obj.valid_from else None,
                "valid_to": str(obj.valid_to) if obj.valid_to else None,
                "validity_days": obj.validity_days, "max_redemptions": obj.max_redemptions,
                "is_active": obj.is_active,
                "items": [{
                    "id": item.id, "item_type": item.item_type,
                    "treatment_id": item.treatment_id, "treatment_name": item.treatment.name if item.treatment else None,
                    "lab_test_id": item.lab_test_id, "lab_test_name": item.lab_test.name if item.lab_test else None,
                    "medicine_id": item.medicine_id, "medicine_name": item.medicine.name if item.medicine else None,
                    "custom_item_name": item.custom_item_name,
                    "quantity": item.quantity, "unit_price": float(item.unit_price),
                    "package_item_price": float(item.package_item_price)
                } for item in items]
            })
            
        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        qs = OfferPackage.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
            
        data = []
        for item in qs:
            pkg_items = OfferPackageItem.objects.filter(package=item)
            data.append({
                "id": item.id, "name": item.name, "code": item.code,
                "description": item.description, "package_type": item.package_type,
                "original_price": float(item.original_price), "package_price": float(item.package_price),
                "discount_type": item.discount_type, "discount_value": float(item.discount_value),
                "valid_from": str(item.valid_from) if item.valid_from else None,
                "valid_to": str(item.valid_to) if item.valid_to else None,
                "validity_days": item.validity_days, "max_redemptions": item.max_redemptions,
                "is_active": item.is_active,
                "items_count": pkg_items.count()
            })
        return Response(data)

    def post(self, request):
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip().upper()
        package_price = request.data.get('package_price')
        package_type = request.data.get('package_type', 'Combo Treatment')

        if not name or not code or package_price is None:
            return Response({"success": False, "error": "Name, Code, and Package Price are required."}, status=status.HTTP_400_BAD_REQUEST)

        if OfferPackage.objects.filter(code=code).exists():
            return Response({"success": False, "error": f"Package code '{code}' already exists."}, status=status.HTTP_400_BAD_REQUEST)

        obj = OfferPackage.objects.create(
            name=name, code=code, description=request.data.get('description', ''),
            package_type=package_type, original_price=request.data.get('original_price', package_price),
            package_price=package_price, discount_type=request.data.get('discount_type', 'Flat Amount'),
            discount_value=request.data.get('discount_value', 0.00),
            valid_from=request.data.get('valid_from') or timezone.now().date(),
            valid_to=request.data.get('valid_to') if request.data.get('valid_to') not in ['', None] else None,
            validity_days=request.data.get('validity_days', 365),
            max_redemptions=request.data.get('max_redemptions', 0),
            is_active=True
        )

        items_data = request.data.get('items', [])
        for i_data in items_data:
            OfferPackageItem.objects.create(
                package=obj,
                item_type=i_data.get('item_type', 'Treatment'),
                treatment_id=i_data.get('treatment_id'),
                lab_test_id=i_data.get('lab_test_id'),
                medicine_id=i_data.get('medicine_id'),
                custom_item_name=i_data.get('custom_item_name', ''),
                quantity=i_data.get('quantity', 1),
                unit_price=i_data.get('unit_price', 0.00),
                package_item_price=i_data.get('package_item_price', 0.00)
            )

        return Response({"success": True, "message": "Offer Package created", "id": obj.id}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(OfferPackage, pk=pk)
        obj.name = request.data.get('name', obj.name).strip()
        obj.package_price = request.data.get('package_price', obj.package_price)
        obj.original_price = request.data.get('original_price', obj.original_price)
        obj.package_type = request.data.get('package_type', obj.package_type)
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Offer Package updated"})

    def delete(self, request, pk):
        obj = get_object_or_404(OfferPackage, pk=pk)
        obj.is_active = False
        obj.save()
        return Response({"success": True, "message": "Offer Package deactivated"})


# ─── 7. PACKAGE SUBSCRIPTIONS & REDEMPTIONS API ───────────────────────────────

class PackageSubscriptionAPIView(APIView):
    def get(self, request):
        patient_id = request.GET.get('patient_id')
        qs = PatientPackageSubscription.objects.all()
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
            
        data = [{
            "id": sub.id, "patient_id": sub.patient.id, "patient_name": sub.patient.name,
            "package_id": sub.package.id, "package_name": sub.package.name,
            "purchase_date": sub.purchase_date, "expiry_date": sub.expiry_date,
            "paid_amount": float(sub.paid_amount), "status": sub.status,
            "redemptions_count": sub.redemptions.count()
        } for sub in qs]
        return Response(data)

    def post(self, request):
        patient_id = request.data.get('patient_id')
        package_id = request.data.get('package_id')
        
        if not patient_id or not package_id:
            return Response({"success": False, "error": "Patient and Package are required."}, status=status.HTTP_400_BAD_REQUEST)
            
        patient = get_object_or_404(Patient, pk=patient_id)
        package = get_object_or_404(OfferPackage, pk=package_id)
        
        purchase_date = timezone.now().date()
        expiry_date = purchase_date + timezone.timedelta(days=package.validity_days)
        
        sub = PatientPackageSubscription.objects.create(
            patient=patient,
            package=package,
            purchase_date=purchase_date,
            expiry_date=expiry_date,
            paid_amount=package.package_price,
            status='ACTIVE'
        )
        return Response({"success": True, "message": f"Package '{package.name}' subscribed for {patient.name}", "subscription_id": sub.id}, status=status.HTTP_201_CREATED)


# ─── CLINICAL MASTERS HELPER & AUTO-CREATE ENGINE ────────────────────────────

def normalize_master_name(val):
    """Normalize string: collapse internal whitespace, strip leading/trailing."""
    if not val:
        return ""
    return re.sub(r'\s+', ' ', str(val)).strip()

def generate_unique_code(model_cls, prefix, name):
    """Generate a clean, collision-free code for a master item."""
    clean_slug = re.sub(r'[^A-Z0-9]', '', name.upper())[:6] or "ITEM"
    base_code = f"{prefix}-{clean_slug}"
    if not model_cls.objects.filter(code=base_code).exists():
        return base_code
    counter = 1
    while model_cls.objects.filter(code=f"{base_code}-{counter:02d}").exists():
        counter += 1
    return f"{base_code}-{counter:02d}"

def find_master_by_name(model_cls, name):
    """
    Safely find existing master record case-insensitively,
    properly escaping regex metacharacters in MongoDB (e.g. parentheses, slashes).
    """
    if not name:
        return None
    # 1. Direct exact match
    direct = model_cls.objects.filter(name=name).first()
    if direct:
        return direct
    # 2. Case-insensitive exact regex with re.escape
    try:
        escaped_pattern = f"^{re.escape(name)}$"
        matched = model_cls.objects.filter(name__iregex=escaped_pattern).first()
        if matched:
            return matched
    except Exception:
        pass
    # 3. Memory fallback comparison if needed
    clean_target = name.strip().casefold()
    for item in model_cls.objects.all():
        if item.name.strip().casefold() == clean_target:
            return item
    return None

def auto_create_or_reuse_master(master_type, raw_name, extra=None):
    """
    Centralized create-or-reuse engine for master-backed clinical fields:
    1. Normalizes value.
    2. Enforces validation rules (length, non-numeric).
    3. Matches case-insensitively (handling MongoDB regex metacharacters).
    4. Reuses existing record or safely creates new record in transaction.
    5. Syncs with DropdownMaster for backward compatibility.
    """
    if extra is None:
        extra = {}
    name = normalize_master_name(raw_name)
    if not name or len(name) < 2:
        return None, False, "Name must be at least 2 characters long."
    if len(name) > 255:
        return None, False, "Name cannot exceed 255 characters."

    # Prevent purely numeric clinical names (e.g. tooth numbers, fees)
    if name.isdigit() or re.match(r'^\d+(\.\d+)?$', name):
        return None, False, "Clinical options cannot be numeric values."

    m_type = str(master_type).lower().strip()
    if m_type in ['treatment', 'procedure']:
        model_cls = TreatmentMaster
        prefix = 'TX'
    elif m_type in ['diagnosis', 'category']:
        model_cls = DiagnosisMaster
        prefix = 'DX'
    elif m_type in ['examination', 'observation', 'finding']:
        model_cls = ExaminationMaster
        prefix = 'EXAM'
    elif m_type in ['tooth_condition', 'condition']:
        model_cls = ToothConditionMaster
        prefix = 'COND'
    else:
        return None, False, f"Unsupported master type '{master_type}'"

    # Case-insensitive lookup (with regex escaping for MongoDB)
    existing = find_master_by_name(model_cls, name)
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.save(update_fields=['is_active'])
        return existing, False, None

    # Safe atomic creation
    try:
        with transaction.atomic():
            code = generate_unique_code(model_cls, prefix, name)
            if model_cls == TreatmentMaster:
                price = extra.get('price', 400.0)
                fee_type = extra.get('fee_type', 'Treatment')
                obj = TreatmentMaster.objects.create(
                    name=name, code=code, price=price, fee_type=fee_type, is_active=True
                )
            elif model_cls == DiagnosisMaster:
                cat = extra.get('category', 'General')
                desc = extra.get('description', '')
                obj = DiagnosisMaster.objects.create(
                    name=name, code=code, category=cat, description=desc, is_active=True
                )
                DropdownMaster.objects.get_or_create(type='diagnosis', name=name)
            elif model_cls == ExaminationMaster:
                cat = extra.get('category', 'General')
                desc = extra.get('description', '')
                obj = ExaminationMaster.objects.create(
                    name=name, code=code, category=cat, description=desc, is_active=True
                )
                DropdownMaster.objects.get_or_create(type='observation', name=name)
            elif model_cls == ToothConditionMaster:
                color = extra.get('color', '#3b82f6')
                desc = extra.get('description', '')
                obj = ToothConditionMaster.objects.create(
                    name=name, code=code, color=color, is_system=False, description=desc, is_active=True
                )
            return obj, True, None
    except Exception as e:
        fallback = find_master_by_name(model_cls, name)
        if fallback:
            return fallback, False, None
        return None, False, str(e)


# ─── 8. TREATMENT / PROCEDURE MASTER API ──────────────────────────────────────

class TreatmentMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(TreatmentMaster, pk=pk)
            return Response({
                "id": str(obj.id), "name": obj.name, "code": obj.code or f"TX-{obj.id}",
                "price": float(obj.price), "fee_type": obj.fee_type,
                "is_active": obj.is_active
            })

        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        search = request.GET.get('search', '').strip()
        qs = TreatmentMaster.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        if search:
            qs = qs.filter(name__icontains=search)

        data = [{
            "id": str(item.id), "name": item.name, "code": item.code or f"TX-{item.id}",
            "price": float(item.price), "fee_type": item.fee_type,
            "is_active": item.is_active
        } for item in qs.order_by('name')]
        return Response(data)

    def post(self, request):
        name = normalize_master_name(request.data.get('name', ''))
        if not name or len(name) < 2:
            return Response({"success": False, "error": "Treatment name must be at least 2 characters long."}, status=status.HTTP_400_BAD_REQUEST)

        # Concurrency & duplicate check
        existing = TreatmentMaster.objects.filter(name__iexact=name).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.save(update_fields=['is_active'])
            return Response({
                "success": True, "created": False, "message": f"Reused existing treatment '{existing.name}'",
                "id": str(existing.id), "name": existing.name, "code": existing.code
            }, status=status.HTTP_200_OK)

        code = request.data.get('code', '').strip().upper() or generate_unique_code(TreatmentMaster, 'TX', name)
        price = request.data.get('price', 400.0)
        fee_type = request.data.get('fee_type', 'Treatment') or 'Treatment'

        obj = TreatmentMaster.objects.create(name=name, code=code, price=price, fee_type=fee_type, is_active=True)
        return Response({"success": True, "created": True, "message": "Treatment created successfully", "id": str(obj.id), "name": obj.name, "code": obj.code}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(TreatmentMaster, pk=pk)
        if 'name' in request.data:
            name = normalize_master_name(request.data['name'])
            if name:
                dup = TreatmentMaster.objects.filter(name__iexact=name).exclude(pk=obj.pk).first()
                if dup:
                    return Response({"success": False, "error": f"Treatment '{name}' already exists."}, status=status.HTTP_400_BAD_REQUEST)
                obj.name = name
        if 'price' in request.data:
            try:
                obj.price = float(request.data['price'])
            except (ValueError, TypeError):
                pass
        if 'fee_type' in request.data:
            obj.fee_type = request.data['fee_type']
        if 'code' in request.data and request.data['code']:
            obj.code = request.data['code'].strip().upper()
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Treatment updated successfully", "id": str(obj.id), "name": obj.name, "code": obj.code, "is_active": obj.is_active})

    def delete(self, request, pk):
        obj = get_object_or_404(TreatmentMaster, pk=pk)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        return Response({"success": True, "message": "Treatment deactivated"})


# ─── 9. DIAGNOSIS MASTER API ──────────────────────────────────────────────────

class DiagnosisMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(DiagnosisMaster, pk=pk)
            return Response({
                "id": str(obj.id), "name": obj.name, "code": obj.code,
                "description": obj.description, "category": obj.category,
                "is_active": obj.is_active, "display_order": obj.display_order
            })

        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        search = request.GET.get('search', '').strip()
        qs = DiagnosisMaster.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        if search:
            qs = qs.filter(name__icontains=search)

        data = [{
            "id": str(item.id), "name": item.name, "code": item.code,
            "description": item.description, "category": item.category,
            "is_active": item.is_active, "display_order": item.display_order
        } for item in qs.order_by('display_order', 'name')]
        return Response(data)

    def post(self, request):
        name = normalize_master_name(request.data.get('name', ''))
        if not name or len(name) < 2:
            return Response({"success": False, "error": "Diagnosis name must be at least 2 characters long."}, status=status.HTTP_400_BAD_REQUEST)

        existing = DiagnosisMaster.objects.filter(name__iexact=name).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.save(update_fields=['is_active'])
            return Response({
                "success": True, "created": False, "message": f"Reused existing diagnosis '{existing.name}'",
                "id": str(existing.id), "name": existing.name, "code": existing.code
            }, status=status.HTTP_200_OK)

        code = request.data.get('code', '').strip().upper() or generate_unique_code(DiagnosisMaster, 'DX', name)
        cat = request.data.get('category', 'General') or 'General'
        desc = request.data.get('description', '')

        obj = DiagnosisMaster.objects.create(name=name, code=code, category=cat, description=desc, is_active=True)
        DropdownMaster.objects.get_or_create(type='diagnosis', name=name)
        return Response({"success": True, "created": True, "message": "Diagnosis created successfully", "id": str(obj.id), "name": obj.name, "code": obj.code}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(DiagnosisMaster, pk=pk)
        if 'name' in request.data:
            name = normalize_master_name(request.data['name'])
            if name:
                dup = DiagnosisMaster.objects.filter(name__iexact=name).exclude(pk=obj.pk).first()
                if dup:
                    return Response({"success": False, "error": f"Diagnosis '{name}' already exists."}, status=status.HTTP_400_BAD_REQUEST)
                obj.name = name
        if 'category' in request.data:
            obj.category = request.data['category']
        if 'description' in request.data:
            obj.description = request.data['description']
        if 'code' in request.data and request.data['code']:
            obj.code = request.data['code'].strip().upper()
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Diagnosis updated successfully", "id": str(obj.id), "name": obj.name, "code": obj.code, "is_active": obj.is_active})

    def delete(self, request, pk):
        obj = get_object_or_404(DiagnosisMaster, pk=pk)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        return Response({"success": True, "message": "Diagnosis deactivated"})


# ─── 10. CLINICAL EXAMINATION MASTER API ─────────────────────────────────────

class ExaminationMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(ExaminationMaster, pk=pk)
            return Response({
                "id": str(obj.id), "name": obj.name, "code": obj.code,
                "description": obj.description, "category": obj.category,
                "is_active": obj.is_active, "display_order": obj.display_order
            })

        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        search = request.GET.get('search', '').strip()
        qs = ExaminationMaster.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        if search:
            qs = qs.filter(name__icontains=search)

        data = [{
            "id": str(item.id), "name": item.name, "code": item.code,
            "description": item.description, "category": item.category,
            "is_active": item.is_active, "display_order": item.display_order
        } for item in qs.order_by('display_order', 'name')]
        return Response(data)

    def post(self, request):
        name = normalize_master_name(request.data.get('name', ''))
        if not name or len(name) < 2:
            return Response({"success": False, "error": "Examination finding must be at least 2 characters long."}, status=status.HTTP_400_BAD_REQUEST)

        existing = ExaminationMaster.objects.filter(name__iexact=name).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.save(update_fields=['is_active'])
            return Response({
                "success": True, "created": False, "message": f"Reused existing examination '{existing.name}'",
                "id": str(existing.id), "name": existing.name, "code": existing.code
            }, status=status.HTTP_200_OK)

        code = request.data.get('code', '').strip().upper() or generate_unique_code(ExaminationMaster, 'EXAM', name)
        cat = request.data.get('category', 'General') or 'General'
        desc = request.data.get('description', '')

        obj = ExaminationMaster.objects.create(name=name, code=code, category=cat, description=desc, is_active=True)
        DropdownMaster.objects.get_or_create(type='observation', name=name)
        return Response({"success": True, "created": True, "message": "Examination created successfully", "id": str(obj.id), "name": obj.name, "code": obj.code}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(ExaminationMaster, pk=pk)
        if 'name' in request.data:
            name = normalize_master_name(request.data['name'])
            if name:
                dup = ExaminationMaster.objects.filter(name__iexact=name).exclude(pk=obj.pk).first()
                if dup:
                    return Response({"success": False, "error": f"Examination '{name}' already exists."}, status=status.HTTP_400_BAD_REQUEST)
                obj.name = name
        if 'category' in request.data:
            obj.category = request.data['category']
        if 'description' in request.data:
            obj.description = request.data['description']
        if 'code' in request.data and request.data['code']:
            obj.code = request.data['code'].strip().upper()
        if 'is_active' in request.data:
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Examination updated successfully", "id": str(obj.id), "name": obj.name, "code": obj.code, "is_active": obj.is_active})

    def delete(self, request, pk):
        obj = get_object_or_404(ExaminationMaster, pk=pk)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        return Response({"success": True, "message": "Examination deactivated"})


# ─── 11. TOOTH CONDITION MASTER API ──────────────────────────────────────────

class ToothConditionMasterAPIView(APIView):
    def get(self, request, pk=None):
        if pk:
            obj = get_object_or_404(ToothConditionMaster, pk=pk)
            return Response({
                "id": str(obj.id), "name": obj.name, "code": obj.code,
                "description": obj.description, "color": obj.color,
                "is_system": obj.is_system, "is_active": obj.is_active,
                "display_order": obj.display_order
            })

        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        search = request.GET.get('search', '').strip()
        qs = ToothConditionMaster.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        if search:
            qs = qs.filter(name__icontains=search)

        data = [{
            "id": str(item.id), "name": item.name, "code": item.code,
            "description": item.description, "color": item.color,
            "is_system": item.is_system, "is_active": item.is_active,
            "display_order": item.display_order
        } for item in qs.order_by('display_order', 'name')]
        return Response(data)

    def post(self, request):
        name = normalize_master_name(request.data.get('name', ''))
        if not name or len(name) < 2:
            return Response({"success": False, "error": "Tooth condition name must be at least 2 characters long."}, status=status.HTTP_400_BAD_REQUEST)

        existing = ToothConditionMaster.objects.filter(name__iexact=name).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.save(update_fields=['is_active'])
            return Response({
                "success": True, "created": False, "message": f"Reused existing condition '{existing.name}'",
                "id": str(existing.id), "name": existing.name, "code": existing.code
            }, status=status.HTTP_200_OK)

        code = request.data.get('code', '').strip().upper() or generate_unique_code(ToothConditionMaster, 'COND', name)
        color = request.data.get('color', '#3b82f6')
        desc = request.data.get('description', '')

        obj = ToothConditionMaster.objects.create(name=name, code=code, color=color, is_system=False, description=desc, is_active=True)
        return Response({"success": True, "created": True, "message": "Tooth condition created successfully", "id": str(obj.id), "name": obj.name, "code": obj.code}, status=status.HTTP_201_CREATED)

    def put(self, request, pk):
        obj = get_object_or_404(ToothConditionMaster, pk=pk)
        if 'name' in request.data:
            name = normalize_master_name(request.data['name'])
            if name:
                dup = ToothConditionMaster.objects.filter(name__iexact=name).exclude(pk=obj.pk).first()
                if dup:
                    return Response({"success": False, "error": f"Tooth condition '{name}' already exists."}, status=status.HTTP_400_BAD_REQUEST)
                obj.name = name
        if 'color' in request.data:
            obj.color = request.data['color']
        if 'description' in request.data:
            obj.description = request.data['description']
        if 'code' in request.data and request.data['code']:
            obj.code = request.data['code'].strip().upper()
        if 'is_active' in request.data:
            if obj.is_system and not request.data['is_active']:
                return Response({"success": False, "error": f"System reserved condition '{obj.name}' cannot be deactivated."}, status=status.HTTP_400_BAD_REQUEST)
            obj.is_active = bool(request.data['is_active'])
        obj.save()
        return Response({"success": True, "message": "Tooth condition updated successfully", "id": str(obj.id), "name": obj.name, "code": obj.code, "is_active": obj.is_active})

    def delete(self, request, pk):
        obj = get_object_or_404(ToothConditionMaster, pk=pk)
        if obj.is_system:
            return Response({"success": False, "error": f"System condition '{obj.name}' cannot be deactivated."}, status=status.HTTP_400_BAD_REQUEST)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        return Response({"success": True, "message": "Tooth condition deactivated"})


# ─── 12. AUTO-CREATE / REUSE MASTER API ───────────────────────────────────────

class AutoCreateOrReuseMasterAPIView(APIView):
    """
    Direct endpoint for frontend fields to resolve / auto-create a master value.
    Returns normalized object, created flag, and the current active catalogue.
    """
    def post(self, request):
        master_type = request.data.get('type', '')
        name = request.data.get('name', '')
        extra = request.data.get('extra', {})

        if not master_type or not name:
            return Response({"success": False, "error": "Both 'type' and 'name' are required."}, status=status.HTTP_400_BAD_REQUEST)

        obj, created, err = auto_create_or_reuse_master(master_type, name, extra)
        if err or not obj:
            return Response({"success": False, "error": err or "Failed to resolve master value."}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve updated active list for instant dropdown refresh
        m_type = str(master_type).lower().strip()
        if m_type in ['treatment', 'procedure']:
            options = list(TreatmentMaster.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
        elif m_type in ['diagnosis', 'category']:
            options = list(DiagnosisMaster.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
        elif m_type in ['examination', 'observation', 'finding']:
            options = list(ExaminationMaster.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
        elif m_type in ['tooth_condition', 'condition']:
            options = list(ToothConditionMaster.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
        else:
            options = []

        return Response({
            "success": True,
            "created": created,
            "id": str(obj.id),
            "name": obj.name,
            "code": getattr(obj, 'code', str(obj.id)),
            "type": master_type,
            "options": options,
            "message": f"Master '{obj.name}' {'created automatically' if created else 'reused from master'}"
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ─── 13. RESOLVE TREATMENT MASTERS BATCH API ──────────────────────────────────

class ResolveTreatmentMastersAPIView(APIView):
    """
    Batch resolve/auto-create all clinical fields submitted when saving a treatment.
    Processes: treatment, diagnosis, examination, condition.
    """
    def post(self, request):
        treatment_name = request.data.get('treatment')
        diagnosis_name = request.data.get('diagnosis')
        exam_name = request.data.get('examination')
        cond_name = request.data.get('condition')
        price = request.data.get('price', 400.0)

        results = {}

        if treatment_name:
            t_names = treatment_name if isinstance(treatment_name, list) else [treatment_name]
            resolved_t = []
            for t_name in t_names:
                if t_name and str(t_name).strip():
                    t_obj, t_created, t_err = auto_create_or_reuse_master('treatment', str(t_name).strip(), {'price': price})
                    if t_obj:
                        resolved_t.append({"id": str(t_obj.id), "name": t_obj.name, "created": t_created})
            if resolved_t:
                results['treatment'] = resolved_t if isinstance(treatment_name, list) else resolved_t[0]

        if diagnosis_name:
            d_names = diagnosis_name if isinstance(diagnosis_name, list) else [diagnosis_name]
            resolved_d = []
            for d_name in d_names:
                if d_name and str(d_name).strip():
                    d_obj, d_created, d_err = auto_create_or_reuse_master('diagnosis', str(d_name).strip())
                    if d_obj:
                        resolved_d.append({"id": str(d_obj.id), "name": d_obj.name, "created": d_created})
            if resolved_d:
                results['diagnosis'] = resolved_d if isinstance(diagnosis_name, list) else resolved_d[0]

        if exam_name:
            e_names = exam_name if isinstance(exam_name, list) else [exam_name]
            resolved_e = []
            for e_name in e_names:
                if e_name and str(e_name).strip():
                    e_obj, e_created, e_err = auto_create_or_reuse_master('examination', str(e_name).strip())
                    if e_obj:
                        resolved_e.append({"id": str(e_obj.id), "name": e_obj.name, "created": e_created})
            if resolved_e:
                results['examination'] = resolved_e if isinstance(exam_name, list) else resolved_e[0]

        if cond_name:
            c_names = cond_name if isinstance(cond_name, list) else [cond_name]
            resolved_c = []
            for c_name in c_names:
                if c_name and str(c_name).strip():
                    c_obj, c_created, c_err = auto_create_or_reuse_master('tooth_condition', str(c_name).strip())
                    if c_obj:
                        resolved_c.append({"id": str(c_obj.id), "name": c_obj.name, "created": c_created})
            if resolved_c:
                results['condition'] = resolved_c if isinstance(cond_name, list) else resolved_c[0]

        # Provide refreshed catalogues
        refreshed = {
            "treatments": list(TreatmentMaster.objects.filter(is_active=True).order_by('name').values_list('name', flat=True)),
            "diagnoses": list(DiagnosisMaster.objects.filter(is_active=True).order_by('name').values_list('name', flat=True)),
            "examinations": list(ExaminationMaster.objects.filter(is_active=True).order_by('name').values_list('name', flat=True)),
            "conditions": list(ToothConditionMaster.objects.filter(is_active=True).order_by('name').values_list('name', flat=True)),
        }

        return Response({
            "success": True,
            "resolved": results,
            "catalogues": refreshed
        })

