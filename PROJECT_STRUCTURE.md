# Project structure

## Python

| Path | Purpose |
| --- | --- |
| `camera_tests/camera_scan.py` | Probe camera indexes and save sample frames. |
| `camera_tests/yolo_single_detect.py` | Capture one frame and run YOLO detection. |
| `training/train_yolo.py` | Train the YOLO model. |
| `common/detect_loop.py` | Shared YOLO loading, camera capture, frame detection, and annotation helpers. |
| `common/stepper_control.py` | Shared stepper serial client, command formatting, and x-to-step mapping. |
| `control_flows/servo_open_close.py` | Servo open/close flow driven by YOLO detection. |
| `control_flows/stepper_detect_position.py` | Single stepper absolute-position style flow driven by detected x. |
| `control_flows/stepper_fixed_move.py` | Single stepper fixed relative move when a target is detected. |
| `control_flows/stepper_follow_target.py` | Single stepper follow-target flow toward a target x coordinate. |
| `control_flows/double_stepper_follow_cycle.py` | Dual stepper flow: motor 1 follows target, motor 2 runs a cycle when centered. |

## Firmware

| Path | Purpose |
| --- | --- |
| `firmware/servo_open_close/servo_open_close.ino` | Servo firmware. Receives `0` or `1`. |
| `firmware/stepper_fixed_move/stepper_fixed_move.ino` | Single stepper firmware. Receives signed relative steps. |
| `firmware/stepper_follow_target/stepper_follow_target.ino` | Single stepper firmware. Receives signed relative steps. |
| `firmware/double_stepper_follow_cycle/double_stepper_follow_cycle.ino` | Dual stepper firmware. Receives `M1:<steps>` and `M2:CYCLE:<steps>`. |

The old original hardware test sketch was removed from the active project.
