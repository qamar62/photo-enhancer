"""
Photometric measurements.

Every function here returns plain numbers - no judgements. `checks.py` turns
them into pass / warn / fail against a PhotoSpec, which keeps the thresholds
in one readable place.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import cv2
import numpy as np

from .landmarks import FaceGeometry

# L* range an open, unobstructed eye shows even in a flat, low-contrast face.
ABSOLUTE_EYE_RANGE = 18.0

# Face width the Laplacian is measured at, and the point below which a focus
# score stops meaning anything. See sharpness().
SHARPNESS_FACE_WIDTH = 320


def _roi(image: np.ndarray, box) -> np.ndarray:
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return image
    return image[y1:y2, x1:x2]


def sharpness(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    """
    Focus measure, normalised across photo sizes - but only downwards.

    A big face is resampled down to SHARPNESS_FACE_WIDTH before the Laplacian so
    a 4000 px photo and an 800 px photo of the same face score the same. A face
    that is already smaller is measured where it is. Scaling one *up* first would
    be measuring the interpolator: upsampling invents no detail, it only smooths,
    so a perfectly focused small photo comes back reading as badly out of focus.

    Below the reference width there are simply not enough pixels to tell focus
    from size, so the result is marked unreliable and the resolution check - the
    one that is actually about having too few pixels - carries the verdict.
    """
    face = _roi(image_bgr, geo.face_bbox(0.05))
    if face.size == 0:
        return {
            "score": 0.0,
            "normalised": 0.0,
            "eye_score": 0.0,
            "face_px": 0,
            "reliable": False,
        }

    def _lapvar(img: np.ndarray, target_w: int) -> float:
        if img.shape[1] < 8:
            return 0.0
        s = min(target_w / float(img.shape[1]), 1.0)
        r = img if s >= 1.0 else cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(r, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(g, cv2.CV_64F).var())

    face_px = int(face.shape[1])
    score = _lapvar(face, SHARPNESS_FACE_WIDTH)
    eye_scores = [_lapvar(_roi(image_bgr, b), 96) for b in geo.eye_regions(1.6)]
    eye_score = float(np.mean(eye_scores)) if eye_scores else 0.0

    # 0-100, saturating around a comfortably sharp studio portrait.
    normalised = float(np.clip(100.0 * (score / 320.0) ** 0.6, 0, 100))
    return {
        "score": round(score, 1),
        "eye_score": round(eye_score, 1),
        "normalised": round(normalised, 1),
        "face_px": face_px,
        "reliable": face_px >= SHARPNESS_FACE_WIDTH,
    }


def resolution(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    h, w = image_bgr.shape[:2]
    return {
        "width": w,
        "height": h,
        "megapixels": round(w * h / 1e6, 2),
        "head_height_px": round(geo.head_height, 1),
        "interocular_px": round(geo.interocular, 1),
    }


def exposure(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    """Luminance statistics over facial skin, plus clipping over the whole face."""
    skin = geo.skin_sample_mask()
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    lum = lab[..., 0].astype(np.float32) * 100.0 / 255.0

    m = skin.astype(bool)
    if m.sum() < 30:
        m = geo.face_mask(image_bgr.shape[:2]).astype(bool)

    skin_l = lum[m]
    face_mask = geo.face_mask(image_bgr.shape[:2]).astype(bool)
    grey = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    face_px = grey[face_mask].astype(np.float32)

    return {
        "skin_lightness": round(float(skin_l.mean()), 1),  # 0-100
        "skin_lightness_p10": round(float(np.percentile(skin_l, 10)), 1),
        "skin_lightness_p90": round(float(np.percentile(skin_l, 90)), 1),
        "face_contrast": round(float(face_px.std()), 1),  # 0-255 scale
        "highlight_clip": round(float((face_px >= 252).mean()), 4),
        "shadow_clip": round(float((face_px <= 4).mean()), 4),
    }


def colour_balance(image_bgr: np.ndarray, geo: FaceGeometry, bg_stats: Dict) -> Dict:
    """
    Colour neutrality + skin-tone plausibility.

    `cast` is the Lab chroma of what *should* be neutral (the background when
    we can measure it, otherwise a robust grey-world estimate). Skin hue is
    checked separately because healthy skin is never neutral.
    """
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    a_all = lab[..., 1] - 128.0
    b_all = lab[..., 2] - 128.0

    if bg_stats.get("available"):
        cast = float(bg_stats["chroma"])
        cast_source = "background"
    else:
        cast = float(np.hypot(a_all.mean(), b_all.mean()))
        cast_source = "grey-world"

    skin = geo.skin_sample_mask().astype(bool)
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    if skin.sum() < 30:
        skin = geo.face_mask(image_bgr.shape[:2]).astype(bool)
    hue = hsv[..., 0][skin].astype(np.float32) * 2.0  # degrees
    sat = hsv[..., 1][skin].astype(np.float32) / 255.0
    # Skin hue wraps through 0; fold reds above 330 down to negative.
    hue = np.where(hue > 330, hue - 360, hue)

    bgr = image_bgr.reshape(-1, 3).astype(np.float32)
    means = bgr.mean(axis=0) + 1e-6
    grey_world = float(means.max() / means.min())

    # Is it actually a colour photo?
    diff = np.abs(image_bgr[..., 0].astype(np.int16) - image_bgr[..., 1].astype(np.int16))
    diff += np.abs(image_bgr[..., 1].astype(np.int16) - image_bgr[..., 2].astype(np.int16))
    is_colour = float(diff.mean()) > 6.0

    return {
        "cast": round(cast, 2),
        "cast_source": cast_source,
        "grey_world_ratio": round(grey_world, 3),
        "skin_hue": round(float(np.median(hue)), 1),
        "skin_saturation": round(float(np.median(sat)), 3),
        "is_colour": is_colour,
    }


def noise(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    """Sigma estimate on flat skin, and a crude block/pixelation detector."""
    skin = geo.skin_sample_mask().astype(bool)
    grey = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    if skin.sum() < 100:
        sigma = 0.0
    else:
        hp = grey - cv2.GaussianBlur(grey, (0, 0), 1.2)
        sigma = float(np.std(hp[skin]))

    # Pixelation: upscaled images have unusually low high-frequency energy at
    # 1 px scale relative to 2 px scale.
    f1 = float(np.mean(np.abs(grey - cv2.GaussianBlur(grey, (0, 0), 1.0))))
    f2 = float(np.mean(np.abs(grey - cv2.GaussianBlur(grey, (0, 0), 2.0))))
    ratio = f1 / (f2 + 1e-6)
    return {"sigma": round(sigma, 2), "detail_ratio": round(ratio, 3)}


def highlights(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    """
    Flash reflection on skin and glare on lenses.

    A specular hotspot is a small, bright, desaturated blob. We measure the
    fraction of skin covered by them, and separately the fraction inside the
    eye boxes (which is where spectacle glare shows up).
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    v = hsv[..., 2].astype(np.float32)
    s = hsv[..., 1].astype(np.float32)

    face_mask = geo.face_mask(image_bgr.shape[:2]).astype(bool)
    if face_mask.sum() < 100:
        return {"skin_hotspot": 0.0, "eye_glare": 0.0, "max_blob": 0.0}

    face_v = v[face_mask]
    thresh = max(float(np.percentile(face_v, 99.0)), 235.0)
    hot = ((v >= thresh) & (s < 45)).astype(np.uint8)
    hot = cv2.morphologyEx(hot, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    skin_hot = float((hot[face_mask] > 0).mean())

    n, _, stats, _ = cv2.connectedComponentsWithStats(
        cv2.bitwise_and(hot, face_mask.astype(np.uint8)), 8
    )
    max_blob = 0.0
    if n > 1:
        max_blob = float(stats[1:, cv2.CC_STAT_AREA].max() / face_mask.sum())

    glare = []
    for box in geo.eye_regions(1.9):
        region = _roi(hot, box)
        if region.size:
            glare.append(float((region > 0).mean()))
    return {
        "skin_hotspot": round(skin_hot, 4),
        "eye_glare": round(max(glare) if glare else 0.0, 4),
        "max_blob": round(max_blob, 4),
    }


def face_shadow(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    """
    Directional lighting on the face.

    `asymmetry` compares the mean lightness of the two halves of the face
    split along the actual facial midline (so it survives a turned head).
    `local_range` catches a hard shadow edge crossing the face.
    """
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    lum = lab[..., 0].astype(np.float32) * 100.0 / 255.0
    mask = geo.face_mask(image_bgr.shape[:2]).astype(bool)
    if mask.sum() < 200:
        return {"asymmetry": 0.0, "local_range": 0.0, "vertical_gradient": 0.0}

    ys, xs = np.nonzero(mask)
    mid = geo.face_midline_x
    left = xs < mid
    right = ~left
    if left.sum() < 50 or right.sum() < 50:
        asym = 0.0
    else:
        asym = float(abs(lum[ys[left], xs[left]].mean() - lum[ys[right], xs[right]].mean()))

    top = ys < geo.eye_line_y
    if top.sum() > 50 and (~top).sum() > 50:
        vgrad = float(lum[ys[top], xs[top]].mean() - lum[ys[~top], xs[~top]].mean())
    else:
        vgrad = 0.0

    # Low-frequency illumination spread across the face.
    illum = cv2.GaussianBlur(lum, (0, 0), max(geo.face_width * 0.08, 3))
    vals = illum[mask]
    local_range = float(np.percentile(vals, 95) - np.percentile(vals, 5))

    return {
        "asymmetry": round(asym, 2),
        "local_range": round(local_range, 2),
        "vertical_gradient": round(vgrad, 2),
    }


def red_eye(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    """
    Red eye, measured as absolute red excess in the pupil core.

    A ratio like r/(g+b) cannot tell red eye from a brown iris: brown eyes are
    genuinely reddish and score 1.2-1.3 on that scale, right on top of any
    useful threshold. Flash red eye differs in kind, not degree - the pupil,
    normally the darkest part of the face, lights up and its red channel runs
    far ahead of the other two. Measuring that excess directly separates them.
    """
    b, g, r = [c.astype(np.float32) for c in cv2.split(image_bgr)]
    excess = (r - np.maximum(g, b)) / 255.0
    lum = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32) * 100.0 / 255.0

    worst = 0.0
    lightest = 0.0
    circles = geo.iris_circles()
    for cx, cy, rad in circles:
        mask = np.zeros(image_bgr.shape[:2], np.uint8)
        # Pupil core only. The outer iris carries the eye's own colour, which is
        # exactly the signal we do not want.
        cv2.circle(mask, (int(cx), int(cy)), max(int(rad * 0.45), 1), 255, -1)
        m = mask.astype(bool)
        if m.sum() < 3:
            continue
        worst = max(worst, float(excess[m].mean()))
        lightest = max(lightest, float(lum[m].mean()))
    return {
        "red_excess": round(worst, 4),
        "pupil_lightness": round(lightest, 1),
        "iris_found": len(circles),
    }


def eye_occlusion(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    """
    Hair or a heavy frame across the eyes, detected by loss of local contrast.

    An open, unobstructed eye is the highest-contrast thing on a face - a dark
    iris against bright sclera. Anything lying across it flattens that range.
    Measuring the eye's tonal range against the face's own range keeps the test
    independent of exposure; an absolute darkness test, by contrast, just
    re-measures how dark the photograph is and flags every underexposed face.
    """
    lum = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32) * 100.0 / 255.0
    face = geo.face_mask().astype(bool)
    face_range = (
        float(np.percentile(lum[face], 92) - np.percentile(lum[face], 8))
        if face.sum() > 50
        else 1.0
    )

    ranges: List[float] = []
    for box in geo.eye_regions(1.0):
        region = _roi(lum, box)
        if region.size < 16:
            continue
        ranges.append(float(np.percentile(region, 90) - np.percentile(region, 10)))

    if not ranges:
        return {"eye_contrast": 1.0, "eye_range": 0.0, "face_range": round(face_range, 1)}

    eye_range = min(ranges)  # judge on the worse of the two eyes
    # The relative term carries the decision on a normally exposed face; the
    # absolute term catches the case where the whole face is flat, where a
    # ratio of small numbers would otherwise look healthy.
    contrast = min(eye_range / max(face_range, 1e-3), eye_range / ABSOLUTE_EYE_RANGE)
    return {
        "eye_contrast": round(contrast, 3),
        "eye_range": round(eye_range, 1),
        "face_range": round(face_range, 1),
    }


def glasses_hint(image_bgr: np.ndarray, geo: FaceGeometry) -> Dict:
    """
    Very light-touch spectacle detector: strong horizontal edge energy across
    the nose bridge, between the eyes. Used only to tailor advice.
    """
    from .landmarks import NOSE_BRIDGE

    bridge = geo.p(NOSE_BRIDGE)
    w = geo.interocular
    box = (bridge[0] - w * 0.55, bridge[1] - w * 0.28, bridge[0] + w * 0.55, bridge[1] + w * 0.28)
    region = _roi(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY), box)
    if region.size < 50:
        return {"likely": False, "edge_energy": 0.0}
    sob = cv2.Sobel(region.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    energy = float(np.mean(np.abs(sob)) / 255.0)
    return {"likely": energy > 0.055, "edge_energy": round(energy, 4)}


def measure_all(image_bgr: np.ndarray, geo: FaceGeometry, bg_stats: Dict) -> Dict:
    return {
        "resolution": resolution(image_bgr, geo),
        "sharpness": sharpness(image_bgr, geo),
        "exposure": exposure(image_bgr, geo),
        "colour": colour_balance(image_bgr, geo, bg_stats),
        "noise": noise(image_bgr, geo),
        "highlights": highlights(image_bgr, geo),
        "shadow": face_shadow(image_bgr, geo),
        "red_eye": red_eye(image_bgr, geo),
        "occlusion": eye_occlusion(image_bgr, geo),
        "glasses": glasses_hint(image_bgr, geo),
        "background": bg_stats,
        "geometry": geo.summary(),
    }
