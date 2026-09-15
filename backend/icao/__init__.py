"""
ICAO-compliant photo engine.

    from icao import get_spec, Options, enhance, analyse

The package is deliberately framework-free: no FastAPI, no file system, no
globals beyond the lazily-loaded models. Everything takes bytes or arrays in
and gives arrays and plain dicts back, so it is equally usable from the API,
a CLI, a worker queue or a test.
"""

from .spec import SPECS, DEFAULT_SPEC_ID, PhotoSpec, get_spec  # noqa: F401
from .landmarks import NoFaceError  # noqa: F401
from .pipeline import Options, Result, analyse, decode, encode, enhance, run  # noqa: F401
from .sheet import PAPERS, build_sheet, list_papers  # noqa: F401
from .geometry import guide_overlay  # noqa: F401

__all__ = [
    "SPECS",
    "DEFAULT_SPEC_ID",
    "PhotoSpec",
    "get_spec",
    "NoFaceError",
    "Options",
    "Result",
    "analyse",
    "enhance",
    "run",
    "decode",
    "encode",
    "build_sheet",
    "list_papers",
    "PAPERS",
    "guide_overlay",
]

__version__ = "2.0.0"
