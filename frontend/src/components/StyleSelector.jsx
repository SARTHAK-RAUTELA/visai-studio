import React, { useState, useCallback } from 'react'
import useEditStore from '../stores/editStore.js'
import { analyzeReference, getReferenceResult, generateEdit } from '../api/client.js'
import StyleDNACard from './StyleDNACard.jsx'

// ─── Style definitions ────────────────────────────────────────────────────────
const STYLES = [
  {
    id: 'cinematic_travel',
    emoji: '🌄',
    name: 'Cinematic Travel',
    desc: 'Long, breathing shots. Teal-orange grade. Let the landscape speak.',
  },
  {
    id: 'genz_fast_edit',
    emoji: '⚡',
    name: 'Gen Z Fast Edit',
    desc: 'Every beat gets a cut. Viral energy. Punchy and surprising.',
  },
  {
    id: 'dark_moody',
    emoji: '🖤',
    name: 'Dark & Moody',
    desc: 'Atmospheric, cinematic. Each frame like a still from an arthouse film.',
  },
  {
    id: 'warm_aesthetic',
    emoji: '☀️',
    name: 'Warm Aesthetic',
    desc: 'Golden, warm, inviting. Like a memory. Lifestyle that makes you feel at home.',
  },
  {
    id: 'vintage_film',
    emoji: '🎞️',
    name: 'Vintage Film',
    desc: 'Old film, grain, nostalgia. Analog warmth, imperfect beauty.',
  },
  {
    id: 'art_showcase',
    emoji: '🎨',
    name: 'Art Showcase',
    desc: 'Gallery quality. Slow, deliberate reveals. The art is the star.',
  },
  {
    id: 'energy_action',
    emoji: '🏃',
    name: 'Energy / Action',
    desc: 'Maximum energy. Sports, gym, action. Every cut feels like a punch.',
  },
  {
    id: 'minimal_slideshow',
    emoji: '🌙',
    name: 'Minimal Slideshow',
    desc: 'Soft, gentle, memory-like. Photo album feel. Each moment breathes.',
  },
]

const DURATIONS = [15, 30, 60, 90]
const RATIOS = ['9:16', '16:9', '1:1']

// ─── Spinner ──────────────────────────────────────────────────────────────────
function Spinner({ size = 'sm' }) {
  const cls = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5'
  return (
    <svg className={`${cls} animate-spin text-violet-400`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

// ─── Style Card ───────────────────────────────────────────────────────────────
function StyleCard({ style, selected, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`
        group relative flex flex-col gap-1.5 p-4 rounded-xl border text-left transition-all duration-150
        ${selected
          ? 'border-violet-500 bg-violet-900/30 ring-1 ring-violet-500/60'
          : 'border-[#1e1e2e] bg-[#12121a] hover:border-violet-700 hover:bg-violet-900/10'
        }
      `}
    >
      <span className="text-2xl">{style.emoji}</span>
      <span className={`text-sm font-semibold ${selected ? 'text-violet-300' : 'text-slate-200'}`}>
        {style.name}
      </span>
      <span className="text-xs text-slate-500 leading-relaxed line-clamp-2">{style.desc}</span>
      {selected && (
        <span className="absolute top-2 right-2 w-4 h-4 rounded-full bg-violet-500 flex items-center justify-center">
          <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      )}
    </button>
  )
}

// ─── Toggle Button ────────────────────────────────────────────────────────────
function ToggleButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`
        px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-150
        ${active
          ? 'bg-violet-600 text-white shadow-md shadow-violet-900/40'
          : 'bg-[#12121a] border border-[#1e1e2e] text-slate-400 hover:border-violet-700 hover:text-slate-200'
        }
      `}
    >
      {children}
    </button>
  )
}

// ─── Toggle Switch ────────────────────────────────────────────────────────────
function ToggleSwitch({ checked, onChange, label }) {
  return (
    <label className="flex items-center justify-between gap-3 cursor-pointer select-none">
      <span className="text-sm text-slate-300">{label}</span>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`
          relative inline-flex w-10 h-5 rounded-full transition-colors duration-200
          ${checked ? 'bg-violet-600' : 'bg-[#1e1e2e]'}
        `}
      >
        <span
          className={`
            absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200
            ${checked ? 'translate-x-5' : 'translate-x-0'}
          `}
        />
      </button>
    </label>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function StyleSelector() {
  const {
    reference,
    clips,
    audio,
    selectedStyle,
    targetDuration,
    aspectRatio,
    autoCaptions,
    soundFx,
    lutIntensity,
    styleDnaId,
    styleDna,
    refAnalysisStatus,
    setSelectedStyle,
    setTargetDuration,
    setAspectRatio,
    setAdvanced,
    setScreen,
    setJobState,
    setStyleDna,
    setRefAnalysisStatus,
  } = useEditStore()

  const [showAdvanced, setShowAdvanced] = useState(false)
  const [generateError, setGenerateError] = useState(null)
  const [generating, setGenerating] = useState(false)

  // ── Reference analysis ────────────────────────────────────────────────────
  const handleSelectMatchReference = useCallback(async () => {
    if (!reference) return
    setSelectedStyle('__match_reference__')

    if (refAnalysisStatus === 'done') return // already analyzed
    if (refAnalysisStatus === 'analyzing') return // in progress

    setRefAnalysisStatus('analyzing')
    try {
      const startRes = await analyzeReference({
        reference_type: 'file',
        or_file_id: reference.id,
      })
      const refId = startRes.data.ref_id

      // Poll until complete
      let attempts = 0
      const MAX_ATTEMPTS = 120 // 2 minutes @ 1s intervals
      const poll = async () => {
        attempts++
        const statusRes = await getReferenceResult(refId)
        const data = statusRes.data
        if (data.status === 'complete') {
          setStyleDna(data, refId)
          setRefAnalysisStatus('done')
        } else if (data.status === 'failed') {
          setRefAnalysisStatus('failed')
        } else if (attempts < MAX_ATTEMPTS) {
          setTimeout(poll, 1000)
        } else {
          setRefAnalysisStatus('failed')
        }
      }
      await poll()
    } catch (err) {
      setRefAnalysisStatus('failed')
    }
  }, [reference, refAnalysisStatus, setRefAnalysisStatus, setStyleDna])

  // ── Generate ──────────────────────────────────────────────────────────────
  const handleGenerate = useCallback(async () => {
    setGenerateError(null)
    setGenerating(true)
    try {
      const payload = {
        clip_ids: clips.map((c) => c.id),
        audio_id: audio?.id,
        style:
          selectedStyle === '__match_reference__'
            ? null
            : selectedStyle,
        style_dna_id:
          selectedStyle === '__match_reference__' ? styleDnaId : null,
        target_duration: targetDuration,
        aspect_ratio: aspectRatio,
        auto_captions: autoCaptions,
        sound_fx: soundFx,
        lut_intensity: lutIntensity,
      }
      const res = await generateEdit(payload)
      const jobId = res.data.job_id
      setJobState({ jobId, jobStatus: 'pending', jobProgress: 0, jobMessage: 'Starting...' })
      setScreen('processing')
    } catch (err) {
      setGenerateError(err.message)
    }
    setGenerating(false)
  }, [
    clips,
    audio,
    selectedStyle,
    styleDnaId,
    targetDuration,
    aspectRatio,
    autoCaptions,
    soundFx,
    lutIntensity,
    setJobState,
    setScreen,
  ])

  const isMatchRef = selectedStyle === '__match_reference__'
  const matchRefReady = isMatchRef && refAnalysisStatus === 'done'
  const canGenerate =
    (selectedStyle !== '__match_reference__' || matchRefReady) &&
    !generating

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 sm:px-6 py-4 border-b border-[#1e1e2e]">
        <h1 className="text-base font-semibold text-slate-300 tracking-tight">Choose Style</h1>
        <button
          onClick={() => setScreen('upload')}
          className="ml-auto text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          ← Back
        </button>
      </header>

      <main className="flex-1 flex flex-col items-center px-4 py-6 sm:py-10">
        <div className="w-full max-w-3xl flex flex-col gap-6 sm:gap-8">
          <div className="text-center">
            <h2 className="text-3xl font-bold text-slate-100 mb-2">Choose your edit style</h2>
            <p className="text-slate-400 text-sm">
              Select a preset or match the style of your reference video.
            </p>
          </div>

          {/* Style grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {STYLES.map((s) => (
              <StyleCard
                key={s.id}
                style={s}
                selected={selectedStyle === s.id}
                onClick={() => setSelectedStyle(s.id)}
              />
            ))}
          </div>

          {/* Match reference option */}
          {reference && (
            <div className="flex flex-col gap-3">
              <button
                onClick={handleSelectMatchReference}
                className={`
                  flex items-center gap-3 p-4 rounded-xl border text-left transition-all duration-150
                  ${isMatchRef
                    ? 'border-violet-500 bg-violet-900/30 ring-1 ring-violet-500/60'
                    : 'border-[#1e1e2e] bg-[#12121a] hover:border-violet-700 hover:bg-violet-900/10'
                  }
                `}
              >
                <span className="text-2xl">🎯</span>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-semibold ${isMatchRef ? 'text-violet-300' : 'text-slate-200'}`}>
                    Match Reference Style
                  </p>
                  <p className="text-xs text-slate-500 truncate">
                    {reference.name}
                  </p>
                </div>
                {refAnalysisStatus === 'analyzing' && <Spinner />}
                {refAnalysisStatus === 'done' && (
                  <span className="text-xs text-emerald-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
                    Ready
                  </span>
                )}
                {refAnalysisStatus === 'failed' && (
                  <span className="text-xs text-red-400">Failed</span>
                )}
              </button>

              {/* Style DNA card */}
              {styleDna && isMatchRef && (
                <StyleDNACard dna={styleDna} />
              )}
              {refAnalysisStatus === 'analyzing' && isMatchRef && (
                <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-[#12121a] border border-[#1e1e2e]">
                  <Spinner size="md" />
                  <div>
                    <p className="text-sm text-slate-200">Analyzing reference video...</p>
                    <p className="text-xs text-slate-500">Extracting Style DNA — this takes ~15–30 seconds</p>
                  </div>
                </div>
              )}
              {refAnalysisStatus === 'failed' && isMatchRef && (
                <p className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
                  Reference analysis failed. Please try again or select a built-in style.
                </p>
              )}
            </div>
          )}

          {/* Settings */}
          <div className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl p-5 flex flex-col gap-5">
            {/* Duration */}
            <div>
              <p className="text-sm font-medium text-slate-300 mb-2">Target duration</p>
              <div className="flex gap-2 flex-wrap">
                {DURATIONS.map((d) => (
                  <ToggleButton
                    key={d}
                    active={targetDuration === d}
                    onClick={() => setTargetDuration(d)}
                  >
                    {d}s
                  </ToggleButton>
                ))}
              </div>
            </div>

            {/* Aspect ratio */}
            <div>
              <p className="text-sm font-medium text-slate-300 mb-2">Aspect ratio</p>
              <div className="flex gap-2">
                {RATIOS.map((r) => (
                  <ToggleButton
                    key={r}
                    active={aspectRatio === r}
                    onClick={() => setAspectRatio(r)}
                  >
                    {r === '9:16' ? '9:16 Reels' : r === '16:9' ? '16:9 YouTube' : '1:1 Feed'}
                  </ToggleButton>
                ))}
              </div>
            </div>

            {/* Advanced toggle */}
            <button
              onClick={() => setShowAdvanced((v) => !v)}
              className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors w-fit"
            >
              <span className={`transition-transform duration-200 ${showAdvanced ? 'rotate-180' : ''}`}>
                ▾
              </span>
              Advanced options
            </button>

            {showAdvanced && (
              <div className="flex flex-col gap-4 pt-2 border-t border-[#1e1e2e]">
                {/* LUT intensity */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium text-slate-300">Color intensity</p>
                    <span className="text-sm text-violet-400 font-medium">
                      {Math.round(lutIntensity * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={Math.round(lutIntensity * 100)}
                    onChange={(e) =>
                      setAdvanced({ lutIntensity: Number(e.target.value) / 100 })
                    }
                    className="w-full h-1.5 rounded-full appearance-none bg-[#1e1e2e] accent-violet-600 cursor-pointer"
                  />
                  <div className="flex justify-between text-xs text-slate-600 mt-1">
                    <span>Subtle</span>
                    <span>Full</span>
                  </div>
                </div>

                <ToggleSwitch
                  checked={autoCaptions}
                  onChange={(v) => setAdvanced({ autoCaptions: v })}
                  label="Auto-captions (Whisper AI)"
                />

                <ToggleSwitch
                  checked={soundFx}
                  onChange={(v) => setAdvanced({ soundFx: v })}
                  label="Sound FX (whoosh, impact)"
                />
              </div>
            )}
          </div>

          {/* Error */}
          {generateError && (
            <p className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-4 py-3">
              {generateError}
            </p>
          )}

          {/* Generate button */}
          <div className="flex flex-col items-center gap-3">
            <button
              disabled={!canGenerate}
              onClick={handleGenerate}
              className={`
                w-full max-w-xs py-3 rounded-xl font-semibold text-base transition-all duration-200 flex items-center justify-center gap-2
                ${canGenerate
                  ? 'bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-900/40 cursor-pointer'
                  : 'bg-[#1e1e2e] text-slate-600 cursor-not-allowed'
                }
              `}
            >
              {generating ? (
                <>
                  <Spinner />
                  Starting...
                </>
              ) : (
                'Generate Edit →'
              )}
            </button>
            {isMatchRef && refAnalysisStatus !== 'done' && refAnalysisStatus !== 'idle' && (
              <p className="text-xs text-slate-600">
                Waiting for reference analysis to complete...
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
