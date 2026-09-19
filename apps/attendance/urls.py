from django.urls import path
from .views import AttendanceCheckInView

urlpatterns = [
    path('event/', AttendanceCheckInView.as_view(), name='attendance-event'),
]
