import pytest
import base64
import os
from django.conf import settings
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from apps.employees.models import Department, Employee
from apps.face_recognition.models import FaceProfile, FaceEmbedding
from apps.audit.models import AuditLog

def get_fixture_b64(filename):
    path = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "tests", "fixtures", filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

@pytest.fixture
def api_client():
    client = APIClient()
    user = User.objects.create_user(username='admin_recog', password='password123')
    client.force_authenticate(user=user)
    return client

@pytest.fixture
def unauthenticated_client():
    return APIClient()

@pytest.fixture
def employee(db):
    dept = Department.objects.create(name="IT Recog")
    return Employee.objects.create(employee_code="EMP-RECOG-1", first_name="Recog", last_name="User", email="recog@example.com", department=dept, status=True)

@pytest.fixture
def inactive_employee(db):
    dept = Department.objects.create(name="HR Recog")
    return Employee.objects.create(employee_code="EMP-RECOG-INACT", first_name="Recog", last_name="Offboarded", email="recogoff@example.com", department=dept, status=False)

@pytest.fixture
def enrolled_employee(api_client, employee):
    img_b64 = get_fixture_b64("face1.jpg")
    api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img_b64]})
    return employee

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_recognition_known_face(api_client, enrolled_employee):
    # Probe with face1.jpg (exact same image, should be ~1.0 match)
    probe_b64 = get_fixture_b64("face1.jpg")
    resp = api_client.post('/api/v1/face/recognize/', {"image_base64": probe_b64})
    assert resp.status_code == 200
    data = resp.json()
    assert data["recognized"] is True
    assert data["employee_id"] == enrolled_employee.id
    assert "embedding" not in data
    
    log = AuditLog.objects.filter(action='FACE_RECOGNITION_SUCCESS').first()
    assert log is not None
    assert str(log.entity_id) == str(enrolled_employee.id)

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_recognition_different_image_same_person(api_client, enrolled_employee):
    # Probe with face2.jpg (different image of the same person)
    probe_b64 = get_fixture_b64("face2.jpg")
    resp = api_client.post('/api/v1/face/recognize/', {"image_base64": probe_b64})
    assert resp.status_code == 200
    data = resp.json()
    assert data["recognized"] is True
    assert data["employee_id"] == enrolled_employee.id

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_recognition_unknown_face(api_client, enrolled_employee):
    # Probe with face3.jpg (completely different person)
    probe_b64 = get_fixture_b64("face3.jpg")
    resp = api_client.post('/api/v1/face/recognize/', {"image_base64": probe_b64})
    assert resp.status_code == 200
    data = resp.json()
    assert data["recognized"] is False
    assert data["employee"] is None

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_recognition_multiple_faces(api_client):
    probe_b64 = get_fixture_b64("multiple_faces.jpg")
    resp = api_client.post('/api/v1/face/recognize/', {"image_base64": probe_b64})
    assert resp.status_code == 400
    assert "Multiple faces" in resp.json()["error"]

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_recognition_no_face(api_client):
    probe_b64 = get_fixture_b64("no_face.jpg")
    resp = api_client.post('/api/v1/face/recognize/', {"image_base64": probe_b64})
    assert resp.status_code == 400
    assert "No face" in resp.json()["error"]

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_recognition_inactive_employee(api_client, inactive_employee):
    # Enroll inactive employee by forcing it (api block bypassed natively for test setup)
    # Wait, the API blocks inactive employees. Let's make them active, enroll, then deactivate.
    inactive_employee.status = True
    inactive_employee.save()
    
    img_b64 = get_fixture_b64("face1.jpg")
    api_client.post(f'/api/v1/employees/{inactive_employee.id}/face/enroll/', {"images_base64": [img_b64]})
    
    inactive_employee.status = False
    inactive_employee.save()
    
    # Now try recognition
    resp = api_client.post('/api/v1/face/recognize/', {"image_base64": img_b64})
    assert resp.status_code == 200
    data = resp.json()
    assert data["recognized"] is False
    assert data["employee"] is None

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_recognition_api_security(unauthenticated_client):
    probe_b64 = get_fixture_b64("face1.jpg")
    resp = unauthenticated_client.post('/api/v1/face/recognize/', {"image_base64": probe_b64})
    assert resp.status_code == 401

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_recognition_multiple_enrollments(api_client, employee):
    img1_b64 = get_fixture_b64("face1.jpg")
    img2_b64 = get_fixture_b64("face2.jpg")
    # Enroll with 2 distinct samples
    api_client.post(f'/api/v1/employees/{employee.id}/face/enroll/', {"images_base64": [img1_b64, img2_b64]})
    
    # Recognize with the 2nd sample
    resp = api_client.post('/api/v1/face/recognize/', {"image_base64": img2_b64})
    assert resp.status_code == 200
    data = resp.json()
    assert data["recognized"] is True
    assert data["employee_id"] == employee.id
