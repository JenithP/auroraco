"""Apply the approved avatar expressions to the talking overlay GIFs.

Uses the warp from make_expression_videos.py, with offsets adapted to a mouth that opens and
closes during speech. Pixels outside the face, frame timing and transparency stay the source's.

    python scripts/make_expression_gifs.py --model face_landmarker.task

Needs: opencv-python-headless mediapipe scipy imageio-ffmpeg numpy pillow
"""
import argparse

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from PIL import Image, ImageSequence
from scipy.ndimage import gaussian_filter1d

from make_expression_videos import BROW_WEIGHTS, CHEEKS, LIPS, LOWER_LIP, OVAL, mouth_axes, smile_offsets, warp

# GIF frames are small, so landmarks and warping run on an enlarged copy.
SCALE = 3
TRANSPARENT = 255


def load(path):
    gif = Image.open(path)
    frames = [np.array(f.convert('RGBA')) for f in ImageSequence.Iterator(gif)]
    gif.seek(0)
    return frames, gif.info['duration']


def track(frames, duration, model):
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model), running_mode=vision.RunningMode.VIDEO, num_faces=1,
        min_face_detection_confidence=0.3, min_face_presence_confidence=0.3, min_tracking_confidence=0.3)
    h, w = frames[0].shape[:2]
    big, points = [], []
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        for i, frame in enumerate(frames):
            rgb = frame[..., :3].copy()
            rgb[frame[..., 3] == 0] = 255
            rgb = cv2.resize(rgb, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_LANCZOS4)
            result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), i * duration)
            big.append(rgb)
            points.append(np.array([[p.x * w * SCALE, p.y * h * SCALE] for p in result.face_landmarks[0]])
                          if result.face_landmarks else None)
    found = [i for i, p in enumerate(points) if p is not None]
    # A short gaussian only: the head moves quickly at 12.5 fps and must not lag.
    smooth = gaussian_filter1d(np.array([points[i] for i in found]), 0.7, axis=0, mode='nearest')
    for i, p in zip(found, smooth):
        points[i] = p
    return big, points


def neutral_talking_offsets(p, s):
    """Keep speech but remove its smile: corners stay low and the mouth stays near resting width."""
    c, ex, ey, hw = mouth_axes(p)
    top = (p[13] - c) @ ey
    gap = max((p[14] - p[13]) @ ey, 0)
    # Both are capped: past these limits the warp creases the cheeks on wide speech shapes.
    level = np.clip(top + 0.35 * gap, 0, s['max_level'] * hw)
    narrow = s['narrow'] + min(max(0, 1 - s['rest_hw'] / hw), s['max_narrow'])
    # The higher the corners sit, the more a parted mouth reads as a grin, so close it in proportion.
    close = s['close'] * gap * min(level / (s['max_level'] * hw), 1)
    d = {}
    for i in LIPS:
        u = np.clip((p[i] - c) @ ex / hw, -1, 1)
        d[i] = (s['drop'] * level + s['extra'] * hw) * u * u * ey - narrow * hw * u * ex
        if i in LOWER_LIP:
            d[i] = d[i] - close * (1 - u * u) * ey
    for i in CHEEKS:
        u = np.clip((p[i] - c) @ ex / hw, -2, 2) / 2
        d[i] = s['cheek'] * level * ey - narrow * hw * u * ex
    for i, weight in BROW_WEIGHTS.items():
        d[i] = s['brow'] * hw * weight * ey
    return d


def resting_half_width(points):
    """Median mouth half-width over the frames where the lips are together."""
    closed = [mouth_axes(p)[3] for p in points
              if p is not None and (p[14] - p[13]) @ mouth_axes(p)[2] < 0.1 * mouth_axes(p)[3]]
    return np.median(closed)


def render(frames, big, points, offsets, strength):
    out = []
    for frame, rgb, p in zip(frames, big, points):
        if p is None:
            out.append(frame)
            continue
        warped = warp(rgb, p, offsets(p, strength))
        small = cv2.resize(warped, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_AREA)
        # Only the face takes the warped pixels, so hair, clothes and hands match the source exactly.
        mask = np.zeros(frame.shape[:2], np.float32)
        cv2.fillConvexPoly(mask, cv2.convexHull((p[OVAL] / SCALE).astype(np.int32)), 1.0)
        mask = cv2.GaussianBlur(mask, (0, 0), 1.5)[..., None]
        result = frame.copy()
        result[..., :3] = (mask * small + (1 - mask) * frame[..., :3] + 0.5).astype(np.uint8)
        out.append(result)
    return out


def save(frames, sources, duration, path):
    images = []
    for frame, source in zip(frames, sources):
        # Each frame reuses its source's colours, so skin and lip tones don't shift and
        # unwarped pixels land on their exact source colour.
        opaque = frame[..., 3] >= 128
        colours = np.unique(source[source[..., 3] >= 128][..., :3], axis=0)[:TRANSPARENT]
        if not len(colours):
            colours = np.zeros((1, 3), np.uint8)
        palette = colours.ravel().tolist()
        palette += [0] * (768 - len(palette))
        reference = Image.new('P', (1, 1))
        reference.putpalette(palette)
        rgb = frame[..., :3].copy()
        rgb[~opaque] = colours[0]
        data = np.array(Image.fromarray(rgb).quantize(palette=reference, dither=Image.Dither.FLOYDSTEINBERG))
        data[~opaque] = TRANSPARENT
        image = Image.fromarray(data, 'P')
        image.putpalette(palette)
        images.append(image)
    images[0].save(path, save_all=True, append_images=images[1:], duration=duration, loop=0, disposal=2,
                   transparency=TRANSPARENT, background=TRANSPARENT, optimize=False)


NEUTRAL = dict(drop=0.9, extra=0.03, narrow=0.03, cheek=0.3, brow=0.05, max_level=0.35, max_narrow=0.14, close=0.5)
# Eyes and upper face only: with these zeros the lips stay pinned to the source's mouth shape.
SMILE = dict(widen=0, lift=0, part=0, cheek=0.10, lid=0.045)
JOBS = [
    ('images/neutral_problem.gif', 'images/neutral_problem_flat.gif', neutral_talking_offsets, NEUTRAL),
    ('images/welcome_neutral_new.gif', 'images/welcome_neutral_new_flat.gif', neutral_talking_offsets, NEUTRAL),
    ('images/smile_problem.gif', 'images/smile_problem_big.gif', smile_offsets, SMILE),
]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    for src, out, offsets, strength in JOBS:
        frames, duration = load(src)
        big, points = track(frames, duration, args.model)
        strength = dict(strength, rest_hw=resting_half_width(points))
        save(render(frames, big, points, offsets, strength), frames, duration, out)
        print(out, len(frames), 'frames')
