"""Guarded hybrid portrait engine core.

Design goals:
- immutable-source processing
- deterministic operations are authoritative
- protected face interior cannot be replaced by generative providers
- optional generative providers are quarantined to explicitly allowed masks
- every stage emits evidence for validation/rollback

This module intentionally has no hard dependency on a particular generative model.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from hashlib import sha256
from typing import Any, Dict, List, Optional, Protocol, Tuple

import cv2
import numpy as np


class Decision(str, Enum):
    READY = "READY"
    READY_WITH_INFO = "READY_WITH_INFO"
    REVIEW = "REVIEW"
    RECAPTURE = "RECAPTURE"
    BLOCKED_IDENTITY = "BLOCKED_IDENTITY"
    BLOCKED_CUTOUT = "BLOCKED_CUTOUT"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"


@dataclass(frozen=True)
class EnginePolicy:
    # Face interior is never generatively rewritten in ID modes.
    allow_generative_face: bool = False
    allow_generative_hair_edge: bool = True
    allow_generative_background: bool = True
    allow_generative_clothing_edge: bool = True
    max_global_tone_gain: float = 1.12
    min_global_tone_gain: float = 0.90
    max_face_mean_abs_diff: float = 2.0
    max_face_p99_abs_diff: float = 10.0
    max_face_structural_change: float = 0.02
    min_hard_background_white_fraction: float = 0.995
    max_halo_fraction: float = 0.005
    deterministic_repeats: int = 3


@dataclass
class StageEvidence:
    stage: str
    passed: bool
    metrics: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


@dataclass
class RunManifest:
    source_sha256: str
    engine_version: str
    model_versions: Dict[str, str] = field(default_factory=dict)
    operations: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[StageEvidence] = field(default_factory=list)
    decision: Decision = Decision.REVIEW

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["decision"] = self.decision.value
        return d


class GenerativeProvider(Protocol):
    """Provider interface for an optional image-edit model.

    Provider MUST obey the supplied binary/soft mask. The engine will still verify
    postconditions and rollback if a protected region changes.
    """

    name: str
    version: str

    def edit(self, image_bgr: np.ndarray, mask: np.ndarray, instruction: str) -> np.ndarray:
        ...


def _hash_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _ensure_u8_bgr(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        raise ValueError("empty image")
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if image.shape[2] != 3:
        raise ValueError("unsupported channel count")
    return image.astype(np.uint8, copy=False)


def ellipse_face_mask(shape: Tuple[int, int], face_box: Tuple[int, int, int, int], shrink: float = 0.13) -> np.ndarray:
    """Conservative protected face interior mask derived from a face box."""
    h, w = shape
    x, y, fw, fh = face_box
    cx, cy = int(x + fw * 0.50), int(y + fh * 0.52)
    ax = max(1, int(fw * (0.50 - shrink)))
    ay = max(1, int(fh * (0.58 - shrink)))
    mask = np.zeros((h, w), np.uint8)
    cv2.ellipse(mask, (cx, cy), (ax, ay), 0, 0, 360, 255, -1, cv2.LINE_AA)
    return mask


def protected_face_metrics(before: np.ndarray, after: np.ndarray, face_mask: np.ndarray) -> Dict[str, float]:
    """Measure pixel drift inside the protected face interior."""
    if before.shape != after.shape:
        raise ValueError("before/after shape mismatch")
    idx = face_mask > 127
    if int(idx.sum()) < 100:
        raise ValueError("protected face mask too small")
    delta = np.abs(after.astype(np.int16) - before.astype(np.int16))[idx]
    mean = float(np.mean(delta))
    p99 = float(np.quantile(delta, 0.99))
    maxd = float(np.max(delta))
    return {"mean_abs_diff": mean, "p99_abs_diff": p99, "max_abs_diff": maxd}


def enforce_protected_face(original: np.ndarray, candidate: np.ndarray, face_mask: np.ndarray) -> np.ndarray:
    """Hard-copy the protected face interior from the authoritative source/crop."""
    out = candidate.copy()
    idx = face_mask > 127
    out[idx] = original[idx]
    return out


def bounded_white_balance(image: np.ndarray, policy: EnginePolicy) -> np.ndarray:
    work = image.astype(np.float32)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    valid = (gray > 18) & (gray < 242)
    if int(valid.sum()) < 100:
        return image.copy()
    means = np.array([work[:, :, c][valid].mean() for c in range(3)], dtype=np.float32)
    gains = float(np.mean(means)) / np.maximum(means, 1.0)
    gains = np.clip(gains, policy.min_global_tone_gain, policy.max_global_tone_gain)
    return np.clip(work * gains.reshape(1, 1, 3), 0, 255).astype(np.uint8)


def conservative_detail(image: np.ndarray, amount: float = 0.28) -> np.ndarray:
    """Edge-selective non-generative detail recovery."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(image, (0, 0), 1.15)
    sharp = cv2.addWeighted(image, 1.0 + amount, blur, -amount, 0)
    edges = cv2.Canny(gray, 45, 130)
    m = cv2.GaussianBlur(edges, (0, 0), 1.0).astype(np.float32) / 255.0
    m = np.clip(m * 1.15, 0, 1)[:, :, None]
    return np.clip(image.astype(np.float32) * (1 - m) + sharp.astype(np.float32) * m, 0, 255).astype(np.uint8)


def composite_on_white(image: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    if alpha.shape[:2] != image.shape[:2]:
        raise ValueError("alpha shape mismatch")
    a = np.clip(alpha.astype(np.float32) / 255.0, 0.0, 1.0)[:, :, None]
    white = np.full_like(image, 255)
    return np.clip(image.astype(np.float32) * a + white.astype(np.float32) * (1 - a), 0, 255).astype(np.uint8)


def hard_background_white_fraction(output: np.ndarray, alpha: np.ndarray) -> float:
    hard_bg = alpha < 8
    if int(hard_bg.sum()) == 0:
        return 1.0
    px = output[hard_bg]
    white = np.all(px >= 250, axis=1)
    return float(np.mean(white))


def estimate_halo_fraction(output: np.ndarray, alpha: np.ndarray) -> float:
    """Simple halo detector around uncertain alpha boundary.

    It is intentionally conservative. Production should additionally use a learned
    boundary-quality detector and reference masks in the validation lab.
    """
    boundary = (alpha >= 8) & (alpha <= 247)
    if int(boundary.sum()) == 0:
        return 0.0
    # suspicious nearly-white/gray fringe on foreground boundary
    px = output[boundary].astype(np.int16)
    spread = px.max(axis=1) - px.min(axis=1)
    brightness = px.mean(axis=1)
    suspicious = (brightness > 220) & (spread < 20)
    return float(np.mean(suspicious))


class HybridPortraitEngine:
    VERSION = "3.0.0-alpha"

    def __init__(self, policy: Optional[EnginePolicy] = None, generative: Optional[GenerativeProvider] = None):
        self.policy = policy or EnginePolicy()
        self.generative = generative

    def _e(self, manifest: RunManifest, stage: str, passed: bool, metrics: Optional[Dict[str, float]] = None, *notes: str) -> None:
        manifest.evidence.append(StageEvidence(stage=stage, passed=passed, metrics=metrics or {}, notes=list(notes)))

    def process_precomposed_portrait(
        self,
        source_bytes: bytes,
        portrait_bgr: np.ndarray,
        alpha: np.ndarray,
        face_box: Tuple[int, int, int, int],
        use_generative_edge_repair: bool = False,
    ) -> Tuple[np.ndarray, RunManifest]:
        """Process an already composed head-and-shoulders portrait.

        Portrait geometry/face detection are separate providers by design. This method
        demonstrates the authoritative safety core used after the crop is chosen.
        """
        source = _ensure_u8_bgr(portrait_bgr)
        manifest = RunManifest(source_sha256=_hash_bytes(source_bytes), engine_version=self.VERSION)
        if self.generative is not None:
            manifest.model_versions["generative"] = f"{self.generative.name}:{self.generative.version}"

        if alpha.dtype != np.uint8:
            alpha = np.clip(alpha, 0, 255).astype(np.uint8)
        if alpha.shape != source.shape[:2]:
            raise ValueError("alpha must match portrait size")

        face_mask = ellipse_face_mask(source.shape[:2], face_box)
        # Protected face must be fully foreground.
        alpha = alpha.copy()
        alpha[face_mask > 127] = 255

        work = bounded_white_balance(source, self.policy)
        work = conservative_detail(work)
        # Face remains source-authoritative after global bounded operations.
        work = enforce_protected_face(source, work, face_mask)

        if use_generative_edge_repair:
            if self.generative is None:
                self._e(manifest, "generative_edge_repair", False, {}, "provider unavailable")
            else:
                # Only uncertain boundary pixels may be touched; face interior is excluded.
                edge_mask = (((alpha > 4) & (alpha < 251)).astype(np.uint8) * 255)
                edge_mask[face_mask > 127] = 0
                if int((edge_mask > 0).sum()) > 0:
                    candidate = _ensure_u8_bgr(self.generative.edit(work.copy(), edge_mask, "repair only portrait cutout boundary artifacts; do not alter identity, expression, skin tone, clothing design, or protected face"))
                    candidate = enforce_protected_face(source, candidate, face_mask)
                    fm = protected_face_metrics(source, candidate, face_mask)
                    ok = fm["mean_abs_diff"] <= self.policy.max_face_mean_abs_diff and fm["p99_abs_diff"] <= self.policy.max_face_p99_abs_diff
                    self._e(manifest, "generative_edge_repair", ok, fm, "rolled back" if not ok else "accepted")
                    if ok:
                        work = candidate

        output = composite_on_white(work, alpha)
        fm = protected_face_metrics(source, output, face_mask)
        face_ok = fm["mean_abs_diff"] <= self.policy.max_face_mean_abs_diff and fm["p99_abs_diff"] <= self.policy.max_face_p99_abs_diff
        self._e(manifest, "protected_face", face_ok, fm)
        if not face_ok:
            manifest.decision = Decision.BLOCKED_IDENTITY
            return output, manifest

        white_fraction = hard_background_white_fraction(output, alpha)
        halo_fraction = estimate_halo_fraction(output, alpha)
        cutout_ok = white_fraction >= self.policy.min_hard_background_white_fraction and halo_fraction <= self.policy.max_halo_fraction
        self._e(manifest, "cutout", cutout_ok, {"hard_background_white_fraction": white_fraction, "halo_fraction": halo_fraction})
        if not cutout_ok:
            manifest.decision = Decision.REVIEW
            return output, manifest

        manifest.decision = Decision.READY
        return output, manifest
