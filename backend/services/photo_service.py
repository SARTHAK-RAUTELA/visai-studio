"""
Photo editing service — Phase 4.
Converts still images to animated video clips with Ken Burns pan/zoom.
Applies LUT via Pillow for color grading of still images.
"""

import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


class PhotoService:
    IMAGE_EXTENSIONS = IMAGE_EXTENSIONS

    def is_image(self, path: str) -> bool:
        """Return True if path has a recognized image extension."""
        return Path(path).suffix.lower() in self.IMAGE_EXTENSIONS

    def image_to_video(
        self,
        image_path: str,
        output_path: str,
        duration: float = 5.0,
        target_width: int = 1080,
        target_height: int = 1920,
        ken_burns: bool = True,
    ) -> str:
        """
        Convert a still image to a video clip.
        Ken Burns: slow zoom from 1.0 to 1.3, center-anchored.
        """
        w, h = target_width, target_height

        if ken_burns:
            fps = 25
            total_frames = int(duration * fps)
            vf = (
                f"zoompan=z='min(zoom+0.0008,1.3)':d={total_frames}"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h},"
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
            )
        else:
            vf = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
            )

        cmd = [
            FFMPEG_BIN, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an", "-pix_fmt", "yuv420p",
            output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def apply_lut_to_image(
        self,
        image_path: str,
        output_path: str,
        lut_path: str,
        intensity: float = 1.0,
    ) -> str:
        """
        Apply a .cube LUT to a still image using numpy trilinear interpolation.
        If intensity < 1.0, blends the result with the original.
        """
        img = Image.open(image_path).convert("RGB")
        original_arr = np.array(img, dtype=np.float32) / 255.0

        lut_size, lut_data = self._parse_cube(lut_path)

        # Apply trilinear interpolation per pixel
        result_arr = self._apply_lut_array(original_arr, lut_data, lut_size)

        if intensity < 1.0:
            result_arr = original_arr * (1.0 - intensity) + result_arr * intensity

        result_arr = np.clip(result_arr * 255.0, 0, 255).astype(np.uint8)
        Image.fromarray(result_arr).save(output_path)
        return output_path

    def enhance_image(
        self,
        image_path: str,
        output_path: str,
        brightness: float = 1.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
    ) -> str:
        """Apply brightness/contrast/saturation adjustments using PIL.ImageEnhance."""
        img = Image.open(image_path).convert("RGB")
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(saturation)
        img.save(output_path)
        return output_path

    # ── LUT helpers ─────────────────────────────────────────────────────────────

    def _parse_cube(self, lut_path: str):
        """Parse a .cube file. Returns (lut_size, np.ndarray of shape (s,s,s,3))."""
        lut_size = None
        values = []

        with open(lut_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.upper().startswith("LUT_3D_SIZE"):
                    lut_size = int(line.split()[-1])
                    continue
                if line.upper().startswith("TITLE") or line.upper().startswith("DOMAIN"):
                    continue
                parts = line.split()
                if len(parts) == 3:
                    try:
                        values.append([float(x) for x in parts])
                    except ValueError:
                        continue

        if lut_size is None:
            lut_size = round(len(values) ** (1 / 3))

        lut_array = np.array(values, dtype=np.float32).reshape(lut_size, lut_size, lut_size, 3)
        return lut_size, lut_array

    def _apply_lut_array(
        self,
        img_arr: np.ndarray,
        lut: np.ndarray,
        lut_size: int,
    ) -> np.ndarray:
        """Trilinear interpolation of a 3D LUT onto img_arr (float32, 0-1 range)."""
        s = lut_size - 1
        # Scale pixel values to LUT index space
        idx = img_arr * s  # shape (H, W, 3)

        r = np.clip(idx[:, :, 0], 0, s)
        g = np.clip(idx[:, :, 1], 0, s)
        b = np.clip(idx[:, :, 2], 0, s)

        r0 = np.floor(r).astype(np.int32)
        g0 = np.floor(g).astype(np.int32)
        b0 = np.floor(b).astype(np.int32)
        r1 = np.minimum(r0 + 1, s)
        g1 = np.minimum(g0 + 1, s)
        b1 = np.minimum(b0 + 1, s)

        dr = (r - r0)[..., np.newaxis]
        dg = (g - g0)[..., np.newaxis]
        db = (b - b0)[..., np.newaxis]

        # Trilinear interpolation
        c000 = lut[r0, g0, b0]
        c001 = lut[r0, g0, b1]
        c010 = lut[r0, g1, b0]
        c011 = lut[r0, g1, b1]
        c100 = lut[r1, g0, b0]
        c101 = lut[r1, g0, b1]
        c110 = lut[r1, g1, b0]
        c111 = lut[r1, g1, b1]

        result = (
            c000 * (1 - dr) * (1 - dg) * (1 - db)
            + c001 * (1 - dr) * (1 - dg) * db
            + c010 * (1 - dr) * dg * (1 - db)
            + c011 * (1 - dr) * dg * db
            + c100 * dr * (1 - dg) * (1 - db)
            + c101 * dr * (1 - dg) * db
            + c110 * dr * dg * (1 - db)
            + c111 * dr * dg * db
        )
        return result
