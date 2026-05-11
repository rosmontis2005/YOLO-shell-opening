from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = PROJECT_ROOT / "shot"
MAX_CAMERA_INDEX = 10


def probe_camera(index: int) -> dict:
    import cv2

    backend = (
        cv2.CAP_DSHOW
        if sys.platform.startswith("win") and hasattr(cv2, "CAP_DSHOW")
        else cv2.CAP_ANY
    )
    cap = cv2.VideoCapture(index, backend)

    result = {
        "camera_index": index,
        "status": "unavailable",
        "image_file": None,
        "width": None,
        "height": None,
        "backend": None,
        "message": "",
    }

    if not cap.isOpened():
        result["message"] = "Cannot open camera"
        cap.release()
        return result

    ok, frame = cap.read()
    backend_name = cap.getBackendName() if hasattr(cap, "getBackendName") else "unknown"
    cap.release()

    result["backend"] = backend_name

    if not ok or frame is None:
        result["status"] = "opened_but_no_frame"
        result["message"] = "Camera opened but no frame was captured"
        return result

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_name = f"camera_{index}_{timestamp}.jpg"
    image_path = SHOT_DIR / image_name

    cv2.imwrite(str(image_path), frame)

    result["status"] = "ok"
    result["image_file"] = image_name
    result["height"], result["width"] = frame.shape[:2]
    result["message"] = "Frame captured successfully"
    return result


def run_probe(index: int) -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    result = probe_camera(index)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


def scan_all_cameras() -> list[dict]:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for index in range(MAX_CAMERA_INDEX):
        try:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--probe", str(index)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                cwd=str(PROJECT_ROOT),
            )
        except subprocess.TimeoutExpired:
            results.append(
                {
                    "camera_index": index,
                    "status": "probe_timeout",
                    "image_file": None,
                    "width": None,
                    "height": None,
                    "backend": None,
                    "message": "Probe timed out after 20 seconds",
                }
            )
            continue

        if completed.returncode == 0:
            stdout = completed.stdout.strip()
            if stdout:
                results.append(json.loads(stdout))
            else:
                results.append(
                    {
                        "camera_index": index,
                        "status": "probe_failed",
                        "image_file": None,
                        "width": None,
                        "height": None,
                        "backend": None,
                        "message": "Probe returned no output",
                    }
                )
            continue

        message = completed.stderr.strip() or completed.stdout.strip() or "Probe process crashed"
        results.append(
            {
                "camera_index": index,
                "status": "probe_failed",
                "image_file": None,
                "width": None,
                "height": None,
                "backend": None,
                "message": message,
            }
        )

    return results


def save_summary(results: list[dict]) -> tuple[Path, Path]:
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary = {
        "scan_time": scan_time,
        "scanned_index_range": f"0-{MAX_CAMERA_INDEX - 1}",
        "results": results,
    }

    json_path = SHOT_DIR / f"camera_scan_{timestamp}.json"
    txt_path = SHOT_DIR / f"camera_scan_{timestamp}.txt"

    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"Camera scan time: {scan_time}",
        f"Scanned camera indexes: 0-{MAX_CAMERA_INDEX - 1}",
        "",
    ]
    for item in results:
        lines.append(
            "index={camera_index}, status={status}, backend={backend}, "
            "size={width}x{height}, image={image_file}, message={message}".format(
                camera_index=item["camera_index"],
                status=item["status"],
                backend=item["backend"] or "unknown",
                width=item["width"] or "-",
                height=item["height"] or "-",
                image_file=item["image_file"] or "-",
                message=item["message"],
            )
        )

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return txt_path, json_path


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--probe":
        raise SystemExit(run_probe(int(sys.argv[2])))

    results = scan_all_cameras()
    txt_path, json_path = save_summary(results)

    print(f"Scan finished. Summary saved to: {txt_path}")
    print(f"JSON saved to: {json_path}")
    print("")
    for item in results:
        print(
            "[{camera_index}] status={status}, image={image_file}, message={message}".format(
                camera_index=item["camera_index"],
                status=item["status"],
                image_file=item["image_file"] or "-",
                message=item["message"],
            )
        )


if __name__ == "__main__":
    main()
