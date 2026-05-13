"""
ClipExtractorService — smart moment extraction from long videos.

For any clip longer than LONG_THRESHOLD seconds:
  1. Detect scenes via PySceneDetect (falls back to fixed intervals)
  2. Score each scene by motion energy (optical flow) + duration fit
  3. Extract the top N scenes as physical temp clips via FFmpeg trim_clip

Short clips (<= threshold) are returned unchanged.
"""

import os
import uuid

import cv2
import numpy as np


LONG_THRESHOLD   = 15.0   # clips shorter than this are used as-is
MIN_SCENE_DUR    = 2.0    # discard scenes shorter than this
MAX_SCENE_DUR    = 8.0    # cap each extracted clip at this length
IDEAL_SCENE_DUR  = 5.0    # scoring target duration


class ClipExtractorService:
    def __init__(self, ffmpeg_service=None):
        from services.ffmpeg_service import FFmpegService
        self.ff = ffmpeg_service or FFmpegService()

    def maybe_extract(self, video_path: str, temp_dir: str, max_clips: int = 4) -> list:
        """
        Return a list of clip paths to use in the edit.
        Long videos are expanded into their best sub-clips.
        Short videos are returned as [video_path] unchanged.
        """
        duration = self.ff.get_duration(video_path)
        if duration <= LONG_THRESHOLD:
            return [video_path]

        print(f"  [extractor] {os.path.basename(video_path)} is {duration:.1f}s — extracting best moments")

        scenes = self._detect_scenes(video_path, duration)
        scored = self._score_scenes(scenes, video_path)
        selected = scored[:max_clips]

        if not selected:
            return [video_path]

        extracted = []
        for start, end, score in selected:
            clip_dur = min(end - start, MAX_SCENE_DUR)
            out_path = os.path.join(temp_dir, f"extract_{uuid.uuid4().hex[:8]}.mp4")
            try:
                self.ff.trim_clip(video_path, out_path, start=start, duration=clip_dur)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    extracted.append(out_path)
                    print(f"    scene {start:.1f}s–{end:.1f}s  score={score:.1f}  → {os.path.basename(out_path)}")
            except Exception as e:
                print(f"    [extractor] Could not extract {start:.1f}–{end:.1f}: {e}")

        return extracted if extracted else [video_path]

    # ── private ───────────────────────────────────────────────────────────────

    def _detect_scenes(self, video_path: str, duration: float) -> list:
        """Return list of (start_sec, end_sec) with usable duration."""
        try:
            from services.scene_service import SceneService
            raw = SceneService().detect_scenes(video_path)
            filtered = [(s, e) for s, e in raw if (e - s) >= MIN_SCENE_DUR]
            if filtered:
                return filtered
        except Exception:
            pass

        # Fallback: fixed-interval segments
        seg = IDEAL_SCENE_DUR
        scenes, t = [], 0.0
        while t < duration - MIN_SCENE_DUR:
            scenes.append((t, min(t + seg, duration)))
            t += seg
        return scenes

    def _score_scenes(self, scenes: list, video_path: str) -> list:
        """
        Score by inter-frame motion energy (70 %) + duration fit (30 %).
        Returns list of (start, end, score) sorted descending.
        """
        scored = []
        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

            for start, end in scenes:
                dur = end - start
                sample_times = [start + dur * frac for frac in (0.2, 0.5, 0.8)]

                frames = []
                for t in sample_times:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
                    ret, frame = cap.read()
                    if ret:
                        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))

                motion = 0.0
                if len(frames) >= 2:
                    diffs = [np.mean(cv2.absdiff(frames[i], frames[i + 1]))
                             for i in range(len(frames) - 1)]
                    motion = float(np.mean(diffs))

                dur_score = 1.0 - min(abs(dur - IDEAL_SCENE_DUR) / IDEAL_SCENE_DUR, 1.0)
                score = motion * 0.7 + dur_score * 30.0 * 0.3
                scored.append((start, end, score))
        except Exception:
            scored = [(s, e, 1.0) for s, e in scenes]
        finally:
            if cap is not None:
                cap.release()

        scored.sort(key=lambda x: x[2], reverse=True)
        return scored
