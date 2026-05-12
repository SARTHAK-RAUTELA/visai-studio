import json
import os
import shutil
import subprocess
from pathlib import Path

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


class FFmpegService:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe", threads: int = 4):
        self.ffmpeg = ffmpeg_bin
        self.ffprobe = ffprobe_bin
        self.threads = threads

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

        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
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
