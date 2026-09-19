import os
from pathlib import Path
import re

BASE_DIR = Path("D:/HR PORTAL/attendance_system")

# 1. Update settings/base.py for Threshold
settings_path = BASE_DIR / "config" / "settings" / "base.py"
settings_content = settings_path.read_text()
if "FACE_LIVENESS_BLINK_THRESHOLD" not in settings_content:
    settings_content += "\n# MediaPipe EAR threshold for blink detection (Liveness)\n"
    settings_content += "FACE_LIVENESS_BLINK_THRESHOLD = env.float('FACE_LIVENESS_BLINK_THRESHOLD', default=0.20)\n"
    settings_path.write_text(settings_content)

# 2. Create liveness.py
liveness_code = """import base64
import cv2
import numpy as np
from django.conf import settings

try:
    import mediapipe as mp
except ImportError:
    mp = None

class LivenessError(Exception):
    pass

class LivenessProvider:
    def analyze_sequence(self, frames_b64):
        raise NotImplementedError("Subclasses must implement analyze_sequence")

class MediaPipeBlinkLivenessProvider(LivenessProvider):
    def __init__(self, frames_required=3):
        if mp is None:
            raise RuntimeError("mediapipe not installed")
        self.mp_face_mesh = mp.solutions.face_mesh
        self.blink_threshold = getattr(settings, 'FACE_LIVENESS_BLINK_THRESHOLD', 0.20)
        self.frames_required = frames_required
        
        # Right eye indices in FaceMesh
        self.RIGHT_EYE = [33, 160, 158, 133, 153, 144]
        # Left eye indices
        self.LEFT_EYE = [362, 385, 387, 263, 373, 380]

    def _compute_ear(self, eye_pts):
        v1 = np.linalg.norm(np.array(eye_pts[1]) - np.array(eye_pts[5]))
        v2 = np.linalg.norm(np.array(eye_pts[2]) - np.array(eye_pts[4]))
        h = np.linalg.norm(np.array(eye_pts[0]) - np.array(eye_pts[3]))
        if h == 0.0:
            return 0.0
        return (v1 + v2) / (2.0 * h)

    def analyze_sequence(self, frames_b64):
        if len(frames_b64) < self.frames_required:
            raise LivenessError(f"Inconclusive: Not enough frames. Required {self.frames_required}.")
            
        ear_values = []
        
        with self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        ) as face_mesh:
            
            for b64 in frames_b64:
                try:
                    img_data = base64.b64decode(b64)
                    nparr = np.frombuffer(img_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception:
                    raise LivenessError("Invalid image data.")
                    
                if frame is None:
                    continue
                    
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb_frame)
                
                if not results.multi_face_landmarks:
                    ear_values.append(None)
                    continue
                    
                if len(results.multi_face_landmarks) > 1:
                    raise LivenessError("Multiple faces detected during liveness.")
                    
                landmarks = results.multi_face_landmarks[0].landmark
                h, w, _ = frame.shape
                
                def get_pts(indices):
                    return [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in indices]
                
                right_pts = get_pts(self.RIGHT_EYE)
                left_pts = get_pts(self.LEFT_EYE)
                
                right_ear = self._compute_ear(right_pts)
                left_ear = self._compute_ear(left_pts)
                avg_ear = (right_ear + left_ear) / 2.0
                ear_values.append(avg_ear)
                
        valid_ears = [ear for ear in ear_values if ear is not None]
        
        if len(valid_ears) == 0:
            raise LivenessError("No face detected in sequence.")
            
        if len(valid_ears) < self.frames_required:
            raise LivenessError("Inconclusive: Could not track face continuously.")
            
        min_ear = min(valid_ears)
        max_ear = max(valid_ears)
        
        # A blink is valid if EAR drops below threshold and rises back up
        if min_ear < self.blink_threshold and max_ear > (self.blink_threshold + 0.03):
            return {
                "live": True,
                "confidence": round((max_ear - min_ear), 4)
            }
            
        return {
            "live": False,
            "confidence": round((max_ear - min_ear), 4)
        }
"""
(BASE_DIR / "apps" / "face_recognition" / "liveness.py").write_text(liveness_code)

# 3. Update serializers.py
serializers_path = BASE_DIR / "apps" / "face_recognition" / "serializers.py"
serializers_content = serializers_path.read_text()
if "FaceLivenessSerializer" not in serializers_content:
    serializers_content += """
class FaceLivenessSerializer(serializers.Serializer):
    frames_base64 = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        help_text="Array of Base64 encoded image frames for liveness detection."
    )
"""
    serializers_path.write_text(serializers_content)

# 4. Update views.py
views_path = BASE_DIR / "apps" / "face_recognition" / "views.py"
views_content = views_path.read_text()
if "FaceLivenessView" not in views_content:
    views_content = "from apps.face_recognition.serializers import FaceLivenessSerializer\n" + views_content
    views_content = "from apps.face_recognition.liveness import MediaPipeBlinkLivenessProvider, LivenessError\n" + views_content
    views_content += """

class FaceLivenessView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FaceLivenessSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            frames = serializer.validated_data['frames_base64']
            provider = MediaPipeBlinkLivenessProvider()
            result = provider.analyze_sequence(frames)
            
            if result['live']:
                AuditLog.objects.create(
                    user=request.user,
                    action='LIVENESS_SUCCESS',
                    entity_type='Employee',
                    metadata={"confidence": result['confidence']}
                )
            else:
                AuditLog.objects.create(
                    user=request.user,
                    action='LIVENESS_SPOOF',
                    entity_type='Unknown',
                    metadata={"confidence": result['confidence']}
                )
            return Response(result)
                
        except LivenessError as e:
            msg = str(e)
            action = 'LIVENESS_INCONCLUSIVE' if 'Inconclusive' in msg else 'LIVENESS_FAILED'
            AuditLog.objects.create(
                user=request.user,
                action=action,
                metadata={"error": msg}
            )
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "An internal error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
"""
    views_path.write_text(views_content)

# 5. Update urls.py
urls_path = BASE_DIR / "apps" / "face_recognition" / "urls.py"
urls_content = urls_path.read_text()
if "FaceLivenessView" not in urls_content:
    urls_content = urls_content.replace(
        "FaceRecognitionView",
        "FaceRecognitionView, FaceLivenessView"
    )
    urls_content = urls_content.replace(
        "]",
        "    path('face/liveness/', FaceLivenessView.as_view(), name='face-liveness'),\n]"
    )
    urls_path.write_text(urls_content)

print("Phase 7 setup complete.")
