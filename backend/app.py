from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import cv2
import numpy as np
from PIL import Image, ImageEnhance
import mediapipe as mp
from rembg import remove
import io
import base64

app = FastAPI(title="Passport Photo Enhancer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mp_face = mp.solutions.face_detection

def process_passport_image(image_bytes, remove_bg=True, bg_color=(255, 255, 255), width=1200, height=1600):
    """Process uploaded image into passport photo format"""
    
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if image is None:
        raise ValueError("Invalid image format")
    
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    face_detection = mp_face.FaceDetection(
        model_selection=1,
        min_detection_confidence=0.5
    )
    
    results = face_detection.process(rgb)
    
    if not results.detections:
        raise ValueError("No face detected in the image")
    
    detection = results.detections[0]
    bbox = detection.location_data.relative_bounding_box
    
    h, w, _ = image.shape
    
    x = int(bbox.xmin * w)
    y = int(bbox.ymin * h)
    bw = int(bbox.width * w)
    bh = int(bbox.height * h)
    
    padding_x = int(bw * 0.7)
    padding_top = int(bh * 0.8)
    padding_bottom = int(bh * 1.2)
    
    x1 = max(0, x - padding_x)
    y1 = max(0, y - padding_top)
    x2 = min(w, x + bw + padding_x)
    y2 = min(h, y + bh + padding_bottom)
    
    crop = image[y1:y2, x1:x2]
    
    passport = cv2.resize(crop, (width, height))
    
    passport_rgb = cv2.cvtColor(passport, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(passport_rgb)
    
    if remove_bg:
        removed = remove(pil_img)
        
        bg_image = Image.new("RGB", removed.size, bg_color)
        bg_image.paste(removed, mask=removed.split()[-1])
        pil_img = bg_image
    
    bright = ImageEnhance.Brightness(pil_img).enhance(1.08)
    sharp = ImageEnhance.Sharpness(bright).enhance(1.3)
    contrast = ImageEnhance.Contrast(sharp).enhance(1.08)
    
    return contrast

@app.get("/")
def read_root():
    return {
        "message": "Passport Photo Enhancer API",
        "version": "1.0.0",
        "endpoints": {
            "/process": "POST - Upload and process passport photo"
        }
    }

@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    remove_bg: bool = True,
    bg_color_r: int = 255,
    bg_color_g: int = 255,
    bg_color_b: int = 255,
    width: int = 1200,
    height: int = 1600
):
    """
    Upload an image and receive a processed passport photo
    
    Parameters:
    - file: Image file to process
    - remove_bg: Whether to remove background (default: True)
    - bg_color_r: Background color red component 0-255 (default: 255)
    - bg_color_g: Background color green component 0-255 (default: 255)
    - bg_color_b: Background color blue component 0-255 (default: 255)
    - width: Output image width in pixels (default: 1200)
    - height: Output image height in pixels (default: 1600)
    """
    try:
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        contents = await file.read()
        
        bg_color = (bg_color_r, bg_color_g, bg_color_b)
        
        processed_image = process_passport_image(
            contents, 
            remove_bg=remove_bg,
            bg_color=bg_color,
            width=width,
            height=height
        )
        
        img_byte_arr = io.BytesIO()
        processed_image.save(img_byte_arr, format='JPEG', quality=100)
        img_byte_arr.seek(0)
        
        return StreamingResponse(
            img_byte_arr,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"attachment; filename=passport_photo.jpg"
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
