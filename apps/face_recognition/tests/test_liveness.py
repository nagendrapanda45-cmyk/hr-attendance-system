import pytest
import base64
import os
from django.conf import settings
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from apps.audit.models import AuditLog

def get_fixture_b64(filename):
    path = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "tests", "fixtures", filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

@pytest.fixture
def api_client():
    client = APIClient()
    user = User.objects.create_user(username='admin_liveness', password='password123')
    client.force_authenticate(user=user)
    return client

@pytest.fixture
def unauthenticated_client():
    return APIClient()

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_liveness_live_person(api_client):
    f1 = get_fixture_b64("live1.jpg")
    f2 = get_fixture_b64("live2.jpg")
    f3 = get_fixture_b64("live3.jpg")
    
    resp = api_client.post('/api/v1/face/liveness/', {"frames_base64": [f1, f2, f3]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["live"] is True
    assert data["confidence"] > 0
    
    log = AuditLog.objects.filter(action='LIVENESS_SUCCESS').first()
    assert log is not None

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_liveness_spoof_photo(api_client):
    f1 = get_fixture_b64("spoof1.jpg")
    f2 = get_fixture_b64("spoof2.jpg")
    f3 = get_fixture_b64("spoof3.jpg")
    
    # 2D transformations preserve geometric ratios -> zero/low variance -> SPOOF
    resp = api_client.post('/api/v1/face/liveness/', {"frames_base64": [f1, f2, f3]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["live"] is False
    # variance should be tiny
    assert data["confidence"] < getattr(settings, 'FACE_LIVENESS_VARIANCE_THRESHOLD', 0.005)
    
    log = AuditLog.objects.filter(action='LIVENESS_SPOOF').first()
    assert log is not None

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_liveness_no_face(api_client):
    f1 = get_fixture_b64("no_face.jpg")
    resp = api_client.post('/api/v1/face/liveness/', {"frames_base64": [f1, f1, f1]})
    assert resp.status_code == 400
    assert "No face detected" in resp.json()["error"]
    
    log = AuditLog.objects.filter(action='LIVENESS_FAILED').first()
    assert log is not None

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_liveness_multiple_faces(api_client):
    f1 = get_fixture_b64("multiple_faces.jpg")
    resp = api_client.post('/api/v1/face/liveness/', {"frames_base64": [f1, f1, f1]})
    assert resp.status_code == 400
    assert "Multiple faces" in resp.json()["error"]

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_liveness_inconclusive_frames(api_client):
    f1 = get_fixture_b64("single_face.jpg")
    resp = api_client.post('/api/v1/face/liveness/', {"frames_base64": [f1]})
    assert resp.status_code == 400
    assert "Inconclusive" in resp.json()["error"]
    
    log = AuditLog.objects.filter(action='LIVENESS_INCONCLUSIVE').first()
    assert log is not None

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_liveness_api_security(unauthenticated_client):
    f1 = get_fixture_b64("single_face.jpg")
    resp = unauthenticated_client.post('/api/v1/face/liveness/', {"frames_base64": [f1, f1, f1]})
    assert resp.status_code == 401
