from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from .models import (
    ClinicProfile, ClinicTiming, AutoNumbering, Salutation, PatientRequiredFields,
    RoleDefaultPermissions, PharmacySettings, PrescriptionTemplate, DosageLabel
)

# ─── CLINIC PROFILE ─────────────────────────────────────────────────────────

class ClinicProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicProfile
        fields = '__all__'

class ClinicProfileAPIView(APIView):
    def get(self, request):
        obj = ClinicProfile.load()
        serializer = ClinicProfileSerializer(obj)
        return Response(serializer.data)

    def patch(self, request):
        obj = ClinicProfile.load()
        serializer = ClinicProfileSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

# ─── CLINIC TIMING ──────────────────────────────────────────────────────────

class ClinicTimingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicTiming
        fields = '__all__'

class ClinicTimingListCreateAPIView(generics.ListCreateAPIView):
    queryset = ClinicTiming.objects.all().order_by('id')
    serializer_class = ClinicTimingSerializer

class ClinicTimingUpdateAPIView(generics.UpdateAPIView):
    queryset = ClinicTiming.objects.all()
    serializer_class = ClinicTimingSerializer

# ─── AUTO NUMBERING ─────────────────────────────────────────────────────────

class AutoNumberingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoNumbering
        fields = '__all__'

class AutoNumberingAPIView(APIView):
    def get(self, request):
        obj = AutoNumbering.load()
        serializer = AutoNumberingSerializer(obj)
        return Response(serializer.data)

    def patch(self, request):
        obj = AutoNumbering.load()
        serializer = AutoNumberingSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

# ─── SALUTATION ─────────────────────────────────────────────────────────────

class SalutationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Salutation
        fields = '__all__'

class SalutationListCreateAPIView(generics.ListCreateAPIView):
    queryset = Salutation.objects.all()
    serializer_class = SalutationSerializer

class SalutationDeleteAPIView(generics.DestroyAPIView):
    queryset = Salutation.objects.all()

# ─── PATIENT REQUIRED FIELDS ────────────────────────────────────────────────

class PatientRequiredFieldsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientRequiredFields
        fields = '__all__'

class PatientRequiredFieldsAPIView(APIView):
    def get(self, request):
        obj = PatientRequiredFields.load()
        serializer = PatientRequiredFieldsSerializer(obj)
        return Response(serializer.data)

    def patch(self, request):
        obj = PatientRequiredFields.load()
        serializer = PatientRequiredFieldsSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

# ─── ROLE DEFAULT PERMISSIONS ───────────────────────────────────────────────

class RoleDefaultPermissionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleDefaultPermissions
        fields = '__all__'

class RoleDefaultPermissionsListView(APIView):
    """
    GET  /api/settings/role-defaults/     → list all roles with their permissions
    POST /api/settings/role-defaults/     → init defaults (idempotent)
    """
    def get(self, request):
        # Ensure all 4 roles exist
        RoleDefaultPermissions.get_or_create_defaults()
        qs = RoleDefaultPermissions.objects.all().order_by('role')
        return Response(RoleDefaultPermissionsSerializer(qs, many=True).data)

class RoleDefaultPermissionsDetailView(APIView):
    """
    GET   /api/settings/role-defaults/<role>/   → get one role
    PATCH /api/settings/role-defaults/<role>/   → update role permissions
    """
    def get(self, request, role):
        RoleDefaultPermissions.get_or_create_defaults()
        try:
            obj = RoleDefaultPermissions.objects.get(role=role)
        except RoleDefaultPermissions.DoesNotExist:
            return Response({'error': 'Role not found'}, status=404)
        return Response(RoleDefaultPermissionsSerializer(obj).data)

    def patch(self, request, role):
        RoleDefaultPermissions.get_or_create_defaults()
        try:
            obj = RoleDefaultPermissions.objects.get(role=role)
        except RoleDefaultPermissions.DoesNotExist:
            return Response({'error': 'Role not found'}, status=404)
        serializer = RoleDefaultPermissionsSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

# ─── PHARMACY SETTINGS ──────────────────────────────────────────────────────

class PharmacySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PharmacySettings
        fields = '__all__'

class PharmacySettingsAPIView(APIView):
    """
    GET   /api/settings/pharmacy/   → get current pharmacy settings
    PATCH /api/settings/pharmacy/   → update pharmacy settings
    """
    def get(self, request):
        obj = PharmacySettings.load()
        return Response(PharmacySettingsSerializer(obj).data)

    def patch(self, request):
        obj = PharmacySettings.load()
        serializer = PharmacySettingsSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

# ─── PRESCRIPTION TEMPLATES ─────────────────────────────────────────────────

class PrescriptionTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionTemplate
        fields = '__all__'

class PrescriptionTemplateListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/settings/prescription-templates/   → list all templates
    POST /api/settings/prescription-templates/   → create new template
    """
    queryset = PrescriptionTemplate.objects.filter(is_active=True).order_by('-created_at')
    serializer_class = PrescriptionTemplateSerializer

class PrescriptionTemplateDetailView(APIView):
    """
    GET    /api/settings/prescription-templates/<pk>/
    PATCH  /api/settings/prescription-templates/<pk>/
    DELETE /api/settings/prescription-templates/<pk>/
    """
    def get_object(self, pk):
        try:
            return PrescriptionTemplate.objects.get(pk=pk)
        except PrescriptionTemplate.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'Not found'}, status=404)
        return Response(PrescriptionTemplateSerializer(obj).data)

    def patch(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'Not found'}, status=404)
        serializer = PrescriptionTemplateSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({'error': 'Not found'}, status=404)
        obj.is_active = False
        obj.save()
        return Response({'status': 'deleted'})

# ─── DOSAGE LABELS ──────────────────────────────────────────────────────────

class DosageLabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = DosageLabel
        fields = '__all__'

class DosageLabelListView(APIView):
    """
    GET  /api/settings/dosage-labels/        → list all dosage labels
    POST /api/settings/dosage-labels/        → add a label
    DELETE /api/settings/dosage-labels/      → delete by label name
    """
    def get(self, request):
        # Seed defaults if empty
        if not DosageLabel.objects.exists():
            defaults = [
                ('1-0-1', 'Twice daily - morning & night'),
                ('1-1-1', 'Three times daily'),
                ('0-0-1', 'Once at night'),
                ('1-0-0', 'Once in the morning'),
                ('BD', 'Twice a day'),
                ('TID', 'Three times a day'),
                ('OD', 'Once a day'),
                ('SOS', 'As needed'),
                ('QID', 'Four times a day'),
                ('HS', 'At bedtime'),
                ('AC', 'Before meals'),
                ('PC', 'After meals'),
            ]
            for label, desc in defaults:
                DosageLabel.objects.get_or_create(label=label, defaults={'description': desc})
        qs = DosageLabel.objects.all().order_by('label')
        return Response(DosageLabelSerializer(qs, many=True).data)

    def post(self, request):
        label = request.data.get('label', '').strip()
        description = request.data.get('description', '').strip()
        if not label:
            return Response({'error': 'Label is required'}, status=400)
        obj, created = DosageLabel.objects.get_or_create(
            label=label, defaults={'description': description}
        )
        if not created:
            return Response({'error': 'Label already exists'}, status=400)
        return Response(DosageLabelSerializer(obj).data, status=201)

    def delete(self, request):
        label = request.data.get('label', '').strip()
        if not label:
            return Response({'error': 'Label required'}, status=400)
        DosageLabel.objects.filter(label=label).delete()
        return Response({'status': 'deleted'})
