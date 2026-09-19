from django.db import models
from apps.common.models import TimeStampedModel

class AttendanceDevice(TimeStampedModel):
    DIRECTION_CHOICES = (('ENTRY', 'Entry'), ('EXIT', 'Exit'), ('BOTH', 'Both'))
    name = models.CharField(max_length=100)
    device_code = models.CharField(max_length=50, unique=True, db_index=True)
    location = models.CharField(max_length=255)
    device_type = models.CharField(max_length=50)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    status = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.device_code})"
