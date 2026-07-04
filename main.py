#!/usr/bin/env python3
"""
HYPER-LUDOVICO V15 - METANOIA (EXTENDED)
- More datamosh variety: optical-flow drag, block-motion echo, feedback decay, frame-skip stutter
- More effects: pixel sort (edge-aware), slit-scan warp, block scramble, chroma bleed,
  luma invert, RGB channel drift, scanline decay, feedback ghosting, VHS noise, posterize
- Deep personalization via CLI flags + JSON preset support
- Same self-injection / dual-source architecture as v14, kept lean
"""

import shutil, subprocess, random, argparse, json, tempfile
from pathlib import Path
import numpy as np
import cv2
import wave

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        raise SystemExit("❌ ffmpeg not found on PATH.")

# ---------------------------------------------------------------- effects --

def fx_chroma_bleed(img, intensity):
    if intensity <= 0: return img
    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV).astype(np.float32)
    shift = int(intensity * 8)
    if shift > 0:
        yuv[:, :, 1] = np.roll(yuv[:, :, 1], shift, axis=1)
        yuv[:, :, 2] = np.roll(yuv[:, :, 2], -shift, axis=0)
    return np.clip(yuv, 0, 255).astype(np.uint8)

def fx_pixel_sort(img, intensity):
    if intensity <= 0: return img
    h, w = img.shape[:2]
    edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 50, 150)
    out = img.copy()
    for _ in range(int(intensity * 15)):
        y = random.randint(0, h - 1)
        idx = np.where(edges[y, :] > 0)[0]
        if len(idx) >= 2:
            x0, x1 = sorted(random.sample(list(idx), 2))
            if x1 - x0 > 5:
                seg = out[y, x0:x1]
                luma = 0.299*seg[:,2] + 0.587*seg[:,1] + 0.114*seg[:,0]
                out[y, x0:x1] = seg[np.argsort(luma)]
    return out

def fx_slit_scan_warp(img, intensity):
    if intensity <= 0: return img
    h, w = img.shape[:2]
    out = img.copy()
    for _ in range(int(intensity * 4)):
        band_h = random.randint(10, max(20, int(h * intensity * 0.3)))
        y = random.randint(0, h - band_h)
        curve = (np.sin(np.linspace(0, np.pi*2, band_h)) * (w * 0.15 * intensity)).astype(int)
        for r in range(band_h):
            out[y+r, :] = np.roll(out[y+r, :], curve[r], axis=1)
    return out

def fx_block_scramble(img, intensity):
    if intensity <= 0: return img
    h, w = img.shape[:2]
    out = img.copy()
    b_size = max(16, int(64 * (1.0 - intensity * 0.5)))
    for _ in range(int(intensity * 8)):
        bw, bh = random.randint(b_size//2, b_size*2), random.randint(b_size//2, b_size*2)
        if bw >= w or bh >= h: continue
        x1, y1 = random.randint(0, w-bw), random.randint(0, h-bh)
        x2, y2 = random.randint(0, w-bw), random.randint(0, h-bh)
        ch = random.randint(0, 2)
        tmp = out[y1:y1+bh, x1:x1+bw, ch].copy()
        out[y1:y1+bh, x1:x1+bw, ch] = out[y2:y2+bh, x2:x2+bw, ch]
        out[y2:y2+bh, x2:x2+bw, ch] = tmp
    return out

def fx_luma_invert(img, probability):
    if random.random() > probability: return img
    h, w = img.shape[:2]
    out = img.copy()
    y0, x0 = random.randint(0, h//2), random.randint(0, w//2)
    rh, rw = random.randint(h//4, h-y0), random.randint(w//4, w-x0)
    out[y0:y0+rh, x0:x0+rw] = 255 - out[y0:y0+rh, x0:x0+rw]
    return out

def fx_rgb_drift(img, intensity):
    """Independently drifts each channel over time-varying random offsets — sickly color separation."""
    if intensity <= 0: return img
    h, w = img.shape[:2]
    m = int(intensity * min(h, w) * 0.03) + 1
    out = np.zeros_like(img)
    for c in range(3):
        dx, dy = random.randint(-m, m), random.randint(-m, m)
        out[:, :, c] = np.roll(img[:, :, c], (dy, dx), axis=(0, 1))
    return out

def fx_scanline_decay(img, intensity):
    """Alternating darkened rows with slight random flicker per row — CRT decay."""
    if intensity <= 0: return img
    out = img.astype(np.float32)
    step = max(2, int(6 - intensity * 4))
    fade = 1.0 - intensity * random.uniform(0.3, 0.7)
    out[::step] *= fade
    return np.clip(out, 0, 255).astype(np.uint8)

def fx_vhs_noise(img, intensity):
    """Grainy luminance noise + occasional horizontal head-switching glitch line."""
    if intensity <= 0: return img
    h, w = img.shape[:2]
    noise = np.random.normal(0, 25 * intensity, (h, w, 1)).astype(np.float32)
    out = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    if random.random() < intensity * 0.4:
        y = random.randint(0, h - 1)
        out[y] = np.roll(out[y], random.randint(-w//3, w//3), axis=0)
    return out

def fx_posterize_bloom(img, intensity):
    """Reduces tonal levels then blooms highlights — waxy, hallucinatory skin tones."""
    if intensity <= 0: return img
    levels = max(2, int(8 - intensity * 6))
    step = 255 / (levels - 1)
    out = np.round(img.astype(np.float32) / step) * step
    bright_mask = (out.mean(axis=2, keepdims=True) > 200).astype(np.float32)
    out = out + bright_mask * intensity * 40
    return np.clip(out, 0, 255).astype(np.uint8)

def fx_feedback_ghost(img, prev_canvas, intensity, decay):
    """Blends in a decaying trail of the accumulated canvas for lingering ghost limbs."""
    if intensity <= 0 or prev_canvas is None: return img
    out = img.astype(np.float32) * (1 - intensity) + prev_canvas.astype(np.float32) * decay * intensity
    return np.clip(out, 0, 255).astype(np.uint8)

EFFECT_FUNCS = {
    "chroma": fx_chroma_bleed, "sort": fx_pixel_sort, "slitscan": fx_slit_scan_warp,
    "scramble": fx_block_scramble, "invert": fx_luma_invert, "drift": fx_rgb_drift,
    "scanline": fx_scanline_decay, "vhs": fx_vhs_noise, "posterize": fx_posterize_bloom,
}

# --------------------------------------------------------------- audio -----

def synth_experimental_audio(duration, chaos, stutter_prob, drone_hz=45.0):
    sr = 44100
    n = max(sr, int(duration * sr))
    t = np.linspace(0.0, duration, n, dtype=np.float32)
    mod_freq = random.uniform(20.0, 150.0)
    mod = np.sin(2*np.pi*mod_freq*t) * (chaos * 600.0)
    carrier = np.sin(2*np.pi*drone_hz*t + mod) * 0.2
    carrier += np.random.normal(0, 0.02*chaos, n).astype(np.float32)
    grain = max(1, int(sr * random.uniform(0.02, 0.07)))
    for i in range(grain, n - grain, grain):
        if random.random() < stutter_prob:
            carrier[i:i+grain] = carrier[i-grain:i] * random.uniform(0.8, 1.3)
    audio = np.tanh(carrier * (1.5 + chaos)).astype(np.float32)
    return (audio * 32767).astype(np.int16), sr

# ------------------------------------------------------------- pipeline ----

def process_video(args):
    check_ffmpeg()
    v1 = Path(args.v1).resolve()
    if not v1.exists(): raise SystemExit(f"❌ Primary source not found: {v1}")

    if not args.v2:
        print("🧬 No --v2 given. Self-Mosh Echo active.")
        v2, self_inject = v1, True
    else:
        v2 = Path(args.v2).resolve()
        if not v2.exists(): raise SystemExit(f"❌ Injection source not found: {v2}")
        self_inject = False

    tmp = Path(tempfile.mkdtemp(prefix="metanoia_v15_"))

    def load(path):
        cap = cv2.VideoCapture(str(path))
        frames = []
        while True:
            ret, f = cap.read()
            if not ret: break
            frames.append(cv2.resize(f, (args.width, args.height), interpolation=cv2.INTER_LANCZOS4))
        cap.release()
        return frames

    frames_v1 = load(v1)
    n1 = len(frames_v1)
    if n1 == 0: raise SystemExit("❌ Primary clip has 0 frames.")

    frames_v2 = frames_v1.copy()[max(1, int(n1*0.15)):] + frames_v1[:max(1, int(n1*0.15))] if self_inject else load(v2)
    n2 = len(frames_v2)
    start_idx = random.randint(0, max(0, n1 - n2)) if n2 > 0 else -1

    out_dir = tmp / "render"; out_dir.mkdir(parents=True, exist_ok=True)
    canvas = frames_v1[0].copy()
    prev_canvas = None

    # active effect roster, either from --effects or all registered
    active = args.effects.split(",") if args.effects else list(EFFECT_FUNCS.keys())
    active = [e for e in active if e in EFFECT_FUNCS]
    weights = {k: getattr(args, f"w_{k}", 1.0) for k in EFFECT_FUNCS}

    print(f"🎬 V15 pipeline: {n1} frames | datamosh mode={args.mosh_mode} | effects={active}")

    for i in range(1, n1):
        curr_source = frames_v1[i]

        # --- datamoshing: three interchangeable strategies for variety ---
        refresh_p = max(0.01, min(0.3, 0.07 / args.chaos))
        do_refresh = random.random() > refresh_p

        if do_refresh:
            if args.mosh_mode in ("flow", "hybrid"):
                prev_gray = cv2.cvtColor(frames_v1[i-1], cv2.COLOR_BGR2GRAY)
                curr_gray = cv2.cvtColor(curr_source, cv2.COLOR_BGR2GRAY)
                flow = cv2.calcOpticalFlowFarneback(prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                h, w = canvas.shape[:2]
                gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
                map_x = (gx + flow[:,:,0] * args.drag).astype(np.float32)
                map_y = (gy + flow[:,:,1] * args.drag).astype(np.float32)
                canvas = cv2.remap(canvas, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            if args.mosh_mode in ("block", "hybrid"):
                # block-motion echo: copy random canvas blocks onto themselves offset by a jitter vector
                h, w = canvas.shape[:2]
                bs = max(8, int(32 / args.chaos))
                for _ in range(int(args.chaos * 6)):
                    by, bx = random.randint(0, h-bs), random.randint(0, w-bs)
                    jy, jx = random.randint(-bs, bs), random.randint(-bs, bs)
                    sy, sx = np.clip(by+jy, 0, h-bs), np.clip(bx+jx, 0, w-bs)
                    canvas[by:by+bs, bx:bx+bs] = canvas[sy:sy+bs, sx:sx+bs]
            if args.mosh_mode == "stutter":
                # pure frame-hold stutter: freeze canvas occasionally, ignore new source entirely
                if random.random() < 0.5:
                    pass  # canvas unchanged -> hard freeze/stutter
                else:
                    canvas = cv2.addWeighted(canvas, 0.6, curr_source, 0.4, 0)
        else:
            if n2 > 0 and start_idx <= i < start_idx + n2:
                canvas = frames_v2[i - start_idx].copy()
            else:
                canvas = curr_source.copy()

        # --- effect lottery: weighted, cumulative chaos roll picks a subset each frame ---
        fx = canvas.copy()
        roll = random.random() * args.chaos
        thresholds = np.linspace(0.3, 2.3, len(active))
        for name, thr in zip(active, thresholds):
            if roll > thr:
                w_ = weights.get(name, 1.0)
                base_intensity = args.chaos * 0.2 * w_
                if name == "chroma":    fx = fx_chroma_bleed(fx, args.chroma * random.uniform(0.5, 2.0) * w_)
                elif name == "sort":    fx = fx_pixel_sort(fx, base_intensity)
                elif name == "slitscan":fx = fx_slit_scan_warp(fx, base_intensity)
                elif name == "scramble":fx = fx_block_scramble(fx, base_intensity)
                elif name == "invert":  fx = fx_luma_invert(fx, args.chaos * 0.1 * w_)
                elif name == "drift":   fx = fx_rgb_drift(fx, base_intensity)
                elif name == "scanline":fx = fx_scanline_decay(fx, base_intensity)
                elif name == "vhs":     fx = fx_vhs_noise(fx, base_intensity)
                elif name == "posterize": fx = fx_posterize_bloom(fx, base_intensity)

        fx = fx_feedback_ghost(fx, prev_canvas, args.feedback, args.feedback_decay)
        prev_canvas = fx.copy()

        final = cv2.addWeighted(fx, 0.85, curr_source, 0.15, 0.0)
        cv2.imwrite(str(out_dir / f"f_{i:05d}.png"), final)

    duration = max(1.0, n1 / float(args.fps))
    audio_data, sr = synth_experimental_audio(duration, args.chaos, args.stutter, args.drone_hz)
    audio_path = tmp / "audio.wav"
    with wave.open(str(audio_path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(audio_data.tobytes())

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-framerate", str(args.fps), "-i", str(out_dir / "f_%05d.png"),
           "-i", str(audio_path), "-c:v", "libx264", "-c:a", "aac",
           "-pix_fmt", "yuv420p", "-crf", str(args.crf), "-preset", "ultrafast",
           "-shortest", args.out]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"🎉 Saved: {args.out}")

# ------------------------------------------------------------------ CLI ----

PRESETS = {
    "clinical_dread":  dict(chaos=1.8, drag=1.2, chroma=0.8, feedback=0.3, feedback_decay=0.6,
                             mosh_mode="flow", effects="scanline,drift,vhs,invert", drone_hz=38),
    "flesh_bloom":     dict(chaos=2.8, drag=2.0, chroma=1.6, feedback=0.5, feedback_decay=0.8,
                             mosh_mode="hybrid", effects="posterize,sort,chroma,invert", drone_hz=52),
    "signal_rot":      dict(chaos=3.2, drag=0.8, chroma=2.0, feedback=0.2, feedback_decay=0.4,
                             mosh_mode="stutter", effects="vhs,scanline,scramble,drift", drone_hz=30),
    "liturgy":         dict(chaos=1.4, drag=2.5, chroma=0.5, feedback=0.6, feedback_decay=0.9,
                             mosh_mode="flow", effects="slitscan,posterize,chroma", drone_hz=41),
}

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="METANOIA V15 — extended datamosh/glitch engine")
    p.add_argument("--v1", required=True)
    p.add_argument("--v2", default=None)
    p.add_argument("--preset", choices=list(PRESETS), default=None,
                   help="Load a named disturbing-look starting point; flags below override it.")
    p.add_argument("--drag", type=float, default=1.5)
    p.add_argument("--chaos", type=float, default=2.5)
    p.add_argument("--chroma", type=float, default=1.2)
    p.add_argument("--stutter", type=float, default=0.2)
    p.add_argument("--feedback", type=float, default=0.0, help="0-1, ghost-trail blend from accumulated canvas")
    p.add_argument("--feedback-decay", type=float, default=0.7, dest="feedback_decay")
    p.add_argument("--mosh-mode", choices=["flow", "block", "hybrid", "stutter"], default="flow", dest="mosh_mode",
                   help="flow=optical-flow drag, block=block-motion echo, hybrid=both, stutter=frame-hold freezes")
    p.add_argument("--effects", default=None, help="comma list from: " + ",".join(EFFECT_FUNCS))
    p.add_argument("--drone-hz", type=float, default=45.0, dest="drone_hz")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--crf", type=int, default=22)
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--out", default="output_metanoia.mp4")
    p.add_argument("--config", default=None, help="Path to a JSON file of arg overrides (deepest personalization)")
    args = p.parse_args()

    if args.preset:
        for k, v in PRESETS[args.preset].items():
            if p.get_default(k) == getattr(args, k):  # only fill if user didn't set it explicitly
                setattr(args, k, v)
    if args.config:
        with open(args.config) as f:
            for k, v in json.load(f).items():
                setattr(args, k, v)

    process_video(args)
