from __future__ import annotations

import argparse
import sys
import time


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")


LINEAR_SLOPE = 1.0
LINEAR_INTERCEPT = 0.0


def camera_x_to_stepper_position(x: float) -> float:
    """Linear mapping from camera x coordinate to target stepper position.

    Initial calibration is y = x. Adjust LINEAR_SLOPE and LINEAR_INTERCEPT after
    measuring the camera pixel range and the lead-screw travel range.
    """
    y = LINEAR_SLOPE * x + LINEAR_INTERCEPT
    return y


def import_pyserial():
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        raise RuntimeError(
            "pyserial is required for serial communication. Install it with: pip install pyserial"
        ) from exc

    return serial, list_ports


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


def build_command(position: int, command_template: str) -> str:
    command = command_template.format(position=position)
    return command.rstrip("\r\n") + "\n"


class StepperSerialClient:
    def __init__(
        self,
        port: str,
        baud: int,
        command_template: str,
        startup_wait_seconds: float,
        ack_wait_seconds: float,
    ) -> None:
        self.port = port
        self.baud = baud
        self.command_template = command_template
        self.startup_wait_seconds = startup_wait_seconds
        self.ack_wait_seconds = ack_wait_seconds
        self.ser = None
        self.ready_lines: list[str] = []

    def open(self) -> "StepperSerialClient":
        serial, _ = import_pyserial()
        self.ser = serial.Serial(port=self.port, baudrate=self.baud, timeout=0.1)
        # Many Arduino-compatible boards reset when the serial port opens.
        time.sleep(self.startup_wait_seconds)
        self.ready_lines = read_serial_lines(self.ser, wait_seconds=0.2)
        return self

    def close(self) -> None:
        if self.ser is not None and self.ser.is_open:
            self.ser.close()

    def __enter__(self) -> "StepperSerialClient":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def send(self, position: int) -> tuple[str, list[str]]:
        if self.ser is None or not self.ser.is_open:
            raise RuntimeError("Stepper serial port is not open")

        command = build_command(position=position, command_template=self.command_template)
        self.ser.write(command.encode("utf-8"))
        self.ser.flush()
        ack_lines = read_serial_lines(self.ser, wait_seconds=self.ack_wait_seconds)
        return command.strip(), ack_lines


def send_position(
    port: str,
    baud: int,
    position: int,
    command_template: str,
    hold_seconds: float,
    startup_wait_seconds: float,
    ack_wait_seconds: float,
) -> tuple[str, list[str]]:
    with StepperSerialClient(
        port=port,
        baud=baud,
        command_template=command_template,
        startup_wait_seconds=startup_wait_seconds,
        ack_wait_seconds=ack_wait_seconds,
    ) as client:
        sent_command, ack_lines = client.send(position=position)
        if hold_seconds > 0:
            time.sleep(hold_seconds)

    return sent_command, client.ready_lines + ack_lines


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
        description="Map camera x coordinate to a stepper target and send it to Arduino."
    )
    parser.add_argument("--port", help="Serial port, e.g. COM3")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument(
        "--target-x",
        type=float,
        help="Target x coordinate from the camera detection result.",
    )
    parser.add_argument(
        "--position",
        type=float,
        help="Bypass camera_x_to_stepper_position() and send this stepper position directly.",
    )
    parser.add_argument(
        "--command-template",
        default="{position}",
        help=(
            "Newline-terminated command sent to Arduino. "
            "Use {position} as the integer target placeholder."
        ),
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0,
        help="Keep the serial port open briefly after sending the command.",
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
    parser.add_argument("--dry-run", action="store_true", help="Print command only")
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="List serial ports and exit",
    )
    return parser.parse_args()


def resolve_position(args: argparse.Namespace) -> tuple[float | None, float, int]:
    if args.position is not None:
        raw_position = float(args.position)
        return None, raw_position, int(round(raw_position))

    if args.target_x is None:
        raise ValueError("--target-x or --position is required unless --list-ports is used")

    x = float(args.target_x)
    raw_position = camera_x_to_stepper_position(x)
    return x, raw_position, int(round(raw_position))


def main() -> None:
    args = parse_args()

    if args.list_ports:
        print_ports()
        return

    x, raw_position, position = resolve_position(args)
    command = build_command(position=position, command_template=args.command_template).strip()

    if x is None:
        print(f"Stepper target position: {raw_position:.2f} -> command {command!r}")
    else:
        print(
            f"Camera target x={x:.2f} -> linear y={raw_position:.2f} "
            f"-> stepper command {command!r}"
        )

    if args.dry_run:
        print("Dry-run mode: no serial command sent")
        return

    if not args.port:
        raise ValueError("--port is required unless --dry-run or --list-ports is used")

    sent_command, replies = send_position(
        port=args.port,
        baud=args.baud,
        position=position,
        command_template=args.command_template,
        hold_seconds=args.hold_seconds,
        startup_wait_seconds=args.startup_wait_seconds,
        ack_wait_seconds=args.ack_wait_seconds,
    )
    print(f"Sent command: {sent_command}")
    for reply in replies:
        print(f"Arduino reply: {reply}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(exc)
        raise SystemExit(1)
