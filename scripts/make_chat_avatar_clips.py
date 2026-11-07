"""Build the chat-window avatar clips: an idle loop and a talking loop per expression.

The chat page plays the idle loop and fades to the talking loop while a bot message is "spoken",
so the face and the words come from the same place at the same time.

Sources are the green-screen originals in references/ (git-ignored, not in the repo). Each clip
gets the approved expression edit, is keyed onto the chat header colour, cropped to head and
shoulders, and played forward then backward so it loops without a jump.

    python scripts/make_chat_avatar_clips.py --model face_landmarker.task

Needs: opencv-python-headless mediapipe scipy imageio-ffmpeg numpy pillow
"""
import argparse
import os

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from scipy.ndimage import gaussian_filter1d

from make_expression_gifs import NEUTRAL, SMILE, neutral_talking_offsets, resting_half_width
from make_expression_videos import encode, smile_offsets, warp

# Matches .chatbot-stage in index.html (360 x 200 CSS px, encoded at 2x).
OUT_W, OUT_H = 720, 400
BACKGROUND = np.array([46, 54, 61], np.uint8)  # BGR of #3d362e
# Crop width in face widths, and where the nose sits in the crop (0 = top).
CROP_FACES, NOSE_Y = 3.6, 0.64
SCALE = 1.5  # warp on an enlarged region, as the GIFs were

CLIPS = [
    # name, kind, source, start s, end s, offsets, strength
    ('neutral', 'talk', 'references/neutral_welcome.mp4', 1.2, 9.0, neutral_talking_offsets, NEUTRAL),
    ('neutral', 'idle', 'references/neutral.mp4', 6.5, 10.0, neutral_talking_offsets, NEUTRAL),
    ('smile', 'talk', 'references/smile_only.mp4', 0.2, 3.6, smile_offsets, SMILE),
    ('smile', 'idle', 'references/smile_only.mp4', 4.6, 10.0, smile_offsets, SMILE),
    ('empathic', 'talk', 'references/empathic.mp4', 1.0, 5.8, None, None),
    ('empathic', 'idle', 'references/empathic.mp4', 6.3, 10.0, None, None),
]


def read(path, start, end):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    return frames[round(start * fps):round(end * fps)], fps


def track(frames, fps, model):
    options = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=model),
                                           running_mode=vision.RunningMode.VIDEO, num_faces=1)
    points = []
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        for i, frame in enumerate(frames):
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            result = landmarker.detect_for_video(image, int(i * 1000 / fps))
            points.append([[p.x * frame.shape[1], p.y * frame.shape[0]] for p in result.face_landmarks[0]])
    return gaussian_filter1d(np.array(points), 1.0, axis=0, mode='nearest')


def key(frame):
    """Green screen to the header colour, with the green spill on hair edges removed."""
    f = frame.astype(np.float32)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    excess = g - np.maximum(r, b)
    alpha = 1 - np.clip((excess - 25) / 45, 0, 1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.8)[..., None]
    f[..., 1] = np.minimum(g, np.maximum(r, b) + 8)
    return (f * alpha + BACKGROUND * (1 - alpha) + 0.5).astype(np.uint8)


def build(source, start, end, offsets, strength, model):
    frames, fps = read(source, start, end)
    points = track(frames, fps, model)
    if offsets:
        strength = dict(strength, rest_hw=resting_half_width(list(points * SCALE)))
        edited = []
        for frame, p in zip(frames, points):
            big = cv2.resize(frame, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_LANCZOS4)
            moved = warp(big, p * SCALE, offsets(p * SCALE, strength))
            edited.append(cv2.resize(moved, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_AREA))
        frames = edited
    # One crop per clip, centred on its mean nose position, so idle and talk line up.
    face = np.mean(np.linalg.norm(points[:, 234] - points[:, 454], axis=1))
    nose = points[:, 1].mean(0)
    w = CROP_FACES * face
    h = w * OUT_H / OUT_W
    x0, y0 = nose[0] - w / 2, nose[1] - NOSE_Y * h
    m = np.float32([[OUT_W / w, 0, -x0 * OUT_W / w], [0, OUT_H / h, -y0 * OUT_H / h]])
    clip = [cv2.warpAffine(key(f), m, (OUT_W, OUT_H), flags=cv2.INTER_LANCZOS4, borderValue=BACKGROUND.tolist())
            for f in frames]
    return clip + clip[-2:0:-1], fps


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    os.makedirs('videos/chat', exist_ok=True)
    for name, kind, source, start, end, offsets, strength in CLIPS:
        clip, fps = build(source, start, end, offsets, strength, args.model)
        out = f'videos/chat/{name}_{kind}.mp4'
        encode(clip, fps, out)
        print(out, len(clip), 'frames', f'{len(clip) / fps:.1f}s')
