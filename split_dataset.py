"""
Move 20% of annotated images (and their label .txt files) from train to val.
Run once after labelling:  python split_dataset.py
"""
import random
import shutil
from pathlib import Path

ROOT = Path("custom_dataset")
IMG_TRAIN, IMG_VAL = ROOT / "images/train", ROOT / "images/val"
LBL_TRAIN, LBL_VAL = ROOT / "labels/train", ROOT / "labels/val"
VAL_RATIO = 0.20
random.seed(42)

for d in (IMG_VAL, LBL_VAL):
    d.mkdir(parents=True, exist_ok=True)

images = [p for p in IMG_TRAIN.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
images = [p for p in images if (LBL_TRAIN / f"{p.stem}.txt").exists()]  # only labelled images
random.shuffle(images)
n_val = max(1, int(len(images) * VAL_RATIO))

for img in images[:n_val]:
    shutil.move(str(img), IMG_VAL / img.name)
    shutil.move(str(LBL_TRAIN / f"{img.stem}.txt"), LBL_VAL / f"{img.stem}.txt")

print(f"Moved {n_val} images to val, {len(images) - n_val} remain in train.")
print("Check that BOTH classes (helmet, no_helmet) appear in the val labels!")
