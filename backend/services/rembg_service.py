"""
Background removal service — Phase 4.
Uses rembg for AI-powered background removal (no green screen needed).
Processes clips frame by frame or uses rembg's video support.
Gracefully skips if rembg is not installed.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")


class RembgService:
    def remove_background(
        self,
        input_path: str,
        output_path: str,
        bg_color: tuple = (0, 0, 0),
        bg_path: str = None,
    ) -> str:
        """
        Remove background from a video clip.
        Extracts frames, runs rembg on each, composites onto bg_color or bg_path image,
        reassembles with FFmpeg preserving original audio.
        Falls back to copying input if rembg is not installed.
        """
        try:
            import rembg
            from PIL import Image
        except ImportError:
            print("Warning: rembg is not installed. Copying input to output unchanged.")
            shutil.copy2(input_path, output_path)
            return output_path

        import cv2

        with tempfile.TemporaryDirectory(prefix="visai_rembg_") as tmp:
            tmp = Path(tmp)
            frames_in = tmp / "frames_in"
            frames_out = tmp / "frames_out"
            frames_in.mkdir()
            frames_out.mkdir()

            # Extract frames
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                shutil.copy2(input_path, output_path)
                return output_path

            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_path = frames_in / f"frame_{idx:06d}.jpg"
                cv2.imwrite(str(frame_path), frame)
                idx += 1
            cap.release()

            if idx == 0:
                shutil.copy2(input_path, output_path)
                return output_path

            # Load background image once if provided
            bg_img = None
            if bg_path and os.path.exists(bg_path):
                bg_img = Image.open(bg_path).convert("RGBA")

            # Process frames
            rembg_session = rembg.new_session()
            for frame_path in sorted(frames_in.glob("frame_*.jpg")):
                with open(frame_path, "rb") as f:
                    img_data = f.read()

                result_bytes = rembg.remove(img_data, session=rembg_session)
                fg = Image.open(__import__("io").BytesIO(result_bytes)).convert("RGBA")

                w, h = fg.size
                if bg_img:
                    bg = bg_img.resize((w, h)).convert("RGBA")
                else:
                    bg = Image.new("RGBA", (w, h), (*bg_color, 255))

                composite = Image.alpha_composite(bg, fg).convert("RGB")
                out_frame = frames_out / frame_path.name.replace(".jpg", ".png")
                composite.save(str(out_frame))

            # Reassemble video
            silent_path = str(tmp / "silent.mp4")
            cmd_video = [
                FFMPEG_BIN, "-y",
                "-framerate", str(fps),
                "-i", str(frames_out / "frame_%06d.png"),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p",
                silent_path,
            ]
            subprocess.run(cmd_video, check=True, capture_output=True)

            # Mux original audio back
            cmd_audio = [
                FFMPEG_BIN, "-y",
                "-i", silent_path,
                "-i", input_path,
                "-map", "0:v:0",
                "-map", "1:a?",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest",
                output_path,
            ]
            subprocess.run(cmd_audio, check=True, capture_output=True)

        return output_path

    def remove_background_image(self, image_path: str, output_path: str) -> str:
        """Remove background from a single still image using PIL + rembg."""
        try:
            import rembg
            from PIL import Image
        except ImportError:
            print("Warning: rembg is not installed. Copying input to output unchanged.")
            shutil.copy2(image_path, output_path)
            return output_path

        with open(image_path, "rb") as f:
            data = f.read()

        result = rembg.remove(data)
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(result))
        img.save(output_path)
        return output_path
