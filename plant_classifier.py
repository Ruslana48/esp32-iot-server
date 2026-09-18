import io
import threading
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.models import efficientnet_b0, mobilenet_v3_large

from config import MODEL_PATH

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

_lock = threading.Lock()
_state: dict | None = None

def _pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

def build_model(arch: str, num_classes: int, pretrained: bool = False):
    if arch == "efficientnet_b0":
        weights = "DEFAULT" if pretrained else None
        model = efficientnet_b0(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = torch.nn.Linear(in_features, num_classes)
    elif arch == "mobilenet_v3_large":
        weights = "DEFAULT" if pretrained else None
        model = mobilenet_v3_large(weights=weights)
        in_features = model.classifier[3].in_features
        model.classifier[3] = torch.nn.Linear(in_features, num_classes)
    else:
        raise ValueError(f"Невідома архітектура: {arch}")
    return model


def build_eval_transform(img_size: int = 224):
    return transforms.Compose(
        [
            transforms.Resize(int(img_size * 1.14)),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )

def _load() -> dict:
    global _state
    with _lock:
        if _state is not None:
            return _state

        path = Path(MODEL_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"Файл моделі не знайдено: {path}. "
                "Спочатку навчіть модель: python train_classifier.py"
            )

        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        classes = ckpt["classes"]
        arch = ckpt.get("arch", "efficientnet_b0")
        img_size = ckpt.get("img_size", 224)

        model = build_model(arch, len(classes), pretrained=False)
        model.load_state_dict(ckpt["state_dict"])
        model.eval()

        device = _pick_device()
        model.to(device)

        _state = {
            "model": model,
            "classes": classes,
            "device": device,
            "transform": build_eval_transform(img_size),
        }
        print(f"Модель завантажено: {arch}, {len(classes)} класів, {device}", flush=True)
        return _state

def is_ready() -> bool:
    return Path(MODEL_PATH).exists()

def predict(image_bytes: bytes, top_k: int = 3) -> list[tuple[str, float]]:
    state = _load()

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = state["transform"](image).unsqueeze(0).to(state["device"])

    with torch.no_grad():
        logits = state["model"](tensor)
        probs = F.softmax(logits, dim=1)[0]

    k = min(top_k, len(state["classes"]))
    values, indices = torch.topk(probs, k)
    return [
        (state["classes"][i], float(v))
        for v, i in zip(values.cpu(), indices.cpu())
    ]