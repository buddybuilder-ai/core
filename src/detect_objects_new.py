import torch
import torch.nn as nn
import cv2
import numpy as np
from ultralytics import YOLOWorld, YOLO
from PIL import Image
import json
import os
import sys

# --- 1. CONFIGURATION ---
DEFAULT_HEIGHT = 2.5
current_dir = os.path.dirname(os.path.abspath(__file__)) 
BASE_DIR = os.path.dirname(current_dir) 
assets_dir = os.path.join(BASE_DIR, "assets")
os.makedirs(assets_dir, exist_ok=True)

try:
    TARGET_HEIGHT = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_HEIGHT
    INPUT_IMAGE_PATH = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(assets_dir, "my_room_2.jpg")
except Exception as e:
    TARGET_HEIGHT = DEFAULT_HEIGHT
    INPUT_IMAGE_PATH = os.path.join(assets_dir, "my_room_2.jpg")

# ขีดจำกัดขนาดมาตรฐาน (ปรับปรุงเพิ่ม)
STANDARD_LIMITS = {
    "bed": {"max_w": 2.2, "max_h": 1.2, "default_elevation": 0.0},
    "chair": {"max_w": 0.9, "max_h": 1.2, "default_elevation": 0.0},
    "sofa": {"max_w": 3.0, "max_h": 1.0, "default_elevation": 0.0},
    "wardrobe": {"max_w": 2.5, "max_h": 2.4, "default_elevation": 0.0},
    "monitor": {"max_w": 1.2, "max_h": 0.8, "default_elevation": 0.7}
}

# --- 2. LOAD SOTA MODELS ---
print(f"🚀 Upgrading Engine to SOTA | Root: {BASE_DIR}")

# A. Load Depth Anything V2 (แทนที่ ZoeDepth)
# หมายเหตุ: ในปี 2026 เราใช้รุ่น v2 ที่เล็กและแม่นยำกว่า
depth_model = torch.hub.load("depth-anything/Depth-Anything-V2", "depth_anything_v2_vits", pretrained=True, trust_repo=True)
depth_model.to("cpu").eval()

# B. Load YOLOv11 (แทนที่ v8-world เพื่อความเป๊ะของ Box ในงาน Indoor)
yolo_model = YOLO('yolo11s.pt') 

# --- 3. PROCESSING FUNCTION ---
def process_room_3d(img_path, output_json, user_h):
    if not os.path.exists(img_path):
        print(f"❌ Error: Image not found")
        return

    # อ่านภาพด้วย OpenCV (รองรับโมเดลใหม่ๆ ได้ดีกว่า)
    raw_img = cv2.imread(img_path)
    img_rgb = cv2.cvtColor(raw_img, cv2.COLOR_BGR2RGB)
    h_img, w_img = img_rgb.shape[:2]

    # 1. Inference Depth
    print("🌀 Estimating Depth with Depth Anything V2...")
    with torch.no_grad():
        # Depth Anything ให้ผลลัพธ์เป็น Relative Depth ที่ละเอียดสูง
        depth_map = depth_model.infer_image(img_rgb) 
    
    # 2. Inference Objects
    print("🔍 Detecting Objects with YOLOv11...")
    results = yolo_model.predict(img_path, conf=0.25)

    # 3. Calibration (คำนวณ Scale Factor จากพื้นและเพดาน)
    # ใช้ค่าเฉลี่ยของส่วนล่าง (พื้น) และส่วนบน (เพดาน) ของภาพ
    floor_region = depth_map[int(h_img*0.9):, :]
    ceiling_region = depth_map[:int(h_img*0.1), :]
    
    avg_floor_depth = np.median(floor_region)
    avg_ceiling_depth = np.median(ceiling_region)
    
    # คำนวณ Scale Factor เพื่อเปลี่ยน Relative Depth เป็น Metric (เมตร)
    # ใช้วิธี Ratio mapping จาก User Height
    raw_range = abs(avg_floor_depth - avg_ceiling_depth)
    scale_factor = user_h / raw_range if raw_range > 0 else 1.0
    cam_height = user_h / 2

    objects_3d = []
    for result in results:
        for box in result.boxes:
            label = yolo_model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)

            # ดึงค่าความลึกตรงจุดกึ่งกลางวัตถุ
            rel_depth = depth_map[min(cy, h_img-1), min(cx, w_img-1)]
            real_dist = rel_depth * scale_factor

            # คำนวณขนาดวัตถุโดยใช้ Field of View (FOV) ประมาณการ
            # สูตร: Width = (Pixel_Width / Image_Width) * 2 * Distance * tan(FOV/2)
            fov_h_rad = np.deg2rad(60) # สมมติ FOV กล้องมือถือทั่วไปที่ 60 องศา
            w_m = ((x2 - x1) / w_img) * 2 * real_dist * np.tan(fov_h_rad / 2)
            h_m = ((y2 - y1) / h_img) * 2 * real_dist * np.tan(fov_h_rad / 2)

            # คำนวณระดับความสูงจากพื้น (Elevation)
            # ใช้พิกเซลล่างสุดของ Box (y2) เทียบกับกึ่งกลางภาพ
            angle_offset = ((y2 / h_img) - 0.5) * fov_h_rad
            elevation_m = max(0, cam_height - (real_dist * np.tan(angle_offset)))

            # Apply Limits
            if label in STANDARD_LIMITS:
                lim = STANDARD_LIMITS[label]
                w_m = min(w_m, lim["max_w"])
                h_m = min(h_m, lim["max_h"])
                if elevation_m < 0.2 and lim["default_elevation"] == 0: elevation_m = 0.0

            objects_3d.append({
                "label": label,
                "confidence": round(conf, 2),
                "width_m": round(w_m, 2),
                "height_m": round(h_m, 2),
                "elevation_m": round(elevation_m, 2),
                "distance_m": round(real_dist, 2),
                "position_px": [cx, cy]
            })
            print(f"📦 {label:15} | Size: {w_m:.2f}x{h_m:.2f}m | Elev: {elevation_m:.2f}m")

    # --- 4. SAVE OUTPUT ---
    final_output = {
        "project": "BuddyBuilder.ai",
        "student_id": "66073169",
        "metadata": {"engine": "DepthAnythingV2+YOLO11", "room_h": user_h},
        "objects": objects_3d,
        "status": "success"
    }

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=4)
    print(f"\n✨ Processed {len(objects_3d)} objects. Saved to {output_json}")

# RUN
output_json_path = os.path.join(assets_dir, "my_room_2_data.json")
process_room_3d(INPUT_IMAGE_PATH, output_json_path, TARGET_HEIGHT)