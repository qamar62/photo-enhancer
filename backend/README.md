# Passport Photo Enhancer - Backend API

FastAPI-based backend service for processing photos into passport-ready images.

## Quick Start

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run server
python app.py
```

Server runs on `http://localhost:8000`

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Dependencies

- **fastapi**: Web framework
- **uvicorn**: ASGI server
- **opencv-python**: Image processing
- **mediapipe**: Face detection
- **rembg**: Background removal
- **Pillow**: Image enhancement
- **numpy**: Array operations
