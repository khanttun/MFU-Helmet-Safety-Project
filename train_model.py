"""
Train the custom helmet / no_helmet YOLO model (as in the Training a Custom YOLO Model lab).
Run from the helmet_project folder:  python train_model.py
Result: custom_dataset/runs/detect/custom_model/train_result/weights/best.pt
"""
from ultralytics import YOLO

model = YOLO("custom_dataset/model/yolo11n.pt")  # base model (downloaded if file is missing)

model.train(
    data="custom_dataset/dataset.yaml",
    epochs=100,
    imgsz=640,
    batch=16,          # lower to 8 if you run out of memory
    patience=30,       # early stop if no improvement
    project="custom_dataset/runs/detect/custom_model",
    name="train_result",
    exist_ok=True,
)

print("Training Completed! Check 'custom_dataset/runs/detect/custom_model/train_result/weights' for best.pt")
