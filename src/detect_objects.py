import torch
import torch.nn as nn
from ultralytics import YOLOWorld
from PIL import Image
import json
import os
import sys
import numpy as np

# --- 1. การตั้งค่าระบบ (Configuration) ---
# รับค่าความสูงจากผู้ใช้ผ่าน Command Line (ถ้าไม่มีให้ใช้ 2.5 เมตร เป็นค่าเริ่มต้น)
try:
    USER_DEFINED_HEIGHT = float(sys.argv[1]) if len(sys.argv) > 1 else 2.5
except ValueError:
    USER_DEFINED_HEIGHT = 2.5

# กำหนด Path สำหรับไฟล์รูปภาพและไฟล์ผลลัพธ์
INPUT_IMAGE = "assets/test-image.jpg"  # ตรวจสอบชื่อไฟล์รูปของคุณในโฟลเดอร์ assets
OUTPUT_JSON = "assets/objects_data.json"

# --- 2. โหลดโมเดล ZoeDepth สำหรับหาระยะลึก ---
print("Loading ZoeDepth model...")
repo = "isl-org/ZoeDepth"
zoe_model = torch.hub.load(repo, "ZoeD_N", pretrained=False, trust_repo=True)

# ระบุตำแหน่งไฟล์ weights ที่คุณโหลดไว้แล้ว
checkpoint_path = os.path.expanduser("~/.cache/torch/hub/checkpoints/ZoeD_M12_N.pt")

if os.path.exists(checkpoint_path):
    state_dict = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
    zoe_model.load_state_dict(state_dict, strict=False)
    print("Successfully loaded ZoeDepth weights.")
else:
    print(f"Error: Weights not found at {checkpoint_path}")
    sys.exit()

zoe_model.to("cpu")
zoe_model.eval()

# แก้ไขปัญหา 'Block' object has no attribute 'drop_path' (สำหรับ Python 3.14)
for name, module in zoe_model.named_modules():
    if module.__class__.__name__ == 'Block':
        if not hasattr(module, 'drop_path'):
            module.drop_path = getattr(module, 'drop_path1', nn.Identity())

# --- 3. โหลดโมเดล YOLO-World สำหรับตรวจจับเฟอร์นิเจอร์ ---
print("Loading YOLO-World for custom objects...")
yolo_model = YOLOWorld('yolov8s-world.pt') 

# กำหนดสิ่งที่ต้องการให้ตรวจจับเป็นพิเศษสำหรับโปรเจกต์ BuddyBuilder.ai
custom_classes = ["bed", "chair", "wardrobe", "air conditioner", "table", "door", "window"]
yolo_model.set_classes(custom_classes)

def process_scene(img_path, output_json, target_height):
    if not os.path.exists(img_path):
        print(f"Error: {img_path} not found.")
        return

    print(f"Scanning Room (Target Height: {target_height}m)...")
    img_pil = Image.open(img_path).convert("RGB")
    w_img, h_img = img_pil.size
    
    # รันการตรวจจับวัตถุ 2D และระยะลึก
    yolo_results = yolo_model(img_path)
    with torch.no_grad():
        depth_map = zoe_model.infer_pil(img_pil)
        
    # --- 4. คำนวณ Scale Factor จากความสูงที่ผู้ใช้กรอก ---
    # สุ่มวัดจุดที่คาดว่าเป็นผนังหรือเพดานกลางภาพเพื่อหาความสูงที่ AI ประเมินได้ (Raw AI Height)
    raw_ai_height = float(np.percentile(depth_map[:, w_img//2], 90)) 
    
    # คำนวณตัวคูณเพื่อปรับสเกลให้ได้ความสูงตามจริงที่ผู้ใช้กรอก
    scale_factor = target_height / raw_ai_height if raw_ai_height > 0 else 1.0
    print(f"Calibration: Raw AI Height {raw_ai_height:.2f}m -> Applied Scale Factor {scale_factor:.2f}x")

    objects_3d = []

    # --- 5. จัดการข้อมูลวัตถุและปรับขนาดตามสเกล ---
    for result in yolo_results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = yolo_model.names[cls_id]
            conf = float(box.conf[0])
            
            # ดึงพิกัดจุดกึ่งกลาง
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            cx, cy = max(0, min(cx, w_img-1)), max(0, min(cy, h_img-1))

            # ระยะห่างจริง (เมตร) หลังจากปรับสเกล
            raw_dist = float(depth_map[cy, cx])
            real_dist = raw_dist * scale_factor
            
            # คำนวณขนาดกว้าง x สูง จริง (เมตร) ตามสัดส่วนภาพพาโนรามา
            real_w = ((x2 - x1) / w_img) * (2 * np.pi * real_dist)
            real_h = ((y2 - y1) / h_img) * (np.pi * real_dist)

            objects_3d.append({
                "label": label,
                "confidence": round(conf, 2),
                "distance_m": round(real_dist, 3),
                "width_m": round(real_w, 3),
                "height_m": round(real_h, 3),
                "center_pixel": [cx, cy]
            })
            print(f"Found {label}: {real_w:.2f}m x {real_h:.2f}m at {real_dist:.2f}m")

    # สรุปข้อมูลทั้งหมดลง JSON
    final_output = {
        "project": "BuddyBuilder.ai",
        "student_id": "66073169",
        "room_summary": {
            "user_defined_height_m": target_height,
            "scale_factor": round(scale_factor, 2),
            "total_detected": len(objects_3d)
        },
        "objects": objects_3d,
        "status": "success"
    }

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=4)
    print(f"\nSuccessfully saved calibrated data to: {output_json}")

# รันฟังก์ชันหลัก
process_scene(INPUT_IMAGE, OUTPUT_JSON, USER_DEFINED_HEIGHT)