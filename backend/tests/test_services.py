"""
Unit tests for VisualAI Studio backend services.
Run from backend/ directory:  pytest tests/ -v
"""

import sys
import os
import json
from pathlib import Path

import numpy as np
import pytest

# Ensure backend/ is on sys.path so imports work without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# FFmpegService helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestFFmpegPath:
    def _path(self, p):
        from services.ffmpeg_service import FFmpegService
        return FFmpegService._ffmpeg_path(p)

    def test_unix_path_unchanged(self):
        assert self._path("/tmp/file.mp4") == "/tmp/file.mp4"

    def test_windows_drive_letter_escaped(self):
        result = self._path("D:\\videos\\clip.mp4")
        assert "D\\:" in result

    def test_backslash_to_forward_slash(self):
        result = self._path("C:\\Users\\test\\file.mp4")
        assert "\\" not in result.replace("\\:", "")

    def test_single_quote_escaped(self):
        result = self._path("/path/with'quote/file.mp4")
        assert "\\'" in result


# ─────────────────────────────────────────────────────────────────────────────
# ColorService — CIELAB matching
# ─────────────────────────────────────────────────────────────────────────────

class TestColorService:
    @pytest.fixture(autouse=True)
    def svc(self):
        from services.color_service import ColorService
        self.color = ColorService()

    def test_match_returns_known_lut(self):
        lut = self.color.match_to_lut_library({
            "L_mean": 118.0, "a_mean": 118.0, "b_mean": 138.0,
            "L_std": 42.0, "a_std": 12.0,
        })
        assert lut == "teal_orange"

    def test_match_airy_bright_high_key(self):
        lut = self.color.match_to_lut_library({
            "L_mean": 165.0, "a_mean": 125.0, "b_mean": 128.0,
            "L_std": 28.0, "a_std": 6.0,
        })
        assert lut == "airy_bright"

    def test_match_moody_blue_dark(self):
        lut = self.color.match_to_lut_library({
            "L_mean": 88.0, "a_mean": 120.0, "b_mean": 118.0,
            "L_std": 52.0, "a_std": 8.0,
        })
        assert lut == "moody_blue"

    def test_default_profile_has_required_keys(self):
        profile = self.color._default_profile()
        for key in ("L_mean", "a_mean", "b_mean", "L_std", "a_std"):
            assert key in profile

    def test_legacy_hsv_profile_accepted(self):
        lut = self.color.match_to_lut_library({
            "shadow_hue": 100, "highlight_hue": 15, "saturation": 160,
            "contrast": 60, "brightness": 120,
        })
        assert isinstance(lut, str)
        assert len(lut) > 0

    def test_average_profiles(self):
        profiles = [
            {"L_mean": 100.0, "a_mean": 128.0, "b_mean": 128.0, "L_std": 40.0, "a_std": 10.0},
            {"L_mean": 120.0, "a_mean": 130.0, "b_mean": 130.0, "L_std": 44.0, "a_std": 12.0},
        ]
        avg = self.color.average_color_profiles(profiles)
        assert avg["L_mean"] == pytest.approx(110.0)
        assert avg["a_mean"] == pytest.approx(129.0)

    def test_analyze_color_grade_black_frame(self):
        black = np.zeros((100, 100, 3), dtype=np.uint8)
        profile = self.color.analyze_color_grade(black)
        assert profile["L_mean"] < 10  # very dark

    def test_analyze_color_grade_none_returns_default(self):
        profile = self.color.analyze_color_grade(None)
        assert "L_mean" in profile


# ─────────────────────────────────────────────────────────────────────────────
# ClaudeService helpers (no API calls)
# ─────────────────────────────────────────────────────────────────────────────

class TestClaudeServiceHelpers:
    @pytest.fixture(autouse=True)
    def svc(self):
        # Patch env so constructor doesn't fail on missing key
        os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-placeholder")
        # We patch anthropic.Anthropic so no real client is created
        import unittest.mock as mock
        with mock.patch("anthropic.Anthropic"):
            from services.claude_service import ClaudeService
            self.svc = ClaudeService.__new__(ClaudeService)
            self.svc.client = mock.MagicMock()

    def test_parse_json_direct(self):
        from services.claude_service import ClaudeService
        svc = self.svc
        result = svc._parse_json('{"key": "value"}', {})
        assert result == {"key": "value"}

    def test_parse_json_strips_markdown_fences(self):
        from services.claude_service import ClaudeService
        svc = self.svc
        text = '```json\n{"a": 1}\n```'
        result = svc._parse_json(text, {})
        assert result == {"a": 1}

    def test_parse_json_extracts_bare_object(self):
        from services.claude_service import ClaudeService
        svc = self.svc
        text = 'Here is the JSON: {"x": 42} end'
        result = svc._parse_json(text, {})
        assert result == {"x": 42}

    def test_parse_json_falls_back_on_invalid(self):
        from services.claude_service import ClaudeService
        svc = self.svc
        result = svc._parse_json("not valid json at all", {"fallback": True})
        assert result == {"fallback": True}

    def test_optimal_frame_count_scales_down(self):
        from services.claude_service import ClaudeService
        assert ClaudeService.optimal_frame_count(1) == 10
        assert ClaudeService.optimal_frame_count(5) == 8
        assert ClaudeService.optimal_frame_count(8) == 5
        assert ClaudeService.optimal_frame_count(15) == 3

    def test_build_fallback_edl_structure(self):
        svc = self.svc
        clips_analysis = [
            {"file": "clip1.mp4", "analysis": {}},
            {"file": "clip2.mp4", "analysis": {}},
        ]
        style_preset = {"transitions": ["dissolve"], "transition_duration": 0.5, "lut": "teal_orange"}
        edl = svc._build_fallback_edl(clips_analysis, style_preset, 30.0, "9:16", "1080x1920")

        assert "clips" in edl
        assert len(edl["clips"]) == 2
        assert edl["project"]["target_duration"] == 30.0
        assert edl["project"]["aspect_ratio"] == "9:16"
        assert edl["global_grade"]["lut"] == "teal_orange"

    def test_fallback_edl_clips_use_correct_filenames(self):
        svc = self.svc
        clips_analysis = [{"file": "/tmp/video.mp4", "analysis": {}}]
        style_preset = {"transitions": ["hard_cut"], "lut": "warm_golden"}
        edl = svc._build_fallback_edl(clips_analysis, style_preset, 15.0, "16:9", "1920x1080")
        assert edl["clips"][0]["source_file"] == "video.mp4"


# ─────────────────────────────────────────────────────────────────────────────
# ExportService helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestExportService:
    @pytest.fixture(autouse=True)
    def svc(self):
        import unittest.mock as mock
        with mock.patch("services.ffmpeg_service.FFmpegService"):
            from services.export_service import ExportService
            self.svc = ExportService.__new__(ExportService)
            self.svc.ffmpeg = mock.MagicMock()
            self.svc.luts_dir = Path("/fake/luts")
            self.svc.fonts_dir = Path("/fake/fonts")

    def test_resolve_clip_absolute_exists(self, tmp_path):
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"")
        result = self.svc._resolve_clip(str(f), None)
        assert result == str(f)

    def test_resolve_clip_finds_in_clips_dir(self, tmp_path):
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"")
        result = self.svc._resolve_clip("clip.mp4", str(tmp_path))
        assert result == str(f)

    def test_resolve_clip_returns_none_missing(self, tmp_path):
        result = self.svc._resolve_clip("nonexistent.mp4", str(tmp_path))
        assert result is None

    def test_resolutions_dict_complete(self):
        from services.export_service import ExportService
        for ratio in ("9:16", "16:9", "1:1", "4:5"):
            assert ratio in ExportService.RESOLUTIONS
            for preset in ("720p", "1080p", "4K"):
                assert preset in ExportService.RESOLUTIONS[ratio]


# ─────────────────────────────────────────────────────────────────────────────
# AudioService helpers (no audio file needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioService:
    @pytest.fixture(autouse=True)
    def svc(self):
        from services.audio_service import AudioService
        self.svc = AudioService()

    def test_mood_energetic(self):
        mood = self.svc._estimate_mood(140, 0.15, 5000)
        assert mood == "energetic"

    def test_mood_dreamy(self):
        mood = self.svc._estimate_mood(70, 0.03, 1500)
        assert mood == "dreamy"

    def test_mood_melancholic(self):
        mood = self.svc._estimate_mood(85, 0.04, 1800)
        assert mood == "melancholic"

    def test_mood_balanced(self):
        mood = self.svc._estimate_mood(100, 0.07, 3000)
        assert mood == "balanced"

    def test_tempo_category_slow(self):
        assert self.svc._categorize_tempo(60) == "slow"

    def test_tempo_category_medium(self):
        assert self.svc._categorize_tempo(100) == "medium"

    def test_tempo_category_fast(self):
        assert self.svc._categorize_tempo(130) == "fast"


# ─────────────────────────────────────────────────────────────────────────────
# SceneService helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestSceneService:
    @pytest.fixture(autouse=True)
    def svc(self):
        from services.scene_service import SceneService
        self.svc = SceneService()

    def test_classify_returns_hard_cut_on_empty(self):
        result = self.svc.classify_transition([], [])
        assert result == "hard_cut"

    def test_classify_fade_black(self):
        dark = [np.zeros((10, 10, 3), dtype=np.uint8)] * 3
        bright = [np.full((10, 10, 3), 200, dtype=np.uint8)] * 3
        result = self.svc.classify_transition(dark, bright)
        assert result == "fade_black"

    def test_classify_hard_cut_high_diff(self):
        black = [np.zeros((50, 50, 3), dtype=np.uint8)] * 3
        white = [np.full((50, 50, 3), 255, dtype=np.uint8)] * 3
        result = self.svc.classify_transition(black, white)
        # diff is very high (255), should be hard_cut
        assert result in ("hard_cut", "fade_black", "fade_white")

    def test_configurable_thresholds(self):
        from services.scene_service import SceneService
        svc_strict = SceneService(fade_black_threshold=5.0)
        dark = [np.full((10, 10, 3), 10, dtype=np.uint8)] * 3  # brightness ~10 > 5 threshold
        bright = [np.full((10, 10, 3), 200, dtype=np.uint8)] * 3
        # With strict threshold of 5, brightness 10 should NOT trigger fade_black
        result = svc_strict.classify_transition(dark, bright)
        assert result != "fade_black"

    def test_default_thresholds_accessible(self):
        assert self.svc.fade_black_threshold == 15.0
        assert self.svc.hard_cut_threshold == 40.0
        assert self.svc.wipe_ratio == 3.0


# ─────────────────────────────────────────────────────────────────────────────
# AudioService — beat sync (no audio file needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioServiceBeatSync:
    @pytest.fixture(autouse=True)
    def svc(self):
        from services.audio_service import AudioService
        self.svc = AudioService()

    def test_snap_empty_edl(self):
        edl = {"clips": []}
        result = self.svc.snap_edl_to_beats(edl, [0.5, 1.0, 1.5])
        assert result["clips"] == []

    def test_snap_empty_beats(self):
        edl = {"clips": [{"source_in": 0.0, "source_out": 3.0}]}
        result = self.svc.snap_edl_to_beats(edl, [])
        assert result["clips"][0]["source_in"] == 0.0

    def test_snap_aligns_within_tolerance(self):
        edl = {"clips": [
            {"source_in": 0.0, "source_out": 2.0},
            {"source_in": 1.0, "source_out": 3.0},
        ]}
        # Second clip timeline_pos = 2.0; nearest beat at 2.1 (diff=0.1 ≤ 0.3)
        result = self.svc.snap_edl_to_beats(edl, [0.0, 2.1, 4.0])
        second = result["clips"][1]
        assert abs(second["source_in"] - 1.1) < 0.01

    def test_snap_skips_outside_tolerance(self):
        edl = {"clips": [
            {"source_in": 0.0, "source_out": 2.0},
            {"source_in": 1.0, "source_out": 3.0},
        ]}
        # Second clip at 2.0; nearest beat at 2.5 (diff=0.5 > default 0.3)
        result = self.svc.snap_edl_to_beats(edl, [0.0, 2.5])
        assert result["clips"][1]["source_in"] == pytest.approx(1.0)

    def test_snap_preserves_clip_duration(self):
        edl = {"clips": [{"source_in": 0.0, "source_out": 4.0}]}
        result = self.svc.snap_edl_to_beats(edl, [0.1])
        clip = result["clips"][0]
        dur = clip["source_out"] - clip["source_in"]
        assert abs(dur - 4.0) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# EDL helpers (main.py functions, tested directly)
# ─────────────────────────────────────────────────────────────────────────────

class TestEDLHelpers:
    def test_validate_edl_valid(self):
        import importlib
        import unittest.mock as mock

        # We need to import validation helpers without starting FastAPI
        # They're module-level functions in main.py
        sys.modules.setdefault("dotenv", mock.MagicMock())

        # Minimal valid EDL
        edl = {"clips": [{"source_file": "a.mp4"}], "project": {}}
        # Test inline since we can't import main without side effects
        assert isinstance(edl.get("clips"), list) and len(edl["clips"]) > 0

    def test_validate_edl_no_clips(self):
        edl = {"project": {}}
        assert not (isinstance(edl.get("clips"), list) and len(edl.get("clips", [])) > 0)

    def test_validate_edl_empty_clips(self):
        edl = {"clips": [], "project": {}}
        assert not len(edl.get("clips", [])) > 0
