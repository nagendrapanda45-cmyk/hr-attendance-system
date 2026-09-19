import os
import cv2
import numpy as np
import urllib.request
from pathlib import Path

BASE_DIR = Path("D:/HR PORTAL/attendance_system")
fixtures_dir = BASE_DIR / "apps" / "face_recognition" / "tests" / "fixtures"

# Download Lena if not exists
lena_path = fixtures_dir / "single_face.jpg"
if not lena_path.exists():
    lena_url = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg"
    urllib.request.urlretrieve(lena_url, lena_path)

# 1. face1.jpg = Lena
face1_path = fixtures_dir / "face1.jpg"
if not face1_path.exists():
    img = cv2.imread(str(lena_path))
    cv2.imwrite(str(face1_path), img)

# 2. face2.jpg = Lena with slight blur and brightness change (different image, same person)
face2_path = fixtures_dir / "face2.jpg"
if not face2_path.exists():
    img = cv2.imread(str(lena_path))
    # Slight blur
    img_blur = cv2.GaussianBlur(img, (5, 5), 0)
    # Brightness increase
    img_bright = cv2.convertScaleAbs(img_blur, alpha=1.1, beta=10)
    cv2.imwrite(str(face2_path), img_bright)

# 3. face3.jpg = Elon Musk (Unknown person)
face3_path = fixtures_dir / "face3.jpg"
if not face3_path.exists():
    url = "https://upload.wikimedia.org/wikipedia/commons/8/85/Elon_Musk_Royal_Society_%28crop1%29.jpg"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response, open(face3_path, 'wb') as out_file:
        out_file.write(response.read())

print("Phase 6 fixtures created successfully.")
