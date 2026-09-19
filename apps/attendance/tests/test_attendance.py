import pytest
import base64
import os
from django.conf import settings
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from apps.employees.models import Employee, Department
from apps.devices.models import AttendanceDevice
from apps.attendance.models import AttendanceEvent, AttendanceSession
from apps.face_recognition.models import FaceEmbedding, FaceProfile
from apps.audit.models import AuditLog

# Import crypto specifically for real biometric integration setup
from cryptography.fernet import Fernet
import numpy as np
import cv2

def get_fixture_b64(filename):
    path = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "tests", "fixtures", filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

@pytest.fixture
def api_client():
    client = APIClient()
    user = User.objects.create_user(username='admin_attendance', password='password123')
    client.force_authenticate(user=user)
    return client

@pytest.fixture
def unauthenticated_client():
    return APIClient()

@pytest.fixture
def test_department():
    return Department.objects.create(name='Engineering')

@pytest.fixture
def test_employee(test_department):
    return Employee.objects.create(
        first_name='Test',
        last_name='User',
        email='test.user@company.com',
        employee_code='EMP-ATT-01',
        department=test_department,
        status=True
    )

@pytest.fixture
def inactive_employee(test_department):
    return Employee.objects.create(
        first_name='Inactive',
        last_name='User',
        email='inactive@company.com',
        employee_code='EMP-INACT-01',
        department=test_department,
        status=False
    )

@pytest.fixture
def device_entry():
    return AttendanceDevice.objects.create(
        name='Main Entrance',
        device_code='FRONT_DOOR_ENTRY',
        direction='ENTRY',
        location='HQ',
        device_type='KIOSK',
        status=True
    )

@pytest.fixture
def device_exit():
    return AttendanceDevice.objects.create(
        name='Main Exit',
        device_code='FRONT_DOOR_EXIT',
        direction='EXIT',
        location='HQ',
        device_type='KIOSK',
        status=True
    )

@pytest.fixture
def device_both():
    return AttendanceDevice.objects.create(
        name='Side Door',
        device_code='SIDE_DOOR_BOTH',
        direction='BOTH',
        location='HQ',
        device_type='KIOSK',
        status=True
    )

@pytest.fixture
def enrolled_employee(test_employee):
    # Enroll the employee with real OpenCV embeddings for `live3.jpg`
    from apps.face_recognition.providers.opencv_dnn import OpenCVDNNFaceProvider
    from apps.face_recognition.crypto import encrypt_embedding
    provider = OpenCVDNNFaceProvider()
    
    path = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "tests", "fixtures", "live3.jpg")
    with open(path, "rb") as f:
        image_bytes = f.read()
        
    embedding = provider.generate_embedding(image_bytes)
    encrypted_vector = encrypt_embedding(embedding)
    
    profile = FaceProfile.objects.create(employee=test_employee)
    FaceEmbedding.objects.create(
        face_profile=profile,
        embedding_data=encrypted_vector
    )
    return test_employee

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_live_entry(api_client, enrolled_employee, device_entry):
    f1 = get_fixture_b64("live1.jpg")
    f2 = get_fixture_b64("live2.jpg")
    f3 = get_fixture_b64("live3.jpg")
    
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_entry.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f2, f3]
    })
    
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    assert data['employee_code'] == enrolled_employee.employee_code
    assert data['action'] == "CHECK_IN"
    
    # Verify records created
    event = AttendanceEvent.objects.get(employee=enrolled_employee, event_type='CHECK_IN')
    assert event.device == device_entry
    assert event.confidence_score > 0
    assert event.liveness_score > 0
    
    session = AttendanceSession.objects.get(employee=enrolled_employee, status='OPEN')
    assert session.check_in_event == event
    
    # Audit log check
    assert AuditLog.objects.filter(action='ATTENDANCE_SUCCESS').exists()

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_live_exit(api_client, enrolled_employee, device_both):
    f1 = get_fixture_b64("live1.jpg")
    f2 = get_fixture_b64("live2.jpg")
    f3 = get_fixture_b64("live3.jpg")
    
    # Check in first
    api_client.post('/api/v1/attendance/event/', {
        "device_code": device_both.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f2, f3]
    })
    
    # Check out
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_both.device_code,
        "action": "CHECK_OUT",
        "frames_base64": [f1, f2, f3]
    })
    
    assert resp.status_code == 200
    
    session = AttendanceSession.objects.get(employee=enrolled_employee, status='CLOSED')
    assert session.check_out_event is not None
    assert session.check_out_time is not None
    assert session.total_work_duration is not None

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_spoof_fails(api_client, enrolled_employee, device_entry):
    f1 = get_fixture_b64("spoof1.jpg")
    f2 = get_fixture_b64("spoof2.jpg")
    f3 = get_fixture_b64("spoof3.jpg")
    
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_entry.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f2, f3]
    })
    
    assert resp.status_code == 400
    assert "Spoof" in resp.json()['error']
    assert AttendanceEvent.objects.count() == 0
    assert AttendanceSession.objects.count() == 0

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_unknown_face_fails(api_client, test_department, device_entry):
    # Do not enroll! Face is unknown.
    f1 = get_fixture_b64("live1.jpg")
    f2 = get_fixture_b64("live2.jpg")
    f3 = get_fixture_b64("live3.jpg")
    
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_entry.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f2, f3]
    })
    
    assert resp.status_code == 400
    assert "recognized" in resp.json()['error']
    assert AttendanceEvent.objects.count() == 0

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_no_face_fails(api_client, device_entry):
    f1 = get_fixture_b64("no_face.jpg")
    
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_entry.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f1, f1]
    })
    
    assert resp.status_code == 400
    assert AttendanceEvent.objects.count() == 0

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_inactive_employee(api_client, inactive_employee, device_entry):
    from apps.face_recognition.providers.opencv_dnn import OpenCVDNNFaceProvider
    from apps.face_recognition.crypto import encrypt_embedding
    provider = OpenCVDNNFaceProvider()
    path = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "tests", "fixtures", "live3.jpg")
    with open(path, "rb") as f:
        embedding = provider.generate_embedding(f.read())
    
    profile = FaceProfile.objects.create(employee=inactive_employee)
    FaceEmbedding.objects.create(
        face_profile=profile,
        embedding_data=encrypt_embedding(embedding)
    )
    
    f1 = get_fixture_b64("live1.jpg")
    f2 = get_fixture_b64("live2.jpg")
    f3 = get_fixture_b64("live3.jpg")
    
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_entry.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f2, f3]
    })
    
    assert resp.status_code == 400
    # Recognition shouldn't even match an inactive employee, or the engine blocks it
    assert AttendanceEvent.objects.count() == 0

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_duplicate_entry(api_client, enrolled_employee, device_both):
    f1 = get_fixture_b64("live1.jpg")
    f2 = get_fixture_b64("live2.jpg")
    f3 = get_fixture_b64("live3.jpg")
    
    api_client.post('/api/v1/attendance/event/', {
        "device_code": device_both.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f2, f3]
    })
    
    # Try again
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_both.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f2, f3]
    })
    
    assert resp.status_code == 400
    assert "already checked in" in resp.json()['error']
    assert AttendanceEvent.objects.count() == 1  # Only the first one

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_invalid_exit(api_client, enrolled_employee, device_exit):
    f1 = get_fixture_b64("live1.jpg")
    f2 = get_fixture_b64("live2.jpg")
    f3 = get_fixture_b64("live3.jpg")
    
    # Try to exit without entry
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_exit.device_code,
        "action": "CHECK_OUT",
        "frames_base64": [f1, f2, f3]
    })
    
    assert resp.status_code == 400
    assert "not checked in" in resp.json()['error']

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_device_validation(api_client, enrolled_employee, device_entry):
    f1 = get_fixture_b64("live1.jpg")
    f2 = get_fixture_b64("live2.jpg")
    f3 = get_fixture_b64("live3.jpg")
    
    # Use an ENTRY device for CHECK_OUT
    resp = api_client.post('/api/v1/attendance/event/', {
        "device_code": device_entry.device_code,
        "action": "CHECK_OUT",
        "frames_base64": [f1, f2, f3]
    })
    
    assert resp.status_code == 400
    assert "only supports CHECK_IN" in resp.json()['error']

@pytest.mark.django_db
@pytest.mark.real_biometric
def test_attendance_auth_failure(unauthenticated_client, device_both):
    f1 = get_fixture_b64("live1.jpg")
    resp = unauthenticated_client.post('/api/v1/attendance/event/', {
        "device_code": device_both.device_code,
        "action": "CHECK_IN",
        "frames_base64": [f1, f1, f1]
    })
    assert resp.status_code == 401
