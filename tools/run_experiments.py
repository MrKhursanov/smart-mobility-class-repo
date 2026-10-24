"""Reproduce M1 synthetic S1 and held-out S2 experiments without ROS."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/smart_hub_m1'))
import csv
import hashlib
import json
import platform
import time
import numpy as np
from smart_hub_m1.core import QueueEngine, features, infer, FEATURE_NAMES
from smart_hub_m1.scenario import observations


def save_csv(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def episode(seed):
    """Independent six-minute episode; hidden schedule is used ONLY to simulate."""
    rng = np.random.default_rng(seed)
    level = rng.uniform(0.04, 0.28)
    boarding_interval = int(rng.integers(45, 91))
    phase = int(rng.integers(0, boarding_interval))
    q, rows = 0, []
    for t in range(361):
        rate = max(.01, level*(1+.65*np.sin(t/100.+seed)))
        arrivals = int(rng.poisson(rate))
        departures = min(q, int(rng.integers(3, 9))) if (t+phase) % boarding_interval == 0 else 0
        q = max(0, q+arrivals-departures)
        # Labeled synthetic observation noise, available online; truth only labels future targets.
        observed = max(0, q + int(rng.choice([-1, 0, 1], p=[.04, .92, .04])))
        rows.append(dict(second=t, observed_count=observed, truth_count=q))
    return rows


def windows(episodes, seeds):
    xx, yy, ids, seconds = [], [], [], []
    for seed in seeds:
        rows = episodes[seed]
        for t in range(59, 331):
            xx.append(features([r['observed_count'] for r in rows[t-59:t+1]]))
            yy.append(rows[t+30]['truth_count'])
            ids.append(seed)
            seconds.append(t)
    return np.array(xx), np.array(yy), ids, seconds


def metrics(y, pred):
    return dict(n=len(y), mae=float(np.mean(np.abs(y-pred))),
                rmse=float(np.sqrt(np.mean((y-pred)**2))))


def plot_svg(path, title, series, ymax=None):
    colors = ['#2563eb', '#ea580c', '#16a34a']
    w, h, left, top, pw, ph = 960, 360, 65, 60, 850, 230
    maximum = ymax or max(1., max(max(v) for _, v in series)*1.12)
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
                '<rect width="100%" height="100%" fill="white"/>',
                f'<text x="30" y="28" font-family="Arial" font-size="20" fill="#10233e">{title}</text>']
    for i in range(5):
        y = top+ph*i/4
        elements += [f'<path d="M{left},{y}H{left+pw}" stroke="#e2e8f0"/>',
                     f'<text x="15" y="{y+5}" font-family="Arial" font-size="12">{maximum*(1-i/4):.1f}</text>']
    for idx, (name, values) in enumerate(series):
        points = ' '.join(f'{left+pw*j/max(1,len(values)-1):.1f},{top+ph*(1-v/maximum):.1f}' for j, v in enumerate(values))
        elements += [f'<polyline points="{points}" fill="none" stroke="{colors[idx]}" stroke-width="2"/>',
                     f'<text x="{left+idx*265}" y="330" font-family="Arial" font-size="13" fill="{colors[idx]}">{name}</text>']
    elements.append('<text x="740" y="308" font-family="Arial" font-size="12">sample index (CSV gives time)</text></svg>')
    path.write_text('\n'.join(elements))


def run():
    for folder in ['evidence', 'data', 'models']:
        (ROOT/folder).mkdir(exist_ok=True)
    e = QueueEngine()
    s1 = []
    for k in range(401):
        t = k/10
        det, truth = observations(t)
        if t < 30:
            e.observe(det, t, t)
        s = e.state(t)
        s1.append(dict(second=t, source_stamp=s.stamp, truth_count=truth,
                       count=s.count, valid=s.valid, confidence=s.confidence,
                       crossing_occupied=s.crossing_occupied))
    save_csv(ROOT/'evidence/s1_trace.csv', s1)
    plot_svg(ROOT/'evidence/s1_count.svg', 'S1 synthetic queue: counting, occlusion, feed freeze',
             [('ground truth', [r['truth_count'] for r in s1]),
              ('estimated count', [r['count'] for r in s1])])
    seeds = list(range(1000, 1030))
    split = {'train': seeds[:18], 'validation': seeds[18:24], 'test': seeds[24:]}
    (ROOT/'data/split.json').write_text(json.dumps(split, indent=2))
    episodes = {s: episode(s) for s in seeds}
    for s, rows in episodes.items():
        save_csv(ROOT/f'data/episode_{s}.csv', rows)
    train_x, train_y, _, _ = windows(episodes, split['train'])
    val_x, val_y, _, _ = windows(episodes, split['validation'])
    test_x, test_y, test_seeds, test_seconds = windows(episodes, split['test'])
    mean, scale = train_x.mean(axis=0), train_x.std(axis=0)
    scale[scale < 1e-9] = 1.
    z = (train_x-mean)/scale
    center = float(train_y.mean())
    candidates = []
    models = []
    for alpha in [.01, .1, 1., 10., 100., 1000.]:
        coef = np.linalg.solve(z.T@z + alpha*np.eye(z.shape[1]), z.T@(train_y-center))
        model = dict(selected='ridge', alpha=alpha, mean=mean.tolist(), scale=scale.tolist(),
                     coef=coef.tolist(), intercept=center, feature_names=FEATURE_NAMES,
                     feature_policy='COUNT_CHANGE_PROXY', horizon_sec=30)
        pred = np.array([infer(model, x) for x in val_x])
        score = metrics(val_y, pred)
        candidates.append(dict(alpha=alpha, **score))
        models.append(model)
    best = min(range(len(models)), key=lambda i: candidates[i]['mae'])
    ridge = models[best]
    baseline_val = metrics(val_y, val_x[:, 0])
    selected = dict(ridge)
    if baseline_val['mae'] < candidates[best]['mae']:
        selected['selected'] = 'persistence'
    model_id = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()[:12]
    selected['model_id'] = f"{selected['selected']}_{model_id}"
    (ROOT/'models/demand_model.json').write_text(json.dumps(selected, indent=2))
    (ROOT/'models/ridge_candidate.json').write_text(json.dumps(ridge, indent=2))
    pred = np.array([infer(ridge, x) for x in test_x])
    base = test_x[:, 0]
    chosen = np.array([infer(selected, x) for x in test_x])
    timings = []
    for i in range(2000):
        before = time.perf_counter_ns()
        infer(selected, test_x[i % len(test_x)])
        timings.append((time.perf_counter_ns()-before)/1e6)
    rows = [dict(seed=s, second=t, truth_30s=float(y), persistence=float(b), ridge=float(p), selected=float(c))
            for s, t, y, b, p, c in zip(test_seeds, test_seconds, test_y, base, pred, chosen)]
    save_csv(ROOT/'evidence/s2_predictions.csv', rows)
    per_episode = []
    for seed in split['test']:
        mask = np.array(test_seeds) == seed
        per_episode.append(dict(seed=seed, ridge=metrics(test_y[mask], pred[mask]),
                                persistence=metrics(test_y[mask], base[mask])))
    failures = [r for r in rows if abs(r['ridge']-r['truth_30s']) > abs(r['persistence']-r['truth_30s'])]
    summary = dict(dataset='30 SYNTHETIC independent six-minute episodes; not real passenger measurements',
                   platform=platform.platform(), python=platform.python_version(), numpy=np.__version__,
                   split=split, validation_candidates=candidates, validation_persistence=baseline_val,
                   chosen_alpha=ridge['alpha'], selection_rule='lowest validation MAE; choose persistence if better',
                   model_id=selected['model_id'], selected_policy=selected['selected'],
                   test_ridge=metrics(test_y, pred), test_persistence=metrics(test_y, base),
                   test_selected=metrics(test_y, chosen), per_test_episode=per_episode,
                   inference_p95_ms=float(np.percentile(timings,95)), timing_n=len(timings),
                   timing_scope='model call only, this machine; excludes ROS, tracking, feature extraction and transport',
                   worse_ridge_example=failures[0] if failures else None,
                   s1_freeze_time=30., s1_first_invalid_after_freeze=next(r['second'] for r in s1 if r['second']>=30 and not r['valid']))
    (ROOT/'evidence/results.json').write_text(json.dumps(summary, indent=2))
    first = [r for r in rows if r['seed'] == split['test'][0]]
    plot_svg(ROOT/'evidence/s2_forecast.svg', 'S2 held-out synthetic episode 1024: 30-second forecasts',
             [('future truth', [r['truth_30s'] for r in first]),
              ('persistence', [r['persistence'] for r in first]),
              ('trained ridge', [r['ridge'] for r in first])])
    print(json.dumps({k:summary[k] for k in ['test_ridge','test_persistence','selected_policy','inference_p95_ms','s1_first_invalid_after_freeze']}, indent=2))


if __name__ == '__main__':
    run()
