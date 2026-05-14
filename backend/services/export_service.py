import os
import shutil
import tempfile
from pathlib import Path

from logger import logger
from services.ffmpeg_service import FFmpegService, IMAGE_EXTENSIONS


class ExportService:
    def __init__(self, assets_dir: str = None):
        self.ffmpeg = FFmpegService()
        if assets_dir is None:
            assets_dir = Path(__file__).parent.parent / "assets"
        self.luts_dir = Path(assets_dir) / "luts"
        self.fonts_dir = Path(assets_dir) / "fonts"

    # Resolution presets: (width, height) indexed by aspect_ratio
    RESOLUTIONS = {
        "9:16":  {"720p": (720, 1280),  "1080p": (1080, 1920),  "4K": (2160, 3840)},
        "16:9":  {"720p": (1280, 720),  "1080p": (1920, 1080),  "4K": (3840, 2160)},
        "1:1":   {"720p": (720, 720),   "1080p": (1080, 1080),  "4K": (2160, 2160)},
        "4:5":   {"720p": (720, 900),   "1080p": (1080, 1350),  "4K": (2160, 2700)},
    }

    def render_from_edl(
        self,
        edl: dict,
        audio_path: str,
        output_path: str,
        clips_dir: str = None,
        auto_captions: bool = False,
        whisper_model: str = "base",
        resolution_preset: str = "1080p",
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
        aspect_ratio = project.get("aspect_ratio", "9:16")
        res_map = self.RESOLUTIONS.get(aspect_ratio, self.RESOLUTIONS["9:16"])
        target_w, target_h = res_map.get(resolution_preset, res_map["1080p"])
        use_hevc = resolution_preset == "4K"

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="visai_render_") as tmp:
            tmp = Path(tmp)

            # ── Step 1: Trim ──────────────────────────────────────────
            logger.info("[1/7] Trimming clips...")
            trimmed_clips = []
            transitions_out = []

            for i, clip_info in enumerate(edl.get("clips", [])):
                source_file = clip_info.get("source_file", "")
                clip_path = self._resolve_clip(source_file, clips_dir)
                if not clip_path:
                    logger.warning(f"Clip not found '{source_file}' — skipping")
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

                # Photo → video conversion with Ken Burns
                if Path(clip_path).suffix.lower() in IMAGE_EXTENSIONS:
                    self.ffmpeg.image_to_video(
                        clip_path, trimmed_path,
                        duration=clip_duration,
                        target_width=target_w,
                        target_height=target_h,
                        ken_burns=True,
                    )
                else:
                    # Speed ramp override if specified in clip info
                    ramp_type = clip_info.get("speed_ramp_type")
                    if ramp_type and speed == 1.0:
                        ramp_path = str(tmp / f"ramp_{i:03d}.mp4")
                        self.ffmpeg.trim_clip(
                            clip_path, ramp_path,
                            start=source_in, duration=clip_duration,
                            target_width=target_w, target_height=target_h,
                        )
                        self.ffmpeg.apply_speed_ramp_eased(
                            ramp_path, trimmed_path,
                            ramp_type=ramp_type,
                            target_width=target_w, target_height=target_h,
                        )
                    else:
                        self.ffmpeg.trim_clip(
                            clip_path, trimmed_path,
                            start=source_in, duration=clip_duration,
                            speed_factor=speed,
                            target_width=target_w, target_height=target_h,
                        )

                # Per-clip LUT override
                per_grade = clip_info.get("per_clip_grade")
                if per_grade:
                    per_lut_name = per_grade.get("lut", "")
                    per_lut_path = str(self.luts_dir / f"{per_lut_name}.cube") if per_lut_name else None
                    per_graded_path = str(tmp / f"per_graded_{i:03d}.mp4")
                    self.ffmpeg.apply_color_grade(
                        trimmed_path, per_graded_path,
                        lut_path=per_lut_path if per_lut_path and os.path.exists(per_lut_path) else None,
                        lut_intensity=float(per_grade.get("lut_intensity", 0.5)),
                        brightness=float(per_grade.get("brightness", 0.0)),
                        contrast=float(per_grade.get("contrast", 1.0)),
                        saturation=float(per_grade.get("saturation", 1.0)),
                    )
                    trimmed_path = per_graded_path

                trimmed_clips.append(trimmed_path)
                transitions_out.append(clip_info.get("transition_out", {"type": "hard_cut", "duration": 0.0}))

            if not trimmed_clips:
                raise RuntimeError("No clips could be processed — check that clip files exist and are readable")

            # ── Step 2: Concatenate ──────────────────────────────────
            logger.info("[2/7] Concatenating with transitions...")
            concat_path = str(tmp / "concat.mp4")
            # transitions_out[i] is between trimmed_clips[i] and trimmed_clips[i+1]
            transitions_between = transitions_out[: len(trimmed_clips) - 1]
            self.ffmpeg.concat_with_transitions(trimmed_clips, transitions_between, concat_path)

            # ── Step 3: Color grade ──────────────────────────────────
            logger.info("[3/7] Applying color grade...")
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
                logger.info("[4/7] Adding text overlays...")
                text_path = str(tmp / "with_text.mp4")
                try:
                    self.ffmpeg.add_text_overlays(
                        graded_path, text_path,
                        overlays=text_overlays,
                        fonts_dir=str(self.fonts_dir),
                    )
                    graded_path = text_path
                except RuntimeError as e:
                    logger.warning(f"Text overlay failed ({e}); skipping overlays")
            else:
                logger.info("[4/7] No text overlays.")

            # ── Step 5: Auto-captions (Whisper) ─────────────────────
            if auto_captions:
                logger.info("[5/7] Generating auto-captions with Whisper...")
                caption_overlays = self.ffmpeg.generate_captions(graded_path, whisper_model)
                if caption_overlays:
                    captions_path = str(tmp / "with_captions.mp4")
                    try:
                        self.ffmpeg.add_text_overlays(
                            graded_path, captions_path,
                            overlays=caption_overlays,
                            fonts_dir=str(self.fonts_dir),
                        )
                        graded_path = captions_path
                    except RuntimeError as e:
                        logger.warning(f"Captions failed ({e}) — skipping")
                else:
                    logger.info("[5/7] No captions generated.")
            else:
                logger.info("[5/7] Auto-captions disabled.")

            # ── Step 6: Sound FX ─────────────────────────────────────
            sound_fx = edl.get("sound_fx", [])
            if sound_fx:
                logger.info("[6/7] Mixing sound FX...")
                sfx_path = str(tmp / "with_sfx.mp4")
                sfx_dir = str(self.luts_dir.parent / "sfx")
                try:
                    self.ffmpeg.mix_sound_fx(graded_path, sfx_path, sound_fx, sfx_dir)
                    graded_path = sfx_path
                except RuntimeError as e:
                    logger.warning(f"SFX mixing failed ({e}) — skipping")
            else:
                logger.info("[6/7] No sound FX.")

            # ── Step 7: Audio mix ────────────────────────────────────
            logger.info("[7/7] Mixing audio...")
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
