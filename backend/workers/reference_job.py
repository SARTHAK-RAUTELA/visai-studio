from workers.celery_app import celery_app


@celery_app.task(bind=True, name="workers.reference_job.analyze_reference")
def analyze_reference(self, job_id: str, video_path: str):
    """
    Celery task: reference video analysis pipeline (Phase 2).
    Produces a Style DNA JSON.
    """
    self.update_state(state="PROGRESS", meta={"progress": 0, "message": "Starting reference analysis"})

    # Phase 2: will use ReferenceService
    raise NotImplementedError("Reference analysis is implemented in Phase 2")
