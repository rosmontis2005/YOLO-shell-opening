from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_device(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the YOLO detector.")
    parser.add_argument(
        "--model",
        default=str(PROJECT_ROOT / "yolo26n.pt"),
        help="Base model or checkpoint path.",
    )
    parser.add_argument(
        "--data",
        default=str(PROJECT_ROOT / "data.yaml"),
        help="Dataset YAML path.",
    )
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Keep low on Windows to avoid dataloader issues.",
    )
    parser.add_argument(
        "--device",
        default="0",
        help='Ultralytics device, e.g. "0" for first CUDA GPU or "cpu".',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=parse_device(args.device),
    )


if __name__ == "__main__":
    main()
