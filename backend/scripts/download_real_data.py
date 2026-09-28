import os
import shutil
import kagglehub

def download_and_map():
    print("=== DOWNLOADING REAL DENTAL DATASETS FROM KAGGLE ===")
    
    datasets = [
        "imtkaggleteam/dental-radiography",
        "lokisilvres/dental-disease-panoramic-detection-dataset"
    ]
    
    # Setup Local Structure
    dirs = {
        'train_img': "datasets/detection/yolo_train/images",
        'train_lbl': "datasets/detection/yolo_train/labels",
        'val_img': "datasets/detection/yolo_val/images",
        'val_lbl': "datasets/detection/yolo_val/labels",
        'all_images': "datasets/detection/images"
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    img_ext = ('.jpg', '.jpeg', '.png')
    lbl_ext = ('.txt')
    counts = {'images': 0, 'labels': 0}

    for dataset_id in datasets:
        print(f"\n--- Processing {dataset_id} ---")
        try:
            path = kagglehub.dataset_download(dataset_id)
            print(f"Dataset downloaded to: {path}")
            
            # Mapping Kaggle folders to our local folders
            mapping = {
                'train': ('train_img', 'train_lbl'),
                'valid': ('val_img', 'val_lbl'),
                'test': ('val_img', 'val_lbl')
            }
            
            found_mapped = False
            for k_folder, (img_key, lbl_key) in mapping.items():
                k_path = os.path.join(path, k_folder)
                if not os.path.exists(k_path):
                    continue
                
                found_mapped = True
                print(f"  Mapping {k_folder} folder...")
                
                for f in os.listdir(k_path):
                    src = os.path.join(k_path, f)
                    if os.path.isdir(src): continue
                    
                    if f.lower().endswith(img_ext):
                        shutil.copy2(src, os.path.join(dirs[img_key], f))
                        shutil.copy2(src, os.path.join(dirs['all_images'], f))
                        counts['images'] += 1
                    elif f.lower().endswith(lbl_ext) and f != 'classes.txt':
                        shutil.copy2(src, os.path.join(dirs[lbl_key], f))
                        counts['labels'] += 1

            # Fallback if no train/valid/test structure (just scan root)
            if not found_mapped:
                print("  No train/valid structure found. Scanning root directory...")
                for root, _, files in os.walk(path):
                    for f in files:
                        src = os.path.join(root, f)
                        if f.lower().endswith(img_ext):
                            shutil.copy2(src, os.path.join(dirs['train_img'], f))
                            shutil.copy2(src, os.path.join(dirs['all_images'], f))
                            counts['images'] += 1
                        elif f.lower().endswith(lbl_ext) and f != 'classes.txt':
                            shutil.copy2(src, os.path.join(dirs['train_lbl'], f))
                            counts['labels'] += 1

        except Exception as e:
            print(f"  Error processing {dataset_id}: {e}")

    print(f"\nSUCCESS: Imported {counts['images']} total images and {counts['labels']} labels.")
    print(f"Data is organized in 'datasets/detection/yolo_train' and 'datasets/detection/yolo_val'.")
    print("\nRun: python models/train_tooth_detection.py to start training on real data!")

if __name__ == "__main__":
    download_and_map()
