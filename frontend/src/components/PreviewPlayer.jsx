import React, { useRef, useState, useCallback, useEffect } from 'react'
import useEditStore from '../stores/editStore.js'
import { getHistory } from '../api/client.js'

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function styleName(id) {
  const map = {
    cinematic_travel:    'Cinematic Travel',
    genz_fast_edit:      'Gen Z Fast Edit',
    dark_moody:          'Dark & Moody',
    warm_aesthetic:      'Warm Aesthetic',
    vintage_film:        'Vintage Film',
    art_showcase:        'Art Showcase',
    energy_action:       'Energy / Action',
    minimal_slideshow:   'Minimal Slideshow',
    __match_reference__: 'Reference Match',
  }
  return map[id] || id
}

// ─── History Popover ──────────────────────────────────────────────────────────
function HistoryPopover({ onClose }) {
  const [items,   setItems]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    let cancelled = false
    getHistory()
      .then((res) => {
        if (!cancelled) {
          setItems(res.data?.history || res.data || [])
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message)
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [])

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="absolute top-14 right-4 sm:right-6 w-72 bg-[#12121a] border border-[#1e1e2e] rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e1e2e]">
          <span className="text-sm font-semibold text-slate-200">Recent Edits</span>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">&times;</button>
        </div>
        <div className="max-h-72 overflow-y-auto">
          {loading && (
            <div className="px-4 py-6 text-center text-sm text-slate-500">Loading...</div>
          )}
          {error && (
            <div className="px-4 py-6 text-center text-sm text-red-400">{error}</div>
          )}
          {!loading && !error && items.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-slate-500">No history yet.</div>
          )}
          {!loading && !error && items.map((item, idx) => (
            <div key={item.job_id || idx} className="flex items-center justify-between px-4 py-3 border-b border-[#1e1e2e] last:border-0 hover:bg-[#1e1e2e] transition-colors">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-slate-200 truncate">
                  {item.title || item.style || `Job ${item.job_id}`}
                </p>
                <p className="text-xs text-slate-600 mt-0.5">
                  {item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}
                </p>
              </div>
              {item.job_id && (
                <a
                  href={`/api/job/${item.job_id}/result`}
                  download
                  className="ml-3 shrink-0 text-xs text-violet-400 hover:text-violet-300 underline"
                >
                  Download
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function PreviewPlayer() {
  const {
    jobId,
    outputUrl,
    clips,
    selectedStyle,
    targetDuration,
    aspectRatio,
    reset,
    setScreen,
    setFineTuneJobId,
  } = useEditStore()

  const videoRef = useRef(null)
  const [playing,       setPlaying]       = useState(false)
  const [currentTime,   setCurrentTime]   = useState(0)
  const [duration,      setDuration]      = useState(0)
  const [videoError,    setVideoError]    = useState(null)
  const [historyOpen,   setHistoryOpen]   = useState(false)

  const videoSrc  = outputUrl || (jobId ? `/api/job/${jobId}/result` : null)
  const downloadUrl = jobId ? `/api/job/${jobId}/result` : outputUrl

  const handlePlayPause = useCallback(() => {
    const vid = videoRef.current
    if (!vid) return
    if (vid.paused) {
      vid.play().catch(() => {})
      setPlaying(true)
    } else {
      vid.pause()
      setPlaying(false)
    }
  }, [])

  const handleTimeUpdate = useCallback(() => {
    const vid = videoRef.current
    if (!vid) return
    setCurrentTime(vid.currentTime)
  }, [])

  const handleLoadedMetadata = useCallback(() => {
    const vid = videoRef.current
    if (!vid) return
    setDuration(vid.duration)
  }, [])

  const handleEnded = useCallback(() => {
    setPlaying(false)
  }, [])

  const handleSeek = useCallback((e) => {
    const vid = videoRef.current
    if (!vid || !duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const pct = Math.max(0, Math.min(1, x / rect.width))
    vid.currentTime = pct * duration
    setCurrentTime(pct * duration)
  }, [duration])

  const handleAdjustColors = useCallback(() => {
    setFineTuneJobId(jobId)
    setScreen('finetune')
  }, [jobId, setFineTuneJobId, setScreen])

  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0

  // Aspect ratio class for the video container
  const ratioClass =
    aspectRatio === '9:16'
      ? 'aspect-[9/16] max-h-[70vh]'
      : aspectRatio === '1:1'
      ? 'aspect-square max-h-[60vh]'
      : 'aspect-video'

  const estimatedCuts = Math.max(1, Math.floor(targetDuration / 3))

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex flex-col">
      {/* Header — minimal since TopNav handles global nav */}
      <header className="flex items-center gap-3 px-4 sm:px-6 py-4 border-b border-[#1e1e2e]">
        <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-emerald-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          Edit complete
        </span>
        <button
          onClick={() => setHistoryOpen(true)}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          History
        </button>
      </header>

      <main className="flex-1 flex flex-col items-center px-4 py-6 sm:py-8 gap-6">
        <div className="w-full max-w-2xl flex flex-col gap-6">
          {/* Video player */}
          <div className={`relative mx-auto w-full ${ratioClass} bg-black rounded-2xl overflow-hidden border border-[#1e1e2e] shadow-2xl shadow-black/60`}>
            {videoSrc ? (
              <video
                ref={videoRef}
                src={videoSrc}
                className="w-full h-full object-contain"
                loop
                playsInline
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={handleLoadedMetadata}
                onEnded={handleEnded}
                onError={() => setVideoError('Failed to load video. The file may still be processing.')}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-slate-600 text-sm">
                No video available
              </div>
            )}

            {/* Play overlay (shown when paused) */}
            {!playing && videoSrc && !videoError && (
              <button
                onClick={handlePlayPause}
                className="absolute inset-0 flex items-center justify-center group"
                aria-label="Play"
              >
                <div className="w-16 h-16 rounded-full bg-white/20 backdrop-blur-sm group-hover:bg-white/30 flex items-center justify-center transition-all">
                  <svg className="w-7 h-7 text-white ml-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M6.3 2.841A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" clipRule="evenodd" />
                  </svg>
                </div>
              </button>
            )}

            {videoError && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 text-center p-6">
                <p className="text-red-400 text-sm mb-2">{videoError}</p>
                <button
                  onClick={() => {
                    setVideoError(null)
                    if (videoRef.current) videoRef.current.load()
                  }}
                  className="text-xs text-violet-400 underline"
                >
                  Retry
                </button>
              </div>
            )}
          </div>

          {/* Custom controls */}
          {videoSrc && !videoError && (
            <div className="flex flex-col gap-2 px-1">
              {/* Seek bar */}
              <div
                className="w-full h-1.5 bg-[#1e1e2e] rounded-full cursor-pointer group relative"
                onClick={handleSeek}
              >
                <div
                  className="h-full rounded-full bg-violet-500 transition-all duration-100"
                  style={{ width: `${progressPct}%` }}
                />
                <div
                  className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-violet-400 shadow opacity-0 group-hover:opacity-100 transition-opacity -translate-x-1/2"
                  style={{ left: `${progressPct}%` }}
                />
              </div>

              {/* Controls row */}
              <div className="flex items-center gap-3">
                <button
                  onClick={handlePlayPause}
                  className="w-8 h-8 rounded-lg bg-[#12121a] border border-[#1e1e2e] hover:border-violet-600 flex items-center justify-center text-slate-300 hover:text-white transition-colors"
                  aria-label={playing ? 'Pause' : 'Play'}
                >
                  {playing ? (
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M6.3 2.841A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" clipRule="evenodd" />
                    </svg>
                  )}
                </button>
                <span className="text-xs text-slate-500 tabular-nums">
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
              </div>
            </div>
          )}

          {/* Edit summary */}
          <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl px-4 py-3">
            <p className="text-xs text-slate-400 font-medium mb-1">Edit summary</p>
            <p className="text-sm text-slate-200">
              {clips.length} clip{clips.length !== 1 ? 's' : ''} •{' '}
              ~{estimatedCuts} cuts •{' '}
              {styleName(selectedStyle)} •{' '}
              {targetDuration}s •{' '}
              {aspectRatio}
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex flex-col gap-3">
            {/* Download */}
            <a
              href={downloadUrl}
              download="visai-edit-1080p.mp4"
              className={`
                flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-colors
                ${downloadUrl
                  ? 'bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-900/40 cursor-pointer'
                  : 'bg-[#1e1e2e] text-slate-600 cursor-not-allowed pointer-events-none'
                }
              `}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download 1080p
            </a>

            {/* Secondary actions */}
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setScreen('style')}
                className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-sm font-medium bg-[#12121a] border border-[#1e1e2e] text-slate-300 hover:border-violet-700 hover:text-slate-100 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Different Style
              </button>
              <button
                onClick={handleAdjustColors}
                className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-sm font-medium bg-[#12121a] border border-[#1e1e2e] text-slate-300 hover:border-violet-700 hover:text-slate-100 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
                </svg>
                Adjust Colors
              </button>
            </div>

            {/* Start new edit */}
            <button
              onClick={reset}
              className="py-2.5 rounded-xl text-sm font-medium text-slate-500 hover:text-slate-300 transition-colors border border-transparent hover:border-[#1e1e2e]"
            >
              Start New Edit
            </button>
          </div>
        </div>
      </main>

      {/* History popover */}
      {historyOpen && <HistoryPopover onClose={() => setHistoryOpen(false)} />}
    </div>
  )
}
