"""
Image corrections.

Rules of the house:

1. Every correction is *measured first, applied second* - nothing is applied
   blindly, so a photo that is already correct comes out untouched.
2. Exposure targets are relative, never absolute. Pushing every face to the
   same lightness would wreck natural skin tones, which the guideline sheet
   explicitly requires ("show your skin tones naturally").
3. Corrections that would invent detail that is not there (heavy sharpening of
   a blurred photo, inpainting an eye) are refused - the photo is flagged for
   a retake instead.

Each function returns (image, note) where `note` is None if nothing was done.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from .landmarks import FaceGeometry

Note = Optional[Dict]

# Absolute red excess, (r - max(g, b)) / 255, measured over the pupil core.
# The trigger matches the pass threshold in checks.py, so we only touch an eye
# the report would otherwise flag. The per-pixel value is lower: once an eye is
# known to be affected, the fringe around the bright core wants repairing too.
RED_EYE_TRIGGER = 0.06
RED_EYE_PIXEL = 0.04


# --------------------------------------------------------------------- utils
def _lab(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)


def _unlab(lab: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def _blend(a: np.ndarray, b: np.ndarray, strength: float) -> np.ndarray:
    s = float(np.clip(strength, 0.0, 1.0))
    return np.clip(a.astype(np.float32) * (1 - s) + b.astype(np.float32) * s, 0, 255).astype(
        np.uint8
    )


# ------------------------------------------------------------ white balance
def white_balance(
    image_bgr: np.ndarray,
    neutral_mask: Optional[np.ndarray] = None,
    strength: float = 0.85,
    max_gain: float = 1.30,
) -> Tuple[np.ndarray, Note]:
    """
    Shades-of-grey (Minkowski p=6) white balance.

    When a plain background is available it is used as the neutral reference -
    far more reliable than assuming the whole frame averages to grey.
    """
    px = image_bgr.reshape(-1, 3).astype(np.float32)
    if neutral_mask is not None and neutral_mask.sum() > 500:
        px = image_bgr[neutral_mask.astype(bool)].astype(np.float32)
        ref = "background"
    else:
        ref = "grey-world"

    p = 6.0
    means = np.power(np.mean(np.power(np.maximum(px, 1.0), p), axis=0), 1.0 / p)
    target = float(means.mean())
    gains = np.clip(target / np.maximum(means, 1e-6), 1.0 / max_gain, max_gain)

    if float(np.max(np.abs(gains - 1.0))) < 0.015:
        return image_bgr, None

    gains = 1.0 + (gains - 1.0) * float(np.clip(strength, 0, 1))
    out = np.clip(image_bgr.astype(np.float32) * gains[None, None, :], 0, 255).astype(np.uint8)
    return out, {
        "reference": ref,
        "gains_bgr": [round(float(g), 3) for g in gains],
    }


# ---------------------------------------------------------------- exposure
SKIN_L_MIN, SKIN_L_MAX = 42.0, 78.0  # Lab L*, 0-100


def exposure(
    image_bgr: np.ndarray, geo: FaceGeometry, strength: float = 0.9
) -> Tuple[np.ndarray, Note]:
    """
    Nudge facial skin into a printable lightness band with a gamma curve on L*.

    The band is deliberately wide (42-78) so genuinely dark and genuinely fair
    skin both pass untouched; only real under/over-exposure is corrected.
    """
    lab = _lab(image_bgr)
    L = lab[..., 0] * 100.0 / 255.0
    skin = geo.skin_sample_mask().astype(bool)
    if skin.sum() < 30:
        skin = geo.face_mask(image_bgr.shape[:2]).astype(bool)
    if skin.sum() < 30:
        return image_bgr, None

    current = float(np.median(L[skin]))
    if SKIN_L_MIN <= current <= SKIN_L_MAX:
        return image_bgr, None

    target = 48.0 if current < SKIN_L_MIN else 72.0
    c = float(np.clip(current, 2.0, 98.0)) / 100.0
    t = target / 100.0
    gamma = float(np.clip(np.log(t) / np.log(c), 0.55, 1.8))
    gamma = 1.0 + (gamma - 1.0) * float(np.clip(strength, 0, 1))

    norm = np.clip(L / 100.0, 0.0, 1.0)
    lab[..., 0] = np.power(norm, gamma) * 255.0
    return _unlab(lab), {
        "skin_lightness_before": round(current, 1),
        "target": target,
        "gamma": round(gamma, 3),
    }


def contrast(
    image_bgr: np.ndarray, geo: FaceGeometry, strength: float = 0.7
) -> Tuple[np.ndarray, Note]:
    """Gentle local contrast (CLAHE on L*) only when the face is flat."""
    grey = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    mask = geo.face_mask(image_bgr.shape[:2]).astype(bool)
    if mask.sum() < 200:
        return image_bgr, None
    std = float(grey[mask].std())
    if std >= 32.0:
        return image_bgr, None

    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    clip = float(np.clip((32.0 - std) / 14.0, 0.4, 2.0))
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    lab[..., 0] = clahe.apply(lab[..., 0])
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return _blend(image_bgr, out, strength), {
        "face_contrast_before": round(std, 1),
        "clip_limit": round(clip, 2),
    }


# ------------------------------------------------------------------ shadows
def flatten_lighting(
    image_bgr: np.ndarray,
    geo: FaceGeometry,
    subject_mask: Optional[np.ndarray] = None,
    asymmetry: float = 0.0,
    strength: float = 0.55,
) -> Tuple[np.ndarray, Note]:
    """
    Even out directional lighting across the face ("uniform lighting, no
    shadows across your face").

    A heavily blurred copy of L* is the illumination estimate; dividing by it
    and re-applying the mean flattens the falloff while leaving facial texture
    and shape intact. Gain is clamped so it can never look like a cut-out.
    """
    if asymmetry < 4.0:
        return image_bgr, None

    lab = _lab(image_bgr)
    L = lab[..., 0]
    sigma = max(float(geo.face_width) * 0.22, 6.0)
    illum = cv2.GaussianBlur(L, (0, 0), sigma)
    mean = float(np.mean(illum[geo.face_mask(image_bgr.shape[:2]).astype(bool)]))
    gain = np.clip(mean / np.maximum(illum, 1.0), 0.86, 1.18)

    amount = float(np.clip((asymmetry - 4.0) / 12.0, 0.2, 1.0)) * float(np.clip(strength, 0, 1))
    gain = 1.0 + (gain - 1.0) * amount

    if subject_mask is not None:
        m = np.clip(subject_mask, 0, 1)
        gain = 1.0 + (gain - 1.0) * m

    lab[..., 0] = np.clip(L * gain, 0, 255)
    return _unlab(lab), {"asymmetry_before": round(asymmetry, 2), "amount": round(amount, 2)}


def soften_hotspots(
    image_bgr: np.ndarray,
    geo: FaceGeometry,
    fraction: float,
    strength: float = 0.75,
) -> Tuple[np.ndarray, Note]:
    """
    Tame small blown specular highlights on skin (flash reflection).

    Eyes and spectacle lenses are deliberately excluded - repairing those would
    be inventing eyes, so glare there is reported as a retake reason instead.
    """
    if fraction < 0.004 or fraction > 0.18:
        return image_bgr, None

    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    v, s = hsv[..., 2], hsv[..., 1]
    face = geo.face_mask(image_bgr.shape[:2])
    hot = ((v >= 248) & (s < 40) & (face > 0)).astype(np.uint8)

    for x1, y1, x2, y2 in geo.eye_regions(2.2):
        hot[y1:y2, x1:x2] = 0
    if hot.sum() < 20:
        return image_bgr, None

    hot = cv2.dilate(hot, np.ones((3, 3), np.uint8))
    repaired = cv2.inpaint(image_bgr, hot, 4, cv2.INPAINT_TELEA)
    m = cv2.GaussianBlur(hot.astype(np.float32), (0, 0), 2.0)[..., None]
    m = np.clip(m * float(np.clip(strength, 0, 1)), 0, 1)
    out = image_bgr.astype(np.float32) * (1 - m) + repaired.astype(np.float32) * m
    return np.clip(out, 0, 255).astype(np.uint8), {"skin_hotspot_before": round(fraction, 4)}


# ------------------------------------------------------------------ red eye
def red_eye(
    image_bgr: np.ndarray, geo: FaceGeometry, red_excess: float, strength: float = 1.0
) -> Tuple[np.ndarray, Note]:
    """
    Classic red-eye repair: inside the iris, pull the red channel down to the
    green/blue level. The specular catchlight is preserved so the eye still
    looks alive.

    Both the trigger and the per-pixel selector use absolute red excess rather
    than a red/green ratio, so a brown iris - which is genuinely reddish - is
    never desaturated into a grey one.
    """
    if red_excess < RED_EYE_TRIGGER:
        return image_bgr, None
    circles = geo.iris_circles()
    if not circles:
        return image_bgr, None

    out = image_bgr.copy()
    b, g, r = cv2.split(out.astype(np.float32))
    excess = (r - np.maximum(g, b)) / 255.0

    fixed = 0
    for cx, cy, rad in circles:
        mask = np.zeros(image_bgr.shape[:2], np.uint8)
        cv2.circle(mask, (int(cx), int(cy)), max(int(rad * 1.05), 3), 255, -1)
        sel = (mask > 0) & (excess > RED_EYE_PIXEL)
        if sel.sum() < 4:
            continue
        neutral = np.minimum(g, b)
        blend = float(np.clip(strength, 0, 1))
        r[sel] = r[sel] * (1 - blend) + neutral[sel] * blend
        # keep the catchlight
        highlight = (mask > 0) & (np.minimum(g, b) > 215)
        r[highlight] = image_bgr[..., 2][highlight]
        fixed += 1

    if not fixed:
        return image_bgr, None
    out = cv2.merge([b, g, r])
    return np.clip(out, 0, 255).astype(np.uint8), {
        "eyes_fixed": fixed,
        "red_excess_before": round(red_excess, 4),
    }


# --------------------------------------------------------------- noise/sharp
def denoise(image_bgr: np.ndarray, sigma: float, strength: float = 0.8) -> Tuple[np.ndarray, Note]:
    if sigma < 4.5:
        return image_bgr, None
    h = float(np.clip((sigma - 3.0) * 1.2, 2.0, 8.0))
    out = cv2.fastNlMeansDenoisingColored(image_bgr, None, h, h, 7, 21)
    return _blend(image_bgr, out, strength), {"sigma_before": round(sigma, 2), "h": round(h, 1)}


def sharpen(
    image_bgr: np.ndarray,
    normalised_sharpness: float,
    head_px: float,
    max_amount: float = 0.85,
) -> Tuple[np.ndarray, Note]:
    """
    Adaptive unsharp mask.

    Amount falls to zero for an already-crisp photo and is *also* held back for
    a badly blurred one - halos around a soft face look worse than the soft
    face and would not survive a border check anyway.
    """
    n = float(normalised_sharpness)
    if n >= 78.0:
        return image_bgr, None
    if n < 12.0:
        return image_bgr, None  # too far gone: flagged for retake instead

    amount = float(np.clip((72.0 - n) / 55.0, 0.15, 1.0)) * max_amount
    sigma = float(np.clip(head_px * 0.0016, 0.7, 2.2))

    blurred = cv2.GaussianBlur(image_bgr, (0, 0), sigma)
    sharp = cv2.addWeighted(image_bgr, 1.0 + amount, blurred, -amount, 0)

    # Only sharpen where there is real structure, so skin and background stay clean.
    grey = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    edge = cv2.GaussianBlur(np.abs(cv2.Laplacian(grey, cv2.CV_32F)), (0, 0), sigma * 1.5)
    w = np.clip(edge / (np.percentile(edge, 97) + 1e-6), 0, 1)[..., None] ** 0.7
    out = image_bgr.astype(np.float32) * (1 - w) + sharp.astype(np.float32) * w
    return np.clip(out, 0, 255).astype(np.uint8), {
        "amount": round(amount, 2),
        "radius": round(sigma, 2),
        "sharpness_before": round(n, 1),
    }


# --------------------------------------------------------------- background
def neutralise_background(
    image_bgr: np.ndarray,
    alpha: np.ndarray,
    target_lightness: float = 86.0,
    strength: float = 0.8,
) -> Tuple[np.ndarray, Note]:
    """
    Keep the real background but make it pass: desaturate it toward neutral,
    lift it to a light tone and flatten any shadow gradient behind the head.
    Used when the user turns background *replacement* off.
    """
    bg = 1.0 - np.clip(alpha, 0, 1)
    if bg.mean() < 0.02:
        return image_bgr, None

    lab = _lab(image_bgr)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    w = (bg * float(np.clip(strength, 0, 1)))

    current = float(np.average(L, weights=bg)) * 100.0 / 255.0
    lift = (target_lightness - current) * 255.0 / 100.0
    flat = cv2.GaussianBlur(L, (0, 0), max(image_bgr.shape[0] * 0.05, 8))
    mean_bg = float(np.average(flat, weights=bg))

    newL = L + w * ((mean_bg - flat) * 0.85 + lift)
    lab[..., 0] = np.clip(newL, 0, 255)
    lab[..., 1] = 128.0 + (A - 128.0) * (1 - w * 0.9)
    lab[..., 2] = 128.0 + (B - 128.0) * (1 - w * 0.9)
    return _unlab(lab), {"lightness_before": round(current, 1), "target": target_lightness}


def replace_background(
    image_bgr: np.ndarray, alpha: np.ndarray, colour_bgr, decontaminate: bool = True
) -> Tuple[np.ndarray, Note]:
    """
    Composite the subject onto a flat colour.

    `decontaminate` removes the dark rim that appears when a subject shot
    against a dark wall is dropped onto white, by pulling semi-transparent edge
    pixels toward the new background colour.
    """
    a = np.clip(alpha, 0, 1).astype(np.float32)
    img = image_bgr.astype(np.float32)
    col = np.asarray(colour_bgr, np.float32)[None, None, :]

    if decontaminate:
        edge = ((a > 0.05) & (a < 0.95)).astype(np.float32)
        edge = cv2.GaussianBlur(edge, (0, 0), 1.5)[..., None]
        img = img * (1 - edge * 0.55) + (img * 0.45 + col * 0.55) * (edge * 0.55)

    out = img * a[..., None] + col * (1.0 - a[..., None])
    return np.clip(out, 0, 255).astype(np.uint8), {
        "colour_rgb": [int(colour_bgr[2]), int(colour_bgr[1]), int(colour_bgr[0])]
    }
