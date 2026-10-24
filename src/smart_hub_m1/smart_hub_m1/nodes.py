"""ROS 2 adapters. Runtime integration must be verified on the team's Jazzy host."""
import json
import math
import time
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.clock import Clock, ClockType
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from smart_hub_interfaces.msg import QueueState, DemandPrediction, M1Track, M1TrackArray
from .core import QueueEngine, Predictor
from .scenario import observations


def seconds(stamp):
    return stamp.sec + stamp.nanosec/1e9


def set_stamp(header, value):
    ns = int(round(value*1e9))
    header.stamp.sec, header.stamp.nanosec = divmod(ns, 1000000000)


class PassengerDetector(Node):
    def __init__(self):
        super().__init__('passenger_detector')
        mode = self.declare_parameter('input_mode', 'synthetic').value
        confidence = float(self.declare_parameter('confidence_threshold', .5).value)
        if not 0 <= confidence <= 1 or mode not in ('synthetic', 'video'):
            raise ValueError('input_mode must be synthetic/video; confidence must be [0,1]')
        self.engine = QueueEngine(threshold=confidence)
        self.pub = self.create_publisher(QueueState, '/hub/queue', 10)
        if mode == 'synthetic':
            self.create_subscription(M1TrackArray, '/m1/observed_tracks', self.on_tracks, 10)
        else:
            from .vision import Vision
            from cv_bridge import CvBridge
            calibration = self.declare_parameter('calibration_file', '').value
            self.vision, self.bridge = Vision(calibration), CvBridge()
            self.create_subscription(Image, '/camera/image_raw', self.on_image, qos_profile_sensor_data)
        self.steady = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(.2, self.publish_state, clock=self.steady)

    def on_tracks(self, msg):
        if msg.header.frame_id != 'map':
            self.engine.frame_valid = False
            return
        self.engine.observe([(t.track_id, t.x, t.y, t.confidence) for t in msg.tracks],
                            seconds(msg.header.stamp), time.monotonic(),
                            self.get_clock().now().nanoseconds/1e9, msg.valid)

    def on_image(self, msg):
        stamp = seconds(msg.header.stamp)
        # Do not run inference again on duplicate/frozen source timestamps.
        if self.engine.source is not None and stamp <= self.engine.source:
            return
        try:
            image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            detections = self.vision.detect(image, stamp)
            self.engine.observe(detections, stamp, time.monotonic(),
                                self.get_clock().now().nanoseconds/1e9)
        except Exception as exc:
            self.engine.frame_valid = False
            self.get_logger().error(f'Image processing failed: {exc}')

    def publish_state(self):
        state = self.engine.state(time.monotonic(), self.get_clock().now().nanoseconds/1e9)
        msg = QueueState()
        set_stamp(msg.header, state.stamp)
        msg.header.frame_id, msg.zone_id = 'map', 'Q'
        msg.count, msg.confidence = state.count, state.confidence
        msg.valid, msg.crossing_occupied = state.valid, state.crossing_occupied
        self.pub.publish(msg)


class DemandPredictor(Node):
    def __init__(self):
        super().__init__('demand_predictor')
        from ament_index_python.packages import get_package_share_directory
        default = str(Path(get_package_share_directory('smart_hub_m1'))/'models/demand_model.json')
        path = self.declare_parameter('model_path', default).value
        self.predictor = Predictor(json.loads(Path(path).read_text()))
        self.latest = None
        self.received = None
        self.create_subscription(QueueState, '/hub/queue', self.on_queue, 10)
        self.pub = self.create_publisher(DemandPrediction, '/hub/demand', 10)
        self.steady = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(1., self.tick, clock=self.steady)

    def on_queue(self, msg):
        stamp = seconds(msg.header.stamp)
        if self.latest is not None and stamp < seconds(self.latest.header.stamp):
            return
        # Preserve invalidity even when it refers to the same old observation.
        if self.latest is not None and stamp == seconds(self.latest.header.stamp):
            if not msg.valid:
                self.latest = msg
            return
        self.latest, self.received = msg, time.monotonic()

    def tick(self):
        q, now = self.latest, time.monotonic()
        source_now = self.get_clock().now().nanoseconds/1e9
        valid = bool(q is not None and q.valid and q.zone_id == 'Q' and q.header.frame_id == 'map'
                     and math.isfinite(q.confidence) and q.confidence >= .5
                     and self.received is not None and now-self.received <= 1.
                     and -.1 <= source_now-seconds(q.header.stamp) <= 1.)
        result = self.predictor.tick(q.count if q is not None else 0, valid, now)
        msg = DemandPrediction()
        # New computation does not make an old input observation fresh.
        if q is not None:
            msg.header.stamp = q.header.stamp
        msg.header.frame_id = 'map'
        msg.horizon_sec = 30
        msg.model_id = self.predictor.model['model_id']
        msg.valid = result is not None
        msg.predicted_count, msg.baseline_count = result if result is not None else (0., 0.)
        self.pub.publish(msg)


class SyntheticTracks(Node):
    def __init__(self):
        super().__init__('m1_synthetic_tracks')
        self.mode = self.declare_parameter('scenario', 's1').value
        if self.mode not in ('s1', 's2'):
            raise ValueError('scenario must be s1 or s2')
        self.rows = None
        if self.mode == 's2':
            from ament_index_python.packages import get_package_share_directory
            import csv
            default = str(Path(get_package_share_directory('smart_hub_m1'))/'data/episode_1024.csv')
            path = self.declare_parameter('episode_file', default).value
            with open(path) as f:
                self.rows = list(csv.DictReader(f))
        self.pub = self.create_publisher(M1TrackArray, '/m1/observed_tracks', 10)
        self.start = time.monotonic()
        self.create_timer(.1, self.tick)

    def tick(self):
        t = time.monotonic()-self.start
        if self.mode == 's1':
            if t >= 30.:
                return  # no new frame: required freeze test
            detections, _ = observations(t)
        else:
            if int(t) >= len(self.rows):
                return
            count = int(self.rows[int(t)]['observed_count'])
            detections = [(str(i), 2.2+(i % 8)*.45, 5.2+(i//8)*.25, .95) for i in range(count)]
            # Large counts are a synthetic density abstraction; not a physical crowd simulator.
            detections = [(i, x, min(y, 6.8), c) for i, x, y, c in detections]
        msg = M1TrackArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id, msg.valid = 'map', True
        for ident, x, y, confidence in detections:
            tr = M1Track()
            tr.track_id, tr.x, tr.y, tr.confidence = ident, x, y, confidence
            msg.tracks.append(tr)
        self.pub.publish(msg)


class VideoSource(Node):
    """Replay sequential frames at 10 Hz; video timeline is source sequence, not live data."""
    def __init__(self):
        super().__init__('m1_video_source')
        import cv2
        from cv_bridge import CvBridge
        path = self.declare_parameter('video_file', '').value
        self.capture = cv2.VideoCapture(path)
        if not self.capture.isOpened():
            raise ValueError(f'Cannot open video: {path}')
        self.bridge = CvBridge()
        self.pub = self.create_publisher(Image, '/camera/image_raw', qos_profile_sensor_data)
        self.timer = self.create_timer(.1, self.tick)

    def tick(self):
        success, frame = self.capture.read()
        if not success:
            self.timer.cancel()  # do not loop or refresh an old frame at EOF
            self.capture.release()
            return
        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_optical_frame'
        self.pub.publish(msg)


def spin(cls, args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = cls()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def detector_main(args=None):
    spin(PassengerDetector, args)


def predictor_main(args=None):
    spin(DemandPredictor, args)


def synthetic_main(args=None):
    spin(SyntheticTracks, args)


def video_main(args=None):
    spin(VideoSource, args)
