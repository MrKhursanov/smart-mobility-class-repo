"""Declared synthetic observations only, never a video accuracy claim."""

def observations(t):
    count = 0 if t < 5 else 3 if t < 10 else 5 if t < 15 else 4
    ids = list(range(count))
    # A 0.3-second occlusion with the same stable ID on recovery.
    if 12 <= t < 12.3:
        ids = [i for i in ids if i != 0]
    tracks = [(str(i), 2.5 + 0.6*i, 6., 0.95) for i in ids]
    if 20 <= t < 24:
        tracks.append(('pedestrian', 5., 3., 0.95))
    return tracks, count
