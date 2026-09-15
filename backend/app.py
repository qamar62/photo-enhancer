"""
Photo Enhancer API.

    GET  /                     service info
    GET  /health               liveness + model warm-up state
    GET  /api/v1/specs         photo specs, paper sizes, rule catalogue
    POST /api/v1/analyse       score a photo, change nothing
    POST /api/v1/process       enhance + score  (JSON or raw image)
    POST /api/v1/batch         many photos in, ZIP out
    POST /api/v1/sheet         tile a finished photo onto print paper
    POST /process              legacy v1 endpoint, unchanged behaviour

Heavy work runs in a worker thread with a concurrency gate, so a slow 12 Mpx
upload can never block the event loop or let ten parallel uploads thrash the
CPU.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import time
import zipfile
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

import icao
from icao import checks as rules
from icao.sheet import DEFAULT_PAPER
from icao.landmarks import NoFaceError

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("api")

MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_BATCH = int(os.getenv("MAX_BATCH", "20"))
CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "2"))

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://localhost:4173",
    ).split(",")
    if o.strip()
]

app = FastAPI(
    title="Photo Enhancer API",
    version=icao.__version__,
    description="ICAO-compliant passport photo processing with a full compliance report.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in ALLOWED_ORIGINS else ALLOWED_ORIGINS,
    allow_credentials="*" not in ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    # The browser can only read a response header we name here, and the UI reads
    # every one of these: the score on a streamed image, the copies-per-sheet
    # note, and the batch tally it shows without unzipping the archive.
    expose_headers=[
        "X-Compliance-Score",
        "X-Compliance-Verdict",
        "X-Sheet-Info",
        "X-Batch-Total",
        "X-Batch-Compliant",
        "Content-Disposition",
    ],
)
app.add_middleware(GZipMiddleware, minimum_size=2048)

_gate = asyncio.Semaphore(CONCURRENCY)


# ----------------------------------------------------------------- helpers
async def _read_upload(file: UploadFile) -> bytes:
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, f"{file.filename or 'file'} is not an image.")
    data = await file.read()
    if not data:
        raise HTTPException(400, f"{file.filename or 'file'} is empty.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            413, f"{file.filename or 'file'} is larger than {MAX_UPLOAD_MB:g} MB."
        )
    return data


def _options(
    remove_background: bool,
    background: Optional[str],
    auto_frame: bool,
    auto_enhance: bool,
    fix_red_eye: bool,
    sharpen: bool,
    output_format: str,
    quality: Optional[int],
) -> icao.Options:
    rgb = _parse_colour(background)
    fmt = (output_format or "jpeg").lower()
    if fmt not in ("jpeg", "jpg", "png"):
        raise HTTPException(400, "format must be jpeg or png")
    return icao.Options(
        remove_background=remove_background,
        background_color=rgb,
        auto_frame=auto_frame,
        auto_enhance=auto_enhance,
        fix_red_eye=fix_red_eye,
        sharpen=sharpen,
        output_format="png" if fmt == "png" else "jpeg",
        quality=quality,
    )


def _parse_colour(value: Optional[str]):
    if not value:
        return None
    v = value.strip().lstrip("#")
    try:
        if len(v) == 3:
            return tuple(int(c * 2, 16) for c in v)
        if len(v) == 6:
            return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))
        parts = [int(p) for p in v.replace(";", ",").split(",")]
        if len(parts) == 3:
            return tuple(max(0, min(255, p)) for p in parts)
    except ValueError:
        pass
    raise HTTPException(400, f"Could not read colour '{value}'. Use #RRGGBB or r,g,b.")


def _resolve_spec(spec_id: Optional[str], width: Optional[int], height: Optional[int]):
    try:
        spec = icao.get_spec(spec_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if width and height:
        if not (64 <= width <= 6000 and 64 <= height <= 6000):
            raise HTTPException(400, "width and height must be between 64 and 6000 px.")
        spec = spec.resized(px_width=width, px_height=height)
    return spec


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, NoFaceError):
        return HTTPException(422, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    log.exception("processing failed")
    return HTTPException(500, f"Processing failed: {exc}")


async def _run(fn, *args, **kwargs):
    async with _gate:
        try:
            return await run_in_threadpool(fn, *args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _handle(exc)


def _data_url(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(payload).decode("ascii")


# -------------------------------------------------------------------- meta
@app.get("/")
def root():
    return {
        "service": "Photo Enhancer API",
        "version": icao.__version__,
        "standard": "ICAO 9303 / UK-style personal photo guideline",
        "endpoints": {
            "GET /api/v1/specs": "photo sizes, paper sizes and the rule catalogue",
            "POST /api/v1/analyse": "compliance report for a photo, unmodified",
            "POST /api/v1/process": "enhance a photo and report on the result",
            "POST /api/v1/batch": "process up to %d photos, returns a ZIP" % MAX_BATCH,
            "POST /api/v1/sheet": "tile a photo onto printable paper",
            "POST /process": "legacy endpoint (returns a JPEG)",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": icao.__version__, "concurrency": CONCURRENCY}


@app.get("/api/v1/specs")
def specs():
    catalogue = {}
    for cid, label in rules.CATEGORY_LABELS.items():
        catalogue[cid] = label
    return {
        "specs": [icao.SPECS[k].to_dict() for k in icao.SPECS],
        "default": icao.DEFAULT_SPEC_ID,
        "papers": icao.list_papers(),
        "categories": catalogue,
        "limits": {
            "max_upload_mb": MAX_UPLOAD_MB,
            "max_batch": MAX_BATCH,
        },
    }


# ----------------------------------------------------------------- analyse
@app.post("/api/v1/analyse")
async def analyse(
    file: UploadFile = File(...),
    spec: Optional[str] = Form(None),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
):
    data = await _read_upload(file)
    target = _resolve_spec(spec, width, height)
    report = await _run(icao.analyse, data, target)
    report["filename"] = file.filename
    return JSONResponse(report)


# ----------------------------------------------------------------- process
@app.post("/api/v1/process")
async def process(
    file: UploadFile = File(...),
    spec: Optional[str] = Form(None),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    remove_background: bool = Form(True),
    background: Optional[str] = Form(None),
    auto_frame: bool = Form(True),
    auto_enhance: bool = Form(True),
    fix_red_eye: bool = Form(True),
    sharpen: bool = Form(True),
    format: str = Form("jpeg"),
    quality: Optional[int] = Form(None),
    response: str = Query("json", pattern="^(json|image)$"),
):
    """
    `response=json` (default) returns {image: data-url, report: {...}}.
    `response=image` streams the file, with the score in the headers.
    """
    data = await _read_upload(file)
    target = _resolve_spec(spec, width, height)
    opts = _options(
        remove_background, background, auto_frame, auto_enhance, fix_red_eye, sharpen, format, quality
    )

    result = await _run(icao.enhance, data, target, opts)
    payload, mime = icao.encode(result.image, target, opts)

    ext = "png" if mime.endswith("png") else "jpg"
    name = f"photo_{target.id}.{ext}"
    score = result.report["summary"]["score"]
    verdict = result.report["summary"]["verdict"]

    if response == "image":
        return Response(
            content=payload,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "X-Compliance-Score": str(score),
                "X-Compliance-Verdict": verdict,
            },
        )

    return JSONResponse(
        {
            "image": _data_url(payload, mime),
            "mime": mime,
            "filename": name,
            "bytes": len(payload),
            "report": result.report,
        }
    )


# ------------------------------------------------------------------- batch
@app.post("/api/v1/batch")
async def batch(
    files: List[UploadFile] = File(...),
    spec: Optional[str] = Form(None),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    remove_background: bool = Form(True),
    background: Optional[str] = Form(None),
    auto_frame: bool = Form(True),
    auto_enhance: bool = Form(True),
    fix_red_eye: bool = Form(True),
    sharpen: bool = Form(True),
    format: str = Form("jpeg"),
    quality: Optional[int] = Form(None),
):
    """Process many photos and return a ZIP: images + reports.json + summary.csv."""
    if not files:
        raise HTTPException(400, "No files uploaded.")
    if len(files) > MAX_BATCH:
        raise HTTPException(400, f"At most {MAX_BATCH} photos per batch.")

    target = _resolve_spec(spec, width, height)
    opts = _options(
        remove_background, background, auto_frame, auto_enhance, fix_red_eye, sharpen, format, quality
    )

    buffer = io.BytesIO()
    reports = []
    started = time.time()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, upload in enumerate(files, start=1):
            stem = os.path.splitext(os.path.basename(upload.filename or f"photo{index}"))[0]
            try:
                data = await _read_upload(upload)
                result = await _run(icao.enhance, data, target, opts)
                payload, mime = icao.encode(result.image, target, opts)
                ext = "png" if mime.endswith("png") else "jpg"
                out_name = f"{index:02d}_{stem}.{ext}"
                zf.writestr(out_name, payload)
                reports.append(
                    {
                        "file": upload.filename,
                        "output": out_name,
                        "score": result.report["summary"]["score"],
                        "verdict": result.report["summary"]["verdict"],
                        "failures": [
                            c["id"] for c in result.report["checks"] if c["status"] == "fail"
                        ],
                        "report": result.report,
                    }
                )
            except HTTPException as exc:
                reports.append(
                    {"file": upload.filename, "error": exc.detail, "verdict": "error"}
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("batch item failed")
                reports.append({"file": upload.filename, "error": str(exc), "verdict": "error"})

        zf.writestr("reports.json", json.dumps(reports, indent=2))
        lines = ["file,output,score,verdict,failures"]
        for r in reports:
            lines.append(
                ",".join(
                    [
                        json.dumps(r.get("file") or ""),
                        json.dumps(r.get("output") or ""),
                        str(r.get("score", "")),
                        r.get("verdict", ""),
                        json.dumps(" ".join(r.get("failures", []))),
                    ]
                )
            )
        zf.writestr("summary.csv", "\n".join(lines))

    buffer.seek(0)
    ok = sum(1 for r in reports if r.get("verdict") in ("compliant", "acceptable"))
    log.info("batch of %d done in %.1fs (%d compliant)", len(files), time.time() - started, ok)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="passport_photos.zip"',
            "X-Batch-Total": str(len(reports)),
            "X-Batch-Compliant": str(ok),
        },
    )


# ------------------------------------------------------------------- sheet
@app.post("/api/v1/sheet")
async def print_sheet(
    file: UploadFile = File(...),
    spec: Optional[str] = Form(None),
    paper: str = Form(DEFAULT_PAPER),
    dpi: int = Form(300),
    already_processed: bool = Form(False),
    remove_background: bool = Form(True),
    background: Optional[str] = Form(None),
    cut_guides: bool = Form(True),
):
    """
    Build a printable sheet.

    Send the finished photo with already_processed=true, or an original and let
    it be enhanced first.
    """
    data = await _read_upload(file)
    target = _resolve_spec(spec, None, None)
    if not (72 <= dpi <= 1200):
        raise HTTPException(400, "dpi must be between 72 and 1200.")

    def build():
        if already_processed:
            photo = icao.decode(data)
        else:
            opts = icao.Options(
                remove_background=remove_background,
                background_color=_parse_colour(background),
            )
            photo = icao.enhance(data, target, opts).image
        sheet, info = icao.build_sheet(photo, target, paper_id=paper, dpi=dpi, cut_guides=cut_guides)
        ok, buf = cv2.imencode(".jpg", sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 96])
        if not ok:
            raise ValueError("Could not encode the print sheet.")
        return buf.tobytes(), info

    payload, info = await _run(build)
    return Response(
        content=payload,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'attachment; filename="print_sheet_{paper}.jpg"',
            "X-Sheet-Info": json.dumps(info),
        },
    )


# ------------------------------------------------------------------ legacy
@app.post("/process")
async def legacy_process(
    file: UploadFile = File(...),
    remove_bg: bool = Query(True),
    bg_color_r: int = Query(255),
    bg_color_g: int = Query(255),
    bg_color_b: int = Query(255),
    width: int = Query(1200),
    height: int = Query(1600),
):
    """Original endpoint, kept so existing clients keep working."""
    data = await _read_upload(file)
    spec = icao.get_spec("general").resized(px_width=width, px_height=height)
    opts = icao.Options(
        remove_background=remove_bg,
        background_color=(bg_color_r, bg_color_g, bg_color_b),
    )
    result = await _run(icao.enhance, data, spec, opts)
    payload, mime = icao.encode(result.image, spec, opts)
    return Response(
        content=payload,
        media_type=mime,
        headers={
            "Content-Disposition": 'attachment; filename="passport_photo.jpg"',
            "X-Compliance-Score": str(result.report["summary"]["score"]),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
