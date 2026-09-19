import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.contrib.auth.models import User
from apps.employees.models import Department, Employee
from apps.devices.models import AttendanceDevice

def seed():
    print("WARNING: This seed script is for DEVELOPMENT ONLY. Do NOT execute in production.")
    print("WARNING: It provisions hardcoded admin credentials and arbitrary employee data.")
    
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
