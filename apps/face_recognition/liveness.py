import base64
import cv2
import numpy as np
from django.conf import settings
from apps.face_recognition.providers.opencv_dnn import OpenCVDNNFaceProvider

class LivenessError(Exception):
    pass

class LivenessProvider:
    def analyze_sequence(self, frames_b64):
        raise NotImplementedError("Subclasses must implement analyze_sequence")

class Geometric3DLivenessProvider(LivenessProvider):
    """
    Analyzes a sequence of frames for 3D head movement.
    A 2D photo (spoof) moving in front of a camera undergoes 2D transformations (translation, scale, rotation),
    which preserve the ratios of internal facial landmark distances.
    A real 3D head moving (e.g., turning slightly) will exhibit variance in these projected 2D ratios.
    """
    def __init__(self, frames_required=3):
        self.provider = OpenCVDNNFaceProvider()
        # Threshold for the variance of the geometric ratio across frames
        self.variance_threshold = getattr(settings, 'FACE_LIVENESS_VARIANCE_THRESHOLD', 0.005)
        self.frames_required = frames_required

    def _extract_ratio(self, face_data):
        # face_data from YuNet: [x, y, w, h, RE_x, RE_y, LE_x, LE_y, N_x, N_y, RM_x, RM_y, LM_x, LM_y, score]
        # YuNet outputs: 
        # Right Eye (4, 5) -> Note: OpenCV YuNet typically has right eye at index 4,5
        # Left Eye (6, 7)
        # Nose (8, 9)
        # Right Mouth (10, 11)
        # Left Mouth (12, 13)
        re = np.array([face_data[4], face_data[5]])
        le = np.array([face_data[6], face_data[7]])
        nose = np.array([face_data[8], face_data[9]])
        
        # Distance between eyes
        eye_dist = np.linalg.norm(re - le)
        
        # Distance from nose to eye center
        eye_center = (re + le) / 2.0
        nose_dist = np.linalg.norm(nose - eye_center)
        
        if nose_dist == 0:
            return 0.0
            
        return eye_dist / nose_dist

    def analyze_sequence(self, frames_b64):
        if len(frames_b64) < self.frames_required:
            raise LivenessError(f"Inconclusive: Not enough frames. Required {self.frames_required}.")
            
        ratios = []
        
        for b64 in frames_b64:
            try:
                img_data = base64.b64decode(b64)
            except Exception:
                raise LivenessError("Invalid image data.")
                
            # Use YuNet to get the face
            # OpenCVDNNFaceProvider._get_faces(img_data) returns an array of faces
            try:
                img, faces = self.provider._get_faces(img_data)
            except Exception:
                continue
                
            if faces is None or len(faces) == 0:
                ratios.append(None)
                continue
                
            if len(faces) > 1:
                raise LivenessError("Multiple faces detected during liveness.")
                
            face = faces[0]
            ratio = self._extract_ratio(face)
            ratios.append(ratio)
            
        valid_ratios = [r for r in ratios if r is not None]
        
        if len(valid_ratios) == 0:
            raise LivenessError("No face detected in sequence.")
            
        if len(valid_ratios) < self.frames_required:
            raise LivenessError("Inconclusive: Could not track face continuously.")
            
        # Calculate variance of the ratio
        variance = np.var(valid_ratios)
        
        # A live 3D head will have variance above the threshold. A static photo (even moving in 2D) will have near 0 variance.
        if variance >= self.variance_threshold:
            return {
                "live": True,
                "confidence": round(float(variance), 5)
            }
            
        return {
            "live": False,
            "confidence": round(float(variance), 5)
        }
