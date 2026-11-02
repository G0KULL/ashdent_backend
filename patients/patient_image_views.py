from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import PatientImage, Patient, Visit
from .serializers import PatientImageSerializer

class PatientImageListView(APIView):
    def get(self, request):
        patient_id = request.query_params.get('patient_id')
        if not patient_id:
            return Response({"error": "patient_id required"}, status=status.HTTP_400_BAD_REQUEST)
        images = PatientImage.objects.filter(patient_id=patient_id).order_by('-created_at')
        return Response(PatientImageSerializer(images, many=True).data)

    def post(self, request):
        serializer = PatientImageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PatientImageDetailView(APIView):
    def delete(self, request, pk):
        img = get_object_or_404(PatientImage, pk=pk)
        img.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
