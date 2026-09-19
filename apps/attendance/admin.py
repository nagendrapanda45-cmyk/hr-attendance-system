from django.contrib import admin
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
