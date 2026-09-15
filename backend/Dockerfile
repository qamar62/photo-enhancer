FROM python:3.11-slim

WORKDIR /app

# libglib2.0-0 is needed by opencv even in its headless build; libgomp1 by
# onnxruntime. The X11 libraries the non-headless opencv wants are deliberately
# absent - see the note on opencv-python-headless in requirements.txt.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY icao ./icao

# Warm the MediaPipe graphs at build time so the first request does not pay for
# them. Harmless if it fails - the models load lazily on demand anyway.
RUN python -c "import icao" || true

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
