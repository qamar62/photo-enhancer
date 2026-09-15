"""
The pipeline.

    analyse(bytes, spec)            -> report on the photo as supplied
    enhance(bytes, spec, options)   -> corrected photo + report on the result

Order matters and is deliberate:

    decode -> landmarks -> matte -> measure
    -> de-rotate -> ICAO crop (canvas extended, never head shrunk)
    -> white balance -> exposure -> flatten lighting -> hotspots -> red eye
    -> contrast -> denoise -> sharpen -> background
    -> measure again -> score

White balance runs before the background is replaced (the old background is
the neutral reference) and sharpening runs before compositing (so the new
background stays perfectly flat and the silhouette gets no halo).
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import checks as rules
from . import corrections as fix
from . import geometry as geom
from . import quality
from . import segmentation as seg
from .landmarks import FaceGeometry, NoFaceError, detect
from .spec import PhotoSpec, get_spec

log = logging.getLogger("icao.pipeline")

MAX_WORKING_PX = 4200


@dataclass
class Options:
    remove_background: bool = True
    background_color: Optional[Tuple[int, int, int]] = None  # RGB
    auto_frame: bool = True
    auto_enhance: bool = True
    fix_red_eye: bool = True
    sharpen: bool = True
    output_format: str = "jpeg"  # jpeg | png
    quality: Optional[int] = None

    def bg_bgr(self, spec: PhotoSpec) -> Tuple[int, int, int]:
        rgb = self.background_color or spec.background
        return (int(rgb[2]), int(rgb[1]), int(rgb[0]))


@dataclass
class Result:
    image: np.ndarray
    report: Dict
    original: np.ndarray
    fixes: List[Dict] = field(default_factory=list)


# ----------------------------------------------------------------- decoding
def decode(image_bytes: bytes) -> np.ndarray:
    """Decode to BGR, honouring EXIF orientation, and cap the working size."""
    try:
        pil = Image.open(io.BytesIO(image_bytes))
        pil = ImageOps.exif_transpose(pil)
        pil = pil.convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception:
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        raise ValueError("That file could not be read as an image.")

    h, w = img.shape[:2]
    longest = max(h, w)
    if longest > MAX_WORKING_PX:
        s = MAX_WORKING_PX / longest
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return img


def encode(image_bgr: np.ndarray, spec: PhotoSpec, options: Options) -> Tuple[bytes, str]:
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    buf = io.BytesIO()
    fmt = (options.output_format or "jpeg").lower()
    dpi = (spec.dpi, spec.dpi)
    if fmt == "png":
        pil.save(buf, format="PNG", dpi=dpi, optimize=True)
        mime = "image/png"
    else:
        pil.save(
            buf,
            format="JPEG",
            quality=int(options.quality or spec.jpeg_quality),
            subsampling=0,
            dpi=dpi,
            optimize=True,
        )
        mime = "image/jpeg"
    return buf.getvalue(), mime


# ---------------------------------------------------------------- analysing
def _landmark_points(geo: FaceGeometry, size: Tuple[int, int]) -> Dict:
    w, h = size
    def n(p):
        return [round(float(p[0]) / w, 4), round(float(p[1]) / h, 4)]

    return {
        "left_eye": n(geo.left_eye),
        "right_eye": n(geo.right_eye),
        "chin": n(geo.chin),
        "crown": [round(geo.face_midline_x / w, 4), round(geo.crown_y / h, 4)],
        "midline_x": round(geo.face_midline_x / w, 4),
        "eye_line_y": round(geo.eye_line_y / h, 4),
        "head_top_y": round(geo.crown_y / h, 4),
        "chin_y": round(float(geo.chin[1]) / h, 4),
    }


def _frame_metrics(geo: FaceGeometry, size: Tuple[int, int], plan=None) -> Dict:
    w, h = size
    d = {
        "head_fraction": round(geo.head_height / h, 4),
        "eye_fraction": round(geo.eye_line_y / h, 4),
        "centre_offset": round(abs(geo.face_midline_x / w - 0.5), 4),
        "extension": round(plan.extension, 4) if plan else 0.0,
    }
    if plan:
        d.update({k: v for k, v in plan.notes.items()})
    return d


def analyse(image_bytes: bytes, spec: PhotoSpec) -> Dict:
    """Score a photo exactly as supplied - no pixels are changed."""
    t0 = time.time()
    img = decode(image_bytes)
    geo = detect(img)
    alpha, matte_source = seg.subject_alpha(img, geo.face_bbox(0.1))
    bg_stats = seg.background_stats(img, alpha)
    m = quality.measure_all(img, geo, bg_stats)

    crop = _frame_metrics(geo, (img.shape[1], img.shape[0]))
    checks = rules.evaluate(m, spec, crop=crop)
    summary = rules.summarise(checks)

    return {
        "mode": "analyse",
        "spec": spec.to_dict(),
        "summary": summary,
        "checks": [c.to_dict() for c in checks],
        "measurements": m,
        "frame": crop,
        "landmarks": _landmark_points(geo, (img.shape[1], img.shape[0])),
        "guide": geom.guide_overlay(spec),
        "matte_source": matte_source,
        "image_size": {"width": img.shape[1], "height": img.shape[0]},
        "processing_ms": int((time.time() - t0) * 1000),
    }


# ---------------------------------------------------------------- enhancing
def enhance(image_bytes: bytes, spec: PhotoSpec, options: Options) -> Result:
    t0 = time.time()
    img = decode(image_bytes)
    original = img.copy()

    geo = detect(img)
    alpha, matte_source = seg.subject_alpha(img, geo.face_bbox(0.1))
    bg_stats_before = seg.background_stats(img, alpha)
    before = quality.measure_all(img, geo, bg_stats_before)

    applied: List[Dict] = []
    fixed: Dict[str, bool] = {}

    def record(check_id: str, label: str, note, detail_key: Optional[str] = None):
        if note is None:
            return
        fixed[check_id] = True
        applied.append({"id": check_id, "label": label, "detail": note})

    # ------------------------------------------------------------- 1. pose
    plan = None
    if options.auto_frame:
        img, geo, angle, matrix = geom.deroll(img, geo)
        if angle and matrix is not None:
            alpha = cv2.warpAffine(
                alpha,
                matrix,
                (img.shape[1], img.shape[0]),
                flags=cv2.INTER_LINEAR,
                borderValue=0.0,
            )
            fixed["head_tilt"] = True
            applied.append(
                {"id": "head_tilt", "label": "Levelled the head", "detail": {"degrees": round(angle, 2)}}
            )

        hair = seg.hair_top_y(alpha, geo.face_midline_x, geo.face_width * 1.8)
        plan = geom.plan_crop(geo, spec, hair_top=hair, source_size=(img.shape[1], img.shape[0]))
        fill = options.bg_bgr(spec) if options.remove_background else None
        img, alpha, matrix = geom.apply_crop(img, plan, spec, alpha, fill)
        geo = geo.transformed(matrix, (img.shape[1], img.shape[0]))
        for cid, label in (
            ("head_size", "Re-framed to the required head size"),
            ("eye_line", "Placed the eye line at the required height"),
            ("centring", "Centred the head in the frame"),
        ):
            fixed[cid] = True
            applied.append({"id": cid, "label": label, "detail": plan.to_dict() if cid == "head_size" else {}})
    else:
        img, alpha, matrix = _fit_to_spec(img, alpha, spec)
        geo = geo.transformed(matrix, (img.shape[1], img.shape[0]))

    alpha = seg.refine_alpha(alpha)
    subject = alpha

    # -------------------------------------------------------- 2. tone work
    if options.auto_enhance:
        neutral = None
        if bg_stats_before.get("available"):
            neutral = (alpha < 0.05).astype(np.uint8)
        img, note = fix.white_balance(img, neutral)
        record("colour_neutral", "Corrected the colour cast", note)

        img, note = fix.exposure(img, geo)
        record("brightness", "Corrected the exposure", note)

        img, note = fix.flatten_lighting(
            img, geo, subject_mask=subject, asymmetry=before["shadow"]["asymmetry"]
        )
        record("even_lighting", "Evened out the lighting across the face", note)

        img, note = fix.soften_hotspots(img, geo, before["highlights"]["skin_hotspot"])
        record("flash_reflection", "Softened flash reflections on the skin", note)

    if options.fix_red_eye:
        img, note = fix.red_eye(img, geo, before["red_eye"]["red_excess"])
        record("red_eye", "Removed red eye", note)

    if options.auto_enhance:
        img, note = fix.contrast(img, geo)
        record("contrast", "Lifted flat contrast", note)

        img, note = fix.denoise(img, before["noise"]["sigma"])
        record("noise", "Reduced grain", note)

    if options.sharpen:
        img, note = fix.sharpen(img, before["sharpness"]["normalised"], geo.head_height)
        record("sharpness", "Sharpened to print standard", note)

    # ------------------------------------------------------ 3. background
    if options.remove_background:
        img, note = fix.replace_background(img, alpha, options.bg_bgr(spec))
        record("background", "Replaced the background with a plain light tone", note)
    elif options.auto_enhance and bg_stats_before.get("available"):
        bad_bg = (
            bg_stats_before["lightness"] < 70
            or bg_stats_before["lightness_std"] > 4
            or max(bg_stats_before["gradient_lr"], bg_stats_before["gradient_tb"]) > 4
        )
        if bad_bg:
            img, note = fix.neutralise_background(img, alpha)
            record("background", "Evened out and lightened the existing background", note)

    # ------------------------------------------------------- 4. re-measure
    try:
        geo_out = detect(img)
    except NoFaceError:
        geo_out = geo
    alpha_out, _ = seg.subject_alpha(img, geo_out.face_bbox(0.1))
    bg_after = seg.background_stats(img, alpha_out)
    after = quality.measure_all(img, geo_out, bg_after)

    frame = _frame_metrics(geo_out, (img.shape[1], img.shape[0]), plan)
    # `before` is measured on the upload, so it is the only honest answer to
    # "did the original have enough pixels?" - see rules.evaluate().
    checks = rules.evaluate(after, spec, crop=frame, fixes=fixed, source=before)
    summary = rules.summarise(checks)

    before_checks = rules.evaluate(
        before, spec, crop=_frame_metrics(geo, (original.shape[1], original.shape[0]))
    )
    before_summary = rules.summarise(before_checks)

    report = {
        "mode": "enhance",
        "spec": spec.to_dict(),
        "options": {
            "remove_background": options.remove_background,
            "auto_frame": options.auto_frame,
            "auto_enhance": options.auto_enhance,
            "fix_red_eye": options.fix_red_eye,
            "sharpen": options.sharpen,
            "background_rgb": list(options.background_color or spec.background),
            "format": options.output_format,
        },
        "summary": summary,
        "score_before": before_summary["score"],
        "verdict_before": before_summary["verdict"],
        "checks": [c.to_dict() for c in checks],
        "fixes_applied": applied,
        "measurements": {"before": before, "after": after},
        "frame": frame,
        "landmarks": _landmark_points(geo_out, (img.shape[1], img.shape[0])),
        "guide": geom.guide_overlay(spec),
        "matte_source": matte_source,
        "image_size": {"width": img.shape[1], "height": img.shape[0]},
        "processing_ms": int((time.time() - t0) * 1000),
    }
    return Result(image=img, report=report, original=original, fixes=applied)


# ----------------------------------------------------------------- helpers
def _fit_to_spec(img, alpha, spec: PhotoSpec):
    """Centre-crop to the spec aspect ratio and resize, without re-framing."""
    h, w = img.shape[:2]
    target = spec.aspect
    if w / h > target:
        new_w = int(round(h * target))
        x1 = (w - new_w) // 2
        box = (x1, 0, x1 + new_w, h)
    else:
        new_h = int(round(w / target))
        y1 = (h - new_h) // 2
        box = (0, y1, w, y1 + new_h)
    x1, y1, x2, y2 = box
    crop = img[y1:y2, x1:x2]
    crop_a = alpha[y1:y2, x1:x2]
    out = cv2.resize(
        crop,
        (spec.width_px, spec.height_px),
        interpolation=cv2.INTER_AREA if crop.shape[1] > spec.width_px else cv2.INTER_CUBIC,
    )
    out_a = cv2.resize(crop_a, (spec.width_px, spec.height_px), interpolation=cv2.INTER_LINEAR)
    sx = spec.width_px / float(crop.shape[1])
    sy = spec.height_px / float(crop.shape[0])
    matrix = np.array([[sx, 0, -x1 * sx], [0, sy, -y1 * sy]], dtype=np.float32)
    return out, out_a, matrix


def run(image_bytes: bytes, spec_id: Optional[str], options: Options) -> Result:
    return enhance(image_bytes, get_spec(spec_id), options)
