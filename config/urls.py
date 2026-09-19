from django.contrib import admin
from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "healthy", "service": "django"})

def ready_check(request):
    return JsonResponse({"status": "ready"})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health/', health_check),
    path('api/v1/ready/', ready_check),
    path('api/v1/auth/token/', obtain_auth_token),
    path('api/v1/', include('apps.employees.urls')),
    path('api/v1/', include('apps.face_recognition.urls')),
    path('api/v1/attendance/', include('apps.attendance.urls')),
]