from django.contrib import admin
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
