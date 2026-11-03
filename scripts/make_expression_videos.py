"""Re-grade the avatar's expression by warping each frame around tracked face landmarks.

Only the mouth, cheeks, inner brows (neutral) and lower eyelids (smile) move. Identity, clothing, head motion
and timing stay the source video's, so the two conditions differ in expression only.

    python scripts/make_expression_videos.py --model face_landmarker.task

Needs: opencv-python-headless mediapipe scipy imageio-ffmpeg numpy
Model: https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
"""
import argparse
import subprocess

import cv2
import imageio_ffmpeg
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from scipy.interpolate import RBFInterpolator
from scipy.ndimage import gaussian_filter1d

OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
        152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
NOSE = [1, 2, 98, 327, 168, 6, 197, 195, 5, 4, 97, 326, 94, 19, 129, 358, 64, 294]
UPPER_LIDS = [33, 246, 161, 160, 159, 158, 157, 173, 133, 263, 466, 388, 387, 386, 385, 384, 398, 362]
LOWER_LIDS = [7, 163, 144, 145, 153, 154, 155, 249, 390, 373, 374, 380, 381, 382]
BROWS = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46, 300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
UPPER_LIP = [185, 40, 39, 37, 0, 267, 269, 270, 409, 191, 80, 81, 82, 13, 312, 311, 310, 415]
LOWER_LIP = [146, 91, 181, 84, 17, 314, 405, 321, 375, 95, 88, 178, 87, 14, 317, 402, 318, 324]
CORNERS = [61, 291, 78, 308]
LIPS = UPPER_LIP + LOWER_LIP + CORNERS
CHEEKS = [205, 425, 187, 411, 50, 280, 207, 427, 206, 426]
# How much of the brow-lowering each point takes: full at the inner end, fading outward.
BROW_WEIGHTS = {107: 1.0, 55: 1.0, 336: 1.0, 285: 1.0, 66: 0.65, 65: 0.65, 296: 0.65, 295: 0.65,
                105: 0.3, 52: 0.3, 334: 0.3, 282: 0.3}


def track(path, model):
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model),
        running_mode=vision.RunningMode.VIDEO, num_faces=1)
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(3)), int(cap.get(4))
    frames, points = [], []
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            result = landmarker.detect_for_video(image, int(len(frames) * 1000 / fps))
            points.append([[p.x * w, p.y * h] for p in result.face_landmarks[0]])
            frames.append(frame)
    return frames, gaussian_filter1d(np.array(points), 1.2, axis=0, mode='nearest'), fps


def mouth_axes(p):
    c = (p[61] + p[291]) / 2
    ex = p[291] - p[61]
    hw = np.linalg.norm(ex) / 2
    ex = ex / (2 * hw)
    return c, ex, np.array([-ex[1], ex[0]]), hw


def neutral_offsets(p, s):
    """Drop the corners past the mouth centre's height, pull them in, lower the inner brows."""
    c, ex, ey, hw = mouth_axes(p)
    centre = ((p[13] + p[14]) / 2 - c) @ ey
    d = {}
    for i in LIPS:
        u = np.clip((p[i] - c) @ ex / hw, -1, 1)
        d[i] = (s['drop'] * centre + s['extra'] * hw) * u * u * ey - s['narrow'] * hw * u * ex
    for i in CHEEKS:
        u = np.clip((p[i] - c) @ ex / hw, -2, 2) / 2
        d[i] = s['cheek'] * centre * ey - s['narrow'] * hw * u * ex
    for i, weight in BROW_WEIGHTS.items():
        d[i] = s['brow'] * hw * weight * ey
    return d


def smile_offsets(p, s):
    """Widen and lift the corners, part the lips further, raise cheeks and lower lids."""
    c, ex, ey, hw = mouth_axes(p)
    d = {}
    for i in LIPS:
        u = np.clip((p[i] - c) @ ex / hw, -1, 1)
        move = s['widen'] * hw * u * ex - s['lift'] * hw * u * u * ey
        if i in LOWER_LIP:
            move = move + s['part'] * hw * (1 - u * u) * ey
        d[i] = move
    for i in CHEEKS:
        u = np.clip((p[i] - c) @ ex / hw, -2, 2) / 2
        d[i] = s['widen'] * hw * u * ex - s['cheek'] * hw * ey
    for upper, lower, lids in ((159, 145, LOWER_LIDS[:7]), (386, 374, LOWER_LIDS[7:])):
        openness = np.clip(np.linalg.norm(p[upper] - p[lower]) / (0.28 * hw), 0, 1)
        for i in lids:
            d[i] = -s['lid'] * hw * openness * ey
    return d


def warp(frame, p, offsets, step=4):
    h, w = frame.shape[:2]
    moved = list(offsets)
    fixed = [i for i in OVAL + NOSE + UPPER_LIDS + LOWER_LIDS + BROWS if i not in offsets]
    # Backward map: for each output pixel, where to sample from the source frame.
    dst = np.vstack([p[moved] + np.array([offsets[i] for i in moved]), p[fixed]])
    delta = np.vstack([-np.array([offsets[i] for i in moved]), np.zeros((len(fixed), 2))])
    rbf = RBFInterpolator(dst, delta, kernel='thin_plate_spline', smoothing=1.0)

    x0, y0 = np.floor(p.min(0)).astype(int) - 8
    x1, y1 = np.ceil(p.max(0)).astype(int) + 8
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    gx, gy = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    coarse = rbf(np.column_stack([gx.ravel(), gy.ravel()])).reshape(*gx.shape, 2).astype(np.float32)
    field = cv2.resize(coarse, (x1 - x0, y1 - y0), interpolation=cv2.INTER_CUBIC)

    # Fade the warp out at the face outline so hair, ears and collar stay untouched.
    mask = np.zeros((h, w), np.float32)
    cv2.fillConvexPoly(mask, cv2.convexHull(p[OVAL].astype(np.int32)), 1.0)
    mask = cv2.GaussianBlur(mask, (0, 0), 6)[y0:y1, x0:x1, None]
    field = field * mask

    map_x, map_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    map_x[y0:y1, x0:x1] += field[..., 0]
    map_y[y0:y1, x0:x1] += field[..., 1]
    return cv2.remap(frame, map_x, map_y, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)


def encode(frames, fps, path):
    h, w = frames[0].shape[:2]
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', f'{w}x{h}', '-r', str(fps), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '17',
           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError('ffmpeg failed for ' + path)


# neutral_1's last frame is a one-frame mouth-open glitch, so it is left out (trim=1).
JOBS = [
    ('videos/neutral_1.mp4', 'videos/neutral_1_flat.mp4', neutral_offsets, 1,
     dict(drop=0.9, extra=0.05, narrow=0.07, cheek=0.3, brow=0.06)),
    ('videos/smile_only.mp4', 'videos/smile_only_big.mp4', smile_offsets, 0,
     dict(widen=0.07, lift=0.07, part=-0.05, cheek=0.10, lid=0.045)),
]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    for src, out, offsets, trim, strength in JOBS:
        frames, points, fps = track(src, args.model)
        frames = frames[:len(frames) - trim]
        encode([warp(f, p, offsets(p, strength)) for f, p in zip(frames, points)], fps, out)
        print(out, len(frames), 'frames')
