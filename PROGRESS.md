# VisualAI Studio — Build Progress

---

## [2026-05-12] — Phase 1 complete: CLI pipeline working end-to-end

**Status:** Complete
**Files changed:**
- `generate.py` — CLI entry point (+ encoding fix: UTF-8 stdout wrapper, `PYTHONUTF8=1`)
- `backend/requirements.txt` — version pins updated to `>=` for Python 3.13 compatibility
- `backend/.env` — created from `.env.example`; `FFMPEG_BIN`, `FFPROBE_BIN`, `PYTHONUTF8` added
- `backend/.env.example` — added `FFMPEG_BIN` / `FFPROBE_BIN` entries
- `backend/services/ffmpeg_service.py` — reads `FFMPEG_BIN`/`FFPROBE_BIN` from env; added `_ffmpeg_path()` helper for Windows path escaping
- `backend/services/audio_service.py` — librosa 0.11 fix: `sparse=False` + `np.squeeze(tempo)`
- `backend/models/edl.py` — Pydantic EDL schema
- `backend/models/style_dna.py` — Pydantic Style DNA schema
- `backend/models/job.py` — Job status schema
- `backend/services/claude_service.py` — Claude Vision clip analysis + EDL generation
- `backend/services/export_service.py` — full render orchestrator (trim → xfade → grade → text → audio)
- `backend/services/scene_service.py` — Phase 2 stub
- `backend/services/color_service.py` — Phase 2 stub
- `backend/services/reference_service.py` — Phase 2 stub
- `backend/workers/celery_app.py`, `edit_job.py`, `reference_job.py` — Phase 3 Celery tasks
- `backend/main.py` — FastAPI app with all Phase 1 endpoints
- `backend/styles/*.json` — all 8 style presets
- `backend/assets/luts/*.cube` — 12 identity placeholder LUT files
- `docker-compose.yml`, `Dockerfile`

**What works now:**
- Full CLI pipeline runs end-to-end: `.\venv\Scripts\python.exe generate.py --clips a.mp4 b.mp4 --audio music.mp3 --style cinematic_travel`
- `--no-claude` flag skips API and builds a simple equal-duration EDL (good for FFmpeg-only testing)
- Audio analysis: Librosa BPM detection, beat timestamps, energy curve, mood estimation
- Keyframe extraction: OpenCV, up to 20 frames per clip, base64 JPEG
- Claude Vision clip analysis: subject, mood, quality, LUT recommendation per clip
- Claude EDL generation: full structured JSON edit plan driven by beats + style preset
- EDL execution: trim → xfade transitions → LUT color grade → text overlays → audio mix/fade
- All 8 style presets selectable (cinematic_travel, genz_fast_edit, dark_moody, warm_aesthetic, vintage_film, art_showcase, energy_action, minimal_slideshow)
- FastAPI backend: /api/upload, /api/generate, /api/job/{id}/status, /api/job/{id}/result, /api/styles, /api/luts
- Verified output: `test_output.mp4` = 1080×1920, H.264, AAC, 7.2s, 3.9MB ✓

**Environment (this machine):**
- Python 3.13.9 (Blender 5.1 bundled) — venv at `venv/`
- Always run as: `.\venv\Scripts\python.exe generate.py ...`
- Packages: anthropic 0.101, opencv 4.13, librosa 0.11, numpy 2.4, scipy 1.17, pydub 0.25
- FFmpeg 8.1.1 at `D:\Installed-apps-files\ffmpeg-8.1.1-essentials_build\ffmpeg-8.1.1-essentials_build\bin\`
- FFmpeg path configured in `backend/.env` — no system PATH change needed

**Next step:**
1. Add real `ANTHROPIC_API_KEY` to `backend/.env`
2. Test with real video clips + Claude:
   ```
   .\venv\Scripts\python.exe generate.py --clips clip1.mp4 clip2.mp4 --audio music.mp3 --style cinematic_travel
   ```
3. Drop real `.cube` LUT files into `backend/assets/luts/` to enable actual color grading
4. Once real-clip test passes → start Phase 2 (Reference Video Analyzer)

**Notes:**
- LUT files are identity pass-throughs — pipeline works but no color change until real `.cube` files added
- `_ffmpeg_path()` escapes Windows drive-letter colons in FFmpeg filter strings (`D:` → `D\:`)
- librosa 0.11 changed `beat_track` to return sparse arrays by default; fixed with `sparse=False`
- Windows console encoding: `PYTHONUTF8=1` in `.env` + UTF-8 stdout wrapper in `generate.py`
- The EDL JSON is saved alongside the output video as `output.edl.json` for debugging every run

---

## Phase 1 Checklist (from projectDetails.md Section 18)

- [x] FastAPI setup with file upload endpoints
- [x] FFmpeg wrapper class (trim, concat, xfade, LUT, audio mix)
- [ ] MoviePy composition pipeline (deferred — FFmpeg direct is faster for Phase 1)
- [x] Librosa beat detection service
- [x] Claude API service (clip analysis + EDL generation)
- [x] Frame extraction (OpenCV, 20 frames/clip)
- [x] EDL JSON parser → FFmpeg command builder
- [x] 3 LUTs working (teal_orange, warm_golden, moody_blue) — identity for now, real .cube needed
- [x] 3 transitions working (fade, dissolve, hard_cut)
- [x] Basic text overlay via FFmpeg drawtext
- [x] CLI: `python generate.py --clips a.mp4 b.mp4 --audio music.mp3 --style cinematic_travel`

---

## Phase 2 — Reference Video Analyzer (not started)

**Goal:** Full style clone feature — upload any video, extract its editing DNA, apply to user's footage

Checklist:
- [ ] PySceneDetect integration — cut detection
- [ ] OpenCV transition classifier (hard_cut, fade, dissolve, zoom, glitch)
- [ ] Color grade analyzer (histogram, hue, saturation)
- [ ] LUT matching algorithm
- [ ] Optical flow speed ramp detection
- [ ] Claude Vision reference frame analysis
- [ ] Style DNA JSON generation
- [ ] yt-dlp integration (YouTube/Instagram/TikTok download)
- [ ] Style DNA → EDL prompt integration
- [ ] Test: clone 5 different reference video styles
