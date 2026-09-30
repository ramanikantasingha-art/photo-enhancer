"""Phase 2: Golden-reference benchmark + production matting scaffold.

Production rule: the reference image is never a pixel donor. It may be used only in
benchmark mode to derive an alignment prior/trimap for diagnostics. All accepted
output pixels come from the source portrait plus a synthetic solid background.

The production provider API is intentionally model-agnostic so BiRefNet/SAM-style
providers can be swapped without changing the validation logic.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Protocol, Tuple, Dict, Any
import json
import cv2
import numpy as np


class MatteProvider(Protocol):
    name: str
    version: str
    def predict_alpha(self, portrait_bgr: np.ndarray) -> np.ndarray: ...


@dataclass
class Phase2Report:
    output_px: Tuple[int, int]
    crop_xywh: Tuple[int, int, int, int]
    face_xywh_source: Tuple[int, int, int, int]
    protected_face_source_authoritative: bool
    reference_assisted_trimap: bool
    reference_pixels_copied: bool
    hard_background_white_fraction: float
    provider: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def detect_largest_face(image: np.ndarray) -> Tuple[int, int, int, int]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
    if len(faces) == 0:
        raise ValueError('no reliable frontal face detected')
    return tuple(map(int, max(faces, key=lambda r: r[2] * r[3])))


def portrait_crop_from_face(image: np.ndarray, face: Tuple[int,int,int,int]) -> Tuple[np.ndarray, Tuple[int,int,int,int], Tuple[int,int,int,int]]:
    x,y,w,h = face
    cx, cy = x+w/2, y+h/2
    crop_w = int(round(w / 0.43))
    crop_h = int(round(crop_w * 45 / 35))
    crop_w = min(crop_w, image.shape[1]); crop_h = min(crop_h, image.shape[0])
    left = int(round(cx - crop_w/2)); top = int(round(cy - 0.33*crop_h))
    left = max(0, min(left, image.shape[1]-crop_w)); top = max(0, min(top, image.shape[0]-crop_h))
    crop = image[top:top+crop_h, left:left+crop_w].copy()
    face_local = (x-left, y-top, w, h)
    return crop, (left, top, crop_w, crop_h), face_local


def protected_face_mask(shape: Tuple[int,int], face: Tuple[int,int,int,int]) -> np.ndarray:
    h,w = shape; x,y,fw,fh = face
    m = np.zeros((h,w), np.uint8)
    cv2.ellipse(m, (int(x+fw*.5), int(y+fh*.52)), (int(fw*.33), int(fh*.41)), 0, 0, 360, 255, -1)
    return m


def reference_silhouette(reference_bgr: np.ndarray) -> np.ndarray:
    mean = reference_bgr.mean(axis=2)
    spread = reference_bgr.max(axis=2) - reference_bgr.min(axis=2)
    raw = (((mean < 246) | (spread > 10)).astype(np.uint8) * 255)
    raw = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, np.ones((5,5),np.uint8), iterations=2)
    n, labels, stats, _ = cv2.connectedComponentsWithStats((raw>0).astype(np.uint8), 8)
    if n <= 1: raise ValueError('reference silhouette unavailable')
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return ((labels == idx).astype(np.uint8) * 255)


def benchmark_reference_trimap(reference_bgr: np.ndarray, reference_face: Tuple[int,int,int,int],
                                source_face_local: Tuple[int,int,int,int], out_shape: Tuple[int,int]) -> np.ndarray:
    """Benchmark-only shape prior. Never contributes RGB pixels to the output."""
    rm = reference_silhouette(reference_bgr)
    rx,ry,rw,rh = reference_face; sx,sy,sw,sh = source_face_local
    scale = sw / float(rw)
    rcx, rcy = rx+rw/2, ry+rh/2
    scx, scy = sx+sw/2, sy+sh/2
    M = np.array([[scale,0,scx-scale*rcx],[0,scale,scy-scale*rcy]], np.float32)
    return cv2.warpAffine(rm, M, (out_shape[1], out_shape[0]), flags=cv2.INTER_LINEAR, borderValue=0)


def grabcut_from_prior(portrait: np.ndarray, prior: np.ndarray, face_local: Tuple[int,int,int,int]) -> np.ndarray:
    H,W = portrait.shape[:2]
    er = cv2.erode((prior>128).astype(np.uint8)*255, np.ones((13,13),np.uint8), 1)
    di = cv2.dilate((prior>16).astype(np.uint8)*255, np.ones((17,17),np.uint8), 1)
    mask = np.full((H,W), cv2.GC_PR_FGD, np.uint8)
    mask[di==0] = cv2.GC_BGD
    mask[(di>0)&(er==0)] = cv2.GC_PR_FGD
    mask[er>0] = cv2.GC_FGD
    pf = protected_face_mask((H,W), face_local)
    mask[pf>0] = cv2.GC_FGD
    mask[:5,:] = mask[-2:,:] = mask[:,:5] = mask[:,-5:] = cv2.GC_BGD
    bg = np.zeros((1,65),np.float64); fg = np.zeros((1,65),np.float64)
    cv2.grabCut(portrait, mask, None, bg, fg, 12, cv2.GC_INIT_WITH_MASK)
    alpha = np.where((mask==cv2.GC_FGD)|(mask==cv2.GC_PR_FGD),255,0).astype(np.uint8)
    alpha[pf>0] = 255
    n, labels, stats, _ = cv2.connectedComponentsWithStats((alpha>0).astype(np.uint8),8)
    sx,sy,sw,sh = face_local
    lid = labels[int(sy+sh*.52), int(sx+sw*.5)]
    alpha = ((labels==lid).astype(np.uint8)*255)
    contours,_ = cv2.findContours(alpha, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        clean = np.zeros_like(alpha); cv2.drawContours(clean,[max(contours,key=cv2.contourArea)],-1,255,-1); alpha=clean
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)),1)
    return cv2.GaussianBlur(alpha,(0,0),0.55)


def composite_white(source: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    a = alpha.astype(np.float32)/255.0
    return np.clip(source.astype(np.float32)*a[...,None] + 255*(1-a[...,None]),0,255).astype(np.uint8)


def run_phase2(source_bgr: np.ndarray, reference_bgr: Optional[np.ndarray]=None,
               provider: Optional[MatteProvider]=None) -> Tuple[np.ndarray, np.ndarray, Phase2Report]:
    face = detect_largest_face(source_bgr)
    portrait, crop_box, face_local = portrait_crop_from_face(source_bgr, face)
    benchmark_mode = reference_bgr is not None
    if provider is not None:
        alpha = provider.predict_alpha(portrait)
        provider_name = f'{provider.name}:{provider.version}'
    elif reference_bgr is not None:
        rface = detect_largest_face(reference_bgr)
        prior = benchmark_reference_trimap(reference_bgr, rface, face_local, portrait.shape[:2])
        alpha = grabcut_from_prior(portrait, prior, face_local)
        provider_name = 'benchmark-guided-grabcut'
    else:
        raise ValueError('production run requires a MatteProvider; benchmark run may use reference trimap')
    # Protected face is source-authoritative by construction; no reference RGB is ever used.
    pf = protected_face_mask(portrait.shape[:2], face_local)
    alpha[pf>0] = 255
    output = composite_white(portrait, alpha)
    output = cv2.resize(output, (700,900), interpolation=cv2.INTER_LANCZOS4)
    hard_white = float(np.mean(np.all(output >= 250, axis=2)))
    report = Phase2Report((700,900), crop_box, face, True, benchmark_mode, False, hard_white, provider_name)
    return output, alpha, report
