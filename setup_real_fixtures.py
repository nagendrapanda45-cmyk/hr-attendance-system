import os
import cv2
import numpy as np
from pathlib import Path

BASE_DIR = Path("D:/HR PORTAL/attendance_system")
fixtures_dir = BASE_DIR / "apps" / "face_recognition" / "tests" / "fixtures"
fixtures_dir.mkdir(parents=True, exist_ok=True)

# 1. Single Face (Lena)
lena_path = BASE_DIR / "apps" / "face_recognition" / "models" / "dnn" / "lena.jpg"
single_face = cv2.imread(str(lena_path))
if single_face is not None:
    cv2.imwrite(str(fixtures_dir / "single_face.jpg"), single_face)
else:
    print("Could not read Lena image!")

# 2. No Face (Black Image)
no_face = np.zeros((300, 300, 3), dtype=np.uint8)
cv2.imwrite(str(fixtures_dir / "no_face.jpg"), no_face)

# 3. Multiple Faces (Lena concatenated horizontally)
if single_face is not None:
    multiple_faces = cv2.hconcat([single_face, single_face])
    cv2.imwrite(str(fixtures_dir / "multiple_faces.jpg"), multiple_faces)

# 4. Poor Quality (Tiny image resized up, or just a 10x10 crop to force tiny bbox)
if single_face is not None:
    # Get a 20x20 crop of the face to guarantee tiny detection box
    face_crop = single_face[100:120, 100:120]
    # Make an image out of it
    poor_quality = np.zeros((300, 300, 3), dtype=np.uint8)
    poor_quality[140:160, 140:160] = face_crop
    cv2.imwrite(str(fixtures_dir / "poor_quality.jpg"), poor_quality)

print("Image fixtures created successfully.")
