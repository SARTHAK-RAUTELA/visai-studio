import numpy as np


class AudioService:
    def analyze_audio(self, audio_path: str) -> dict:
        """Full audio analysis: BPM, beats, energy, mood."""
        import librosa
        from scipy.signal import find_peaks

        y, sr = librosa.load(audio_path, sr=22050)

        # Beat tracking
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="time")
        beat_times = [float(b) for b in beat_frames]

        # Onset detection (energy peaks, not just metronome)
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="time")
        onset_times = [float(o) for o in onset_frames]

        # Per-second energy curve
        hop_length = sr
        energy = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        energy_curve = [float(e) for e in energy]

        # Key musical moments (energy peaks above 120% of mean)
        mean_e = float(np.mean(energy))
        peaks, _ = find_peaks(energy, height=mean_e * 1.2, distance=2)
        peak_moments = [float(p) for p in peaks]

        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        bpm = float(tempo)
        avg_energy = float(np.mean(energy))
        avg_brightness = float(np.mean(spectral_centroid))

        return {
            "bpm": bpm,
            "beat_times": beat_times,
            "onset_times": onset_times,
            "energy_curve": energy_curve,
            "peak_moments": peak_moments,
            "total_duration": float(len(y) / sr),
            "mood": self._estimate_mood(bpm, avg_energy, avg_brightness),
            "tempo_category": self._categorize_tempo(bpm),
        }

    def _estimate_mood(self, bpm: float, energy: float, brightness: float) -> str:
        if bpm > 130 and energy > 0.1:
            return "energetic"
        if bpm < 80 and energy < 0.05:
            return "dreamy"
        if bpm < 90 and brightness < 2000:
            return "melancholic"
        if bpm > 120 and brightness > 4000:
            return "intense"
        return "balanced"

    def _categorize_tempo(self, bpm: float) -> str:
        if bpm < 80:
            return "slow"
        if bpm < 120:
            return "medium"
        return "fast"
