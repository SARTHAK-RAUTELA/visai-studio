import os
import shutil
import tempfile
from pathlib import Path

from services.ffmpeg_service import FFmpegService


class ExportService:
    def __init__(self, assets_dir: str = None):
        self.ffmpeg = FFmpegService()
        if assets_dir is None:
            assets_dir = Path(__file__).parent.parent / "assets"
        self.luts_dir = Path(assets_dir) / "luts"
        self.fonts_dir = Path(assets_dir) / "fonts"

    def render_from_edl(
        self,
        edl: dict,
        audio_path: str,
        output_path: str,
        clips_dir: str = None,
    ) -> str:
        """
        Full rendering pipeline:
          1. Trim clips (with speed + resize normalization)
          2. Concatenate with xfade transitions
          3. Apply global color grade (LUT + eq + vignette/grain)
          4. Burn text overlays
          5. Mix in music track
        """
        project = edl.get("project", {})
        resolution = project.get("resolution", "1080x1920")
        parts = resolution.split("x")
        target_w, target_h = int(parts[0]), int(parts[1])

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="visai_render_") as tmp:
            tmp = Path(tmp)

            # ── Step 1: Trim ──────────────────────────────────────────
            print("  [1/5] Trimming clips...")
            trimmed_clips = []
            transitions_out = []

            for i, clip_info in enumerate(edl.get("clips", [])):
                source_file = clip_info.get("source_file", "")
                clip_path = self._resolve_clip(source_file, clips_dir)
                if not clip_path:
                    print(f"    Warning: clip not found '{source_file}' — skipping")
                    continue

                source_in = float(clip_info.get("source_in", 0.0))
                source_out = float(clip_info.get("source_out", 5.0))
                speed = float(clip_info.get("speed_factor", 1.0))

                # Guard: cap source_out at actual clip duration
                actual_dur = self.ffmpeg.get_duration(clip_path)
                if actual_dur > 0:
                    source_out = min(source_out, actual_dur)
                source_in = min(source_in, source_out - 0.1)
                clip_duration = source_out - source_in

                trimmed_path = str(tmp / f"trimmed_{i:03d}.mp4")
                self.ffmpeg.trim_clip(
                    clip_path, trimmed_path,
                    start=source_in,
                    duration=clip_duration,
                    speed_factor=speed,
                    target_width=target_w,
                    target_height=target_h,
                )
                trimmed_clips.append(trimmed_path)
                transitions_out.append(clip_info.get("transition_out", {"type": "hard_cut", "duration": 0.0}))

            if not trimmed_clips:
                raise RuntimeError("No clips could be processed — check that clip files exist and are readable")

            # ── Step 2: Concatenate ──────────────────────────────────
            print("  [2/5] Concatenating with transitions...")
            concat_path = str(tmp / "concat.mp4")
            # transitions_out[i] is between trimmed_clips[i] and trimmed_clips[i+1]
            transitions_between = transitions_out[: len(trimmed_clips) - 1]
            self.ffmpeg.concat_with_transitions(trimmed_clips, transitions_between, concat_path)

            # ── Step 3: Color grade ──────────────────────────────────
            print("  [3/5] Applying color grade...")
            grade = edl.get("global_grade", {})
            lut_name = grade.get("lut", "teal_orange")
            lut_path = str(self.luts_dir / f"{lut_name}.cube")

            graded_path = str(tmp / "graded.mp4")
            self.ffmpeg.apply_color_grade(
                concat_path, graded_path,
                lut_path=lut_path if os.path.exists(lut_path) else None,
                lut_intensity=float(grade.get("lut_intensity", 1.0)),
                brightness=float(grade.get("brightness", 0.0)),
                contrast=float(grade.get("contrast", 1.0)),
                saturation=float(grade.get("saturation", 1.0)),
                vignette=bool(grade.get("vignette", False)),
                vignette_strength=float(grade.get("vignette_strength", 0.3)),
                film_grain=bool(grade.get("film_grain", False)),
                grain_strength=int(grade.get("grain_strength", 10)),
            )

            # ── Step 4: Text overlays ────────────────────────────────
            text_overlays = edl.get("text_overlays", [])
            if text_overlays:
                print("  [4/5] Adding text overlays...")
                text_path = str(tmp / "with_text.mp4")
                try:
                    self.ffmpeg.add_text_overlays(
                        graded_path, text_path,
                        overlays=text_overlays,
                        fonts_dir=str(self.fonts_dir),
                    )
                    graded_path = text_path
                except RuntimeError as e:
                    print(f"    Warning: text overlay failed ({e}); skipping overlays")
            else:
                print("  [4/5] No text overlays.")

            # ── Step 5: Audio mix ────────────────────────────────────
            print("  [5/5] Mixing audio...")
            audio_cfg = edl.get("audio", {})

            if audio_path and os.path.exists(audio_path):
                self.ffmpeg.mix_audio(
                    graded_path, audio_path, output_path,
                    music_volume=float(audio_cfg.get("music_volume", 0.9)),
                    original_audio_volume=float(audio_cfg.get("original_audio_volume", 0.0)),
                    fade_in_duration=float(audio_cfg.get("fade_in_duration", 0.5)),
                    fade_out_start=float(audio_cfg.get("fade_out_start", 28.0)),
                    fade_out_duration=float(audio_cfg.get("fade_out_duration", 2.0)),
                )
            else:
                shutil.copy2(graded_path, output_path)

        return output_path

    def _resolve_clip(self, source_file: str, clips_dir: str = None) -> str:
        """Search for the clip file in common locations."""
        candidates = []

        if os.path.isabs(source_file):
            candidates.append(source_file)

        if clips_dir:
            candidates.append(os.path.join(clips_dir, source_file))
            candidates.append(os.path.join(clips_dir, Path(source_file).name))

        candidates.append(source_file)

        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None
