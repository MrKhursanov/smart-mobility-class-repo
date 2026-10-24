"""Offline real-video counting evaluation; requires actual video and >=100 labels.

CSV format: frame_index,count. Frames are zero-based original video frames.
Reports valid-frame MAE and invalid coverage separately; no fake labels generated.
"""
import argparse
import csv
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/smart_hub_m1'))
import cv2
from smart_hub_m1.core import QueueEngine
from smart_hub_m1.vision import Vision


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--video', required=True)
    p.add_argument('--calibration', required=True)
    p.add_argument('--labels', required=True)
    p.add_argument('--output', default=str(ROOT/'evidence/real_video'))
    args = p.parse_args()
    with open(args.labels) as f:
        rows = list(csv.DictReader(f))
    labels = {int(r['frame_index']):int(r['count']) for r in rows}
    if len(labels) < 100 or len(labels) != len(rows) or min(labels) < 0 or min(labels.values()) < 0:
        raise ValueError('Provide at least 100 unique annotated frames and nonnegative counts')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or fps <= 0:
        raise ValueError('Video missing or FPS unavailable')
    detector, engine = Vision(args.calibration), QueueEngine()
    results, index = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = index/fps
        engine.observe(detector.detect(frame, t), t, t)
        s = engine.state(t)
        if index in labels:
            results.append(dict(frame_index=index, second=t, truth_count=labels[index],
                                estimated_count=s.count, valid=s.valid, abs_error=abs(s.count-labels[index])))
            cv2.putText(frame, f'M1 count={s.count} valid={s.valid} label={labels[index]}',
                        (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 255), 2)
            cv2.imwrite(str(out/f'frame_{index:06}.jpg'), frame)
        index += 1
    cap.release()
    if len(results) != len(labels):
        raise ValueError('One or more annotation frame indices exceed video length')
    with (out/'counts.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    valid = [r for r in results if r['valid']]
    summary = dict(annotated_frames=len(results), valid_frames=len(valid),
                   invalid_frames=len(results)-len(valid),
                   count_mae_valid=sum(r['abs_error'] for r in valid)/len(valid) if valid else None,
                   count_mae_all=sum(r['abs_error'] for r in results)/len(results),
                   target_mae=1.,
                   detection_precision_recall='NOT MEASURED: requires bounding-box labels and matching protocol',
                   timing='original video frame_index / FPS; offline processing, no real-time claim')
    (out/'metrics.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
