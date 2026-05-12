from pydantic import BaseModel
from typing import Optional


class JobStatus(BaseModel):
    job_id: str
    status: str = "queued"   # queued | processing | complete | failed
    progress: int = 0
    message: str = ""
    output_file: Optional[str] = None
    error: Optional[str] = None
