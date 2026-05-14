import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

from logger import logger

app = FastAPI(title="VisualAI Studio API", version="5.0.0")

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
except Exception as e:
    logger.warning(f"Analytics middleware unavailable: {e}")

try:
    from middleware.auth import APIKeyMiddleware
    app.add_middleware(APIKeyMiddleware)
except Exception as e:
    logger.warning(f"Auth middleware unavailable: {e}")

# ── Paths ─────────────────────────────────────────────────────────────────────

STORAGE_PATH   = Path(os.getenv("STORAGE_PATH", "./temp"))
OUTPUT_PATH    = Path(os.getenv("OUTPUT_PATH", "./output"))
STYLES_PATH    = Path(__file__).parent / "styles"
DNA_LIB_PATH   = Path(os.getenv("OUTPUT_PATH", "./output")) / "dna_library"
JOB_STORE_PATH = OUTPUT_PATH / "job_store"
SFX_DIR        = Path(__file__).parent / "assets" / "sfx"
WHISPER_MODEL  = os.getenv("WHISPER_MODEL", "base")
MAX_UPLOAD_MB  = int(os.getenv("MAX_UPLOAD_MB", "500"))

for _p in (STORAGE_PATH, OUTPUT_PATH, DNA_LIB_PATH, JOB_STORE_PATH):
    _p.mkdir(parents=True, exist_ok=True)

# ── EDL versioning ────────────────────────────────────────────────────────────

EDL_SCHEMA_VERSION = "1.0"

def _stamp_edl(edl: dict) -> dict:
    edl.setdefault("schema_version", EDL_SCHEMA_VERSION)
    return edl

def _validate_edl(edl: dict) -> bool:
    return (
        isinstance(edl, dict)
        and isinstance(edl.get("clips"), list)
        and len(edl.get("clips", [])) > 0
    )

# ── Job persistence ───────────────────────────────────────────────────────────

jobs: dict           = {}
reference_jobs: dict = {}
batch_jobs: dict     = {}


def _persist(prefix: str, job_id: str, data: dict) -> None:
    try:
        (JOB_STORE_PATH / f"{prefix}_{job_id}.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning(f"Persist failed [{prefix}/{job_id}]: {exc}")


def _load_jobs_from_disk() -> None:
    loaded_jobs = loaded_refs = 0
    for f in JOB_STORE_PATH.glob("job_*.json"):
        jid = f.stem[4:]
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if jid not in jobs:
                jobs[jid] = data
                loaded_jobs += 1
        except Exception:
            pass
    for f in JOB_STORE_PATH.glob("ref_*.json"):
        rid = f.stem[4:]
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if rid not in reference_jobs:
                reference_jobs[rid] = data
                loaded_refs += 1
        except Exception:
            pass
    logger.info(f"Loaded {loaded_jobs} jobs and {loaded_refs} reference jobs from disk")


_load_jobs_from_disk()


def _update_job(store: dict, job_id: str, prefix: str, patch: dict) -> None:
    store[job_id].update(patch)
    _persist(prefix, job_id, store[job_id])


# ── Export presets ────────────────────────────────────────────────────────────

EXPORT_PRESETS = [
    {"id": "tiktok",          "label": "TikTok",           "aspect_ratio": "9:16",  "resolution": "1080p"},
    {"id": "youtube_shorts",  "label": "YouTube Shorts",   "aspect_ratio": "9:16",  "resolution": "1080p"},
    {"id": "instagram_reels", "label": "Instagram Reels",  "aspect_ratio": "9:16",  "resolution": "1080p"},
    {"id": "instagram_feed",  "label": "Instagram Feed",   "aspect_ratio": "4:5",   "resolution": "1080p"},
    {"id": "instagram_square","label": "Instagram Square", "aspect_ratio": "1:1",   "resolution": "1080p"},
    {"id": "youtube",         "label": "YouTube",          "aspect_ratio": "16:9",  "resolution": "1080p"},
    {"id": "youtube_4k",      "label": "YouTube 4K",       "aspect_ratio": "16:9",  "resolution": "4K"},
    {"id": "twitter",         "label": "Twitter/X",        "aspect_ratio": "16:9",  "resolution": "720p"},
]

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
    resolution_preset: str = "1080p"
    background_removal: bool = False
    speed_ramp: Optional[str] = None
    beat_sync: bool = False
    audio_ducking: bool = False


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
    clip_transitions: Optional[dict] = None
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


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    checks: dict = {"status": "ok", "version": "5.0.0"}

    # FFmpeg
    try:
        from services.ffmpeg_service import FFmpegService
        ffmpeg = FFmpegService()
        r = subprocess.run([ffmpeg.ffmpeg, "-version"], capture_output=True, timeout=5)
        ver_line = r.stdout.decode(errors="ignore").splitlines()[0] if r.returncode == 0 else "unavailable"
        checks["ffmpeg"] = ver_line.split("version")[-1].strip().split(" ")[0] if "version" in ver_line else "ok"
    except Exception as e:
        checks["ffmpeg"] = f"error: {e}"
        checks["status"] = "degraded"

    # Disk space
    try:
        usage = shutil.disk_usage(OUTPUT_PATH)
        checks["disk_free_gb"] = round(usage.free / (1024 ** 3), 1)
    except Exception:
        checks["disk_free_gb"] = "unknown"

    # Claude API key present
    checks["claude_api_key"] = bool(os.getenv("ANTHROPIC_API_KEY"))

    # Job counts
    checks["jobs_in_memory"] = len(jobs)
    checks["ref_jobs_in_memory"] = len(reference_jobs)

    return checks


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "app": "VisualAI Studio", "version": "5.0.0"}


# ── Upload ────────────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)

    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(413, f"File too large ({size_mb:.1f} MB). Limit: {MAX_UPLOAD_MB} MB")

    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    save_path = STORAGE_PATH / f"{file_id}{ext}"
    save_path.write_bytes(content)

    # Generate thumbnail for video clips
    thumbnail = ""
    video_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    if ext in video_exts:
        try:
            from services.ffmpeg_service import FFmpegService
            thumbnail = FFmpegService().generate_thumbnail(str(save_path))
        except Exception as e:
            logger.debug(f"Thumbnail skip: {e}")

    return {
        "file_id": file_id,
        "original_name": file.filename,
        "size_mb": round(size_mb, 2),
        "thumbnail": thumbnail,
    }


@app.post("/api/upload/reference")
async def upload_reference(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
):
    if url:
        ref_id = str(uuid.uuid4())
        reference_jobs[ref_id] = {
            "status": "downloading", "progress": 5,
            "message": "Download queued", "file_path": None,
            "style_dna": None, "error": None,
        }
        _persist("ref", ref_id, reference_jobs[ref_id])
        # Non-blocking: download happens in background
        background_tasks.add_task(_download_reference_url, ref_id, url)
        return {"file_id": ref_id, "source": "url", "status": "downloading"}

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
    _persist("ref", ref_id, reference_jobs[ref_id])
    return {"file_id": ref_id, "original_name": file.filename}


async def _download_reference_url(ref_id: str, url: str) -> None:
    await asyncio.to_thread(_download_reference_url_sync, ref_id, url)


def _download_reference_url_sync(ref_id: str, url: str) -> None:
    try:
        from services.reference_service import ReferenceService
        file_path = ReferenceService().download_from_url(url, str(STORAGE_PATH))
        _update_job(reference_jobs, ref_id, "ref", {
            "status": "downloaded", "progress": 100,
            "message": "Download complete", "file_path": file_path,
        })
    except Exception as e:
        _update_job(reference_jobs, ref_id, "ref", {
            "status": "failed", "error": str(e), "message": "Download failed",
        })
        logger.error(f"Reference URL download failed [{ref_id}]: {e}")


# ── Styles, LUTs, Export presets ──────────────────────────────────────────────

@app.get("/api/styles")
def list_styles():
    styles = []
    for f in sorted(STYLES_PATH.glob("*.json")):
        try:
            with open(f) as fp:
                styles.append(json.load(fp))
        except Exception:
            pass
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


@app.get("/api/export-presets")
def list_export_presets():
    return {"presets": EXPORT_PRESETS}


# ── Reference analysis ────────────────────────────────────────────────────────

@app.post("/api/analyze/reference")
async def analyze_reference(request: ReferenceRequest, background_tasks: BackgroundTasks):
    ref_id = request.file_id or str(uuid.uuid4())

    if request.reference_type == "url" and request.url:
        existing = reference_jobs.get(ref_id, {})
        file_path = existing.get("file_path")
        if not file_path:
            raise HTTPException(400, "URL reference not yet downloaded. Use /api/upload/reference first.")
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
    _persist("ref", ref_id, reference_jobs[ref_id])
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


async def _run_reference_job(ref_id: str, file_path: str) -> None:
    await asyncio.to_thread(_run_reference_job_sync, ref_id, file_path)


def _run_reference_job_sync(ref_id: str, file_path: str) -> None:
    import traceback
    try:
        _update_job(reference_jobs, ref_id, "ref", {
            "status": "processing", "progress": 10, "message": "Detecting scenes",
        })
        from services.reference_service import ReferenceService
        from services.claude_service import ClaudeService
        svc = ReferenceService()
        try:
            claude = ClaudeService()
        except Exception:
            claude = None
        _update_job(reference_jobs, ref_id, "ref", {"progress": 60, "message": "Generating Style DNA"})
        style_dna = svc.analyze(file_path, claude_service=claude)
        dna_path = OUTPUT_PATH / f"style_dna_{ref_id}.json"
        dna_path.write_text(json.dumps(style_dna, indent=2), encoding="utf-8")
        _update_job(reference_jobs, ref_id, "ref", {
            "status": "complete", "progress": 100, "message": "Style DNA ready",
            "style_dna": style_dna, "dna_file": str(dna_path),
        })
        _record_analytics("complete")
    except Exception as e:
        _update_job(reference_jobs, ref_id, "ref", {
            "status": "failed", "error": str(e), "message": "Analysis failed",
        })
        logger.error(f"Reference job {ref_id} failed:\n{traceback.format_exc()}")
        _record_analytics("failed")


# ── Generate ──────────────────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate_edit(request: GenerateRequest, background_tasks: BackgroundTasks):
    if not request.clip_ids:
        raise HTTPException(400, "Provide at least one clip_id")
    if not request.audio_id:
        raise HTTPException(400, "Provide audio_id")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "queued", "progress": 0, "message": "",
        "output_file": None, "error": None,
    }
    _persist("job", job_id, jobs[job_id])

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

    _record_analytics("started")

    background_tasks.add_task(
        _run_edit_job,
        job_id, clip_paths, audio_path,
        request.style, request.target_duration, request.aspect_ratio,
        style_dna, request.auto_captions, request.sound_fx,
        request.resolution_preset, request.background_removal, request.speed_ramp,
        request.beat_sync, request.audio_ducking,
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
    beat_sync: bool = False,
    audio_ducking: bool = False,
) -> None:
    await asyncio.to_thread(
        _run_edit_job_sync,
        job_id, clip_paths, audio_path, style, target_duration, aspect_ratio,
        style_dna, auto_captions, sound_fx, resolution_preset,
        background_removal, speed_ramp, beat_sync, audio_ducking,
    )


def _run_edit_job_sync(
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
    beat_sync: bool = False,
    audio_ducking: bool = False,
) -> None:
    import traceback
    try:
        _update_job(jobs, job_id, "job", {"status": "processing", "progress": 10, "message": "Loading style preset"})

        style_path = STYLES_PATH / f"{style}.json"
        if not style_path.exists():
            raise FileNotFoundError(f"Style preset '{style}' not found")
        with open(style_path) as f:
            style_preset = json.load(f)

        _update_job(jobs, job_id, "job", {"progress": 15, "message": "Extracting best moments from long clips"})
        from services.clip_extractor import ClipExtractorService
        extractor = ClipExtractorService()
        expanded = []
        for cp in clip_paths:
            expanded.extend(extractor.maybe_extract(cp, str(STORAGE_PATH), max_clips=4))
        clip_paths = expanded or clip_paths

        _update_job(jobs, job_id, "job", {"progress": 20, "message": "Analyzing audio"})
        from services.audio_service import AudioService
        audio_analysis = AudioService().analyze_audio(audio_path)

        _update_job(jobs, job_id, "job", {"progress": 35, "message": "Analyzing clips with Claude Vision"})
        from services.claude_service import ClaudeService
        claude = ClaudeService()
        num_frames = ClaudeService.optimal_frame_count(len(clip_paths))
        clips_analysis = []
        for cp in clip_paths:
            frames = claude.extract_keyframes(cp, num_frames=num_frames)
            analysis = claude.analyze_clip(frames, cp)
            analysis["source_file"] = Path(cp).name
            clips_analysis.append({"file": cp, "analysis": analysis})

        _update_job(jobs, job_id, "job", {
            "progress": 60,
            "message": "Generating edit plan using Style DNA" if style_dna else "Generating edit plan",
        })
        edl = claude.generate_edl(
            clips_analysis=clips_analysis,
            audio_analysis=audio_analysis,
            style_preset=style_preset,
            target_duration=target_duration,
            aspect_ratio=aspect_ratio,
            style_dna=style_dna,
        )

        # Validate EDL; fall back if malformed
        if not _validate_edl(edl):
            logger.warning(f"Job {job_id}: EDL from Claude failed validation, using fallback")
            edl = claude._build_fallback_edl(clips_analysis, style_preset, target_duration, aspect_ratio,
                                              {"9:16": "1080x1920", "16:9": "1920x1080", "1:1": "1080x1080"}.get(aspect_ratio, "1080x1920"))

        _stamp_edl(edl)

        # Beat sync: snap clip cut points to nearest beat
        if beat_sync and audio_analysis.get("beat_times"):
            _update_job(jobs, job_id, "job", {"progress": 63, "message": "Snapping cuts to beats"})
            try:
                edl = AudioService().snap_edl_to_beats(edl, audio_analysis["beat_times"])
                logger.info(f"Job {job_id}: beat sync applied")
            except Exception as bs_err:
                logger.warning(f"Job {job_id}: beat sync failed ({bs_err}) — continuing without")

        # Speed ramp injection
        if speed_ramp:
            for clip in edl.get("clips", []):
                clip.setdefault("speed_ramp_type", speed_ramp)

        # SFX injection when requested and EDL has no SFX
        if sound_fx and not edl.get("sound_fx"):
            edl["sound_fx"] = _build_sfx_entries(edl)

        # Save EDL for history
        edl_path = OUTPUT_PATH / f"{job_id}.edl.json"
        edl_path.write_text(json.dumps(edl, indent=2), encoding="utf-8")

        _update_job(jobs, job_id, "job", {"progress": 70, "message": "Rendering video"})
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

        # Validate output exists and is non-zero
        if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
            raise RuntimeError("Render produced no output — check FFmpeg logs")

        # Audio ducking: compress music peaks to improve perceived clarity
        if audio_ducking:
            _update_job(jobs, job_id, "job", {"progress": 85, "message": "Applying audio ducking"})
            try:
                from services.ffmpeg_service import FFmpegService as _FFSvc
                ducked_path = output_path.replace(".mp4", "_ducked.mp4")
                _FFSvc().apply_audio_ducking(output_path, ducked_path)
                if Path(ducked_path).exists():
                    os.replace(ducked_path, output_path)
                    logger.info(f"Job {job_id}: audio ducking applied")
            except Exception as ad_err:
                logger.warning(f"Job {job_id}: audio ducking failed ({ad_err}) — continuing")

        if background_removal:
            _update_job(jobs, job_id, "job", {"progress": 92, "message": "Removing backgrounds"})
            try:
                from services.rembg_service import RembgService
                bg_output = output_path.replace(".mp4", "_nobg.mp4")
                RembgService().remove_background(output_path, bg_output)
                if Path(bg_output).exists():
                    output_path = bg_output
                else:
                    logger.warning(f"Job {job_id}: background removal produced no output, keeping original")
                    _update_job(jobs, job_id, "job", {"message": "Background removal skipped (rembg unavailable)"})
            except ImportError:
                logger.warning(f"Job {job_id}: rembg not installed — background removal skipped")
                _update_job(jobs, job_id, "job", {"message": "Background removal skipped (rembg not installed)"})
            except Exception as e:
                logger.warning(f"Job {job_id}: background removal failed: {e} — keeping original")

        _update_job(jobs, job_id, "job", {
            "status": "complete", "progress": 100, "message": "Done",
            "output_file": output_path,
        })
        _record_analytics("complete", claude_call=True)

    except Exception as e:
        _update_job(jobs, job_id, "job", {"status": "failed", "error": str(e), "message": "Failed"})
        logger.error(f"Job {job_id} failed:\n{traceback.format_exc()}")
        _record_analytics("failed")


# ── Fine-tune ─────────────────────────────────────────────────────────────────

@app.post("/api/finetune/{job_id}")
async def finetune_edit(job_id: str, request: FineTuneRequest, background_tasks: BackgroundTasks):
    edl_path = OUTPUT_PATH / f"{job_id}.edl.json"
    if not edl_path.exists():
        raise HTTPException(404, f"EDL for job '{job_id}' not found in history")

    edl = json.loads(edl_path.read_text(encoding="utf-8"))

    grade = edl.setdefault("global_grade", {})
    if request.lut_override:
        grade["lut"] = request.lut_override
    grade["lut_intensity"] = request.lut_intensity
    grade["brightness"]    = request.brightness
    grade["contrast"]      = request.contrast
    grade["saturation"]    = request.saturation

    if request.clip_transitions:
        clips = edl.get("clips", [])
        for idx_str, t_type in request.clip_transitions.items():
            idx = int(idx_str)
            if idx < len(clips) - 1:
                clips[idx]["transition_out"] = {"type": t_type, "duration": 0.5}
            if idx + 1 < len(clips):
                clips[idx + 1]["transition_in"] = {"type": t_type, "duration": 0.5}

    if request.remove_text_overlays:
        edl["text_overlays"] = []
    if request.new_text_overlays:
        edl.setdefault("text_overlays", []).extend(request.new_text_overlays)

    new_job_id = str(uuid.uuid4())
    jobs[new_job_id] = {
        "status": "queued", "progress": 0, "message": "Fine-tune job queued",
        "output_file": None, "error": None,
    }
    _persist("job", new_job_id, jobs[new_job_id])

    audio_path = _find_audio_for_job(job_id) or ""
    background_tasks.add_task(_run_finetune_job, new_job_id, edl, audio_path)
    return {"job_id": new_job_id, "status": "queued"}


async def _run_finetune_job(job_id: str, edl: dict, audio_path: str) -> None:
    await asyncio.to_thread(_run_finetune_job_sync, job_id, edl, audio_path)


def _run_finetune_job_sync(job_id: str, edl: dict, audio_path: str) -> None:
    import traceback
    try:
        _update_job(jobs, job_id, "job", {"status": "processing", "progress": 30, "message": "Re-rendering with adjustments"})
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
        _update_job(jobs, job_id, "job", {"status": "complete", "progress": 100, "message": "Done", "output_file": output_path})
    except Exception as e:
        _update_job(jobs, job_id, "job", {"status": "failed", "error": str(e), "message": "Fine-tune failed"})
        logger.error(f"Fine-tune job {job_id} failed:\n{traceback.format_exc()}")


# ── Preview render ────────────────────────────────────────────────────────────

@app.post("/api/preview/{job_id}")
async def create_preview(job_id: str, background_tasks: BackgroundTasks):
    """Generate a 30-second preview render for an existing edit."""
    edl_path = OUTPUT_PATH / f"{job_id}.edl.json"
    if not edl_path.exists():
        raise HTTPException(404, f"EDL for job '{job_id}' not found")

    edl = json.loads(edl_path.read_text(encoding="utf-8"))

    # Trim EDL to first 30 seconds
    preview_duration = 30.0
    preview_edl = _trim_edl_to_duration(edl, preview_duration)

    preview_job_id = f"preview_{str(uuid.uuid4())[:8]}"
    jobs[preview_job_id] = {
        "status": "queued", "progress": 0,
        "message": "Preview render queued", "output_file": None, "error": None,
    }
    _persist("job", preview_job_id, jobs[preview_job_id])

    audio_path = _find_audio_for_job(job_id) or ""
    background_tasks.add_task(_run_finetune_job, preview_job_id, preview_edl, audio_path)
    return {"job_id": preview_job_id, "status": "queued", "preview_duration": preview_duration}


def _trim_edl_to_duration(edl: dict, max_duration: float) -> dict:
    """Return a copy of the EDL with clips trimmed to fit within max_duration."""
    import copy
    edl = copy.deepcopy(edl)
    clips = edl.get("clips", [])
    kept, total = [], 0.0
    for clip in clips:
        clip_dur = float(clip.get("source_out", 5)) - float(clip.get("source_in", 0))
        if total + clip_dur > max_duration:
            remaining = max_duration - total
            if remaining > 0.5:
                clip["source_out"] = float(clip.get("source_in", 0)) + remaining
                kept.append(clip)
            break
        kept.append(clip)
        total += clip_dur
    edl["clips"] = kept
    if edl.get("project"):
        edl["project"]["target_duration"] = min(max_duration, total)
    return edl


# ── Photo to video ────────────────────────────────────────────────────────────

@app.post("/api/photo/convert")
async def photo_to_video(
    file_id: str = Form(...),
    duration: float = Form(5.0),
    ken_burns: bool = Form(True),
    resolution_preset: str = Form("1080p"),
    aspect_ratio: str = Form("9:16"),
):
    file_path = _resolve_id(file_id)
    if not file_path:
        raise HTTPException(404, f"File '{file_id}' not found")

    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
    if Path(file_path).suffix.lower() not in image_exts:
        raise HTTPException(400, "File is not a supported image (jpg/png/webp/bmp/tiff)")

    output_id = str(uuid.uuid4())
    output_path = str(STORAGE_PATH / f"{output_id}.mp4")

    from services.export_service import ExportService
    from services.ffmpeg_service import FFmpegService

    res_map = ExportService.RESOLUTIONS.get(aspect_ratio, ExportService.RESOLUTIONS["9:16"])
    preset_map = {"720p": "720p", "1080p": "1080p", "4K": "4K"}
    w, h = res_map.get(preset_map.get(resolution_preset, "1080p"), res_map["1080p"])

    try:
        FFmpegService().image_to_video(
            file_path, output_path,
            duration=max(0.5, min(duration, 30.0)),
            target_width=w,
            target_height=h,
            ken_burns=ken_burns,
        )
    except Exception as e:
        raise HTTPException(500, f"Photo conversion failed: {e}")

    # Register converted clip so it can be used in generate
    clip_size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
    return {
        "file_id": output_id,
        "original_name": Path(file_path).name,
        "size_mb": round(clip_size / (1024 * 1024), 2),
        "duration": duration,
    }


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
    # Remove persisted file
    try:
        (JOB_STORE_PATH / f"job_{job_id}.json").unlink(missing_ok=True)
    except Exception:
        pass
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
                "schema_version": edl.get("schema_version", "legacy"),
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
        _persist("job", job_id, jobs[job_id])
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
    complete = sum(1 for j in job_statuses if j["status"] == "complete")
    failed   = sum(1 for j in job_statuses if j["status"] == "failed")
    return {
        "batch_id": batch_id,
        "total": len(job_statuses),
        "complete": complete,
        "failed": failed,
        "jobs": job_statuses,
    }


# ── Transitions catalogue ─────────────────────────────────────────────────────

TRANSITIONS_CATALOGUE = {
    "Basic": [
        {"id": "hard_cut",   "label": "Hard Cut",     "desc": "Instant jump-cut between clips"},
        {"id": "dissolve",   "label": "Dissolve",     "desc": "Classic crossfade blend"},
        {"id": "fade",       "label": "Fade",         "desc": "Fade to/from transparent"},
        {"id": "fade_black", "label": "Fade to Black","desc": "Fade through black frame"},
        {"id": "fade_white", "label": "Fade to White","desc": "Fade through white frame"},
    ],
    "Slides": [
        {"id": "wipe_left",    "label": "Wipe Left",    "desc": "Wipe new clip in from right"},
        {"id": "wipe_right",   "label": "Wipe Right",   "desc": "Wipe new clip in from left"},
        {"id": "slide_left",   "label": "Slide Left",   "desc": "Slide clips to the left"},
        {"id": "slide_right",  "label": "Slide Right",  "desc": "Slide clips to the right"},
    ],
    "Zooms": [
        {"id": "zoom_in",    "label": "Zoom In",      "desc": "Zoom into next clip"},
        {"id": "zoom_out",   "label": "Zoom Out",     "desc": "Zoom out to next clip"},
    ],
    "Stylized": [
        {"id": "glitch",    "label": "Glitch",       "desc": "Digital glitch effect"},
        {"id": "flash",     "label": "Flash",        "desc": "White flash between clips"},
        {"id": "spin",      "label": "Spin",         "desc": "Rotation transition"},
        {"id": "pixelate",  "label": "Pixelate",     "desc": "Pixel-blur between clips"},
        {"id": "circle_open","label":"Circle Open",  "desc": "Iris-open reveal"},
    ],
}


@app.get("/api/transitions")
def list_transitions():
    return {"categories": TRANSITIONS_CATALOGUE}


# ── Scene detection ────────────────────────────────────────────────────────────

@app.post("/api/clips/{file_id}/detect-scenes")
async def detect_scenes(file_id: str):
    """Detect scene cuts in an uploaded clip and return scene timestamps."""
    file_path = _resolve_id(file_id)
    if not file_path:
        raise HTTPException(404, f"Clip '{file_id}' not found")

    video_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    if Path(file_path).suffix.lower() not in video_exts:
        raise HTTPException(400, "File is not a video clip")

    try:
        from services.scene_service import SceneService
        scenes = await asyncio.to_thread(SceneService().detect_scenes, file_path)
    except Exception as e:
        raise HTTPException(500, f"Scene detection failed: {e}")

    return {
        "file_id": file_id,
        "scene_count": len(scenes),
        "scenes": [{"index": i, "start": round(s, 3), "end": round(e, 3), "duration": round(e - s, 3)}
                   for i, (s, e) in enumerate(scenes)],
    }


# ── Auto reframe ───────────────────────────────────────────────────────────────

class ReframeRequest(BaseModel):
    target_ratio: str = "9:16"


@app.post("/api/clips/{file_id}/reframe")
async def reframe_clip(file_id: str, request: ReframeRequest):
    """Re-crop a clip to a new aspect ratio."""
    file_path = _resolve_id(file_id)
    if not file_path:
        raise HTTPException(404, f"Clip '{file_id}' not found")

    valid_ratios = {"9:16", "16:9", "1:1", "4:5"}
    if request.target_ratio not in valid_ratios:
        raise HTTPException(400, f"target_ratio must be one of {sorted(valid_ratios)}")

    output_id = str(uuid.uuid4())
    output_path = str(STORAGE_PATH / f"{output_id}.mp4")

    try:
        from services.ffmpeg_service import FFmpegService
        await asyncio.to_thread(
            FFmpegService().reframe_clip, file_path, output_path, request.target_ratio
        )
    except Exception as e:
        raise HTTPException(500, f"Reframe failed: {e}")

    size_mb = round(Path(output_path).stat().st_size / (1024 * 1024), 2) if Path(output_path).exists() else 0

    thumbnail = ""
    try:
        from services.ffmpeg_service import FFmpegService
        thumbnail = FFmpegService().generate_thumbnail(output_path)
    except Exception:
        pass

    return {
        "file_id": output_id,
        "original_file_id": file_id,
        "target_ratio": request.target_ratio,
        "size_mb": size_mb,
        "thumbnail": thumbnail,
    }


# ── Vocal isolation ────────────────────────────────────────────────────────────

@app.post("/api/audio/{file_id}/vocal-isolate")
async def vocal_isolate(file_id: str):
    """Isolate harmonic/vocal content from an audio file using HPSS."""
    file_path = _resolve_id(file_id)
    if not file_path:
        raise HTTPException(404, f"Audio file '{file_id}' not found")

    audio_exts = {".mp3", ".wav", ".aac", ".flac", ".m4a"}
    if Path(file_path).suffix.lower() not in audio_exts:
        raise HTTPException(400, "File is not a supported audio format")

    output_id = str(uuid.uuid4())
    output_path = str(STORAGE_PATH / f"{output_id}.wav")

    try:
        from services.audio_service import AudioService
        await asyncio.to_thread(AudioService().isolate_vocals, file_path, output_path)
    except ImportError:
        raise HTTPException(503, "soundfile package required — pip install soundfile")
    except Exception as e:
        raise HTTPException(500, f"Vocal isolation failed: {e}")

    size_mb = round(Path(output_path).stat().st_size / (1024 * 1024), 2) if Path(output_path).exists() else 0
    return {"file_id": output_id, "original_file_id": file_id, "size_mb": size_mb}


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
    for ext in (".mp3", ".wav", ".aac", ".flac", ".m4a"):
        matches = list(STORAGE_PATH.glob(f"*{ext}"))
        if matches:
            return str(matches[-1])
    return None


def _build_sfx_entries(edl: dict) -> list:
    """Auto-populate SFX entries at cut points from the assets/sfx library."""
    if not SFX_DIR.exists():
        return []
    available = list(SFX_DIR.glob("*.mp3")) + list(SFX_DIR.glob("*.wav"))
    if not available:
        return []
    cut_times = edl.get("cut_timestamps", [])
    entries = []
    for i, t in enumerate(cut_times[:5]):
        sfx_file = available[i % len(available)]
        entries.append({
            "file": sfx_file.name,
            "timeline_time": float(t),
            "volume": 0.35,
        })
    return entries


def _record_analytics(status: str, claude_call: bool = False) -> None:
    try:
        from middleware.analytics import analytics
        analytics.record_job(status)
        if claude_call:
            analytics.record_claude_call()
    except Exception:
        pass
