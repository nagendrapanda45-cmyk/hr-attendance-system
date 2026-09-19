from django.db import models
from apps.common.models import TimeStampedModel
from apps.employees.models import Employee
from apps.attendance.models import AttendanceEvent

class OdooEmployeeMapping(TimeStampedModel):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='odoo_mapping_ext')
    odoo_record_id = models.IntegerField(unique=True, db_index=True)

    def __str__(self):
        return f"Map: {self.employee.employee_code} -> Odoo:{self.odoo_record_id}"

class OdooSyncRecord(TimeStampedModel):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'), ('SYNCING', 'Syncing'), 
        ('SUCCESS', 'Success'), ('FAILED', 'Failed'), ('RETRYING', 'Retrying')
    )
    attendance_event = models.OneToOneField(AttendanceEvent, on_delete=models.CASCADE, related_name='odoo_sync_record')
    odoo_record_id = models.IntegerField(null=True, blank=True)
    sync_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    attempt_count = models.IntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Sync {self.attendance_event.id} - {self.sync_status}"
