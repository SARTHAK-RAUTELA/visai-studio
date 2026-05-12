#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
"""
VisualAI Studio — CLI entry point (Phase 1)

Usage:
  python generate.py --clips a.mp4 b.mp4 --audio music.mp3 --style cinematic_travel
  python generate.py --clips a.mp4 --audio music.mp3 --style genz_fast_edit --duration 15 --output reel.mp4
  python generate.py --clips a.mp4 b.mp4 --audio music.mp3 --style warm_aesthetic --no-claude

Options:
  --clips     One or more input video clip paths (required)
  --audio     Input audio / music file path (required)
  --style     Edit style preset (default: cinematic_travel)
  --duration  Target output duration in seconds (default: 30)
  --output    Output video file path (default: output.mp4)
  --aspect    Aspect ratio: 9:16 | 16:9 | 1:1 (default: 9:16)
  --no-claude Skip Claude API calls; use a simple fallback EDL
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Ensure both the repo root and backend/ are importable
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / "backend" / ".env")

VALID_STYLES = [
    "cinematic_travel", "genz_fast_edit", "dark_moody",
    "warm_aesthetic", "vintage_film", "art_showcase",
    "energy_action", "minimal_slideshow",
]


def main():
    parser = argparse.ArgumentParser(
        description="VisualAI Studio — AI-powered video editor CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--clips", nargs="+", required=True, help="Input video clip paths")
    parser.add_argument("--audio", required=True, help="Input audio/music file path")
    parser.add_argument("--style", default="cinematic_travel", choices=VALID_STYLES)
    parser.add_argument("--duration", type=float, default=30.0, help="Target duration in seconds")
    parser.add_argument("--output", default="output.mp4", help="Output file path")
    parser.add_argument("--aspect", default="9:16", choices=["9:16", "16:9", "1:1"])
    parser.add_argument("--no-claude", action="store_true", help="Skip Claude, use fallback EDL")
    args = parser.parse_args()

    # ── Validate inputs ────────────────────────────────────────────────────
    for clip in args.clips:
        if not os.path.exists(clip):
            print(f"[ERROR] Clip not found: {clip}")
            sys.exit(1)
    if not os.path.exists(args.audio):
        print(f"[ERROR] Audio file not found: {args.audio}")
        sys.exit(1)

    style_path = REPO_ROOT / "backend" / "styles" / f"{args.style}.json"
    if not style_path.exists():
        print(f"[ERROR] Style preset not found: {style_path}")
        sys.exit(1)

    with open(style_path) as f:
        style_preset = json.load(f)

    print("\n===================================================")
    print("  VisualAI Studio — Starting pipeline")
    print("===================================================")
    print(f"  Clips    : {args.clips}")
    print(f"  Audio    : {args.audio}")
    print(f"  Style    : {args.style}")
    print(f"  Duration : {args.duration}s  |  Aspect: {args.aspect}")
    print(f"  Output   : {args.output}")
    print()

    # ── Step 1: Audio analysis ─────────────────────────────────────────────
    print("Step 1/3 — Analyzing audio with Librosa...")
    try:
        from services.audio_service import AudioService
        audio_analysis = AudioService().analyze_audio(args.audio)
        print(
            f"  BPM: {audio_analysis['bpm']:.1f}  |  "
            f"Mood: {audio_analysis['mood']}  |  "
            f"Duration: {audio_analysis['total_duration']:.1f}s  |  "
            f"Beats detected: {len(audio_analysis['beat_times'])}"
        )
    except Exception as e:
        print(f"  [WARNING] Audio analysis failed ({e}) — using defaults")
        audio_analysis = {
            "bpm": 120.0, "beat_times": [], "onset_times": [],
            "energy_curve": [], "peak_moments": [],
            "total_duration": 60.0, "mood": "balanced", "tempo_category": "medium",
        }

    # ── Step 2: Clip analysis + EDL generation ─────────────────────────────
    use_claude = not args.no_claude and bool(os.environ.get("ANTHROPIC_API_KEY"))

    if use_claude:
        print("Step 2/3 — Analyzing clips with Claude Vision + generating EDL...")
        edl = _run_claude_pipeline(args.clips, audio_analysis, style_preset, args.duration, args.aspect)
    else:
        reason = "--no-claude flag" if args.no_claude else "ANTHROPIC_API_KEY not set"
        print(f"Step 2/3 — Skipping Claude ({reason}); building fallback EDL...")
        edl = _build_fallback_edl(args.clips, args.audio, style_preset, args.duration, args.aspect)

    # Save EDL for inspection / debugging
    edl_path = Path(args.output).with_suffix(".edl.json")
    with open(edl_path, "w") as f:
        json.dump(edl, f, indent=2)
    print(f"  EDL saved → {edl_path}")

    # ── Step 3: Render ─────────────────────────────────────────────────────
    print("Step 3/3 — Rendering video with FFmpeg...")
    clips_dir = str(Path(args.clips[0]).parent.resolve())

    try:
        from services.export_service import ExportService
        output = ExportService().render_from_edl(
            edl=edl,
            audio_path=args.audio,
            output_path=args.output,
            clips_dir=clips_dir,
        )
        size_mb = Path(output).stat().st_size / (1024 * 1024)
        print(f"\n===================================================")
        print(f"  Done!  Output → {output}  ({size_mb:.1f} MB)")
        print(f"===================================================\n")
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Rendering failed: {e}")
        traceback.print_exc()
        sys.exit(1)


def _run_claude_pipeline(clips, audio_analysis, style_preset, duration, aspect):
    """Run full Claude clip analysis + EDL generation."""
    try:
        from services.claude_service import ClaudeService
        claude = ClaudeService()

        clips_analysis = []
        for clip_path in clips:
            print(f"  Extracting keyframes: {Path(clip_path).name}")
            frames = claude.extract_keyframes(clip_path, num_frames=8)
            print(f"    {len(frames)} frames extracted — sending to Claude Vision...")
            analysis = claude.analyze_clip(frames, clip_path)
            clips_analysis.append({"file": clip_path, "analysis": analysis})
            print(
                f"    Subject: {analysis.get('subject', '?')}  |  "
                f"Mood: {analysis.get('mood', '?')}  |  "
                f"Quality: {analysis.get('visual_quality', '?')}  |  "
                f"LUT: {analysis.get('lut_recommendation', '?')}"
            )

        print("  Generating edit plan with Claude...")
        edl = claude.generate_edl(
            clips_analysis=clips_analysis,
            audio_analysis=audio_analysis,
            style_preset=style_preset,
            target_duration=duration,
            aspect_ratio=aspect,
        )
        print(f"  EDL generated — {len(edl.get('clips', []))} clips in plan")
        return edl

    except Exception as e:
        import traceback
        print(f"  [WARNING] Claude pipeline failed: {e}")
        traceback.print_exc()
        print("  Falling back to simple EDL...")
        return _build_fallback_edl(clips, None, style_preset, duration, aspect)


def _build_fallback_edl(clips, audio, style_preset, duration, aspect):
    """Build a simple equal-length EDL without Claude."""
    res_map = {"9:16": "1080x1920", "16:9": "1920x1080", "1:1": "1080x1080"}
    resolution = res_map.get(aspect, "1080x1920")

    n = len(clips)
    clip_dur = duration / n
    t_type = style_preset.get("transitions", ["hard_cut"])[0]
    t_dur = float(style_preset.get("transition_duration", 0.5))
    lut = style_preset.get("lut", "teal_orange")
    intensity = float(style_preset.get("color_grade_intensity", 0.85))

    clips_list = []
    for i, cp in enumerate(clips):
        clips_list.append({
            "clip_id": f"clip_{i}",
            "source_file": Path(cp).name,
            "timeline_start": i * clip_dur,
            "timeline_end": (i + 1) * clip_dur,
            "source_in": 0.0,
            "source_out": clip_dur,
            "speed_factor": 1.0,
            "transition_in": {"type": t_type, "duration": t_dur},
            "transition_out": {"type": t_type, "duration": t_dur},
            "per_clip_grade": None,
            "notes": f"Clip {i + 1}",
        })

    return {
        "project": {
            "title": "fallback_edit",
            "target_duration": duration,
            "aspect_ratio": aspect,
            "fps": 30,
            "resolution": resolution,
        },
        "global_grade": {
            "lut": lut,
            "lut_intensity": intensity,
            "brightness": 0.0,
            "contrast": 1.0,
            "saturation": 1.1,
            "temperature_shift": "neutral",
            "vignette": bool(style_preset.get("vignette", False)),
            "vignette_strength": 0.3,
            "film_grain": bool(style_preset.get("film_grain", False)),
            "grain_strength": 10,
        },
        "audio": {
            "music_file": Path(audio).name if audio else "music.mp3",
            "music_volume": 0.9,
            "original_audio_volume": 0.0,
            "fade_in_duration": 0.5,
            "fade_out_duration": 2.0,
            "fade_out_start": duration - 2,
        },
        "clips": clips_list,
        "text_overlays": [],
        "sound_fx": [],
        "cut_timestamps": [i * clip_dur for i in range(1, n)],
        "reasoning": "Fallback EDL — equal-duration clips, no Claude",
    }


if __name__ == "__main__":
    main()
