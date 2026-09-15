"""
Face geometry from MediaPipe FaceMesh.

Everything the compliance checks need about *where the face is and how it is
posed* is derived here once, so the rest of the pipeline never touches
MediaPipe directly.

Landmark indices used (MediaPipe FaceMesh, 468 + 10 iris points):

    1    nose tip                  152  chin (menton)
    10   mid forehead / trichion   168  nose bridge
    33   left eye outer corner     133  left eye inner corner
    263  right eye outer corner    362  right eye inner corner
    159  left upper lid            145  left lower lid
    386  right upper lid           374  right lower lid
    61   left mouth corner         291  right mouth corner
    13   upper inner lip           14   lower inner lip
    234  left face edge            454  right face edge
    468-472 left iris              473-477 right iris

"Left"/"right" below are *image* left/right (the subject's right/left).
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Indices -------------------------------------------------------------------
NOSE_TIP = 1
CHIN = 152
FOREHEAD = 10
NOSE_BRIDGE = 168
L_EYE_OUT, L_EYE_IN = 33, 133
R_EYE_IN, R_EYE_OUT = 362, 263
L_LID_UP, L_LID_DN = 159, 145
R_LID_UP, R_LID_DN = 386, 374
L_MOUTH, R_MOUTH = 61, 291
LIP_UP_IN, LIP_DN_IN = 13, 14
LIP_UP_OUT, LIP_DN_OUT = 0, 17
L_FACE_EDGE, R_FACE_EDGE = 234, 454
L_BROW, R_BROW = 105, 334
L_CHEEK, R_CHEEK = 50, 280
L_IRIS = (468, 469, 470, 471, 472)
R_IRIS = (473, 474, 475, 476, 477)

FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379,
    378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127,
    162, 21, 54, 103, 67, 109,
]

# Menton -> vertex is about 1.14x menton -> trichion for an adult skull.
SKULL_ABOVE_TRICHION = 1.145

# Canonical 3D model (mm-ish) used for the solvePnP pose estimate.
_MODEL_3D = np.array(
    [
        (0.0, 0.0, 0.0),  # nose tip
        (0.0, -330.0, -65.0),  # chin
        (-225.0, 170.0, -135.0),  # left eye outer corner
        (225.0, 170.0, -135.0),  # right eye outer corner
        (-150.0, -150.0, -125.0),  # left mouth corner
        (150.0, -150.0, -125.0),  # right mouth corner
    ],
    dtype=np.float64,
)
_MODEL_IDX = [NOSE_TIP, CHIN, L_EYE_OUT, R_EYE_OUT, L_MOUTH, R_MOUTH]


class NoFaceError(ValueError):
    pass


_mesh = None
_mesh_lock = threading.Lock()


def _get_mesh(max_faces: int = 4):
    """FaceMesh is expensive to build; keep one warm instance."""
    global _mesh
    if _mesh is None:
        with _mesh_lock:
            if _mesh is None:
                import mediapipe as mp

                if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "face_mesh"):
                    raise RuntimeError(
                        "This build of mediapipe has no FaceMesh solution. "
                        "Install mediapipe==0.10.14 (see backend/requirements.txt)."
                    )
                _mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=True,
                    max_num_faces=max_faces,
                    refine_landmarks=True,  # gives us the iris points
                    min_detection_confidence=0.4,
                )
    return _mesh


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, float) - np.asarray(b, float)))


@dataclass
class FaceGeometry:
    """All measurements are in pixels of the image the landmarks came from."""

    points: np.ndarray  # (N, 2) float32
    image_size: Tuple[int, int]  # (w, h)
    face_count: int = 1
    other_faces: List[Dict] = field(default_factory=list)

    # ------------------------------------------------------------- helpers
    def p(self, idx: int) -> np.ndarray:
        return self.points[idx]

    @property
    def chin(self) -> np.ndarray:
        return self.p(CHIN)

    @property
    def forehead(self) -> np.ndarray:
        return self.p(FOREHEAD)

    @property
    def left_eye(self) -> np.ndarray:
        """Centre of the image-left eye (iris centre when available)."""
        if len(self.points) > L_IRIS[0]:
            return self.points[list(L_IRIS)].mean(axis=0)
        return (self.p(L_EYE_OUT) + self.p(L_EYE_IN)) / 2.0

    @property
    def right_eye(self) -> np.ndarray:
        if len(self.points) > R_IRIS[0]:
            return self.points[list(R_IRIS)].mean(axis=0)
        return (self.p(R_EYE_OUT) + self.p(R_EYE_IN)) / 2.0

    @property
    def eye_centre(self) -> np.ndarray:
        return (self.left_eye + self.right_eye) / 2.0

    @property
    def eye_line_y(self) -> float:
        return float(self.eye_centre[1])

    @property
    def interocular(self) -> float:
        return _dist(self.left_eye, self.right_eye)

    @property
    def face_midline_x(self) -> float:
        """Robust horizontal centre of the face (eyes + nose + chin + mouth)."""
        parts = [
            self.eye_centre[0],
            self.p(NOSE_BRIDGE)[0],
            self.chin[0],
            (self.p(L_MOUTH)[0] + self.p(R_MOUTH)[0]) / 2.0,
        ]
        return float(np.mean(parts))

    @property
    def face_width(self) -> float:
        return _dist(self.p(L_FACE_EDGE), self.p(R_FACE_EDGE))

    @property
    def chin_to_trichion(self) -> float:
        return _dist(self.chin, self.forehead)

    @property
    def crown_y(self) -> float:
        """
        Estimated top of the skull (the ICAO 'crown'), excluding hair volume.

        MediaPipe's landmark 10 sits near the trichion; the vertex is about
        14.5% further up along the chin->forehead axis.
        """
        vec = self.forehead - self.chin
        vertex = self.chin + vec * SKULL_ABOVE_TRICHION
        return float(vertex[1])

    @property
    def head_height(self) -> float:
        """Crown -> chin in pixels."""
        return float(self.chin[1] - self.crown_y)

    @property
    def roll_deg(self) -> float:
        """In-plane tilt from the eye line. Positive = head tilted clockwise."""
        dx = float(self.right_eye[0] - self.left_eye[0])
        dy = float(self.right_eye[1] - self.left_eye[1])
        return math.degrees(math.atan2(dy, dx))

    # ------------------------------------------------------------- 3D pose
    def pose(self) -> Tuple[float, float, float]:
        """(yaw, pitch, roll) in degrees via solvePnP. Yaw>0 = turned to image right."""
        w, h = self.image_size
        focal = float(w)
        cam = np.array(
            [[focal, 0, w / 2.0], [0, focal, h / 2.0], [0, 0, 1]], dtype=np.float64
        )
        pts = np.array([self.points[i] for i in _MODEL_IDX], dtype=np.float64)
        ok, rvec, tvec = cv2.solvePnP(
            _MODEL_3D, pts, cam, np.zeros((4, 1)), flags=cv2.SOLVEPNP_ITERATIVE
        )
        if not ok:
            return 0.0, 0.0, self.roll_deg
        rmat, _ = cv2.Rodrigues(rvec)
        sy = math.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
        if sy > 1e-6:
            pitch = math.degrees(math.atan2(-rmat[2, 1], rmat[2, 2]))
            yaw = math.degrees(math.atan2(-rmat[2, 0], sy))
            roll = math.degrees(math.atan2(rmat[1, 0], rmat[0, 0]))
        else:
            pitch = math.degrees(math.atan2(rmat[1, 2], rmat[1, 1]))
            yaw = math.degrees(math.atan2(-rmat[2, 0], sy))
            roll = 0.0
        # Normalise pitch to a signed value around 0 (the model is upside down
        # in OpenCV's convention).
        pitch = ((pitch + 180.0) % 360.0) - 180.0
        if pitch > 90:
            pitch -= 180
        elif pitch < -90:
            pitch += 180
        return float(yaw), float(pitch), float(roll)

    @property
    def yaw_symmetry(self) -> float:
        """
        Cheap, very stable yaw proxy: how far the nose sits from the middle of
        the two face edges, as a fraction of half the face width.
        0 = square on, +1 = fully turned. Sign matches `pose()` yaw.
        """
        left = self.p(L_FACE_EDGE)[0]
        right = self.p(R_FACE_EDGE)[0]
        nose = self.p(NOSE_TIP)[0]
        half = (right - left) / 2.0
        if half <= 1e-6:
            return 0.0
        return float((nose - (left + half)) / half)

    # ------------------------------------------------------- eyes & mouth
    def _ear(self, up: int, dn: int, out: int, inn: int) -> float:
        width = _dist(self.p(out), self.p(inn))
        if width <= 1e-6:
            return 0.0
        return _dist(self.p(up), self.p(dn)) / width

    @property
    def left_ear(self) -> float:
        return self._ear(L_LID_UP, L_LID_DN, L_EYE_OUT, L_EYE_IN)

    @property
    def right_ear(self) -> float:
        return self._ear(R_LID_UP, R_LID_DN, R_EYE_OUT, R_EYE_IN)

    @property
    def eye_aperture(self) -> float:
        return min(self.left_ear, self.right_ear)

    @property
    def mouth_aperture(self) -> float:
        """Inner-lip gap / mouth width. ~0 when closed."""
        width = _dist(self.p(L_MOUTH), self.p(R_MOUTH))
        if width <= 1e-6:
            return 0.0
        return _dist(self.p(LIP_UP_IN), self.p(LIP_DN_IN)) / width

    @property
    def smile_ratio(self) -> float:
        """Mouth width / interocular distance. ~1.0 neutral, >1.25 broad smile."""
        if self.interocular <= 1e-6:
            return 0.0
        return _dist(self.p(L_MOUTH), self.p(R_MOUTH)) / self.interocular

    @property
    def mouth_corner_lift(self) -> float:
        """How far the corners sit above the lip centre, normalised. >0.12 = smiling."""
        corners_y = (self.p(L_MOUTH)[1] + self.p(R_MOUTH)[1]) / 2.0
        centre_y = (self.p(LIP_UP_IN)[1] + self.p(LIP_DN_IN)[1]) / 2.0
        width = _dist(self.p(L_MOUTH), self.p(R_MOUTH))
        if width <= 1e-6:
            return 0.0
        return float((centre_y - corners_y) / width)

    # ------------------------------------------------------------- regions
    def face_polygon(self) -> np.ndarray:
        return self.points[FACE_OVAL].astype(np.int32)

    def face_mask(self, shape: Optional[Tuple[int, int]] = None) -> np.ndarray:
        h, w = shape if shape else (self.image_size[1], self.image_size[0])
        mask = np.zeros((h, w), np.uint8)
        cv2.fillConvexPoly(mask, cv2.convexHull(self.face_polygon()), 255)
        return mask

    def face_bbox(self, pad: float = 0.0) -> Tuple[int, int, int, int]:
        pts = self.points[FACE_OVAL]
        x1, y1 = pts.min(axis=0)
        x2, y2 = pts.max(axis=0)
        px, py = (x2 - x1) * pad, (y2 - y1) * pad
        w, h = self.image_size
        return (
            int(max(0, x1 - px)),
            int(max(0, y1 - py)),
            int(min(w, x2 + px)),
            int(min(h, y2 + py)),
        )

    def eye_regions(self, scale: float = 1.0) -> List[Tuple[int, int, int, int]]:
        """Bounding boxes around each eye, expanded by `scale`."""
        boxes = []
        for out, inn, up, dn in (
            (L_EYE_OUT, L_EYE_IN, L_LID_UP, L_LID_DN),
            (R_EYE_OUT, R_EYE_IN, R_LID_UP, R_LID_DN),
        ):
            pts = self.points[[out, inn, up, dn]]
            x1, y1 = pts.min(axis=0)
            x2, y2 = pts.max(axis=0)
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            hw = max((x2 - x1) / 2 * scale, 4)
            hh = max((y2 - y1) / 2 * scale, 4)
            w, h = self.image_size
            boxes.append(
                (
                    int(max(0, cx - hw)),
                    int(max(0, cy - hh)),
                    int(min(w, cx + hw)),
                    int(min(h, cy + hh)),
                )
            )
        return boxes

    def iris_circles(self) -> List[Tuple[float, float, float]]:
        """(cx, cy, r) for each iris, when refine_landmarks gave us the points."""
        out = []
        for idx in (L_IRIS, R_IRIS):
            if len(self.points) <= idx[-1]:
                continue
            pts = self.points[list(idx)]
            c = pts[0]
            r = float(np.mean([_dist(c, p) for p in pts[1:]]))
            out.append((float(c[0]), float(c[1]), max(r, 2.0)))
        return out

    def skin_sample_mask(self) -> np.ndarray:
        """Cheeks + forehead: the most reliable skin pixels for tone analysis."""
        h, w = self.image_size[1], self.image_size[0]
        mask = np.zeros((h, w), np.uint8)
        r = max(int(self.interocular * 0.35), 3)
        for idx in (L_CHEEK, R_CHEEK):
            cv2.circle(mask, tuple(self.p(idx).astype(int)), r, 255, -1)
        brow = (self.p(L_BROW) + self.p(R_BROW)) / 2.0
        forehead_pt = brow + (self.forehead - brow) * 0.55
        cv2.circle(mask, tuple(forehead_pt.astype(int)), r, 255, -1)
        return mask

    # -------------------------------------------------------- transforms
    def transformed(self, matrix: np.ndarray, image_size: Tuple[int, int]) -> "FaceGeometry":
        """Apply a 2x3 affine matrix to every landmark."""
        pts = np.hstack([self.points, np.ones((len(self.points), 1), np.float32)])
        new = (matrix @ pts.T).T.astype(np.float32)
        return FaceGeometry(
            points=new,
            image_size=image_size,
            face_count=self.face_count,
            other_faces=self.other_faces,
        )

    def translated(self, dx: float, dy: float, image_size: Tuple[int, int]) -> "FaceGeometry":
        pts = self.points.copy()
        pts[:, 0] += dx
        pts[:, 1] += dy
        return FaceGeometry(pts, image_size, self.face_count, self.other_faces)

    def scaled(self, sx: float, sy: float, image_size: Tuple[int, int]) -> "FaceGeometry":
        pts = self.points.copy()
        pts[:, 0] *= sx
        pts[:, 1] *= sy
        return FaceGeometry(pts, image_size, self.face_count, self.other_faces)

    def summary(self) -> Dict:
        yaw, pitch, roll = self.pose()
        return {
            "face_count": self.face_count,
            "head_height_px": round(self.head_height, 1),
            "face_width_px": round(self.face_width, 1),
            "interocular_px": round(self.interocular, 1),
            "eye_line_y": round(self.eye_line_y, 1),
            "crown_y": round(self.crown_y, 1),
            "chin_y": round(float(self.chin[1]), 1),
            "roll_deg": round(self.roll_deg, 2),
            "yaw_deg": round(yaw, 2),
            "pitch_deg": round(pitch, 2),
            "yaw_symmetry": round(self.yaw_symmetry, 3),
            "eye_aperture": round(self.eye_aperture, 3),
            "mouth_aperture": round(self.mouth_aperture, 3),
            "smile_ratio": round(self.smile_ratio, 3),
        }


def detect(image_bgr: np.ndarray, max_faces: int = 4) -> FaceGeometry:
    """
    Run FaceMesh and return geometry for the largest face.

    Raises NoFaceError when nothing usable is found.
    """
    h, w = image_bgr.shape[:2]

    # FaceMesh is happiest around 1-2 Mpx; downscale for detection, then map back.
    scale = 1.0
    work = image_bgr
    longest = max(h, w)
    if longest > 1600:
        scale = 1600.0 / longest
        work = cv2.resize(image_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    rgb = cv2.cvtColor(work, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    mesh = _get_mesh(max_faces)
    with _mesh_lock:  # MediaPipe graphs are not re-entrant
        res = mesh.process(rgb)

    if not res.multi_face_landmarks:
        raise NoFaceError(
            "No face detected. Use a clear, front-facing close-up of one person."
        )

    faces = []
    for lms in res.multi_face_landmarks:
        pts = np.array(
            [(lm.x * w, lm.y * h) for lm in lms.landmark], dtype=np.float32
        )
        span = float(
            np.linalg.norm(pts[L_FACE_EDGE] - pts[R_FACE_EDGE])
        )
        faces.append((span, pts))

    faces.sort(key=lambda f: f[0], reverse=True)
    main_span, main_pts = faces[0]

    others = []
    for span, pts in faces[1:]:
        # Ignore tiny background faces (posters, reflections) below 25% the size
        # of the subject - but still record them for the report.
        x1, y1 = pts.min(axis=0)
        x2, y2 = pts.max(axis=0)
        others.append(
            {
                "relative_size": round(span / main_span, 3) if main_span else 0.0,
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
            }
        )

    significant = 1 + sum(1 for o in others if o["relative_size"] > 0.25)

    return FaceGeometry(
        points=main_pts,
        image_size=(w, h),
        face_count=significant,
        other_faces=others,
    )
