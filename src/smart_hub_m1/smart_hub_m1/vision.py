"""Documented simpler baseline: OpenCV HOG people detector + greedy tracking.

Requires user-supplied floor calibration. Not robust to dense crowds or long
occlusion. Detector scores are heuristic, not calibrated probabilities.
"""
import json
import math
from pathlib import Path
import cv2
import numpy as np


class Vision:
    def __init__(self, calibration_file):
        config = json.loads(Path(calibration_file).read_text())
        pixels = np.asarray(config['image_points'], dtype=np.float32)
        mapped = np.asarray(config['map_points'], dtype=np.float32)
        if pixels.shape != mapped.shape or pixels.ndim != 2 or pixels.shape[1] != 2 or len(pixels) < 4:
            raise ValueError('Need at least four matching 2D floor-plane point pairs')
        if not np.isfinite(pixels).all() or not np.isfinite(mapped).all():
            raise ValueError('Calibration coordinates must be finite')
        self.H, _ = cv2.findHomography(pixels, mapped, method=0)
        if self.H is None or abs(np.linalg.det(self.H)) < 1e-12:
            raise ValueError('Degenerate homography; use noncollinear floor points')
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.tracks, self.next_id = {}, 0

    def detect(self, frame, stamp):
        boxes, weights = self.hog.detectMultiScale(frame, winStride=(8, 8),
                                                  padding=(8, 8), scale=1.05)
        boxes = [tuple(map(int, b)) for b in boxes]
        scores = [float(w) for w in np.asarray(weights).reshape(-1)]
        # Explicit suppression avoids treating multiple boxes around one person as people.
        keep = cv2.dnn.NMSBoxes(boxes, scores, score_threshold=0., nms_threshold=.4)
        indices = np.asarray(keep).reshape(-1) if len(keep) else []
        detections = []
        for i in indices:
            x, y, w, h = boxes[int(i)]
            p = self.H @ np.array([x+w/2, y+h, 1.])
            if abs(p[2]) < 1e-9:
                continue
            point = p[:2]/p[2]
            confidence = 1/(1+math.exp(-max(-30., min(30., scores[int(i)]))))
            detections.append((float(point[0]), float(point[1]), confidence))
        self.tracks = {k:v for k,v in self.tracks.items() if 0 <= stamp-v[2] <= .5}
        pairs = sorted((math.dist((x, y), old[:2]), ident, idx)
                       for idx, (x, y, c) in enumerate(detections)
                       for ident, old in self.tracks.items())
        assigned, used = {}, set()
        for distance, ident, idx in pairs:
            if distance <= .8 and ident not in used and idx not in assigned:
                assigned[idx], used = ident, used | {ident}
        result = []
        for idx, (x, y, c) in enumerate(detections):
            if idx not in assigned:
                assigned[idx] = str(self.next_id)
                self.next_id += 1
            ident = assigned[idx]
            self.tracks[ident] = (x, y, stamp)
            result.append((ident, x, y, c))
        return result
