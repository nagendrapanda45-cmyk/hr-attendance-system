from abc import ABC, abstractmethod

class FaceQualityError(Exception):
    pass

class FaceRecognitionProvider(ABC):
    @abstractmethod
    def validate_face_quality(self, image_bytes: bytes) -> bool:
        pass

    @abstractmethod
    def generate_embedding(self, image_bytes: bytes) -> list:
        pass
