from apps.face_recognition.liveness import Geometric3DLivenessProvider, LivenessError
from apps.face_recognition.serializers import FaceLivenessSerializer
import base64
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from apps.employees.models import Employee
from apps.face_recognition.models import FaceProfile, FaceEmbedding
from apps.face_recognition.serializers import FaceEnrollmentSerializer
from apps.face_recognition.providers.opencv_dnn import OpenCVDNNFaceProvider
from apps.face_recognition.providers.base import FaceQualityError
from apps.face_recognition.crypto import encrypt_embedding
from apps.audit.models import AuditLog
import logging

logger = logging.getLogger(__name__)

class FaceStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, employee_id):
        employee = get_object_or_404(Employee, id=employee_id)
        profile, created = FaceProfile.objects.get_or_create(employee=employee, defaults={'enrollment_status': 'NOT_ENROLLED'})
        
        # Check if actual embeddings exist to ensure consistent state
        active_embeddings = FaceEmbedding.objects.filter(face_profile=profile).count()
        actual_status = profile.enrollment_status if active_embeddings > 0 else 'NOT_ENROLLED'
        
        return Response({
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "status": actual_status,
            "active_samples": active_embeddings
        })

class FaceEnrollmentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, employee_id):
        employee = get_object_or_404(Employee, id=employee_id)
        
        if not employee.status:
            return Response({"error": "Cannot enroll face for an inactive employee."}, status=status.HTTP_400_BAD_REQUEST)

        profile, _ = FaceProfile.objects.get_or_create(employee=employee)
        if profile.enrollment_status == 'ENROLLED' and 're-enroll' not in request.path:
            return Response({"error": "Employee already enrolled. Use re-enroll endpoint."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = FaceEnrollmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        provider = OpenCVDNNFaceProvider()
        embeddings_to_save = []

        try:
            # 1. Validate and Generate Embeddings for all samples in memory
            for b64_img in serializer.validated_data['images_base64']:
                image_data = base64.b64decode(b64_img)
                # Raw image is processed and discarded here
                embedding = provider.generate_embedding(image_data)
                embeddings_to_save.append(embedding)

            # 2. Encrypt embeddings
            encrypted_samples = [encrypt_embedding(emb) for emb in embeddings_to_save]

            # 3. Securely persist to DB
            with transaction.atomic():
                if 're-enroll' in request.path:
                    # Safely deactivate/remove old active embeddings
                    FaceEmbedding.objects.filter(face_profile=profile).delete()

                for enc_emb in encrypted_samples:
                    FaceEmbedding.objects.create(
                        face_profile=profile,
                        embedding_data=enc_emb,
                        model_version="OpenCV_SFace_128d",
                        quality_score=0.99
                    )
                
                profile.enrollment_status = 'ENROLLED'
                profile.save()

                AuditLog.objects.create(
                    user=request.user,
                    action='FACE_ENROLL' if 're-enroll' not in request.path else 'FACE_REENROLL',
                    entity_type='Employee',
                    entity_id=employee.id,
                    metadata={"status": "success", "samples": len(embeddings_to_save)}
                )

            return Response({
                "status": "enrolled",
                "employee_id": employee.id,
                "samples_enrolled": len(embeddings_to_save),
                "message": "Face enrollment completed successfully."
            })

        except FaceQualityError as e:
            AuditLog.objects.create(
                user=request.user, action='FACE_ENROLL_FAILED', entity_type='Employee',
                entity_id=employee.id, metadata={"error": str(e)}
            )
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Enrollment error", exc_info=True)
            return Response({"error": "An internal error occurred during enrollment."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from apps.face_recognition.serializers import FaceRecognitionSerializer
from apps.face_recognition.services import recognize_face

class FaceRecognitionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FaceRecognitionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            image_data = base64.b64decode(serializer.validated_data['image_base64'])
            
            # Offload heavy lifting to service
            result = recognize_face(image_data)
            
            if result['recognized']:
                AuditLog.objects.create(
                    user=request.user,
                    action='FACE_RECOGNITION_SUCCESS',
                    entity_type='Employee',
                    entity_id=result['employee'].id,
                    metadata={"confidence": result['confidence']}
                )
                return Response({
                    "recognized": True,
                    "employee_id": result['employee'].id,
                    "employee_code": result['employee'].employee_code,
                    "confidence": round(result['confidence'], 4),
                    "message": "Face recognized successfully."
                })
            else:
                AuditLog.objects.create(
                    user=request.user,
                    action='FACE_RECOGNITION_UNKNOWN',
                    entity_type='Unknown',
                    metadata={"confidence": result['confidence']}
                )
                return Response({
                    "recognized": False,
                    "employee": None,
                    "message": "Unknown face."
                })
                
        except FaceQualityError as e:
            AuditLog.objects.create(
                user=request.user,
                action='FACE_RECOGNITION_FAILED',
                metadata={"error": str(e)}
            )
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Recognition error", exc_info=True)
            return Response({"error": "An internal error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FaceLivenessView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FaceLivenessSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            frames = serializer.validated_data['frames_base64']
            provider = Geometric3DLivenessProvider()
            result = provider.analyze_sequence(frames)
            
            if result['live']:
                AuditLog.objects.create(
                    user=request.user,
                    action='LIVENESS_SUCCESS',
                    entity_type='Employee',
                    metadata={"confidence": result['confidence']}
                )
            else:
                AuditLog.objects.create(
                    user=request.user,
                    action='LIVENESS_SPOOF',
                    entity_type='Unknown',
                    metadata={"confidence": result['confidence']}
                )
            return Response(result)
                
        except LivenessError as e:
            msg = str(e)
            action = 'LIVENESS_INCONCLUSIVE' if 'Inconclusive' in msg else 'LIVENESS_FAILED'
            AuditLog.objects.create(
                user=request.user,
                action=action,
                metadata={"error": msg}
            )
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "An internal error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
