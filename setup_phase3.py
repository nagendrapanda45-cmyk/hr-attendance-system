import os
from pathlib import Path
import re

BASE_DIR = Path("D:/HR PORTAL/attendance_system")

# 1. Temporarily force SQLite in .env so we can actually build the DB and Admin panel
env_path = BASE_DIR / ".env"
env_data = env_path.read_text()
env_data = re.sub(r'DATABASE_NAME=.*', 'DATABASE_NAME=sqlite3', env_data)
env_path.write_text(env_data)

# 2. Write customized Admin configurations

employees_admin = """from django.contrib import admin
from .models import Employee, Department

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_code', 'first_name', 'last_name', 'department', 'status', 'odoo_employee_id')
    list_filter = ('status', 'department')
    search_fields = ('employee_code', 'first_name', 'last_name', 'email')
    actions = ['initiate_face_enrollment', 'activate_employees', 'deactivate_employees']

    def initiate_face_enrollment(self, request, queryset):
        # Placeholder for Face Enrollment Phase
        self.message_user(request, "Face enrollment initiated for selected employees.")
    initiate_face_enrollment.short_description = "Initiate Face Enrollment"

    def activate_employees(self, request, queryset):
        queryset.update(status=True)
    
    def deactivate_employees(self, request, queryset):
        queryset.update(status=False)
"""
(BASE_DIR / "apps" / "employees" / "admin.py").write_text(employees_admin, encoding="utf-8")


attendance_admin = """from django.contrib import admin
from .models import AttendanceEvent, AttendanceSession

@admin.register(AttendanceEvent)
class AttendanceEventAdmin(admin.ModelAdmin):
    list_display = ('employee', 'device', 'event_type', 'timestamp', 'confidence_score', 'recognition_status')
    list_filter = ('event_type', 'recognition_status', 'device')
    search_fields = ('employee__employee_code', 'employee__first_name', 'employee__last_name')
    readonly_fields = ('employee', 'device', 'event_type', 'timestamp', 'confidence_score', 'liveness_score', 'recognition_status', 'source')

    def has_change_permission(self, request, obj=None):
        return False # Events are immutable

@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('employee', 'check_in_time', 'check_out_time', 'total_work_duration', 'status')
    list_filter = ('status',)
    search_fields = ('employee__employee_code',)
"""
(BASE_DIR / "apps" / "attendance" / "admin.py").write_text(attendance_admin, encoding="utf-8")


odoo_admin = """from django.contrib import admin
from .models import OdooEmployeeMapping, OdooSyncRecord

@admin.register(OdooEmployeeMapping)
class OdooEmployeeMappingAdmin(admin.ModelAdmin):
    list_display = ('employee', 'odoo_record_id')

@admin.register(OdooSyncRecord)
class OdooSyncRecordAdmin(admin.ModelAdmin):
    list_display = ('attendance_event', 'odoo_record_id', 'sync_status', 'attempt_count', 'last_attempt_at')
    list_filter = ('sync_status',)
    actions = ['retry_sync']

    def retry_sync(self, request, queryset):
        queryset.update(sync_status='PENDING', attempt_count=0)
        self.message_user(request, "Selected records queued for retry.")
    retry_sync.short_description = "Retry Failed Odoo Synchronization"
"""
(BASE_DIR / "apps" / "odoo_integration" / "admin.py").write_text(odoo_admin, encoding="utf-8")


# 3. Create Seed Data script
seed_data_script = """import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.contrib.auth.models import User
from apps.employees.models import Department, Employee
from apps.devices.models import AttendanceDevice

def seed():
    # Superuser
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        print("Superuser created (admin / admin123)")

    # Departments
    it_dept, _ = Department.objects.get_or_create(name="IT Department", description="Information Technology")
    hr_dept, _ = Department.objects.get_or_create(name="Human Resources", description="HR and Admin")

    # Employees
    Employee.objects.get_or_create(
        employee_code="EMP001",
        defaults={'first_name': "John", 'last_name': "Doe", 'email': "john.doe@example.com", 'department': it_dept, 'designation': "Developer", 'odoo_employee_id': 101}
    )
    Employee.objects.get_or_create(
        employee_code="EMP002",
        defaults={'first_name': "Jane", 'last_name': "Smith", 'email': "jane.smith@example.com", 'department': hr_dept, 'designation': "HR Manager", 'odoo_employee_id': 102}
    )

    # Devices
    AttendanceDevice.objects.get_or_create(
        device_code="DEV-ENT-01",
        defaults={'name': "Main Entrance Kiosk", 'location': "Lobby", 'device_type': "KIOSK", 'direction': "ENTRY", 'ip_address': "192.168.1.100"}
    )
    AttendanceDevice.objects.get_or_create(
        device_code="DEV-EXT-01",
        defaults={'name': "Main Exit Kiosk", 'location': "Lobby", 'device_type': "KIOSK", 'direction': "EXIT", 'ip_address': "192.168.1.101"}
    )
    print("Seed data created successfully.")

if __name__ == '__main__':
    seed()
"""
(BASE_DIR / "seed_data.py").write_text(seed_data_script, encoding="utf-8")

print("Phase 3 setup complete.")
