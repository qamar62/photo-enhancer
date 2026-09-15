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

# mediapipe declares a hard dependency on opencv-contrib-python - the GUI build,
# which links libGL - so pip drags it in and it lands on top of the headless
# wheel we asked for. Both own the same cv2 package, so whichever was installed
# last wins the import, and the GUI one dies with
# "ImportError: libGL.so.1: cannot open shared object file".
#
# Removing both GUI variants and putting the headless wheel back is what keeps
# the X11 libraries out of this image. --no-deps stops the reinstall from
# dragging numpy along with it. mediapipe only ever calls basic cv2 functions,
# which the headless wheel provides in full.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y opencv-contrib-python opencv-python \
    && pip install --no-cache-dir --force-reinstall --no-deps \
       opencv-python-headless==4.9.0.80

# Give onnxruntime an explicit thread count. Left unset, it sizes its pool from
# the host's core count and then pins each worker to a core the container's
# cpuset may not include; the pin fails with EINVAL and ORT logs a red
# "pthread_setaffinity_np failed ... error code: 22" for every thread on the
# first matting call. Harmless - it runs unpinned - but it reads like a crash.
ENV OMP_NUM_THREADS=4

# Bake the 176MB u2net matte model into the image. Without it the first request
# after every deploy stops to download it from GitHub, and the container needs
# outbound network at runtime to matte at all - segmentation.py would otherwise
# fall back to the coarser MediaPipe mask. Kept above the COPY so that editing
# code does not invalidate the layer and re-download it.
RUN python -c "from rembg import new_session; new_session('u2net_human_seg')"

COPY app.py .
COPY icao ./icao

# Fail the build, not the container, if cv2 cannot load its shared libraries.
# This is the one import that depends on apt packages rather than pip, so it is
# the one worth proving here instead of discovering in a restart loop.
RUN python -c "import cv2, mediapipe; print('cv2', cv2.__version__)"

# Warm the MediaPipe graphs so the first request does not pay for them. Harmless
# if it fails - the models load lazily on demand anyway.
RUN python -c "import icao" || true

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
