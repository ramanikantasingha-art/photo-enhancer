"""Hybrid engine API wrapper.

Uses the existing application pipeline but replaces the background-removal stage
with local MODNet portrait matting. The old U2Net/rembg implementation remains a
fallback if the MODNet model is unavailable or fails.
"""
from pathlib import Path

import cv2
import numpy as np

try:
    from . import app as legacy_app
    from .modnet_background import ModNetMatting, composite_bgr, force_face_opaque
except ImportError:  # when launched from the backend directory by uvicorn
    import app as legacy_app
    from modnet_background import ModNetMatting, composite_bgr, force_face_opaque


_MODEL_PATH = Path(__file__).resolve().parent / "models" / "modnet_photographic_portrait_matting.onnx"
_MODNET = ModNetMatting(_MODEL_PATH, ref_size=512)
_ORIGINAL_REPLACE_BACKGROUND = legacy_app._replace_background


def _replace_background_modnet(image: np.ndarray, bg_color: tuple[int, int, int]) -> np.ndarray:
    """Primary local matting path with identity-safe face protection."""
    try:
        alpha = _MODNET.matte(image)

        # Do not permit any matting model to punch holes through the face interior.
        try:
            face = legacy_app._largest_face(image)
            alpha = force_face_opaque(alpha, face)
        except Exception:
            # If face re-detection fails, keep the matte but do not alter source pixels.
            pass

        # Sanity checks. A wildly implausible foreground mask is rejected.
        coverage = float(np.mean(alpha > 32))
        opaque = float(np.mean(alpha > 245))
        if coverage < 0.10 or coverage > 0.90 or opaque < 0.05:
            raise ValueError("MODNet matte failed plausibility checks")

        return composite_bgr(image, alpha, bg_color)
    except Exception:
        # Safe fallback: retain the previously proven local provider.
        return _ORIGINAL_REPLACE_BACKGROUND(image, bg_color)


# Patch only the segmentation/matting stage. Everything else in the existing
# processing flow remains unchanged.
legacy_app._replace_background = _replace_background_modnet
legacy_app.app.version = "3.0.0-hybrid-modnet"

app = legacy_app.app
process_passport_image = legacy_app.process_passport_image
