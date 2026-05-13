"""
Scene detection and transition classification — Phase 2.
Uses PySceneDetect to find cut points, OpenCV for transition type classification.
"""

import cv2
import numpy as np


class SceneService:
    def detect_scenes(self, video_path: str) -> list:
        """
        Detect scene cuts using PySceneDetect.
        Returns list of (start_sec, end_sec) tuples.
        Falls back to 3-second intervals if PySceneDetect fails.
        """
        try:
            from scenedetect import detect, ContentDetector, ThresholdDetector, AdaptiveDetector
            scene_list = detect(video_path, [
                ContentDetector(threshold=27.0),
                ThresholdDetector(threshold=12.0),
                AdaptiveDetector(),
            ])
            if scene_list:
                return [(s[0].get_seconds(), s[1].get_seconds()) for s in scene_list]
        except Exception:
            pass

        # Fallback: 3-second interval slices
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        duration = total_frames / fps
        interval = 3.0
        scenes = []
        t = 0.0
        while t < duration:
            scenes.append((t, min(t + interval, duration)))
            t += interval
        return scenes if scenes else [(0.0, max(duration, 1.0))]

    def classify_transition(self, frames_before: list, frames_after: list) -> str:
        """
        Classify the transition type at a cut boundary.
        Algorithm order: fade_black → fade_white → hard_cut → dissolve → zoom → wipe → hard_cut.
        See projectDetails.md Section 3.2.
        """
        if not frames_before or not frames_after:
            return "hard_cut"

        last_before = frames_before[-1]
        first_after = frames_after[0]

        # 1. Fade to black
        gray_vals = [np.mean(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)) for f in frames_before[-5:]]
        if gray_vals and min(gray_vals) < 15:
            return "fade_black"

        # 2. Fade to white
        if gray_vals and min(gray_vals) > 240:
            return "fade_white"

        # 3. Hard cut (abrupt pixel difference)
        diff = cv2.absdiff(last_before, first_after)
        if np.mean(diff) > 40:
            return "hard_cut"

        # 4. Cross dissolve (gradual histogram progression)
        transition_region = frames_before[-5:] + frames_after[:5]
        if len(transition_region) >= 4:
            hist_scores = []
            for i in range(len(transition_region) - 1):
                h1 = cv2.calcHist([transition_region[i]], [0, 1, 2], None, [16, 16, 16], [0, 256] * 3)
                h2 = cv2.calcHist([transition_region[i + 1]], [0, 1, 2], None, [16, 16, 16], [0, 256] * 3)
                hist_scores.append(cv2.compareHist(h1, h2, cv2.HISTCMP_INTERSECT))
            if self._is_gradual_change(hist_scores):
                return "dissolve"

        # 5. Zoom (optical flow expands from center)
        try:
            gray_b = cv2.cvtColor(last_before, cv2.COLOR_BGR2GRAY)
            gray_a = cv2.cvtColor(first_after, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(gray_b, gray_a, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            if self._is_zoom_flow(flow):
                return "zoom"
        except Exception:
            pass

        # 6. Wipe (one side changes, other stays)
        if self._is_wipe_pattern(frames_before[-3:], frames_after[:3]):
            return "wipe"

        return "hard_cut"

    def extract_frames_at(
        self, cap, start_sec: float, end_sec: float, fps: float, max_frames: int = 10
    ) -> list:
        """Extract up to max_frames frames between two timestamps."""
        frames = []
        start_frame = int(start_sec * fps)
        end_frame = int(end_sec * fps)
        span = max(end_frame - start_frame, 1)
        indices = [start_frame + int(i * span / max_frames) for i in range(max_frames)]

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        return frames

    def get_frame_at(self, cap, time_sec: float):
        """Get a single frame at a specific timestamp. Returns None on failure."""
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_idx = int(time_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        return frame if ret else None

    # ── private helpers ──────────────────────────────────────────────────────

    def _is_gradual_change(self, hist_scores: list) -> bool:
        if len(hist_scores) < 3:
            return False
        mean_val = np.mean(hist_scores)
        variance = np.var(hist_scores)
        return mean_val > 0 and variance < (mean_val * 0.3)

    def _is_zoom_flow(self, flow: np.ndarray) -> bool:
        h, w = flow.shape[:2]
        cy, cx = h // 2, w // 2
        step = max(h // 8, 1)
        outward, total = 0, 0
        for y in range(0, h, step):
            for x in range(0, w, step):
                fx, fy = flow[y, x]
                dy, dx = y - cy, x - cx
                if abs(dx) + abs(dy) > 10:
                    total += 1
                    if fx * dx + fy * dy > 0:
                        outward += 1
        return total > 0 and (outward / total) > 0.65

    def _is_wipe_pattern(self, frames_before: list, frames_after: list) -> bool:
        if not frames_before or not frames_after:
            return False
        try:
            b = frames_before[-1].astype(float)
            a = frames_after[0].astype(float)
            diff = np.abs(b - a)
            h, w = diff.shape[:2]
            left_diff = np.mean(diff[:, :w // 2])
            right_diff = np.mean(diff[:, w // 2:])
            top_diff = np.mean(diff[:h // 2, :])
            bot_diff = np.mean(diff[h // 2:, :])
            ratio = 3.0
            return (
                max(left_diff, right_diff) / (min(left_diff, right_diff) + 1e-6) > ratio
                or max(top_diff, bot_diff) / (min(top_diff, bot_diff) + 1e-6) > ratio
            )
        except Exception:
            return False
