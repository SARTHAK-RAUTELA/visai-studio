import React, { useState, useCallback } from 'react'
import useEditStore from '../stores/editStore.js'
import { fineTuneEdit } from '../api/client.js'

// ─── Constants ────────────────────────────────────────────────────────────────

const LUT_OPTIONS = [
  { value: '', label: 'None (use style default)' },
  { value: 'teal_orange',    label: 'Teal & Orange' },
  { value: 'warm_golden',    label: 'Warm Golden' },
  { value: 'moody_blue',     label: 'Moody Blue' },
  { value: 'vintage_film',   label: 'Vintage Film' },
  { value: 'airy_bright',    label: 'Airy & Bright' },
  { value: 'bleach_bypass',  label: 'Bleach Bypass' },
  { value: 'pink_dream',     label: 'Pink Dream' },
  { value: 'forest_green',   label: 'Forest Green' },
  { value: 'cyberpunk',      label: 'Cyberpunk' },
  { value: 'matte_black',    label: 'Matte Black' },
  { value: 'sunrise',        label: 'Sunrise' },
  { value: 'nordic',         label: 'Nordic' },
  { value: 'lofi_aesthetic', label: 'Lo-Fi Aesthetic' },
  { value: 'dark_nature',    label: 'Dark Nature' },
]

const TRANSITION_OPTIONS = [
  { value: 'hard_cut',    label: 'Hard Cut' },
  { value: 'fade',        label: 'Fade' },
  { value: 'fade_black',  label: 'Fade to Black' },
  { value: 'fade_white',  label: 'Fade to White' },
  { value: 'dissolve',    label: 'Dissolve' },
  { value: 'wipe_left',   label: 'Wipe Left' },
  { value: 'wipe_right',  label: 'Wipe Right' },
  { value: 'slide_left',  label: 'Slide Left' },
  { value: 'slide_right', label: 'Slide Right' },
  { value: 'zoom_in',     label: 'Zoom In' },
  { value: 'zoom_out',    label: 'Zoom Out' },
  { value: 'spin',        label: 'Spin' },
  { value: 'glitch',      label: 'Glitch' },
  { value: 'flash',       label: 'Flash' },
  { value: 'flash_black', label: 'Flash Black' },
  { value: 'zoom_punch',  label: 'Zoom Punch' },
  { value: 'ken_burns',   label: 'Ken Burns' },
  { value: 'circle_open', label: 'Circle Open' },
  { value: 'pixelate',    label: 'Pixelate' },
]

// ─── Slider Row ───────────────────────────────────────────────────────────────
function SliderRow({ label, value, min, max, step, display, onChange }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <label className="text-sm text-slate-300">{label}</label>
        <span className="text-sm font-medium text-violet-400 tabular-nums">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none bg-[#1e1e2e] accent-violet-600 cursor-pointer"
      />
    </div>
  )
}

// ─── Section Heading ──────────────────────────────────────────────────────────
function SectionHeading({ children }) {
  return (
    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
      {children}
    </h3>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function FineTuneEditor() {
  const {
    jobId,
    fineTuneJobId,
    outputUrl,
    clips,
    setScreen,
    setJobState,
    setOutputUrl,
  } = useEditStore()

  const videoJobId = fineTuneJobId || jobId
  const videoSrc = outputUrl || (videoJobId ? `/api/job/${videoJobId}/result` : null)

  // ── Color grading state ───────────────────────────────────────────────────
  const [brightness,  setBrightness]  = useState(0)
  const [contrast,    setContrast]    = useState(1.0)
  const [saturation,  setSaturation]  = useState(1.0)
  const [lut,         setLut]         = useState('')
  const [lutIntensity, setLutIntensity] = useState(70)

  // ── Transitions state ─────────────────────────────────────────────────────
  // Build a transition map keyed by clip index (0 = gap between clip 1 and 2, etc.)
  const clipCount = Math.max(clips.length, 2)
  const gapCount  = Math.max(0, clipCount - 1)
  const [clipTransitions, setClipTransitions] = useState(() => {
    const initial = {}
    for (let i = 0; i < gapCount; i++) initial[String(i)] = 'hard_cut'
    return initial
  })

  const setTransition = useCallback((idx, value) => {
    setClipTransitions((prev) => ({ ...prev, [String(idx)]: value }))
  }, [])

  // ── Text overlays state ───────────────────────────────────────────────────
  const [removeTextOverlays, setRemoveTextOverlays] = useState(false)
  const [newOverlayText,     setNewOverlayText]     = useState('')
  const [newTextOverlays,    setNewTextOverlays]    = useState([])

  const addOverlay = useCallback(() => {
    const text = newOverlayText.trim()
    if (!text) return
    setNewTextOverlays((prev) => [...prev, { text, position: 'bottom', size: 'medium' }])
    setNewOverlayText('')
  }, [newOverlayText])

  const removeOverlay = useCallback((idx) => {
    setNewTextOverlays((prev) => prev.filter((_, i) => i !== idx))
  }, [])

  // ── Submit ────────────────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const handleApply = useCallback(async () => {
    if (!videoJobId) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const payload = {
        brightness,
        contrast,
        saturation,
        lut_override:         lut || null,
        lut_intensity:        lutIntensity / 100,
        clip_transitions:     clipTransitions,
        remove_text_overlays: removeTextOverlays,
        new_text_overlays:    newTextOverlays,
      }
      const res = await fineTuneEdit(videoJobId, payload)
      const newJobId = res.data.job_id
      // Reset job state for the new re-render job
      setOutputUrl(null)
      setJobState({
        jobId:    newJobId,
        jobStatus: 'pending',
        jobProgress: 0,
        jobMessage: 'Starting fine-tune render...',
      })
      setScreen('processing')
    } catch (err) {
      setSubmitError(err.message)
    }
    setSubmitting(false)
  }, [
    videoJobId, brightness, contrast, saturation, lut, lutIntensity,
    clipTransitions, removeTextOverlays, newTextOverlays,
    setOutputUrl, setJobState, setScreen,
  ])

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 sm:px-6 py-4 border-b border-[#1e1e2e]">
        <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
          V
        </div>
        <h1 className="text-base sm:text-lg font-semibold text-slate-100 tracking-tight">
          Fine-Tune Editor
        </h1>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setScreen('preview')}
            className="px-3 py-1.5 text-xs sm:text-sm font-medium text-slate-400 hover:text-slate-200 border border-[#1e1e2e] hover:border-slate-600 rounded-lg transition-colors"
          >
            Back
          </button>
          <button
            onClick={handleApply}
            disabled={submitting || !videoJobId}
            className="px-4 py-1.5 text-xs sm:text-sm font-semibold bg-violet-600 hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors flex items-center gap-1.5"
          >
            {submitting ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                Applying...
              </>
            ) : (
              'Apply Changes'
            )}
          </button>
        </div>
      </header>

      <main className="flex-1 flex flex-col lg:flex-row gap-0 overflow-hidden">
        {/* Left: Video preview */}
        <div className="lg:w-[40%] xl:w-[45%] bg-black flex items-center justify-center p-4 lg:min-h-[calc(100vh-65px)]">
          {videoSrc ? (
            <video
              src={videoSrc}
              className="w-full max-h-[40vh] lg:max-h-[80vh] rounded-xl object-contain"
              controls
              playsInline
              loop
            />
          ) : (
            <div className="w-full aspect-video flex items-center justify-center bg-[#12121a] border border-[#1e1e2e] rounded-xl text-slate-600 text-sm">
              No video available
            </div>
          )}
        </div>

        {/* Right: Controls */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 flex flex-col gap-6 max-w-2xl lg:max-w-none mx-auto w-full">

          {/* Error */}
          {submitError && (
            <div className="px-4 py-3 rounded-xl bg-red-900/20 border border-red-800 text-sm text-red-400">
              {submitError}
            </div>
          )}

          {/* Color Grading */}
          <section className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl p-5">
            <SectionHeading>Color Grading</SectionHeading>
            <div className="flex flex-col gap-5">
              <SliderRow
                label="Brightness"
                value={brightness}
                min={-0.3}
                max={0.3}
                step={0.01}
                display={brightness > 0 ? `+${brightness.toFixed(2)}` : brightness.toFixed(2)}
                onChange={setBrightness}
              />
              <SliderRow
                label="Contrast"
                value={contrast}
                min={0.5}
                max={2.0}
                step={0.05}
                display={contrast.toFixed(2)}
                onChange={setContrast}
              />
              <SliderRow
                label="Saturation"
                value={saturation}
                min={0.5}
                max={2.0}
                step={0.05}
                display={saturation.toFixed(2)}
                onChange={setSaturation}
              />

              {/* LUT selector */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm text-slate-300">Color LUT</label>
                <select
                  value={lut}
                  onChange={(e) => setLut(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg text-slate-200 focus:outline-none focus:border-violet-600 transition-colors"
                >
                  {LUT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {lut && (
                <SliderRow
                  label="LUT Intensity"
                  value={lutIntensity}
                  min={0}
                  max={100}
                  step={1}
                  display={`${lutIntensity}%`}
                  onChange={setLutIntensity}
                />
              )}
            </div>
          </section>

          {/* Transitions */}
          <section className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl p-5">
            <SectionHeading>Transitions</SectionHeading>
            {gapCount === 0 ? (
              <p className="text-sm text-slate-500">Only one clip — no transitions to configure.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {Array.from({ length: gapCount }, (_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-xs text-slate-500 whitespace-nowrap min-w-[80px]">
                      Clip {i + 1} → {i + 2}
                    </span>
                    <select
                      value={clipTransitions[String(i)] || 'hard_cut'}
                      onChange={(e) => setTransition(i, e.target.value)}
                      className="flex-1 px-3 py-1.5 text-sm bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg text-slate-200 focus:outline-none focus:border-violet-600 transition-colors"
                    >
                      {TRANSITION_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Text Overlays */}
          <section className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl p-5">
            <SectionHeading>Text Overlays</SectionHeading>
            <div className="flex flex-col gap-4">
              {/* Toggle existing overlays */}
              <label className="flex items-center justify-between gap-3 cursor-pointer select-none">
                <span className="text-sm text-slate-300">Hide existing text overlays</span>
                <button
                  role="switch"
                  aria-checked={removeTextOverlays}
                  onClick={() => setRemoveTextOverlays((v) => !v)}
                  className={`relative inline-flex w-10 h-5 rounded-full transition-colors duration-200 ${removeTextOverlays ? 'bg-violet-600' : 'bg-[#1e1e2e]'}`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${removeTextOverlays ? 'translate-x-5' : 'translate-x-0'}`}
                  />
                </button>
              </label>

              {/* Add new overlay */}
              <div>
                <p className="text-xs text-slate-500 mb-2">Add new text overlay</p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newOverlayText}
                    onChange={(e) => setNewOverlayText(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && addOverlay()}
                    placeholder="Enter text..."
                    className="flex-1 px-3 py-2 text-sm bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600 transition-colors"
                  />
                  <button
                    onClick={addOverlay}
                    disabled={!newOverlayText.trim()}
                    className="px-3 py-2 text-sm bg-violet-700 hover:bg-violet-600 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors"
                  >
                    Add
                  </button>
                </div>
              </div>

              {/* List added overlays */}
              {newTextOverlays.length > 0 && (
                <ul className="flex flex-col gap-2">
                  {newTextOverlays.map((ov, idx) => (
                    <li
                      key={idx}
                      className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#0a0a0f] border border-[#1e1e2e]"
                    >
                      <span className="text-sm text-slate-300 truncate">{ov.text}</span>
                      <button
                        onClick={() => removeOverlay(idx)}
                        className="ml-3 w-6 h-6 flex items-center justify-center rounded-full text-slate-500 hover:text-red-400 hover:bg-red-900/20 transition-colors shrink-0"
                        aria-label="Remove overlay"
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          {/* Bottom apply button (mobile-friendly) */}
          <div className="pb-6 lg:hidden">
            <button
              onClick={handleApply}
              disabled={submitting || !videoJobId}
              className="w-full py-3 rounded-xl font-semibold text-sm bg-violet-600 hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Applying...
                </>
              ) : (
                'Apply Changes'
              )}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
