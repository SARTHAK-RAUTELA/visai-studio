from pydantic import BaseModel
from typing import Optional, Dict


class PacingDNA(BaseModel):
    avg_clip_duration: float = 2.5
    clip_duration_std: float = 0.8
    cuts_per_second: float = 0.4
    pacing_style: str = "medium_energetic"
    rhythm: str = "beat_synced"


class TransitionsDNA(BaseModel):
    types_detected: Dict[str, float] = {"hard_cut": 1.0}
    dominant_transition: str = "hard_cut"
    avg_transition_duration: float = 0.3
    transition_consistency: str = "consistent"


class ColorDNA(BaseModel):
    overall_temperature: str = "warm"
    saturation_level: str = "medium"
    contrast_level: str = "medium"
    brightness: str = "normal"
    shadow_color: str = "neutral"
    highlight_color: str = "warm"
    matched_lut: str = "teal_orange"
    lut_intensity_estimate: float = 0.8
    has_film_grain: bool = False
    has_vignette: bool = False
    vignette_strength: str = "none"
    color_description: str = ""


class AudioSyncDNA(BaseModel):
    is_beat_synced: bool = False
    sync_frequency: str = "every_4_beats"
    estimated_bpm: float = 120.0
    cuts_align_to_beats: bool = False


class MotionDNA(BaseModel):
    speed_ramps_detected: bool = False
    slow_motion_used: bool = False
    fast_motion_used: bool = False
    camera_movement_style: str = "mix_of_static_and_handheld"


class TextOverlaysDNA(BaseModel):
    present: bool = False
    frequency: str = "none"
    estimated_count: int = 0
    style: str = "minimal_lowercase"
    position: str = "lower_third"
    animation: str = "fade"
    font_weight: str = "light"


class EnergyDNA(BaseModel):
    level: str = "medium"
    mood: str = "balanced"
    emotional_tone: str = "neutral"
    platform_feel: str = "instagram_reels"


class StyleDNA(BaseModel):
    source_video: str = ""
    analyzed_at: str = ""
    pacing: PacingDNA = PacingDNA()
    transitions: TransitionsDNA = TransitionsDNA()
    color: ColorDNA = ColorDNA()
    audio_sync: AudioSyncDNA = AudioSyncDNA()
    motion: MotionDNA = MotionDNA()
    text_overlays: TextOverlaysDNA = TextOverlaysDNA()
    energy: EnergyDNA = EnergyDNA()
    aspect_ratio: str = "9:16"
    overall_style: str = ""
    claude_analysis: str = ""
