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
from control_flows import stepper_follow_target


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")


def log(message: str, json_mode: bool) -> None:
    print(message, file=sys.stderr if json_mode else sys.stdout, flush=True)


def send_raw_command(
    client: stepper_control.StepperSerialClient,
    command: str,
) -> tuple[str, list[str]]:
    if client.ser is None or not client.ser.is_open:
        raise RuntimeError("Stepper serial port is not open")

    clean_command = command.rstrip("\r\n")
    client.ser.write((clean_command + "\n").encode("utf-8"))
    client.ser.flush()
    replies = stepper_control.read_serial_lines(
        client.ser,
        wait_seconds=client.ack_wait_seconds,
    )
    return clean_command, replies


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Wait for a target, enter a work cycle, use motor 1 to correct "
            "position until centered, then run motor 2 out and back."
        )
    )
    parser.add_argument("--camera-index", type=int, default=1)
    parser.add_argument("--conf", type=float, default=0.1)
    parser.add_argument("--device", help="Optional Ultralytics device, e.g. 0 or cpu.")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5,
        help="Seconds to wait before the next detection cycle after movement finishes.",
    )
    parser.add_argument(
        "--weights",
        help="Optional YOLO weights path. Defaults to newest runs/detect/train*/weights/best.pt.",
    )
    parser.add_argument("--port", help="Stepper Arduino serial port, e.g. COM3")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--target-x", type=float, default=320)
    parser.add_argument("--tolerance", type=float, default=20)
    parser.add_argument(
        "--step-size",
        type=int,
        default=100,
        help="Motor 1 relative steps when target is outside tolerance.",
    )
    parser.add_argument(
        "--aux-steps",
        type=int,
        default=10000,
        help="Motor 2 one-way steps for the out-and-back cycle.",
    )
    parser.add_argument(
        "--invert-direction",
        action="store_true",
        help="Swap motor 1 direction used when x is greater or less than target-x.",
    )
    parser.add_argument(
        "--primary-command-template",
        default="M1:{position}",
        help="Command template for motor 1. {position} is signed relative steps.",
    )
    parser.add_argument(
        "--aux-command-template",
        default="M2:CYCLE:{position}",
        help="Command template for motor 2 cycle. {position} is one-way steps.",
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
        default=45,
        help="Wait this long for Arduino to finish moving and reply OK:/ERR:.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Run one idle check if no target is found, or one full work cycle "
            "if a target is found."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print JSON result each step.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run detection and command generation only; do not send serial commands.",
    )
    parser.add_argument("--list-ports", action="store_true", help="List serial ports and exit.")
    return parser.parse_args()


def capture_detection(args: argparse.Namespace, model: detect_loop.YOLO, cap) -> dict:
    ok, image = cap.read()
    if not ok or image is None:
        raise RuntimeError(f"Cannot read frame from camera {args.camera_index}")

    return detect_loop.detect_frame(
        model=model,
        image=image,
        camera_index=args.camera_index,
        conf=args.conf,
        device=args.device,
    )


def prepare_result(
    result: dict,
    args: argparse.Namespace,
    work_state: bool,
    work_cycle_id: int | None,
    correction_index: int | None,
) -> dict:
    result["work_state"] = work_state
    result["work_cycle_id"] = work_cycle_id
    result["correction_index"] = correction_index
    result["target_x"] = args.target_x
    result["tolerance"] = args.tolerance
    result["x_error"] = (
        None if result["x_center"] is None else round(float(result["x_center"]) - args.target_x, 2)
    )
    result["relative_steps"] = None
    result["aux_steps"] = None
    result["double_decision"] = "not_detected"
    result["state_transition"] = None
    return result


def print_or_emit_result(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return

    print_result(result=result, dry_run=args.dry_run)
    print("", flush=True)


def print_result(result: dict, dry_run: bool) -> None:
    timestamp = result["timestamp"]
    if not result["detected"]:
        if result.get("work_state"):
            print(f"[{timestamp}] Work state active; target not detected, retrying")
        else:
            print(f"[{timestamp}] Work state idle; no target detected")
        print(f"Input frame saved to: {result['input_frame']}")
        return

    print(
        f"[{timestamp}] Target x={result['x_center']:.2f}, "
        f"error={result['x_error']:.2f}, confidence={result['confidence']:.4f}, "
        f"work_state={result['work_state']}, decision={result['double_decision']}"
    )
    print(f"Input frame saved to: {result['input_frame']}")
    print(f"Output saved to: {result['output_frame']}")
    if result.get("state_transition"):
        print(f"State transition: {result['state_transition']}")

    if not result.get("stepper_command"):
        print("No stepper command needed")
    elif dry_run:
        print(f"Dry-run command: {result['stepper_command']!r}")
    else:
        print(f"Sent command: {result['stepper_command']!r}")
        for reply in result["arduino_replies"]:
            print(f"Arduino reply: {reply}")


def run_motor1_correction(
    args: argparse.Namespace,
    result: dict,
    steps: int,
    serial_client: stepper_control.StepperSerialClient | None,
) -> None:
    command = stepper_control.build_command(
        position=steps,
        command_template=args.primary_command_template,
    ).strip()
    result["stepper_command"] = command
    if args.dry_run:
        return

    sent_command, replies = serial_client.send(steps)
    result["stepper_command"] = sent_command
    result["arduino_replies"] = replies


def run_motor2_cycle(
    args: argparse.Namespace,
    result: dict,
    serial_client: stepper_control.StepperSerialClient | None,
) -> None:
    aux_steps = abs(args.aux_steps)
    command = stepper_control.build_command(
        position=aux_steps,
        command_template=args.aux_command_template,
    ).strip()
    result["aux_steps"] = aux_steps
    result["stepper_command"] = command
    if args.dry_run:
        return

    sent_command, replies = send_raw_command(serial_client, command)
    result["stepper_command"] = sent_command
    result["arduino_replies"] = replies


def run_work_cycle(
    args: argparse.Namespace,
    model: detect_loop.YOLO,
    cap,
    serial_client: stepper_control.StepperSerialClient | None,
    initial_result: dict,
    work_cycle_id: int,
) -> None:
    result = initial_result
    correction_count = 0
    first_work_step = True

    while True:
        prepare_result(
            result=result,
            args=args,
            work_state=True,
            work_cycle_id=work_cycle_id,
            correction_index=correction_count,
        )
        if first_work_step:
            result["state_transition"] = "work_state:false->true"
            first_work_step = False

        if not result["detected"]:
            result["double_decision"] = "work_target_lost_retry_detection"
            print_or_emit_result(args=args, result=result)
            time.sleep(args.interval_seconds)
            result = capture_detection(args=args, model=model, cap=cap)
            continue

        steps, decision = stepper_follow_target.choose_relative_steps(
            x_center=float(result["x_center"]),
            target_x=args.target_x,
            tolerance=args.tolerance,
            step_size=args.step_size,
            invert_direction=args.invert_direction,
        )
        result["relative_steps"] = steps

        if steps == 0:
            result["double_decision"] = "target_reached_run_motor2_cycle"
            run_motor2_cycle(args=args, result=result, serial_client=serial_client)
            result["work_state"] = False
            result["state_transition"] = "work_state:true->false"
            print_or_emit_result(args=args, result=result)
            return

        correction_count += 1
        result["correction_index"] = correction_count
        result["double_decision"] = f"correct_motor1_{decision}"
        run_motor1_correction(
            args=args,
            result=result,
            steps=steps,
            serial_client=serial_client,
        )
        print_or_emit_result(args=args, result=result)

        time.sleep(args.interval_seconds)
        result = capture_detection(args=args, model=model, cap=cap)


def run(args: argparse.Namespace) -> None:
    weights_path = Path(args.weights).resolve() if args.weights else detect_loop.find_latest_weights()
    serial_client = None
    work_state = False
    work_cycle_id = 0

    log(f"Loading YOLO weights once: {weights_path}", args.json)
    model = detect_loop.YOLO(str(weights_path))
    log(f"Opening camera {args.camera_index}", args.json)
    cap = detect_loop.open_camera(args.camera_index)

    try:
        if not args.dry_run:
            log(f"Opening double stepper serial port {args.port} at {args.baud} baud", args.json)
            serial_client = stepper_control.StepperSerialClient(
                port=args.port,
                baud=args.baud,
                command_template=args.primary_command_template,
                startup_wait_seconds=args.startup_wait_seconds,
                ack_wait_seconds=args.ack_wait_seconds,
            ).open()
            for reply in serial_client.ready_lines:
                log(f"Arduino reply: {reply}", args.json)

        while True:
            result = capture_detection(args=args, model=model, cap=cap)
            prepare_result(
                result=result,
                args=args,
                work_state=work_state,
                work_cycle_id=None,
                correction_index=None,
            )

            if not result["detected"]:
                result["double_decision"] = "idle_wait_for_target"
                print_or_emit_result(args=args, result=result)
                if args.once:
                    break

                time.sleep(args.interval_seconds)
                continue

            work_state = True
            work_cycle_id += 1
            run_work_cycle(
                args=args,
                model=model,
                cap=cap,
                serial_client=serial_client,
                initial_result=result,
                work_cycle_id=work_cycle_id,
            )
            work_state = False

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
