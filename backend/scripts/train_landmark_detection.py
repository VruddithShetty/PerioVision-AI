import os
import sys
import time
import csv
import copy
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from pathlib import Path

# Ensure utilities is in the path to import DentalDatasetLoader
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from utilities.dataset_loader import DentalDatasetLoader, DentalTorchDataset
except ImportError:
    print("Error: Could not import DentalDatasetLoader.")
    sys.exit(1)


# ─── ADVANCED LOSS FUNCTIONS ──────────────────────────────────────────────────

class WingLoss(nn.Module):
    def __init__(self, w=10, epsilon=2):
        super(WingLoss, self).__init__()
        self.w = w
        self.epsilon = epsilon
        self.C = self.w - self.w * np.log(1 + self.w / self.epsilon)

    def forward(self, predictions, targets):
        x = predictions - targets
        absolute_x = torch.abs(x)
        losses = torch.where(
            absolute_x < self.w,
            self.w * torch.log(1 + absolute_x / self.epsilon),
            absolute_x - self.C
        )
        return torch.mean(losses)


# ─── DEEPER ARCHITECTURE ──────────────────────────────────────────────────────

class LandmarkCNN(nn.Module):
    def __init__(self):
        super(LandmarkCNN, self).__init__()
        
        # Input: 1 x 128 x 128
        self.features = nn.Sequential(
            # Block 1
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(32, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.LeakyReLU(0.1, inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2), # 64x64
            
            # Block 2
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(64, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(0.1, inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2), # 32x32
            
            # Block 3
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(128, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(0.1, inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2), # 16x16
            
            # Block 4
            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(0.1, inplace=True),
            nn.AdaptiveAvgPool2d((4, 4))           # 4x4
        )
        
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(256 * 4 * 4, 1024),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Dropout(0.3),
            nn.Linear(1024, 512),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Dropout(0.3),
            nn.Linear(512, 6),
            nn.Sigmoid()
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x


# ─── TRAINING LOGIC ───────────────────────────────────────────────────────────

def compute_med(preds, targets, img_size=128):
    """
    Compute Mean Euclidean Distance (MED) in pixels.
    preds and targets are normalized to [0, 1].
    """
    # Reshape from (B, 6) to (B, 3, 2) to compute distance for each point (cej, apex, crest)
    b_size = preds.size(0)
    p = preds.view(b_size, 3, 2) * img_size
    t = targets.view(b_size, 3, 2) * img_size
    
    # Euclidean distance per point: sqrt((x1-x2)^2 + (y1-y2)^2)
    distances = torch.sqrt(torch.sum((p - t) ** 2, dim=2))
    
    # Mean across all points and batch
    return torch.mean(distances).item()

def train_model():
    # Configuration
    epochs = 150
    batch_size = 16
    learning_rate = 1e-3
    patience_limit = 20
    model_dir = 'weights/landmark_detection_model'
    os.makedirs(model_dir, exist_ok=True)
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Training on device: {device}")
    
    # 1. Load Data
    loader = DentalDatasetLoader()
    print("Loading data...")
    # Attempt custom load, fallback to synthetic
    samples = loader.load_custom('datasets/detection/sample_annotations.csv', 'datasets/detection/images/')
    if not samples:
        print("Using synthetic data for training (no custom dataset found).")
        samples = loader.generate_synthetic(n=500)
    
    train_samples, val_samples, _ = loader.split(samples)
    
    train_dataset = DentalTorchDataset(train_samples, augment=True, loader=loader)
    val_dataset = DentalTorchDataset(val_samples, augment=False, loader=loader)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    print(f"Train samples: {len(train_samples)} | Val samples: {len(val_samples)}")
    
    # 2. Initialize Model & Training Components
    model = LandmarkCNN().to(device)
    
    # Wing Loss (more sensitive to small errors in landmark detection)
    criterion = WingLoss(w=10, epsilon=2)
    optimizer = optim.Adam(model.parameters(), lr=learning_rate, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=8, factor=0.5)
    
    # Logging & Checkpointing
    log_path = os.path.join(model_dir, 'training_log.csv')
    checkpoint_path = os.path.join(model_dir, 'landmark_checkpoint.pt')
    best_med = float('inf')
    start_epoch = 1
    patience_counter = 0

    # Resume if checkpoint exists
    if os.path.exists(checkpoint_path):
        print(f"Found checkpoint at {checkpoint_path}. Resuming...")
        checkpoint = torch.load(checkpoint_path)
        model.load_state_dict(checkpoint['model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        start_epoch = checkpoint['epoch'] + 1
        best_med = checkpoint['best_med']
        print(f"Resuming from Epoch {start_epoch}")
    
    best_model_wts = copy.deepcopy(model.state_dict())
    
    with open(log_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['epoch', 'train_loss', 'val_loss', 'val_med_pixels'])
        
        # 3. Training Loop
        for epoch in range(start_epoch, epochs + 1):
            # --- TRAIN PHASE ---
            model.train()
            running_loss = 0.0
            
            for inputs, targets, _ in train_loader:
                # Resize input from 512x512 to 128x128 inside the loop dynamically
                import torch.nn.functional as F
                inputs = F.interpolate(inputs, size=(128, 128), mode='bilinear', align_corners=False)
                
                inputs = inputs.to(device)
                targets = targets.to(device)
                
                optimizer.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs, targets)
                loss.backward()
                optimizer.step()
                
                running_loss += loss.item() * inputs.size(0)
                
            epoch_loss = running_loss / len(train_samples)
            
            # --- VAL PHASE ---
            model.eval()
            val_loss = 0.0
            val_med = 0.0
            
            with torch.no_grad():
                for inputs, targets, _ in val_loader:
                    inputs = F.interpolate(inputs, size=(128, 128), mode='bilinear', align_corners=False)
                    inputs = inputs.to(device)
                    targets = targets.to(device)
                    
                    outputs = model(inputs)
                    loss = criterion(outputs, targets)
                    
                    val_loss += loss.item() * inputs.size(0)
                    
                    # Compute MED (Mean Euclidean Distance)
                    med_batch = compute_med(outputs, targets, img_size=128)
                    val_med += med_batch * inputs.size(0)
                    
            epoch_val_loss = val_loss / len(val_samples)
            epoch_val_med = val_med / len(val_samples)
            
            # Log & Print
            writer.writerow([epoch, epoch_loss, epoch_val_loss, epoch_val_med])
            print(f"Epoch {epoch}/{epochs} | Train Loss: {epoch_loss:.4f} | Val Loss: {epoch_val_loss:.4f} | Val MED: {epoch_val_med:.2f}px")
            
            # Step Scheduler
            scheduler.step(epoch_val_med)
            
            # Check for improvement
            # Save checkpoint every epoch for resuming
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'best_med': best_med,
            }, checkpoint_path)

            if epoch_val_med < best_med:
                best_med = epoch_val_med
                best_model_wts = copy.deepcopy(model.state_dict())
                patience_counter = 0
                torch.save(model.state_dict(), os.path.join(model_dir, 'landmark_cnn.pt'))
                print(f"  -> Saved new best model (MED: {best_med:.2f}px)")
            else:
                patience_counter += 1
                
            # Early Stopping
            if patience_counter >= patience_limit:
                print(f"\nEarly stopping triggered at epoch {epoch}")
                break

    print(f"\nTraining Complete. Best Val MED: {best_med:.2f}px")
    
    # 4. Export to ONNX
    print("Exporting model to ONNX...")
    model.load_state_dict(best_model_wts)
    model.eval()
    model.to('cpu')
    
    dummy_input = torch.randn(1, 1, 128, 128, device='cpu')
    onnx_path = os.path.join(model_dir, 'landmark_cnn.onnx')
    
    torch.onnx.export(
        model, 
        dummy_input, 
        onnx_path, 
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={'input': {0: 'batch_size'}, 'output': {0: 'batch_size'}}
    )
    print(f"Saved ONNX model to: {onnx_path}")


# ─── SMOKE TEST ───────────────────────────────────────────────────────────────

def run_smoke_test():
    print("\n--- Running Smoke Test ---")
    model = LandmarkCNN()
    model.eval()
    
    dummy_input = torch.randn(1, 1, 128, 128)
    with torch.no_grad():
        out = model(dummy_input)
    
    # Check shape
    assert out.shape == (1, 6), f"Expected shape (1, 6), got {out.shape}"
    
    # Check bounds
    values = out[0].tolist()
    assert all(0 <= v <= 1 for v in values), f"Outputs out of [0, 1] range: {values}"
    
    # Check param count
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Total Parameters: {total_params:,} (Target < 10M)")
    assert total_params < 10000000, "Model is too large!"
    
    print("Landmark CNN smoke test passed successfully.")


if __name__ == '__main__':
    run_smoke_test()
    print("\n")
    train_model()
