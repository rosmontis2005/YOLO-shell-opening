# Ubuntu migration guide

This project runs YOLO detection from a USB camera and sends serial commands to an Arduino-controlled servo or stepper motor.

## Dependency map

| Area | Used by | Dependency |
| --- | --- | --- |
| YOLO inference/training | `camera_tests/yolo_single_detect.py`, `common/detect_loop.py`, `training/train_yolo.py`, `control_flows/*.py` | `ultralytics` |
| Camera capture and image writing | `camera_tests/yolo_single_detect.py`, `common/detect_loop.py`, `camera_tests/camera_scan.py` | `opencv-python` |
| Arduino serial communication | `control_flows/*.py`, `common/stepper_control.py` | `pyserial` |
| Model files | `yolo26n.pt`, `runs/detect/train*/weights/best.pt` | keep these files in the repo or copy them after cloning |
| Dataset config | `data.yaml` | paths are relative to the repo root |
| Arduino sketches | `firmware/` | Arduino IDE or Arduino CLI, no Python package needed |

`requirements.txt` pins the direct Python dependencies found in the current working environment. `ultralytics` installs its main Python sub-dependencies such as PyTorch, TorchVision, NumPy, Pillow, PyYAML, SciPy, Requests, Matplotlib, Polars, Psutil, and `ultralytics-thop`.

## Quick setup after `git clone`

```bash
cd yolo-based-shell-opening-control
bash setup_ubuntu.sh
source .venv/bin/activate
```

If you need Arduino serial access, add your user to the `dialout` group once:

```bash
sudo usermod -aG dialout "$USER"
```

Log out and log back in after changing the group.

## Manual setup

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 v4l-utils

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Check the environment

```bash
source .venv/bin/activate
python - <<'PY'
import cv2
import serial
import ultralytics
print("OpenCV:", cv2.__version__)
print("pyserial:", serial.VERSION)
print("ultralytics:", ultralytics.__version__)
PY
```

List cameras:

```bash
v4l2-ctl --list-devices
python camera_tests/camera_scan.py
```

List Arduino serial ports:

```bash
python control_flows/servo_open_close.py --list-ports
python common/stepper_control.py --list-ports
```

On Ubuntu, camera indexes are usually `0`, `1`, ... and Arduino ports are usually `/dev/ttyACM0` or `/dev/ttyUSB0`, not `COM3`.

## Common run commands

Single detection:

```bash
python camera_tests/yolo_single_detect.py --camera-index 0 --json
```

Detection only, no serial command:

```bash
python control_flows/stepper_detect_position.py --camera-index 0 --dry-run --once
```

Servo control:

```bash
python control_flows/servo_open_close.py --port /dev/ttyACM0 --baud 9600 --camera-index 0
```

Stepper follow control:

```bash
python control_flows/stepper_follow_target.py --port /dev/ttyACM0 --baud 9600 --camera-index 0
```

Double stepper control:

```bash
python control_flows/double_stepper_follow_cycle.py --port /dev/ttyACM0 --baud 9600 --camera-index 0
```

Training:

```bash
python training/train_yolo.py
```

`training/train_yolo.py` defaults to `--device 0`, which expects a CUDA GPU. If the Ubuntu machine has no NVIDIA GPU, run it with `--device cpu`.

## Optional CUDA note

For inference, CPU is enough to verify the workflow. For faster training or inference on NVIDIA GPUs, install a CUDA-compatible PyTorch build that matches the driver on the Ubuntu machine, then install this project's requirements.

## Files that must be present

The detection scripts look for trained weights under:

```text
runs/detect/train*/weights/best.pt
```

The repo currently also has:

```text
yolo26n.pt
runs/detect/train/weights/best.pt
runs/detect/train/weights/last.pt
```

Make sure these model files are included in the clone or copied to the same paths after cloning.
