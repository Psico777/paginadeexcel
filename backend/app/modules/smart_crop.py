"""
EMFOX OMS v3.0 - Smart Crop Module (AI-Enhanced with Local Vision)
===================================================================
Enhanced product detection pipeline:
  1. Ollama Vision (moondream) — local AI bounding box detection (0 API cost)
  2. Gemini AI bboxes (if available from upstream)
  3. OpenCV multi-strategy contour detection
  4. Intelligent grid splitting
  5. Full-image thumbnail fallback

Optimized for: 2GB VRAM (MX230) + 32GB RAM
"""

import os
import json
import uuid
import base64
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image as PILImage, ImageFilter, ImageEnhance

from app.config import settings

# Try imports
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("[CROP] OpenCV not available")

try:
    import requests as http_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

CROP_DIR = Path(settings.upload_dir) / "crops"
CROP_DIR.mkdir(parents=True, exist_ok=True)

THUMB_MAX = (400, 400)

# Ollama config (from settings)
try:
    from app.config import settings as _settings
    OLLAMA_URL = _settings.ollama_url
    OLLAMA_VISION_MODEL = _settings.ollama_vision_model
except Exception:
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "moondream")


# ============================================================
# OLLAMA VISION - LOCAL AI DETECTION (FREE, NO API COST)
# ============================================================
def _detect_with_ollama_vision(image_path: str, expected_count: int = 0) -> List[dict]:
    """
    Use Ollama Vision (moondream) to detect product bounding boxes.
    Returns list of bbox dicts: [{x_pct, y_pct, w_pct, h_pct}, ...]
    
    This runs 100% locally — zero API cost, zero tokens burned.
    """
    if not HAS_REQUESTS:
        print("[CROP] requests library not available for Ollama")
        return []

    try:
        # Convert image to base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        count_hint = f" I expect approximately {expected_count} products." if expected_count > 0 else ""

        prompt = f"""Look at this image carefully. It contains multiple products/items displayed together.{count_hint}

For EACH distinct product/item visible in the image, give me the bounding box coordinates as percentages of the image dimensions.

Respond ONLY with a JSON array. Each element should have:
- "x_pct": left edge as percentage (0-100) of image width
- "y_pct": top edge as percentage (0-100) of image height  
- "w_pct": width as percentage (0-100) of image width
- "h_pct": height as percentage (0-100) of image height
- "label": brief description of the product

Example response:
[{{"x_pct": 5, "y_pct": 10, "w_pct": 45, "h_pct": 80, "label": "blue stuffed animal"}}, {{"x_pct": 52, "y_pct": 8, "w_pct": 43, "h_pct": 82, "label": "red toy car"}}]

Respond ONLY with the JSON array, no other text."""

        response = http_requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_VISION_MODEL,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 1024,
                }
            },
            timeout=60
        )

        if response.status_code != 200:
            print(f"[CROP] Ollama returned {response.status_code}")
            return []

        result = response.json()
        text = result.get("response", "").strip()
        
        # Extract JSON from response
        bboxes = _parse_bbox_json(text)
        
        if bboxes:
            print(f"[CROP] Ollama Vision detected {len(bboxes)} products")
            # Validate and clamp values
            validated = []
            for bb in bboxes:
                try:
                    validated.append({
                        "x_pct": max(0, min(100, float(bb.get("x_pct", 0)))),
                        "y_pct": max(0, min(100, float(bb.get("y_pct", 0)))),
                        "w_pct": max(5, min(100, float(bb.get("w_pct", 50)))),
                        "h_pct": max(5, min(100, float(bb.get("h_pct", 50)))),
                    })
                except (ValueError, TypeError):
                    continue
            return validated
        
        print("[CROP] Ollama Vision: could not parse bboxes from response")
        return []

    except http_requests.exceptions.ConnectionError:
        print("[CROP] Ollama not running — skipping local vision")
        return []
    except Exception as e:
        print(f"[CROP] Ollama Vision error: {e}")
        return []


def _parse_bbox_json(text: str) -> list:
    """Extract JSON array from AI response, handling common formatting issues."""
    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Find JSON array in text
    import re
    matches = re.findall(r'\[[\s\S]*?\]', text)
    for match in matches:
        try:
            result = json.loads(match)
            if isinstance(result, list) and len(result) > 0:
                return result
        except json.JSONDecodeError:
            continue

    # Try fixing common issues
    text_clean = text.replace("'", '"').replace("True", "true").replace("False", "false")
    try:
        result = json.loads(text_clean)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    return []


# ============================================================
# OPENCV DETECTION PIPELINE (multi-strategy, unchanged)
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

    # Strategy 1: Canny edge detection
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

    # Strategy 4: Color-based (HSV saturation)
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

    row_height = max(1, h // 4)
    best_bboxes.sort(key=lambda b: (b[1] // row_height, b[0]))
    print(f"[CROP] OpenCV detected {len(best_bboxes)} regions (expected {expected_count})")
    return best_bboxes


def _filter_bboxes(contours, min_area, max_area, min_dim, img_w, img_h):
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
# GRID SPLITTING
# ============================================================
def _grid_split(img_w, img_h, count):
    """
    Split image into grid matching image orientation.
    For TALL images (portrait): horizontal strips (products stacked vertically)
    For WIDE images (landscape): vertical strips
    For square-ish: standard grid
    """
    if count <= 0:
        return []
    if count == 1:
        return [(0, 0, img_w, img_h)]

    aspect = img_w / max(img_h, 1)

    # Portrait photo (taller than wide) — common in warehouse product photos
    # Products are typically stacked top-to-bottom
    if aspect < 0.85:
        # Horizontal strips: 1 column, N rows
        best_cols, best_rows = 1, count
    # Landscape photo
    elif aspect > 1.3:
        # Vertical strips: N columns, 1 row
        best_cols, best_rows = count, 1
    else:
        # Square-ish: find best grid
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
    # Overlap padding (5%) so products at borders aren't cut
    pad_w = int(cell_w * 0.05)
    pad_h = int(cell_h * 0.05)

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
# BBOX-BASED CROP
# ============================================================
def crop_product_from_bbox(img_cv, bbox, img_w, img_h):
    """
    Crop using bbox percentages (0-100 scale).
    Enhanced: validates crop area and uses adaptive padding.
    """
    x_pct = bbox.get("x_pct", 0)
    y_pct = bbox.get("y_pct", 0)
    w_pct = bbox.get("w_pct", 100)
    h_pct = bbox.get("h_pct", 100)

    x = int(x_pct / 100 * img_w)
    y = int(y_pct / 100 * img_h)
    w = int(w_pct / 100 * img_w)
    h = int(h_pct / 100 * img_h)

    # Skip if bbox covers almost the entire image (bad detection)
    if w_pct > 90 and h_pct > 90:
        return None

    # Adaptive padding: more for small crops, less for large ones
    size_ratio = (w * h) / max(img_w * img_h, 1)
    pad_factor = 0.12 if size_ratio < 0.15 else 0.06
    pad_x = int(w * pad_factor)
    pad_y = int(h * pad_factor)

    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(img_w, x + w + pad_x)
    y2 = min(img_h, y + h + pad_y)

    # Minimum crop size
    if x2 - x1 < 50 or y2 - y1 < 50:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return img_cv[y1:y2, x1:x2]


# ============================================================
# MAIN PUBLIC API (ENHANCED)
# ============================================================
def _is_good_bbox(bbox: dict, img_w: int, img_h: int) -> bool:
    """
    Check if a Gemini bbox is specific enough to be useful.
    Rejects bboxes that cover too much of the image width
    (Gemini default fallback when it's unsure about position).
    """
    if not bbox:
        return False
    w_pct = bbox.get("w_pct", 100)
    h_pct = bbox.get("h_pct", 100)
    x_pct = bbox.get("x_pct", 0)

    # Reject if covers >80% width AND >60% height (too generic)
    if w_pct > 80 and h_pct > 60:
        return False
    # Reject if basically full image
    if w_pct > 90 and h_pct > 90:
        return False
    # Reject if x_pct=0 and w_pct>70% (Gemini gave up on horizontal position)
    if x_pct < 2 and w_pct > 70:
        return False
    return True


def detect_and_crop_products(
    source_path: str,
    product_uids: List[str],
    expected_count: int = 0,
    bboxes_from_ai: Optional[List[Optional[dict]]] = None,
) -> List[Optional[str]]:
    """
    Detect and crop individual products from a group photo.

    ENHANCED Priority:
      1. Gemini AI bounding boxes (if provided from upstream)
      2. ★ NEW: Ollama Vision (moondream) — local AI detection, FREE
      3. OpenCV multi-strategy contour detection
      4. Grid-based splitting
      5. Full-image thumbnail

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

    # ---- Strategy 1: Gemini AI bboxes (from upstream) ----
    # Only use bboxes that are specific enough (not generic fallbacks)
    ai_crop_count = 0
    valid_ai_bboxes = 0
    if bboxes_from_ai:
        valid_ai_bboxes = sum(1 for b in bboxes_from_ai if _is_good_bbox(b, img_w_cv, img_h_cv))

    if bboxes_from_ai and img_cv is not None and valid_ai_bboxes == len(product_uids):
        # All bboxes look specific — trust Gemini fully
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
            print(f"[CROP] Gemini AI bboxes (all valid): {ai_crop_count}/{len(product_uids)} crops")
    elif bboxes_from_ai and img_cv is not None and valid_ai_bboxes > 0:
        # Some bboxes are good, use them, skip the rest
        for i, bbox in enumerate(bboxes_from_ai):
            if i >= len(product_uids) or not _is_good_bbox(bbox, img_w_cv, img_h_cv):
                continue
            cropped = crop_product_from_bbox(img_cv, bbox, img_w_cv, img_h_cv)
            if cropped is not None and cropped.size > 0:
                url = _save_crop_cv(cropped, product_uids[i])
                if url:
                    results[i] = url
                    ai_crop_count += 1
        if ai_crop_count > 0:
            print(f"[CROP] Gemini AI bboxes (partial {valid_ai_bboxes}/{len(product_uids)}): {ai_crop_count} crops")

    # ---- Strategy 2: ★ Ollama Vision (local AI, FREE) ----
    missing = [i for i in range(len(product_uids)) if results[i] is None]
    if missing and img_cv is not None:
        ollama_bboxes = _detect_with_ollama_vision(source_path, expected_count=len(missing))
        if len(ollama_bboxes) >= len(missing):
            for j, idx in enumerate(missing):
                if j < len(ollama_bboxes):
                    cropped = crop_product_from_bbox(img_cv, ollama_bboxes[j], img_w_cv, img_h_cv)
                    if cropped is not None and cropped.size > 0:
                        url = _save_crop_cv(cropped, product_uids[idx])
                        if url:
                            results[idx] = url
            ollama_done = sum(1 for i in missing if results[i] is not None)
            if ollama_done > 0:
                print(f"[CROP] Ollama Vision: {ollama_done}/{len(missing)} crops")

    # ---- Strategy 3: OpenCV for remaining ----
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

    # ---- Strategy 4: Grid split for remaining ----
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

    # ---- Strategy 5: Thumbnail fallback ----
    for i in range(len(product_uids)):
        if results[i] is None:
            results[i] = create_thumbnail_from_full_image(source_path, product_uids[i])

    # Clean up: delete original if ALL crops succeeded
    all_cropped = all(r is not None and "crop_" in r for r in results)
    if all_cropped and len(results) > 1:
        print(f"[CROP] ✅ All {len(results)} products cropped — original can be replaced in UI")

    return results


def _save_crop_cv(cropped_cv, uid):
    """Convert OpenCV crop to enhanced PIL thumbnail and save.
    Includes smart trimming to remove handwritten text margins."""
    try:
        pil_crop = PILImage.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
        
        # Smart trim: if the left portion is mostly white/empty (handwritten text area),
        # crop it out to focus on the product
        if HAS_CV2:
            try:
                gray = cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2GRAY)
                h, w = gray.shape[:2]
                
                # Check if left 30% is mostly empty (>70% white-ish pixels)
                left_region = gray[:, :int(w * 0.3)]
                white_ratio = np.sum(left_region > 200) / max(left_region.size, 1)
                
                if white_ratio > 0.60 and w > 200:
                    # Find where the product actually starts (first column with significant content)
                    col_means = np.mean(gray < 180, axis=0)  # dark pixel ratio per column
                    product_cols = np.where(col_means > 0.15)[0]
                    if len(product_cols) > 0:
                        start_x = max(0, product_cols[0] - int(w * 0.03))
                        if start_x > int(w * 0.1):  # only trim if meaningful
                            cropped_cv = cropped_cv[:, start_x:]
                            pil_crop = PILImage.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
            except Exception:
                pass  # If smart trim fails, continue with original crop
        
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
# MANUAL CROP (user-defined coordinates)
# ============================================================
def manual_crop(source_path: str, x: int, y: int, width: int, height: int, product_uid: str) -> str:
    """
    Crop image at exact pixel coordinates provided by the user.
    Args:
        source_path: Local path to the source image
        x, y: Top-left corner of the crop area
        width, height: Dimensions of the crop area
        product_uid: UID for naming the output file
    Returns:
        URL path to the saved crop (e.g. /uploads/crops/crop_<uid>.jpg)
    """
    try:
        img = PILImage.open(source_path)
        img_w, img_h = img.size

        # Clamp to image bounds
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(img_w, int(x) + int(width))
        y2 = min(img_h, int(y) + int(height))

        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"Invalid crop region: ({x1},{y1})-({x2},{y2})")

        cropped = img.crop((x1, y1, x2, y2))
        # Light enhancement
        cropped = ImageEnhance.Sharpness(cropped).enhance(1.2)
        cropped = ImageEnhance.Contrast(cropped).enhance(1.05)
        cropped.thumbnail(THUMB_MAX, PILImage.LANCZOS)

        crop_name = f"crop_{product_uid}.jpg"
        crop_path = CROP_DIR / crop_name
        cropped.convert("RGB").save(crop_path, "JPEG", quality=92)
        print(f"[CROP] Manual crop saved: {crop_path}")
        return f"/uploads/crops/{crop_name}"
    except Exception as e:
        print(f"[CROP] manual_crop failed: {e}")
        raise


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
