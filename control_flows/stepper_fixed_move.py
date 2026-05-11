from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common import detect_loop, stepper_control


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")


def log(message: str, json_mode: bool) -> None:
    print(message, file=sys.stderr if json_mode else sys.stdout, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keep the stepper still, move right by fixed steps when a target is detected."
    )
    parser.add_argument("--camera-index", type=int, default=1)
    parser.add_argument("--conf", type=float, default=0.1)
    parser.add_argument("--device", help="Optional Ultralytics device, e.g. 0 or cpu.")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5,
        help="Seconds to wait before the next detection cycle.",
    )
    parser.add_argument(
        "--weights",
        help="Optional YOLO weights path. Defaults to newest runs/detect/train*/weights/best.pt.",
    )
    parser.add_argument("--port", help="Stepper Arduino serial port, e.g. COM3")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument(
        "--steps",
        type=int,
        default=1000,
        help="Relative steps to move right after a detection.",
    )
    parser.add_argument(
        "--invert-direction",
        action="store_true",
        help="Send negative steps instead, if the motor direction is reversed.",
    )
    parser.add_argument(
        "--command-template",
        default="{position}",
        help="Newline-terminated serial command template. {position} is signed relative steps.",
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
        default=20,
        help="Wait this long for Arduino to finish moving and reply OK:/ERR:.",
    )
    parser.add_argument("--once", action="store_true", help="Run only one cycle.")
    parser.add_argument("--json", action="store_true", help="Print JSON result each cycle.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run detection and command generation only; do not send serial commands.",
    )
    parser.add_argument("--list-ports", action="store_true", help="List serial ports and exit.")
    return parser.parse_args()


def build_result(detection: dict, command_steps: int | None, command_template: str) -> dict:
    result = dict(detection)
    result["relative_steps"] = command_steps
    result["stepper_command"] = (
        None
        if command_steps is None
        else stepper_control.build_command(command_steps, command_template).strip()
    )
    return result


def print_result(result: dict, dry_run: bool) -> None:
    timestamp = result["timestamp"]
    if not result["detected"]:
        print(f"[{timestamp}] No target detected; stepper stays still")
        print(f"Input frame saved to: {result['input_frame']}")
        return

    print(
        f"[{timestamp}] Target detected, x={result['x_center']:.2f}, "
        f"confidence={result['confidence']:.4f}"
    )
    print(f"Input frame saved to: {result['input_frame']}")
    print(f"Output saved to: {result['output_frame']}")
    if dry_run:
        print(f"Dry-run command: {result['stepper_command']!r}")
    else:
        print(f"Sent command: {result['stepper_command']!r}")
        for reply in result["arduino_replies"]:
            print(f"Arduino reply: {reply}")


def run(args: argparse.Namespace) -> None:
    weights_path = Path(args.weights).resolve() if args.weights else detect_loop.find_latest_weights()
    command_steps = -abs(args.steps) if args.invert_direction else abs(args.steps)
    serial_client = None

    log(f"Loading YOLO weights once: {weights_path}", args.json)
    model = detect_loop.YOLO(str(weights_path))
    log(f"Opening camera {args.camera_index}", args.json)
    cap = detect_loop.open_camera(args.camera_index)

    try:
        if not args.dry_run:
            log(f"Opening stepper serial port {args.port} at {args.baud} baud", args.json)
            serial_client = stepper_control.StepperSerialClient(
                port=args.port,
                baud=args.baud,
                command_template=args.command_template,
                startup_wait_seconds=args.startup_wait_seconds,
                ack_wait_seconds=args.ack_wait_seconds,
            ).open()
            for reply in serial_client.ready_lines:
                log(f"Arduino reply: {reply}", args.json)

        while True:
            ok, image = cap.read()
            if not ok or image is None:
                raise RuntimeError(f"Cannot read frame from camera {args.camera_index}")

            detection = detect_loop.detect_frame(
                model=model,
                image=image,
                camera_index=args.camera_index,
                conf=args.conf,
                device=args.device,
            )
            result = build_result(
                detection=detection,
                command_steps=command_steps if detection["detected"] else None,
                command_template=args.command_template,
            )

            if detection["detected"] and not args.dry_run:
                sent_command, replies = serial_client.send(command_steps)
                result["stepper_command"] = sent_command
                result["arduino_replies"] = replies

            if args.json:
                print(json.dumps(result, ensure_ascii=False), flush=True)
            else:
                print_result(result=result, dry_run=args.dry_run)
                print("", flush=True)

            if args.once:
                break

            time.sleep(args.interval_seconds)
    finally:
        if serial_client is not None:
            serial_client.close()
        cap.release()


def main() -> None:
    args = parse_args()

    if args.list_ports:
        stepper_control.print_ports()
        return

    if not args.dry_run and not args.port:
        raise ValueError("--port is required unless --dry-run or --list-ports is used")

    run(args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        print(exc)
        raise SystemExit(1)
