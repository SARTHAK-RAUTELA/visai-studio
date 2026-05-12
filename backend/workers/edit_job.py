import json
import os
from pathlib import Path

from workers.celery_app import celery_app


@celery_app.task(bind=True, name="workers.edit_job.run_edit")
def run_edit(self, job_id: str, clip_paths: list, audio_path: str,
             style: str, target_duration: float, aspect_ratio: str):
    """
    Celery task: full edit pipeline.
    Runs in background worker; updates task state for WebSocket progress.
    """
    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Loading style preset"})

        styles_dir = Path(__file__).parent.parent / "styles"
        with open(styles_dir / f"{style}.json") as f:
            style_preset = json.load(f)

        # Audio analysis
        self.update_state(state="PROGRESS", meta={"progress": 15, "message": "Analyzing audio"})
        from services.audio_service import AudioService
        audio_analysis = AudioService().analyze_audio(audio_path)

        # Clip analysis
        self.update_state(state="PROGRESS", meta={"progress": 30, "message": "Analyzing clips with Claude"})
        from services.claude_service import ClaudeService
        claude = ClaudeService()

        clips_analysis = []
        for clip_path in clip_paths:
            frames = claude.extract_keyframes(clip_path, num_frames=8)
            analysis = claude.analyze_clip(frames, clip_path)
            analysis["source_file"] = Path(clip_path).name
            clips_analysis.append({"file": clip_path, "analysis": analysis})

        # EDL generation
        self.update_state(state="PROGRESS", meta={"progress": 55, "message": "Generating edit plan"})
        edl = claude.generate_edl(
            clips_analysis=clips_analysis,
            audio_analysis=audio_analysis,
            style_preset=style_preset,
            target_duration=target_duration,
            aspect_ratio=aspect_ratio,
        )

        # Render
        self.update_state(state="PROGRESS", meta={"progress": 65, "message": "Rendering video"})
        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        output_path = str(output_dir / f"{job_id}.mp4")

        from services.export_service import ExportService
        clips_dir = str(Path(clip_paths[0]).parent) if clip_paths else "."
        ExportService().render_from_edl(edl, audio_path, output_path, clips_dir)

        self.update_state(state="PROGRESS", meta={"progress": 100, "message": "Done"})
        return {"status": "complete", "output_file": output_path, "edl": edl}

    except Exception as e:
        import traceback
        self.update_state(
            state="FAILURE",
            meta={"progress": 0, "message": str(e), "traceback": traceback.format_exc()}
        )
        raise
