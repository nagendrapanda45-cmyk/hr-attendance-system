import os
import cv2
import numpy as np
from pathlib import Path

BASE_DIR = Path("D:/HR PORTAL/attendance_system")
fixtures_dir = BASE_DIR / "apps" / "face_recognition" / "tests" / "fixtures"

img = cv2.imread(str(fixtures_dir / "single_face.jpg"))
h, w = img.shape[:2]

# Live Sequence (Simulating 3D turn by horizontal stretching)
# live1 = original
cv2.imwrite(str(fixtures_dir / "live1.jpg"), img)
# live2 = stretched 10% horizontally
live2 = cv2.resize(img, (int(w * 1.1), h))
cv2.imwrite(str(fixtures_dir / "live2.jpg"), live2)
# live3 = stretched 20% horizontally
live3 = cv2.resize(img, (int(w * 1.2), h))
cv2.imwrite(str(fixtures_dir / "live3.jpg"), live3)

# Spoof Sequence (Simulating a 2D photo scaling - no internal ratio change)
# spoof1 = original
cv2.imwrite(str(fixtures_dir / "spoof1.jpg"), img)
# spoof2 = uniform scale 1.1
spoof2 = cv2.resize(img, (int(w * 1.1), int(h * 1.1)))
cv2.imwrite(str(fixtures_dir / "spoof2.jpg"), spoof2)
# spoof3 = uniform scale 1.2
spoof3 = cv2.resize(img, (int(w * 1.2), int(h * 1.2)))
cv2.imwrite(str(fixtures_dir / "spoof3.jpg"), spoof3)

print("Phase 7 3D geometric fixtures generated.")
