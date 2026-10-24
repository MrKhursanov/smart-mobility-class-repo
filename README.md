# M1 - Passenger detection and demand prediction

Prepared for the Smart Mobility Hub assignment. This is the **M1 member subsystem** for S1 and S2, not the five-member integrated project. The assignment also calls its common site map "M1"; that is a separate use of the name.

## Start here

1. Read `docs/M1_Project_Report.pdf` for the project explanation and actual results.
2. Read `docs/M1_Explanation_Script.pdf` for the short speaking script, detailed walkthrough and defense answers.
3. Use the commands below to reproduce the portable experiments.
4. Give `docs/TEAM_HANDOFF.md` to M2/M5 before integration.

## What is delivered and what is still pending

- Implemented and locally executed: pure-Python tracking/counting, source/receipt freshness, crossing occupancy hold, causal features, ridge training, validation-based model selection, 30 synthetic episodes, held-out evaluation, CSV traces and 14 unit tests.
- Supplied, syntax checked, **not runtime verified here**: ROS 2 package definitions, 5 Hz queue node, 1 Hz demand node, test-track publishers, launch file and calibrated camera/video adapters. The separate OpenCV HOG Mall image benchmark was executed; see its failed-baseline result below.
- Still required on your team's system: ROS build/QoS/rate/bag evidence, actual calibrated video with >=100 manual frame labels, M2 dispatch/action and M5 crossing-stop integration. The implementation is not a claim that full T01-T04 or the team submission has passed.

## Run without ROS (Mac, Windows or Linux)

From this directory, with Python 3.10 or later:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
PYTHONPATH=src/smart_hub_m1 python3 -m unittest discover -s src/smart_hub_m1/test -v
python3 tools/run_experiments.py
```

Windows: activate `.venv\Scripts\activate`; set `PYTHONPATH` to `src/smart_hub_m1` using your shell. The training script sets its own import path. `numpy` is the only required non-ROS dependency.

`tools/run_experiments.py` regenerates data/model/evidence. It never reads a future count when constructing features. Data seeds are 1000-1029, split into 18/6/6 whole episodes. Model timing varies by machine; values reported in the PDFs describe the packaged run.

## ROS 2 Jazzy setup (Ubuntu 24.04)

Use the team's agreed ROS distribution. The following commands are supplied instructions, **not a successful build transcript**. Start with ROS 2 Jazzy and colcon already installed using the official ROS instructions.

```sh
source /opt/ros/jazzy/setup.bash
sudo apt install python3-numpy python3-opencv python3-pytest ros-jazzy-cv-bridge
mkdir -p ~/smart_hub_m1_ws/src
cp -R src/smart_hub_m1 src/smart_hub_interfaces ~/smart_hub_m1_ws/src/
cd ~/smart_hub_m1_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
ros2 launch smart_hub_m1 m1.launch.py scenario:=s1
```

In another sourced terminal:

```sh
ros2 topic echo /hub/queue
ros2 topic hz /hub/queue
ros2 topic info /hub/queue --verbose
ros2 topic echo /hub/demand
ros2 bag record -o m1_s1 /m1/observed_tracks /hub/queue /hub/demand
```

S1: spawn at 5/10 s, remove at 15 s, pedestrian at 20-24 s, freeze from 30 s. Counts stabilize after 0.4-0.5 s. Keep running to 40 s. **S1 is too short to warm the 60-second predictor; invalid forecasts throughout S1 are expected.**

Stop the first launch and start the separate six-minute S2 replay:

```sh
ros2 launch smart_hub_m1 m1.launch.py scenario:=s2
```

S2 feeds noisy synthetic observed counts through stable test IDs and the detector. It has detector debounce and transport timing; therefore its live forecast trace is not identical to the offline evaluation on one-second counts. Compare it separately. Restart nodes to reset state between runs; this M1-only package does not implement the team `/scenario/reset` service.

**Shared interface package:** the supplied `smart_hub_interfaces` contains the two exact M1 public messages plus two explicitly local test messages. If your team already has this package, merge the message files and CMake entries into it. Do not create a second package of the same name or replace your teammates' services/actions. M1 application code is under the distinct package name `smart_hub_m1`.

After regenerating the trained model, refresh its installed package copy before building:

```sh
cp models/demand_model.json src/smart_hub_m1/models/demand_model.json
```

Record OS, ROS distribution, RMW implementation, Python/NumPy/OpenCV versions, commit hash and configuration. Run `colcon test --packages-select smart_hub_m1` and `colcon test-result --verbose`. Add the team's required ament style checks and launch_testing tests; those checks are not certified by the portable unittest run.

## Real-video path

Obtain a fixed-view lab video and measure at least four noncollinear floor-plane correspondences. Copy `src/smart_hub_m1/config/calibration.template.json` to a working file and replace all null pixel values. The provided map points are queue corners; use additional correspondences covering the crossing to reduce extrapolation error. Never use the template unchanged. Homography is valid only on the calibrated ground plane.

Create a CSV with `frame_index,count` and at least 100 unique zero-based original-frame indices. Label actual queue occupancy manually, including partial occlusion. No sample labels have been invented.

```sh
python3 -m pip install 'opencv-python>=4.8,<5'
python3 tools/evaluate_video.py --video lab.mp4 --calibration calibration.json --labels labels.csv
```

The offline tool generates annotated frame images, count errors and validity coverage. It processes the original video timestamps. Detection precision/recall requires additional bounding-box labels; count-only labels cannot establish it. HOG's raw score is mapped by a sigmoid to a heuristic confidence. This is a simpler documented baseline, not a calibrated detection probability or a claimed high-accuracy crowd detector.

To replay video through ROS, start these in three separate sourced terminals, with the predictor optional:

```sh
ros2 run smart_hub_m1 passenger_detector --ros-args -p input_mode:=video -p calibration_file:=/absolute/path/calibration.json
ros2 run smart_hub_m1 video_source --ros-args -p video_file:=/absolute/path/lab.mp4
ros2 run smart_hub_m1 demand_predictor
```

The ROS source publishes sequential frames at 10 Hz, so a 30 FPS input plays three times slower. Stamps describe replay observation times, not the original recording's wall-clock acquisition. It stops at EOF to expose stale-feed handling. This is a replay demonstration, not real-time camera performance. Synchronous HOG inference may reduce throughput; measure the actual frame processing rate on your machine.

## File map

- `core.py`: polygon test, track confirmation, queue/crossing state, features and prediction history.
- `scenario.py`: deterministic test observations.
- `nodes.py`: ROS adapters and publishers.
- `vision.py`: HOG detection, homography and greedy identity association.
- `tools/run_experiments.py`: synthetic data generation, ridge fit, evaluation and charts.
- `tools/evaluate_video.py`: actual labeled-video evaluation when inputs are available.
- `test/test_core.py`: 14 portable checks.
- `data/`, `models/`, `evidence/`: reproducible inputs, learned coefficients and measured results.

Original newly authored code is MIT licensed; dependency licenses remain with their projects. The professor's PDFs and any personal video are not bundled. Replace package maintainer placeholder details with your own details before submission.

## Downloaded real dataset (added at your request)

The original university-hosted **Mall dataset** is saved as `data/external/mall_dataset.zip` (91,833,998 bytes; about 92 MB). It has 2,000 real 640x480 images and publisher manual head/count annotations. It is research-only and noncommercial; its terms are separate from this project's MIT code license. See `docs/DATASET_CARD.md` for source, attribution, checksum and benchmark limits.

The downloadable project ZIP excludes the large archive; the dataset archive is provided separately beside it. After unzipping the project, put the supplied `mall_dataset.zip` in `data/external/`, or download it with the script below.

```sh
python3 -m pip install -r requirements-real-data.txt
python3 tools/download_mall.py
python3 tools/benchmark_mall.py
```

The benchmark uses 100 fixed, evenly spaced images. Red crosses show the publisher's head annotations; yellow boxes show HOG detections; the green boundary is the publisher ROI. Inspect the output in `evidence/mall_benchmark/annotated_frames/`. Full label counts are exported for all 2,000 frames. No model is fitted to these benchmark images.

This real-image crowd benchmark supplements S1. It is not map-calibrated queue occupancy, has no independent demand episodes and has no exact 30-second timing contract. Keep the original synthetic S1/S2 tests. A student manual review of the annotations and a calibrated queue video are still needed before claiming the assignment's full video requirement.

Measured real-image baseline: HOG count MAE **25.51 people**, RMSE **26.15**, on the fixed 100-image Mall sample. This is a poor baseline and does not meet the one-person accuracy target. See the report and dataset card; no real-world accuracy success is claimed.
