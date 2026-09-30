import numpy as np

from hybrid_engine import (
    Decision,
    EnginePolicy,
    HybridPortraitEngine,
    ellipse_face_mask,
    protected_face_metrics,
)


class HostileGenerativeProvider:
    """Deliberately tries to alter everything; engine must protect the face."""
    name = "hostile-test-provider"
    version = "1"

    def edit(self, image_bgr, mask, instruction):
        out = image_bgr.copy()
        out[mask > 0] = 255 - out[mask > 0]
        # Also maliciously attempt to modify the whole image, including face.
        out = np.clip(out.astype(np.int16) + 17, 0, 255).astype(np.uint8)
        return out


def synthetic_portrait():
    h, w = 600, 450
    img = np.full((h, w, 3), 180, np.uint8)
    # subject body
    img[110:590, 80:370] = (90, 130, 170)
    # face area with stable texture
    yy, xx = np.ogrid[:h, :w]
    face = ((xx - 225) / 78) ** 2 + ((yy - 225) / 100) ** 2 <= 1
    img[face] = (125, 155, 190)
    img[210:214, 185:205] = 30
    img[210:214, 245:265] = 30
    img[270:274, 205:245] = 60

    alpha = np.zeros((h, w), np.uint8)
    alpha[95:595, 65:385] = 255
    # create soft uncertain border so generative edge path runs
    alpha[95:105, 65:385] = 128
    alpha[585:595, 65:385] = 128
    alpha[95:595, 65:75] = 128
    alpha[95:595, 375:385] = 128
    return img, alpha, (145, 120, 160, 210)


def test_protected_face_copy_is_exact():
    img, _, face_box = synthetic_portrait()
    mask = ellipse_face_mask(img.shape[:2], face_box)
    altered = np.zeros_like(img)
    from hybrid_engine import enforce_protected_face
    fixed = enforce_protected_face(img, altered, mask)
    metrics = protected_face_metrics(img, fixed, mask)
    assert metrics["mean_abs_diff"] == 0.0
    assert metrics["p99_abs_diff"] == 0.0
    assert metrics["max_abs_diff"] == 0.0


def test_hostile_generative_provider_cannot_change_protected_face():
    img, alpha, face_box = synthetic_portrait()
    engine = HybridPortraitEngine(generative=HostileGenerativeProvider())
    output, manifest = engine.process_precomposed_portrait(
        source_bytes=b"synthetic-source",
        portrait_bgr=img,
        alpha=alpha,
        face_box=face_box,
        use_generative_edge_repair=True,
    )
    face_mask = ellipse_face_mask(img.shape[:2], face_box)
    metrics = protected_face_metrics(img, output, face_mask)
    assert metrics["mean_abs_diff"] == 0.0
    assert metrics["p99_abs_diff"] == 0.0
    assert manifest.decision in {Decision.READY, Decision.REVIEW}


def test_hard_background_is_white():
    img, alpha, face_box = synthetic_portrait()
    engine = HybridPortraitEngine(policy=EnginePolicy(max_halo_fraction=1.0))
    output, manifest = engine.process_precomposed_portrait(
        source_bytes=b"synthetic-source",
        portrait_bgr=img,
        alpha=alpha,
        face_box=face_box,
    )
    bg = alpha < 8
    assert np.all(output[bg] == 255)
    assert manifest.decision == Decision.READY


def test_same_input_is_deterministic():
    img, alpha, face_box = synthetic_portrait()
    engine = HybridPortraitEngine(policy=EnginePolicy(max_halo_fraction=1.0))
    a, ma = engine.process_precomposed_portrait(b"same", img, alpha, face_box)
    b, mb = engine.process_precomposed_portrait(b"same", img, alpha, face_box)
    assert np.array_equal(a, b)
    assert ma.to_dict() == mb.to_dict()
