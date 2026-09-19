import json
from .base import FaceRecognitionProvider, FaceQualityError

class MockFaceProvider(FaceRecognitionProvider):
    def validate_face_quality(self, image_bytes: bytes) -> bool:
        # Mock validation based on payload content for testing
        if b'NO_FACE' in image_bytes:
            raise FaceQualityError("No face detected.")
        if b'MULTIPLE_FACES' in image_bytes:
            raise FaceQualityError("Multiple faces detected. Please ensure only one person is visible.")
        if b'POOR_QUALITY' in image_bytes:
            raise FaceQualityError("Image quality is too low. Please try again.")
        return True

    def generate_embedding(self, image_bytes: bytes) -> list:
        self.validate_face_quality(image_bytes)
        # Return a fake 128-d embedding
        return [0.0123] * 128
