import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from ultralytics import YOLOWorld
import matplotlib.pyplot as plt

# --- 1. CONFIGURATION & ARGUMENT HANDLING ---
DEFAULT_HEIGHT = 2.5
# หาตำแหน่ง Root ของโปรเจกต์ (ย้อนกลับจาก core/src ไป 3 ชั้น)
# หาตำแหน่งโฟลเดอร์ src (ที่ไฟล์นี้อยู่)
current_dir = os.path.dirname(os.path.abspath(__file__))
# ย้อนกลับ 1 ชั้นไปที่โฟลเดอร์ core
BASE_DIR = os.path.dirname(current_dir)

# กำหนด Path ไปที่ assets (จะกลายเป็น core/assets)
assets_dir = os.path.join(BASE_DIR, "assets")

# ตรวจสอบ/สร้างโฟลเดอร์ assets
os.makedirs(assets_dir, exist_ok=True)

# กำหนดชื่อไฟล์ output
output_json_path = os.path.join(assets_dir, "my_room_2_data.json")
DEFAULT_IMAGE = os.path.join(assets_dir, "my_room_2.jpg")

# ระบบรับค่าจาก Command Line (FastAPI จะส่งมาให้)
try:
    # Argument 1: ความสูงห้อง (e.g., 2.5)
    TARGET_HEIGHT = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_HEIGHT

    # Argument 2: Path ของรูปภาพที่อัปโหลด (ส่งมาจาก FastAPI)
    if len(sys.argv) > 2:
        INPUT_IMAGE_PATH = os.path.abspath(sys.argv[2])
    else:
        INPUT_IMAGE_PATH = DEFAULT_IMAGE

    # Argument 3: User ID (Optional)
    USER_ID = sys.argv[3] if len(sys.argv) > 3 else None

except Exception as e:
    print(f"⚠️ Argument Error: {e}")
    TARGET_HEIGHT = DEFAULT_HEIGHT
    INPUT_IMAGE_PATH = DEFAULT_IMAGE
    USER_ID = None

# กำหนดขีดจำกัดขนาดมาตรฐานสำหรับเฟอร์นิเจอร์แต่ละชนิด
STANDARD_LIMITS = {
    "bed": {"max_w": 2.2, "max_h": 1.0, "default_elevation": 0.0},
    "chair": {"max_w": 0.8, "max_h": 1.1, "default_elevation": 0.0},
    "wardrobe": {"max_w": 2.5, "max_h": 2.2, "default_elevation": 0.0},
    "air conditioner": {"max_w": 1.2, "max_h": 0.5, "default_elevation": 2.0},
    "table": {"max_w": 2.0, "max_h": 0.8, "default_elevation": 0.0},
}

# --- 2. LOAD MODELS ---
print(f"🚀 Loading AI Engine | Project Root: {BASE_DIR}")
print(f"📸 Target Image: {INPUT_IMAGE_PATH}")

repo = "isl-org/ZoeDepth"
zoe_model = torch.hub.load(repo, "ZoeD_N", pretrained=False, trust_repo=True)  # type: ignore
checkpoint_path = os.path.expanduser("~/.cache/torch/hub/checkpoints/ZoeD_M12_N.pt")

if os.path.exists(checkpoint_path):
    state_dict = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    zoe_model.load_state_dict(state_dict, strict=False)
else:
    print("❌ Warning: ZoeDepth checkpoint not found. Model might not work correctly.")

for _, module in zoe_model.named_modules():
    if module.__class__.__name__ == "Block" and not hasattr(module, "drop_path"):
        module.drop_path = getattr(module, "drop_path1", nn.Identity())

zoe_model.to("cpu").eval()
yolo_model = YOLOWorld("yolov8s-world.pt")
# --- แก้ไขส่วน set_classes ใน detect_objects_2.py ---
yolo_model.set_classes(
    [
        # โซนนอน (Sleeping Zone)
        "bed",
        "bunk bed",
        "bed frame",
        # "sofa bed",
        "nightstand",
        "dresser",
        # โซนนั่งเล่น (Living Zone)
        "sofa",
        "armchair",
        "coffee table",
        "tv stand",
        "room divider",
        # โซนทำงาน & ออฟฟิศ (Working/Office Zone)
        "desk",
        "computer desk",
        # "folding desk",
        "chair",
        "office chair",
        "filing cabinet",
        # โซนทานอาหาร (Dining Zone)
        "dining table",
        # "compact dining",
        "dining chair",
        "sideboard",
        # โซนครัว (Kitchen Zone)
        "kitchen counter",
        "mini fridge",
        "microwave stand",
        # เก็บของ (Storage)
        "wardrobe",
        # "compact wardrobe",
        "bookshelf",
        "shelf",
        "shoe cabinet",
        "coat rack",
        # เครื่องตกแต่ง & ทั่วไป (Decor/General)
        "plant",
        "lamp",
        "ceiling light", # เพิ่มคำนี้เข้าไป
        "pendant lamp",  # หรือคำนี้สำหรับโคมไฟระย้า
        "rug",
        "door",
        "monitor",
    ]
)


# --- 3. PROCESSING FUNCTION ---
def process_with_elevation(img_path: str, output_json: str, user_h: float, user_id: str | None = None) -> None:
    if not os.path.exists(img_path):
        print(f"❌ Error: Image not found at {img_path}")
        sys.exit(1)

    img_pil = Image.open(img_path).convert("RGB")
    w_img, h_img = img_pil.size

    yolo_results = yolo_model(img_path)

    for i, result in enumerate(yolo_results):
        # วาดกรอบและป้ายกำกับลงบนรูป
        annotated_frame = result.plot() 
        
        # กำหนด Path สำหรับเซฟรูป (เซฟไว้ในโฟลเดอร์ assets)
        debug_image_path = os.path.join(assets_dir, f"debug_detection_{i}.jpg")
        
        # แปลงจาก BGR (OpenCV) เป็น RGB แล้วบันทึก
        Image.fromarray(annotated_frame[..., ::-1]).save(debug_image_path)
        
        print(f"📸 Debug image saved to: {debug_image_path}")

    with torch.no_grad():
        depth_map = zoe_model.infer_pil(img_pil)

        plt.figure(figsize=(10, 10))
        plt.imshow(depth_map, cmap='magma') # 'magma' หรือ 'plasma' จะเห็นความลึกชัดมาก
        plt.axis('off')
        
        depth_debug_path = os.path.join(assets_dir, "debug_depth.jpg")
        plt.savefig(depth_debug_path, bbox_inches='tight', pad_inches=0)
        plt.close()
        
        print(f"📏 Depth map (Visual) saved to: {depth_debug_path}")

    # Get depth map dimensions
    h_depth, w_depth = depth_map.shape

    # Calculate scaling factors
    x_scale = w_depth / w_img
    y_scale = h_depth / h_img

    dist_to_floor = float(np.median(depth_map[-20:, w_depth // 2]))
    dist_to_ceiling = float(np.median(depth_map[:20, w_depth // 2]))
    raw_ai_height = dist_to_floor + dist_to_ceiling
    scale_factor = user_h / raw_ai_height if raw_ai_height > 0 else 1.0
    cam_height = user_h / 2

    objects_3d = []
    for result in yolo_results:
        for box in result.boxes:
            label = yolo_model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            if conf < 0.1:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx_orig, cy_orig = int((x1 + x2) / 2), int((y1 + y2) / 2)

            # Scale coordinates to match depth map dimensions
            scaled_cx = int(cx_orig * x_scale)
            scaled_cy = int(cy_orig * y_scale)

            # Clamp values to be within the bounds of the depth map
            scaled_cx = max(0, min(w_depth - 1, scaled_cx))
            scaled_cy = max(0, min(h_depth - 1, scaled_cy))

            real_dist = float(depth_map[scaled_cy, scaled_cx]) * scale_factor
            w_m = ((x2 - x1) / w_img) * (2 * np.pi * real_dist)
            h_m = ((y2 - y1) / h_img) * (np.pi * real_dist)

            angle_rad = (0.5 - (y2 / h_img)) * np.pi
            elevation_m = cam_height + (real_dist * np.sin(angle_rad))
            elevation_m = max(0, elevation_m)

            if label in STANDARD_LIMITS:
                limits = STANDARD_LIMITS[label]
                if w_m > limits["max_w"]:
                    w_m = limits["max_w"]
                if h_m > limits["max_h"]:
                    h_m = limits["max_h"]
                if limits["default_elevation"] == 0 and elevation_m < 0.3:
                    elevation_m = 0.0

            # --- ตัวอย่างการ Log เพื่อดูการทำงานร่วมกัน ---
            print(f"\n🔍 Analyzing: {label} ({conf:.2f} confidence)")
            print(f"   [YOLO] Bounding Box (pixels): x1={x1:.0f}, y1={y1:.0f}, x2={x2:.0f}, y2={y2:.0f}")
            print(f"   [ZOE]  Sampling Depth at Center [{scaled_cx}, {scaled_cy}]: {real_dist:.2f} meters")
            print(f"   [CALC] Real-world Size: {w_m:.2f}m (W) x {h_m:.2f}m (H)")
            print(f"   [CALC] Elevation from Floor: {elevation_m:.2f}m")

            objects_3d.append(
                {
                    "label": label,
                    "confidence": round(conf, 2),
                    "width_m": round(w_m, 2),
                    "height_m": round(h_m, 2),
                    "elevation_m": round(elevation_m, 2),
                    "distance_m": round(real_dist, 2),
                    "center_pixel": [cx_orig, cy_orig],
                }
            )
            print(f"✅ Found {label:15}: {w_m:.2f}x{h_m:.2f}m at {elevation_m:.2f}m")

    final_data = {
        "room_summary": {
            "applied_height_m": user_h,
            "scale_factor": round(scale_factor, 2),
            "total_objects": len(objects_3d),
        },
        "objects": objects_3d,
        "status": "success",
    }
    
    if user_id:
        final_data["userId"] = user_id

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=4)
    print(f"\n✨ DONE! Data saved to: {output_json}")


# --- 4. EXECUTION ---
# บันทึกผลลัพธ์ไว้ที่โฟลเดอร์ assets ของ Root เสมอเพื่อให้ Frontend เข้าถึงได้
output_json_path = os.path.join(BASE_DIR, "assets", "my_room_2_data.json")

process_with_elevation(INPUT_IMAGE_PATH, output_json_path, TARGET_HEIGHT, USER_ID)
