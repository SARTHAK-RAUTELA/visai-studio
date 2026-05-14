import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from logger import logger

# Maps VisualAI transition names → FFmpeg xfade transition names
XFADE_MAP = {
    "fade": "fade",
    "fade_black": "fadeblack",
    "fade_white": "fadewhite",
    "dissolve": "dissolve",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "slide_left": "slideleft",
    "slide_right": "slideright",
    "zoom_in": "zoominA",
    "zoom_out": "zoomout",
    "spin": "rotate",
    "circle_open": "circleopen",
    "pixelate": "pixelize",
    # These map to fade as FFmpeg equivalents; custom implementations are Phase 4
    "glitch": "fade",
    "flash": "fadewhite",
    "flash_black": "fadeblack",
    "zoom_punch": "zoominA",
    "ken_burns": "fade",
    "hard_cut": None,  # handled separately via concat
}


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}


class FFmpegService:
    def __init__(self, ffmpeg_bin: str = None, ffprobe_bin: str = None, threads: int = None):
        self.ffmpeg = ffmpeg_bin or os.getenv("FFMPEG_BIN", "ffmpeg")
        self.ffprobe = ffprobe_bin or os.getenv("FFPROBE_BIN", "ffprobe")
        self.threads = threads or int(os.getenv("FFMPEG_THREADS", "4"))
        self._encoder = None  # lazily detected

    def _get_encoder(self, use_hevc: bool = False) -> str:
        """Return the best available encoder. Auto-detects NVENC once and caches result."""
        if use_hevc:
            try:
                r = subprocess.run(
                    [self.ffmpeg, "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
                     "-c:v", "hevc_nvenc", "-f", "null", "-"],
                    capture_output=True, timeout=5,
                )
                if r.returncode == 0:
                    return "hevc_nvenc"
            except Exception:
                pass
            return "libx265"

        if self._encoder is None:
            try:
                r = subprocess.run(
                    [self.ffmpeg, "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
                     "-c:v", "h264_nvenc", "-f", "null", "-"],
                    capture_output=True, timeout=5,
                )
                self._encoder = "h264_nvenc" if r.returncode == 0 else "libx264"
            except Exception:
                self._encoder = "libx264"
        return self._encoder

    def run(self, cmd: list, raise_on_error: bool = True) -> tuple:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if raise_on_error and result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg command failed (exit {result.returncode}):\n"
                f"CMD: {' '.join(str(c) for c in cmd)}\n"
                f"STDERR (last 2000 chars): {result.stderr[-2000:]}"
            )
        return result.returncode, result.stdout, result.stderr

    def get_duration(self, video_path: str) -> float:
        cmd = [
            self.ffprobe, "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(result.stdout)
            stream = data.get("streams", [{}])[0]
            return float(stream.get("duration", 0))
        except (json.JSONDecodeError, IndexError, ValueError):
            return 0.0

    def trim_clip(
        self,
        input_path: str,
        output_path: str,
        start: float,
        duration: float,
        speed_factor: float = 1.0,
        target_width: int = None,
        target_height: int = None,
    ) -> str:
        """Trim a clip to [start, start+duration] with optional speed and resize."""
        filters = []

        if target_width and target_height:
            scale = (
                f"scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={target_width}:{target_height}"
            )
            filters.append(scale)

        if speed_factor != 1.0:
            pts = 1.0 / speed_factor
            filters.append(f"setpts={pts:.6f}*PTS")

        cmd = [self.ffmpeg, "-y", "-ss", str(start), "-t", str(duration), "-i", input_path]

        if filters:
            cmd += ["-vf", ",".join(filters)]

        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an",  # drop audio; we mix separately
            "-threads", str(self.threads),
            output_path,
        ]
        self.run(cmd)
        return output_path

    def concat_with_transitions(
        self,
        clip_paths: list,
        transitions: list,
        output_path: str,
    ) -> str:
        """
        Concatenate clips with xfade transitions.
        transitions[i] = transition between clip[i] and clip[i+1].
        len(transitions) must be len(clip_paths) - 1.
        """
        n = len(clip_paths)
        if n == 0:
            raise ValueError("No clips to concatenate")

        if n == 1:
            shutil.copy2(clip_paths[0], output_path)
            return output_path

        # Fetch actual durations for offset calculations
        durations = [self.get_duration(p) for p in clip_paths]

        # Build input args
        cmd = [self.ffmpeg, "-y"]
        for p in clip_paths:
            cmd += ["-i", p]

        all_hard_cut = all(
            t.get("type", "hard_cut") == "hard_cut" for t in transitions
        )

        if all_hard_cut:
            concat_inputs = "".join(f"[{i}:v]" for i in range(n))
            filter_str = f"{concat_inputs}concat=n={n}:v=1:a=0[outv]"
            cmd += ["-filter_complex", filter_str, "-map", "[outv]"]
        else:
            # Build xfade chain; track output_len to compute correct offsets
            filter_parts = []
            output_len = durations[0]
            current_label = "[0:v]"

            for i in range(n - 1):
                t = transitions[i] if i < len(transitions) else {"type": "hard_cut", "duration": 0.0}
                t_type = t.get("type", "hard_cut")
                t_dur = max(float(t.get("duration", 0.0)), 0.05)

                xfade_type = XFADE_MAP.get(t_type, "fade")
                if xfade_type is None:
                    xfade_type = "fade"

                # Clamp t_dur to be less than both adjacent clip durations
                t_dur = min(t_dur, durations[i] * 0.8, durations[i + 1] * 0.8)
                t_dur = max(t_dur, 0.05)

                offset = max(output_len - t_dur, 0.0)
                next_label = f"[xf{i + 1}]"

                filter_parts.append(
                    f"{current_label}[{i + 1}:v]xfade=transition={xfade_type}:"
                    f"duration={t_dur:.3f}:offset={offset:.3f}{next_label}"
                )

                current_label = next_label
                output_len = output_len - t_dur + durations[i + 1]

            final_label = f"[xf{n - 1}]"
            filter_str = ";".join(filter_parts)
            cmd += ["-filter_complex", filter_str, "-map", final_label]

        encoder = self._get_encoder()
        cmd += [
            "-c:v", encoder, "-preset", "fast", "-crf", "18",
            "-threads", str(self.threads),
            output_path,
        ]
        self.run(cmd)
        return output_path

    def apply_color_grade(
        self,
        input_path: str,
        output_path: str,
        lut_path: str = None,
        lut_intensity: float = 1.0,
        brightness: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        vignette: bool = False,
        vignette_strength: float = 0.3,
        film_grain: bool = False,
        grain_strength: int = 10,
    ) -> str:
        """Apply LUT + exposure adjustments + optional vignette/grain."""
        filters = []

        if lut_path and os.path.exists(lut_path):
            safe_lut = self._ffmpeg_path(lut_path)
            filters.append(f"lut3d=file='{safe_lut}'")

        eq_parts = []
        if abs(brightness) > 0.001:
            eq_parts.append(f"brightness={brightness:.4f}")
        if abs(contrast - 1.0) > 0.001:
            eq_parts.append(f"contrast={contrast:.4f}")
        if abs(saturation - 1.0) > 0.001:
            eq_parts.append(f"saturation={saturation:.4f}")
        if eq_parts:
            filters.append(f"eq={':'.join(eq_parts)}")

        if vignette and vignette_strength > 0:
            angle = vignette_strength * (3.14159 / 4)
            filters.append(f"vignette=angle={angle:.4f}")

        if film_grain and grain_strength > 0:
            filters.append(f"noise=alls={grain_strength}:allf=t+u")

        if not filters:
            shutil.copy2(input_path, output_path)
            return output_path

        cmd = [
            self.ffmpeg, "-y", "-i", input_path,
            "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-threads", str(self.threads),
            output_path,
        ]
        self.run(cmd)
        return output_path

    def mix_audio(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        music_volume: float = 0.9,
        original_audio_volume: float = 0.0,
        fade_in_duration: float = 0.5,
        fade_out_start: float = 28.0,
        fade_out_duration: float = 2.0,
    ) -> str:
        """Mix music track into video with fade in/out."""
        fade = f"afade=t=in:st=0:d={fade_in_duration:.2f}"
        if fade_out_start > 0:
            fade += f",afade=t=out:st={fade_out_start:.2f}:d={fade_out_duration:.2f}"

        cmd = [self.ffmpeg, "-y", "-i", video_path, "-i", audio_path]

        if original_audio_volume > 0.001:
            filter_complex = (
                f"[0:a]volume={original_audio_volume:.3f}[orig];"
                f"[1:a]volume={music_volume:.3f},{fade}[music];"
                f"[orig][music]amix=inputs=2:duration=first[outa]"
            )
            cmd += ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[outa]"]
        else:
            filter_complex = f"[1:a]volume={music_volume:.3f},{fade}[outa]"
            cmd += ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[outa]"]

        cmd += [
            "-shortest",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]
        self.run(cmd)
        return output_path

    def add_text_overlays(
        self,
        input_path: str,
        output_path: str,
        overlays: list,
        fonts_dir: str = None,
    ) -> str:
        """Burn text overlays using FFmpeg drawtext filter."""
        if not overlays:
            shutil.copy2(input_path, output_path)
            return output_path

        FONT_SIZE_MAP = {"small": 28, "medium": 42, "large": 60}
        POSITION_MAP = {
            "top": ("(w-text_w)/2", "50"),
            "center": ("(w-text_w)/2", "(h-text_h)/2"),
            "bottom": ("(w-text_w)/2", "h-80"),
            "lower_third": ("(w-text_w)/2", "h*3/4"),
        }

        drawtext_parts = []
        for ov in overlays:
            text = str(ov.get("text", "")).replace("'", "\\'").replace(":", "\\:")
            if not text:
                continue
            start = float(ov.get("start_time", 0))
            dur = float(ov.get("duration", 2))
            end = start + dur
            pos = ov.get("position", "bottom")
            size = ov.get("size", "medium")
            color = ov.get("color", "white")
            opacity = float(ov.get("opacity", 0.9))

            x, y = POSITION_MAP.get(pos, POSITION_MAP["bottom"])
            fs = FONT_SIZE_MAP.get(size, 42)

            alpha = (
                f"if(lt(t,{start:.2f}+0.3),(t-{start:.2f})/0.3,"
                f"if(gt(t,{end:.2f}-0.3),({end:.2f}-t)/0.3,{opacity:.2f}))"
            )

            font_arg = ""
            if fonts_dir:
                font_file = os.path.join(fonts_dir, "minimal_sans.ttf")
                if os.path.exists(font_file):
                    font_arg = f":fontfile='{self._ffmpeg_path(font_file)}'"

            drawtext_parts.append(
                f"drawtext=text='{text}'{font_arg}:fontsize={fs}:"
                f"fontcolor={color}:x={x}:y={y}:"
                f"enable='between(t,{start:.2f},{end:.2f})':"
                f"alpha='{alpha}'"
            )

        if not drawtext_parts:
            shutil.copy2(input_path, output_path)
            return output_path

        cmd = [
            self.ffmpeg, "-y", "-i", input_path,
            "-vf", ",".join(drawtext_parts),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-threads", str(self.threads),
            output_path,
        ]
        self.run(cmd)
        return output_path

    def image_to_video(
        self,
        image_path: str,
        output_path: str,
        duration: float = 5.0,
        target_width: int = 1080,
        target_height: int = 1920,
        ken_burns: bool = True,
    ) -> str:
        """Convert a still image to a video clip with optional Ken Burns zoom."""
        total_frames = max(int(duration * 25), 1)
        if ken_burns:
            vf = (
                f"zoompan=z='min(zoom+0.0008,1.3)':"
                f"d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':"
                f"s={target_width}x{target_height},"
                f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2"
            )
        else:
            vf = (
                f"scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2"
            )
        cmd = [
            self.ffmpeg, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an", "-pix_fmt", "yuv420p",
            "-threads", str(self.threads),
            output_path,
        ]
        self.run(cmd)
        return output_path

    def apply_speed_ramp_eased(
        self,
        input_path: str,
        output_path: str,
        ramp_type: str = "ease_out",
        target_width: int = None,
        target_height: int = None,
    ) -> str:
        """
        Apply a smooth two-segment speed ramp.
        ease_in  : first half at 2× speed, second half at 1× (fast → normal)
        ease_out : first half at 1× speed, second half at 2× (normal → fast)
        slow_mo  : full clip at 0.5× speed (hero slow motion)
        """
        duration = self.get_duration(input_path)
        if duration <= 0.5:
            shutil.copy2(input_path, output_path)
            return output_path

        resize = ""
        if target_width and target_height:
            resize = (
                f"scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={target_width}:{target_height},"
            )

        if ramp_type == "slow_mo":
            cmd = [
                self.ffmpeg, "-y", "-i", input_path,
                "-vf", f"{resize}setpts=2.0*PTS",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-an", "-threads", str(self.threads),
                output_path,
            ]
            self.run(cmd)
            return output_path

        mid = duration / 2
        speed1, speed2 = (2.0, 1.0) if ramp_type == "ease_in" else (1.0, 2.0)

        import tempfile
        with tempfile.TemporaryDirectory(prefix="visai_ramp_") as tmp:
            tmp = Path(tmp)
            p1, p2 = str(tmp / "seg1.mp4"), str(tmp / "seg2.mp4")

            for path, pts, start, dur in [
                (p1, 1.0 / speed1, 0, mid),
                (p2, 1.0 / speed2, mid, duration - mid),
            ]:
                cmd = [
                    self.ffmpeg, "-y",
                    "-ss", str(start), "-t", str(dur), "-i", input_path,
                    "-vf", f"{resize}setpts={pts:.4f}*PTS",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-an", "-threads", str(self.threads), path,
                ]
                self.run(cmd)

            self.concat_with_transitions(
                [p1, p2], [{"type": "hard_cut", "duration": 0}], output_path
            )
        return output_path

    def generate_captions(self, video_path: str, whisper_model: str = "base") -> list:
        """
        Run Whisper on the video's audio track and return caption segments
        formatted as text-overlay dicts (compatible with add_text_overlays).
        Gracefully returns [] if whisper is not installed or fails.
        """
        try:
            import whisper
        except ImportError:
            logger.info("[captions] openai-whisper not installed — skipping")
            return []

        import tempfile
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            self.run([
                self.ffmpeg, "-y", "-i", video_path,
                "-vn", "-ar", "16000", "-ac", "1", tmp_path,
            ])
            model = whisper.load_model(whisper_model)
            result = model.transcribe(tmp_path)
            os.unlink(tmp_path)

            overlays = []
            for seg in result.get("segments", []):
                text = seg["text"].strip()
                if text:
                    overlays.append({
                        "text": text,
                        "start_time": float(seg["start"]),
                        "duration": float(seg["end"]) - float(seg["start"]),
                        "position": "bottom",
                        "animation": "fade",
                        "size": "small",
                        "color": "white",
                        "opacity": 0.9,
                    })
            return overlays

        except Exception as e:
            logger.warning(f"[captions] Whisper failed ({e}) — skipping")
            return []

    def mix_sound_fx(
        self,
        video_path: str,
        output_path: str,
        sound_fx: list,
        sfx_dir: str,
    ) -> str:
        """
        Overlay sound FX at specific timestamps using FFmpeg adelay + amix.
        Skips silently if no SFX files exist.
        """
        valid_fx = []
        for fx in sound_fx:
            sfx_path = os.path.join(sfx_dir, fx.get("file", ""))
            if os.path.exists(sfx_path):
                valid_fx.append({**fx, "path": sfx_path})

        if not valid_fx:
            shutil.copy2(video_path, output_path)
            return output_path

        cmd = [self.ffmpeg, "-y", "-i", video_path]
        for fx in valid_fx:
            cmd += ["-i", fx["path"]]

        filter_parts = []
        mix_labels = ["[0:a]"]
        for i, fx in enumerate(valid_fx):
            delay_ms = int(float(fx.get("timeline_time", 0)) * 1000)
            vol = float(fx.get("volume", 0.5))
            label = f"[sfx{i}]"
            filter_parts.append(
                f"[{i + 1}:a]adelay={delay_ms}|{delay_ms},volume={vol:.3f}{label}"
            )
            mix_labels.append(label)

        n = len(mix_labels)
        filter_parts.append(f"{''.join(mix_labels)}amix=inputs={n}:duration=first[outa]")

        cmd += [
            "-filter_complex", ";".join(filter_parts),
            "-map", "0:v", "-map", "[outa]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-threads", str(self.threads),
            output_path,
        ]
        self.run(cmd)
        return output_path

    def reframe_clip(
        self,
        input_path: str,
        output_path: str,
        target_ratio: str = "9:16",
    ) -> str:
        """Crop and scale a video clip to a new aspect ratio."""
        from services.export_service import ExportService
        res_map = ExportService.RESOLUTIONS.get(target_ratio, ExportService.RESOLUTIONS["9:16"])
        w, h = res_map.get("1080p", (1080, 1920))

        probe = subprocess.run(
            [self.ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", input_path],
            capture_output=True, text=True,
        )
        src_w, src_h = 1920, 1080
        try:
            data = json.loads(probe.stdout)
            stream = data.get("streams", [{}])[0]
            src_w = int(stream.get("width", 1920))
            src_h = int(stream.get("height", 1080))
        except Exception:
            pass

        src_ar = src_w / src_h
        tgt_ar = w / h
        if src_ar > tgt_ar:
            crop_h = src_h
            crop_w = int(src_h * tgt_ar)
        else:
            crop_w = src_w
            crop_h = int(src_w / tgt_ar)
        crop_x = (src_w - crop_w) // 2
        crop_y = (src_h - crop_h) // 2

        vf = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={w}:{h}"
        cmd = [
            self.ffmpeg, "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-threads", str(self.threads),
            output_path,
        ]
        self.run(cmd)
        return output_path

    def apply_audio_ducking(
        self,
        video_path: str,
        output_path: str,
        duck_gain: float = 8.0,
    ) -> str:
        """Reduce loud music peaks to improve dialog clarity.

        Uses FFmpeg compand filter — brings down peaks > -20 dB by duck_gain dB,
        which simulates background music ducking under voice.
        """
        filter_str = (
            f"[0:a]compand="
            f"attacks=0.3:decays=1.0:"
            f"points=-80/-80|-20/-20|0/-{duck_gain:.1f}:"
            f"soft-knee=0.5[aout]"
        )
        cmd = [
            self.ffmpeg, "-y", "-i", video_path,
            "-filter_complex", filter_str,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-threads", str(self.threads),
            output_path,
        ]
        self.run(cmd)
        return output_path

    def generate_thumbnail(self, video_path: str, seek: float = 1.0, width: int = 160) -> str:
        """Extract one frame, return as base64 JPEG string. Returns '' on failure."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
            self.run([
                self.ffmpeg, "-y", "-ss", str(seek), "-i", video_path,
                "-vframes", "1", "-vf", f"scale={width}:-1",
                tmp_path,
            ], raise_on_error=False)
            p = Path(tmp_path)
            if p.exists() and p.stat().st_size > 0:
                data = base64.b64encode(p.read_bytes()).decode()
                p.unlink(missing_ok=True)
                return data
            p.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"Thumbnail generation failed for {video_path}: {e}")
        return ""

    @staticmethod
    def _ffmpeg_path(path: str) -> str:
        """
        Convert a filesystem path to a format safe for FFmpeg filter option values.
        Escapes the Windows drive-letter colon and replaces backslashes.
        The result is intended to be wrapped in single quotes inside a filter string.
        """
        p = path.replace("\\", "/")
        # Escape colon in Windows drive letter: C: -> C\:
        if len(p) >= 2 and p[1] == ":":
            p = p[0] + "\\:" + p[2:]
        p = p.replace("'", "\\'")
        return p
