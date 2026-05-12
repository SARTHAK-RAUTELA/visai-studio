"""
Color analysis service — Phase 2.
Analyzes color grade of reference video frames and matches to LUT library.
"""


class ColorService:
    def analyze_color_grade(self, frame_bgr) -> dict:
        """
        Analyze color grade of a single frame.
        Returns shadow_hue, highlight_hue, saturation, contrast, brightness.

        Phase 2 implementation uses OpenCV + NumPy (see projectDetails.md Section 3.3).
        """
        raise NotImplementedError("Color analysis is implemented in Phase 2")

    def match_to_lut_library(self, color_profile: dict) -> str:
        """
        Match a color profile dict to the closest LUT name.
        Uses Euclidean distance on profile vector.

        Phase 2 implementation.
        """
        raise NotImplementedError("LUT matching is implemented in Phase 2")
