import React, { useState, useEffect, useCallback } from 'react'
import useEditStore from '../stores/editStore.js'
import { getDnaLibrary, saveDna, deleteDna } from '../api/client.js'

// ─── DNA Card ─────────────────────────────────────────────────────────────────
function DnaCard({ entry, onApply, onDelete }) {
  const avgDuration =
    entry.pacing?.avg_clip_duration != null
      ? `${Number(entry.pacing.avg_clip_duration).toFixed(1)}s avg clip`
      : null

  const lutBadge = entry.color?.lut

  return (
    <div className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-xl p-4 flex flex-col gap-3 hover:border-violet-700 transition-colors">
      {/* Name + delete */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-100 truncate">{entry.name}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            {entry.saved_at ? new Date(entry.saved_at).toLocaleDateString() : 'Unknown date'}
          </p>
        </div>
        <button
          onClick={() => onDelete(entry.name)}
          className="shrink-0 w-6 h-6 flex items-center justify-center rounded-full text-slate-600 hover:text-red-400 hover:bg-red-900/20 transition-colors"
          aria-label={`Delete ${entry.name}`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </div>

      {/* Description */}
      {entry.overall_style && (
        <p className="text-xs text-slate-400 leading-relaxed line-clamp-2">
          {entry.overall_style}
        </p>
      )}

      {/* Badges */}
      <div className="flex flex-wrap gap-1.5">
        {lutBadge && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-violet-900/40 border border-violet-700/50 text-violet-300">
            {lutBadge}
          </span>
        )}
        {avgDuration && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-[#1e1e2e] text-slate-400">
            {avgDuration}
          </span>
        )}
      </div>

      {/* Apply button */}
      <button
        onClick={() => onApply(entry)}
        className="mt-auto w-full py-2 rounded-lg text-xs font-semibold bg-violet-600 hover:bg-violet-700 text-white transition-colors"
      >
        Apply This Style
      </button>
    </div>
  )
}

// ─── Spinner ──────────────────────────────────────────────────────────────────
function Spinner() {
  return (
    <svg className="w-5 h-5 animate-spin text-violet-400" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function StyleDNALibrary() {
  const { setDnaLibraryOpen, setStyleDna, styleDna } = useEditStore()

  const [library,  setLibrary]  = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)

  // Save DNA state
  const [saveName,    setSaveName]    = useState('')
  const [saving,      setSaving]      = useState(false)
  const [saveError,   setSaveError]   = useState(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [showSaveForm, setShowSaveForm] = useState(false)

  // ── Load library ──────────────────────────────────────────────────────────
  const loadLibrary = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getDnaLibrary()
      setLibrary(res.data.library || [])
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    loadLibrary()
  }, [loadLibrary])

  // ── Close on Escape ───────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') setDnaLibraryOpen(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setDnaLibraryOpen])

  // ── Apply a DNA ───────────────────────────────────────────────────────────
  const handleApply = useCallback((entry) => {
    setStyleDna(entry, entry.name)
    setDnaLibraryOpen(false)
  }, [setStyleDna, setDnaLibraryOpen])

  // ── Delete a DNA ──────────────────────────────────────────────────────────
  const handleDelete = useCallback(async (name) => {
    if (!window.confirm(`Delete style DNA "${name}"? This cannot be undone.`)) return
    try {
      await deleteDna(name)
      setLibrary((prev) => prev.filter((e) => e.name !== name))
    } catch (err) {
      alert(`Failed to delete: ${err.message}`)
    }
  }, [])

  // ── Save current DNA ──────────────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    const name = saveName.trim()
    if (!name || !styleDna) return
    setSaving(true)
    setSaveError(null)
    setSaveSuccess(false)
    try {
      await saveDna({ name, style_dna: styleDna })
      setSaveSuccess(true)
      setSaveName('')
      setShowSaveForm(false)
      loadLibrary()
    } catch (err) {
      setSaveError(err.message)
    }
    setSaving(false)
  }, [saveName, styleDna, loadLibrary])

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget) setDnaLibraryOpen(false) }}
    >
      {/* Panel */}
      <div className="relative w-full max-w-3xl max-h-[90vh] bg-[#12121a] border border-[#1e1e2e] rounded-2xl flex flex-col overflow-hidden shadow-2xl">

        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-[#1e1e2e] shrink-0">
          <div className="w-7 h-7 rounded-lg bg-violet-600 flex items-center justify-center text-white font-bold text-xs">
            DNA
          </div>
          <h2 className="text-base font-semibold text-slate-100">Style DNA Library</h2>

          {/* Save current DNA */}
          {styleDna && (
            <div className="ml-auto mr-8 flex items-center gap-2">
              {!showSaveForm ? (
                <button
                  onClick={() => setShowSaveForm(true)}
                  className="px-3 py-1.5 text-xs font-medium bg-[#1e1e2e] hover:border-violet-600 border border-[#1e1e2e] text-slate-300 hover:text-white rounded-lg transition-colors"
                >
                  Save current DNA
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={saveName}
                    onChange={(e) => setSaveName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                    placeholder="Name this style..."
                    className="w-40 px-3 py-1.5 text-xs bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600"
                    autoFocus
                  />
                  <button
                    onClick={handleSave}
                    disabled={!saveName.trim() || saving}
                    className="px-3 py-1.5 text-xs font-semibold bg-violet-600 hover:bg-violet-700 disabled:opacity-40 text-white rounded-lg transition-colors"
                  >
                    {saving ? '...' : 'Save'}
                  </button>
                  <button
                    onClick={() => { setShowSaveForm(false); setSaveName('') }}
                    className="text-slate-500 hover:text-slate-300 text-xs"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Close */}
          <button
            onClick={() => setDnaLibraryOpen(false)}
            className="absolute top-4 right-4 w-7 h-7 flex items-center justify-center rounded-full text-slate-500 hover:text-slate-200 hover:bg-[#1e1e2e] transition-colors"
            aria-label="Close"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Feedback */}
        {saveError && (
          <div className="mx-5 mt-3 px-3 py-2 rounded-lg bg-red-900/20 border border-red-800 text-xs text-red-400 shrink-0">
            {saveError}
          </div>
        )}
        {saveSuccess && (
          <div className="mx-5 mt-3 px-3 py-2 rounded-lg bg-emerald-900/20 border border-emerald-800 text-xs text-emerald-400 shrink-0">
            Style DNA saved successfully.
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-12 gap-3 text-slate-500 text-sm">
              <Spinner />
              Loading library...
            </div>
          ) : error ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <p className="text-sm text-red-400">{error}</p>
              <button
                onClick={loadLibrary}
                className="text-xs text-violet-400 underline"
              >
                Retry
              </button>
            </div>
          ) : library.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-center">
              <p className="text-slate-400 text-sm">No saved Style DNAs yet.</p>
              <p className="text-slate-600 text-xs">
                Analyze a reference video on the Style screen, then save it here.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {library.map((entry) => (
                <DnaCard
                  key={entry.name}
                  entry={entry}
                  onApply={handleApply}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
