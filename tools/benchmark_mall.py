"""Supplementary real-image benchmark, distinct from map queue/tracking tests.

Uses publisher-provided count labels. No model is trained/tuned on these images.
Filters box-derived head estimates with the publisher ROI. No map calibration or queue ROI is claimed.
"""
import argparse
import csv
import hashlib
import io
import json
import platform
import time
import zipfile
from pathlib import Path
import cv2
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://staff.ie.cuhk.edu.hk/~ccloy/downloads_mall_dataset.html'
URL = 'https://staff.ie.cuhk.edu.hk/~ccloy/files/datasets/mall_dataset.zip'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive', default=str(ROOT/'data/external/mall_dataset.zip'))
    p.add_argument('--output', default=str(ROOT/'evidence/mall_benchmark'))
    args = p.parse_args()
    archive, output = Path(args.archive), Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'annotated_frames').mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        gt_name = next(n for n in names if n.endswith('mall_gt.mat'))
        gt = loadmat(io.BytesIO(z.read(gt_name)), simplify_cells=True)
        counts = np.asarray(gt['count']).reshape(-1)
        roi_name = next(n for n in names if n.endswith('perspective_roi.mat'))
        roi = loadmat(io.BytesIO(z.read(roi_name)), simplify_cells=True)['roi']['mask']
        frames = sorted(n for n in names if n.lower().endswith('.jpg') and '/frames/' in n)
        if len(frames) != len(counts) or len(frames) != 2000:
            raise ValueError(f'Unexpected alignment: {len(frames)} frames, {len(counts)} counts')
        with (output/'all_publisher_counts.csv').open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['frame_number_1based', 'image', 'publisher_count'])
            writer.writerows((i+1, name, int(counts[i])) for i,name in enumerate(frames))
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        rows = []
        for i in np.linspace(0,len(frames)-1,100,dtype=int):
            image = cv2.imdecode(np.frombuffer(z.read(frames[int(i)]),dtype=np.uint8), cv2.IMREAD_COLOR)
            before = time.perf_counter()
            boxes, weights = hog.detectMultiScale(image, winStride=(8,8), padding=(8,8), scale=1.05)
            boxes = [list(map(int,b)) for b in boxes]
            scores = [float(v) for v in np.asarray(weights).reshape(-1)]
            keep = cv2.dnn.NMSBoxes(boxes,scores,0.,.4)
            indices = np.asarray(keep).reshape(-1) if len(keep) else []
            indices = [int(k) for k in indices if roi[min(479,max(0,int(boxes[int(k)][1]+.1*boxes[int(k)][3]))), min(639,max(0,int(boxes[int(k)][0]+.5*boxes[int(k)][2])))]]
            elapsed = (time.perf_counter()-before)*1000
            predicted, truth = len(indices), int(counts[int(i)])
            rows.append(dict(frame_number_1based=int(i)+1,image=frames[int(i)],
                             publisher_count=truth,hog_count=predicted,
                             absolute_error=abs(truth-predicted),inference_ms=elapsed))
            for k in indices:
                x,y,w,h=boxes[int(k)]
                cv2.rectangle(image,(x,y),(x+w,y+h),(0,220,255),2)
            for hx,hy in gt['frame'][int(i)]['loc']:
                cv2.drawMarker(image,(int(round(hx-1)),int(round(hy-1))),(60,70,255),cv2.MARKER_CROSS,8,1)
            contours,_=cv2.findContours(roi,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(image,contours,-1,(80,210,80),1)
            cv2.rectangle(image,(0,0),(image.shape[1],42),(20,30,45),-1)
            cv2.putText(image,f'Mall frame {i+1}: HOG {predicted} | label {truth}',
                        (10,28),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2)
            cv2.imwrite(str(output/'annotated_frames'/f'frame_{i+1:06}.jpg'),image)
            if len(rows) % 20 == 0:
                print(f'Processed {len(rows)}/100',flush=True)
    with (output/'counts.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    errors=np.array([r['absolute_error'] for r in rows])
    summary=dict(source=SOURCE,download_url=URL,archive_bytes=archive.stat().st_size,
                 archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                 original_frames=len(frames),evaluated_frames=len(rows),
                 sampling='100 evenly spaced frame indices across all 2000 images, fixed before evaluation',
                 labels='Publisher manual head/count annotations in supplied ROI; not student manual queue labels',
                 benchmark='publisher-ROI crowd counting with pretrained HOG and NMS; ROI gates estimated head at box top + 0.1 height; no fitting',
                 count_mae=float(errors.mean()),count_rmse=float(np.sqrt(np.mean(errors**2))),
                 p95_detection_ms=float(np.percentile([r['inference_ms'] for r in rows],95)),
                 mae_target_1_person_met=bool(errors.mean()<=1.),
                 opencv=cv2.__version__,numpy=np.__version__,python=platform.python_version(),
                 cadence='Publisher states <2 Hz; exact timing unavailable. Do not infer a 30-second forecast timeline.',
                 limits='Full-image mall people are not queue occupancy. No map homography, tracking, real-time rate, stop-response, or 30 independent demand episodes demonstrated.',
                 terms='Research only; noncommercial; cite original publications; separate from project MIT code license')
    (output/'metrics.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
