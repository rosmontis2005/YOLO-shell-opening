from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")


def import_pyserial():
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        raise RuntimeError(
            "pyserial is required for serial communication. Install it with: pip install pyserial"
        ) from exc

    return serial, list_ports


def run_detection(detect_script: Path, camera_index: int, conf: float) -> dict:
    command = [
        sys.executable,
        str(detect_script),
        "--camera-index",
        str(camera_index),
        "--conf",
        str(conf),
        "--json",
    ]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "Unknown error"
        raise RuntimeError(f"Detection failed: {message}")

    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("Detection failed: no JSON output")

    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue

    raise RuntimeError(f"Detection output does not contain valid JSON: {stdout}")


def read_serial_lines(ser, wait_seconds: float) -> list[str]:
    deadline = time.monotonic() + wait_seconds
    lines = []

    while time.monotonic() < deadline:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if line:
            lines.append(line)
            if line.startswith("OK:") or line.startswith("ERR:"):
                break

    return lines


def send_command(
    port: str,
    baud: int,
    detected: bool,
    hold_seconds: float,
    startup_wait_seconds: float,
) -> tuple[str, list[str]]:
    serial, _ = import_pyserial()
    command = "1\n" if detected else "0\n"

    with serial.Serial(port=port, baudrate=baud, timeout=0.1) as ser:
        # Many Arduino boards reset after opening serial.
        time.sleep(startup_wait_seconds)
        ready_lines = read_serial_lines(ser, wait_seconds=0.2)
        ser.write(command.encode("utf-8"))
        ser.flush()
        ack_lines = read_serial_lines(ser, wait_seconds=2)
        if hold_seconds > 0:
            time.sleep(hold_seconds)

    return command.strip(), ready_lines + ack_lines


def print_ports() -> None:
    _, list_ports = import_pyserial()
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found")
        return

    print("Available serial ports:")
    for port in ports:
        print(f"- {port.device}: {port.description}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run YOLO detection once and send an open/close command to Arduino."
    )
    parser.add_argument("--port", help="Serial port, e.g. COM3")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--camera-index", type=int, default=1)
    parser.add_argument("--conf", type=float, default=0.1)
    parser.add_argument("--detect-script", default="camera_tests/yolo_single_detect.py")
    parser.add_argument(
        "--force-command",
        choices=("0", "1"),
        help="Skip detection and send a raw servo command for serial/servo testing.",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=3,
        help="Keep the serial port open briefly after sending the command.",
    )
    parser.add_argument(
        "--startup-wait-seconds",
        type=float,
        default=2,
        help="Wait after opening serial because many Arduino boards reset on connect.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run detection only")
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="List serial ports and exit",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list_ports:
        print_ports()
        return

    if args.force_command is None:
        detect_script = (PROJECT_ROOT / args.detect_script).resolve()
        if not detect_script.exists():
            raise FileNotFoundError(f"Detection script not found: {detect_script}")

        result = run_detection(
            detect_script=detect_script,
            camera_index=args.camera_index,
            conf=args.conf,
        )

        detected = bool(result.get("detected", False))
        print(f"Detection result: detected={detected}, confidence={result.get('confidence')}")
        print(f"Input frame: {result.get('input_frame')}")
        if result.get("output_frame"):
            print(f"Output frame: {result['output_frame']}")
    else:
        detected = args.force_command == "1"
        print(f"Forced servo command: {args.force_command}")

    if args.dry_run:
        print("Dry-run mode: no serial command sent")
        return

    if not args.port:
        raise ValueError("--port is required unless --dry-run or --list-ports is used")

    command, replies = send_command(
        port=args.port,
        baud=args.baud,
        detected=detected,
        hold_seconds=args.hold_seconds,
        startup_wait_seconds=args.startup_wait_seconds,
    )
    angle = 90 if detected else 0
    print(f"Sent command: {command} (servo target angle: {angle} deg)")
    for reply in replies:
        print(f"Arduino reply: {reply}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(exc)
        raise SystemExit(1)
