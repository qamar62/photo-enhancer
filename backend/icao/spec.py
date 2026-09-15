"""
Photo specifications.

The default spec implements the personal-photo requirements in the supplied
ICAO / UK-style guideline sheet:

    * 35-40 mm wide
    * close up of head and top of shoulders so the face takes up 70-80%
      of the photograph
    * plain light-coloured background
    * uniform lighting, no shadows / flash reflections / red eye
    * looking square on at the camera, neutral expression, mouth closed

Everything geometric is expressed as a *fraction of the output image height*
so the same numbers work for any pixel size or DPI.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple

MM_PER_INCH = 25.4


@dataclass(frozen=True)
class PhotoSpec:
    id: str
    name: str
    description: str

    # Physical size. When width_mm is None the spec is pure-pixel (general use).
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    dpi: int = 600

    # Explicit pixel size, only used when width_mm is None.
    px_width: Optional[int] = None
    px_height: Optional[int] = None

    # Head height (crown -> chin) as a fraction of image height.
    head_min: float = 0.70
    head_max: float = 0.80
    head_target: float = 0.75

    # Eye line measured from the TOP of the image, as a fraction of height.
    # ICAO 9303 states 50-60% measured from the bottom edge.
    eye_min: float = 0.40
    eye_max: float = 0.50
    eye_target: float = 0.45

    # Horizontal centring tolerance (fraction of width the face midline may
    # deviate from the centre of the frame).
    centre_tolerance: float = 0.05

    # Minimum free space above the top of the hair, fraction of image height.
    top_margin_min: float = 0.02

    background: Tuple[int, int, int] = (250, 250, 250)
    background_must_be_light: bool = True

    max_roll_deg: float = 5.0
    max_yaw_deg: float = 8.0
    max_pitch_deg: float = 8.0

    # Minimum head height in *source* pixels for a genuinely sharp result.
    min_source_head_px: int = 360

    jpeg_quality: int = 95
    strict: bool = True  # False => geometry rules become advisory only

    # ---------------------------------------------------------------- sizes
    @property
    def width_px(self) -> int:
        if self.width_mm:
            return int(round(self.width_mm / MM_PER_INCH * self.dpi))
        return int(self.px_width or 827)

    @property
    def height_px(self) -> int:
        if self.height_mm:
            return int(round(self.height_mm / MM_PER_INCH * self.dpi))
        return int(self.px_height or 1063)

    @property
    def aspect(self) -> float:
        """width / height"""
        return self.width_px / self.height_px

    @property
    def physical(self) -> bool:
        return self.width_mm is not None

    @property
    def size_label(self) -> str:
        if self.physical:
            return f"{self.width_mm:g}×{self.height_mm:g} mm @ {self.dpi} dpi"
        return f"{self.width_px}×{self.height_px} px"

    def to_dict(self) -> Dict:
        d = asdict(self)
        d.update(
            width_px=self.width_px,
            height_px=self.height_px,
            aspect=round(self.aspect, 4),
            physical=self.physical,
            size_label=self.size_label,
        )
        return d

    def resized(
        self,
        px_width: Optional[int] = None,
        px_height: Optional[int] = None,
        dpi: Optional[int] = None,
        background: Optional[Tuple[int, int, int]] = None,
    ) -> "PhotoSpec":
        """Return a copy with overridden output size / background."""
        data = asdict(self)
        if px_width and px_height:
            data.update(
                width_mm=None, height_mm=None, px_width=int(px_width), px_height=int(px_height)
            )
        if dpi:
            data["dpi"] = int(dpi)
        if background:
            data["background"] = tuple(background)
        return PhotoSpec(**data)


ICAO_35X45 = PhotoSpec(
    id="icao_35x45",
    name="ICAO / UK 35×45 mm",
    description=(
        "The standard in the guideline sheet: 35×45 mm, head and top of "
        "shoulders, face 70-80% of the frame, plain light background."
    ),
    width_mm=35,
    height_mm=45,
    dpi=600,
)

ICAO_40X60 = PhotoSpec(
    id="icao_40x60",
    name="Gulf / Saudi 40×60 mm",
    description="40×60 mm visa format, same face rules as ICAO.",
    width_mm=40,
    height_mm=60,
    dpi=600,
    head_min=0.60,
    head_max=0.72,
    head_target=0.66,
    eye_min=0.38,
    eye_max=0.48,
    eye_target=0.43,
)

SCHENGEN_35X45 = PhotoSpec(
    id="schengen_35x45",
    name="Schengen visa 35×45 mm",
    description="EU / Schengen visa. Face 70-80% of the frame.",
    width_mm=35,
    height_mm=45,
    dpi=600,
)

US_2X2 = PhotoSpec(
    id="us_2x2",
    name="US passport / visa 2×2 in",
    description="51×51 mm square. Head 25-35 mm (50-69%), eyes 56-69% from bottom.",
    width_mm=50.8,
    height_mm=50.8,
    dpi=600,
    head_min=0.50,
    head_max=0.69,
    head_target=0.60,
    eye_min=0.31,
    eye_max=0.44,
    eye_target=0.38,
)

INDIA_51X51 = PhotoSpec(
    id="india_51x51",
    name="India / OCI 51×51 mm",
    description="Square format used for Indian visa and OCI applications.",
    width_mm=51,
    height_mm=51,
    dpi=600,
    head_min=0.60,
    head_max=0.75,
    head_target=0.68,
    eye_min=0.33,
    eye_max=0.45,
    eye_target=0.40,
)

GENERAL_PORTRAIT = PhotoSpec(
    id="general",
    name="General portrait (free size)",
    description=(
        "Non-passport mode: same enhancement engine, relaxed framing. "
        "Use any pixel size you like."
    ),
    width_mm=None,
    height_mm=None,
    px_width=1200,
    px_height=1600,
    head_min=0.45,
    head_max=0.80,
    head_target=0.62,
    eye_min=0.30,
    eye_max=0.52,
    eye_target=0.42,
    centre_tolerance=0.10,
    max_roll_deg=12.0,
    max_yaw_deg=20.0,
    max_pitch_deg=20.0,
    background=(255, 255, 255),
    background_must_be_light=False,
    min_source_head_px=200,
    strict=False,
)

SPECS: Dict[str, PhotoSpec] = {
    s.id: s
    for s in (ICAO_35X45, ICAO_40X60, SCHENGEN_35X45, US_2X2, INDIA_51X51, GENERAL_PORTRAIT)
}

DEFAULT_SPEC_ID = ICAO_35X45.id


def get_spec(spec_id: Optional[str]) -> PhotoSpec:
    if not spec_id:
        return SPECS[DEFAULT_SPEC_ID]
    try:
        return SPECS[spec_id]
    except KeyError:
        raise ValueError(
            f"Unknown spec '{spec_id}'. Available: {', '.join(sorted(SPECS))}"
        )
