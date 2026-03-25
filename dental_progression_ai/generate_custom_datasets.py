import os
import shutil
import cv2
import numpy as np
import yaml
from pathlib import Path

def generate_datasets(base_dir="../dentex-2", output_dir="custom_datasets"):
    """
    Generates YOLO-Pose and YOLO-Seg datasets from standard YOLO bounding box labels.
    """
    print(f"Generating custom surrogate datasets from {base_dir}")
    
    out_pose = os.path.join(output_dir, "pose")
    out_seg = os.path.join(output_dir, "seg")
    
    # Create directories
    for split in ['train', 'valid']:
        os.makedirs(os.path.join(out_pose, "images", split), exist_ok=True)
        os.makedirs(os.path.join(out_pose, "labels", split), exist_ok=True)
        os.makedirs(os.path.join(out_seg, "images", split), exist_ok=True)
        os.makedirs(os.path.join(out_seg, "labels", split), exist_ok=True)
        
    for split in ['train', 'valid']:
        images_dir = os.path.join(base_dir, split, "images")
        labels_dir = os.path.join(base_dir, split, "labels")
        
        if not os.path.exists(images_dir) or not os.path.exists(labels_dir):
            print(f"Directory not found: {images_dir} or {labels_dir}")
            continue
            
        print(f"Processing {split} split...")
        count = 0
        
        for img_name in os.listdir(images_dir):
            if not img_name.endswith(('.jpg', '.png', '.jpeg')):
                continue
                
            img_path = os.path.join(images_dir, img_name)
            label_name = img_name.replace('.jpg', '.txt').replace('.png', '.txt')
            label_path = os.path.join(labels_dir, label_name)
            
            if not os.path.exists(label_path):
                continue
                
            # Copy images
            shutil.copy(img_path, os.path.join(out_pose, "images", split, img_name))
            shutil.copy(img_path, os.path.join(out_seg, "images", split, img_name))
            
            pose_lines = []
            seg_lines = []
            
            with open(label_path, 'r') as f:
                lines = f.readlines()
                
            for line in lines:
                parts = line.strip().split()
                if len(parts) < 5: continue
                
                cls_id = parts[0]
                cx, cy, w, h = map(float, parts[1:5])
                
                # --- POSE (Keypoints) ---
                # 3 keypoints: CEJ (top 15%), Root Apex (bottom 5%), Bone Crest (middle 50%)
                k1_x, k1_y = cx, cy - (h * 0.35) # CEJ
                k2_x, k2_y = cx, cy + (h * 0.45) # Apex
                k3_x, k3_y = cx, cy              # Bone Crest
                
                # Visibility = 2 (visible)
                pose_line = f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f} {k1_x:.6f} {k1_y:.6f} 2 {k2_x:.6f} {k2_y:.6f} 2 {k3_x:.6f} {k3_y:.6f} 2"
                pose_lines.append(pose_line)
                
                # --- SEGMENTATION (Polygon mask) ---
                # Create a simple hexagon-like polygon inside the bbox to simulate tooth/bone mask
                p1_x, p1_y = cx - w*0.3, cy - h*0.4
                p2_x, p2_y = cx + w*0.3, cy - h*0.4
                p3_x, p3_y = cx + w*0.4, cy
                p4_x, p4_y = cx + w*0.2, cy + h*0.4
                p5_x, p5_y = cx - w*0.2, cy + h*0.4
                p6_x, p6_y = cx - w*0.4, cy
                
                seg_line = f"{cls_id} {p1_x:.6f} {p1_y:.6f} {p2_x:.6f} {p2_y:.6f} {p3_x:.6f} {p3_y:.6f} {p4_x:.6f} {p4_y:.6f} {p5_x:.6f} {p5_y:.6f} {p6_x:.6f} {p6_y:.6f}"
                seg_lines.append(seg_line)
                
            # Write new labels
            with open(os.path.join(out_pose, "labels", split, label_name), 'w') as f:
                f.write('\n'.join(pose_lines))
                
            with open(os.path.join(out_seg, "labels", split, label_name), 'w') as f:
                f.write('\n'.join(seg_lines))
                
            count += 1
                
        print(f"Processed {count} images for {split}.")

    # Write yaml files
    pose_yaml = {
        'path': os.path.abspath(out_pose),
        'train': 'images/train',
        'val': 'images/valid',
        'kpt_shape': [3, 3], # 3 keypoints, 3 dimensions (x, y, vis)
        'names': {0: 'tooth'}
    }
    with open(os.path.join(out_pose, 'dataset.yaml'), 'w') as f:
        yaml.dump(pose_yaml, f)
        
    seg_yaml = {
        'path': os.path.abspath(out_seg),
        'train': 'images/train',
        'val': 'images/valid',
        'names': {0: 'tooth'}
    }
    with open(os.path.join(out_seg, 'dataset.yaml'), 'w') as f:
        yaml.dump(seg_yaml, f)

    print(f"\nCreated YAMLs:")
    print(f"- {os.path.abspath(os.path.join(out_pose, 'dataset.yaml'))}")
    print(f"- {os.path.abspath(os.path.join(out_seg, 'dataset.yaml'))}")

if __name__ == "__main__":
    generate_datasets()
