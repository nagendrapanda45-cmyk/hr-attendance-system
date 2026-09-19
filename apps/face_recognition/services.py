import numpy as np
from django.conf import settings
from apps.face_recognition.models import FaceEmbedding
from apps.face_recognition.crypto import decrypt_embedding
from apps.face_recognition.providers.opencv_dnn import OpenCVDNNFaceProvider
from apps.face_recognition.providers.base import FaceQualityError

def compute_cosine_similarity(feature1, feature2):
    f1 = np.array(feature1)
    f2 = np.array(feature2)
    norm1 = np.linalg.norm(f1)
    norm2 = np.linalg.norm(f2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(f1, f2) / (norm1 * norm2))

def recognize_face(image_bytes):
    provider = OpenCVDNNFaceProvider()
    
    # This will raise FaceQualityError if no face or multiple faces
    probe_embedding = provider.generate_embedding(image_bytes)
    
    threshold = settings.FACE_RECOGNITION_THRESHOLD
    best_match = None
    highest_similarity = -1.0
    
    # Retrieve all embeddings for active employees
    # Note: In production at massive scale, we'd use a vector database (e.g., pgvector, FAISS, Milvus) 
    # For Phase 6, we retrieve active encrypted embeddings to compare in-memory natively.
    active_embeddings = FaceEmbedding.objects.filter(
        face_profile__employee__status=True
    ).select_related('face_profile__employee')
    
    for emb_record in active_embeddings:
        try:
            enrolled_vector = decrypt_embedding(emb_record.embedding_data)
            sim = compute_cosine_similarity(probe_embedding, enrolled_vector)
            if sim > highest_similarity:
                highest_similarity = sim
                best_match = emb_record.face_profile.employee
        except Exception:
            continue
            
    if highest_similarity >= threshold and best_match:
        return {
            "recognized": True,
            "employee": best_match,
            "confidence": highest_similarity
        }
        
    return {
        "recognized": False,
        "employee": None,
        "confidence": highest_similarity
    }
