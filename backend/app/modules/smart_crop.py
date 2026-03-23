"""
EMFOX OMS v2.2 - Smart Crop Module (Improved)
================================================
Primary strategy: Use Gemini bounding boxes to crop products.
Secondary: OpenCV with multiple detection pipelines.
Fallback: Intelligent grid splitting based on expected count.
Last resort: Full-image thumbnail.
"""

import os
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image as PILImage, ImageFilter, ImageEnhance

from app.config import settings

# Try to import OpenCV
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("[CROP] OpenCV not available")

CROP_DIR = Path(settings.upload_dir) / "crops"
CROP_DIR.mkdir(parents=True, exist_ok=True)

THUMB_MAX = (400, 400)


# ============================================================
# OPENCV DETECTION PIPELINE (improved multi-strategy)
# ============================================================
def _detect_contours(img_cv, expected_count: int = 0) -> List[Tuple[int, int, int, int]]:
    """Multi-strategy contour detection for warehouse/showroom photos."""
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    min_area = int(h * w * 0.02)
    max_area = int(h * w * 0.80)
    min_dim = min(h, w) // 10

    best_bboxes: List[Tuple[int, int, int, int]] = []
    best_score = -1

    def _score(bboxes, target):
        if target <= 0:
            return len(bboxes)
        if len(bboxes) == target:
            return 10000 + len(bboxes)
        return len(bboxes) - abs(len(bboxes) - target) * 2

    # Strategy 1: Canny edge detection with various params
    canny_params = [
        (5, 30, 90, 2), (7, 40, 120, 3), (5, 50, 150, 2),
        (9, 20, 80, 4), (7, 60, 180, 2), (11, 30, 100, 3),
    ]
    for blur_k, canny_lo, canny_hi, dilate_it in canny_params:
        blurred = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
        edges = cv2.Canny(blurred, canny_lo, canny_hi)
        kernel = np.ones((5, 5), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=dilate_it)
        closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        bboxes = _filter_bboxes(contours, min_area, max_area, min_dim, w, h)
        bboxes = _nms_bboxes(bboxes, 0.35)
        score = _score(bboxes, expected_count)
        if score > best_score:
            best_score = score
            best_bboxes = bboxes
        if expected_count > 0 and len(bboxes) == expected_count:
            break

    # Strategy 2: Otsu thresholding
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((7, 7), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    otsu_bboxes = _filter_bboxes(contours, min_area, max_area, min_dim, w, h)
    otsu_bboxes = _nms_bboxes(otsu_bboxes, 0.35)
    score = _score(otsu_bboxes, expected_count)
    if score > best_score:
        best_score = score
        best_bboxes = otsu_bboxes

    # Strategy 3: Adaptive thresholding
    adaptive = cv2.adaptiveThreshold(
        cv2.GaussianBlur(gray, (11, 11), 0), 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 5
    )
    kernel = np.ones((9, 9), np.uint8)
    closed = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, kernel, iterations=4)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    adapt_bboxes = _filter_bboxes(contours, min_area, max_area, min_dim, w, h)
    adapt_bboxes = _nms_bboxes(adapt_bboxes, 0.35)
    score = _score(adapt_bboxes, expected_count)
    if score > best_score:
        best_score = score
        best_bboxes = adapt_bboxes

    # Strategy 4: Color-based (HSV saturation) — good for colorful products
    hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)
    _, sat_thresh = cv2.threshold(hsv[:, :, 1], 50, 255, cv2.THRESH_BINARY)
    kernel = np.ones((9, 9), np.uint8)
    sat_closed = cv2.morphologyEx(sat_thresh, cv2.MORPH_CLOSE, kernel, iterations=4)
    contours, _ = cv2.findContours(sat_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sat_bboxes = _filter_bboxes(contours, min_area, max_area, min_dim, w, h)
    sat_bboxes = _nms_bboxes(sat_bboxes, 0.35)
    score = _score(sat_bboxes, expected_count)
    if score > best_score:
        best_bboxes = sat_bboxes

    # Sort: top-to-bottom, left-to-right
    row_height = max(1, h // 4)
    best_bboxes.sort(key=lambda b: (b[1] // row_height, b[0]))
    print(f"[CROP] OpenCV detected {len(best_bboxes)} regions (expected {expected_count})")
    return best_bboxes


def _filter_bboxes(contours, min_area, max_area, min_dim, img_w, img_h):
    """Filter contours to valid product-sized bounding boxes."""
    bboxes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < min_dim or bh < min_dim:
            continue
        aspect = max(bw, bh) / max(min(bw, bh), 1)
        if aspect > 6:
            continue
        bboxes.append((x, y, bw, bh))
    return bboxes


def _nms_bboxes(bboxes, overlap_thresh=0.35):
    """Non-max suppression to remove overlapping detections."""
    if not bboxes:
        return []
    boxes = np.array(bboxes)
    x1, y1 = boxes[:, 0], boxes[:, 1]
    x2, y2 = x1 + boxes[:, 2], y1 + boxes[:, 3]
    areas = boxes[:, 2] * boxes[:, 3]
    indices = np.argsort(areas)[::-1]
    keep = []
    while len(indices) > 0:
        i = indices[0]
        keep.append(i)
        if len(indices) == 1:
            break
        xx1 = np.maximum(x1[i], x1[indices[1:]])
        yy1 = np.maximum(y1[i], y1[indices[1:]])
        xx2 = np.minimum(x2[i], x2[indices[1:]])
        yy2 = np.minimum(y2[i], y2[indices[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / np.minimum(areas[i], areas[indices[1:]])
        remaining = np.where(iou <= overlap_thresh)[0]
        indices = indices[remaining + 1]
    return [bboxes[i] for i in keep]


# ============================================================
# GRID SPLITTING (improved aspect-ratio-aware)
# ============================================================
def _grid_split(img_w, img_h, count):
    """Split image into grid matching image aspect ratio."""
    if count <= 0:
        return []
    if count == 1:
        return [(0, 0, img_w, img_h)]

    aspect = img_w / max(img_h, 1)
    best_cols, best_rows = 1, count
    best_diff = float("inf")
    for cols in range(1, count + 1):
        rows = int(np.ceil(count / cols))
        diff = abs((cols / max(rows, 1)) - aspect)
        if diff < best_diff:
            best_diff = diff
            best_cols, best_rows = cols, rows

    cell_w = img_w // best_cols
    cell_h = img_h // best_rows
    pad_w = int(cell_w * 0.02)
    pad_h = int(cell_h * 0.02)

    bboxes = []
    for r in range(best_rows):
        for c in range(best_cols):
            if len(bboxes) >= count:
                break
            x = max(0, c * cell_w - pad_w)
            y = max(0, r * cell_h - pad_h)
            w = min(cell_w + 2 * pad_w, img_w - x)
            h = min(cell_h + 2 * pad_h, img_h - y)
            bboxes.append((x, y, w, h))
    return bboxes


# ============================================================
# BBOX-BASED CROP (from Gemini AI percentages)
# ============================================================
def crop_product_from_bbox(img_cv, bbox, img_w, img_h):
    """Crop using Gemini bbox percentages (0-100 scale)."""
    x_pct = bbox.get("x_pct", 0)
    y_pct = bbox.get("y_pct", 0)
    w_pct = bbox.get("w_pct", 100)
    h_pct = bbox.get("h_pct", 100)

    x = int(x_pct / 100 * img_w)
    y = int(y_pct / 100 * img_h)
    w = int(w_pct / 100 * img_w)
    h = int(h_pct / 100 * img_h)

    # 8% padding for better framing
    pad_x = int(w * 0.08)
    pad_y = int(h * 0.08)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(img_w, x + w + pad_x)
    y2 = min(img_h, y + h + pad_y)

    if x2 <= x1 or y2 <= y1:
        return None
    return img_cv[y1:y2, x1:x2]


# ============================================================
# MAIN PUBLIC API
# ============================================================
def detect_and_crop_products(
    source_path: str,
    product_uids: List[str],
    expected_count: int = 0,
    bboxes_from_ai: Optional[List[Optional[dict]]] = None,
) -> List[Optional[str]]:
    """
    Detect and crop individual products from a group photo.

    Priority:
      1. Gemini AI bounding boxes (if provided)
      2. OpenCV multi-strategy contour detection
      3. Grid-based splitting
      4. Full-image thumbnail

    Args:
        source_path: Path to source image
        product_uids: UIDs for each product
        expected_count: How many products to find
        bboxes_from_ai: Optional Gemini bbox dicts

    Returns:
        List of crop URL paths (same length as product_uids)
    """
    count = expected_count or len(product_uids)
    results: List[Optional[str]] = [None] * len(product_uids)

    # Open image
    img_cv = None
    if HAS_CV2:
        try:
            img_cv = cv2.imread(source_path)
        except Exception as e:
            print(f"[CROP] OpenCV imread failed: {e}")

    try:
        pil_img = PILImage.open(source_path)
        img_w, img_h = pil_img.size
    except Exception as e:
        print(f"[CROP] Cannot open image: {e}")
        return [create_thumbnail_from_full_image(source_path, uid) for uid in product_uids]

    if img_cv is not None:
        img_h_cv, img_w_cv = img_cv.shape[:2]
    else:
        img_h_cv, img_w_cv = img_h, img_w

    # ---- Strategy 1: Gemini AI bboxes ----
    ai_crop_count = 0
    if bboxes_from_ai and img_cv is not None:
        for i, bbox in enumerate(bboxes_from_ai):
            if i >= len(product_uids) or bbox is None:
                continue
            cropped = crop_product_from_bbox(img_cv, bbox, img_w_cv, img_h_cv)
            if cropped is not None and cropped.size > 0:
                url = _save_crop_cv(cropped, product_uids[i])
                if url:
                    results[i] = url
                    ai_crop_count += 1
    if ai_crop_count > 0:
        print(f"[CROP] AI bboxes: {ai_crop_count}/{len(product_uids)} crops")

    # ---- Strategy 2: OpenCV for remaining ----
    missing = [i for i in range(len(product_uids)) if results[i] is None]
    if missing and img_cv is not None and HAS_CV2:
        try:
            cv_bboxes = _detect_contours(img_cv, expected_count=len(missing))
            if len(cv_bboxes) >= len(missing):
                for j, idx in enumerate(missing):
                    if j < len(cv_bboxes):
                        x, y, bw, bh = cv_bboxes[j]
                        pad = int(min(bw, bh) * 0.06)
                        x1 = max(0, x - pad)
                        y1 = max(0, y - pad)
                        x2 = min(img_w_cv, x + bw + pad)
                        y2 = min(img_h_cv, y + bh + pad)
                        cropped = img_cv[y1:y2, x1:x2]
                        if cropped.size > 0:
                            url = _save_crop_cv(cropped, product_uids[idx])
                            if url:
                                results[idx] = url
        except Exception as e:
            print(f"[CROP] OpenCV detection failed: {e}")

    # ---- Strategy 3: Grid split for remaining ----
    missing = [i for i in range(len(product_uids)) if results[i] is None]
    if missing:
        grid_bboxes = _grid_split(img_w, img_h, len(missing))
        for j, idx in enumerate(missing):
            if j < len(grid_bboxes):
                x, y, bw, bh = grid_bboxes[j]
                try:
                    cropped = pil_img.crop((x, y, x + bw, y + bh))
                    cropped.thumbnail(THUMB_MAX, PILImage.LANCZOS)
                    crop_name = f"crop_{product_uids[idx]}.jpg"
                    crop_path = CROP_DIR / crop_name
                    cropped.convert("RGB").save(crop_path, "JPEG", quality=85)
                    results[idx] = f"/uploads/crops/{crop_name}"
                except Exception as e:
                    print(f"[CROP] Grid crop failed: {e}")

    # ---- Strategy 4: Thumbnail fallback ----
    for i in range(len(product_uids)):
        if results[i] is None:
            results[i] = create_thumbnail_from_full_image(source_path, product_uids[i])

    return results


def _save_crop_cv(cropped_cv, uid):
    """Convert OpenCV crop to enhanced PIL thumbnail and save."""
    try:
        pil_crop = PILImage.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
        pil_crop = ImageEnhance.Sharpness(pil_crop).enhance(1.2)
        pil_crop = ImageEnhance.Contrast(pil_crop).enhance(1.1)
        pil_crop.thumbnail(THUMB_MAX, PILImage.LANCZOS)
        crop_name = f"crop_{uid}.jpg"
        crop_path = CROP_DIR / crop_name
        pil_crop.convert("RGB").save(crop_path, "JPEG", quality=90)
        return f"/uploads/crops/{crop_name}"
    except Exception as e:
        print(f"[CROP] Save crop failed: {e}")
        return None


# ============================================================
# LEGACY SINGLE-PRODUCT CROP
# ============================================================
def crop_product_from_image(source_path, bbox, product_uid):
    """Crop a single product using bounding box."""
    try:
        img = PILImage.open(source_path)
        img_w, img_h = img.size

        if "x_pct" in bbox:
            x = int(bbox["x_pct"] / 100 * img_w)
            y = int(bbox["y_pct"] / 100 * img_h)
            w = int(bbox["w_pct"] / 100 * img_w)
            h = int(bbox["h_pct"] / 100 * img_h)
        elif all(0 <= bbox.get(k, 0) <= 1 for k in ["x", "y", "w", "h"]):
            x = int(bbox["x"] * img_w)
            y = int(bbox["y"] * img_h)
            w = int(bbox["w"] * img_w)
            h = int(bbox["h"] * img_h)
        else:
            x = int(bbox.get("x", 0))
            y = int(bbox.get("y", 0))
            w = int(bbox.get("w", img_w))
            h = int(bbox.get("h", img_h))

        pad_x = int(w * 0.08)
        pad_y = int(h * 0.08)
        left = max(0, x - pad_x)
        top = max(0, y - pad_y)
        right = min(img_w, x + w + pad_x)
        bottom = min(img_h, y + h + pad_y)

        if right <= left or bottom <= top:
            return None

        cropped = img.crop((left, top, right, bottom))
        cropped = ImageEnhance.Sharpness(cropped).enhance(1.2)
        cropped.thumbnail(THUMB_MAX, PILImage.LANCZOS)

        crop_name = f"crop_{product_uid}.jpg"
        crop_path = CROP_DIR / crop_name
        cropped.convert("RGB").save(crop_path, "JPEG", quality=90)
        return f"/uploads/crops/{crop_name}"

    except Exception as e:
        print(f"[CROP] Error cropping {product_uid}: {e}")
        return None


def create_thumbnail_from_full_image(source_path, product_uid):
    """Create a thumbnail of the full image as last resort."""
    try:
        img = PILImage.open(source_path)
        img.thumbnail(THUMB_MAX, PILImage.LANCZOS)
        crop_name = f"thumb_{product_uid}.jpg"
        crop_path = CROP_DIR / crop_name
        img.convert("RGB").save(crop_path, "JPEG", quality=85)
        return f"/uploads/crops/{crop_name}"
    except Exception as e:
        print(f"[CROP] Error creating thumbnail {product_uid}: {e}")
        return None
