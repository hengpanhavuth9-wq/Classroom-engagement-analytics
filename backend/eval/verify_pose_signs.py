#!/usr/bin/env python3
"""
Sanity-check the head-pose sign convention before any tuning.

    python eval/verify_pose_signs.py eval/out/lesson1.jsonl

`desk_work` classification assumes MediaPipe's transform matrix yields
"positive pitch = looking down" (head_pose.pose_from_matrix, marked
TODO: assumed). If that sign is flipped, every desk_work / off_task call
inverts and a fit on top of it is meaningless.

Checks, over detections the extract stage matched to a human label:

  1. median pitch on `desk_work` frames is clearly greater (more positive)
     than on `on_board` frames — students looking at notes really are pitched
     down relative to students looking at the board.
  2. `off_board` yaw spreads wider than `on_board` yaw — turning away shows up
     as larger yaw magnitude.
  3. (informational) on detections where both head pose and eye gaze were
     measured, do the two axes correlate positively? `engagement_engine.py`
     blends them as a weighted average (GAZE_YAW_SIGN / GAZE_PITCH_SIGN in
     config.py, both currently +1.0, unverified) — if they're anti-correlated,
     gaze is fighting head pose instead of refining it, and one of those
     settings should be -1.0.

Prints the medians and a PASS / FAIL. Non-zero exit on FAIL.
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from eval.run_eval import Record                                  # noqa: E402

PITCH_MARGIN_DEG = 4.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("jsonl", help="extract cache from run_eval.py")
    args = parser.parse_args()

    pitch: dict[str, list[float]] = {"on_board": [], "desk_work": []}
    yaw_abs: dict[str, list[float]] = {"on_board": [], "off_board": []}
    pose_yaw: list[float] = []
    gaze_yaw: list[float] = []
    pose_pitch: list[float] = []
    gaze_pitch: list[float] = []
    for line in open(args.jsonl, encoding="utf-8"):
        record = Record.from_json(line)
        if record.detected and record.pose is not None and record.gaze is not None:
            pose_yaw.append(record.pose[0]);   gaze_yaw.append(record.gaze[0])
            pose_pitch.append(record.pose[1]); gaze_pitch.append(record.gaze[1])
        if not record.detected or record.pose is None or record.truth is None:
            continue
        yaw, p = record.pose[0], record.pose[1]
        if record.truth in pitch:
            pitch[record.truth].append(p)
        if record.truth in yaw_abs:
            yaw_abs[record.truth].append(abs(yaw))

    if len(pitch["desk_work"]) < 5 or len(pitch["on_board"]) < 5:
        raise SystemExit("not enough on_board / desk_work samples in the cache to check")

    med_desk = statistics.median(pitch["desk_work"])
    med_board = statistics.median(pitch["on_board"])
    pitch_ok = med_desk - med_board >= PITCH_MARGIN_DEG

    yaw_ok = True
    if len(yaw_abs["off_board"]) >= 5:
        yaw_ok = statistics.median(yaw_abs["off_board"]) > statistics.median(yaw_abs["on_board"])

    print(f"pitch  on_board median={med_board:+.1f}deg  desk_work median={med_desk:+.1f}deg"
          f"  (desk_work should be >= on_board + {PITCH_MARGIN_DEG})")
    if len(yaw_abs["off_board"]) >= 5:
        print(f"|yaw|  on_board median={statistics.median(yaw_abs['on_board']):.1f}deg"
              f"  off_board median={statistics.median(yaw_abs['off_board']):.1f}deg")
    else:
        print("|yaw|  not enough off_board samples — skipped")

    _print_gaze_agreement("yaw",   pose_yaw,   gaze_yaw)
    _print_gaze_agreement("pitch", pose_pitch, gaze_pitch)

    if pitch_ok and yaw_ok:
        print("PASS — sign convention looks right")
        return 0
    print("FAIL — head-pose signs may be flipped; do not tune on this cache")
    return 1


def _print_gaze_agreement(axis: str, pose: list[float], gaze: list[float]) -> None:
    if len(pose) < 10:
        print(f"gaze vs head-pose ({axis})  not enough paired samples — skipped")
        return
    try:
        r = statistics.correlation(pose, gaze)
    except statistics.StatisticsError:
        print(f"gaze vs head-pose ({axis})  no variance in the sample — skipped")
        return
    verdict = "agree" if r > 0 else "DISAGREE — consider GAZE_{}_SIGN = -1.0".format(axis.upper())
    print(f"gaze vs head-pose ({axis})  r={r:+.2f} over {len(pose)} paired samples  ({verdict})")


if __name__ == "__main__":
    raise SystemExit(main())
