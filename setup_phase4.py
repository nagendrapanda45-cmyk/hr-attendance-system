import os
from pathlib import Path
import re

BASE_DIR = Path("D:/HR PORTAL/attendance_system")

# 1. Update requirements to include django-filter
req_path = BASE_DIR / "requirements" / "base.txt"
if "django-filter" not in req_path.read_text():
    req_path.write_text(req_path.read_text() + "\ndjango-filter>=23.2\n")

# 2. Update settings to include django_filters and token auth
settings_path = BASE_DIR / "config" / "settings" / "base.py"
settings_content = settings_path.read_text()
if "'django_filters'" not in settings_content:
    # Add django_filters to INSTALLED_APPS
    insert_idx = settings_content.find("INSTALLED_APPS = [")
    end_idx = settings_content.find("]", insert_idx)
    settings_content = settings_content[:end_idx] + "    'django_filters',\n    'rest_framework.authtoken',\n" + settings_content[end_idx:]
    
    # Add DjangoFilterBackend to DRF settings
    drf_idx = settings_content.find("REST_FRAMEWORK = {")
    if drf_idx != -1:
        drf_end_idx = settings_content.find("}", drf_idx)
        drf_insert = "    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],\n"
        settings_content = settings_content[:drf_idx + 19] + "\n" + drf_insert + settings_content[drf_idx + 19:]
    settings_path.write_text(settings_content)

# 3. Create Serializers
serializers_content = """from rest_framework import serializers
from .models import Employee, Department

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class EmployeeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Employee
        # EXPLICITLY omit any face profiles or embeddings from API responses to protect biometric data
        fields = [
            'id', 'employee_code', 'first_name', 'last_name', 'email', 
            'phone', 'department', 'department_name', 'designation', 
            'status', 'odoo_employee_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
"""
(BASE_DIR / "apps" / "employees" / "serializers.py").write_text(serializers_content, encoding="utf-8")

# 4. Create Views
views_content = """from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import Employee, Department
from .serializers import EmployeeSerializer, DepartmentSerializer

class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all().order_by('name')
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all().select_related('department').order_by('employee_code')
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['department', 'status']
    search_fields = ['employee_code', 'first_name', 'last_name', 'email']

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        employee = self.get_object()
        employee.status = True
        employee.save()
        return Response({'status': 'activated', 'employee_code': employee.employee_code})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        employee = self.get_object()
        employee.status = False
        employee.save()
        return Response({'status': 'deactivated', 'employee_code': employee.employee_code})
"""
(BASE_DIR / "apps" / "employees" / "views.py").write_text(views_content, encoding="utf-8")

# 5. Create URLs
urls_content = """from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmployeeViewSet, DepartmentViewSet

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'departments', DepartmentViewSet, basename='department')

urlpatterns = [
    path('', include(router.urls)),
]
"""
(BASE_DIR / "apps" / "employees" / "urls.py").write_text(urls_content, encoding="utf-8")

# 6. Include employees URLs in root config/urls.py
urls_path = BASE_DIR / "config" / "urls.py"
urls_data = urls_path.read_text()
if "'api/v1/', include('apps.employees.urls')" not in urls_data:
    # Needs to import include if not already
    if "from django.urls import path, include" not in urls_data:
        urls_data = urls_data.replace("from django.urls import path", "from django.urls import path, include")
    
    urls_data = urls_data.replace("path('api/v1/ready/', ready_check),", "path('api/v1/ready/', ready_check),\n    path('api/v1/', include('apps.employees.urls')),")
    urls_path.write_text(urls_data)

# 7. Create Tests
tests_dir = BASE_DIR / "apps" / "employees" / "tests"
tests_dir.mkdir(exist_ok=True)
(tests_dir / "__init__.py").touch(exist_ok=True)
tests_content = """import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from apps.employees.models import Department, Employee

@pytest.fixture
def api_client():
    client = APIClient()
    user = User.objects.create_user(username='testadmin', password='testpassword')
    client.force_authenticate(user=user)
    return client

@pytest.fixture
def unauthenticated_client():
    return APIClient()

@pytest.fixture
def department(db):
    return Department.objects.create(name="Engineering")

@pytest.mark.django_db
def test_create_employee(api_client, department):
    payload = {
        "employee_code": "EMP003",
        "first_name": "Alice",
        "last_name": "Wonderland",
        "email": "alice@example.com",
        "department": department.id,
        "designation": "Software Engineer",
        "status": True
    }
    response = api_client.post('/api/v1/employees/', payload)
    assert response.status_code == 201
    data = response.json()
    assert data["employee_code"] == "EMP003"
    assert data["department_name"] == "Engineering"
    # Ensure biometric fields are strictly NOT exposed
    assert "face_profile" not in data
    assert "embeddings" not in data

@pytest.mark.django_db
def test_duplicate_employee_code_prevented(api_client, department):
    Employee.objects.create(
        employee_code="EMP004", first_name="Bob", last_name="Builder",
        email="bob@example.com", designation="Builder"
    )
    payload = {
        "employee_code": "EMP004", # Duplicate!
        "first_name": "Charlie",
        "last_name": "Chaplin",
        "email": "charlie@example.com",
        "designation": "Actor"
    }
    response = api_client.post('/api/v1/employees/', payload)
    assert response.status_code == 400
    assert "employee_code" in response.json()

@pytest.mark.django_db
def test_unauthorized_access(unauthenticated_client):
    response = unauthenticated_client.get('/api/v1/employees/')
    assert response.status_code == 401

@pytest.mark.django_db
def test_employee_activation_actions(api_client, department):
    employee = Employee.objects.create(
        employee_code="EMP005", first_name="Eve", last_name="Hacker",
        email="eve@example.com", designation="Security", status=True
    )
    # Deactivate
    response = api_client.post(f'/api/v1/employees/{employee.id}/deactivate/')
    assert response.status_code == 200
    employee.refresh_from_db()
    assert not employee.status

    # Reactivate
    response = api_client.post(f'/api/v1/employees/{employee.id}/activate/')
    assert response.status_code == 200
    employee.refresh_from_db()
    assert employee.status
"""
(tests_dir / "test_api.py").write_text(tests_content, encoding="utf-8")

print("Phase 4 setup files created.")
