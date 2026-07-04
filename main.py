#!/usr/bin/env python3
"""
HYPER-LUDOVICO V14 - METANOIA
- Optimized for memory execution (minimal disk bottlenecking)
- Deeply aggressive topological glitches (Edge-bound sorting, Slit-scan warp)
- Self-injection architecture if v2 is omitted
"""

import shutil
import subprocess
import random
import argparse
import os
import sys
import tempfile
from pathlib import Path
import numpy as np
import cv2
import wave

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        raise SystemExit("❌ ffmpeg not found on PATH. Ensure it is installed on your GitHub runner environment.")

def apply_chroma_bleed(img, intensity: float):
    if intensity <= 0: return img
    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV).astype(np.float32)
    shift = int(intensity * 8)
    if shift > 0:
        yuv[:, :, 1] = np.roll(yuv[:, :, 1], shift, axis=1)
        yuv[:, :, 2] = np.roll(yuv[:, :, 2], -shift, axis=0) # Cross-axis split
    return np.clip(yuv, 0, 255).astype(np.uint8)

def apply_advanced_pixel_sort(img, intensity: float):
    """Sorts pixels along high-contrast contour paths rather than plain rigid lines."""
    if intensity <= 0: return img
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    
    out = img.copy()
    num_lines = int(intensity * 15)
    for _ in range(num_lines):
        y = random.randint(0, h - 1)
        edge_indices = np.where(edges[y, :] > 0)[0]
        if len(edge_indices) >= 2:
            x0, x1 = random.choice(edge_indices), random.choice(edge_indices)
            if x0 > x1: x0, x1 = x1, x0
            if x1 - x0 > 5:
                segment = out[y, x0:x1]
                luma = 0.299 * segment[:, 2] + 0.587 * segment[:, 1] + 0.114 * segment[:, 0]
                sort_order = np.argsort(luma)
                out[y, x0:x1] = segment[sort_order]
    return out

def apply_slit_scan_warp(img, intensity: float):
    """Creates classic analog tape speed variance / liquid time bending."""
    if intensity <= 0: return img
    h, w = img.shape[:2]
    out = img.copy()
    num_warps = int(intensity * 4)
    for _ in range(num_warps):
        band_h = random.randint(10, max(20, int(h * intensity * 0.3)))
        y = random.randint(0, h - band_h)
        shift_curve = (np.sin(np.linspace(0, np.pi * 2, band_h)) * (w * 0.15 * intensity)).astype(int)
        for r in range(band_h):
            if 0 <= y + r < h:
                out[y + r, :] = np.roll(out[y + r, :], shift_curve[r], axis=1)
    return out

def apply_block_scramble(img, intensity: float):
    if intensity <= 0: return img
    h, w = img.shape[:2]
    out = img.copy()
    b_size = max(16, int(64 * (1.0 - intensity * 0.5)))
    for _ in range(int(intensity * 8)):
        bw, bh = random.randint(b_size//2, b_size*2), random.randint(b_size//2, b_size*2)
        if bw >= w or bh >= h: continue
        x1, y1 = random.randint(0, w - bw), random.randint(0, h - bh)
        x2, y2 = random.randint(0, w - bw), random.randint(0, h - bh)
        
        # Channel-isolated block swap for added avant-garde coloring
        ch = random.randint(0, 2)
        tmp = out[y1:y1+bh, x1:x1+bw, ch].copy()
        out[y1:y1+bh, x1:x1+bw, ch] = out[y2:y2+bh, x2:x2+bw, ch]
        out[y2:y2+bh, x2:x2+bw, ch] = tmp
    return out

def apply_luma_invert(img, probability: float):
    if random.random() > probability: return img
    h, w = img.shape[:2]
    out = img.copy()
    y0, x0 = random.randint(0, h//2), random.randint(0, w//2)
    rh, rw = random.randint(h//4, h-y0), random.randint(w//4, w-x0)
    out[y0:y0+rh, x0:x0+rw] = 255 - out[y0:y0+rh, x0:x0+rw]
    return out

def synth_experimental_audio(duration: float, chaos: float, stutter_prob: float):
    sr = 44100
    n = max(sr, int(duration * sr))
    t = np.linspace(0.0, duration, n, dtype=np.float32)
    
    # Industrial noise generation layer + sub-bass waves
    mod_freq = random.uniform(20.0, 150.0)
    mod = np.sin(2 * np.pi * mod_freq * t) * (chaos * 600.0)
    carrier = np.sin(2 * np.pi * 45.0 * t + mod) * 0.2
    
    # White noise industrial textures
    noise = np.random.normal(0, 0.02 * chaos, n).astype(np.float32)
    carrier += noise
    
    # Granular buffer execution
    grain = max(1, int(sr * random.uniform(0.02, 0.07)))
    for i in range(grain, n - grain, grain):
        if random.random() < stutter_prob:
            carrier[i:i+grain] = carrier[i-grain:i] * random.uniform(0.8, 1.3)
            
    audio = np.tanh(carrier * (1.5 + chaos)).astype(np.float32)
    return (audio * 32767).astype(np.int16), sr

def process_video(args):
    check_ffmpeg()
    
    v1 = Path(args.v1).resolve()
    if not v1.exists(): raise SystemExit(f"❌ Primary source video not found at: {v1}")
        
    # Self-Injection Engine
    use_self_injection = False
    if not args.v2:
        print("🧬 No explicit injection file (--v2) passed. Activating Self-Mosh Echo architecture.")
        use_self_injection = True
        v2 = v1
    else:
        v2 = Path(args.v2).resolve()
        if not v2.exists(): raise SystemExit(f"❌ Injection source file not found at: {v2}")

    tmp = Path(tempfile.mkdtemp(prefix="metanoia_v14_"))
    
    # Pipeline optimization: Extract straight to targeted streams
    cap1 = cv2.VideoCapture(str(v1))
    cap2 = cv2.VideoCapture(str(v2))
    
    frames_v1 = []
    while True:
        ret, frame = cap1.read()
        if not ret: break
        # Resize dynamically in memory to bypass slow intermediate disk scaling
        frame_resized = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LANCZOS4)
        frames_v1.append(frame_resized)
    cap1.release()

    frames_v2 = []
    while True:
        ret, frame = cap2.read()
        if not ret: break
        frame_resized = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LANCZOS4)
        frames_v2.append(frame_resized)
    cap2.release()

    n1 = len(frames_v1)
    if n1 == 0: raise SystemExit("❌ Primary clip stream parse context contains 0 frames.")

    # Frame sync calculation
    if use_self_injection:
        frames_v2 = frames_v1.copy()
        # Create a time-offset phase loop for self-injection
        frames_v2 = frames_v2[max(1, int(n1 * 0.15)):] + frames_v2[:max(1, int(n1 * 0.15))]
    
    n2 = len(frames_v2)
    start_idx = random.randint(0, max(0, n1 - n2)) if n2 > 0 else -1

    out_dir = tmp / "render"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    canvas = frames_v1[0].copy()
    
    print(f"🎬 Commencing V14 Chaos Pipeline across {n1} frames...")
    
    for i in range(1, n1):
        curr_source = frames_v1[i]
        
        # Datamosh frame replacement calculation
        refresh_p = max(0.01, min(0.3, 0.07 / args.chaos))
        if random.random() > refresh_p:
            # Replicating compression frame skip smears
            prev_gray = cv2.cvtColor(frames_v1[i-1], cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(curr_source, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            
            h, w = canvas.shape[:2]
            gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
            map_x = (gx + flow[:, :, 0] * float(args.drag)).astype(np.float32)
            map_y = (gy + flow[:, :, 1] * float(args.drag)).astype(np.float32)
            canvas = cv2.remap(canvas, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        else:
            if n2 > 0 and (start_idx <= i < start_idx + n2):
                canvas = frames_v2[i - start_idx].copy()
            else:
                canvas = curr_source.copy()

        # Effect lottery compilation
        fx = canvas.copy()
        roll = random.random() * args.chaos
        
        if roll > 0.3:  fx = apply_chroma_bleed(fx, args.chroma * random.uniform(0.5, 2.0))
        if roll > 0.6:  fx = apply_slit_scan_warp(fx, args.chaos * 0.2)
        if roll > 1.0:  fx = apply_advanced_pixel_sort(fx, args.chaos * 0.25)
        if roll > 1.5:  fx = apply_block_scramble(fx, args.chaos * 0.3)
        if roll > 2.0:  fx = apply_luma_invert(fx, args.chaos * 0.1)

        final = cv2.addWeighted(fx, 0.85, curr_source, 0.15, 0.0)
        cv2.imwrite(str(out_dir / f"f_{i:05d}.png"), final)

    # Compile Audio
    duration = max(1.0, n1 / float(args.fps))
    audio_data, sr = synth_experimental_audio(duration, args.chaos, args.stutter)
    
    audio_path = tmp / "audio.wav"
    with wave.open(str(audio_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_data.tobytes())

    # Write file out
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(args.fps), "-i", str(out_dir / "f_%05d.png"),
        "-i", str(audio_path), "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p", "-crf", str(args.crf), "-preset", "ultrafast",
        "-shortest", args.out
    ]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"🎉 Complete! Saved output asset to: {args.out}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1", required=True, help="Primary source video clip")
    parser.add_argument("--v2", default=None, help="Optional source injection video clip")
    parser.add_argument("--drag", type=float, default=1.5, help="Optical flow smear multiplier")
    parser.add_argument("--chaos", type=float, default=2.5, help="Chaos value coefficient")
    parser.add_argument("--chroma", type=float, default=1.2, help="Color separation index")
    parser.add_argument("--stutter", type=float, default=0.2, help="Audio buffer manipulation rate")
    parser.add_argument("--crf", type=int, default=22)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--out", default="output_metanoia.mp4")
    args = parser.parse_args()
    process_video(args)
