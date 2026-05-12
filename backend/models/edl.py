from pydantic import BaseModel
from typing import Optional, List


class TransitionConfig(BaseModel):
    type: str = "hard_cut"
    duration: float = 0.0


class PerClipGrade(BaseModel):
    lut: str
    lut_intensity: float = 1.0


class ClipEntry(BaseModel):
    clip_id: str
    source_file: str
    timeline_start: float
    timeline_end: float
    source_in: float = 0.0
    source_out: float
    speed_factor: float = 1.0
    transition_in: TransitionConfig = TransitionConfig()
    transition_out: TransitionConfig = TransitionConfig()
    per_clip_grade: Optional[PerClipGrade] = None
    notes: str = ""


class GlobalGrade(BaseModel):
    lut: str = "teal_orange"
    lut_intensity: float = 0.85
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    temperature_shift: str = "neutral"
    vignette: bool = False
    vignette_strength: float = 0.3
    film_grain: bool = False
    grain_strength: int = 0


class AudioConfig(BaseModel):
    music_file: str
    music_volume: float = 0.9
    original_audio_volume: float = 0.0
    fade_in_duration: float = 0.5
    fade_out_duration: float = 2.0
    fade_out_start: float = 28.0


class TextOverlay(BaseModel):
    text: str
    start_time: float
    duration: float
    position: str = "bottom"
    animation: str = "fade"
    font_style: str = "minimal_sans"
    size: str = "medium"
    color: str = "white"
    opacity: float = 0.9


class SoundFX(BaseModel):
    file: str
    timeline_time: float
    volume: float = 0.3


class ProjectConfig(BaseModel):
    title: str = "my_edit"
    target_duration: float
    aspect_ratio: str = "9:16"
    fps: int = 30
    resolution: str = "1080x1920"


class EDL(BaseModel):
    project: ProjectConfig
    global_grade: GlobalGrade = GlobalGrade()
    audio: AudioConfig
    clips: List[ClipEntry]
    text_overlays: List[TextOverlay] = []
    sound_fx: List[SoundFX] = []
    cut_timestamps: List[float] = []
    reasoning: str = ""
