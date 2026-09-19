import os
import cv2
import numpy as np
from django.conf import settings
from .base import FaceRecognitionProvider, FaceQualityError

class OpenCVDNNFaceProvider(FaceRecognitionProvider):
    def __init__(self):
        models_dir = os.path.join(settings.BASE_DIR, "apps", "face_recognition", "models", "dnn")
        yunet_path = os.path.join(models_dir, "yunet.onnx")
        sface_path = os.path.join(models_dir, "sface.onnx")
        
        if not os.path.exists(yunet_path) or not os.path.exists(sface_path):
            raise RuntimeError("Face recognition ONNX models not found.")
            
        self.detector = cv2.FaceDetectorYN.create(yunet_path, "", (320, 320))
        self.recognizer = cv2.FaceRecognizerSF.create(sface_path, "")

    def _get_faces(self, image_bytes):
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise FaceQualityError("Unreadable or invalid image.")
        
        height, width, _ = img.shape
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(img)
        return img, faces

    def validate_face_quality(self, image_bytes: bytes) -> bool:
        img, faces = self._get_faces(image_bytes)
        if faces is None or len(faces) == 0:
            raise FaceQualityError("No face detected.")
        if len(faces) > 1:
            raise FaceQualityError("Multiple faces detected. Please ensure only one person is visible.")
        
        # Quality/Size validation
        box = faces[0][:4]
        if box[2] < 50 or box[3] < 50:
            raise FaceQualityError("Face is too small. Move closer to the camera.")
            
        return True

    def generate_embedding(self, image_bytes: bytes) -> list:
        img, faces = self._get_faces(image_bytes)
        if faces is None or len(faces) != 1:
            self.validate_face_quality(image_bytes)
            
        aligned_face = self.recognizer.alignCrop(img, faces[0])
        feature = self.recognizer.feature(aligned_face)
        return feature[0].tolist()
