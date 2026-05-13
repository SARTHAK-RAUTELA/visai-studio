import React, { useState, useEffect, useCallback, useRef } from 'react'
import useEditStore from '../stores/editStore.js'
import { startBatch, getBatchStatus } from '../api/client.js'

// ─── Constants ────────────────────────────────────────────────────────────────
const MAX_JOBS = 10

const STYLES = [
  { id: 'cinematic_travel', label: 'Cinematic Travel' },
  { id: 'genz_fast_edit',   label: 'Gen Z Fast Edit' },
  { id: 'dark_moody',       label: 'Dark & Moody' },
  { id: 'warm_aesthetic',   label: 'Warm Aesthetic' },
  { id: 'vintage_film',     label: 'Vintage Film' },
  { id: 'art_showcase',     label: 'Art Showcase' },
  { id: 'energy_action',    label: 'Energy / Action' },
  { id: 'minimal_slideshow', label: 'Minimal Slideshow' },
]

const DURATIONS  = [15, 30, 60, 90]
const RATIOS     = ['9:16', '16:9', '1:1']

const STATUS_COLORS = {
  queued:     'text-slate-400 bg-slate-900/40 border-slate-700',
  processing: 'text-violet-400 bg-violet-900/30 border-violet-700',
  complete:   'text-emerald-400 bg-emerald-900/20 border-emerald-700',
  failed:     'text-red-400 bg-red-900/20 border-red-700',
}

// ─── Status Chip ──────────────────────────────────────────────────────────────
function StatusChip({ status }) {
  const cls = STATUS_COLORS[status] || STATUS_COLORS.queued
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {status}
    </span>
  )
}

// ─── Job Row ──────────────────────────────────────────────────────────────────
function JobRow({ job }) {
  const downloadUrl = job.status === 'complete' && job.id
    ? `/api/job/${job.id}/result`
    : null

  return (
    <div className="flex flex-col gap-2 p-3 rounded-xl bg-[#0a0a0f] border border-[#1e1e2e]">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium text-slate-200 truncate flex-1">
          {job.style || 'Unknown style'}
        </span>
        <StatusChip status={job.status} />
      </div>

      <div className="flex items-center gap-3 flex-wrap text-xs text-slate-500">
        <span>{job.duration}s</span>
        <span>{job.aspectRatio}</span>
        {downloadUrl && (
          <a
            href={downloadUrl}
            download="visai-batch.mp4"
            className="ml-auto text-violet-400 hover:text-violet-300 underline transition-colors"
          >
            Download
          </a>
        )}
      </div>

      {(job.status === 'processing' || job.status === 'queued') && (
        <div className="w-full h-1 bg-[#1e1e2e] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out bg-violet-600"
            style={{ width: `${job.progress || 0}%` }}
          />
        </div>
      )}
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function BatchQueue() {
  const {
    clips,
    audio,
    batchJobs,
    addBatchJob,
    updateBatchJob,
    setScreen,
  } = useEditStore()

  // Form state
  const [formStyle,    setFormStyle]    = useState('cinematic_travel')
  const [formDuration, setFormDuration] = useState(30)
  const [formRatio,    setFormRatio]    = useState('9:16')
  const [showForm,     setShowForm]     = useState(false)
  const [addError,     setAddError]     = useState(null)
  const [adding,       setAdding]       = useState(false)

  // Polling refs
  const pollTimers = useRef({})

  // ── Poll a single job ─────────────────────────────────────────────────────
  const pollJob = useCallback(async (id) => {
    try {
      const res = await getBatchStatus(id)
      const data = res.data
      updateBatchJob(id, {
        status:   data.status   || 'processing',
        progress: data.progress || 0,
      })
      if (data.status !== 'complete' && data.status !== 'failed') {
        pollTimers.current[id] = setTimeout(() => pollJob(id), 2000)
      } else {
        delete pollTimers.current[id]
      }
    } catch {
      pollTimers.current[id] = setTimeout(() => pollJob(id), 3000)
    }
  }, [updateBatchJob])

  // ── Resume polling for any running jobs on mount ──────────────────────────
  useEffect(() => {
    batchJobs.forEach((job) => {
      if ((job.status === 'processing' || job.status === 'queued') && !pollTimers.current[job.id]) {
        pollJob(job.id)
      }
    })
    return () => {
      Object.values(pollTimers.current).forEach(clearTimeout)
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Add job to queue ──────────────────────────────────────────────────────
  const handleAddToQueue = useCallback(async () => {
    if (!clips.length || !audio) {
      setAddError('Upload at least one clip and audio track first.')
      return
    }
    if (batchJobs.length >= MAX_JOBS) {
      setAddError(`Max ${MAX_JOBS} jobs in queue.`)
      return
    }
    setAddError(null)
    setAdding(true)
    try {
      const jobPayload = {
        clip_ids:     clips.map((c) => c.id),
        audio_id:     audio.id,
        style:        formStyle,
        target_duration: formDuration,
        aspect_ratio:    formRatio,
      }
      const res = await startBatch([jobPayload])
      const batchId = res.data.batch_id || res.data.job_id
      const newJob = {
        id:          batchId,
        style:       formStyle,
        duration:    formDuration,
        aspectRatio: formRatio,
        status:      'queued',
        progress:    0,
      }
      addBatchJob(newJob)
      setShowForm(false)
      // Start polling
      pollTimers.current[batchId] = setTimeout(() => pollJob(batchId), 2000)
    } catch (err) {
      setAddError(err.message)
    }
    setAdding(false)
  }, [clips, audio, batchJobs.length, formStyle, formDuration, formRatio, addBatchJob, pollJob])

  const displayJobs = batchJobs.slice(-MAX_JOBS)

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 sm:px-6 py-4 border-b border-[#1e1e2e]">
        <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
          V
        </div>
        <h1 className="text-base sm:text-lg font-semibold text-slate-100 tracking-tight">Batch Queue</h1>
        <button
          onClick={() => setScreen('upload')}
          className="ml-auto text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          Home
        </button>
      </header>

      <main className="flex-1 px-4 sm:px-6 py-6 flex flex-col gap-6 max-w-2xl mx-auto w-full">

        {/* Queue header + add button */}
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-100">Job Queue</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {displayJobs.length} / {MAX_JOBS} jobs
            </p>
          </div>
          <button
            onClick={() => setShowForm((v) => !v)}
            disabled={batchJobs.length >= MAX_JOBS}
            className="px-3 py-2 text-xs sm:text-sm font-semibold bg-violet-600 hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
          >
            + Add to Queue
          </button>
        </div>

        {/* Add form */}
        {showForm && (
          <div className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl p-4 flex flex-col gap-4">
            <h3 className="text-sm font-semibold text-slate-300">New Batch Job</h3>

            {/* Style */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-slate-500">Style</label>
              <select
                value={formStyle}
                onChange={(e) => setFormStyle(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg text-slate-200 focus:outline-none focus:border-violet-600"
              >
                {STYLES.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
            </div>

            {/* Duration */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-slate-500">Target Duration</label>
              <div className="flex gap-2 flex-wrap">
                {DURATIONS.map((d) => (
                  <button
                    key={d}
                    onClick={() => setFormDuration(d)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      formDuration === d
                        ? 'bg-violet-600 text-white'
                        : 'bg-[#0a0a0f] border border-[#1e1e2e] text-slate-400 hover:border-violet-700 hover:text-slate-200'
                    }`}
                  >
                    {d}s
                  </button>
                ))}
              </div>
            </div>

            {/* Aspect ratio */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-slate-500">Aspect Ratio</label>
              <div className="flex gap-2 flex-wrap">
                {RATIOS.map((r) => (
                  <button
                    key={r}
                    onClick={() => setFormRatio(r)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      formRatio === r
                        ? 'bg-violet-600 text-white'
                        : 'bg-[#0a0a0f] border border-[#1e1e2e] text-slate-400 hover:border-violet-700 hover:text-slate-200'
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>

            {/* Uses current clips note */}
            <p className="text-xs text-slate-600">
              Uses current upload: {clips.length} clip{clips.length !== 1 ? 's' : ''}
              {audio ? ` + "${audio.name}"` : ' (no audio)'}
            </p>

            {addError && (
              <p className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
                {addError}
              </p>
            )}

            <div className="flex gap-2">
              <button
                onClick={handleAddToQueue}
                disabled={adding}
                className="flex-1 py-2 rounded-lg text-sm font-semibold bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white transition-colors"
              >
                {adding ? 'Adding...' : 'Add Job'}
              </button>
              <button
                onClick={() => { setShowForm(false); setAddError(null) }}
                className="px-4 py-2 rounded-lg text-sm text-slate-400 border border-[#1e1e2e] hover:border-slate-600 hover:text-slate-200 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Job list */}
        {displayJobs.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-center">
            <p className="text-slate-400 text-sm">No jobs in queue yet.</p>
            <p className="text-slate-600 text-xs">
              Click "Add to Queue" to batch-render multiple edits with different styles.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {displayJobs.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
