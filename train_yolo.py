"""
EMFOX OMS — Entrenador YOLOv8-nano para Smart Crop
====================================================
Optimizado para: i7 10ma gen + 32GB RAM + MX230 2GB VRAM

Uso local:
    python3 train_yolo.py --data ~/Escritorio/FOX_TRAIN_DATA --epochs 50

Uso Colab:
    python3 train_yolo.py --prepare-colab  (genera zip para subir)

Restricciones:
    - Batch size alto en CPU/RAM (aprovecha 32GB)
    - GPU limitada al 30% para no calentar
    - Si >3h estimadas, genera zip para Colab
"""

import argparse
import os
import shutil
import time
from pathlib import Path


def prepare_dataset(data_dir: str, synthetic_dir: str = None):
    """Merge real + synthetic data into YOLO format dataset."""
    data_path = Path(data_dir)
    output = data_path / "merged_dataset"
    
    for split in ["train", "val"]:
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    real_images = list((data_path / "images").glob("*.jpg"))
    real_labels = list((data_path / "labels").glob("*.txt"))
    
    print(f"Real images: {len(real_images)}")
    print(f"Real labels: {len(real_labels)}")

    # Split 80/20
    split_idx = max(1, int(len(real_images) * 0.8))
    
    for i, img in enumerate(real_images):
        split = "train" if i < split_idx else "val"
        shutil.copy2(img, output / "images" / split / img.name)
        label = data_path / "labels" / f"{img.stem}.txt"
        if label.exists():
            shutil.copy2(label, output / "labels" / split / label.name)

    # Add synthetic data if available
    if synthetic_dir and Path(synthetic_dir).exists():
        syn = Path(synthetic_dir)
        for split in ["train", "val"]:
            syn_imgs = list((syn / "images" / split).glob("*.jpg"))
            for img in syn_imgs:
                shutil.copy2(img, output / "images" / split / img.name)
                label = syn / "labels" / split / f"{img.stem}.txt"
                if label.exists():
                    shutil.copy2(label, output / "labels" / split / label.name)
        print(f"Synthetic data added from {synthetic_dir}")

    # Count final
    train_imgs = len(list((output / "images" / "train").glob("*")))
    val_imgs = len(list((output / "images" / "val").glob("*")))
    
    # Write dataset.yaml
    yaml = f"""path: {output.resolve()}
train: images/train
val: images/val

nc: 1
names: ['product']

# EMFOX OMS Training Dataset
# Real: {len(real_images)} images | Synthetic: {train_imgs + val_imgs - len(real_images)}
# Generated: {time.strftime('%Y-%m-%d %H:%M')}
"""
    (output / "dataset.yaml").write_text(yaml)
    
    print(f"\nDataset ready: {train_imgs} train + {val_imgs} val")
    print(f"Config: {output / 'dataset.yaml'}")
    return str(output / "dataset.yaml")


def estimate_training_time(n_images: int, epochs: int = 50):
    """Estimate training time based on hardware."""
    # Rough estimates for YOLOv8n
    sec_per_epoch_cpu = n_images * 0.3  # ~0.3s per image on i7 CPU
    sec_per_epoch_gpu = n_images * 0.05  # ~0.05s per image on MX230
    
    total_cpu = sec_per_epoch_cpu * epochs
    total_gpu = sec_per_epoch_gpu * epochs
    
    return {
        "cpu_hours": round(total_cpu / 3600, 1),
        "gpu_hours": round(total_gpu / 3600, 1),
        "colab_minutes": round(n_images * 0.01 * epochs / 60, 0),  # T4 GPU
        "recommend_colab": total_cpu > 10800,  # >3 hours
    }


def prepare_colab_zip(data_dir: str, synthetic_dir: str = None):
    """Create a zip file ready to upload to Google Colab."""
    yaml_path = prepare_dataset(data_dir, synthetic_dir)
    dataset_dir = Path(yaml_path).parent
    
    zip_path = Path(data_dir) / "colab_dataset"
    shutil.make_archive(str(zip_path), 'zip', str(dataset_dir))
    
    colab_notebook = f"""# EMFOX OMS — YOLOv8 Training (Google Colab)
# Upload colab_dataset.zip first, then run all cells

# Cell 1: Setup
!pip install ultralytics
from google.colab import files
import zipfile

# Cell 2: Upload and extract
uploaded = files.upload()  # Upload colab_dataset.zip
with zipfile.ZipFile('colab_dataset.zip', 'r') as z:
    z.extractall('dataset')

# Cell 3: Train
from ultralytics import YOLO
model = YOLO('yolov8n.pt')  # nano model
results = model.train(
    data='dataset/dataset.yaml',
    epochs=50,
    imgsz=640,
    batch=16,
    device=0,  # GPU
    workers=2,
    patience=15,
    save=True,
    name='emfox_crop'
)

# Cell 4: Download best model
files.download('runs/detect/emfox_crop/weights/best.pt')
# This ~6MB file goes into your OMS backend
"""
    (Path(data_dir) / "colab_training.py").write_text(colab_notebook)
    
    print(f"\n📦 Colab package ready:")
    print(f"   Zip: {zip_path}.zip")
    print(f"   Notebook: {Path(data_dir) / 'colab_training.py'}")
    print(f"\n🚀 Upload to Colab → Run all cells → Download best.pt")


def train_local(yaml_path: str, epochs: int = 50, device: str = "cpu"):
    """Train YOLOv8n locally."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics not installed. Run: pip install ultralytics")
        print("   Or use --prepare-colab to train on Google Colab (free GPU)")
        return None
    
    model = YOLO('yolov8n.pt')
    
    # Optimized for i7 + 32GB RAM + limited GPU
    train_args = {
        "data": yaml_path,
        "epochs": epochs,
        "imgsz": 640,
        "device": device,
        "workers": 4,
        "patience": 15,
        "save": True,
        "name": "emfox_crop",
        "verbose": True,
    }
    
    if device == "cpu":
        train_args["batch"] = 32  # High batch, lots of RAM
    else:
        train_args["batch"] = 8   # Low batch for 2GB VRAM
    
    print(f"\n🚀 Training YOLOv8-nano on {device}")
    print(f"   Epochs: {epochs}, Batch: {train_args['batch']}, ImgSize: 640")
    
    results = model.train(**train_args)
    
    best_path = Path("runs/detect/emfox_crop/weights/best.pt")
    if best_path.exists():
        # Copy to OMS backend
        oms_model = Path(__file__).parent / "backend" / "models" / "emfox_crop.pt"
        oms_model.parent.mkdir(exist_ok=True)
        shutil.copy2(best_path, oms_model)
        print(f"\n✅ Model saved: {oms_model} ({oms_model.stat().st_size / 1024:.0f} KB)")
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EMFOX YOLOv8 Trainer")
    parser.add_argument("--data", default=os.path.expanduser("~/Escritorio/FOX_TRAIN_DATA"))
    parser.add_argument("--synthetic", default="./dataset")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--device", default="cpu", choices=["cpu", "0"])
    parser.add_argument("--prepare-colab", action="store_true")
    parser.add_argument("--estimate", action="store_true")
    args = parser.parse_args()

    if args.estimate:
        real = len(list(Path(args.data, "images").glob("*"))) if Path(args.data, "images").exists() else 0
        syn = len(list(Path(args.synthetic, "images/train").glob("*"))) if Path(args.synthetic).exists() else 0
        total = real + syn
        est = estimate_training_time(total, args.epochs)
        print(f"Images: {total} ({real} real + {syn} synthetic)")
        print(f"CPU: ~{est['cpu_hours']}h | GPU: ~{est['gpu_hours']}h | Colab: ~{est['colab_minutes']}min")
        if est['recommend_colab']:
            print("⚠️ Recomendado usar Colab (>3h local)")
    elif args.prepare_colab:
        prepare_colab_zip(args.data, args.synthetic)
    else:
        yaml_path = prepare_dataset(args.data, args.synthetic)
        train_local(yaml_path, args.epochs, args.device)
