from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(PROJECT_ROOT / ".ultralytics"))

import cv2
from ultralytics import YOLO


def run_detection(camera_index: int, conf: float) -> dict:
    weights_candidates = sorted(
        (PROJECT_ROOT / "runs" / "detect").glob("train*/weights/best.pt"),
        key=lambda p: p.stat().st_mtime,
    )
    if not weights_candidates:
        raise FileNotFoundError("best.pt was not found. Please train the model first.")

    model = YOLO(str(weights_candidates[-1]))

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {camera_index}")

    ok, image = cap.read()
    cap.release()
    if not ok or image is None:
        raise RuntimeError(f"Cannot read frame from camera {camera_index}")

    shot_dir = PROJECT_ROOT / "shot"
    shot_dir.mkdir(parents=True, exist_ok=True)
    input_shot_path = shot_dir / f"camera{camera_index}_input.jpg"
    cv2.imwrite(str(input_shot_path), image)

    results = model.predict(source=image, show=False, save=False, conf=conf, verbose=False)

    response = {
        "detected": False,
        "x_center": None,
        "confidence": None,
        "camera_index": camera_index,
        "input_frame": str(input_shot_path),
        "output_frame": None,
    }

    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        return response

    confs = result.boxes.conf
    max_idx = int(confs.argmax().item())
    xyxy = result.boxes.xyxy[max_idx].tolist()
    x1, y1, x2, y2 = [int(v) for v in xyxy]
    x_center = (x1 + x2) / 2.0

    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        image,
        f"conf={float(confs[max_idx]):.3f}",
        (x1, max(0, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2,
    )

    out_dir = PROJECT_ROOT / "runs" / "detect" / "predict_best"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"camera{camera_index}.jpg"
    cv2.imwrite(str(out_path), image)

    response["detected"] = True
    response["x_center"] = round(x_center, 2)
    response["confidence"] = round(float(confs[max_idx]), 4)
    response["output_frame"] = str(out_path)
    return response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture one frame and run YOLO detection."
    )
    parser.add_argument("--camera-index", type=int, default=1)
    parser.add_argument("--conf", type=float, default=0.1)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_detection(camera_index=args.camera_index, conf=args.conf)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return

    if not result["detected"]:
        print("No target detected")
        print(f"Input frame saved to: {result['input_frame']}")
        return

    print(f"Target detected, x={result['x_center']:.2f}")
    print(f"Confidence: {result['confidence']:.4f}")
    print(f"Output saved to: {result['output_frame']}")
    print(f"Input frame saved to: {result['input_frame']}")


if __name__ == "__main__":
    main()

