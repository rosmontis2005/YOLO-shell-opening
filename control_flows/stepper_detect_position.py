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


def map_camera_x_to_steps(x_center: float) -> int:
    raw_steps = stepper_control.camera_x_to_stepper_position(x_center)
    return int(round(raw_steps))


def should_send_position(
    previous_position: int | None,
    next_position: int,
    min_step_delta: int,
) -> bool:
    if previous_position is None:
        return True
    return abs(next_position - previous_position) >= min_step_delta


def print_control_result(
    result: dict,
    dry_run: bool,
    serial_enabled: bool,
    skipped_reason: str | None,
) -> None:
    timestamp = result["timestamp"]
    if not result["detected"]:
        print(f"[{timestamp}] No target detected")
        print(f"Input frame saved to: {result['input_frame']}")
        return

    print(
        f"[{timestamp}] Target x={result['x_center']:.2f}, "
        f"confidence={result['confidence']:.4f}, "
        f"mapped steps={result['stepper_position']}"
    )
    print(f"Input frame saved to: {result['input_frame']}")
    print(f"Output saved to: {result['output_frame']}")

    if skipped_reason:
        print(f"Stepper command skipped: {skipped_reason}")
    elif dry_run:
        print(f"Dry-run stepper command: {result['stepper_command']!r}")
    elif not serial_enabled:
        print("No serial port configured: no stepper command sent")
    else:
        print(f"Sent stepper command: {result['stepper_command']!r}")
        for reply in result["arduino_replies"]:
            print(f"Arduino reply: {reply}")


def log(message: str, json_mode: bool) -> None:
    print(message, file=sys.stderr if json_mode else sys.stdout, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect camera target x on a timer and drive the stepper by mapped steps."
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
        "--map-slope",
        type=float,
        help="Optional runtime override for the linear mapping slope k in y = kx + b.",
    )
    parser.add_argument(
        "--map-intercept",
        type=float,
        help="Optional runtime override for the linear mapping intercept b in y = kx + b.",
    )
    parser.add_argument(
        "--command-template",
        default="{position}",
        help=(
            "Newline-terminated command sent to Arduino. "
            "Use {position} as the integer mapped-step placeholder."
        ),
    )
    parser.add_argument(
        "--min-step-delta",
        type=int,
        default=1,
        help=(
            "Only send a new command when mapped steps differ from the last sent "
            "value by at least this amount."
        ),
    )
    parser.add_argument(
        "--force-repeat",
        action="store_true",
        help="Send a command for every detection even if mapped steps did not change.",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0,
        help="Keep waiting briefly after each serial command.",
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
    parser.add_argument("--once", action="store_true", help="Run only one cycle.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print each cycle result as machine-readable JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run detection and mapping only, but do not send serial commands.",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="List serial ports and exit.",
    )
    return parser.parse_args()


def run_control(args: argparse.Namespace) -> None:
    weights_path = Path(args.weights).resolve() if args.weights else detect_loop.find_latest_weights()
    serial_client = None
    last_sent_position: int | None = None

    if args.map_slope is not None:
        stepper_control.LINEAR_SLOPE = args.map_slope
    if args.map_intercept is not None:
        stepper_control.LINEAR_INTERCEPT = args.map_intercept

    log(
        "Mapping: y = "
        f"{stepper_control.LINEAR_SLOPE} * x + {stepper_control.LINEAR_INTERCEPT}",
        json_mode=args.json,
    )
    log(f"Loading YOLO weights once: {weights_path}", json_mode=args.json)
    model = detect_loop.YOLO(str(weights_path))
    log(f"Opening camera {args.camera_index}", json_mode=args.json)
    cap = detect_loop.open_camera(args.camera_index)

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

            result = detect_loop.detect_frame(
                model=model,
                image=image,
                camera_index=args.camera_index,
                conf=args.conf,
                device=args.device,
            )
            skipped_reason = None

            if result["detected"]:
                position = map_camera_x_to_steps(float(result["x_center"]))
                result["stepper_position"] = position
                result["stepper_command"] = stepper_control.build_command(
                    position=position,
                    command_template=args.command_template,
                ).strip()

                if not args.force_repeat and not should_send_position(
                    previous_position=last_sent_position,
                    next_position=position,
                    min_step_delta=args.min_step_delta,
                ):
                    skipped_reason = (
                        f"mapped steps changed less than {args.min_step_delta} "
                        f"from last sent value {last_sent_position}"
                    )
                elif args.dry_run:
                    last_sent_position = position
                elif serial_client is None:
                    skipped_reason = "serial port is not open"
                else:
                    sent_command, replies = serial_client.send(position=position)
                    if args.hold_seconds > 0:
                        time.sleep(args.hold_seconds)
                    result["stepper_command"] = sent_command
                    result["arduino_replies"] = replies
                    last_sent_position = position

            if args.json:
                result["stepper_skipped_reason"] = skipped_reason
                print(json.dumps(result, ensure_ascii=False), flush=True)
            else:
                print_control_result(
                    result=result,
                    dry_run=args.dry_run,
                    serial_enabled=serial_client is not None,
                    skipped_reason=skipped_reason,
                )
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

    run_control(args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        print(exc)
        raise SystemExit(1)
