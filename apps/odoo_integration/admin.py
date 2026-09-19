from django.contrib import admin
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
