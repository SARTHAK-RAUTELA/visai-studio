"""
Color analysis and LUT matching — Phase 2.
Analyzes color grade of reference video frames and matches to LUT library.
"""

import cv2
import numpy as np

# Approximate color-profile fingerprints for each LUT.
# Format: (shadow_hue, highlight_hue, saturation, contrast, brightness)
# Hue values use OpenCV HSV scale (0–180). Shadow hue ~ color cast in dark regions.
_LUT_PROFILES = {
    "teal_orange":   (100, 15,  160, 60,  120),
    "warm_golden":   (20,  20,  170, 45,  145),
    "moody_blue":    (110, 110, 100, 75,  90),
    "vintage_film":  (18,  18,  120, 50,  130),
    "airy_bright":   (70,  70,  90,  30,  180),
    "bleach_bypass": (80,  80,  60,  85,  100),
    "pink_dream":    (160, 10,  140, 35,  155),
    "forest_green":  (70,  70,  150, 55,  110),
    "cyberpunk":     (130, 155, 180, 80,  95),
    "matte_black":   (80,  80,  70,  90,  85),
    "sunrise":       (10,  10,  165, 55,  150),
    "nordic":        (110, 100, 75,  50,  140),
}

# Weights for Euclidean distance: hue channels matter most
_WEIGHTS = np.array([2.0, 2.0, 1.5, 1.0, 0.5])


class ColorService:
    def analyze_color_grade(self, frame_bgr: np.ndarray) -> dict:
        """
        Analyze the color grade of a single frame.
        Returns shadow_hue, highlight_hue, saturation, contrast, brightness.
        See projectDetails.md Section 3.3 for algorithm.
        """
        if frame_bgr is None:
            return self._default_profile()

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

        shadow_mask = v < np.percentile(v, 15)
        highlight_mask = v > np.percentile(v, 85)

        shadow_hue = float(np.mean(h[shadow_mask])) if np.any(shadow_mask) else 80.0
        highlight_hue = float(np.mean(h[highlight_mask])) if np.any(highlight_mask) else 30.0

        return {
            "shadow_hue": shadow_hue,
            "highlight_hue": highlight_hue,
            "saturation": float(np.mean(s)),
            "contrast": float(np.std(v)),
            "brightness": float(np.mean(v)),
        }

    def average_color_profiles(self, profiles: list) -> dict:
        """Average a list of color profiles into a single representative profile."""
        if not profiles:
            return self._default_profile()
        keys = ["shadow_hue", "highlight_hue", "saturation", "contrast", "brightness"]
        return {k: float(np.mean([p.get(k, 0) for p in profiles])) for k in keys}

    def match_to_lut_library(self, color_profile: dict) -> str:
        """
        Return the LUT name whose fingerprint is closest to color_profile,
        using weighted Euclidean distance.
        """
        vec = np.array([
            color_profile.get("shadow_hue", 80),
            color_profile.get("highlight_hue", 30),
            color_profile.get("saturation", 120),
            color_profile.get("contrast", 50),
            color_profile.get("brightness", 120),
        ], dtype=float)

        best_lut = "teal_orange"
        best_dist = float("inf")

        for lut_name, ref_tuple in _LUT_PROFILES.items():
            ref = np.array(ref_tuple, dtype=float)
            dist = float(np.sqrt(np.sum(_WEIGHTS * (vec - ref) ** 2)))
            if dist < best_dist:
                best_dist = dist
                best_lut = lut_name

        return best_lut

    def _default_profile(self) -> dict:
        return {
            "shadow_hue": 80.0,
            "highlight_hue": 30.0,
            "saturation": 120.0,
            "contrast": 50.0,
            "brightness": 120.0,
        }
