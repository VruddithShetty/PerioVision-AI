import os
import glob
import yaml
import cv2

def validate_split(split_name, img_dir, label_dir):
    print(f"\n--- Validating Split: {split_name} ---")
    img_files = glob.glob(os.path.join(img_dir, "*.*"))
    # Filter for standard image formats
    img_files = [f for f in img_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
    
    total_images = len(img_files)
    valid_images = 0
    missing_labels = 0
    invalid_labels = 0
    out_of_range_coords = 0
    corrupt_images = 0
    
    print(f"Total images found in {img_dir}: {total_images}")
    
    for img_path in img_files:
        img_name = os.path.basename(img_path)
        base_name, _ = os.path.splitext(img_name)
        
        # 1. Check if image is corrupt
        img = cv2.imread(img_path)
        if img is None:
            print(f"[ERROR] Corrupt image file: {img_path}")
            corrupt_images += 1
            continue
        
        h, w = img.shape[:2]
        valid_images += 1
        
        # 2. Check matching label file
        label_path = os.path.join(label_dir, f"{base_name}.txt")
        if not os.path.exists(label_path):
            print(f"[ERROR] Missing label file for image: {img_name}")
            missing_labels += 1
            continue
            
        # 3. Validate label contents
        with open(label_path, 'r') as f:
            lines = f.readlines()
            
        label_valid = True
        for line_num, line in enumerate(lines):
            parts = line.strip().split()
            if len(parts) < 14:
                print(f"[ERROR] {label_path} Line {line_num}: invalid format (too few elements: {len(parts)})")
                invalid_labels += 1
                label_valid = False
                break
                
            try:
                class_id = int(parts[0])
                coords = [float(x) for x in parts[1:]]
            except ValueError:
                print(f"[ERROR] {label_path} Line {line_num}: coordinate parsing failed")
                invalid_labels += 1
                label_valid = False
                break
                
            # Check range of bbox coordinates
            # coords[0]: x_center, coords[1]: y_center, coords[2]: width, coords[3]: height
            bbox = coords[:4]
            if any(val < 0.0 or val > 1.0 for val in bbox):
                print(f"[WARNING] {label_path} Line {line_num}: bbox coordinates out of [0, 1] range: {bbox}")
                out_of_range_coords += 1
                
            # Check keypoints
            # coords[4:]: [x1, y1, v1, x2, y2, v2, x3, y3, v3]
            kpts = coords[4:]
            # Ensure keypoint visibility matches 0, 1, or 2
            for kp_idx in range(3):
                vis_val = int(kpts[kp_idx * 3 + 2])
                if vis_val not in (0, 1, 2):
                    print(f"[ERROR] {label_path} Line {line_num}: invalid keypoint visibility {vis_val}")
                    label_valid = False
                    
                kp_x = kpts[kp_idx * 3]
                kp_y = kpts[kp_idx * 3 + 1]
                # Keypoint coordinates should be normalized (usually [0, 1])
                # However, if keypoint is not visible (visibility = 0), coordinates are often 0.0
                if vis_val > 0 and (kp_x < 0.0 or kp_x > 1.0 or kp_y < 0.0 or kp_y > 1.0):
                    print(f"[WARNING] {label_path} Line {line_num}: keypoint {kp_idx} out of [0, 1] range: ({kp_x}, {kp_y})")
                    out_of_range_coords += 1
        
    print(f"Split {split_name} Validation Summary:")
    print(f"  Valid images: {valid_images}/{total_images}")
    print(f"  Corrupt images: {corrupt_images}")
    print(f"  Missing label files: {missing_labels}")
    print(f"  Invalid labels: {invalid_labels}")
    print(f"  Out of range coordinates flagged: {out_of_range_coords}")
    
    return corrupt_images == 0 and missing_labels == 0 and invalid_labels == 0

def main():
    yaml_path = "datasets/pose/data.yaml"
    if not os.path.exists(yaml_path):
        print(f"[ERROR] data.yaml not found at: {yaml_path}")
        return
        
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
        
    base_path = data.get("path", "")
    train_img_rel = data.get("train", "")
    val_img_rel = data.get("val", "")
    
    train_img_dir = os.path.join(base_path, train_img_rel)
    train_lbl_dir = train_img_dir.replace("images", "labels")
    
    val_img_dir = os.path.join(base_path, val_img_rel)
    val_lbl_dir = val_img_dir.replace("images", "labels")
    
    # Run validations
    train_ok = validate_split("train", train_img_dir, train_lbl_dir)
    val_ok = validate_split("val", val_img_dir, val_lbl_dir)
    
    if train_ok and val_ok:
        print("\n[SUCCESS] Dataset is ready and fully valid for YOLOv8-pose training!")
    else:
        print("\n[FAILED] Dataset has issues. Please fix them before training.")

if __name__ == "__main__":
    main()
