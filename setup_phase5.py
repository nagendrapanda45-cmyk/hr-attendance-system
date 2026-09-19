import os
from pathlib import Path
import re
from cryptography.fernet import Fernet

BASE_DIR = Path("D:/HR PORTAL/attendance_system")

# 1. Update .env with ENCRYPTION_KEY if not present
env_path = BASE_DIR / ".env"
env_content = env_path.read_text()
if "FACE_ENCRYPTION_KEY=" not in env_content:
    key = Fernet.generate_key().decode()
    env_content += f"\nFACE_ENCRYPTION_KEY={key}\n"
    env_path.write_text(env_content)

# 2. Update config/settings/base.py
settings_path = BASE_DIR / "config" / "settings" / "base.py"
settings_content = settings_path.read_text()
if "FACE_ENCRYPTION_KEY" not in settings_content:
    settings_content += "\nFACE_ENCRYPTION_KEY = env('FACE_ENCRYPTION_KEY', default='')\n"
    settings_path.write_text(settings_content)

# 3. Create Crypto Module
crypto_code = """from django.conf import settings
from cryptography.fernet import Fernet
import json

def get_fernet():
    key = settings.FACE_ENCRYPTION_KEY
    if not key:
        raise ValueError("FACE_ENCRYPTION_KEY is not set.")
    return Fernet(key.encode())

def encrypt_embedding(embedding_list):
    f = get_fernet()
    data = json.dumps(embedding_list).encode()
    return f.encrypt(data).decode()

def decrypt_embedding(encrypted_str):
    f = get_fernet()
    data = f.decrypt(encrypted_str.encode())
    return json.loads(data.decode())
"""
(BASE_DIR / "apps" / "face_recognition" / "crypto.py").write_text(crypto_code)

# 4. Create Provider Abstraction
providers_dir = BASE_DIR / "apps" / "face_recognition" / "providers"
providers_dir.mkdir(exist_ok=True)
(providers_dir / "__init__.py").touch(exist_ok=True)

base_provider_code = """from abc import ABC, abstractmethod

class FaceQualityError(Exception):
    pass

class FaceRecognitionProvider(ABC):
    @abstractmethod
    def validate_face_quality(self, image_bytes: bytes) -> bool:
        pass

    @abstractmethod
    def generate_embedding(self, image_bytes: bytes) -> list:
        pass
"""
(providers_dir / "base.py").write_text(base_provider_code)

mock_provider_code = """import json
from .base import FaceRecognitionProvider, FaceQualityError

class MockFaceProvider(FaceRecognitionProvider):
    def validate_face_quality(self, image_bytes: bytes) -> bool:
        # Mock validation based on payload content for testing
        if b'NO_FACE' in image_bytes:
            raise FaceQualityError("No face detected.")
        if b'MULTIPLE_FACES' in image_bytes:
            raise FaceQualityError("Multiple faces detected. Please ensure only one person is visible.")
        if b'POOR_QUALITY' in image_bytes:
            raise FaceQualityError("Image quality is too low. Please try again.")
        return True

    def generate_embedding(self, image_bytes: bytes) -> list:
        self.validate_face_quality(image_bytes)
        # Return a fake 128-d embedding
        return [0.0123] * 128
"""
(providers_dir / "mock.py").write_text(mock_provider_code)

# 5. Create Serializers
serializers_code = """from rest_framework import serializers

class FaceEnrollmentSerializer(serializers.Serializer):
    image_base64 = serializers.CharField(required=True, help_text="Base64 encoded image data")
"""
(BASE_DIR / "apps" / "face_recognition" / "serializers.py").write_text(serializers_code)

# 6. Create Views
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
from apps.face_recognition.providers.mock import MockFaceProvider
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
        return Response({
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "status": profile.enrollment_status
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

        try:
            image_data = base64.b64decode(serializer.validated_data['image_base64'])
            provider = MockFaceProvider() # Abstraction layer
            
            embedding = provider.generate_embedding(image_data)
            encrypted_embedding = encrypt_embedding(embedding)

            with transaction.atomic():
                if 're-enroll' in request.path:
                    # Deactivate/Remove old embeddings safely
                    FaceEmbedding.objects.filter(face_profile=profile).delete()

                FaceEmbedding.objects.create(
                    face_profile=profile,
                    embedding_data=encrypted_embedding,
                    model_version="mock_v1",
                    quality_score=0.99
                )
                
                profile.enrollment_status = 'ENROLLED'
                profile.save()

                AuditLog.objects.create(
                    user=request.user,
                    action='FACE_ENROLL' if 're-enroll' not in request.path else 'FACE_REENROLL',
                    entity_type='Employee',
                    entity_id=employee.id,
                    metadata={"status": "success"}
                )

            return Response({
                "status": "enrolled",
                "employee_id": employee.id,
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

# 7. Create URLs
urls_code = """from django.urls import path
from .views import FaceStatusView, FaceEnrollmentView

urlpatterns = [
    path('employees/<int:employee_id>/face/status/', FaceStatusView.as_view(), name='face-status'),
    path('employees/<int:employee_id>/face/enroll/', FaceEnrollmentView.as_view(), name='face-enroll'),
    path('employees/<int:employee_id>/face/re-enroll/', FaceEnrollmentView.as_view(), name='face-reenroll'),
]
"""
(BASE_DIR / "apps" / "face_recognition" / "urls.py").write_text(urls_code)

# 8. Hook into root urls
root_urls = BASE_DIR / "config" / "urls.py"
urls_data = root_urls.read_text()
if "'apps.face_recognition.urls'" not in urls_data:
    urls_data = urls_data.replace(
        "path('api/v1/', include('apps.employees.urls')),",
        "path('api/v1/', include('apps.employees.urls')),\n    path('api/v1/', include('apps.face_recognition.urls')),"
    )
    root_urls.write_text(urls_data)

# 9. Create Tests
tests_dir = BASE_DIR / "apps" / "face_recognition" / "tests"
tests_dir.mkdir(exist_ok=True)
(tests_dir / "__init__.py").touch(exist_ok=True)

test_code = """import pytest
import base64
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from apps.employees.models import Department, Employee
from apps.face_recognition.models import FaceProfile, FaceEmbedding
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

@pytest.mark.django_db
def test_unauthorized_enrollment(unauthenticated_client, employee):
    resp = unauthenticated_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"image_base64": "fake"})
    assert resp.status_code == 401

@pytest.mark.django_db
def test_valid_enrollment(api_client, employee):
    img_b64 = base64.b64encode(b'VALID_IMAGE').decode()
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"image_base64": img_b64})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "enrolled"
    assert "embedding" not in data # CRITICAL: Ensure embedding is not exposed
    
    profile = FaceProfile.objects.get(employee=employee)
    assert profile.enrollment_status == 'ENROLLED'
    
    embedding = FaceEmbedding.objects.get(face_profile=profile)
    assert embedding.embedding_data is not None
    assert '128' not in data # Ensuring vectors don't leak
    
    log = AuditLog.objects.filter(entity_id=employee.id, action='FACE_ENROLL').first()
    assert log is not None

@pytest.mark.django_db
def test_inactive_employee_enrollment(api_client, inactive_employee):
    img_b64 = base64.b64encode(b'VALID_IMAGE').decode()
    resp = api_client.post(f'/api/v1/employees/{inactive_employee.id}/face/enroll/', {"image_base64": img_b64})
    assert resp.status_code == 400
    assert "inactive" in resp.json()["error"]

@pytest.mark.django_db
def test_quality_validation_no_face(api_client, employee):
    img_b64 = base64.b64encode(b'NO_FACE').decode()
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"image_base64": img_b64})
    assert resp.status_code == 400
    assert "No face detected" in resp.json()["error"]

@pytest.mark.django_db
def test_quality_validation_multiple_faces(api_client, employee):
    img_b64 = base64.b64encode(b'MULTIPLE_FACES').decode()
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"image_base64": img_b64})
    assert resp.status_code == 400
    assert "Multiple faces" in resp.json()["error"]

@pytest.mark.django_db
def test_re_enrollment(api_client, employee):
    img_b64 = base64.b64encode(b'VALID_IMAGE').decode()
    # First enroll
    api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"image_base64": img_b64})
    
    # Try normal enroll again (should fail)
    resp2 = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"image_base64": img_b64})
    assert resp2.status_code == 400
    assert "Use re-enroll" in resp2.json()["error"]

    # Re-enroll
    resp3 = api_client.post(f'/api/v1/employees/{employee.id}/face/re-enroll/', {"image_base64": img_b64})
    assert resp3.status_code == 200
    assert FaceEmbedding.objects.filter(face_profile__employee=employee).count() == 1 # Replaced

@pytest.mark.django_db
def test_face_status(api_client, employee):
    resp = api_client.get(f'/api/v1/employees/{employee.id}/face/status/')
    assert resp.status_code == 200
    assert resp.json()["status"] == "NOT_ENROLLED"
"""
(tests_dir / "test_enrollment.py").write_text(test_code)

print("Phase 5 scripts generated successfully.")
