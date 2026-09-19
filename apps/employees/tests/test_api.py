import pytest
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

@pytest.mark.django_db
def test_token_authentication(db):
    user = User.objects.create_user(username='tokentest', password='password123')
    client = APIClient()
    
    # Obtain token
    response = client.post('/api/v1/auth/token/', {'username': 'tokentest', 'password': 'password123'})
    assert response.status_code == 200
    token = response.json()['token']
    
    # Use token
    client.credentials(HTTP_AUTHORIZATION='Token ' + token)
    response = client.get('/api/v1/employees/')
    assert response.status_code == 200
