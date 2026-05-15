#!/usr/bin/env python3
"""
Gen-Z video builder — mirrors refrenceVideo.mp4 editing structure
using clips extracted from tocreate videos, synced to audio.mp3.

Reference structure (from scene-change detection):
  0.00 – 0.87s  : Section 1  — 3 quick intro flashes
  0.87s          : WHITE FLASH transition
  0.87 – 2.70s  : Section 2  — 9 rapid cuts × 0.20s
  2.70s          : WHITE FLASH transition
  2.70 – 7.00s  : HERO SCENE — single 4.30s breather clip
  7.00 – 16.75s : Section 3  — varied-pace outro (15 clips)

Source footage:
  tocreate (1)  6.4s  | 1920×1080 | 30fps  | h264
  tocreate (2)  135s  | 720×1280  | 24fps  | h264  (portrait → crop to landscape)
  tocreate (3)  46.9s | 3840×2160 | 60fps  | hevc
  tocreate (4)  43.8s | 3840×2160 | 60fps  | hevc
"""

import os
import subprocess
import shutil

FFMPEG  = r"D:\Installed-apps-files\ffmpeg-8.1.1-essentials_build\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"
DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT  = os.path.join(DIR, "output_genz_v3.mp4")
AUDIO   = os.path.join(DIR, "audio.mp3")
TEMP    = os.path.join(DIR, "_build_v3")

T1 = os.path.join(DIR, "tocreate (1).mp4")   # 6.4s  | 1920×1080 | 30fps
T2 = os.path.join(DIR, "tocreate (2).mp4")   # 135s  | 720×1280  | 24fps (portrait)
T3 = os.path.join(DIR, "tocreate (3).mp4")   # 46.9s | 3840×2160 | 60fps
T4 = os.path.join(DIR, "tocreate (4).mp4")   # 43.8s | 3840×2160 | 60fps

W, H = 1280, 720
FPS  = 30

# Gen-Z color grade: vivid saturation + contrast punch + slight warmth
GRADE = "eq=saturation=1.35:contrast=1.1:brightness=0.02"

# Timeline: (source, start_sec, duration_sec)
# Total must ≈ 16.75s to match audio.mp3
TIMELINE = [
    # ── Section 1: quick intro flashes (0.87s) ──────────────────────────
    (T1,      0.5,   0.30),   # 0.00 – 0.30
    (T3,      5.0,   0.30),   # 0.30 – 0.60
    (T4,      3.0,   0.27),   # 0.60 – 0.87
    # ── White flash transition ───────────────────────────────────────────
    ("FLASH", 0,     0.033),  # 0.87 – 0.90
    # ── Section 2: rapid burst (9 × 0.20s = 1.80s) ──────────────────────
    (T3,     10.0,   0.20),   # 0.90 – 1.10
    (T4,      8.0,   0.20),   # 1.10 – 1.30
    (T1,      2.0,   0.20),   # 1.30 – 1.50
    (T3,     20.0,   0.20),   # 1.50 – 1.70
    (T4,     15.0,   0.20),   # 1.70 – 1.90
    (T3,     28.0,   0.20),   # 1.90 – 2.10
    (T4,     22.0,   0.20),   # 2.10 – 2.30
    (T3,     38.0,   0.20),   # 2.30 – 2.50
    (T4,     32.0,   0.20),   # 2.50 – 2.70
    # ── White flash transition ───────────────────────────────────────────
    ("FLASH", 0,     0.033),  # 2.70 – 2.73
    # ── Hero / breather scene (4.30s) ────────────────────────────────────
    (T2,     30.0,   4.30),   # 2.73 – 7.03
    # ── Section 3: varied pace outro (9.72s) ─────────────────────────────
    (T3,     12.0,   0.60),   # 7.03 – 7.63
    (T4,     18.0,   0.60),   # 7.63 – 8.23
    (T3,     22.0,   0.60),   # 8.23 – 8.83
    (T4,     28.0,   0.60),   # 8.83 – 9.43
    (T3,     33.0,   0.60),   # 9.43 – 10.03
    (T4,      5.0,   0.70),   # 10.03 – 10.73
    (T3,     42.0,   0.13),   # 10.73 – 10.86  ← rapid burst
    (T4,     38.0,   0.13),   # 10.86 – 10.99
    (T3,     44.0,   0.13),   # 10.99 – 11.12
    (T3,     15.0,   0.93),   # 11.12 – 12.05
    (T4,     10.0,   0.60),   # 12.05 – 12.65
    (T3,     25.0,   0.53),   # 12.65 – 13.18
    (T4,     35.0,   0.53),   # 13.18 – 13.71
    (T3,      8.0,   0.47),   # 13.71 – 14.18
    (T4,     40.0,   2.57),   # 14.18 – 16.75  ← outro
]


def vf_for(src: str) -> str:
    """Build the -vf filter string for a source clip."""
    if src == "FLASH":
        return ""
    if src == T2:
        # Portrait 720×1280 → center-crop 720×405 → scale to 1280×720
        return f"crop=720:405:0:438,scale={W}:{H},{GRADE}"
    return f"scale={W}:{H},{GRADE}"


def extract_clip(src: str, start: float, dur: float, out: str) -> bool:
    if src == "FLASH":
        cmd = [
            FFMPEG, "-y",
            "-f", "lavfi",
            "-i", f"color=c=white:s={W}x{H}:r={FPS}",
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-an",
            out,
        ]
    else:
        vf = vf_for(src)
        cmd = [
            FFMPEG, "-y",
            "-ss", str(start),
            "-i", src,
            "-t", str(dur),
            "-vf", vf,
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-an",
            out,
        ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        snippet = r.stderr.decode(errors="replace")[-400:]
        print(f"    ERROR: {snippet}")
        return False
    if not os.path.exists(out) or os.path.getsize(out) < 100:
        print(f"    ERROR: output missing or empty: {out}")
        return False
    return True


def main():
    total = sum(d for _, _, d in TIMELINE)
    print(f"Timeline: {len(TIMELINE)} clips  |  total {total:.3f}s  |  audio target 16.752s")
    print()

    os.makedirs(TEMP, exist_ok=True)

    clip_paths = []
    for i, (src, start, dur) in enumerate(TIMELINE):
        label = "FLASH" if src == "FLASH" else os.path.basename(src)
        out = os.path.join(TEMP, f"clip_{i:03d}.mp4")
        print(f"  [{i+1:2d}/{len(TIMELINE)}] {label:<25} @{start:6.1f}s  +{dur:.3f}s")
        if not extract_clip(src, start, dur, out):
            print("  Aborting.")
            return
        clip_paths.append(out)

    # Write FFmpeg concat list (forward slashes required)
    concat_txt = os.path.join(TEMP, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.replace(chr(92), '/')}'\n")

    # Concatenate all clips (stream-copy since all have identical codec params)
    concat_mp4 = os.path.join(TEMP, "concat.mp4")
    print(f"\nConcatenating {len(clip_paths)} clips...")
    r = subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0",
         "-i", concat_txt, "-c", "copy", concat_mp4],
        capture_output=True,
    )
    if r.returncode != 0:
        print("Concat failed:\n" + r.stderr.decode(errors="replace")[-600:])
        return

    # Replace audio track with audio.mp3
    print("Mixing audio...")
    r = subprocess.run(
        [FFMPEG, "-y",
         "-i", concat_mp4, "-i", AUDIO,
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k",
         "-shortest",
         OUTPUT],
        capture_output=True,
    )
    if r.returncode != 0:
        print("Audio mix failed:\n" + r.stderr.decode(errors="replace")[-600:])
        return

    size_mb = os.path.getsize(OUTPUT) / 1_048_576
    print(f"\nDone!  output: {OUTPUT}  ({size_mb:.1f} MB)")

    shutil.rmtree(TEMP, ignore_errors=True)


if __name__ == "__main__":
    main()
