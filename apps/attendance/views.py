from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from apps.attendance.serializers import AttendanceEventSerializer
from apps.attendance.engine import AttendanceEngine, AttendanceEngineException

class AttendanceCheckInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AttendanceEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        data = serializer.validated_data
        engine = AttendanceEngine()
        
        try:
            result = engine.process_attendance(
                device_code=data['device_code'],
                action=data['action'],
                frames_base64=data['frames_base64'],
                user=request.user
            )
            return Response(result, status=status.HTTP_200_OK)
        except AttendanceEngineException as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
