"""Natural, identity-preserving passport photo processing API."""

import io
import os

import cv2
import mediapipe as mp
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image, ImageFilter, ImageOps
from rembg import new_session, remove

app = FastAPI(title="Natural Passport Photo Enhancer API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mp_face = mp.solutions.face_detection
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_OUTPUT_PIXELS = 20_000_000
ALLOWED_PROFILES = {"natural", "restore", "document"}
ALLOWED_FRAMING = {"standard", "loose", "close"}
_BACKGROUND_SESSION = None


def _decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode safely, honour EXIF orientation, and normalise to BGR."""
    if not image_bytes or len(image_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("Image is empty or larger than 25 MB")
    try:
        pil = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    except Exception as exc:
        raise ValueError("Invalid or unsupported image file") from exc
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def _largest_face(image: np.ndarray) -> tuple[int, int, int, int]:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.55) as detector:
        detections = detector.process(rgb).detections or []
    if not detections:
        raise ValueError("No clear face detected. Use a front-facing, well-lit photo.")

    h, w = image.shape[:2]
    boxes = []
    for detection in detections:
        box = detection.location_data.relative_bounding_box
        x = max(0, round(box.xmin * w))
        y = max(0, round(box.ymin * h))
        bw = min(w - x, round(box.width * w))
        bh = min(h - y, round(box.height * h))
        boxes.append((x, y, bw, bh))
    return max(boxes, key=lambda b: b[2] * b[3])


def _crop_without_stretching(
    image: np.ndarray,
    face: tuple[int, int, int, int],
    out_width: int,
    out_height: int,
    framing: str = "standard",
) -> np.ndarray:
    """Crop to the output ratio while positioning the head naturally."""
    h, w = image.shape[:2]
    x, y, fw, fh = face
    ratio = out_width / out_height
    frame_scale = {"close": 2.25, "standard": 2.65, "loose": 3.05}[framing]
    crop_h = max(fh * frame_scale, fw * 1.85 / ratio)
    crop_w = crop_h * ratio
    if crop_w > w:
        crop_w = float(w)
        crop_h = crop_w / ratio
    if crop_h > h:
        crop_h = float(h)
        crop_w = crop_h * ratio

    face_cx = x + fw / 2
    face_cy = y + fh / 2
    left = float(np.clip(face_cx - crop_w / 2, 0, max(0, w - crop_w)))
    # Put the face centre around 43% down the canvas: visible hair margin above,
    # useful shoulder area below, and less risk of cutting the crown.
    top = float(np.clip(face_cy - crop_h * 0.43, 0, max(0, h - crop_h)))
    x1, y1 = int(round(left)), int(round(top))
    x2, y2 = int(round(left + crop_w)), int(round(top + crop_h))
    crop = image[y1:y2, x1:x2]
    interpolation = cv2.INTER_AREA if crop.shape[1] > out_width else cv2.INTER_LANCZOS4
    return cv2.resize(crop, (out_width, out_height), interpolation=interpolation)


def _limited_white_balance(image: np.ndarray) -> np.ndarray:
    """Neutralise colour casts using tightly bounded channel gains."""
    work = image.astype(np.float32)
    luminance = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    valid = (luminance > 18) & (luminance < 242)
    if valid.sum() < 100:
        return image
    means = np.array([work[:, :, c][valid].mean() for c in range(3)])
    gains = np.clip(float(np.mean(means)) / np.maximum(means, 1), 0.90, 1.10)
    return np.clip(work * gains.reshape(1, 1, 3), 0, 255).astype(np.uint8)


def _natural_tone(image: np.ndarray, strength: float) -> np.ndarray:
    """Improve exposure locally while protecting highlights and texture."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    gain = float(np.clip(142.0 / max(float(np.median(l_chan)), 1.0), 0.88, 1.14))
    corrected = np.clip(l_chan.astype(np.float32) * (1 + (gain - 1) * strength), 0, 255)
    clahe = cv2.createCLAHE(clipLimit=1.35, tileGridSize=(8, 8)).apply(corrected.astype(np.uint8))
    mix = 0.18 + 0.12 * strength
    corrected = cv2.addWeighted(corrected.astype(np.uint8), 1 - mix, clahe, mix, 0)
    return cv2.cvtColor(cv2.merge((corrected, a_chan, b_chan)), cv2.COLOR_LAB2BGR)


def _noise_estimate(gray: np.ndarray) -> float:
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    return float(np.median(np.abs(lap - np.median(lap))) / 0.6745)


def _detail_recovery(image: np.ndarray, profile: str, strength: float) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    noise = _noise_estimate(gray)
    base = image
    if noise > 12:
        denoise_h = int(np.clip(3 + (noise - 12) * 0.12, 3, 7))
        denoised = cv2.fastNlMeansDenoisingColored(image, None, denoise_h, denoise_h, 7, 21)
        base = cv2.addWeighted(image, 0.55, denoised, 0.45, 0)

    sigma = 1.15 if profile == "restore" else 1.35
    blur = cv2.GaussianBlur(base, (0, 0), sigma)
    amount = (0.30 if profile == "natural" else 0.46) * strength
    sharpened = cv2.addWeighted(base, 1 + amount, blur, -amount, 0)

    # Apply detail recovery to real edges, not smooth skin or compression noise.
    edges = cv2.Canny(gray, 45, 130)
    edge_mask = cv2.GaussianBlur(edges, (0, 0), 1.2).astype(np.float32) / 255.0
    edge_mask = np.clip(edge_mask * 1.35, 0, 1)[:, :, None]
    result = base.astype(np.float32) * (1 - edge_mask) + sharpened.astype(np.float32) * edge_mask
    return np.clip(result, 0, 255).astype(np.uint8)


def _enhance_face_detail(image: np.ndarray, strength: float) -> np.ndarray:
    """Add controlled local clarity to the detected face without smoothing it."""
    try:
        x, y, fw, fh = _largest_face(image)
    except ValueError:
        return image

    h, w = image.shape[:2]
    pad_x, pad_y = int(fw * 0.14), int(fh * 0.18)
    x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
    x2, y2 = min(w, x + fw + pad_x), min(h, y + fh + pad_y)
    roi = image[y1:y2, x1:x2]
    if roi.size == 0:
        return image

    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    local = cv2.createCLAHE(clipLimit=1.45, tileGridSize=(6, 6)).apply(l_chan)
    l_chan = cv2.addWeighted(l_chan, 0.78, local, 0.22, 0)
    clarified = cv2.cvtColor(cv2.merge((l_chan, a_chan, b_chan)), cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(clarified, (0, 0), 1.0)
    clarified = cv2.addWeighted(clarified, 1 + 0.22 * strength, blur, -0.22 * strength, 0)

    yy, xx = np.ogrid[: roi.shape[0], : roi.shape[1]]
    cx, cy = roi.shape[1] / 2, roi.shape[0] / 2
    ellipse = ((xx - cx) / max(cx, 1)) ** 2 + ((yy - cy) / max(cy, 1)) ** 2
    mask = np.clip((1.0 - ellipse) * 2.8, 0, 1).astype(np.float32)
    mask = cv2.GaussianBlur(mask, (0, 0), max(3, fw * 0.025))[:, :, None]
    mixed = roi.astype(np.float32) * (1 - mask) + clarified.astype(np.float32) * mask
    output = image.copy()
    output[y1:y2, x1:x2] = np.clip(mixed, 0, 255).astype(np.uint8)
    return output


def _replace_background(image: np.ndarray, bg_color: tuple[int, int, int]) -> np.ndarray:
    """Remove background with a portrait-specific model and safe mask."""
    global _BACKGROUND_SESSION
    if _BACKGROUND_SESSION is None:
        _BACKGROUND_SESSION = new_session("u2net_human_seg")

    source = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    removed = remove(
        source,
        session=_BACKGROUND_SESSION,
        alpha_matting=False,
        post_process_mask=True,
    ).convert("RGBA")

    alpha_array = np.asarray(removed.getchannel("A"))
    coverage = float(np.mean(alpha_array > 32))
    if coverage < 0.12:
        # Never return a result where a failed mask erases the person.
        return image

    alpha = removed.getchannel("A").filter(ImageFilter.GaussianBlur(0.8))
    foreground = Image.merge("RGBA", (*removed.split()[:3], alpha))
    background = Image.new("RGBA", removed.size, (*bg_color, 255))
    composed = Image.alpha_composite(background, foreground).convert("RGB")
    return cv2.cvtColor(np.asarray(composed), cv2.COLOR_RGB2BGR)


def process_passport_image(
    image_bytes: bytes,
    remove_bg: bool = True,
    bg_color: tuple[int, int, int] = (255, 255, 255),
    width: int = 1200,
    height: int = 1600,
    profile: str = "natural",
    strength: float = 0.7,
    auto_crop: bool = True,
    framing: str = "standard",
) -> Image.Image:
    if width < 200 or height < 200 or width * height > MAX_OUTPUT_PIXELS:
        raise ValueError("Output must be at least 200×200 and no more than 20 megapixels")
    if profile not in ALLOWED_PROFILES:
        raise ValueError("Profile must be natural, restore, or document")
    if framing not in ALLOWED_FRAMING:
        raise ValueError("Framing must be standard, loose, or close")
    strength = float(np.clip(strength, 0.0, 1.0))

    image = _decode_image(image_bytes)
    face = _largest_face(image)
    if auto_crop:
        image = _crop_without_stretching(image, face, width, height, framing)
    else:
        pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        pil = ImageOps.fit(pil, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
        image = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)

    image = _limited_white_balance(image)
    image = _natural_tone(image, strength)
    image = _detail_recovery(image, profile, strength)
    image = _enhance_face_detail(image, strength)
    if remove_bg:
        image = _replace_background(image, bg_color)
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


@app.get("/")
def read_root():
    return {"message": "Natural Passport Photo Enhancer API", "version": "2.0.0", "health": "ok"}


@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    remove_bg: bool = True,
    bg_color_r: int = 255,
    bg_color_g: int = 255,
    bg_color_b: int = 255,
    width: int = 1200,
    height: int = 1600,
    profile: str = "natural",
    strength: float = 0.7,
    auto_crop: bool = True,
    framing: str = "standard",
):
    try:
        if not (file.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        contents = await file.read()
        bg_color = tuple(int(np.clip(v, 0, 255)) for v in (bg_color_r, bg_color_g, bg_color_b))
        processed = process_passport_image(
            contents, remove_bg, bg_color, width, height, profile, strength, auto_crop, framing
        )
        output = io.BytesIO()
        processed.save(output, format="JPEG", quality=95, subsampling=0, optimize=True)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": 'attachment; filename="passport_photo_enhanced.jpg"',
                "X-Enhancement-Profile": profile,
            },
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if os.getenv("DEBUG") == "1":
            raise
        raise HTTPException(status_code=500, detail="Image processing failed. Try another image.") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
