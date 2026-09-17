#!/usr/bin/env python3
"""
Download the model weights the pipeline needs.

Weights are gitignored rather than vendored, so a fresh clone runs this once:

    python scripts/fetch_models.py

The MediaPipe face_landmarker.task is not listed here — mediapipe_init fetches
it on first use.

Pass --with-sixdrepnet to additionally fetch the 6DRepNet360 head-pose model
(see config.py: HEAD_POSE_BACKEND). It's a 90 MB extract out of a ~300 MB
PINTO_model_zoo tarball for a backend that's opt-in and unverified against
this project's own footage, so it's not part of the default set — most
clones don't need it.
"""
import argparse
import io
import os
import sys
import tarfile
import urllib.request

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SIXDREPNET_URL = "https://s3.ap-northeast-2.wasabisys.com/pinto-model-zoo/423_6DRepNet360/resources.tar.gz"
SIXDREPNET_MEMBER = "sixdrepnet360_Nx3x224x224.onnx"
SIXDREPNET_DEST = os.path.join(BACKEND, "app", "pipeline", "weights", SIXDREPNET_MEMBER)

MODELS = [
    (
        "models/face-detection/face_detection_yunet_2023mar.onnx",
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
        "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "YuNet face detector",
    ),
    (
        "models/gaze-estimation/weights/resnet34_gaze.onnx",
        "https://github.com/yakhyo/gaze-estimation/releases/download/weights/resnet34_gaze.onnx",
        "Eye gaze (resnet34)",
    ),
    (
        "models/gaze-estimation/weights/resnet18_gaze.onnx",
        "https://github.com/yakhyo/gaze-estimation/releases/download/weights/resnet18_gaze.onnx",
        "Eye gaze (resnet18, faster fallback)",
    ),
]

MIN_BYTES = 10_000   # anything smaller is an error page or a git-lfs pointer


def _fetch_sixdrepnet() -> bool:
    """Stream the PINTO tarball and pull out only the one member we need —
    the tarball also bundles demo videos/images we have no use for."""
    if os.path.exists(SIXDREPNET_DEST) and os.path.getsize(SIXDREPNET_DEST) > MIN_BYTES:
        print("[ok]   6DRepNet360 head pose — already present")
        return True
    os.makedirs(os.path.dirname(SIXDREPNET_DEST), exist_ok=True)
    print("[..]   6DRepNet360 head pose — downloading ~300 MB tarball (extracting one file)")
    try:
        with urllib.request.urlopen(SIXDREPNET_URL) as resp:
            data = resp.read()
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            member = tar.extractfile(SIXDREPNET_MEMBER)
            if member is None:
                raise FileNotFoundError(f"{SIXDREPNET_MEMBER} not found in tarball")
            with open(SIXDREPNET_DEST, "wb") as out:
                out.write(member.read())
    except Exception as exc:
        print(f"[FAIL] 6DRepNet360 head pose: {exc}")
        return False
    size = os.path.getsize(SIXDREPNET_DEST)
    if size <= MIN_BYTES:
        print(f"[FAIL] 6DRepNet360 head pose: got {size} bytes")
        os.remove(SIXDREPNET_DEST)
        return False
    print(f"[ok]   6DRepNet360 head pose — {size / 1e6:.1f} MB")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-sixdrepnet", action="store_true",
                         help="also fetch the opt-in 6DRepNet360 head-pose model")
    args = parser.parse_args()

    failed = []
    for rel_path, url, label in MODELS:
        dest = os.path.join(BACKEND, rel_path)
        if os.path.exists(dest) and os.path.getsize(dest) > MIN_BYTES:
            print(f"[ok]   {label} — already present")
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        print(f"[..]   {label} — downloading")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:
            print(f"[FAIL] {label}: {exc}")
            failed.append(label)
            continue
        size = os.path.getsize(dest)
        if size <= MIN_BYTES:
            print(f"[FAIL] {label}: got {size} bytes — check the URL")
            os.remove(dest)
            failed.append(label)
        else:
            print(f"[ok]   {label} — {size / 1e6:.1f} MB")

    if args.with_sixdrepnet and not _fetch_sixdrepnet():
        failed.append("6DRepNet360 head pose")

    if failed:
        print(f"\n{len(failed)} download(s) failed: {', '.join(failed)}")
        return 1
    print("\nAll models present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
