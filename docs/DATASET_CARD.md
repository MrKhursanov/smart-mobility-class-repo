# Downloaded real dataset: Mall

## Provenance and permitted use

Original publisher page: https://staff.ie.cuhk.edu.hk/~ccloy/downloads_mall_dataset.html

Original download: https://staff.ie.cuhk.edu.hk/~ccloy/files/datasets/mall_dataset.zip

Downloaded 24 October 2026 into `data/external/mall_dataset.zip`. Verified size: 91,833,998 bytes. SHA-256: `21baea1066ea1473289c28c2f9fc8440cea3c8d8905b83a66529fbef184d47e3`.

The university page permits research use and excludes commercial use. Cite the authors when using this dataset in academic work. The project's MIT license applies to newly authored code, not to the dataset. No Kaggle account or API key was used.

Dataset citation: K. Chen, C. C. Loy, S. Gong and T. Xiang, "Feature Mining for Localised Crowd Counting," British Machine Vision Conference, 2012. The publisher also lists related CVPR/ICCV 2013 work on the source page.

## Actual archive contents checked

- 2,000 JPEG images, 640x480, `mall_dataset/frames/seq_000001.jpg` through `seq_002000.jpg`.
- `mall_gt.mat`: 2,000 manual count labels and per-frame head coordinates.
- `perspective_roi.mat`: publisher ROI mask and perspective-normalization map.
- `mall_feat.mat` and `demo.m`: original feature/example materials.

The source describes the frame cadence as below 2 Hz, rather than supplying the exact timing required for the assignment's thirty-second horizon. Do not silently assume 1 Hz or 2 Hz. The single mall scene is not thirty independent six-minute demand episodes.

## Evaluation actually executed

`tools/benchmark_mall.py` selects 100 evenly spaced frame indices across all 2,000 images, using a fixed rule before evaluation. It uses OpenCV 4.14.0 HOG's default pretrained people detector, an 8x8 scan stride, 1.05 scale factor and NMS overlap threshold 0.4. No threshold tuning or fitting is performed on these images.

To align with head-based labels, detections are admitted to the publisher ROI using an approximate head point at horizontal box centre and vertical top plus 10% of box height. This approximation introduces its own boundary error and is not the foot-point mapping used by the separate map-calibrated queue task.

Actual count MAE: **25.51 people**. Count RMSE: **26.15 people**. Detection-call p95: about **37.63 ms** on this machine, excluding image reading, annotation drawing and ROS. Timing can vary on rerun. The benchmark does **not** meet a one-person MAE target.

This documents a failed simple baseline under dense/far-person conditions, not evidence of acceptable deployed perception. It motivates replacing HOG with a stronger person detector or crowd model, calibrating the actual scene, and reevaluating on a held-out set. The project does not claim that improvement has already been achieved.

Outputs: `evidence/mall_benchmark/metrics.json`, 100 count/error rows, all 2,000 publisher counts as CSV and 100 images with publisher head crosses (red), detected boxes (yellow) and ROI boundary (green). The original images remain in the verified archive.

## Relationship to the assignment

Useful for: a reproducible real-image counting baseline, visible occlusion/scale failures and a manual review pack of 100 publisher-labeled images.

Insufficient for: verified floor homography to the assignment map, actual queue membership, precise passenger arrival/departure events, track-ID continuity tests, thirty independent demand episodes, exact thirty-second real forecasting, bus response or crossing-stop safety.

Publisher labels are not a claim that the student personally annotated the images. Review them manually and record any label issues. For the complete S1 video requirement, agree with the professor whether this external benchmark plus a calibrated lab queue demonstration is sufficient.

Keep the required seeded synthetic S1/S2 experiments unchanged. The real dataset is an additional evidence source, not a substitute for the professor's acceptance scenarios.
