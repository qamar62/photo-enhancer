"""
The rule book.

`evaluate()` turns raw measurements into a list of pass / warn / fail results,
each carrying the number that was measured, the requirement it was measured
against, and - when it fails - advice written in the language of the guideline
sheet the user was given.

Every threshold lives in this file so the whole standard can be read, audited
and tuned in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from .spec import PhotoSpec

PASS, WARN, FAIL = "pass", "warn", "fail"

CRITICAL, MAJOR, MINOR = "critical", "major", "minor"
_WEIGHT = {CRITICAL: 10.0, MAJOR: 5.0, MINOR: 2.0}
_PENALTY = {PASS: 0.0, WARN: 0.45, FAIL: 1.0}
# Score band each verdict reports within, worst to best. See summarise().
_BAND = {
    "rejected": (0.0, 40.0),
    "needs_attention": (40.0, 75.0),
    "acceptable": (75.0, 95.0),
    "compliant": (95.0, 100.0),
}

FRAMING, POSE, EXPRESSION, LIGHTING, BACKGROUND, QUALITY, SUBJECT = (
    "framing",
    "pose",
    "expression",
    "lighting",
    "background",
    "quality",
    "subject",
)

CATEGORY_LABELS = {
    FRAMING: "Size and framing",
    POSE: "Head position",
    EXPRESSION: "Eyes and expression",
    LIGHTING: "Lighting",
    BACKGROUND: "Background",
    QUALITY: "Image quality",
    SUBJECT: "Subject",
}


@dataclass
class Check:
    id: str
    category: str
    label: str
    status: str
    requirement: str
    measured: str
    severity: str = MAJOR
    value: Optional[float] = None
    tip: str = ""
    auto_fixable: bool = False
    fixed: bool = False

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["category_label"] = CATEGORY_LABELS.get(self.category, self.category)
        return d


def _band(value: float, lo: float, hi: float, tol: float) -> str:
    """pass inside [lo, hi]; warn inside the tolerance band either side."""
    if lo <= value <= hi:
        return PASS
    if (lo - tol) <= value <= (hi + tol):
        return WARN
    return FAIL


def _below(value: float, good: float, acceptable: float) -> str:
    if value <= good:
        return PASS
    if value <= acceptable:
        return WARN
    return FAIL


def _above(value: float, good: float, acceptable: float) -> str:
    if value >= good:
        return PASS
    if value >= acceptable:
        return WARN
    return FAIL


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def evaluate(
    m: Dict,
    spec: PhotoSpec,
    crop: Optional[Dict] = None,
    fixes: Optional[Dict] = None,
    source: Optional[Dict] = None,
) -> List[Check]:
    """
    m      - the dict returned by quality.measure_all() for the FINAL image
    crop   - CropPlan.to_dict() when the image was re-framed
    fixes  - {check_id: True} for issues the pipeline repaired
    source - the same dict for the ORIGINAL upload, when the two differ.

    Two questions can only honestly be asked of the original: how many real
    pixels the face had, and whether there were enough of them to judge focus
    at all. Asking them of the final image measures our own upscaler - the head
    is 75% of an 827x1063 frame by construction, so a resolution rule applied
    there passes every photo ever uploaded. Defaults to `m` for analyse(), where
    the original *is* the final image.
    """
    fixes = fixes or {}
    src = source or m
    geo = m["geometry"]
    res = src["resolution"]
    sharp = m["sharpness"]
    src_sharp = src["sharpness"]
    exp = m["exposure"]
    col = m["colour"]
    noi = m["noise"]
    hot = m["highlights"]
    shd = m["shadow"]
    red = m["red_eye"]
    occ = m["occlusion"]
    bg = m["background"]
    glasses = m.get("glasses", {})

    out: List[Check] = []
    add = out.append

    # ------------------------------------------------------------- subject
    add(
        Check(
            id="single_subject",
            category=SUBJECT,
            label="One person only",
            status=PASS if geo["face_count"] == 1 else FAIL,
            severity=CRITICAL,
            requirement="exactly one face in the frame",
            measured=f"{geo['face_count']} face(s) detected",
            value=float(geo["face_count"]),
            tip="The photo must show you alone - no chair backs, toys or other people.",
        )
    )

    head_src = res["head_height_px"]
    add(
        Check(
            id="resolution",
            category=SUBJECT,
            label="Enough detail in the original",
            status=_above(head_src, spec.min_source_head_px, spec.min_source_head_px * 0.6),
            severity=MAJOR,
            requirement=f"head at least {spec.min_source_head_px}px tall in the source",
            measured=f"{head_src:.0f}px head height",
            value=head_src,
            tip="Move closer or use a higher-resolution camera; an upscaled face looks pixelated in print.",
        )
    )

    # ------------------------------------------------------------- framing
    if crop:
        head_frac = crop["head_fraction"]
        eye_frac = crop["eye_fraction"]
    else:
        head_frac = geo["head_height_px"] / max(res["height"], 1)
        eye_frac = geo["eye_line_y"] / max(res["height"], 1)

    add(
        Check(
            id="head_size",
            category=FRAMING,
            label="Face fills the frame correctly",
            status=_band(head_frac, spec.head_min, spec.head_max, 0.03),
            severity=CRITICAL if spec.strict else MINOR,
            requirement=f"head {_pct(spec.head_min)}-{_pct(spec.head_max)} of image height",
            measured=_pct(head_frac),
            value=round(head_frac, 4),
            tip="Your face must take up 70-80% of the photograph - not too close, not too far away.",
            auto_fixable=True,
            fixed=bool(fixes.get("head_size")),
        )
    )
    add(
        Check(
            id="eye_line",
            category=FRAMING,
            label="Eye line height",
            status=_band(eye_frac, spec.eye_min, spec.eye_max, 0.04),
            severity=MAJOR if spec.strict else MINOR,
            requirement=f"eyes {_pct(spec.eye_min)}-{_pct(spec.eye_max)} down from the top",
            measured=_pct(eye_frac),
            value=round(eye_frac, 4),
            tip="The frame should sit so your eyes fall just above the middle of the photo.",
            auto_fixable=True,
            fixed=bool(fixes.get("eye_line")),
        )
    )

    if crop:
        offset = abs(crop.get("centre_offset", 0.0))
        add(
            Check(
                id="centring",
                category=FRAMING,
                label="Head centred horizontally",
                status=_below(offset, spec.centre_tolerance, spec.centre_tolerance * 2),
                severity=MINOR,
                requirement=f"face midline within ±{_pct(spec.centre_tolerance)} of centre",
                measured=_pct(offset),
                value=round(offset, 4),
                tip="Centre yourself in the frame - portrait-style off-centre framing is not accepted.",
                auto_fixable=True,
                fixed=bool(fixes.get("centring")),
            )
        )
        ext = crop.get("extension", 0.0)
        if ext > 0.02:
            add(
                Check(
                    id="frame_extended",
                    category=FRAMING,
                    label="Original photo was too tight",
                    status=WARN if ext < 0.18 else FAIL,
                    severity=MAJOR,
                    requirement="the full head and top of the shoulders must be in the original",
                    measured=f"{_pct(ext)} of the frame had to be reconstructed",
                    value=round(ext, 4),
                    tip="Step back and re-shoot with space around your head and shoulders.",
                )
            )

    # ---------------------------------------------------------------- pose
    add(
        Check(
            id="head_tilt",
            category=POSE,
            label="Head not tilted",
            status=_below(abs(geo["roll_deg"]), spec.max_roll_deg, spec.max_roll_deg * 2.2),
            severity=MAJOR,
            requirement=f"tilt within ±{spec.max_roll_deg:g}°",
            measured=f"{geo['roll_deg']:+.1f}°",
            value=geo["roll_deg"],
            tip="Keep your head upright - eyes level, not tilted to one side.",
            auto_fixable=True,
            fixed=bool(fixes.get("head_tilt")),
        )
    )
    add(
        Check(
            id="facing_camera",
            category=POSE,
            label="Facing square on to the camera",
            status=_below(abs(geo["yaw_deg"]), spec.max_yaw_deg, spec.max_yaw_deg * 2.0),
            severity=CRITICAL,
            requirement=f"turn within ±{spec.max_yaw_deg:g}°",
            measured=f"{geo['yaw_deg']:+.1f}°",
            value=geo["yaw_deg"],
            tip="Face the camera square on, not over one shoulder - both edges of your face must show clearly.",
        )
    )
    add(
        Check(
            id="chin_level",
            category=POSE,
            label="Chin level (not up or down)",
            status=_below(abs(geo["pitch_deg"]), spec.max_pitch_deg, spec.max_pitch_deg * 2.0),
            severity=MAJOR,
            requirement=f"chin within ±{spec.max_pitch_deg:g}°",
            measured=f"{geo['pitch_deg']:+.1f}°",
            value=geo["pitch_deg"],
            tip="Look directly at the camera lens with your chin level.",
        )
    )

    # ---------------------------------------------------------- expression
    ear = geo["eye_aperture"]
    add(
        Check(
            id="eyes_open",
            category=EXPRESSION,
            label="Eyes open",
            status=_above(ear, 0.21, 0.15),
            severity=CRITICAL,
            requirement="both eyes clearly open",
            measured=f"aperture {ear:.2f}",
            value=ear,
            tip="Your eyes must be open and clearly visible.",
        )
    )
    add(
        Check(
            id="eyes_visible",
            category=EXPRESSION,
            label="Eyes not covered",
            status=_above(occ["eye_contrast"], 0.40, 0.25),
            severity=MAJOR,
            requirement="no hair or frames across the eyes",
            measured=f"eye detail {occ['eye_contrast']:.2f}× the face average",
            value=occ["eye_contrast"],
            tip="Sweep hair away from your eyes, and make sure heavy frames do not cover any part of them.",
        )
    )
    mar = geo["mouth_aperture"]
    add(
        Check(
            id="mouth_closed",
            category=EXPRESSION,
            label="Mouth closed",
            status=_below(mar, 0.06, 0.12),
            severity=MAJOR,
            requirement="mouth closed",
            measured=f"opening {mar:.2f}",
            value=mar,
            tip="Keep your mouth closed with a neutral expression.",
        )
    )
    smile = geo["smile_ratio"]
    add(
        Check(
            id="neutral_expression",
            category=EXPRESSION,
            label="Neutral expression",
            status=_below(smile, 1.22, 1.35),
            severity=MINOR,
            requirement="no broad smile",
            measured=f"mouth width {smile:.2f}× eye spacing",
            value=smile,
            tip="A neutral expression is required - relax your mouth.",
        )
    )

    # ------------------------------------------------------------ lighting
    skin_l = exp["skin_lightness"]
    add(
        Check(
            id="brightness",
            category=LIGHTING,
            label="Appropriate brightness",
            status=_band(skin_l, 42, 78, 6),
            severity=MAJOR,
            requirement="facial skin lightness 42-78 (L*)",
            measured=f"{skin_l:.0f}",
            value=skin_l,
            tip="The photo must not be too dark or too light - use even, front-on light.",
            auto_fixable=True,
            fixed=bool(fixes.get("brightness")),
        )
    )
    add(
        Check(
            id="contrast",
            category=LIGHTING,
            label="Appropriate contrast",
            status=_band(exp["face_contrast"], 26, 72, 8),
            severity=MINOR,
            requirement="facial contrast 26-72",
            measured=f"{exp['face_contrast']:.0f}",
            value=exp["face_contrast"],
            tip="A washed-out photo will be rejected; aim for natural contrast.",
            auto_fixable=True,
            fixed=bool(fixes.get("contrast")),
        )
    )
    add(
        Check(
            id="clipping",
            category=LIGHTING,
            label="No burnt-out or blocked-up areas",
            status=_below(max(exp["highlight_clip"], exp["shadow_clip"]), 0.01, 0.04),
            severity=MAJOR,
            requirement="under 1% of the face clipped",
            measured=f"{_pct(exp['highlight_clip'])} blown / {_pct(exp['shadow_clip'])} black",
            value=max(exp["highlight_clip"], exp["shadow_clip"]),
            tip="Move away from direct sun or a bare flash; detail lost to pure white or pure black cannot be recovered.",
        )
    )
    add(
        Check(
            id="even_lighting",
            category=LIGHTING,
            label="No shadows across the face",
            status=_below(shd["asymmetry"], 5.0, 11.0),
            severity=MAJOR,
            requirement="left/right lightness difference under 5",
            measured=f"{shd['asymmetry']:.1f}",
            value=shd["asymmetry"],
            tip="Light yourself evenly from the front - side light casts a shadow across your face.",
            auto_fixable=True,
            fixed=bool(fixes.get("even_lighting")),
        )
    )
    add(
        Check(
            id="flash_reflection",
            category=LIGHTING,
            label="No flash reflection on skin",
            status=_below(hot["skin_hotspot"], 0.008, 0.03),
            severity=MAJOR,
            requirement="under 0.8% of the face blown out by specular highlights",
            measured=_pct(hot["skin_hotspot"]),
            value=hot["skin_hotspot"],
            tip="Avoid direct flash - bounce the light or use diffuse daylight.",
            auto_fixable=True,
            fixed=bool(fixes.get("flash_reflection")),
        )
    )
    lens_status = _below(hot["eye_glare"], 0.012, 0.045)
    add(
        Check(
            id="lens_glare",
            category=LIGHTING,
            label="No reflection off glasses",
            status=lens_status,
            severity=CRITICAL,
            requirement="no flash reflection over the eyes",
            measured=_pct(hot["eye_glare"]),
            value=hot["eye_glare"],
            tip=(
                "Tilt your glasses down slightly or take them off and re-shoot - "
                "reflection over the lenses cannot be repaired without inventing your eyes."
                if glasses.get("likely")
                else "Re-shoot without a direct flash pointed at your face."
            ),
        )
    )
    add(
        Check(
            id="red_eye",
            category=LIGHTING,
            label="No red eye",
            status=_below(red["red_excess"], 0.06, 0.12),
            severity=MAJOR,
            requirement="pupils neutral, not red",
            measured=f"red excess {red['red_excess']:.3f}",
            value=red["red_excess"],
            tip="Turn off direct flash, or use the red-eye repair this tool applies automatically.",
            auto_fixable=True,
            fixed=bool(fixes.get("red_eye")),
        )
    )

    # ---------------------------------------------------------- background
    if bg.get("available"):
        add(
            Check(
                id="bg_plain",
                category=BACKGROUND,
                label="Plain background",
                status=_below(bg["edge_density"], 0.02, 0.06),
                severity=MAJOR,
                requirement="no objects or pattern behind you",
                measured=f"detail {bg['edge_density']:.3f}",
                value=bg["edge_density"],
                tip="Stand in front of a plain wall - a busy background is not accepted.",
                auto_fixable=True,
                fixed=bool(fixes.get("background")),
            )
        )
        add(
            Check(
                id="bg_uniform",
                category=BACKGROUND,
                label="Uniform background tone",
                status=_below(max(bg["lightness_std"], bg["chroma_std"]), 4.0, 9.0),
                severity=MINOR,
                requirement="even tone across the background",
                measured=f"variation {max(bg['lightness_std'], bg['chroma_std']):.1f}",
                value=max(bg["lightness_std"], bg["chroma_std"]),
                tip="Light the background evenly, or let the tool replace it.",
                auto_fixable=True,
                fixed=bool(fixes.get("background")),
            )
        )
        if spec.background_must_be_light:
            add(
                Check(
                    id="bg_light",
                    category=BACKGROUND,
                    label="Light-coloured background",
                    status=_above(bg["lightness"], 70.0, 55.0),
                    severity=MAJOR,
                    requirement="plain light-coloured background (L* ≥ 70)",
                    measured=f"L* {bg['lightness']:.0f}",
                    value=bg["lightness"],
                    tip="Use a white, off-white or light grey background.",
                    auto_fixable=True,
                    fixed=bool(fixes.get("background")),
                )
            )
        add(
            Check(
                id="bg_shadow",
                category=BACKGROUND,
                label="No shadow behind the head",
                status=_below(max(bg["gradient_lr"], bg["gradient_tb"]), 4.0, 9.0),
                severity=MAJOR,
                requirement="no cast shadow on the background",
                measured=f"gradient {max(bg['gradient_lr'], bg['gradient_tb']):.1f}",
                value=max(bg["gradient_lr"], bg["gradient_tb"]),
                tip="Stand about a metre away from the wall so your shadow does not fall on it.",
                auto_fixable=True,
                fixed=bool(fixes.get("background")),
            )
        )

    # ------------------------------------------------------------- quality
    # Below the reference face width a focus score tracks how big the face was,
    # not how sharp it was, so failing on it would be a guess dressed up as a
    # measurement. Say so, drop it to advisory, and let `resolution` - which is
    # precisely the "not enough pixels" rule - deliver the verdict instead.
    focus_readable = bool(src_sharp.get("reliable", True))
    add(
        Check(
            id="sharpness",
            category=QUALITY,
            label="In sharp focus",
            status=_above(sharp["normalised"], 35.0, 18.0) if focus_readable else WARN,
            severity=CRITICAL if focus_readable else MINOR,
            requirement="focus score 35+/100",
            measured=(
                f"{sharp['normalised']:.0f}/100"
                if focus_readable
                else f"cannot be judged - the face is only {src_sharp.get('face_px', 0)}px wide in your original"
            ),
            value=sharp["normalised"],
            tip=(
                "The photo must be in sharp focus and clear - hold the camera steady and tap to focus on the eyes."
                if focus_readable
                else "Send a larger original and we can check the focus properly."
            ),
            auto_fixable=True,
            fixed=bool(fixes.get("sharpness")),
        )
    )
    add(
        Check(
            id="noise",
            category=QUALITY,
            label="Clean, not grainy",
            status=_below(noi["sigma"], 4.5, 8.0),
            severity=MINOR,
            requirement="skin noise under 4.5",
            measured=f"{noi['sigma']:.1f}",
            value=noi["sigma"],
            tip="Shoot in better light instead of raising ISO.",
            auto_fixable=True,
            fixed=bool(fixes.get("noise")),
        )
    )
    add(
        Check(
            id="colour_neutral",
            category=QUALITY,
            label="Colour neutral",
            status=_below(col["cast"], 5.0, 11.0),
            severity=MAJOR,
            requirement="neutral tones with no colour cast",
            measured=f"cast {col['cast']:.1f}",
            value=col["cast"],
            tip="The photograph must be colour neutral - avoid mixed or coloured lighting.",
            auto_fixable=True,
            fixed=bool(fixes.get("colour_neutral")),
        )
    )
    add(
        Check(
            id="skin_tone",
            category=QUALITY,
            label="Natural skin tones",
            status=(
                PASS
                if -8 <= col["skin_hue"] <= 42 and 0.08 <= col["skin_saturation"] <= 0.62
                else WARN
            ),
            severity=MINOR,
            requirement="skin hue 0-40°, moderate saturation",
            measured=f"hue {col['skin_hue']:.0f}°, sat {col['skin_saturation']:.2f}",
            value=col["skin_hue"],
            tip="Skin tones must look natural - no filters, and no heavy colour cast.",
            auto_fixable=True,
            fixed=bool(fixes.get("colour_neutral")),
        )
    )
    add(
        Check(
            id="colour_photo",
            category=QUALITY,
            label="Colour photograph",
            status=PASS if col["is_colour"] else FAIL,
            severity=MAJOR,
            requirement="colour, not black and white",
            measured="colour" if col["is_colour"] else "greyscale",
            tip="Photographs taken with a digital camera must be high quality colour.",
        )
    )
    add(
        Check(
            id="pixelation",
            category=QUALITY,
            label="Not pixelated or over-compressed",
            status=_above(noi["detail_ratio"], 0.42, 0.30),
            severity=MINOR,
            requirement="fine detail present at pixel level",
            measured=f"{noi['detail_ratio']:.2f}",
            value=noi["detail_ratio"],
            tip="Use the original file from the camera, not a screenshot or a re-saved messenger copy.",
        )
    )

    return out


def summarise(checks: List[Check]) -> Dict:
    """Weighted score, verdict and the human-readable to-do list."""
    failures = [c for c in checks if c.status == FAIL]
    warnings = [c for c in checks if c.status == WARN]
    critical = [c for c in failures if c.severity == CRITICAL]

    if critical:
        verdict = "rejected"
    elif failures:
        verdict = "needs_attention"
    elif warnings:
        verdict = "acceptable"
    else:
        verdict = "compliant"

    total = sum(_WEIGHT[c.severity] for c in checks) or 1.0
    lost = sum(_WEIGHT[c.severity] * _PENALTY[c.status] for c in checks)
    quality = max(0.0, 1.0 - lost / total)

    # A photo is judged rule by rule, not on average: an examiner who finds one
    # breach does not care that thirty other things were right. Left as a plain
    # average, a single broken rule out of thirty costs about three points, so a
    # photo that will certainly be refused reads 94/100 - a near miss, sitting
    # next to its own red FAIL badge.
    #
    # So the verdict picks the band and the average only positions the photo
    # inside it. The number can then never contradict the ruling beside it, the
    # bands cannot overlap, and the before/after delta stays meaningful: fixing
    # the one blocking issue visibly jumps the score into the next band, while
    # tidying up warnings moves it within the current one.
    lo, hi = _BAND[verdict]
    score = lo + (hi - lo) * quality

    by_category: Dict[str, Dict] = {}
    for c in checks:
        entry = by_category.setdefault(
            c.category,
            {"label": CATEGORY_LABELS.get(c.category, c.category), "pass": 0, "warn": 0, "fail": 0},
        )
        entry[c.status] += 1

    return {
        "score": round(score, 1),
        "verdict": verdict,
        "passed": sum(1 for c in checks if c.status == PASS),
        "warnings": len(warnings),
        "failures": len(failures),
        "blocking": [c.id for c in critical],
        "retake_reasons": [
            {"id": c.id, "label": c.label, "tip": c.tip}
            for c in failures
            if not c.auto_fixable or not c.fixed
        ],
        "by_category": by_category,
    }
