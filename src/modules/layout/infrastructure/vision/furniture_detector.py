"""Furniture detector using YOLOv8 (COCO labels → furniture catalog mapping)."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# COCO class names → furniture catalog category mapping
# YOLOv8n trained on COCO detects these furniture-relevant classes
COCO_TO_CATALOG: dict[str, str] = {
    "chair": "chair",
    "couch": "sofa",
    "bed": "bed",
    "dining table": "dining_table",
    "toilet": None,         # exclude
    "tv": "tv_stand",
    "laptop": None,         # exclude
    "book": None,           # exclude
    "clock": None,          # exclude
    "vase": "plant",
    "potted plant": "plant",
    "refrigerator": "mini_fridge",
    "microwave": "microwave_stand",
    "oven": None,
    "sink": None,
    "desk": "desk",
    "wardrobe": "wardrobe",
    "cabinet": "wardrobe",
    "bookshelf": "bookshelf",
    "sofa": "sofa",
    "armchair": "armchair",
    "lamp": "lamp",
    "table": "coffee_table",
}

# Approximate real-world dimensions per catalog category (width_m, depth_m, height_m)
CATEGORY_DIMENSIONS: dict[str, tuple[float, float, float]] = {
    "bed":            (1.6, 2.0, 0.5),
    "wardrobe":       (1.2, 0.6, 2.0),
    "nightstand":     (0.5, 0.4, 0.6),
    "dresser":        (1.0, 0.5, 0.8),
    "sofa":           (2.0, 0.9, 0.8),
    "armchair":       (0.8, 0.8, 0.9),
    "coffee_table":   (1.0, 0.6, 0.45),
    "tv_stand":       (1.4, 0.4, 0.5),
    "bookshelf":      (0.8, 0.3, 1.8),
    "desk":           (1.2, 0.6, 0.75),
    "chair":          (0.5, 0.5, 0.9),
    "dining_table":   (1.6, 0.9, 0.75),
    "dining_chair":   (0.45, 0.45, 0.9),
    "plant":          (0.4, 0.4, 0.8),
    "lamp":           (0.3, 0.3, 1.5),
    "rug":            (2.0, 1.5, 0.02),
    "sofa_bed":       (2.0, 0.9, 0.8),
    "mini_fridge":    (0.5, 0.5, 0.85),
    "microwave_stand":(0.6, 0.5, 0.9),
}


@lru_cache(maxsize=1)
def _get_model():
    """Load YOLOv8n model once and cache it."""
    try:
        from ultralytics import YOLO
        model_path = Path(__file__).parent / "weights" / "yolov8n.pt"
        if model_path.exists():
            model = YOLO(str(model_path))
        else:
            # Download automatically to weights/ dir
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model = YOLO("yolov8n.pt")
            # Move downloaded weights to our dir for caching
            import shutil
            downloaded = Path("yolov8n.pt")
            if downloaded.exists():
                shutil.move(str(downloaded), str(model_path))
        logger.info("YOLOv8n loaded successfully")
        return model
    except Exception as exc:
        logger.error("Failed to load YOLOv8 model: %s", exc)
        raise


def detect_furniture(
    image_bytes: bytes,
    target_height_m: float = 2.7,
    conf_threshold: float = 0.35,
) -> list[dict[str, Any]]:
    """Run YOLOv8 on image bytes and return furniture detections.

    Args:
        image_bytes: Raw image bytes (JPEG/PNG).
        target_height_m: Room height in metres — used to estimate real-world scale.
        conf_threshold: Minimum confidence to include a detection.

    Returns:
        List of dicts matching the DetectedObject schema expected by the frontend:
          label, confidence, width_m, height_m, elevation_m, distance_m, center_pixel
    """
    import io
    from PIL import Image

    model = _get_model()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_w, img_h = image.size

    results = model(image, conf=conf_threshold, verbose=False)

    detections: list[dict[str, Any]] = []
    seen_categories: set[str] = set()

    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue

        for box in boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            coco_label = model.names[cls_id].lower()

            catalog_category = COCO_TO_CATALOG.get(coco_label)
            if catalog_category is None:
                continue

            # Deduplicate: keep only the highest-confidence instance per category
            if catalog_category in seen_categories:
                continue
            seen_categories.add(catalog_category)

            # Bounding box in pixels
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            box_w_px = x2 - x1
            box_h_px = y2 - y1

            # Scale estimation: use known height of furniture relative to image height
            dims = CATEGORY_DIMENSIONS.get(catalog_category, (1.0, 1.0, 1.0))
            real_w, real_d, real_h = dims

            # Pixel-per-metre estimate from furniture height in image vs real height
            px_per_m = (box_h_px / real_h) if real_h > 0 else (img_h / target_height_m)
            px_per_m = max(px_per_m, img_h / (target_height_m * 3))  # sanity clamp

            est_width_m = box_w_px / px_per_m
            est_height_m = real_h

            # Distance: objects that appear smaller are further away
            # Use ratio of furniture pixel height vs expected pixel height at 1m
            expected_px_at_1m = img_h / target_height_m * real_h
            distance_m = max(0.3, expected_px_at_1m / max(box_h_px, 1))
            distance_m = min(distance_m, 8.0)  # clamp to reasonable room depth

            # Elevation: bottom of bounding box relative to image bottom
            elevation_m = max(0.0, (img_h - y2) / img_h * target_height_m)

            detections.append({
                "label": catalog_category,
                "confidence": round(conf, 3),
                "width_m": round(est_width_m, 2),
                "height_m": round(est_height_m, 2),
                "elevation_m": round(elevation_m, 2),
                "distance_m": round(distance_m, 2),
                "center_pixel": [round(cx), round(cy)],
            })

    # Sort by confidence descending
    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections
