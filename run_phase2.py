import os
import sys
from pathlib import Path
import pymysql
import re

BASE_DIR = Path("D:/HR PORTAL/attendance_system")

apps = [
    "employees", "face_recognition", "devices", "attendance", "odoo_integration", "audit", "common"
]

# Scaffold Apps
for app in apps:
    app_dir = BASE_DIR / "apps" / app
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "__init__.py").touch(exist_ok=True)
    with open(app_dir / "apps.py", "w", encoding="utf-8") as f:
        f.write(f"from django.apps import AppConfig\nclass {app.title().replace('_', '')}Config(AppConfig):\n    default_auto_field = 'django.db.models.BigAutoField'\n    name = 'apps.{app}'\n")
    (app_dir / "admin.py").write_text("from django.contrib import admin\n", encoding="utf-8")

# common/models.py
(BASE_DIR / "apps" / "common" / "models.py").write_text("""from django.db import models

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
""", encoding="utf-8")

# employees/models.py
(BASE_DIR / "apps" / "employees" / "models.py").write_text("""from django.db import models
from apps.common.models import TimeStampedModel

class Department(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Employee(TimeStampedModel):
    employee_code = models.CharField(max_length=50, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='employees')
    designation = models.CharField(max_length=100)
    status = models.BooleanField(default=True)
    odoo_employee_id = models.IntegerField(null=True, blank=True, unique=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_code})"
""", encoding="utf-8")

# face_recognition/models.py
(BASE_DIR / "apps" / "face_recognition" / "models.py").write_text("""from django.db import models
from apps.common.models import TimeStampedModel
from apps.employees.models import Employee

class FaceProfile(TimeStampedModel):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('ENROLLED', 'Enrolled'),
        ('FAILED', 'Failed'),
    )
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='face_profile')
    enrollment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    def __str__(self):
        return f"Face Profile: {self.employee.employee_code}"

class FaceEmbedding(TimeStampedModel):
    face_profile = models.ForeignKey(FaceProfile, on_delete=models.CASCADE, related_name='embeddings')
    embedding_data = models.TextField(help_text="Encrypted or serialized vector data. Do not expose via API.")
    model_version = models.CharField(max_length=50)
    quality_score = models.FloatField(default=0.0)

    def __str__(self):
        return f"Embedding for {self.face_profile.employee.employee_code}"
""", encoding="utf-8")

# devices/models.py
(BASE_DIR / "apps" / "devices" / "models.py").write_text("""from django.db import models
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
""", encoding="utf-8")

# attendance/models.py
(BASE_DIR / "apps" / "attendance" / "models.py").write_text("""from django.db import models
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

    def save, *args, **kwargs):
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
""", encoding="utf-8")

# odoo_integration/models.py
(BASE_DIR / "apps" / "odoo_integration" / "models.py").write_text("""from django.db import models
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
""", encoding="utf-8")

# audit/models.py
(BASE_DIR / "apps" / "audit" / "models.py").write_text("""from django.db import models
from django.conf import settings
from apps.common.models import TimeStampedModel

class AuditLog(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.action} on {self.entity_type} {self.entity_id}"

class SystemConfiguration(TimeStampedModel):
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.key
""", encoding="utf-8")

# Admin registrations
admin_code = "from django.contrib import admin\nfrom .models import {model}\n\n@admin.register({model})\nclass {model}Admin(admin.ModelAdmin):\n    pass\n"
(BASE_DIR / "apps" / "employees" / "admin.py").write_text("from django.contrib import admin\nfrom .models import Employee, Department\nadmin.site.register(Employee)\nadmin.site.register(Department)\n")
(BASE_DIR / "apps" / "face_recognition" / "admin.py").write_text("from django.contrib import admin\nfrom .models import FaceProfile, FaceEmbedding\nadmin.site.register(FaceProfile)\nadmin.site.register(FaceEmbedding)\n")
(BASE_DIR / "apps" / "devices" / "admin.py").write_text("from django.contrib import admin\nfrom .models import AttendanceDevice\nadmin.site.register(AttendanceDevice)\n")
(BASE_DIR / "apps" / "attendance" / "admin.py").write_text("from django.contrib import admin\nfrom .models import AttendanceEvent, AttendanceSession\nadmin.site.register(AttendanceEvent)\nadmin.site.register(AttendanceSession)\n")
(BASE_DIR / "apps" / "odoo_integration" / "admin.py").write_text("from django.contrib import admin\nfrom .models import OdooEmployeeMapping, OdooSyncRecord\nadmin.site.register(OdooEmployeeMapping)\nadmin.site.register(OdooSyncRecord)\n")
(BASE_DIR / "apps" / "audit" / "admin.py").write_text("from django.contrib import admin\nfrom .models import AuditLog, SystemConfiguration\nadmin.site.register(AuditLog)\nadmin.site.register(SystemConfiguration)\n")

# Update settings
settings_path = BASE_DIR / "config" / "settings" / "base.py"
settings_content = settings_path.read_text()
if "'apps.employees'" not in settings_content:
    insert_idx = settings_content.find("INSTALLED_APPS = [")
    end_idx = settings_content.find("]", insert_idx)
    new_apps = "    'apps.common',\n    'apps.employees',\n    'apps.face_recognition',\n    'apps.devices',\n    'apps.attendance',\n    'apps.odoo_integration',\n    'apps.audit',\n"
    settings_path.write_text(settings_content[:end_idx] + new_apps + settings_content[end_idx:])

# Try resolving MySQL password
passwords = ["", "root", "password", "admin", "mysql", "123456"]
success_pw = None
for pw in passwords:
    try:
        conn = pymysql.connect(host='127.0.0.1', user='root', password=pw)
        success_pw = pw
        conn.close()
        break
    except Exception:
        continue

if success_pw is not None:
    conn = pymysql.connect(host='127.0.0.1', user='root', password=success_pw)
    conn.cursor().execute("CREATE DATABASE IF NOT EXISTS attendance_db;")
    conn.close()
    
    env_path = BASE_DIR / ".env"
    env_data = env_path.read_text()
    env_data = re.sub(r'DATABASE_PASSWORD=.*', f'DATABASE_PASSWORD={success_pw}', env_data)
    env_path.write_text(env_data)
    print("MySQL Database setup completed.")
else:
    print("MySQL root password not found among common defaults.")

print("Models created and apps configured.")
