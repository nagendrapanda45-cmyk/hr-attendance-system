from django.urls import path
from .views import FaceStatusView, FaceEnrollmentView, FaceRecognitionView, FaceLivenessView

urlpatterns = [
    path('employees/<int:employee_id>/face/status/', FaceStatusView.as_view(), name='face-status'),
    path('employees/<int:employee_id>/face/enroll/', FaceEnrollmentView.as_view(), name='face-enroll'),
    path('employees/<int:employee_id>/face/re-enroll/', FaceEnrollmentView.as_view(), name='face-reenroll'),
    path('face/recognize/', FaceRecognitionView.as_view(), name='face-recognize'),
    path('face/liveness/', FaceLivenessView.as_view(), name='face-liveness'),
]
