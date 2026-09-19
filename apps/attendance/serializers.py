from rest_framework import serializers
from apps.devices.models import AttendanceDevice

class AttendanceEventSerializer(serializers.Serializer):
    device_code = serializers.CharField(required=True)
    action = serializers.ChoiceField(choices=['CHECK_IN', 'CHECK_OUT'], required=True)
    frames_base64 = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        required=True
    )
