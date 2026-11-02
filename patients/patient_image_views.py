from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from .models import PatientImage, Patient, Visit
from .serializers import PatientImageSerializer
from .file_validators import validate_file, sanitize_filename, generate_unique_filename


class PatientImageListView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        patient_id = request.query_params.get('patient_id')
        if not patient_id:
            return Response({"error": "patient_id required"}, status=status.HTTP_400_BAD_REQUEST)
        images = PatientImage.objects.filter(patient_id=patient_id).order_by('-created_at')
        return Response(PatientImageSerializer(images, many=True, context={'request': request}).data)

    def post(self, request):
        patient_id = request.data.get('patient') or request.data.get('patient_id')
        if not patient_id:
            return Response({"error": "patient or patient_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        patient = get_object_or_404(Patient, id=patient_id)

        visit_id = request.data.get('visit') or request.data.get('visit_id')
        visit = Visit.objects.filter(id=visit_id).first() if visit_id else None

        image_type = request.data.get('image_type', 'RVG')
        notes = request.data.get('notes', '')
        tooth_number = request.data.get('tooth_number', '')

        # Check for multipart file upload
        uploaded_file = request.FILES.get('image') or request.FILES.get('file')
        if uploaded_file:
            try:
                validate_file(uploaded_file, allowed_types={'jpg', 'jpeg', 'png', 'webp', 'tif', 'tiff', 'dcm', 'bmp', 'pdf'})
            except ValidationError as ve:
                err_msg = ve.message if hasattr(ve, 'message') else str(ve)
                return Response({"error": err_msg}, status=status.HTTP_400_BAD_REQUEST)

            orig_name = sanitize_filename(uploaded_file.name)
            uploaded_file.name = generate_unique_filename(orig_name)

            img_obj = PatientImage.objects.create(
                patient=patient,
                visit=visit,
                image=uploaded_file,
                file_name=orig_name,
                image_type=image_type,
                tooth_number=tooth_number,
                notes=notes
            )
            return Response(PatientImageSerializer(img_obj, context={'request': request}).data, status=status.HTTP_201_CREATED)

        # Fallback to base64 image_data
        image_data = request.data.get('image_data')
        if image_data:
            img_obj = PatientImage.objects.create(
                patient=patient,
                visit=visit,
                image_data=image_data,
                file_name=request.data.get('file_name', f'{image_type}_scan'),
                image_type=image_type,
                tooth_number=tooth_number,
                notes=notes
            )
            return Response(PatientImageSerializer(img_obj, context={'request': request}).data, status=status.HTTP_201_CREATED)

        return Response({"error": "No file or image_data provided in request"}, status=status.HTTP_400_BAD_REQUEST)


class PatientImageDetailView(APIView):
    def delete(self, request, pk):
        img = get_object_or_404(PatientImage, pk=pk)
        if img.image:
            try:
                img.image.delete(save=False)
            except Exception:
                pass
        img.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
