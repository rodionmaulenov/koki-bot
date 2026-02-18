import io
import logging

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


def preprocess_image(image_bytes: bytes) -> bytes:
    """Preprocess image for OCR: EXIF rotate, deskew, enhance contrast.

    Returns JPEG bytes. On any error returns original bytes unchanged.
    """
    try:
        image = _fix_exif_rotation(image_bytes)
        cv_image = np.array(image)
        cv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)

        cv_image = _deskew(cv_image)
        cv_image = _enhance_contrast(cv_image)

        _, buffer = cv2.imencode(".jpg", cv_image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return buffer.tobytes()
    except Exception:
        logger.exception("Image preprocessing failed, using original")
        return image_bytes


def _fix_exif_rotation(image_bytes: bytes) -> Image.Image:
    """Fix EXIF orientation using Pillow (most reliable method)."""
    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def _deskew(image: np.ndarray) -> np.ndarray:
    """Correct skew using minAreaRect on detected edges."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    coords = np.column_stack(np.where(edges > 0))
    if len(coords) < 100:
        return image

    rect = cv2.minAreaRect(coords)
    angle = rect[2]

    if angle < -45:
        angle += 90
    elif angle > 45:
        angle -= 90

    if abs(angle) < 0.5:
        return image

    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _enhance_contrast(image: np.ndarray) -> np.ndarray:
    """Enhance contrast using CLAHE on LAB L-channel."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)

    lab = cv2.merge([l_channel, a_channel, b_channel])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
