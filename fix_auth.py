import os
from pathlib import Path
import re

BASE_DIR = Path("D:/HR PORTAL/attendance_system")
settings_path = BASE_DIR / "config" / "settings" / "base.py"
settings_content = settings_path.read_text(encoding="utf-8")

# 1. Update DRF Auth Classes
drf_auth_str = """    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),"""

settings_content = re.sub(
    r"'DEFAULT_AUTHENTICATION_CLASSES': \([\s\S]*?\),",
    drf_auth_str,
    settings_content
)
settings_path.write_text(settings_content, encoding="utf-8")

# 2. Update config/urls.py for Token API
urls_path = BASE_DIR / "config" / "urls.py"
urls_data = urls_path.read_text(encoding="utf-8")

if "obtain_auth_token" not in urls_data:
    urls_data = urls_data.replace(
        "from django.urls import path, include",
        "from django.urls import path, include\nfrom rest_framework.authtoken.views import obtain_auth_token"
    )
    urls_data = urls_data.replace(
        "path('api/v1/', include('apps.employees.urls')),",
        "path('api/v1/auth/token/', obtain_auth_token),\n    path('api/v1/', include('apps.employees.urls')),"
    )
    urls_path.write_text(urls_data, encoding="utf-8")

# 3. Update tests to assert 401 and test token
test_path = BASE_DIR / "apps" / "employees" / "tests" / "test_api.py"
test_content = test_path.read_text(encoding="utf-8")

# Revert 403 to 401
test_content = test_content.replace("assert response.status_code == 403", "assert response.status_code == 401")

# Add token test
token_test_str = """
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
"""

if "def test_token_authentication" not in test_content:
    test_content += token_test_str

test_path.write_text(test_content, encoding="utf-8")
print("Fixes applied successfully.")
