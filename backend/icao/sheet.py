"""
Print sheets.

Tiles the finished photo across a standard paper size at true physical scale,
with cut guides, so a high-street print shop produces correctly sized photos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import cv2
import numpy as np

from .spec import MM_PER_INCH, PhotoSpec


@dataclass(frozen=True)
class Paper:
    id: str
    name: str
    width_mm: float
    height_mm: float


PAPERS: Dict[str, Paper] = {
    p.id: p
    for p in (
        Paper("4x6", '4×6 in photo paper', 152.4, 101.6),
        Paper("5x7", '5×7 in photo paper', 177.8, 127.0),
        Paper("a4", "A4", 297.0, 210.0),
        Paper("a6", "A6", 148.0, 105.0),
    )
}

DEFAULT_PAPER = "4x6"


def build_sheet(
    photo_bgr: np.ndarray,
    spec: PhotoSpec,
    paper_id: str = DEFAULT_PAPER,
    dpi: int = 300,
    gap_mm: float = 2.0,
    margin_mm: float = 4.0,
    cut_guides: bool = True,
    max_copies: int = 0,
) -> Tuple[np.ndarray, Dict]:
    """
    Returns (sheet image BGR, info dict).

    `spec` must be a physical (mm-based) spec; pixel-only specs have no real
    world size to print at.
    """
    paper = PAPERS.get(paper_id)
    if paper is None:
        raise ValueError(f"Unknown paper '{paper_id}'. Available: {', '.join(sorted(PAPERS))}")
    if not spec.physical:
        raise ValueError(
            "Print sheets need a physical size - choose an ICAO/passport preset rather than a free pixel size."
        )

    px_per_mm = dpi / MM_PER_INCH
    sheet_w = int(round(paper.width_mm * px_per_mm))
    sheet_h = int(round(paper.height_mm * px_per_mm))
    cell_w = int(round(spec.width_mm * px_per_mm))
    cell_h = int(round(spec.height_mm * px_per_mm))
    gap = int(round(gap_mm * px_per_mm))
    margin = int(round(margin_mm * px_per_mm))

    cols = max(int((sheet_w - 2 * margin + gap) // (cell_w + gap)), 0)
    rows = max(int((sheet_h - 2 * margin + gap) // (cell_h + gap)), 0)
    if cols == 0 or rows == 0:
        raise ValueError(
            f"{spec.size_label} does not fit on {paper.name}. Try a larger paper size."
        )

    photo = cv2.resize(
        photo_bgr,
        (cell_w, cell_h),
        interpolation=cv2.INTER_AREA if photo_bgr.shape[1] > cell_w else cv2.INTER_CUBIC,
    )

    sheet = np.full((sheet_h, sheet_w, 3), 255, np.uint8)

    grid_w = cols * cell_w + (cols - 1) * gap
    grid_h = rows * cell_h + (rows - 1) * gap
    ox = (sheet_w - grid_w) // 2
    oy = (sheet_h - grid_h) // 2

    placed = 0
    positions: List[Tuple[int, int]] = []
    for r in range(rows):
        for c in range(cols):
            if max_copies and placed >= max_copies:
                break
            x = ox + c * (cell_w + gap)
            y = oy + r * (cell_h + gap)
            sheet[y : y + cell_h, x : x + cell_w] = photo
            positions.append((x, y))
            placed += 1

    if cut_guides:
        grey = (170, 170, 170)
        tick = int(round(2.5 * px_per_mm))
        for x, y in positions:
            cv2.rectangle(sheet, (x, y), (x + cell_w - 1, y + cell_h - 1), grey, 1)
            for cx, cy in ((x, y), (x + cell_w - 1, y), (x, y + cell_h - 1), (x + cell_w - 1, y + cell_h - 1)):
                cv2.line(sheet, (cx - tick, cy), (cx + tick, cy), grey, 1)
                cv2.line(sheet, (cx, cy - tick), (cx, cy + tick), grey, 1)

        label = f"{spec.width_mm:g}x{spec.height_mm:g}mm  |  print at 100% on {paper.name} @ {dpi}dpi"
        cv2.putText(
            sheet,
            label,
            (margin, max(oy - int(1.5 * px_per_mm), 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.32 * px_per_mm / 3.0,
            (120, 120, 120),
            1,
            cv2.LINE_AA,
        )

    info = {
        "paper": paper.id,
        "paper_name": paper.name,
        "dpi": dpi,
        "copies": placed,
        "columns": cols,
        "rows": rows,
        "sheet_px": [sheet_w, sheet_h],
        "cell_mm": [spec.width_mm, spec.height_mm],
        "note": "Print at 100% / 'actual size' - do not let the printer scale to fit.",
    }
    return sheet, info


def list_papers() -> List[Dict]:
    return [
        {"id": p.id, "name": p.name, "width_mm": p.width_mm, "height_mm": p.height_mm}
        for p in PAPERS.values()
    ]
