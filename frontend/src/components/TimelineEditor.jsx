import React, { useState, useCallback, useEffect } from 'react'
import useEditStore from '../stores/editStore.js'
import { getHistoryEdl, fineTuneEdit, getTransitions } from '../api/client.js'

const TRANSITION_CATEGORIES_FALLBACK = {
  Basic:     ['hard_cut', 'dissolve', 'fade', 'fade_black', 'fade_white'],
  Slides:    ['wipe_left', 'wipe_right', 'slide_left', 'slide_right'],
  Zooms:     ['zoom_in', 'zoom_out'],
  Stylized:  ['glitch', 'flash', 'spin', 'pixelate', 'circle_open'],
}

function ClipBlock({ clip, index, total, selected, onSelect, onMoveLeft, onMoveRight, onRemove }) {
  const dur = (parseFloat(clip.source_out || 5) - parseFloat(clip.source_in || 0)).toFixed(1)
  const isFirst = index === 0
  const isLast = index === total - 1

  return (
    <div
      onClick={() => onSelect(index)}
      className={`
        relative flex flex-col gap-1 px-3 py-2 rounded-lg border cursor-pointer select-none
        transition-all duration-150 min-w-[120px] max-w-[160px] shrink-0
        ${selected
          ? 'border-violet-500 bg-violet-900/30 ring-1 ring-violet-500/40'
          : 'border-[#1e1e2e] bg-[#12121a] hover:border-violet-700'
        }
      `}
    >
      <span className="text-xs font-semibold text-slate-200 truncate">
        {clip.source_file || `Clip ${index + 1}`}
      </span>
      <span className="text-xs text-slate-500">{dur}s</span>
      {clip.notes && (
        <span className="text-xs text-slate-600 truncate italic">{clip.notes}</span>
      )}

      {selected && (
        <div className="flex items-center gap-1 mt-1">
          <button
            onClick={(e) => { e.stopPropagation(); onMoveLeft(index) }}
            disabled={isFirst}
            className="flex-1 py-0.5 rounded text-xs bg-[#1e1e2e] text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Move left"
          >
            ←
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onMoveRight(index) }}
            disabled={isLast}
            className="flex-1 py-0.5 rounded text-xs bg-[#1e1e2e] text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Move right"
          >
            →
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onRemove(index) }}
            className="flex-1 py-0.5 rounded text-xs bg-[#1e1e2e] text-red-500 hover:text-red-300 transition-colors"
            title="Remove"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  )
}

function TransitionBadge({ transition, clipIndex, onChange, categories }) {
  const [open, setOpen] = useState(false)
  const type = transition?.type || 'hard_cut'
  const label = type === 'hard_cut' ? '|' : type.replace(/_/g, ' ')
  const cats = categories || TRANSITION_CATEGORIES_FALLBACK

  return (
    <div className="relative flex items-center justify-center w-16 shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="px-1.5 py-0.5 rounded text-xs bg-[#1e1e2e] border border-[#2e2e3e] text-slate-500 hover:text-violet-300 hover:border-violet-700 transition-colors truncate max-w-[60px]"
        title={`Transition: ${type}`}
      >
        {label}
      </button>

      {open && (
        <div className="absolute top-7 left-1/2 -translate-x-1/2 z-50 w-44 bg-[#12121a] border border-[#1e1e2e] rounded-xl shadow-2xl overflow-hidden max-h-72 overflow-y-auto">
          {Object.entries(cats).map(([catName, items]) => (
            <div key={catName}>
              <div className="px-3 py-1 text-xs text-slate-600 font-semibold uppercase tracking-wider bg-[#0d0d14] sticky top-0">
                {catName}
              </div>
              {(Array.isArray(items)
                ? items.map((t) => ({ id: t, label: t.replace(/_/g, ' ') }))
                : items
              ).map((item) => {
                const id = item.id || item
                const itemLabel = item.label || id.replace(/_/g, ' ')
                return (
                  <button
                    key={id}
                    onClick={() => { onChange(clipIndex, id); setOpen(false) }}
                    className={`w-full px-3 py-1.5 text-left text-xs transition-colors hover:bg-violet-900/30 ${
                      id === type ? 'text-violet-300 bg-violet-900/20' : 'text-slate-400'
                    }`}
                  >
                    {itemLabel}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function TimelineEditor({ onClose }) {
  const { jobId, fineTuneJobId, setScreen, setJobState } = useEditStore()
  const sourceJobId = fineTuneJobId || jobId

  const [clips, setClips]             = useState([])
  const [transitions, setTransitions] = useState([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)
  const [selectedIdx, setSelectedIdx] = useState(null)
  const [applying, setApplying]       = useState(false)
  const [applyError, setApplyError]   = useState(null)
  const [transitionCats, setTransitionCats] = useState(null)

  useEffect(() => {
    getTransitions()
      .then((r) => setTransitionCats(r.data?.categories || null))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!sourceJobId) { setLoading(false); setError('No active job'); return }
    let cancelled = false
    getHistoryEdl(sourceJobId)
      .then((r) => {
        if (cancelled) return
        const edl = r.data
        setClips(edl.clips || [])
        const ts = (edl.clips || []).slice(0, -1).map((c) => c.transition_out || { type: 'hard_cut', duration: 0.5 })
        setTransitions(ts)
        setLoading(false)
      })
      .catch((e) => {
        if (!cancelled) { setError(e.message); setLoading(false) }
      })
    return () => { cancelled = true }
  }, [sourceJobId])

  const handleMoveLeft = useCallback((i) => {
    if (i === 0) return
    setClips((prev) => { const a = [...prev]; [a[i - 1], a[i]] = [a[i], a[i - 1]]; return a })
    setTransitions((prev) => { const a = [...prev]; if (i - 1 < a.length) [a[i - 2], a[i - 1]] = [a[i - 1] ?? a[i - 2], a[i - 2] ?? a[i - 1]]; return a })
    setSelectedIdx(i - 1)
  }, [])

  const handleMoveRight = useCallback((i) => {
    setClips((prev) => { if (i >= prev.length - 1) return prev; const a = [...prev]; [a[i], a[i + 1]] = [a[i + 1], a[i]]; return a })
    setTransitions((prev) => { const a = [...prev]; if (i < a.length) [a[i], a[i + 1]] = [a[i + 1] ?? a[i], a[i] ?? a[i + 1]]; return a })
    setSelectedIdx(i + 1)
  }, [])

  const handleRemove = useCallback((i) => {
    setClips((prev) => prev.filter((_, idx) => idx !== i))
    setTransitions((prev) => prev.filter((_, idx) => idx !== i && idx !== i - 1).slice(0, clips.length - 2))
    setSelectedIdx(null)
  }, [clips.length])

  const handleTransitionChange = useCallback((clipIndex, newType) => {
    setTransitions((prev) => {
      const a = [...prev]
      a[clipIndex] = { type: newType, duration: 0.5 }
      return a
    })
  }, [])

  const handleApply = useCallback(async () => {
    if (!sourceJobId) return
    setApplying(true)
    setApplyError(null)
    try {
      // Build clip_transitions map: index → transition type
      const clipTransitions = {}
      transitions.forEach((t, i) => { clipTransitions[String(i)] = t.type })

      const res = await fineTuneEdit(sourceJobId, {
        clip_transitions: clipTransitions,
        lut_intensity: 0.85,
        brightness: 0,
        contrast: 1,
        saturation: 1,
      })
      const newJobId = res.data.job_id
      setJobState({ jobId: newJobId, jobStatus: 'pending', jobProgress: 0, jobMessage: 'Re-rendering...' })
      setScreen('processing')
      onClose?.()
    } catch (e) {
      setApplyError(e.message)
    }
    setApplying(false)
  }, [sourceJobId, transitions, setJobState, setScreen, onClose])

  const totalDuration = clips.reduce((s, c) => s + Math.max(0, parseFloat(c.source_out || 5) - parseFloat(c.source_in || 0)), 0)

  return (
    <div className="flex flex-col gap-4 bg-[#0d0d14] border border-[#1e1e2e] rounded-2xl p-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Timeline Editor</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {clips.length} clips · ~{totalDuration.toFixed(1)}s total
          </p>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">
            ×
          </button>
        )}
      </div>

      {/* Content */}
      {loading && (
        <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
          Loading timeline...
        </div>
      )}

      {error && (
        <p className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {!loading && !error && clips.length > 0 && (
        <>
          {/* Clip track */}
          <div className="overflow-x-auto pb-2">
            <div className="flex items-start gap-0 min-w-max">
              {clips.map((clip, i) => (
                <React.Fragment key={`${clip.clip_id || i}-${i}`}>
                  <ClipBlock
                    clip={clip}
                    index={i}
                    total={clips.length}
                    selected={selectedIdx === i}
                    onSelect={setSelectedIdx}
                    onMoveLeft={handleMoveLeft}
                    onMoveRight={handleMoveRight}
                    onRemove={handleRemove}
                  />
                  {i < clips.length - 1 && (
                    <TransitionBadge
                      transition={transitions[i]}
                      clipIndex={i}
                      onChange={handleTransitionChange}
                      categories={transitionCats}
                    />
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>

          <p className="text-xs text-slate-600">
            Click a clip to select it, then use ← → to reorder or ✕ to remove. Click the transition label to change it.
          </p>
        </>
      )}

      {!loading && !error && clips.length === 0 && (
        <p className="text-sm text-slate-500 text-center py-6">No clips in this edit.</p>
      )}

      {/* Footer actions */}
      {!loading && !error && clips.length > 0 && (
        <div className="flex items-center gap-3 pt-2 border-t border-[#1e1e2e]">
          {applyError && (
            <p className="text-xs text-red-400 flex-1">{applyError}</p>
          )}
          <div className="flex gap-2 ml-auto">
            {onClose && (
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm rounded-lg border border-[#1e1e2e] text-slate-400 hover:text-slate-200 hover:border-violet-700 transition-colors"
              >
                Cancel
              </button>
            )}
            <button
              onClick={handleApply}
              disabled={applying}
              className="px-4 py-2 text-sm rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-medium transition-colors flex items-center gap-1.5"
            >
              {applying ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Re-rendering...
                </>
              ) : (
                'Apply Changes'
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
