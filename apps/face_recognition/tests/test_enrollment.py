import pytest
import base64
import os
import json
from django.conf import settings
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from apps.employees.models import Department, Employee
from apps.face_recognition.models import FaceProfile, FaceEmbedding
from apps.face_recognition.crypto import decrypt_embedding
from apps.audit.models import AuditLog
from apps.face_recognition.providers.opencv_dnn import OpenCVDNNFaceProvider
from apps.face_recognition.providers.base import FaceQualityError

def get_fixture_b64(filename):
    path = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "tests", "fixtures", filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def get_fixture_bytes(filename):
    path = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "tests", "fixtures", filename)
    with open(path, "rb") as f:
        return f.read()

@pytest.fixture
def api_client():
    client = APIClient()
    user = User.objects.create_user(username='admin_real', password='password123')
    client.force_authenticate(user=user)
    return client

@pytest.fixture
def unauthenticated_client():
    return APIClient()

@pytest.fixture
def employee(db):
    dept = Department.objects.create(name="IT Real")
    return Employee.objects.create(employee_code="EMP-REAL-1", first_name="Real", last_name="User", email="real@example.com", department=dept, status=True)

@pytest.fixture
def inactive_employee(db):
    dept = Department.objects.create(name="HR Real")
    return Employee.objects.create(employee_code="EMP-REAL-0", first_name="Off", last_name="Boarded", email="offreal@example.com", department=dept, status=False)


# ==========================================
# 1. DIRECT ENGINE TESTS (No HTTP/API)
# ==========================================
@pytest.mark.real_biometric
def test_real_detector_direct():
    provider = OpenCVDNNFaceProvider()
    img_bytes = get_fixture_bytes("single_face.jpg")
    # Must not raise an exception
    is_valid = provider.validate_face_quality(img_bytes)
    assert is_valid is True

@pytest.mark.real_biometric
def test_real_embedding_direct():
    provider = OpenCVDNNFaceProvider()
    img_bytes = get_fixture_bytes("single_face.jpg")
    embedding = provider.generate_embedding(img_bytes)
    
    assert embedding is not None
    assert isinstance(embedding, list)
    assert len(embedding) == 128
    assert all(isinstance(val, float) for val in embedding)
    # Validate it's not just a mock array
    assert embedding[0] != 0.0123
    assert embedding[1] != 0.0123

# ==========================================
# 2. REAL API ENROLLMENT TESTS
# ==========================================
@pytest.mark.django_db
@pytest.mark.real_biometric
def test_real_enrollment_api(api_client, employee):
    img_b64 = get_fixture_b64("single_face.jpg")
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 200
    
    data = resp.json()
    assert data["status"] == "enrolled"
    assert data["samples_enrolled"] == 1
    # Biometric isolation check
    assert "embedding" not in data 
    assert "embedding_data" not in data
    
    # Database check
    profile = FaceProfile.objects.get(employee=employee)
    assert profile.enrollment_status == 'ENROLLED'
    
    # Audit log check
    log = AuditLog.objects.filter(entity_id=employee.id, action='FACE_ENROLL').first()
    assert log is not None
    assert log.metadata.get("status") == "success"

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_real_multi_sample(api_client, employee):
    img_b64 = get_fixture_b64("single_face.jpg")
    # Sending 3 samples
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64, img_b64, img_b64]})
    assert resp.status_code == 200
    assert resp.json()["samples_enrolled"] == 3
    
    assert FaceEmbedding.objects.filter(face_profile__employee=employee).count() == 3

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_real_reenrollment(api_client, employee):
    img_b64 = get_fixture_b64("single_face.jpg")
    
    # 1. Initial Enroll
    api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64, img_b64]})
    assert FaceEmbedding.objects.filter(face_profile__employee=employee).count() == 2
    
    old_embedding_ids = list(FaceEmbedding.objects.filter(face_profile__employee=employee).values_list('id', flat=True))
    
    # 2. Try normal enroll again (should fail)
    resp_conflict = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp_conflict.status_code == 400
    
    # 3. Re-enroll
    resp_reenroll = api_client.post(f'/api/v1/employees/{employee.id}/face/re-enroll/', {"images_base64": [img_b64]})
    assert resp_reenroll.status_code == 200
    
    # Validate transaction cleanup
    current_embeddings = list(FaceEmbedding.objects.filter(face_profile__employee=employee).values_list('id', flat=True))
    assert len(current_embeddings) == 1
    assert current_embeddings[0] not in old_embedding_ids

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_real_encryption_mysql(api_client, employee):
    img_b64 = get_fixture_b64("single_face.jpg")
    api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    
    embedding_obj = FaceEmbedding.objects.get(face_profile__employee=employee)
    
    # Direct DB check: Ensure stored data is ciphertext, not plaintext JSON
    raw_db_value = embedding_obj.embedding_data
    assert raw_db_value is not None
    assert not raw_db_value.startswith("[")  # A JSON array would start with [
    
    # Verify Decryption works natively
    decrypted_vector = decrypt_embedding(raw_db_value)
    assert len(decrypted_vector) == 128
    assert isinstance(decrypted_vector[0], float)

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_raw_image_lifecycle(api_client, employee):
    import glob
    # Count image files in project before
    jpgs_before = len(glob.glob(os.path.join(settings.BASE_DIR, "**", "*.jpg"), recursive=True))
    
    img_b64 = get_fixture_b64("single_face.jpg")
    api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    
    # Count image files after to ensure no temporary file leaks
    jpgs_after = len(glob.glob(os.path.join(settings.BASE_DIR, "**", "*.jpg"), recursive=True))
    assert jpgs_after == jpgs_before

# ==========================================
# 3. REAL FAILURE CONDITIONS (Bad Images)
# ==========================================
@pytest.mark.django_db
@pytest.mark.real_biometric
def test_real_failure_no_face(api_client, employee):
    img_b64 = get_fixture_b64("no_face.jpg")
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 400
    assert "No face detected" in resp.json()["error"]

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_real_failure_multiple_faces(api_client, employee):
    img_b64 = get_fixture_b64("multiple_faces.jpg")
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 400
    assert "Multiple faces" in resp.json()["error"]

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_real_failure_poor_quality(api_client, employee):
    # This uses the tiny crop, so YuNet shouldn't find a 50x50 face
    img_b64 = get_fixture_b64("poor_quality.jpg")
    resp = api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 400
    # Depending on the exact detection logic, YuNet might find NO face or a tiny face.
    assert ("No face detected" in resp.json()["error"] or "Face is too small" in resp.json()["error"])

# ==========================================
# 4. API SECURITY TESTS
# ==========================================
@pytest.mark.django_db
@pytest.mark.real_biometric
def test_api_security_unauth(unauthenticated_client, employee):
    img_b64 = get_fixture_b64("single_face.jpg")
    resp = unauthenticated_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 401

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_api_security_inactive(api_client, inactive_employee):
    img_b64 = get_fixture_b64("single_face.jpg")
    resp = api_client.post(f'/api/v1/employees/{inactive_employee.id}/face/enroll/', {"images_base64": [img_b64]})
    assert resp.status_code == 400
    assert "inactive" in resp.json()["error"]
