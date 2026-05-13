import json
from pathlib import Path

from workers.celery_app import celery_app


@celery_app.task(bind=True, name="workers.reference_job.analyze_reference")
def analyze_reference(self, ref_id: str, video_path: str):
    """
    Celery task: full reference video analysis → Style DNA JSON.
    """
    try:
        self.update_state(state="PROGRESS", meta={"progress": 10, "message": "Detecting scenes"})

        from services.reference_service import ReferenceService
        from services.claude_service import ClaudeService

        svc = ReferenceService()
        try:
            claude = ClaudeService()
        except Exception:
            claude = None

        self.update_state(state="PROGRESS", meta={"progress": 60, "message": "Generating Style DNA"})
        style_dna = svc.analyze(video_path, claude_service=claude)

        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        dna_path = output_dir / f"style_dna_{ref_id}.json"
        dna_path.write_text(json.dumps(style_dna, indent=2), encoding="utf-8")

        self.update_state(state="PROGRESS", meta={"progress": 100, "message": "Style DNA ready"})
        return {"status": "complete", "style_dna": style_dna, "dna_file": str(dna_path)}

    except Exception as e:
        import traceback
        self.update_state(
            state="FAILURE",
            meta={"progress": 0, "message": str(e), "traceback": traceback.format_exc()},
        )
        raise
