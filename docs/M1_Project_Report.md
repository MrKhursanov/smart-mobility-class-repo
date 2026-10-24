# Smart Mobility Hub | M1

Passenger detection, queue tracking and thirty-second demand forecasting

Prepared 24 October 2026. Scope: member M1, scenarios S1 and S2. The supplied work is an implementation and explanation package for your subsystem. It is not the full five-person hub or a completed claim of all graded evidence.

## 1. What your task does

Your subsystem answers two questions: how many passengers are waiting now, and how many may be waiting thirty seconds from now? It provides observations and forecasts to the coordinator, dashboard and safety components.

The current queue count comes from tracked passenger positions inside a defined queue area. A separate crossing flag tells downstream components whether pedestrians occupy the crossing. A predictor converts recent valid counts into a future-demand estimate, while always publishing a persistence baseline for comparison.

The assignment's member M1 owns detector, tracking, demand features, model training and S1/S2 experiments. M2 owns dispatch and the bus/coordinator. M5 supplies simulator and safety integration. Your independent cross-review is M3 state validity. The common site is also named map M1; that name does not change your member responsibilities.

## 2. Requirements traced to implementation

The source assignment's sections 8 and 9 define S1/S2. Sections 4-6 define node/topic/message contracts; section 21 defines tests and metrics; sections 23-24 define ownership and submission. Handbook section 4.1-4.2 gives the companion build order and clarifies the M2 dispatch handoff.

- S1 input: synthetic stable-ID observations for deterministic tests, plus a calibrated camera/video demonstration.
- S1 output: QueueState on /hub/queue, nominal 5 Hz, reliable depth 10; original observation stamp and map frame.
- Counting: track IDs, current polygon occupancy, 0.4 s confirmation, short occlusion tolerance of 0.5 s, no unbounded stale tracks.
- Crossing: independent region check, immediate conservative occupancy indication, 2 s continuous clear hold before release indication.
- Freshness: source and receipt age checks; missing or low-confidence observations are invalid rather than valid zero.
- S2 output: DemandPrediction on /hub/demand, nominal 1 Hz, thirty-second horizon, selected model and persistence values, model ID and validity.
- Training: at least thirty independent six-minute episodes, whole-episode 60/20/20 split, causal features, training-only scaling and validation-only model selection.
- Evidence: T01-T04 contribution, held-out MAE/RMSE, inference timing, model failure examples, actual video labels and integrated response.

## 3. Architecture and message flow

Synthetic map tracks OR camera images -> passenger_detector -> /hub/queue -> demand_predictor -> /hub/demand -> M2 coordinator -> bus action.

/hub/queue also goes directly to M2/M5 for crossing and safety decisions. The detector does not command motors. Forecasts never grant crossing ownership or override a safety stop.

The public QueueState contains a header, zone_id, count, confidence, valid and crossing_occupied. DemandPrediction contains a header, horizon_sec, predicted_count, baseline_count, model_id and valid. These exact fields match the assignment. Two extra M1Track messages are explicitly test-adapter interfaces, not replacements for public assignment types.

The supplied interface package is only an M1 subset. During team integration, merge it into the existing shared smart_hub_interfaces package. Do not overwrite teammates' message, service or action definitions.

## 4. Source structure and control flow

core.py separates all portable domain logic from ROS. QueueEngine accepts observations, maintains track confirmation and polygon membership, and exposes a current state with freshness checks. Predictor maintains sixty one-second samples, clears history on invalid data/gaps and calls the selected model after warm-up. The inside function handles polygon boundaries explicitly.

nodes.py supplies ROS adapters. PassengerDetector subscribes to one chosen input and publishes queue state every 0.2 s. DemandPredictor consumes that stream and publishes every second. The state publishers use steady timers for local checks, while preserving ROS source stamps in messages. SyntheticTracks supplies deterministic S1 or episode-based S2 input. VideoSource is an optional prerecorded-image publisher.

vision.py uses OpenCV's built-in HOG person detector, nonmaximum suppression, homography and greedy nearest-position association. This is a documented simpler baseline allowed by the assignment. It is supplied but unexecuted here. Dense crowds, overlapping people, bad calibration and nearby crossing tracks can cause errors or ID switches.

tools/run_experiments.py creates the data split, fits ridge coefficients, chooses a policy using validation, evaluates held-out episodes and saves full CSV/JSON evidence and SVG charts. tools/evaluate_video.py evaluates actual manually labeled video after those inputs are provided. README.md contains execution commands; docs/TEAM_HANDOFF.md defines integration responsibilities.

## 5. Passenger counting and validity

Queue Q is x in [2,6], y in [5,7] metres. Crossing C is x in [4.5,5.5], y in [1.25,4.75]. Synthetic observations already use map coordinates. Video detections require a floor-plane homography from at least four noncollinear measured point pairs. Use the bottom-centre of the bounding box as the ground foot-point.

A track must persist for 0.4 s before it is confirmed. Queue-entry/exit boundaries are debounced. A short missing observation retains identity up to 0.5 s; longer disappearance expires it. Duplicate IDs in a frame count once. The queue count is occupancy, not cumulative entries.

Crossing detections inhibit clearance immediately, before confirmation. Continuous valid clear frames must span two seconds before crossing_occupied becomes false. A long observation gap restarts that proof. Invalid data conservatively reports crossing occupied, but downstream components must also honor valid=false.

Both source age and local monotonic receipt age must be within one second. Repeated source stamps do not refresh receipt time. Out-of-order frames are ignored; future timestamps beyond 0.1 s and malformed/uncertain observations cannot establish fresh valid state. Old numeric counts may remain visible with valid=false. Consumers must check validity before thresholding.

## 6. Deterministic S1 experiment

The forty-second observation scenario begins empty. Three tracks appear at t=5 s, two more at t=10 s and one leaves at t=15 s. One existing passenger is occluded for 0.3 s at t=12 s. A crossing pedestrian appears at t=20 s and leaves at t=24 s. New observations stop at t=30 s.

Stable counts are 0, 3, 5 and 4 after debounce. The 0.3 s occlusion preserves count. The crossing remains occupied during the pedestrian event and through the two-second clear hold. The final accepted source frame is t=29.9 s; the first invalid state is t=31.0 s, one second after the freeze begins and within the required 1.2 s.

[[S1_CHART]]

Evidence: evidence/s1_trace.csv and evidence/s1_count.svg. This is algorithm-level synthetic evidence. It demonstrates the occupancy signal, not zero physical crossing conflicts or actual vehicle stopping; those require M2/M5 integration.

## 7. Prediction features and learning

At one-second samples, the feature vector is [current count, mean of last ten counts, current minus ten-seconds-ago count, sum of positive changes over thirty seconds, sum of negative changes over thirty seconds]. All features use present and past observations only. Sixty consecutive valid samples are required before any valid prediction.

The change sums are explicitly labeled proxies for arrivals/departures. Simultaneous entry and exit can cancel, so they cannot recover exact flows. This is the assignment's permitted count-only alternative; a future track-event extension should preserve those distinctions rather than silently relabel proxies as ground truth.

Persistence predicts the current count thirty seconds ahead. Ridge fits a weighted linear model with an L2 penalty. Features are standardized with training-only mean/scale. Predictions are clamped at zero; fractional values represent expected queue size. Candidate regularization strengths are 0.01, 0.1, 1, 10, 100 and 1000. Validation MAE selects alpha=0.01. The saved policy also compares the best ridge against persistence on validation and selects persistence if it is better.

The generator creates thirty independent 360-second episodes (361 samples including both endpoints) with varying arrivals, boarding intervals and observation noise. Its private future schedule is never a feature. Seeds 1000-1017 train, 1018-1023 validate and 1024-1029 test. Whole episodes are split before overlapping windows. There are 4,896 training windows, 1,632 validation windows and 1,632 held-out windows.

The synthetic observations include occasional +/-1 count noise. Future true counts are labels only. This evaluates forecasting from simplified noisy counts; it does not establish real-video detection quality or complete end-to-end transport performance.

## 8. Measured S2 results

[[RESULTS_TABLE]]

The ridge MAE is approximately 27.9% lower than persistence on this fixed synthetic test set. Windows overlap within each episode, so six episodes are the independent experimental units; 1,632 is the number of evaluated windows, not independent trials. Individual episode metrics are retained in evidence/results.json.

[[S2_CHART]]

Failure remains visible: on test seed 1027, ridge MAE is 1.79 while persistence MAE is 1.12. On seed 1024, ridge MAE is 3.29 versus 3.25 for persistence. Do not claim the trained model always wins. The selected validation policy is fixed before test evaluation; it is not retroactively changed for an unfavorable test episode.

A 2,000-call model-only timing sample on this Mac/ARM Python 3.12.14, NumPy 2.3.5 environment gave p95 around 0.0045 ms. This excludes feature generation, person detection, ROS scheduling and transport. It does not certify the assignment's end-to-end pipeline latency; remeasure the required scope on the deployment machine.

No waiting-time gain is claimed. M2/M5 must run paired reactive/predictive dispatch on identical episodes, measure queue-entry-to-boarding times and report passengers still waiting at the end as censored.

## 9. Real data downloaded and evaluated

At your request, the original university-hosted Mall dataset has been downloaded: 2,000 real 640x480 pedestrian images with manual head/count annotations, a region mask and perspective information. The verified archive is 91,833,998 bytes (about 92 MB). Its SHA-256 and research-only attribution are recorded in docs/DATASET_CARD.md. No Kaggle login is needed.

A supplementary benchmark runs the HOG baseline on 100 fixed, evenly spaced images. Counts use the publisher ROI, filtering each detected box by an approximate head position. Publisher head annotations and HOG boxes are shown in the 100 output images. This benchmark measures crowd counting in the mall scene, not geometrically mapped queue occupancy.

Measured MAE is 25.51 people and RMSE is 26.15 people. Detection-call p95 is about 37.63 ms on this machine with OpenCV 4.14.0; it excludes image reading, overlay drawing and ROS. The simple detector misses distant and overlapping people, so this is an explicitly failed baseline, not acceptable real-world perception or a one-person MAE success. Improve the detector and evaluate again before claiming deployment quality.

The source gives a cadence below 2 Hz without the exact timeline needed here. A single mall scene cannot supply thirty independent six-minute demand episodes. Keep the required synthetic S2 experiment; do not label the mall count sequence as thirty-second queue forecasts. Student manual review, actual floor calibration and queue/crossing demonstration remain pending. Full original archive, benchmark code, 100 labeled-result images, all 2,000 count labels and measured CSV/JSON are supplied.

## 10. Testing status and honest submission boundary

Fourteen portable unit tests executed successfully. Coverage includes polygon boundary/outside, known counts/freeze, short occlusion/duplicate IDs, disappearance expiry, repeated-stamp freeze, future/out-of-order/malformed observations, low confidence, immediate crossing occupancy/clear hold, long-gap clearance reset, queue-boundary debounce, exact causal features, invalid history, warm-up/stale recovery and sample-gap reset.

- T01: portable stable-count checks passed; ROS timing and recorded plot/bag correlation remain pending.
- T02: portable occlusion, repeated stamp and freeze logic passed; real-video >=100 labeled-frame accuracy and integrated crossing inhibition remain pending.
- T03: synthetic episode split, training, baseline comparison and held-out metrics executed; ROS inference timing and deployment reproducibility remain pending.
- T04: M2 handoff contract supplied; actual outstanding-action, fallback, cooldown and hysteresis integration is not executed or certified.
- Full S8/S9 safety, hardware and all other members' scenarios are outside this M1 package. No such success is claimed.

ROS 2 and pytest are not installed in the authoring runtime. OpenCV and SciPy were installed in a temporary task environment for the executed Mall benchmark. The ROS adapters and calibrated camera pipeline remain unexecuted; Python syntax has been checked. Portable tests use unittest, which pytest can discover in the target environment. Team-required ament style checks and launch_testing integration remain to be added/run on the team host.

## 11. What you need to finish with the team

Start with README.md and reproduce portable tests. Build the packages on the team's agreed Jazzy/Humble installation, inspect generated public messages and measure topic rates/QoS. Capture S1 for forty seconds, then run a separate six-minute S2 episode: S1 freezes before the sixty-second predictor warm-up, so invalid demand throughout S1 is expected.

Provide a fixed-view video, actual homography measurements and at least 100 manually labeled queue-count frames. Include partially occluded people and keep count error separate from invalid-frame coverage. If detection precision/recall is reported, annotate boxes and define matching criteria as well; count labels alone are insufficient.

Integrate M2 dispatch with the required three high forecasts, one outstanding mission, thirty-second cooldown, five low forecasts to clear and fresh observed-queue fallback. Demand never overrides safety. Integrate M5 observed input, reset, private evaluator truth and crossing-stop evidence. Restart the M1 launch between standalone tests; the shared reset service belongs to team integration.

Review M3 state validity using the handoff checklist and document the actual finding/commit. Replace package maintainer placeholders with your details, capture commit/version/configuration IDs and preserve failures in the report. Add your actual ROS/video evidence and contribution record before claiming final submission readiness.

## 12. Source documents and technical references

Primary assignment: Smart_Mobility_Hub_Assignment (1).pdf, PDF pages 6-10, 15-16, 30, 33-35 (printed sections 4-9, 21, 23-24). Requirements take precedence over companion examples.

Companion: Smart_Mobility_Hub_ROS2_Implementation_Handbook.pdf, PDF pages 4-11 and 16-22, particularly S1/S2, the responsibility map and readiness checklist. The handbook explicitly says its reference code is not a complete assessed ROS system.

ROS references for target-machine verification: https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html and the official Python publisher/subscriber tutorial. Access to those full documentation pages was blocked in this environment; no unverified API-runtime success is inferred from that lookup.

Newly authored source is under MIT license. OpenCV's built-in HOG model and other dependencies retain their upstream licenses. The professor's documents and personal video are not redistributed inside this package.

Mall dataset source: https://staff.ie.cuhk.edu.hk/~ccloy/downloads_mall_dataset.html . Cite K. Chen, C. C. Loy, S. Gong and T. Xiang, "Feature Mining for Localised Crowd Counting," BMVC 2012. Dataset use is research-only and noncommercial, separate from the MIT code license.
