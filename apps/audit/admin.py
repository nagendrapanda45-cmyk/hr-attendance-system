from django.contrib import admin
from .models import AuditLog, SystemConfiguration
admin.site.register(AuditLog)
admin.site.register(SystemConfiguration)
