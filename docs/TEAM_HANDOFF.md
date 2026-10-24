# M1 integration handoff

## Ownership

M1 owns `passenger_detector` and `demand_predictor`, S1/S2 algorithm tests and experiments, model/data provenance, and independent review of M3 state validity. M2 owns dispatch policy, `/bus/dock` action-client lifecycle and crossing arbitration. M5 supplies simulator observations, independent truth, safety response, launch/logging and overall resets.

This package has **no motor-command publisher**. Crossing occupancy is evidence for M2/M5, not permission to move. A fresh clear flag still requires the arbiter's ownership and safety checks.

## Exact public topics

`/hub/queue`: `smart_hub_interfaces/msg/QueueState`, reliable volatile depth 10, nominal 5 Hz, `header.frame_id=map`, `zone_id=Q`. Header stamp is the latest accepted source observation time. `count` is current confirmed queue occupancy, not cumulative entries. `confidence` is a heuristic minimum accepted-track score (empty valid scene: 1). Check `valid` and freshness before using any numeric field. Old counts may remain numerically visible with `valid=false`. Invalid perception conservatively sets `crossing_occupied=true`.

`/hub/demand`: `smart_hub_interfaces/msg/DemandPrediction`, reliable volatile depth 10, nominal 1 Hz, horizon 30 seconds. `predicted_count` is the selected model forecast, `baseline_count` is persistence, and `model_id` identifies serialized parameters/policy. Fractional demand is an expectation, not an integer detection count. Header preserves latest input observation time. During warm-up/gaps, `valid=false`; zeros then are invalid placeholders, not zero demand.

`/m1/observed_tracks`: test-only reliable depth 10 `M1TrackArray`. Coordinates already in metres/map, stable IDs and synchronized header; no hidden truth. Use this adapter or camera input, never both simultaneously. Image input uses sensor-data QoS.

## M2 policy to integrate and verify as T04

1. Reject stale/future/invalid demand before thresholding. Use source and local receipt age.
2. Count three consecutive valid predictions >=6 before escalation.
3. Only request DockBus when bus is available, no goal/request is outstanding, and 30 s cooldown elapsed.
4. Set the outstanding reservation **before** asynchronous goal send; preserve it until acceptance/rejection/result resolves. Rejection and exceptions must release it deterministically, with bounded retry policy.
5. Reset escalation only after five consecutive valid predictions below 4. A stale/invalid sample must break the consecutive-sample streak.
6. If forecast is unavailable, use documented fallback on fresh valid observed queue >=6. Mark reason FALLBACK; stale queue cannot trigger fallback. Apply the same mission-exclusivity and cooldown guards.
7. Record reason, source stamps, correlation/goal IDs, acceptance/rejection, completion and cancel status in the team's `HubEvent` logger.
8. Demand cannot override crossing ownership, safety latch, door interlock or motion clearance.

Test rising, steady, noisy threshold sequences and feed gaps. Verify one outstanding mission and no dispatch from invalid forecast. Queue fallback is a distinct authorized decision, not a use of an invalid forecast.

## M5 inputs/evidence required

- Integrate reset by reinitializing all M1 histories/track IDs or restarting these nodes under team orchestration. The standalone launch uses wall time and node restart resets.
- Add observed tracks/camera data to scenario runner; retain private truth only in evaluator.
- Capture queue 5 Hz, demand 1 Hz, compatible QoS, original stamps and freeze recovery.
- Make a crossing pedestrian visibly inhibit candidate motion and verify zero physical/resource conflicts over the team runs. The M1 synthetic test verifies the occupancy flag only.
- Run a six-minute S2 replay separately from the 40-second S1 fault test.
- Compare reactive and predictive waiting times on identical seeds, with censored waiting passengers recorded. These transport results are not provided by M1 forecast accuracy.

## M1 independent review of M3

Ask M3 for a trace proving: startup UNKNOWN; low confidence/stale remains UNKNOWN; TTL removes reservation only, never physical occupancy; occupied/stale slots cannot be allocated; duplicate request payload returns same result; conflicting key reuse fails; simultaneous reservations have one winner; wrong token fails; traffic freeze does not become empty road. Record the actual code commit and review finding. This document is a review checklist, not evidence that another member's code has been reviewed.
