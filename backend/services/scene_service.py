"""
Scene detection service — Phase 2.
Uses PySceneDetect to find cut points in reference videos.
"""


class SceneService:
    def detect_scenes(self, video_path: str) -> list:
        """
        Detect scene cuts in a video.
        Returns list of (start_sec, end_sec) tuples.

        Phase 2 implementation will use:
            from scenedetect import detect, ContentDetector, ThresholdDetector, AdaptiveDetector
        """
        raise NotImplementedError("Scene detection is implemented in Phase 2")
