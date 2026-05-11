from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("YOLO_CONFIG_DIR", str(PROJECT_ROOT / ".ultralytics"))

import cv2
from ultralytics import YOLO

from common import stepper_control


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")


def find_latest_weights() -> Path:
    weights_candidates = sorted(
        (PROJECT_ROOT / "runs" / "detect").glob("train*/weights/best.pt"),
        key=lambda p: p.stat().st_mtime,
    )
    if not weights_candidates:
        raise FileNotFoundError("best.pt was not found. Please train the model first.")

    return weights_candidates[-1]


def open_camera(camera_index: int):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot open camera {camera_index}")
    return cap


def annotate_and_save(
    image,
    camera_index: int,
    result,
    max_idx: int,
    confidence: float,
) -> str:
    xyxy = result.boxes.xyxy[max_idx].tolist()
    x1, y1, x2, y2 = [int(v) for v in xyxy]

    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        image,
        f"conf={confidence:.3f}",
        (x1, max(0, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2,
    )

    out_dir = PROJECT_ROOT / "runs" / "detect" / "predict_loop"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"camera{camera_index}.jpg"
    cv2.imwrite(str(out_path), image)
    return str(out_path)


def detect_frame(
    model: YOLO,
    image,
    camera_index: int,
    conf: float,
    device: str | None,
) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_dir = PROJECT_ROOT / "shot"
    shot_dir.mkdir(parents=True, exist_ok=True)
    input_shot_path = shot_dir / f"camera{camera_index}_loop_input.jpg"
    cv2.imwrite(str(input_shot_path), image)

    predict_kwargs = {
        "source": image,
        "show": False,
        "save": False,
        "conf": conf,
        "verbose": False,
    }
    if device:
        predict_kwargs["device"] = device

    results = model.predict(**predict_kwargs)

    response = {
        "detected": False,
        "x_center": None,
        "confidence": None,
        "camera_index": camera_index,
        "timestamp": timestamp,
        "input_frame": str(input_shot_path),
        "output_frame": None,
        "stepper_position": None,
        "stepper_command": None,
        "arduino_replies": [],
    }

    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        return response

    confs = result.boxes.conf
    max_idx = int(confs.argmax().item())
    xyxy = result.boxes.xyxy[max_idx].tolist()
    x1, _, x2, _ = [int(v) for v in xyxy]
    x_center = (x1 + x2) / 2.0
    confidence = float(confs[max_idx])

    response["detected"] = True
    response["x_center"] = round(x_center, 2)
    response["confidence"] = round(confidence, 4)
    response["output_frame"] = annotate_and_save(
        image=image,
        camera_index=camera_index,
        result=result,
        max_idx=max_idx,
        confidence=confidence,
    )
    return response


def log(message: str, json_mode: bool) -> None:
    print(message, file=sys.stderr if json_mode else sys.stdout, flush=True)


def maybe_send_to_stepper(
    args: argparse.Namespace,
    result: dict,
    serial_client: stepper_control.StepperSerialClient | None,
) -> None:
    if not result["detected"]:
        return

    raw_position = stepper_control.camera_x_to_stepper_position(float(result["x_center"]))
    position = int(round(raw_position))
    result["stepper_position"] = position
    result["stepper_command"] = stepper_control.build_command(
        position=position,
        command_template=args.command_template,
    ).strip()

    if args.dry_run:
        return

    if serial_client is None:
        return

    sent_command, replies = serial_client.send(position=position)
    if args.hold_seconds > 0:
        time.sleep(args.hold_seconds)
    result["stepper_command"] = sent_command
    result["arduino_replies"] = replies


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keep YOLO loaded and run camera detection every few seconds."
    )
    parser.add_argument("--camera-index", type=int, default=1)
    parser.add_argument("--conf", type=float, default=0.1)
    parser.add_argument(
        "--device",
        help="Optional Ultralytics device, e.g. 0 for CUDA GPU or cpu.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5,
        help="Seconds between captured frames.",
    )
    parser.add_argument(
        "--weights",
        help="Optional YOLO weights path. Defaults to the newest runs/detect/train*/weights/best.pt.",
    )
    parser.add_argument("--port", help="Stepper Arduino serial port, e.g. COM3")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument(
        "--command-template",
        default="{position}",
        help=(
            "Newline-terminated command sent to Arduino when a target is detected. "
            "Use {position} as the integer target placeholder."
        ),
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0,
        help="Keep the serial port open briefly after each command.",
    )
    parser.add_argument(
        "--startup-wait-seconds",
        type=float,
        default=2,
        help="Wait after opening serial because many Arduino boards reset on connect.",
    )
    parser.add_argument(
        "--ack-wait-seconds",
        type=float,
        default=5,
        help="Wait this long for an OK:/ERR: reply from the Arduino sketch.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run only one capture/detection cycle.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print each detection result as machine-readable JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run detection and mapping only, but do not send serial commands.",
    )
    return parser.parse_args()


def print_human_result(result: dict, serial_enabled: bool, dry_run: bool) -> None:
    timestamp = result["timestamp"]
    if not result["detected"]:
        print(f"[{timestamp}] No target detected")
        print(f"Input frame saved to: {result['input_frame']}")
        return

    print(
        f"[{timestamp}] Target detected, x={result['x_center']:.2f}, "
        f"confidence={result['confidence']:.4f}"
    )
    print(f"Input frame saved to: {result['input_frame']}")
    print(f"Output saved to: {result['output_frame']}")
    print(
        f"Stepper mapping y=x -> position={result['stepper_position']}, "
        f"command={result['stepper_command']!r}"
    )

    if dry_run:
        print("Dry-run mode: no serial command sent")
    elif not serial_enabled:
        print("No --port provided: no serial command sent")
    else:
        for reply in result["arduino_replies"]:
            print(f"Arduino reply: {reply}")


def main() -> None:
    args = parse_args()
    weights_path = Path(args.weights).resolve() if args.weights else find_latest_weights()

    log(f"Loading YOLO weights once: {weights_path}", json_mode=args.json)
    model = YOLO(str(weights_path))
    log(f"Opening camera {args.camera_index}", json_mode=args.json)
    cap = open_camera(args.camera_index)
    serial_client = None

    try:
        if args.port and not args.dry_run:
            log(
                f"Opening stepper serial port {args.port} at {args.baud} baud",
                json_mode=args.json,
            )
            serial_client = stepper_control.StepperSerialClient(
                port=args.port,
                baud=args.baud,
                command_template=args.command_template,
                startup_wait_seconds=args.startup_wait_seconds,
                ack_wait_seconds=args.ack_wait_seconds,
            ).open()
            for reply in serial_client.ready_lines:
                log(f"Arduino reply: {reply}", json_mode=args.json)

        while True:
            ok, image = cap.read()
            if not ok or image is None:
                raise RuntimeError(f"Cannot read frame from camera {args.camera_index}")

            result = detect_frame(
                model=model,
                image=image,
                camera_index=args.camera_index,
                conf=args.conf,
                device=args.device,
            )
            maybe_send_to_stepper(args=args, result=result, serial_client=serial_client)

            if args.json:
                print(json.dumps(result, ensure_ascii=False), flush=True)
            else:
                print_human_result(
                    result=result,
                    serial_enabled=bool(args.port),
                    dry_run=args.dry_run,
                )
                print("", flush=True)

            if args.once:
                break

            time.sleep(args.interval_seconds)
    finally:
        if serial_client is not None:
            serial_client.close()
        cap.release()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(exc)
        raise SystemExit(1)
