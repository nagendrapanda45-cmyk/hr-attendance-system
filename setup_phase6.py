import os
from pathlib import Path
import re

BASE_DIR = Path("D:/HR PORTAL/attendance_system")

# 1. Update settings/base.py for Threshold
settings_path = BASE_DIR / "config" / "settings" / "base.py"
settings_content = settings_path.read_text()
if "FACE_RECOGNITION_THRESHOLD" not in settings_content:
    settings_content += "\n# OpenCV SFace Cosine Similarity Threshold (>= 0.363 is considered a match)\n"
    settings_content += "FACE_RECOGNITION_THRESHOLD = env.float('FACE_RECOGNITION_THRESHOLD', default=0.363)\n"
    settings_path.write_text(settings_content)

# 2. Create services.py
services_code = """import numpy as np
from django.conf import settings
from apps.face_recognition.models import FaceEmbedding
from apps.face_recognition.crypto import decrypt_embedding
from apps.face_recognition.providers.opencv_dnn import OpenCVDNNFaceProvider
from apps.face_recognition.providers.base import FaceQualityError

def compute_cosine_similarity(feature1, feature2):
    f1 = np.array(feature1)
    f2 = np.array(feature2)
    norm1 = np.linalg.norm(f1)
    norm2 = np.linalg.norm(f2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(f1, f2) / (norm1 * norm2))

def recognize_face(image_bytes):
    provider = OpenCVDNNFaceProvider()
    
    # This will raise FaceQualityError if no face or multiple faces
    probe_embedding = provider.generate_embedding(image_bytes)
    
    threshold = settings.FACE_RECOGNITION_THRESHOLD
    best_match = None
    highest_similarity = -1.0
    
    # Retrieve all embeddings for active employees
    # Note: In production at massive scale, we'd use a vector database (e.g., pgvector, FAISS, Milvus) 
    # For Phase 6, we retrieve active encrypted embeddings to compare in-memory natively.
    active_embeddings = FaceEmbedding.objects.filter(
        face_profile__employee__status=True
    ).select_related('face_profile__employee')
    
    for emb_record in active_embeddings:
        try:
            enrolled_vector = decrypt_embedding(emb_record.embedding_data)
            sim = compute_cosine_similarity(probe_embedding, enrolled_vector)
            if sim > highest_similarity:
                highest_similarity = sim
                best_match = emb_record.face_profile.employee
        except Exception:
            continue
            
    if highest_similarity >= threshold and best_match:
        return {
            "recognized": True,
            "employee": best_match,
            "confidence": highest_similarity
        }
        
    return {
        "recognized": False,
        "employee": None,
        "confidence": highest_similarity
    }
"""
(BASE_DIR / "apps" / "face_recognition" / "services.py").write_text(services_code)

# 3. Update serializers.py
serializers_path = BASE_DIR / "apps" / "face_recognition" / "serializers.py"
serializers_content = serializers_path.read_text()
if "FaceRecognitionSerializer" not in serializers_content:
    serializers_content += """

class FaceRecognitionSerializer(serializers.Serializer):
    image_base64 = serializers.CharField(required=True, help_text="Base64 encoded image string for recognition.")
"""
    serializers_path.write_text(serializers_content)

# 4. Update views.py
views_path = BASE_DIR / "apps" / "face_recognition" / "views.py"
views_content = views_path.read_text()
if "FaceRecognitionView" not in views_content:
    views_content += """
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
"""
    views_path.write_text(views_content)

# 5. Update urls.py
urls_path = BASE_DIR / "apps" / "face_recognition" / "urls.py"
urls_content = urls_path.read_text()
if "FaceRecognitionView" not in urls_content:
    urls_content = urls_content.replace(
        "from .views import FaceStatusView, FaceEnrollmentView",
        "from .views import FaceStatusView, FaceEnrollmentView, FaceRecognitionView"
    )
    urls_content = urls_content.replace(
        "]",
        "    path('face/recognize/', FaceRecognitionView.as_view(), name='face-recognize'),\n]"
    )
    urls_path.write_text(urls_content)

# 6. Create Phase 6 Test File
tests_code = """import pytest
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
    assert log.entity_id == enrolled_employee.id

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
"""
(BASE_DIR / "apps" / "face_recognition" / "tests" / "test_recognition.py").write_text(tests_code)

print("Phase 6 setup complete.")
