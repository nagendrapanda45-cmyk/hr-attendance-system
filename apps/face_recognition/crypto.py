from django.conf import settings
from cryptography.fernet import Fernet
import json

def get_fernet():
    key = settings.FACE_ENCRYPTION_KEY
    if not key:
        raise ValueError("FACE_ENCRYPTION_KEY is not set.")
    return Fernet(key.encode())

def encrypt_embedding(embedding_list):
    f = get_fernet()
    data = json.dumps(embedding_list).encode()
    return f.encrypt(data).decode()

def decrypt_embedding(encrypted_str):
    f = get_fernet()
    data = f.decrypt(encrypted_str.encode())
    return json.loads(data.decode())
