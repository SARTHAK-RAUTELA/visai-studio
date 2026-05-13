import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="VisualAI Studio API", version="4.0.0")

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from middleware.analytics import AnalyticsMiddleware
    app.add_middleware(AnalyticsMiddleware)
except Exception:
    pass

# ── Paths ─────────────────────────────────────────────────────────────────────

STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "./temp"))
OUTPUT_PATH  = Path(os.getenv("OUTPUT_PATH", "./output"))
STYLES_PATH  = Path(__file__).parent / "styles"
DNA_LIB_PATH = Path(os.getenv("OUTPUT_PATH", "./output")) / "dna_library"
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

STORAGE_PATH.mkdir(exist_ok=True)
OUTPUT_PATH.mkdir(exist_ok=True)
DNA_LIB_PATH.mkdir(exist_ok=True)

# ── In-memory job stores ──────────────────────────────────────────────────────

jobs: dict           = {}
reference_jobs: dict = {}
batch_jobs: dict     = {}


# ── Request schemas ───────────────────────────────────────────────────────────

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
    resolution_preset: str = "1080p"       # 720p | 1080p | 4K
    background_removal: bool = False
    speed_ramp: Optional[str] = None       # ease_in | ease_out | slow_mo | null


class ReferenceRequest(BaseModel):
    reference_type: str = "file"
    url: Optional[str] = None
    file_id: Optional[str] = None


class FineTuneRequest(BaseModel):
    lut_override: Optional[str] = None
    lut_intensity: float = 0.85
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    clip_transitions: Optional[dict] = None   # {"0": "dissolve", "1": "hard_cut"}
    remove_text_overlays: bool = False
    new_text_overlays: Optional[list] = None


class DnaSaveRequest(BaseModel):
    name: str
    style_dna: dict


class BatchJobSpec(BaseModel):
    clip_ids: List[str]
    audio_id: str
    style: str = "cinematic_travel"
    target_duration: float = 30.0
    aspect_ratio: str = "9:16"


class BatchRequest(BaseModel):
    jobs: List[BatchJobSpec]


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "app": "VisualAI Studio", "version": "4.0.0"}


# ── Upload ────────────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    save_path = STORAGE_PATH / f"{file_id}{ext}"
    content = await file.read()
    save_path.write_bytes(content)
    return {
        "file_id": file_id,
        "original_name": file.filename,
        "size_mb": round(len(content) / (1024 * 1024), 2),
    }


@app.post("/api/upload/reference")
async def upload_reference(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
):
    if url:
        ref_id = str(uuid.uuid4())
        reference_jobs[ref_id] = {
            "status": "downloading", "progress": 0, "message": "Downloading from URL",
            "file_path": None, "style_dna": None, "error": None,
        }
        try:
            from services.reference_service import ReferenceService
            file_path = ReferenceService().download_from_url(url, str(STORAGE_PATH))
            reference_jobs[ref_id].update(status="downloaded", progress=100,
                                          message="Download complete", file_path=file_path)
            return {"file_id": ref_id, "source": "url", "url": url}
        except Exception as e:
            reference_jobs[ref_id].update(status="failed", error=str(e))
            raise HTTPException(500, f"URL download failed: {e}")

    if not file:
        raise HTTPException(400, "Provide either a file or url parameter")

    ref_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    save_path = STORAGE_PATH / f"ref_{ref_id}{ext}"
    save_path.write_bytes(await file.read())
    reference_jobs[ref_id] = {
        "status": "uploaded", "progress": 0, "message": "File uploaded",
        "file_path": str(save_path), "style_dna": None, "error": None,
    }
    return {"file_id": ref_id, "original_name": file.filename}


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


# ── Reference analysis ────────────────────────────────────────────────────────

@app.post("/api/analyze/reference")
async def analyze_reference(request: ReferenceRequest, background_tasks: BackgroundTasks):
    ref_id = request.file_id or str(uuid.uuid4())

    if request.reference_type == "url" and request.url:
        existing = reference_jobs.get(ref_id, {})
        file_path = existing.get("file_path")
        if not file_path:
            try:
                from services.reference_service import ReferenceService
                file_path = ReferenceService().download_from_url(request.url, str(STORAGE_PATH))
            except Exception as e:
                raise HTTPException(500, f"URL download failed: {e}")
    elif request.file_id:
        existing = reference_jobs.get(request.file_id, {})
        file_path = existing.get("file_path") or _find_ref_file(request.file_id)
        if not file_path:
            raise HTTPException(404, f"Reference file '{request.file_id}' not found")
    else:
        raise HTTPException(400, "Provide file_id or url with reference_type='url'")

    reference_jobs[ref_id] = {
        "status": "queued", "progress": 0, "message": "Queued",
        "file_path": file_path, "style_dna": None, "error": None,
    }
    background_tasks.add_task(_run_reference_job, ref_id, file_path)
    return {"ref_id": ref_id, "status": "queued"}


@app.get("/api/analyze/reference/{ref_id}")
def get_reference_result(ref_id: str):
    if ref_id not in reference_jobs:
        raise HTTPException(404, f"Reference job '{ref_id}' not found")
    job = reference_jobs[ref_id]
    return {
        "ref_id": ref_id, "status": job["status"],
        "progress": job["progress"], "message": job["message"],
        "style_dna": job.get("style_dna"), "error": job.get("error"),
    }


async def _run_reference_job(ref_id: str, file_path: str):
    import traceback
    try:
        reference_jobs[ref_id].update(status="processing", progress=10, message="Detecting scenes")
        from services.reference_service import ReferenceService
        from services.claude_service import ClaudeService
        svc = ReferenceService()
        try:
            claude = ClaudeService()
        except Exception:
            claude = None
        reference_jobs[ref_id].update(progress=60, message="Generating Style DNA")
        style_dna = svc.analyze(file_path, claude_service=claude)
        dna_path = OUTPUT_PATH / f"style_dna_{ref_id}.json"
        dna_path.write_text(json.dumps(style_dna, indent=2), encoding="utf-8")
        reference_jobs[ref_id].update(
            status="complete", progress=100, message="Style DNA ready",
            style_dna=style_dna, dna_file=str(dna_path),
        )
        try:
            from middleware.analytics import analytics
            analytics.record_job("complete")
        except Exception:
            pass
    except Exception as e:
        reference_jobs[ref_id].update(status="failed", error=str(e), message="Analysis failed")
        print(f"Reference job {ref_id} failed:\n{traceback.format_exc()}")
        try:
            from middleware.analytics import analytics
            analytics.record_job("failed")
        except Exception:
            pass


# ── Generate ──────────────────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate_edit(request: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "queued", "progress": 0, "message": "",
        "output_file": None, "error": None,
    }

    clip_paths = _resolve_ids(request.clip_ids)
    audio_path = _resolve_id(request.audio_id)

    style_dna = None
    if request.style_dna_id:
        ref_job = reference_jobs.get(request.style_dna_id, {})
        style_dna = ref_job.get("style_dna")
        if not style_dna:
            dna_path = OUTPUT_PATH / f"style_dna_{request.style_dna_id}.json"
            if dna_path.exists():
                style_dna = json.loads(dna_path.read_text(encoding="utf-8"))

    try:
        from middleware.analytics import analytics
        analytics.record_job("started")
    except Exception:
        pass

    background_tasks.add_task(
        _run_edit_job,
        job_id, clip_paths, audio_path,
        request.style, request.target_duration, request.aspect_ratio,
        style_dna, request.auto_captions, request.sound_fx,
        request.resolution_preset, request.background_removal, request.speed_ramp,
    )
    return {"job_id": job_id, "status": "queued"}


async def _run_edit_job(
    job_id: str,
    clip_paths: list,
    audio_path: str,
    style: str,
    target_duration: float,
    aspect_ratio: str,
    style_dna: dict | None = None,
    auto_captions: bool = False,
    sound_fx: bool = False,
    resolution_preset: str = "1080p",
    background_removal: bool = False,
    speed_ramp: str | None = None,
):
    import traceback
    try:
        jobs[job_id].update(status="processing", progress=10, message="Loading style preset")

        with open(STYLES_PATH / f"{style}.json") as f:
            style_preset = json.load(f)

        # Expand long clips into their best sub-clips before analysis
        jobs[job_id].update(progress=15, message="Extracting best moments from long clips")
        from services.clip_extractor import ClipExtractorService
        extractor = ClipExtractorService()
        expanded = []
        for cp in clip_paths:
            expanded.extend(extractor.maybe_extract(cp, str(STORAGE_PATH), max_clips=4))
        clip_paths = expanded or clip_paths

        jobs[job_id].update(progress=20, message="Analyzing audio")
        from services.audio_service import AudioService
        audio_analysis = AudioService().analyze_audio(audio_path)

        jobs[job_id].update(progress=35, message="Analyzing clips with Claude Vision")
        from services.claude_service import ClaudeService
        claude = ClaudeService()
        num_frames = ClaudeService.optimal_frame_count(len(clip_paths))
        clips_analysis = []
        for cp in clip_paths:
            frames = claude.extract_keyframes(cp, num_frames=num_frames)
            analysis = claude.analyze_clip(frames, cp)
            analysis["source_file"] = Path(cp).name
            clips_analysis.append({"file": cp, "analysis": analysis})

        jobs[job_id].update(
            progress=60,
            message="Generating edit plan using Style DNA" if style_dna else "Generating edit plan",
        )
        edl = claude.generate_edl(
            clips_analysis=clips_analysis,
            audio_analysis=audio_analysis,
            style_preset=style_preset,
            target_duration=target_duration,
            aspect_ratio=aspect_ratio,
            style_dna=style_dna,
        )

        # Inject speed_ramp into all clips if requested at job level
        if speed_ramp:
            for clip in edl.get("clips", []):
                clip.setdefault("speed_ramp_type", speed_ramp)

        # Save EDL for history
        edl_path = OUTPUT_PATH / f"{job_id}.edl.json"
        edl_path.write_text(json.dumps(edl, indent=2), encoding="utf-8")

        jobs[job_id].update(progress=70, message="Rendering video")
        output_path = str(OUTPUT_PATH / f"{job_id}.mp4")

        from services.export_service import ExportService
        ExportService().render_from_edl(
            edl=edl,
            audio_path=audio_path,
            output_path=output_path,
            clips_dir=str(STORAGE_PATH),
            auto_captions=auto_captions,
            whisper_model=WHISPER_MODEL,
            resolution_preset=resolution_preset,
        )

        # Optional background removal post-processing
        if background_removal:
            jobs[job_id].update(progress=92, message="Removing backgrounds")
            try:
                from services.rembg_service import RembgService
                bg_output = output_path.replace(".mp4", "_nobg.mp4")
                RembgService().remove_background(output_path, bg_output)
                if Path(bg_output).exists():
                    output_path = bg_output
            except Exception as e:
                print(f"  Background removal failed: {e} — skipping")

        jobs[job_id].update(
            status="complete", progress=100, message="Done", output_file=output_path,
        )
        try:
            from middleware.analytics import analytics
            analytics.record_job("complete")
            analytics.record_claude_call()
        except Exception:
            pass

    except Exception as e:
        jobs[job_id].update(status="failed", error=str(e), message="Failed")
        print(f"Job {job_id} failed:\n{traceback.format_exc()}")
        try:
            from middleware.analytics import analytics
            analytics.record_job("failed")
        except Exception:
            pass


# ── Fine-tune ─────────────────────────────────────────────────────────────────

@app.post("/api/finetune/{job_id}")
async def finetune_edit(job_id: str, request: FineTuneRequest, background_tasks: BackgroundTasks):
    """
    Apply manual adjustments to a completed edit and re-render.
    Loads the saved EDL, applies adjustments, creates a new job.
    """
    edl_path = OUTPUT_PATH / f"{job_id}.edl.json"
    if not edl_path.exists():
        raise HTTPException(404, f"EDL for job '{job_id}' not found in history")

    edl = json.loads(edl_path.read_text(encoding="utf-8"))

    # Apply global grade overrides
    grade = edl.setdefault("global_grade", {})
    if request.lut_override:
        grade["lut"] = request.lut_override
    grade["lut_intensity"] = request.lut_intensity
    grade["brightness"]    = request.brightness
    grade["contrast"]      = request.contrast
    grade["saturation"]    = request.saturation

    # Apply per-clip transition overrides
    if request.clip_transitions:
        clips = edl.get("clips", [])
        for idx_str, t_type in request.clip_transitions.items():
            idx = int(idx_str)
            if idx < len(clips) - 1:
                clips[idx]["transition_out"] = {"type": t_type, "duration": 0.5}
            if idx + 1 < len(clips):
                clips[idx + 1]["transition_in"] = {"type": t_type, "duration": 0.5}

    # Text overlay overrides
    if request.remove_text_overlays:
        edl["text_overlays"] = []
    if request.new_text_overlays:
        edl.setdefault("text_overlays", []).extend(request.new_text_overlays)

    new_job_id = str(uuid.uuid4())
    jobs[new_job_id] = {
        "status": "queued", "progress": 0, "message": "Fine-tune job queued",
        "output_file": None, "error": None,
    }

    # Find the audio path from the original job context (best-effort)
    audio_path = _find_audio_for_job(job_id) or ""

    background_tasks.add_task(_run_finetune_job, new_job_id, edl, audio_path)
    return {"job_id": new_job_id, "status": "queued"}


async def _run_finetune_job(job_id: str, edl: dict, audio_path: str):
    import traceback
    try:
        jobs[job_id].update(status="processing", progress=30, message="Re-rendering with adjustments")
        output_path = str(OUTPUT_PATH / f"{job_id}.mp4")
        edl_path = OUTPUT_PATH / f"{job_id}.edl.json"
        edl_path.write_text(json.dumps(edl, indent=2), encoding="utf-8")

        from services.export_service import ExportService
        ExportService().render_from_edl(
            edl=edl,
            audio_path=audio_path if audio_path and os.path.exists(audio_path) else "",
            output_path=output_path,
            clips_dir=str(STORAGE_PATH),
        )
        jobs[job_id].update(status="complete", progress=100, message="Done", output_file=output_path)
    except Exception as e:
        jobs[job_id].update(status="failed", error=str(e), message="Fine-tune failed")
        print(f"Fine-tune job {job_id} failed:\n{traceback.format_exc()}")


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


# ── Edit history ──────────────────────────────────────────────────────────────

@app.get("/api/history")
def list_history():
    edl_files = sorted(
        OUTPUT_PATH.glob("*.edl.json"),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    history = []
    for f in edl_files[:50]:
        try:
            edl = json.loads(f.read_text(encoding="utf-8"))
            job_id = f.stem.replace(".edl", "")
            history.append({
                "job_id": job_id,
                "title": edl.get("project", {}).get("title", "untitled"),
                "duration": edl.get("project", {}).get("target_duration", 0),
                "aspect_ratio": edl.get("project", {}).get("aspect_ratio", "9:16"),
                "clip_count": len(edl.get("clips", [])),
                "saved_at": f.stat().st_mtime,
                "has_video": (OUTPUT_PATH / f"{job_id}.mp4").exists(),
            })
        except Exception:
            pass
    return {"history": history}


@app.get("/api/history/{job_id}")
def get_history_edl(job_id: str):
    edl_path = OUTPUT_PATH / f"{job_id}.edl.json"
    if not edl_path.exists():
        raise HTTPException(404, "Edit not found in history")
    return json.loads(edl_path.read_text(encoding="utf-8"))


# ── Style DNA library ─────────────────────────────────────────────────────────

@app.get("/api/dna")
def list_dna_library():
    items = []
    for f in sorted(DNA_LIB_PATH.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            dna = json.loads(f.read_text(encoding="utf-8"))
            items.append({
                "name": f.stem,
                "saved_at": f.stat().st_mtime,
                "overall_style": dna.get("overall_style", ""),
                "pacing": dna.get("pacing", {}),
                "color": dna.get("color", {}),
            })
        except Exception:
            pass
    return {"library": items}


@app.post("/api/dna")
def save_dna(request: DnaSaveRequest):
    safe_name = "".join(c for c in request.name if c.isalnum() or c in "-_ ").strip().replace(" ", "_")
    if not safe_name:
        raise HTTPException(400, "Invalid DNA name")
    path = DNA_LIB_PATH / f"{safe_name}.json"
    path.write_text(json.dumps(request.style_dna, indent=2), encoding="utf-8")
    return {"saved": safe_name}


@app.get("/api/dna/{name}")
def get_dna(name: str):
    path = DNA_LIB_PATH / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, f"DNA '{name}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.delete("/api/dna/{name}")
def delete_dna(name: str):
    path = DNA_LIB_PATH / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, f"DNA '{name}' not found")
    path.unlink()
    return {"deleted": name}


# ── Batch processing ──────────────────────────────────────────────────────────

@app.post("/api/batch")
async def start_batch(request: BatchRequest, background_tasks: BackgroundTasks):
    """Queue multiple edit jobs as a batch."""
    if not request.jobs:
        raise HTTPException(400, "Provide at least one job spec")

    batch_id = str(uuid.uuid4())
    job_ids = []

    for spec in request.jobs:
        job_id = str(uuid.uuid4())
        job_ids.append(job_id)
        jobs[job_id] = {
            "status": "queued", "progress": 0, "message": "Batch queued",
            "output_file": None, "error": None,
        }
        clip_paths = _resolve_ids(spec.clip_ids)
        audio_path = _resolve_id(spec.audio_id)
        background_tasks.add_task(
            _run_edit_job,
            job_id, clip_paths, audio_path,
            spec.style, spec.target_duration, spec.aspect_ratio,
        )

    batch_jobs[batch_id] = {"job_ids": job_ids, "created_at": __import__("time").time()}
    return {"batch_id": batch_id, "job_ids": job_ids, "count": len(job_ids)}


@app.get("/api/batch/{batch_id}")
def get_batch_status(batch_id: str):
    if batch_id not in batch_jobs:
        raise HTTPException(404, "Batch not found")
    batch = batch_jobs[batch_id]
    job_statuses = []
    for jid in batch["job_ids"]:
        job = jobs.get(jid, {"status": "unknown", "progress": 0, "message": ""})
        job_statuses.append({
            "job_id": jid,
            "status": job["status"],
            "progress": job["progress"],
            "output_file": job.get("output_file"),
        })
    complete  = sum(1 for j in job_statuses if j["status"] == "complete")
    failed    = sum(1 for j in job_statuses if j["status"] == "failed")
    return {
        "batch_id": batch_id,
        "total": len(job_statuses),
        "complete": complete,
        "failed": failed,
        "jobs": job_statuses,
    }


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/api/analytics")
def get_analytics():
    try:
        from middleware.analytics import analytics
        return analytics.get_stats()
    except Exception:
        return {"error": "Analytics not available", "jobs": {}, "requests": {}}


# ── WebSocket — live job progress ─────────────────────────────────────────────

@app.websocket("/ws/{job_id}")
async def ws_job_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    try:
        while True:
            job = jobs.get(job_id) or reference_jobs.get(job_id)
            if not job:
                await websocket.send_json({"status": "failed", "error": "job not found", "progress": 0})
                break

            payload = {
                "status": job["status"],
                "progress": job["progress"],
                "message": job.get("message", ""),
            }
            if job["status"] == "complete":
                payload["output_file"] = job.get("output_file")
                payload["style_dna"]   = job.get("style_dna")

            await websocket.send_json(payload)

            if job["status"] in ("complete", "failed"):
                break

            await asyncio.sleep(0.4)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_id(file_id: str) -> Optional[str]:
    if not file_id:
        return None
    matches = list(STORAGE_PATH.glob(f"{file_id}*"))
    return str(matches[0]) if matches else None


def _resolve_ids(file_ids: List[str]) -> List[str]:
    return [p for fid in file_ids if (p := _resolve_id(fid))]


def _find_ref_file(ref_id: str) -> Optional[str]:
    matches = list(STORAGE_PATH.glob(f"ref_{ref_id}*"))
    return str(matches[0]) if matches else None


def _find_audio_for_job(job_id: str) -> Optional[str]:
    """Best-effort: scan STORAGE_PATH for an audio file associated with a job."""
    for ext in (".mp3", ".wav", ".aac", ".flac", ".m4a"):
        matches = list(STORAGE_PATH.glob(f"*{ext}"))
        if matches:
            return str(matches[-1])
    return None
