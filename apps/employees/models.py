from django.db import models
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
