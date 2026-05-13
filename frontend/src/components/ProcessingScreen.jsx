import React, { useEffect, useRef, useCallback } from 'react'
import useEditStore from '../stores/editStore.js'
import { getJobStatus } from '../api/client.js'

// ─── Processing steps mapped from progress % ──────────────────────────────────
const STEPS = [
  { id: 'audio',     label: 'Analyzing audio',                    minPct: 0,  maxPct: 20  },
  { id: 'frames',    label: 'Extracting keyframes',               minPct: 20, maxPct: 35  },
  { id: 'claude',    label: 'Claude analyzing your footage',      minPct: 35, maxPct: 60  },
  { id: 'plan',      label: 'Generating edit plan',               minPct: 60, maxPct: 70  },
  { id: 'render',    label: 'Rendering video',                    minPct: 70, maxPct: 95  },
  { id: 'finalize',  label: 'Finalizing',                         minPct: 95, maxPct: 100 },
]

function getStepStatus(step, progress) {
  if (progress >= step.maxPct) return 'done'
  if (progress >= step.minPct) return 'active'
  return 'pending'
}

// ─── Step Row ─────────────────────────────────────────────────────────────────
function StepRow({ step, status, message }) {
  return (
    <div className={`flex items-start gap-3 py-2 transition-opacity duration-300 ${status === 'pending' ? 'opacity-40' : 'opacity-100'}`}>
      {/* Icon */}
      <div className="mt-0.5 w-5 h-5 flex items-center justify-center shrink-0">
        {status === 'done' && (
          <svg className="w-5 h-5 text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        )}
        {status === 'active' && (
          <svg className="w-5 h-5 text-violet-400 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        )}
        {status === 'pending' && (
          <div className="w-4 h-4 rounded-full border-2 border-slate-700" />
        )}
      </div>

      {/* Label */}
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${
          status === 'done' ? 'text-emerald-400' :
          status === 'active' ? 'text-slate-100' :
          'text-slate-500'
        }`}>
          {step.label}
        </p>
        {status === 'active' && message && (
          <p className="text-xs text-slate-500 mt-0.5 italic truncate">{message}</p>
        )}
      </div>
    </div>
  )
}

// ─── Error State ──────────────────────────────────────────────────────────────
function ErrorState({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center gap-4 py-8">
      <div className="w-16 h-16 rounded-full bg-red-900/30 border border-red-800 flex items-center justify-center text-3xl">
        ✗
      </div>
      <div className="text-center">
        <h3 className="text-lg font-semibold text-red-400 mb-1">Processing failed</h3>
        <p className="text-sm text-slate-500">{message || 'Something went wrong. Please try again.'}</p>
      </div>
      <button
        onClick={onRetry}
        className="px-6 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl font-medium text-sm transition-colors"
      >
        Try Again
      </button>
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function ProcessingScreen() {
  const {
    jobId,
    jobStatus,
    jobProgress,
    jobMessage,
    setJobState,
    setOutputUrl,
    setScreen,
  } = useEditStore()

  const wsRef = useRef(null)
  const pollRef = useRef(null)
  const mountedRef = useRef(true)

  // ── Handle incoming status data ───────────────────────────────────────────
  const handleStatusData = useCallback(
    (data) => {
      if (!mountedRef.current) return
      const progress = typeof data.progress === 'number' ? data.progress : 0
      const status = data.status || 'processing'
      const message = data.message || ''

      setJobState({ jobStatus: status, jobProgress: progress, jobMessage: message })

      if (status === 'complete') {
        setOutputUrl(`/api/job/${jobId}/result`)
        setScreen('preview')
      }
    },
    [jobId, setJobState, setOutputUrl, setScreen]
  )

  // ── Start polling fallback ────────────────────────────────────────────────
  const startPolling = useCallback(() => {
    if (pollRef.current) return
    const tick = async () => {
      if (!mountedRef.current) return
      try {
        const res = await getJobStatus(jobId)
        handleStatusData(res.data)
        if (res.data.status !== 'complete' && res.data.status !== 'failed') {
          pollRef.current = setTimeout(tick, 1000)
        }
      } catch {
        pollRef.current = setTimeout(tick, 2000)
      }
    }
    pollRef.current = setTimeout(tick, 1000)
  }, [jobId, handleStatusData])

  // ── Connect WebSocket ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!jobId) return
    mountedRef.current = true

    let wsConnected = false
    let ws

    try {
      ws = new WebSocket(`ws://localhost:8000/ws/${jobId}`)
      wsRef.current = ws

      ws.onopen = () => {
        wsConnected = true
        // Cancel polling if WS connected
        if (pollRef.current) {
          clearTimeout(pollRef.current)
          pollRef.current = null
        }
      }

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data)
          handleStatusData(data)
        } catch {
          // ignore unparseable messages
        }
      }

      ws.onerror = () => {
        if (!wsConnected) {
          startPolling()
        }
      }

      ws.onclose = (evt) => {
        if (!wsConnected || (evt.code !== 1000 && mountedRef.current)) {
          // WS closed unexpectedly — fall back to polling
          startPolling()
        }
      }
    } catch {
      startPolling()
    }

    // Safety net: if WS hasn't connected within 2 seconds, start polling anyway
    const safetyTimer = setTimeout(() => {
      if (!wsConnected && mountedRef.current) {
        startPolling()
      }
    }, 2000)

    return () => {
      mountedRef.current = false
      clearTimeout(safetyTimer)
      if (pollRef.current) {
        clearTimeout(pollRef.current)
        pollRef.current = null
      }
      if (wsRef.current) {
        try { wsRef.current.close() } catch {}
        wsRef.current = null
      }
    }
  }, [jobId, handleStatusData, startPolling])

  const handleRetry = useCallback(() => {
    setJobState({ jobStatus: 'idle', jobProgress: 0, jobMessage: '' })
    setScreen('style')
  }, [setJobState, setScreen])

  const isFailed = jobStatus === 'failed'

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex flex-col">
      {/* Header — no TopNav while processing */}
      <header className="flex items-center gap-3 px-4 sm:px-6 py-4 border-b border-[#1e1e2e]">
        <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
          V
        </div>
        <h1 className="text-base sm:text-lg font-semibold text-slate-100 tracking-tight">VisualAI Studio</h1>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-4 py-8 sm:py-10">
        <div className="w-full max-w-md flex flex-col gap-6 sm:gap-8">
          {isFailed ? (
            <ErrorState message={jobMessage} onRetry={handleRetry} />
          ) : (
            <>
              {/* Title */}
              <div className="text-center">
                <h2 className="text-2xl font-bold text-slate-100 mb-1">Creating your edit...</h2>
                <p className="text-sm text-slate-500">
                  Claude is analyzing your footage and building the edit plan.
                </p>
              </div>

              {/* Steps checklist */}
              <div className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl px-4 sm:px-5 py-3 sm:py-4 flex flex-col divide-y divide-[#1e1e2e]">
                {STEPS.map((step) => {
                  const status = getStepStatus(step, jobProgress)
                  return (
                    <StepRow
                      key={step.id}
                      step={step}
                      status={status}
                      message={status === 'active' ? jobMessage : null}
                    />
                  )
                })}
              </div>

              {/* Progress bar */}
              <div className="flex flex-col gap-2">
                <div className="flex justify-between text-xs text-slate-500">
                  <span>{jobMessage || 'Processing...'}</span>
                  <span className="text-violet-400 font-medium">{jobProgress}%</span>
                </div>
                <div className="w-full h-2 bg-[#1e1e2e] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500 ease-out"
                    style={{
                      width: `${jobProgress}%`,
                      background: 'linear-gradient(to right, #7c3aed, #a78bfa)',
                    }}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
