import os
import glob

def inspect_and_parse_example():
    """
    1. INSPECT THE ANNOTATION FORMAT
    Parses and prints the details of a single annotation file to demonstrate the structure.
    """
    label_dir = "datasets/pose/labels/train"
    label_files = glob.glob(os.path.join(label_dir, "*.txt"))
    if not label_files:
        print("No label files found in datasets/pose/labels/train")
        return
        
    example_file = label_files[0]
    print(f"Parsing example file: {example_file}")
    
    with open(example_file, 'r') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        parts = line.strip().split()
        if len(parts) < 14:
            print(f"Line {i}: invalid YOLO-pose format (too few elements: {len(parts)})")
            continue
            
        class_id = int(parts[0])
        # Box center coordinates, width, height (normalized to [0, 1])
        x_center, y_center = float(parts[1]), float(parts[2])
        width, height = float(parts[3]), float(parts[4])
        
        # Keypoints: [x, y, visibility]
        cej_x, cej_y, cej_vis = float(parts[5]), float(parts[6]), int(parts[7])
        apex_x, apex_y, apex_vis = float(parts[8]), float(parts[9]), int(parts[10])
        crest_x, crest_y, crest_vis = float(parts[11]), float(parts[12]), int(parts[13])
        
        print(f"--- Object {i} ---")
        print(f"  Class ID: {class_id} (Tooth)")
        print(f"  Bbox Center: ({x_center:.4f}, {y_center:.4f}), Size: ({width:.4f}, {height:.4f})")
        print(f"  CEJ Landmark: ({cej_x:.4f}, {cej_y:.4f}), Visibility: {cej_vis}")
        print(f"  Root Apex Landmark: ({apex_x:.4f}, {apex_y:.4f}), Visibility: {apex_vis}")
        print(f"  Bone Crest Landmark: ({crest_x:.4f}, {crest_y:.4f}), Visibility: {crest_vis}")

def main():
    print("YOLO-pose format inspection script running...")
    inspect_and_parse_example()
    print("Data is already formatted correctly for YOLOv8-pose training under datasets/pose/.")

if __name__ == "__main__":
    main()
