import argparse
import json
import os
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
from torchvision.datasets import ImageFolder

from plant_classifier import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    build_eval_transform,
    build_model,
)

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

def _dir_has_images(d: Path) -> bool:
    try:
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in IMG_EXT:
                return True
    except OSError:
        pass
    return False

def find_dataset_root(base: Path) -> Path:
    candidates: list[Path] = [base]
    for depth1 in [p for p in base.iterdir() if p.is_dir()]:
        candidates.append(depth1)
        candidates.extend([p for p in depth1.iterdir() if p.is_dir()])

    best: tuple[Path, int] | None = None
    for d in candidates:
        subdirs = [s for s in d.iterdir() if s.is_dir()]
        if len(subdirs) < 5:
            continue
        with_images = sum(1 for s in subdirs if _dir_has_images(s))
        if with_images >= len(subdirs) * 0.8:
            if best is None or with_images > best[1]:
                best = (d, with_images)

    if best is None:
        raise RuntimeError(f"Не вдалося знайти теки класів усередині {base}")
    return best[0]

def build_train_transform(img_size: int):
    return transforms.Compose(
        [
            transforms.RandomResizedCrop(img_size, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


def make_datasets(root: Path, img_size: int, val_split: float, seed: int):
    train_full = ImageFolder(root, transform=build_train_transform(img_size))
    val_full = ImageFolder(root, transform=build_eval_transform(img_size))

    n = len(train_full)
    n_val = int(n * val_split)
    generator = torch.Generator().manual_seed(seed)
    perm = torch.randperm(n, generator=generator).tolist()

    train_ds = Subset(train_full, perm[n_val:])
    val_ds = Subset(val_full, perm[:n_val])
    return train_ds, val_ds, train_full.classes

def run_epoch(model, loader, criterion, optimizer, device, train: bool):
    model.train() if train else model.eval()
    total_loss, correct, total = 0.0, 0, 0

    with torch.set_grad_enabled(train):
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)

            outputs = model(images)
            loss = criterion(outputs, labels)

            if train:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            total_loss += loss.item() * labels.size(0)
            correct += (outputs.argmax(1) == labels).sum().item()
            total += labels.size(0)

    return total_loss / total, correct / total

def pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", default="efficientnet_b0",
                        choices=["efficientnet_b0", "mobilenet_v3_large"])
    parser.add_argument("--img-size", type=int, default=224)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--head-epochs", type=int, default=2,
                        help="епохи з замороженим backbone")
    parser.add_argument("--epochs", type=int, default=6,
                        help="епохи fine-tuning усієї мережі")
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", default=None,
                        help="локальний шлях до датасету (пропустити завантаження)")
    parser.add_argument("--out", default="models/plant_classifier.pt")
    args = parser.parse_args()

    torch.manual_seed(args.seed)

    # 1. Датасет
    if args.data_dir:
        base = Path(args.data_dir)
    else:
        import kagglehub
        base = Path(kagglehub.dataset_download(
            "kacpergregorowicz/house-plant-species"))
    print(f"Датасет: {base}")

    root = find_dataset_root(base)
    print(f"Корінь класів: {root}")

    train_ds, val_ds, classes = make_datasets(
        root, args.img_size, args.val_split, args.seed
    )
    print(f"Класів: {len(classes)} | train: {len(train_ds)} | val: {len(val_ds)}")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=args.workers, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            num_workers=args.workers, pin_memory=True)

    device = pick_device()
    model = build_model(args.arch, len(classes), pretrained=True).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    best_acc = 0.0

    def save(acc: float) -> None:
        torch.save(
            {
                "state_dict": model.state_dict(),
                "classes": classes,
                "arch": args.arch,
                "img_size": args.img_size,
                "val_accuracy": acc,
            },
            out_path,
        )

    backbone = model.features
    for p in backbone.parameters():
        p.requires_grad = False

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=1e-3
    )
    for epoch in range(args.head_epochs):
        tr_loss, tr_acc = run_epoch(model, train_loader, criterion, optimizer, device, True)
        va_loss, va_acc = run_epoch(model, val_loader, criterion, None, device, False)
        print(f"[head {epoch + 1}/{args.head_epochs}] "
              f"train {tr_loss:.3f}/{tr_acc:.3f} | val {va_loss:.3f}/{va_acc:.3f}")
        if va_acc > best_acc:
            best_acc = va_acc
            save(best_acc)

    for p in backbone.parameters():
        p.requires_grad = True

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(args.epochs, 1))

    for epoch in range(args.epochs):
        tr_loss, tr_acc = run_epoch(model, train_loader, criterion, optimizer, device, True)
        va_loss, va_acc = run_epoch(model, val_loader, criterion, None, device, False)
        scheduler.step()
        print(f"[ft {epoch + 1}/{args.epochs}] "
              f"train {tr_loss:.3f}/{tr_acc:.3f} | val {va_loss:.3f}/{va_acc:.3f}")
        if va_acc > best_acc:
            best_acc = va_acc
            save(best_acc)
            print(f"  -> збережено (val acc {best_acc:.3f})")

    with open(out_path.parent / "classes.json", "w", encoding="utf-8") as f:
        json.dump(classes, f, ensure_ascii=False, indent=2)

    print(f"\nГотово. Найкраща val accuracy: {best_acc:.3f}")
    print(f"Модель: {out_path}")


if __name__ == "__main__":
    main()