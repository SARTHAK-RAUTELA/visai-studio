"""
Reference video analysis — Phase 2.
Full pipeline: scene detection → transition classification →
color analysis → optical flow → Claude Style DNA generation.
"""

import base64
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np


class ReferenceService:
    def __init__(self):
        from services.scene_service import SceneService
        from services.color_service import ColorService
        self._scene = SceneService()
        self._color = ColorService()

    # ── Public API ───────────────────────────────────────────────────────────

    def analyze(self, video_path: str, claude_service=None) -> dict:
        """
        Full reference video analysis pipeline.
        Returns Style DNA dict (see projectDetails.md Section 15).
        claude_service: optional ClaudeService instance for Vision-based analysis.
        """
        video_path = str(video_path)
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps else 0.0

        # 1. Scene detection
        scenes = self._scene.detect_scenes(video_path)
        if not scenes:
            scenes = [(0.0, max(duration, 1.0))]

        clip_durations = [end - start for start, end in scenes]
        avg_clip_duration = float(np.mean(clip_durations)) if clip_durations else 3.0
        clip_duration_std = float(np.std(clip_durations)) if clip_durations else 0.0
        cuts_per_second = len(scenes) / duration if duration > 0 else 0.0

        # 2. Transition classification at each cut boundary
        transition_types = []
        for i in range(len(scenes) - 1):
            cut_time = scenes[i][1]
            frames_b = self._scene.extract_frames_at(cap, max(0.0, cut_time - 1.0), cut_time, fps)
            frames_a = self._scene.extract_frames_at(cap, cut_time, min(duration, cut_time + 1.0), fps)
            transition_types.append(self._scene.classify_transition(frames_b, frames_a))

        transition_counts: dict[str, int] = {}
        for t in transition_types:
            transition_counts[t] = transition_counts.get(t, 0) + 1
        total_t = max(len(transition_types), 1)
        transition_ratios = {k: round(v / total_t, 3) for k, v in transition_counts.items()}
        dominant_transition = max(transition_counts, key=transition_counts.get) if transition_counts else "hard_cut"

        # 3. Color analysis — mid-frame from each scene
        color_profiles = []
        for start, end in scenes:
            frame = self._scene.get_frame_at(cap, (start + end) / 2)
            if frame is not None:
                color_profiles.append(self._color.analyze_color_grade(frame))
        avg_color = self._color.average_color_profiles(color_profiles)
        matched_lut = self._color.match_to_lut_library(avg_color)

        # 4. Speed-ramp detection via optical flow magnitude variance
        speed_ramps = self._detect_speed_ramps(cap, scenes, fps)

        # 5. Sample 10 frames for Claude Vision
        sampled_b64 = self._sample_frames_b64(cap, total_frames, n=10)

        cap.release()

        # 6. Beat-sync analysis (tries to extract audio from the video)
        beat_sync = self._analyze_beat_sync(video_path, [s[1] for s in scenes[:-1]])

        computed = {
            "total_duration": duration,
            "num_cuts": len(scenes),
            "cut_timestamps": [s[1] for s in scenes[:-1]],
            "clip_durations": clip_durations,
            "avg_clip_duration": avg_clip_duration,
            "clip_duration_std": clip_duration_std,
            "transition_types": transition_types,
            "transition_type_counts": transition_ratios,
            "dominant_transition": dominant_transition,
            "color_profile": avg_color,
            "matched_lut": matched_lut,
            "speed_ramps_detected": speed_ramps,
            "cuts_per_second": cuts_per_second,
            "beat_sync": beat_sync,
        }

        # 7. Claude Vision for holistic Style DNA
        if claude_service and sampled_b64:
            style_dna = claude_service.generate_style_dna(computed, sampled_b64)
            style_dna.setdefault("_computed", computed)
            return style_dna

        return self._build_fallback_style_dna(computed, matched_lut)

    def download_from_url(self, url: str, output_dir: str) -> str:
        """
        Download a reference video via yt-dlp (YouTube / Instagram / TikTok / etc.).
        Returns the local file path.
        """
        import yt_dlp

        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        template = str(output_dir / "ref_%(id)s.%(ext)s")

        ydl_opts = {
            "format": (
                "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                "/best[height<=1080][ext=mp4]/best[height<=1080]/best"
            ),
            "outtmpl": template,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # After merge, extension is always .mp4
            if not Path(filename).exists():
                filename = str(Path(filename).with_suffix(".mp4"))
            return str(filename)

    # ── Private helpers ──────────────────────────────────────────────────────

    def _detect_speed_ramps(self, cap, scenes: list, fps: float) -> list:
        """Detect speed ramps using optical flow magnitude variance within each scene."""
        ramps = []
        for start, end in scenes:
            if end - start < 0.5:
                continue
            magnitudes = []
            prev_gray = None
            for t in np.linspace(start, end, 6):
                frame = self._scene.get_frame_at(cap, float(t))
                if frame is None:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    try:
                        flow = cv2.calcOpticalFlowFarneback(
                            prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
                        )
                        mag = float(np.mean(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)))
                        magnitudes.append(mag)
                    except Exception:
                        pass
                prev_gray = gray

            if len(magnitudes) >= 3:
                var = float(np.var(magnitudes))
                mean = float(np.mean(magnitudes))
                if var > mean * 0.5 and mean > 2.0:
                    ramps.append({"start": start, "end": end, "type": "speed_ramp"})
        return ramps

    def _sample_frames_b64(self, cap, total_frames: int, n: int = 10) -> list:
        """Sample n evenly-spaced frames from the video as base64 JPEGs."""
        frames_b64 = []
        if total_frames == 0:
            return frames_b64
        for i in range(n):
            idx = int(i * total_frames / n)
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            h, w = frame.shape[:2]
            if w > 1280:
                frame = cv2.resize(frame, (1280, int(h * 1280 / w)))
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frames_b64.append(base64.b64encode(buf).decode("utf-8"))
        return frames_b64

    def _analyze_beat_sync(self, video_path: str, cut_timestamps: list) -> dict:
        """
        Extract audio from the video and check if cuts align with beats (librosa).
        Returns beat sync metadata.
        """
        try:
            import librosa

            ffmpeg_bin = os.getenv("FFMPEG_BIN", "ffmpeg")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            result = subprocess.run(
                [ffmpeg_bin, "-y", "-i", video_path, "-vn", "-ar", "22050", "-ac", "1", tmp_path],
                capture_output=True,
                timeout=120,
            )

            if result.returncode != 0 or not Path(tmp_path).exists():
                return self._default_beat_sync()

            y, sr = librosa.load(tmp_path, sr=22050)
            os.unlink(tmp_path)

            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="time", sparse=False)
            beat_times = [float(b) for b in np.atleast_1d(beat_frames)]
            bpm = float(np.squeeze(tempo))

            if not beat_times or not cut_timestamps:
                return {"is_beat_synced": False, "estimated_bpm": bpm, "cuts_align_to_beats": False, "sync_frequency": "none"}

            aligned = sum(1 for cut in cut_timestamps if any(abs(cut - bt) < 0.1 for bt in beat_times))
            ratio = aligned / len(cut_timestamps)

            return {
                "is_beat_synced": ratio > 0.5,
                "estimated_bpm": bpm,
                "cuts_align_to_beats": ratio > 0.5,
                "sync_frequency": (
                    "every_beat" if ratio > 0.8
                    else "every_2_beats" if ratio > 0.5
                    else "partial"
                ),
                "alignment_ratio": round(ratio, 3),
            }

        except Exception:
            return self._default_beat_sync()

    def _default_beat_sync(self) -> dict:
        return {
            "is_beat_synced": False,
            "estimated_bpm": 120.0,
            "cuts_align_to_beats": False,
            "sync_frequency": "none",
        }

    def _build_fallback_style_dna(self, computed: dict, matched_lut: str) -> dict:
        """Build a Style DNA dict from computed analysis alone (no Claude)."""
        cps = computed.get("cuts_per_second", 0.3)
        avg_dur = computed.get("avg_clip_duration", 3.0)
        pacing_style = (
            "fast" if cps > 0.8
            else "medium_energetic" if cps > 0.4
            else "slow_cinematic"
        )

        return {
            "pacing": {
                "avg_clip_duration": avg_dur,
                "clip_duration_std": computed.get("clip_duration_std", 0.5),
                "cuts_per_second": cps,
                "pacing_style": pacing_style,
                "rhythm": "beat_synced" if computed.get("beat_sync", {}).get("is_beat_synced") else "free",
            },
            "transitions": {
                "types_detected": computed.get("transition_type_counts", {"hard_cut": 1.0}),
                "dominant_transition": computed.get("dominant_transition", "hard_cut"),
                "avg_transition_duration": 0.3,
                "transition_consistency": "consistent",
            },
            "color": {
                "matched_lut": matched_lut,
                "lut_intensity_estimate": 0.8,
                "has_film_grain": False,
                "has_vignette": False,
                "color_description": f"Matched to {matched_lut} LUT profile",
            },
            "audio_sync": computed.get("beat_sync", self._default_beat_sync()),
            "motion": {
                "speed_ramps_detected": len(computed.get("speed_ramps_detected", [])) > 0,
                "slow_motion_used": False,
                "fast_motion_used": cps > 0.8,
            },
            "text_overlays": {"present": False, "frequency": "none"},
            "energy": {
                "level": "high" if cps > 0.8 else "medium" if cps > 0.4 else "low",
                "mood": "energetic" if cps > 0.8 else "balanced",
            },
            "overall_style": f"Detected: {pacing_style} pacing with {matched_lut} color grade",
            "_computed": computed,
        }
