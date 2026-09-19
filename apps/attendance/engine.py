from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.attendance.models import AttendanceEvent, AttendanceSession
from apps.devices.models import AttendanceDevice
from apps.face_recognition.liveness import Geometric3DLivenessProvider, LivenessError
from apps.face_recognition.services import recognize_face
from apps.face_recognition.providers.base import FaceQualityError
from apps.audit.models import AuditLog

class AttendanceEngineException(Exception):
    pass

class AttendanceEngine:
    def __init__(self):
        self.liveness_provider = Geometric3DLivenessProvider()

    def process_attendance(self, device_code, action, frames_base64, user):
        # 1. Device Validation
        try:
            device = AttendanceDevice.objects.get(device_code=device_code, status=True)
        except AttendanceDevice.DoesNotExist:
            self._log(user, 'ATTENDANCE_FAILED', {"error": "Invalid or inactive device."})
            raise AttendanceEngineException("Invalid or inactive device.")

        if device.direction == 'ENTRY' and action != 'CHECK_IN':
            self._log(user, 'ATTENDANCE_FAILED', {"error": "Device is ENTRY only."})
            raise AttendanceEngineException("This device only supports CHECK_IN.")
        if device.direction == 'EXIT' and action != 'CHECK_OUT':
            self._log(user, 'ATTENDANCE_FAILED', {"error": "Device is EXIT only."})
            raise AttendanceEngineException("This device only supports CHECK_OUT.")

        # 2. Liveness Check
        try:
            liveness_result = self.liveness_provider.analyze_sequence(frames_base64)
            if not liveness_result['live']:
                self._log(user, 'ATTENDANCE_FAILED', {"error": "Liveness spoof detected.", "liveness_confidence": liveness_result['confidence']})
                raise AttendanceEngineException("Liveness check failed (Spoof).")
        except LivenessError as e:
            self._log(user, 'ATTENDANCE_FAILED', {"error": str(e)})
            raise AttendanceEngineException(str(e))

        liveness_score = liveness_result['confidence']

        # 3. Recognition
        import base64
        probe_image_bytes = base64.b64decode(frames_base64[-1])
        try:
            recognition_result = recognize_face(probe_image_bytes)
        except FaceQualityError as e:
            self._log(user, 'ATTENDANCE_FAILED', {"error": str(e)})
            raise AttendanceEngineException(str(e))
        
        if not recognition_result['recognized']:
            self._log(user, 'ATTENDANCE_FAILED', {"error": "Face not recognized."})
            raise AttendanceEngineException("Face not recognized.")

        employee = recognition_result['employee']
        confidence_score = recognition_result['confidence']

        # Verify employee is active (recognition service usually handles this, but double check)
        if not employee.status:
            self._log(user, 'ATTENDANCE_FAILED', {"error": "Employee inactive."})
            raise AttendanceEngineException("Employee is inactive.")

        # 4. State Validation & Event Creation
        with transaction.atomic():
            now = timezone.now()
            
            # Check current open session
            open_session = AttendanceSession.objects.select_for_update().filter(
                employee=employee, 
                status='OPEN'
            ).first()

            if action == 'CHECK_IN':
                if open_session:
                    self._log(user, 'ATTENDANCE_REJECTED', {"error": "Duplicate ENTRY. Employee already checked in."})
                    raise AttendanceEngineException("Employee is already checked in.")
                
                # Create Event
                event = AttendanceEvent.objects.create(
                    employee=employee,
                    device=device,
                    event_type='CHECK_IN',
                    confidence_score=confidence_score,
                    liveness_score=liveness_score,
                    recognition_status='SUCCESS',
                    source='KIOSK',
                    timestamp=now
                )
                
                # Create Session
                AttendanceSession.objects.create(
                    employee=employee,
                    check_in_event=event,
                    check_in_time=now,
                    status='OPEN'
                )
                
            elif action == 'CHECK_OUT':
                if not open_session:
                    self._log(user, 'ATTENDANCE_REJECTED', {"error": "Invalid EXIT. No open session found."})
                    raise AttendanceEngineException("Employee is not checked in.")
                
                # Create Event
                event = AttendanceEvent.objects.create(
                    employee=employee,
                    device=device,
                    event_type='CHECK_OUT',
                    confidence_score=confidence_score,
                    liveness_score=liveness_score,
                    recognition_status='SUCCESS',
                    source='KIOSK',
                    timestamp=now
                )
                
                # Close Session
                open_session.check_out_event = event
                open_session.check_out_time = now
                open_session.total_work_duration = now - open_session.check_in_time
                open_session.status = 'CLOSED'
                open_session.save()

            self._log(user, 'ATTENDANCE_SUCCESS', {
                "employee_code": employee.employee_code,
                "action": action,
                "device_code": device_code
            })

        return {
            "employee_name": f"{employee.first_name} {employee.last_name}",
            "employee_code": employee.employee_code,
            "action": action,
            "timestamp": now.isoformat()
        }

    def _log(self, user, action, metadata):
        AuditLog.objects.create(
            user=user,
            action=action,
            metadata=metadata
        )
