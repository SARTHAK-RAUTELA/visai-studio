import json
import os
import uuid
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="VisualAI Studio API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "./temp"))
OUTPUT_PATH = Path(os.getenv("OUTPUT_PATH", "./output"))
STYLES_PATH = Path(__file__).parent / "styles"

STORAGE_PATH.mkdir(exist_ok=True)
OUTPUT_PATH.mkdir(exist_ok=True)

# In-memory job store — replaced by Redis in Phase 3
jobs: dict = {}


# ── Request / response schemas ──────────────────────────────────────────────

class GenerateRequest(BaseModel):
    clip_ids: List[str]
    audio_id: str
    style: str = "cinematic_travel"
    style_dna_id: Optional[str] = None
    target_duration: float = 30.0
    aspect_ratio: str = "9:16"
    auto_captions: bool = False
    sound_fx: bool = False
    lut_override: Optional[str] = None
    lut_intensity: float = 0.85


class ReferenceRequest(BaseModel):
    reference_type: str = "file"  # file | url
    url: Optional[str] = None
    file_id: Optional[str] = None


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "app": "VisualAI Studio", "version": "1.0.0"}


# ── Upload ────────────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload one or more video clips and/or an audio file."""
    uploaded = []
    for file in files:
        file_id = str(uuid.uuid4())
        ext = Path(file.filename).suffix.lower()
        save_path = STORAGE_PATH / f"{file_id}{ext}"
        content = await file.read()
        save_path.write_bytes(content)
        uploaded.append({
            "file_id": file_id,
            "original_name": file.filename,
            "size_mb": round(save_path.stat().st_size / (1024 * 1024), 2),
        })
    return {"uploaded": uploaded}


@app.post("/api/upload/reference")
async def upload_reference(file: Optional[UploadFile] = File(None), url: Optional[str] = None):
    """Upload a reference video file, or provide a URL (Phase 2)."""
    if url:
        return {"error": "URL download (yt-dlp) is implemented in Phase 2"}
    if not file:
        raise HTTPException(400, "Either file upload or url parameter required")

    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    save_path = STORAGE_PATH / f"ref_{file_id}{ext}"
    save_path.write_bytes(await file.read())
    return {"file_id": file_id, "original_name": file.filename}


# ── Styles & LUTs ─────────────────────────────────────────────────────────────

@app.get("/api/styles")
def list_styles():
    styles = []
    for f in sorted(STYLES_PATH.glob("*.json")):
        with open(f) as fp:
            styles.append(json.load(fp))
    return {"styles": styles}


@app.get("/api/styles/{name}")
def get_style(name: str):
    path = STYLES_PATH / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, f"Style '{name}' not found")
    with open(path) as f:
        return json.load(f)


@app.get("/api/luts")
def list_luts():
    luts_dir = Path(__file__).parent / "assets" / "luts"
    return {"luts": [f.stem for f in sorted(luts_dir.glob("*.cube"))]}


# ── Generate ──────────────────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate_edit(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Start an edit generation job. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "progress": 0, "message": "", "output_file": None, "error": None}

    clip_paths = _resolve_ids(request.clip_ids)
    audio_path = _resolve_id(request.audio_id)

    background_tasks.add_task(
        _run_edit_job,
        job_id, clip_paths, audio_path,
        request.style, request.target_duration, request.aspect_ratio,
    )
    return {"job_id": job_id, "status": "queued"}


async def _run_edit_job(
    job_id: str,
    clip_paths: list,
    audio_path: str,
    style: str,
    target_duration: float,
    aspect_ratio: str,
):
    import traceback
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = "Loading style preset"

        with open(STYLES_PATH / f"{style}.json") as f:
            style_preset = json.load(f)

        jobs[job_id]["progress"] = 20
        jobs[job_id]["message"] = "Analyzing audio"

        from services.audio_service import AudioService
        audio_analysis = AudioService().analyze_audio(audio_path)

        jobs[job_id]["progress"] = 35
        jobs[job_id]["message"] = "Analyzing clips with Claude Vision"

        from services.claude_service import ClaudeService
        claude = ClaudeService()
        clips_analysis = []
        for cp in clip_paths:
            frames = claude.extract_keyframes(cp, num_frames=8)
            analysis = claude.analyze_clip(frames, cp)
            analysis["source_file"] = Path(cp).name
            clips_analysis.append({"file": cp, "analysis": analysis})

        jobs[job_id]["progress"] = 60
        jobs[job_id]["message"] = "Generating edit plan"

        edl = claude.generate_edl(
            clips_analysis=clips_analysis,
            audio_analysis=audio_analysis,
            style_preset=style_preset,
            target_duration=target_duration,
            aspect_ratio=aspect_ratio,
        )

        jobs[job_id]["progress"] = 70
        jobs[job_id]["message"] = "Rendering video"

        output_path = str(OUTPUT_PATH / f"{job_id}.mp4")
        clips_dir = str(STORAGE_PATH)

        from services.export_service import ExportService
        ExportService().render_from_edl(edl, audio_path, output_path, clips_dir)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = "Done"
        jobs[job_id]["output_file"] = output_path

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["message"] = "Failed"
        print(f"Job {job_id} failed:\n{traceback.format_exc()}")


# ── Reference analysis ────────────────────────────────────────────────────────

@app.post("/api/analyze/reference")
async def analyze_reference(request: ReferenceRequest, background_tasks: BackgroundTasks):
    """Start reference video analysis job (Phase 2)."""
    return {"error": "Reference analysis is implemented in Phase 2"}


@app.get("/api/analyze/reference/{ref_id}")
def get_reference_result(ref_id: str):
    return {"error": "Reference analysis is implemented in Phase 2"}


# ── Job status ────────────────────────────────────────────────────────────────

@app.get("/api/job/{job_id}/status")
def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/api/job/{job_id}/result")
def get_job_result(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    job = jobs[job_id]
    if job["status"] != "complete":
        raise HTTPException(400, f"Job not complete (status: {job['status']})")
    out = job.get("output_file")
    if not out or not os.path.exists(out):
        raise HTTPException(404, "Output file not found")
    return FileResponse(out, media_type="video/mp4", filename=f"visai_{job_id[:8]}.mp4")


@app.delete("/api/job/{job_id}")
def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    out = jobs[job_id].get("output_file")
    if out and os.path.exists(out):
        os.remove(out)
    del jobs[job_id]
    return {"deleted": job_id}


# ── Fine-tune ─────────────────────────────────────────────────────────────────

@app.post("/api/finetune")
def finetune(job_id: str, adjustments: dict):
    """Apply manual adjustments to an existing EDL (Phase 3)."""
    return {"error": "Fine-tune is implemented in Phase 3"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_id(file_id: str) -> Optional[str]:
    matches = list(STORAGE_PATH.glob(f"{file_id}*"))
    return str(matches[0]) if matches else None


def _resolve_ids(file_ids: List[str]) -> List[str]:
    return [p for fid in file_ids if (p := _resolve_id(fid))]
