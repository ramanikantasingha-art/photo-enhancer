"""Local MODNet portrait-matting provider using ONNX Runtime.

The model is used only to predict foreground alpha. It never generates or
reconstructs facial pixels. A protected face interior is forced fully opaque
before compositing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import onnxruntime as ort


class ModNetMatting:
    def __init__(self, model_path: str | Path, ref_size: int = 512):
        self.model_path = Path(model_path)
        self.ref_size = int(ref_size)
        self._session: Optional[ort.InferenceSession] = None
        self._input_name: Optional[str] = None
        self._output_name: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.model_path.is_file() and self.model_path.stat().st_size > 1_000_000

    def _load(self) -> None:
        if self._session is not None:
            return
        if not self.available:
            raise FileNotFoundError(f"MODNet model not found: {self.model_path}")
        providers = ["CPUExecutionProvider"]
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self._session = ort.InferenceSession(str(self.model_path), providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name

    @staticmethod
    def _multiple_of_32(value: float) -> int:
        return max(32, int(round(value / 32.0)) * 32)

    def _network_size(self, width: int, height: int) -> Tuple[int, int]:
        if width <= 0 or height <= 0:
            raise ValueError("invalid image size")
        scale = self.ref_size / min(width, height)
        nw = self._multiple_of_32(width * scale)
        nh = self._multiple_of_32(height * scale)
        # Prevent pathological memory use on very tall/wide inputs.
        max_side = max(nw, nh)
        if max_side > 1536:
            scale2 = 1536.0 / max_side
            nw = self._multiple_of_32(nw * scale2)
            nh = self._multiple_of_32(nh * scale2)
        return nw, nh

    def matte(self, image_bgr: np.ndarray) -> np.ndarray:
        """Return a uint8 alpha matte (0..255) at the original image size."""
        self._load()
        if image_bgr is None or image_bgr.size == 0:
            raise ValueError("empty image")
        h, w = image_bgr.shape[:2]
        nw, nh = self._network_size(w, h)

        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA if nw < w else cv2.INTER_CUBIC)
        x = resized.astype(np.float32) / 255.0
        x = (x - 0.5) / 0.5
        x = np.transpose(x, (2, 0, 1))[None, ...].astype(np.float32)

        assert self._session is not None
        assert self._input_name is not None
        assert self._output_name is not None
        pred = self._session.run([self._output_name], {self._input_name: x})[0]
        matte = np.squeeze(pred).astype(np.float32)
        matte = np.clip(matte, 0.0, 1.0)
        matte = cv2.resize(matte, (w, h), interpolation=cv2.INTER_CUBIC)
        matte = np.clip(matte, 0.0, 1.0)

        # Preserve the model's soft hair boundary while making obvious regions stable.
        matte[matte <= 0.015] = 0.0
        matte[matte >= 0.985] = 1.0
        return np.clip(matte * 255.0 + 0.5, 0, 255).astype(np.uint8)


def force_face_opaque(alpha: np.ndarray, face_box: Tuple[int, int, int, int]) -> np.ndarray:
    """Protect the central face from any accidental transparency."""
    out = alpha.copy()
    h, w = out.shape[:2]
    x, y, fw, fh = face_box
    cx = int(round(x + fw * 0.50))
    cy = int(round(y + fh * 0.52))
    ax = max(1, int(round(fw * 0.36)))
    ay = max(1, int(round(fh * 0.43)))
    face = np.zeros((h, w), np.uint8)
    cv2.ellipse(face, (cx, cy), (ax, ay), 0, 0, 360, 255, -1, cv2.LINE_AA)
    out[face > 127] = 255
    return out


def composite_bgr(image_bgr: np.ndarray, alpha: np.ndarray, bg_rgb: Tuple[int, int, int]) -> np.ndarray:
    """Composite the source pixels over a solid RGB background."""
    if alpha.shape[:2] != image_bgr.shape[:2]:
        raise ValueError("alpha shape mismatch")
    a = np.clip(alpha.astype(np.float32) / 255.0, 0.0, 1.0)[:, :, None]
    # Input image is BGR; convert requested RGB background to BGR.
    bg_bgr = np.array([bg_rgb[2], bg_rgb[1], bg_rgb[0]], dtype=np.float32).reshape(1, 1, 3)
    out = image_bgr.astype(np.float32) * a + bg_bgr * (1.0 - a)
    return np.clip(out, 0, 255).astype(np.uint8)
