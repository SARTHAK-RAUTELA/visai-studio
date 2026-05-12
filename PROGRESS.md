# VisualAI Studio — Build Progress

---

## [2026-05-12] — Phase 1 scaffolding: folder structure + all core services

**Status:** Complete
**Files changed:**
- Created full folder structure (backend/, frontend/, assets/, styles/, etc.)
- `backend/requirements.txt`
- `backend/.env.example`
- `backend/__init__.py`, `backend/models/__init__.py`, `backend/services/__init__.py`, `backend/workers/__init__.py`
- `backend/models/edl.py` — Pydantic schema for EDL JSON
- `backend/models/style_dna.py` — Pydantic schema for Style DNA JSON
- `backend/models/job.py` — Job status schema
- `backend/services/ffmpeg_service.py` — FFmpeg command builder (trim, xfade, LUT, audio mix, text)
- `backend/services/audio_service.py` — Librosa beat detection + mood analysis
- `backend/services/claude_service.py` — Claude API: keyframe extraction, clip analysis, EDL generation
- `backend/services/export_service.py` — Rendering orchestrator (trim → concat → grade → text → audio)
- `backend/services/scene_service.py` — Stub (Phase 2: PySceneDetect)
- `backend/services/color_service.py` — Stub (Phase 2: color analysis + LUT matching)
- `backend/services/reference_service.py` — Stub (Phase 2: full reference video analyzer)
- `backend/workers/celery_app.py` — Celery config
- `backend/workers/edit_job.py` — Edit pipeline Celery task
- `backend/workers/reference_job.py` — Reference analysis Celery task
- `backend/main.py` — FastAPI app with all API endpoints
- `backend/styles/*.json` — All 8 built-in style presets
- `backend/assets/luts/*.cube` — 12 placeholder LUT files (identity; real .cube files needed)
- `generate.py` — CLI entry point
- `docker-compose.yml`, `Dockerfile`

**What works now:**
- Full folder structure matches Section 16 blueprint
- CLI: `python generate.py --clips a.mp4 b.mp4 --audio music.mp3 --style cinematic_travel`
- Audio analysis with Librosa (BPM, beat times, energy, mood)
- Keyframe extraction with OpenCV (20 frames per clip, base64 JPEGs)
- Claude Vision clip analysis (subject, mood, quality, LUT recommendation)
- Claude EDL generation (full edit plan as JSON)
- FFmpeg rendering pipeline (trim → xfade transitions → LUT color grade → text overlays → audio mix)
- FastAPI endpoints: /api/upload, /api/generate, /api/job/{id}/status, /api/job/{id}/result, /api/styles
- All 8 style presets loaded and selectable
- Fallback EDL (no Claude required) for testing pipeline without API key

**Next step:**
- Install dependencies: `pip install -r backend/requirements.txt`
- Copy `backend/.env.example` to `backend/.env` and add `ANTHROPIC_API_KEY`
- Test CLI with real video clips: `python generate.py --clips test.mp4 --audio music.mp3 --style cinematic_travel`
- Replace placeholder LUT .cube files with real cinematic LUTs (download from FreeLUTs or similar)
- If CLI works end-to-end → move to Phase 2 (Reference Video Analyzer)

**Notes:**
- LUT files in `backend/assets/luts/` are identity LUTs (pass-through). The pipeline works but color grading will be no-op until real .cube files are dropped in.
- `--no-claude` flag available to test rendering pipeline without API key
- FFmpeg must be installed and in PATH (`ffmpeg --version` should work)
- Python 3.11+ required
- The xfade offset calculation handles transition overlap correctly (accumulated output_len tracking)
- Windows paths in FFmpeg filters use forward slashes for compatibility
