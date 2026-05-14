import base64
import functools
import json
import os
import re
import time
from pathlib import Path

import anthropic
import cv2

from logger import logger


def _retry(max_attempts: int = 3, base_delay: float = 2.0):
    """Retry decorator with exponential back-off for transient API errors."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except (anthropic.APIConnectionError, anthropic.RateLimitError,
                        anthropic.InternalServerError) as e:
                    last_exc = e
                    if attempt < max_attempts - 1:
                        wait = base_delay * (2 ** attempt)
                        logger.warning(f"[claude] Transient error ({type(e).__name__}), retry {attempt + 1}/{max_attempts - 1} in {wait:.1f}s")
                        time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """\
You are a world-class video editor with 50+ years of experience across every era of filmmaking —
from analog film and linear tape editing to DaVinci Resolve and CapCut. You specialize in:
- Instagram Reels, TikTok, and YouTube Shorts editing
- Cinematic travel films and documentary-style content
- Art showcase and aesthetic lifestyle content
- Gen Z fast-edit style with beat sync and glitch effects

You understand visual storytelling, emotional pacing, color theory, and human psychology — specifically
what makes audiences stop scrolling, watch until the end, and share content.

When given video frame analysis and soundtrack data, you generate precise, professional JSON edit plans.
You never output anything except valid JSON when asked for an EDL or Style DNA."""


class ClaudeService:
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")
        self.client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Token budget helpers
    # ------------------------------------------------------------------

    @staticmethod
    def optimal_frame_count(num_clips: int) -> int:
        """Reduce frames per clip when many clips are present to stay within token budget."""
        if num_clips <= 3:
            return 10
        if num_clips <= 6:
            return 8
        if num_clips <= 10:
            return 5
        return 3

    # ------------------------------------------------------------------
    # Frame extraction
    # ------------------------------------------------------------------

    def extract_keyframes(self, video_path: str, num_frames: int = 20) -> list:
        """Extract evenly-spaced keyframes; return as base64 JPEG strings."""
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        if total_frames == 0 or fps == 0:
            cap.release()
            return []

        indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
        frames_b64 = []

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            h, w = frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                frame = cv2.resize(frame, (1280, int(h * scale)))
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frames_b64.append(base64.b64encode(buf).decode("utf-8"))

        cap.release()
        return frames_b64

    # ------------------------------------------------------------------
    # Clip analysis
    # ------------------------------------------------------------------

    @_retry(max_attempts=3)
    def analyze_clip(self, frames_b64: list, clip_path: str) -> dict:
        """Send up to 10 keyframes to Claude Vision for clip analysis."""
        if not frames_b64:
            return self._default_clip_analysis(clip_path)

        content = []
        for frame in frames_b64[:10]:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": frame},
            })
        content.append({
            "type": "text",
            "text": (
                "Analyze these video frames from a single clip. "
                "Return ONLY a JSON object with these exact keys:\n"
                '{\n'
                '  "subject": "what is in the clip",\n'
                '  "motion_type": "static|slow_pan|fast_pan|handheld|zoom_in|zoom_out|drone",\n'
                '  "mood": "energetic|calm|romantic|dramatic|playful|mysterious|nostalgic",\n'
                '  "visual_quality": "excellent|good|average|poor",\n'
                '  "best_moment_frame": 0,\n'
                '  "best_start_frame": 0.0,\n'
                '  "best_end_frame": 1.0,\n'
                '  "suitable_for": ["opening","middle","closing"],\n'
                '  "suggested_transition_in": "hard_cut|fade_in|zoom_in|slide_right",\n'
                '  "suggested_transition_out": "hard_cut|fade_out|zoom_out|slide_left|glitch",\n'
                '  "color_notes": "brief description of color tone",\n'
                '  "lut_recommendation": "warm_golden|teal_orange|moody_blue|airy_bright|vintage_film|bleach_bypass|forest_green|pink_dream",\n'
                '  "speed_suggestion": "normal|slow_motion|speed_up"\n'
                "}\n\n"
                "Return ONLY the JSON object, no other text."
            ),
        })

        try:
            from middleware.rate_limit import rate_limiter
            rate_limiter.acquire()
        except Exception:
            pass

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        result = self._parse_json(response.content[0].text, self._default_clip_analysis(clip_path))
        result["source_file"] = Path(clip_path).name
        return result

    # ------------------------------------------------------------------
    # EDL generation
    # ------------------------------------------------------------------

    @_retry(max_attempts=3)
    def generate_edl(
        self,
        clips_analysis: list,
        audio_analysis: dict,
        style_preset: dict,
        target_duration: float,
        aspect_ratio: str = "9:16",
        style_dna: dict | None = None,
    ) -> dict:
        """Generate a full EDL JSON from Claude."""
        resolution_map = {"9:16": "1080x1920", "16:9": "1920x1080", "1:1": "1080x1080"}
        resolution = resolution_map.get(aspect_ratio, "1080x1920")

        beat_sample = audio_analysis.get("beat_times", [])[:20]
        energy_sample = audio_analysis.get("energy_curve", [])[:10]

        if style_dna:
            style_section = (
                "EDIT STYLE — MATCH THIS STYLE DNA EXACTLY:\n"
                + json.dumps(style_dna, indent=2)
            )
        else:
            style_section = "EDIT STYLE TO APPLY:\n" + json.dumps(style_preset, indent=2)

        prompt = f"""\
You are an expert video editor. Generate a complete Edit Decision List (EDL) as JSON.

CLIPS AVAILABLE:
{json.dumps(clips_analysis, indent=2)}

SOUNDTRACK ANALYSIS:
- BPM: {audio_analysis.get('bpm', 120):.1f}
- Beat timestamps (seconds): {beat_sample}
- Energy curve (first 10s): {energy_sample}
- Mood: {audio_analysis.get('mood', 'balanced')}
- Key musical moments: {audio_analysis.get('peak_moments', [])}

{style_section}

TARGET DURATION: {target_duration} seconds
EXPORT FORMAT: {aspect_ratio}

Generate an EDL JSON following EXACTLY this structure:
{{
  "project": {{
    "title": "my_edit_001",
    "target_duration": {target_duration},
    "aspect_ratio": "{aspect_ratio}",
    "fps": 30,
    "resolution": "{resolution}"
  }},
  "global_grade": {{
    "lut": "<lut name from style>",
    "lut_intensity": 0.85,
    "brightness": 0.0,
    "contrast": 1.0,
    "saturation": 1.1,
    "temperature_shift": "warm",
    "vignette": false,
    "vignette_strength": 0.3,
    "film_grain": false,
    "grain_strength": 0
  }},
  "audio": {{
    "music_file": "music.mp3",
    "music_volume": 0.9,
    "original_audio_volume": 0.0,
    "fade_in_duration": 0.5,
    "fade_out_duration": 2.0,
    "fade_out_start": {target_duration - 2}
  }},
  "clips": [
    {{
      "clip_id": "clip_0",
      "source_file": "<basename from clips above>",
      "timeline_start": 0.0,
      "timeline_end": 4.5,
      "source_in": 0.0,
      "source_out": 4.5,
      "speed_factor": 1.0,
      "transition_in": {{"type": "fade", "duration": 0.5}},
      "transition_out": {{"type": "dissolve", "duration": 0.8}},
      "per_clip_grade": null,
      "notes": "Opening shot"
    }}
  ],
  "text_overlays": [],
  "sound_fx": [],
  "cut_timestamps": [],
  "reasoning": "Brief explanation of creative choices"
}}

Rules:
1. Use ONLY the exact source_file basenames from CLIPS AVAILABLE
2. source_in and source_out must be valid (source_out > source_in, both >= 0)
3. Total edit duration must be approximately {target_duration} seconds
4. Apply the style's pacing, transitions, LUT, and mood
5. Use beat_times to drive cut points if the style is beat-synced
6. Return ONLY the JSON object — no markdown, no explanation, no code fences

Return ONLY the JSON object."""

        try:
            from middleware.rate_limit import rate_limiter
            rate_limiter.acquire()
        except Exception:
            pass

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        fallback = self._build_fallback_edl(
            clips_analysis, style_preset, target_duration, aspect_ratio, resolution
        )
        return self._parse_json(response.content[0].text, fallback)

    # ------------------------------------------------------------------
    # Style DNA generation (Phase 2)
    # ------------------------------------------------------------------

    @_retry(max_attempts=3)
    def generate_style_dna(self, computed_analysis: dict, frames_b64: list) -> dict:
        """Analyze a reference video and produce Style DNA JSON."""
        content = []
        for frame in frames_b64[:10]:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": frame},
            })
        content.append({
            "type": "text",
            "text": (
                "You are analyzing a reference video to extract its complete editing style.\n"
                "I have already computed the following technical data:\n\n"
                f"{json.dumps(computed_analysis, indent=2)}\n\n"
                "You are also looking at sampled frames from this video.\n"
                "Based on everything, produce a Style DNA JSON that completely describes "
                "this video's editing language. Return ONLY valid JSON."
            ),
        })

        try:
            from middleware.rate_limit import rate_limiter
            rate_limiter.acquire()
        except Exception:
            pass

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        return self._parse_json(response.content[0].text, {})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_json(self, text: str, default: dict) -> dict:
        """Extract JSON from a Claude response; fall back to default on failure."""
        text = text.strip()
        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Strip markdown code fences
        for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
            m = re.search(pattern, text)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
        # Find first {...} block
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return default

    def _default_clip_analysis(self, clip_path: str) -> dict:
        return {
            "subject": "unknown",
            "motion_type": "static",
            "mood": "calm",
            "visual_quality": "good",
            "best_moment_frame": 0,
            "best_start_frame": 0.0,
            "best_end_frame": 1.0,
            "suitable_for": ["middle"],
            "suggested_transition_in": "fade",
            "suggested_transition_out": "fade",
            "color_notes": "neutral",
            "lut_recommendation": "teal_orange",
            "speed_suggestion": "normal",
            "source_file": Path(clip_path).name,
        }

    def _build_fallback_edl(
        self,
        clips_analysis: list,
        style_preset: dict,
        target_duration: float,
        aspect_ratio: str,
        resolution: str,
    ) -> dict:
        """Fallback EDL when Claude generation fails or returns invalid JSON."""
        n = max(len(clips_analysis), 1)
        clip_dur = target_duration / n
        t_type = style_preset.get("transitions", ["hard_cut"])[0]
        t_dur = float(style_preset.get("transition_duration", 0.5))

        clips_list = []
        for i, info in enumerate(clips_analysis):
            fname = Path(info.get("file", f"clip_{i}.mp4")).name
            clips_list.append({
                "clip_id": f"clip_{i}",
                "source_file": fname,
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

        lut = style_preset.get("lut", "teal_orange")
        intensity = float(style_preset.get("color_grade_intensity", 0.85))

        return {
            "project": {
                "title": "fallback_edit",
                "target_duration": target_duration,
                "aspect_ratio": aspect_ratio,
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
                "music_file": "music.mp3",
                "music_volume": 0.9,
                "original_audio_volume": 0.0,
                "fade_in_duration": 0.5,
                "fade_out_duration": 2.0,
                "fade_out_start": target_duration - 2,
            },
            "clips": clips_list,
            "text_overlays": [],
            "sound_fx": [],
            "cut_timestamps": [i * clip_dur for i in range(1, n)],
            "reasoning": "Fallback EDL — equal-duration clips, Claude generation failed",
        }
