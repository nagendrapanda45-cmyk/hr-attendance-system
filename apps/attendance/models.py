from django.db import models
from django.core.exceptions import ValidationError
from apps.common.models import TimeStampedModel
from apps.employees.models import Employee
from apps.devices.models import AttendanceDevice

class AttendanceEvent(models.Model):
    EVENT_CHOICES = (('CHECK_IN', 'Check In'), ('CHECK_OUT', 'Check Out'))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_events')
    device = models.ForeignKey(AttendanceDevice, on_delete=models.RESTRICT, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    confidence_score = models.FloatField(default=0.0)
    liveness_score = models.FloatField(default=0.0)
    recognition_status = models.CharField(max_length=50)
    source = models.CharField(max_length=50, default='KIOSK')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['employee', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.employee.employee_code} - {self.event_type} at {self.timestamp}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("AttendanceEvents are immutable and cannot be modified.")
        super().save(*args, **kwargs)

class AttendanceSession(TimeStampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_sessions')
    check_in_event = models.OneToOneField(AttendanceEvent, on_delete=models.RESTRICT, related_name='session_as_checkin')
    check_out_event = models.OneToOneField(AttendanceEvent, on_delete=models.RESTRICT, related_name='session_as_checkout', null=True, blank=True)
    check_in_time = models.DateTimeField()
    check_out_time = models.DateTimeField(null=True, blank=True)
    total_work_duration = models.DurationField(null=True, blank=True)
    status = models.CharField(max_length=50, default='OPEN')

    def __str__(self):
        return f"Session: {self.employee.employee_code} ({self.check_in_time.date()})"
