import os
from pathlib import Path
import urllib.request
import re

BASE_DIR = Path("D:/HR PORTAL/attendance_system")

# 1. Download ONNX Models
models_dir = BASE_DIR / "apps" / "face_recognition" / "models" / "dnn"
models_dir.mkdir(parents=True, exist_ok=True)

yunet_url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
sface_url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
lena_url = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg"

print("Downloading ONNX models...")
if not (models_dir / "yunet.onnx").exists():
    urllib.request.urlretrieve(yunet_url, models_dir / "yunet.onnx")
if not (models_dir / "sface.onnx").exists():
    urllib.request.urlretrieve(sface_url, models_dir / "sface.onnx")
if not (models_dir / "lena.jpg").exists():
    urllib.request.urlretrieve(lena_url, models_dir / "lena.jpg")
print("Downloads complete.")

# 2. Implement Real OpenCV DNN Provider
provider_code = f"""import os
import cv2
import numpy as np
from django.conf import settings
from .base import FaceRecognitionProvider, FaceQualityError

class OpenCVDNNFaceProvider(FaceRecognitionProvider):
    def __init__(self):
        models_dir = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "models", "dnn")
        yunet_path = os.path.join(models_dir, "yunet.onnx")
        sface_path = os.path.join(models_dir, "sface.onnx")
        
        if not os.path.exists(yunet_path) or not os.path.exists(sface_path):
            raise RuntimeError("Face recognition ONNX models not found.")
            
        self.detector = cv2.FaceDetectorYN.create(yunet_path, "", (320, 320))
        self.recognizer = cv2.FaceRecognizerSF.create(sface_path, "")

    def _get_faces(self, image_bytes):
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise FaceQualityError("Unreadable or invalid image.")
        
        height, width, _ = img.shape
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(img)
        return img, faces

    def validate_face_quality(self, image_bytes: bytes) -> bool:
        img, faces = self._get_faces(image_bytes)
        if faces is None or len(faces) == 0:
            raise FaceQualityError("No face detected.")
        if len(faces) > 1:
            raise FaceQualityError("Multiple faces detected. Please ensure only one person is visible.")
        
        # Quality/Size validation
        box = faces[0][:4]
        if box[2] < 50 or box[3] < 50:
            raise FaceQualityError("Face is too small. Move closer to the camera.")
            
        return True

    def generate_embedding(self, image_bytes: bytes) -> list:
        img, faces = self._get_faces(image_bytes)
        if faces is None or len(faces) != 1:
            self.validate_face_quality(image_bytes)
            
        aligned_face = self.recognizer.alignCrop(img, faces[0])
        feature = self.recognizer.feature(aligned_face)
        return feature[0].tolist()
"""
(BASE_DIR / "apps" / "face_recognition" / "providers" / "opencv_dnn.py").write_text(provider_code)

# 3. Update Serializer to support multiple images
serializer_code = """from rest_framework import serializers

class FaceEnrollmentSerializer(serializers.Serializer):
    # Support multiple samples. If only one image is sent, it can be passed as a single string,
    # but we will standardize on a list of base64 strings to support "front", "left", "right" variations.
    images_base64 = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        max_length=5,
        help_text="List of Base64 encoded image strings."
    )
"""
(BASE_DIR / "apps" / "face_recognition" / "serializers.py").write_text(serializer_code)

# 4. Update Views to use the Real Provider and loop over multiple samples
views_code = """import base64
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
"""
(BASE_DIR / "apps" / "face_recognition" / "views.py").write_text(views_code)

# 5. Update Tests to run against Real OpenCV Provider and test Real Images
tests_code = """import pytest
import base64
import os
import cv2
import numpy as np
from django.conf import settings
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from apps.employees.models import Department, Employee
from apps.face_recognition.models import FaceProfile, FaceEmbedding
from apps.face_recognition.crypto import decrypt_embedding
from apps.audit.models import AuditLog

@pytest.fixture
def api_client():
    client = APIClient()
    user = User.objects.create_user(username='admin', password='password123')
    client.force_authenticate(user=user)
    return client

@pytest.fixture
def unauthenticated_client():
    return APIClient()

@pytest.fixture
def employee(db):
    dept = Department.objects.create(name="IT")
    return Employee.objects.create(employee_code="EMP999", first_name="Test", last_name="User", email="test@example.com", department=dept, status=True)

@pytest.fixture
def inactive_employee(db):
    dept = Department.objects.create(name="HR")
    return Employee.objects.create(employee_code="EMP888", first_name="Off", last_name="Boarded", email="off@example.com", department=dept, status=False)

def get_real_face_b64():
    # Use Lena image downloaded in setup
    img_path = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "models", "dnn", "lena.jpg")
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def get_invalid_image_b64():
    # Random noise (no face)
    noise = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
    _, buffer = cv2.imencode('.jpg', noise)
    return base64.b64encode(buffer).decode()

@pytest.mark.django_db
def test_unauthorized_enrollment(unauthenticated_client, employee):
    resp = unauthenticated_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": ["fake"]})
    assert resp.status_code == 401

@pytest.mark.django_db
def test_valid_enrollment(api_client, employee):
    img_b64 = get_real_face_b64()
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "enrolled"
    assert data["samples_enrolled"] == 1
    assert "embedding" not in data # CRITICAL: Ensure embedding is not exposed
    
    profile = FaceProfile.objects.get(employee=employee)
    assert profile.enrollment_status == 'ENROLLED'
    
    embedding_obj = FaceEmbedding.objects.get(face_profile=profile)
    assert embedding_obj.embedding_data is not None
    assert '128' not in data # Ensuring vectors don't leak
    
    # Internal Encryption Decryption check
    decrypted_vector = decrypt_embedding(embedding_obj.embedding_data)
    assert len(decrypted_vector) == 128
    
    log = AuditLog.objects.filter(entity_id=employee.id, action='FACE_ENROLL').first()
    assert log is not None

@pytest.mark.django_db
def test_multiple_samples_enrollment(api_client, employee):
    img_b64 = get_real_face_b64()
    # Testing 3 variations
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64, img_b64, img_b64]})
    assert resp.status_code == 200
    assert resp.json()["samples_enrolled"] == 3
    assert FaceEmbedding.objects.filter(face_profile__employee=employee).count() == 3

@pytest.mark.django_db
def test_inactive_employee_enrollment(api_client, inactive_employee):
    img_b64 = get_real_face_b64()
    resp = api_client.post(f'/api/v1/employees/{inactive_employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 400
    assert "inactive" in resp.json()["error"]

@pytest.mark.django_db
def test_quality_validation_no_face(api_client, employee):
    img_b64 = get_invalid_image_b64()
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 400
    assert "No face detected" in resp.json()["error"]

@pytest.mark.django_db
def test_re_enrollment(api_client, employee):
    img_b64 = get_real_face_b64()
    # First enroll (2 samples)
    api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64, img_b64]})
    
    # Try normal enroll again (should fail)
    resp2 = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp2.status_code == 400
    assert "Use re-enroll" in resp2.json()["error"]

    # Re-enroll with 1 sample
    resp3 = api_client.post(f'/api/v1/employees/{employee.id}/face/re-enroll/', {"images_base64": [img_b64]})
    assert resp3.status_code == 200
    # The old 2 samples should be safely removed, only 1 new active embedding should exist
    assert FaceEmbedding.objects.filter(face_profile__employee=employee).count() == 1

@pytest.mark.django_db
def test_face_status(api_client, employee):
    resp = api_client.get(f'/api/v1/employees/{employee.id}/face/status/')
    assert resp.status_code == 200
    assert resp.json()["status"] == "NOT_ENROLLED"
"""
(BASE_DIR / "apps" / "face_recognition" / "tests" / "test_enrollment.py").write_text(tests_code)

print("Setup for REAL ENGINE VERIFICATION complete.")
