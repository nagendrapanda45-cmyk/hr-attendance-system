from rest_framework import serializers
from .models import Employee, Department

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class EmployeeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Employee
        # EXPLICITLY omit any face profiles or embeddings from API responses to protect biometric data
        fields = [
            'id', 'employee_code', 'first_name', 'last_name', 'email', 
            'phone', 'department', 'department_name', 'designation', 
            'status', 'odoo_employee_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
