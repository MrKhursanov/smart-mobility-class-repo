"""ROS-independent M1 counting and forecasting logic; map units are metres."""
from dataclasses import dataclass
from collections import deque
import math
import numpy as np

QUEUE = ((2., 5.), (6., 5.), (6., 7.), (2., 7.))
CROSSING = ((4.5, 1.25), (5.5, 1.25), (5.5, 4.75), (4.5, 4.75))
FEATURE_NAMES = ['current', 'mean_last_10', 'change_10s',
                 'positive_count_changes_30s', 'negative_count_changes_30s']


def inside(point, polygon):
    """Ray casting, including the boundary."""
    x, y = point
    hit = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        ax, ay = a
        bx, by = b
        cross = (x-ax)*(by-ay) - (y-ay)*(bx-ax)
        if abs(cross) < 1e-9 and min(ax, bx)-1e-9 <= x <= max(ax, bx)+1e-9 and min(ay, by)-1e-9 <= y <= max(ay, by)+1e-9:
            return True
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay) + ax:
            hit = not hit
    return hit


@dataclass
class Track:
    first: float
    last: float
    point: tuple
    confidence: float
    confirmed: bool = False
    in_queue: bool = False
    pending_queue: bool = False
    zone_since: float = 0.


@dataclass
class Queue:
    stamp: float
    count: int
    confidence: float
    valid: bool
    crossing_occupied: bool


class QueueEngine:
    """Source time and receipt monotonic time must both advance normally.

    Repeated source stamps do not refresh the receipt watchdog. Empty frames
    are valid observations; missing/low quality frames are not empty frames.
    """
    def __init__(self, threshold=0.5, debounce=0.4, occlusion=0.5,
                 freshness=1., future_tolerance=0.1):
        self.threshold = threshold
        self.debounce = debounce
        self.occlusion = occlusion
        self.freshness = freshness
        self.future_tolerance = future_tolerance
        self.tracks = {}
        self.source = None
        self.receipt = None
        self.frame_valid = False
        self.clear_since = None
        self.crossing = True

    def observe(self, detections, stamp, received, source_now=None, frame_valid=True):
        source_now = stamp if source_now is None else source_now
        if not all(math.isfinite(v) for v in (stamp, received, source_now)):
            self.frame_valid = False
            return False
        if stamp-source_now > self.future_tolerance or source_now-stamp > self.freshness:
            self.frame_valid = False
            return False
        if self.source is not None and stamp <= self.source:
            return False
        # A feed gap cannot establish continuous crossing clearance.
        if self.receipt is not None and received-self.receipt > self.freshness:
            self.clear_since = None
            self.crossing = True
        self.source, self.receipt = stamp, received
        self.frame_valid = bool(frame_valid)
        if not frame_valid:
            self.clear_since = None
            self.crossing = True
            return False
        accepted = {}
        low_confidence = False
        for ident, x, y, confidence in detections:
            if not all(math.isfinite(v) for v in (x, y, confidence)) or not 0 <= confidence <= 1:
                self.frame_valid = False
                continue
            if confidence < self.threshold:
                low_confidence = True
                continue
            accepted[str(ident)] = (x, y, confidence)  # duplicate ID counted once
        if low_confidence:
            self.frame_valid = False  # uncertain observation is UNKNOWN, never an empty queue
        self.tracks = {k: v for k, v in self.tracks.items()
                       if stamp-v.last <= self.occlusion+1e-8}
        for ident, (x, y, confidence) in accepted.items():
            point = (x, y)
            in_q = inside(point, QUEUE)
            if ident not in self.tracks:
                self.tracks[ident] = Track(stamp, stamp, point, confidence,
                                          pending_queue=in_q, zone_since=stamp)
            tr = self.tracks[ident]
            tr.last, tr.point, tr.confidence = stamp, point, confidence
            if in_q != tr.pending_queue:
                tr.pending_queue, tr.zone_since = in_q, stamp
            if stamp-tr.first >= self.debounce-1e-8:
                tr.confirmed = True
            if stamp-tr.zone_since >= self.debounce-1e-8:
                tr.in_queue = in_q
        # Use any crossing detection immediately, before track confirmation.
        occupied = any(inside((x, y), CROSSING) for x, y, c in accepted.values())
        if occupied or not self.frame_valid:
            self.crossing, self.clear_since = True, None
        elif self.clear_since is None:
            self.clear_since = stamp
        elif stamp-self.clear_since >= 2.-1e-8:
            self.crossing = False
        return True

    def state(self, now, source_now=None):
        source_now = now if source_now is None else source_now
        fresh = (self.source is not None and self.receipt is not None
                 and 0 <= now-self.receipt <= self.freshness+1e-8
                 and -self.future_tolerance <= source_now-self.source <= self.freshness+1e-8)
        active = [v for v in self.tracks.values() if v.confirmed and v.in_queue
                  and self.source-v.last <= self.occlusion+1e-8]
        valid = bool(fresh and self.frame_valid)
        confidence = min((v.confidence for v in active), default=1.) if valid else 0.
        return Queue(self.source if self.source is not None else 0., len(active),
                     confidence, valid, self.crossing if valid else True)


def features(counts):
    """Count-only proxy: entries/exits cannot be recovered during simultaneous flow."""
    q = np.asarray(counts, dtype=float)
    if len(q) < 60 or not np.isfinite(q).all() or (q < 0).any():
        raise ValueError('Need 60 consecutive finite nonnegative one-second samples')
    delta = np.diff(q[-31:])
    return np.array([q[-1], q[-10:].mean(), q[-1]-q[-11],
                     np.maximum(delta, 0).sum(), np.maximum(-delta, 0).sum()])


def infer(model, x):
    if model.get('selected') == 'persistence':
        return float(x[0])
    return max(0., float(((x-np.array(model['mean']))/np.array(model['scale']))
                         @ np.array(model['coef']) + model['intercept']))


class Predictor:
    def __init__(self, model):
        self.model = model
        self.history = deque(maxlen=60)
        self.previous_tick = None

    def reset(self):
        self.history.clear()
        self.previous_tick = None

    def tick(self, count, valid, now):
        if not valid or not math.isfinite(count) or count < 0:
            self.reset()
            return None
        if self.previous_tick is not None and not 0.5 <= now-self.previous_tick <= 1.5:
            self.reset()
        self.previous_tick = now
        self.history.append(count)
        if len(self.history) < 60:
            return None
        x = features(self.history)
        return infer(self.model, x), float(count)
