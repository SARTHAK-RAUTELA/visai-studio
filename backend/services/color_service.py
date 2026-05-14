"""
Color analysis and LUT matching — Phase 2 (improved in Phase 5+).
Uses CIE L*a*b* color space for perceptually accurate LUT matching.
"""

import cv2
import numpy as np

# Lab fingerprints for each LUT.
# Format: (L_mean, a_mean, b_mean, L_std, a_std)
# L: luminance 0-255, a: green(-128)→red(+128), b: blue(-128)→yellow(+128) in OpenCV scale (0-255 offset by 128)
# These represent the average appearance of footage graded with each LUT.
_LUT_PROFILES_LAB = {
    #                   L     a     b     L_std  a_std
    "teal_orange":   (118, 118,  138,   42,   12),  # warm highlights, teal shadows
    "warm_golden":   (135, 122,  145,   38,   10),  # golden warm, slight lift
    "moody_blue":    ( 90, 122,  118,   50,    8),  # dark, cool blue cast
    "vintage_film":  (120, 125,  138,   35,    9),  # warm with reduced saturation
    "airy_bright":   (165, 125,  128,   28,    6),  # high key, low saturation
    "bleach_bypass": ( 95, 128,  128,   60,    5),  # high contrast, desaturated
    "pink_dream":    (140, 138,  122,   30,   14),  # pink/lavender cast
    "forest_green":  (105, 118,  135,   40,   10),  # green midtones
    "cyberpunk":     ( 88, 118,  145,   55,   16),  # neon: magenta + cyan
    "matte_black":   ( 80, 126,  126,   55,    5),  # lifted blacks, matte
    "sunrise":       (138, 125,  148,   40,   11),  # warm orange-yellow
    "nordic":        (118, 122,  122,   45,    7),  # cool, desaturated, slightly blue
}

# Perceptual weights for Lab distance (L matters most for mood matching)
_LAB_WEIGHTS = np.array([1.5, 1.2, 1.0, 0.8, 0.5])


class ColorService:
    def analyze_color_grade(self, frame_bgr: np.ndarray) -> dict:
        """
        Analyze the color grade of a single frame using CIE L*a*b* color space.
        Returns L_mean, a_mean, b_mean, L_std, a_std for perceptual matching.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return self._default_profile()

        # Convert BGR → L*a*b* (OpenCV range: L 0-255, a 0-255, b 0-255)
        lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
        L_ch = lab[:, :, 0].astype(float)
        a_ch = lab[:, :, 1].astype(float)
        b_ch = lab[:, :, 2].astype(float)

        return {
            "L_mean": float(np.mean(L_ch)),
            "a_mean": float(np.mean(a_ch)),
            "b_mean": float(np.mean(b_ch)),
            "L_std":  float(np.std(L_ch)),
            "a_std":  float(np.std(a_ch)),
        }

    def average_color_profiles(self, profiles: list) -> dict:
        if not profiles:
            return self._default_profile()
        keys = ["L_mean", "a_mean", "b_mean", "L_std", "a_std"]
        return {k: float(np.mean([p.get(k, 0) for p in profiles])) for k in keys}

    def match_to_lut_library(self, color_profile: dict) -> str:
        """
        Return the LUT name closest to color_profile using weighted Lab distance.
        Accepts both legacy HSV profiles and new Lab profiles.
        """
        # Support legacy HSV profiles from saved EDLs
        if "shadow_hue" in color_profile and "L_mean" not in color_profile:
            color_profile = self._hsv_profile_to_lab(color_profile)

        vec = np.array([
            color_profile.get("L_mean", 118),
            color_profile.get("a_mean", 128),
            color_profile.get("b_mean", 128),
            color_profile.get("L_std",  42),
            color_profile.get("a_std",  10),
        ], dtype=float)

        best_lut  = "teal_orange"
        best_dist = float("inf")

        for lut_name, ref_tuple in _LUT_PROFILES_LAB.items():
            ref  = np.array(ref_tuple, dtype=float)
            dist = float(np.sqrt(np.sum(_LAB_WEIGHTS * (vec - ref) ** 2)))
            if dist < best_dist:
                best_dist = dist
                best_lut  = lut_name

        return best_lut

    def _default_profile(self) -> dict:
        return {"L_mean": 118.0, "a_mean": 128.0, "b_mean": 128.0, "L_std": 42.0, "a_std": 10.0}

    @staticmethod
    def _hsv_profile_to_lab(hsv: dict) -> dict:
        """Rough conversion from legacy HSV profile dict to Lab profile dict."""
        brightness = hsv.get("brightness", 120)
        saturation = hsv.get("saturation", 120)
        shadow_hue  = hsv.get("shadow_hue", 80)
        return {
            "L_mean": float(brightness * 0.65),
            "a_mean": float(128 + (shadow_hue - 90) * 0.3),
            "b_mean": float(128 + (saturation - 120) * 0.15),
            "L_std":  float(hsv.get("contrast", 50) * 0.7),
            "a_std":  10.0,
        }
