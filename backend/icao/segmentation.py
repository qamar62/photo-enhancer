"""
Subject / background separation.

Primary matte comes from rembg (u2net_human_seg). If the model cannot be
loaded (offline container, first-run download blocked) we fall back to
MediaPipe SelfieSegmentation, and finally to a face-shaped ellipse so the
pipeline degrades instead of exploding.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger("icao.segmentation")

REMBG_MODEL = os.getenv("REMBG_MODEL", "u2net_human_seg")

_lock = threading.Lock()
_rembg_session = None
_rembg_failed = False
_selfie = None


def _get_rembg():
    global _rembg_session, _rembg_failed
    if _rembg_session is not None or _rembg_failed:
        return _rembg_session
    with _lock:
        if _rembg_session is None and not _rembg_failed:
            try:
                from rembg import new_session

                _rembg_session = new_session(REMBG_MODEL)
                log.info("rembg session ready (%s)", REMBG_MODEL)
            except Exception as exc:  # pragma: no cover - environment dependent
                log.warning("rembg unavailable (%s); falling back to selfie segmentation", exc)
                _rembg_failed = True
    return _rembg_session


def _get_selfie():
    global _selfie
    if _selfie is None:
        import mediapipe as mp

        _selfie = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
    return _selfie


def _rembg_alpha(image_bgr: np.ndarray) -> Optional[np.ndarray]:
    session = _get_rembg()
    if session is None:
        return None
    try:
        from rembg import remove

        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        out = remove(rgb, session=session, only_mask=True)
        if out.ndim == 3:
            out = out[..., -1]
        return out.astype(np.float32) / 255.0
    except Exception as exc:  # pragma: no cover
        log.warning("rembg matting failed: %s", exc)
        return None


def _selfie_alpha(image_bgr: np.ndarray) -> Optional[np.ndarray]:
    try:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        res = _get_selfie().process(rgb)
        return np.asarray(res.segmentation_mask, dtype=np.float32)
    except Exception as exc:  # pragma: no cover
        log.warning("selfie segmentation failed: %s", exc)
        return None


def _ellipse_alpha(shape: Tuple[int, int], face_box) -> np.ndarray:
    h, w = shape
    alpha = np.zeros((h, w), np.float32)
    if face_box is None:
        return alpha + 1.0
    x1, y1, x2, y2 = face_box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ax, ay = (x2 - x1) * 1.15, (y2 - y1) * 1.35
    cv2.ellipse(alpha, (int(cx), int(cy)), (int(ax), int(ay)), 0, 0, 360, 1.0, -1)
    cv2.rectangle(alpha, (int(cx - ax * 1.6), int(cy + ay * 0.5)), (int(cx + ax * 1.6), h), 1.0, -1)
    return cv2.GaussianBlur(alpha, (0, 0), max(w, h) * 0.004)


def subject_alpha(image_bgr: np.ndarray, face_box=None) -> Tuple[np.ndarray, str]:
    """
    Returns (alpha in 0..1 float32, source name).

    Large images are matted at reduced resolution and the matte is upsampled -
    u2net runs at 320px internally anyway, so nothing is lost and it is ~4x
    faster on a 12 Mpx phone photo.
    """
    h, w = image_bgr.shape[:2]
    longest = max(h, w)
    work = image_bgr
    if longest > 1400:
        s = 1400.0 / longest
        work = cv2.resize(image_bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)

    alpha = _rembg_alpha(work)
    source = "rembg"
    if alpha is None:
        alpha = _selfie_alpha(work)
        source = "selfie"
    if alpha is None:
        return _ellipse_alpha((h, w), face_box), "ellipse"

    if alpha.shape[:2] != (h, w):
        alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(alpha, 0.0, 1.0), source


def refine_alpha(alpha: np.ndarray, feather_px: float = 1.2, shrink_px: int = 1) -> np.ndarray:
    """
    Clean the matte: fill pinholes, shave one pixel off the silhouette so the
    old background does not survive as a halo, then feather the edge.
    """
    a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    a8 = cv2.morphologyEx(a8, cv2.MORPH_CLOSE, k)
    a8 = cv2.morphologyEx(a8, cv2.MORPH_OPEN, k)

    # keep only the largest connected blob (drops stray specks)
    solid = (a8 > 128).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(solid, 8)
    if n > 2:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        a8 = np.where(labels == biggest, a8, 0).astype(np.uint8)

    if shrink_px > 0:
        er = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (shrink_px * 2 + 1,) * 2)
        a8 = cv2.erode(a8, er)

    out = a8.astype(np.float32) / 255.0
    if feather_px > 0:
        out = cv2.GaussianBlur(out, (0, 0), feather_px)
    return np.clip(out, 0.0, 1.0)


def hair_top_y(alpha: np.ndarray, centre_x: float, band: float) -> Optional[float]:
    """
    Topmost subject pixel within a horizontal band around the face midline -
    i.e. the top of the hair, which must stay inside the frame.
    """
    h, w = alpha.shape[:2]
    x1 = int(max(0, centre_x - band / 2))
    x2 = int(min(w, centre_x + band / 2))
    if x2 <= x1:
        return None
    strip = alpha[:, x1:x2] > 0.5
    rows = np.where(strip.any(axis=1))[0]
    if rows.size == 0:
        return None
    return float(rows[0])


def composite(image_bgr: np.ndarray, alpha: np.ndarray, colour_bgr) -> np.ndarray:
    """Alpha-composite the subject over a flat colour."""
    a = alpha[..., None].astype(np.float32)
    bg = np.empty_like(image_bgr, dtype=np.float32)
    bg[:] = np.asarray(colour_bgr, dtype=np.float32)
    out = image_bgr.astype(np.float32) * a + bg * (1.0 - a)
    return np.clip(out, 0, 255).astype(np.uint8)


def background_stats(image_bgr: np.ndarray, alpha: np.ndarray) -> Dict:
    """
    Describe the ORIGINAL background: is it plain, uniform, light, shadow-free?

    Only pixels well outside the subject are sampled, and the band immediately
    around the silhouette is excluded so hair wisps do not pollute the stats.
    """
    h, w = image_bgr.shape[:2]
    bg_mask = (alpha < 0.05).astype(np.uint8)
    near = cv2.dilate(
        (alpha > 0.05).astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)),
    )
    bg_mask = cv2.bitwise_and(bg_mask, 1 - near)

    count = int(bg_mask.sum())
    coverage = count / float(h * w)
    if coverage < 0.01:
        return {
            "available": False,
            "coverage": round(coverage, 4),
            "reason": "subject fills the frame - background could not be measured",
        }

    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    m = bg_mask.astype(bool)
    L = lab[..., 0][m].astype(np.float32) * 100.0 / 255.0
    A = lab[..., 1][m].astype(np.float32) - 128.0
    B = lab[..., 2][m].astype(np.float32) - 128.0

    grey = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(grey, (5, 5), 0), 60, 160)
    edge_density = float(edges[m].mean() / 255.0)

    # Shadow behind the head: compare the mean lightness of the left/right and
    # upper/lower halves of the measurable background.
    ys, xs = np.nonzero(bg_mask)
    lum = lab[..., 0].astype(np.float32) * 100.0 / 255.0
    def _half(sel_a, sel_b):
        if sel_a.sum() < 50 or sel_b.sum() < 50:
            return 0.0
        return float(abs(lum[ys[sel_a], xs[sel_a]].mean() - lum[ys[sel_b], xs[sel_b]].mean()))

    left = xs < w / 2
    top = ys < h / 2
    lr_delta = _half(left, ~left)
    tb_delta = _half(top, ~top)

    return {
        "available": True,
        "coverage": round(coverage, 4),
        "lightness": round(float(L.mean()), 1),  # 0-100
        "lightness_std": round(float(L.std()), 2),
        "chroma": round(float(np.hypot(A.mean(), B.mean())), 2),
        "chroma_std": round(float(np.hypot(A.std(), B.std())), 2),
        "edge_density": round(edge_density, 4),
        "gradient_lr": round(lr_delta, 2),
        "gradient_tb": round(tb_delta, 2),
        "mean_bgr": [round(float(image_bgr[..., i][m].mean()), 1) for i in range(3)],
    }
