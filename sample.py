import cv2
import numpy as np
from PIL import Image, ImageEnhance
import mediapipe as mp
from rembg import remove

INPUT_IMAGE = "input.jpg"
OUTPUT_IMAGE = "passport_output.jpg"

# -----------------------------
# Load image
# -----------------------------
image = cv2.imread(INPUT_IMAGE)

if image is None:
    raise Exception("Image not found")

rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

# -----------------------------
# Face detection with MediaPipe
# -----------------------------
mp_face = mp.solutions.face_detection
face_detection = mp_face.FaceDetection(
    model_selection=1,
    min_detection_confidence=0.5
)

results = face_detection.process(rgb)

if not results.detections:
    raise Exception("No face detected")

detection = results.detections[0]
bbox = detection.location_data.relative_bounding_box

h, w, _ = image.shape

x = int(bbox.xmin * w)
y = int(bbox.ymin * h)
bw = int(bbox.width * w)
bh = int(bbox.height * h)

# -----------------------------
# Expand crop around face
# -----------------------------
padding_x = int(bw * 0.7)
padding_top = int(bh * 0.8)
padding_bottom = int(bh * 1.2)

x1 = max(0, x - padding_x)
y1 = max(0, y - padding_top)

x2 = min(w, x + bw + padding_x)
y2 = min(h, y + bh + padding_bottom)

crop = image[y1:y2, x1:x2]

# -----------------------------
# Resize to passport format
# -----------------------------
passport = cv2.resize(crop, (1200, 1600))

# -----------------------------
# Convert to PIL
# -----------------------------
passport_rgb = cv2.cvtColor(passport, cv2.COLOR_BGR2RGB)
pil_img = Image.fromarray(passport_rgb)

# -----------------------------
# Background removal
# -----------------------------
removed = remove(pil_img)

# White background
white_bg = Image.new("RGB", removed.size, (255, 255, 255))
white_bg.paste(removed, mask=removed.split()[-1])

# -----------------------------
# Brightness and sharpness
# -----------------------------
bright = ImageEnhance.Brightness(white_bg).enhance(1.08)
sharp = ImageEnhance.Sharpness(bright).enhance(1.3)
contrast = ImageEnhance.Contrast(sharp).enhance(1.08)

# -----------------------------
# Save
# -----------------------------
contrast.save(OUTPUT_IMAGE, quality=100)

print("Passport image saved:", OUTPUT_IMAGE)