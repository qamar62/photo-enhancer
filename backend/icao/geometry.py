"""
ICAO framing maths.

Given the face geometry and a PhotoSpec, work out the exact rectangle to cut
out of the source image so that, in the finished photo:

    * the head (crown -> chin) occupies `head_target` of the image height
    * the eye line lands inside the spec's allowed band
    * the face midline is horizontally centred
    * the top of the hair stays inside the frame

The crop is allowed to fall outside the source image; `apply_crop` extends the
canvas instead of shrinking the head, because cropping tighter would break the
head-size rule - which is the rule that actually matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from .landmarks import FaceGeometry
from .spec import PhotoSpec

# Inset from the eye band edges, so that re-measuring the finished photo (which
# re-runs the detector and lands a pixel or two off) still reads as in-band.
EYE_BAND_SAFETY = 0.015
HEAD_BAND_SAFETY = 0.02


@dataclass
class CropPlan:
    x: float
    y: float
    width: float
    height: float
    head_fraction: float
    eye_fraction: float
    extension: float  # fraction of the crop area that lies outside the source
    notes: Dict

    @property
    def box(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def to_dict(self) -> Dict:
        return {
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "width": round(self.width, 1),
            "height": round(self.height, 1),
            "head_fraction": round(self.head_fraction, 4),
            "eye_fraction": round(self.eye_fraction, 4),
            "extension": round(self.extension, 4),
            **self.notes,
        }


def deroll(
    image_bgr: np.ndarray, geo: FaceGeometry, max_correction_deg: float = 25.0
) -> Tuple[np.ndarray, FaceGeometry, float, Optional[np.ndarray]]:
    """
    Rotate the image so the eye line is horizontal.

    Rotating about the eye centre and expanding the canvas keeps every pixel we
    might need for the crop.

    Returns (image, updated geometry, applied degrees, 2x3 matrix or None).
    """
    angle = geo.roll_deg
    if abs(angle) < 0.35 or abs(angle) > max_correction_deg:
        return image_bgr, geo, 0.0, None

    h, w = image_bgr.shape[:2]
    centre = tuple(float(v) for v in geo.eye_centre)
    m = cv2.getRotationMatrix2D(centre, angle, 1.0)

    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)
    m[0, 2] += new_w / 2 - centre[0]
    m[1, 2] += new_h / 2 - centre[1]

    rotated = cv2.warpAffine(
        image_bgr,
        m,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, geo.transformed(m, (new_w, new_h)), float(angle), m


def plan_crop(
    geo: FaceGeometry,
    spec: PhotoSpec,
    hair_top: Optional[float] = None,
    source_size: Optional[Tuple[int, int]] = None,
) -> CropPlan:
    """Compute the ideal crop rectangle in source-pixel coordinates."""
    src_w, src_h = source_size or geo.image_size

    head_h = max(geo.head_height, 4.0)
    crown_y = geo.crown_y
    chin_y = float(geo.chin[1])

    target = spec.head_target
    crop_h = head_h / target
    notes: Dict = {}

    eye_y = geo.eye_line_y

    # Hair that already runs off the top of the source cannot be rescued, and a
    # matte touching the edge tells us nothing about where the hair really ends.
    # Trusting it would drag the whole frame up and throw the eye line out.
    if hair_top is not None and hair_top <= 1.0:
        hair_top = None
        notes["hair_clipped_in_source"] = True

    # Whatever is highest - the hair when we have a usable matte, otherwise the
    # estimated skull vertex - is what needs headroom above it.
    protect_top = crown_y if hair_top is None else min(hair_top, crown_y)

    def _place(crop_height: float) -> float:
        """Best top edge for a given crop height, honouring the eye band."""
        t = eye_y - spec.eye_target * crop_height
        t = min(t, protect_top - spec.top_margin_min * crop_height)
        # The eye line is a spec requirement; headroom above the hair is only a
        # preference. Never let headroom push the eyes outside the allowed band.
        # (top shrinks as the eye fraction grows, hence the inverted bounds.)
        lo = eye_y - (spec.eye_max - EYE_BAND_SAFETY) * crop_height
        hi = eye_y - (spec.eye_min + EYE_BAND_SAFETY) * crop_height
        return float(np.clip(t, min(lo, hi), max(lo, hi)))

    top = _place(crop_h)

    # If the hair still overhangs, buy headroom by growing the frame. Growing it
    # lowers the head fraction, so we only spend what the head-size rule can
    # afford: head size is the rule examiners actually measure, tall hair is not
    # worth failing it for. Whatever hair still overhangs gets reported instead.
    if protect_top < top + spec.top_margin_min * crop_h:
        room = spec.eye_max - EYE_BAND_SAFETY - spec.top_margin_min
        needed = (eye_y - protect_top) / max(room, 1e-3)
        max_crop_h = head_h / (spec.head_min + HEAD_BAND_SAFETY)
        crop_h = float(np.clip(needed, crop_h, max_crop_h))
        top = _place(crop_h)
        notes["hair_adjusted"] = crop_h > head_h / target + 1e-6
        if protect_top < top + spec.top_margin_min * crop_h:
            notes["hair_cropped"] = True

    crop_w = crop_h * spec.aspect
    left = geo.face_midline_x - crop_w / 2.0

    # How much of the plan lies outside the source?
    ix1, iy1 = max(left, 0.0), max(top, 0.0)
    ix2, iy2 = min(left + crop_w, src_w), min(top + crop_h, src_h)
    inside = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    extension = 1.0 - inside / (crop_w * crop_h)

    return CropPlan(
        x=left,
        y=top,
        width=crop_w,
        height=crop_h,
        head_fraction=head_h / crop_h,
        eye_fraction=(eye_y - top) / crop_h,
        extension=max(0.0, extension),
        notes=notes,
    )


def apply_crop(
    image_bgr: np.ndarray,
    plan: CropPlan,
    spec: PhotoSpec,
    alpha: Optional[np.ndarray] = None,
    fill_bgr: Optional[Tuple[int, int, int]] = None,
) -> Tuple[np.ndarray, Optional[np.ndarray], np.ndarray]:
    """
    Cut the planned rectangle out, extending the canvas when it overhangs, then
    resample to the spec's pixel size.

    Returns (image, alpha, 2x3 matrix mapping source coords -> output coords).
    """
    h, w = image_bgr.shape[:2]
    x1 = int(np.floor(plan.x))
    y1 = int(np.floor(plan.y))
    x2 = int(np.ceil(plan.x + plan.width))
    y2 = int(np.ceil(plan.y + plan.height))

    pad_l, pad_t = max(0, -x1), max(0, -y1)
    pad_r, pad_b = max(0, x2 - w), max(0, y2 - h)

    if any((pad_l, pad_t, pad_r, pad_b)):
        if fill_bgr is not None:
            border = cv2.BORDER_CONSTANT
            value = tuple(int(v) for v in fill_bgr)
        else:
            border = cv2.BORDER_REPLICATE
            value = None
        image_bgr = cv2.copyMakeBorder(
            image_bgr, pad_t, pad_b, pad_l, pad_r, border,
            **({"value": value} if value is not None else {}),
        )
        if fill_bgr is None:
            # Replicated edges look like streaks; blur just the added band so
            # it reads as an out-of-focus surround instead.
            image_bgr = _soften_border(image_bgr, pad_l, pad_t, pad_r, pad_b)
        if alpha is not None:
            alpha = cv2.copyMakeBorder(
                alpha, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_CONSTANT, value=0.0
            )
        x1 += pad_l
        x2 += pad_l
        y1 += pad_t
        y2 += pad_t

    crop = image_bgr[y1:y2, x1:x2]
    crop_a = alpha[y1:y2, x1:x2] if alpha is not None else None

    out_w, out_h = spec.width_px, spec.height_px
    interp = cv2.INTER_AREA if crop.shape[1] > out_w else cv2.INTER_CUBIC
    out = cv2.resize(crop, (out_w, out_h), interpolation=interp)
    out_a = (
        cv2.resize(crop_a, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        if crop_a is not None
        else None
    )

    sx = out_w / float(crop.shape[1])
    sy = out_h / float(crop.shape[0])
    matrix = np.array(
        [[sx, 0.0, -(x1 - pad_l) * sx], [0.0, sy, -(y1 - pad_t) * sy]], dtype=np.float32
    )
    return out, out_a, matrix


def _soften_border(img: np.ndarray, l: int, t: int, r: int, b: int) -> np.ndarray:
    if not any((l, t, r, b)):
        return img
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.float32)
    if l:
        mask[:, :l] = 1.0
    if r:
        mask[:, w - r:] = 1.0
    if t:
        mask[:t, :] = 1.0
    if b:
        mask[h - b:, :] = 1.0
    mask = cv2.GaussianBlur(mask, (0, 0), max(3.0, min(h, w) * 0.01))
    blurred = cv2.GaussianBlur(img, (0, 0), max(4.0, min(h, w) * 0.012))
    m = mask[..., None]
    return np.clip(img.astype(np.float32) * (1 - m) + blurred.astype(np.float32) * m, 0, 255).astype(
        np.uint8
    )


def guide_overlay(spec: PhotoSpec) -> Dict:
    """Fractions the UI uses to draw the ICAO guide lines over the result."""
    return {
        "head_min": spec.head_min,
        "head_max": spec.head_max,
        "head_target": spec.head_target,
        "eye_min": spec.eye_min,
        "eye_max": spec.eye_max,
        "eye_target": spec.eye_target,
        "centre_tolerance": spec.centre_tolerance,
        "aspect": spec.aspect,
    }
